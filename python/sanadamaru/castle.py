"""真田丸の本体：偽の扉・目印入りの偽の鍵・記録と知らせ・締め出し。

Web の枠組み（FastAPI・Flask など）には依存しません。つなぎは asgi.py と wsgi.py です。
別の言語に移す時は、Castle.check の流れを写してください（docs/how-it-works.md）。
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import logging
import os
import re
import secrets
import threading
import time
import unicodedata
from collections import deque
from typing import Callable, Deque, Dict, List, Mapping, NamedTuple, Optional, Sequence, Tuple, Union
from urllib.parse import unquote_plus

from . import netaddr
from ._version import __version__
from .doors import NAME_PATTERN, Door, default_doors

logger = logging.getLogger("sanadamaru")

DEFAULT_KEY_PREFIX = "app_live_"
DEFAULT_KEY_HEADERS = ("authorization", "x-api-key", "x-admin-key", "x-auth-token", "x-access-token")
DEFAULT_NEVER_BLOCK = ("/health",)
CLIENT_IP_MODES = ("direct", "cloudflare", "x-forwarded-for")

# 他社の本物の鍵の書き出し。偽の鍵がこれに似ると、他社の検査の仕組みや、事故の対応をまどわせます（docs/lines.md の 4）。
FOREIGN_KEY_PREFIXES = (
    "AKIA", "ASIA",                                    # AWS
    "AIza",                                            # Google
    "sk_live_", "sk_test_", "rk_live_", "rk_test_",    # Stripe
    "pk_live_", "pk_test_", "whsec_",
    "ghp_", "gho_", "ghu_", "ghs_", "ghr_", "github_pat_",   # GitHub
    "glpat-",                                          # GitLab
    "xoxa-", "xoxb-", "xoxp-", "xoxr-",                # Slack
    "sk-",                                             # OpenAI・Anthropic など
    "SG.",                                             # SendGrid
    "npm_",                                            # npm
    "hf_",                                             # Hugging Face
)

_KEY_PREFIX_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{1,31}")
_TOKEN_HEX = 32              # 偽の鍵の、書き出しの後ろの長さ（16進）
_SCAN_LIMIT = 16384          # 1つの値の中で、偽の鍵を探す長さの上限（重い問い合わせで手間取らない）
# 記録に残さない文字の種類：制御文字（Cc）・見えない書式文字（Cf＝表示の向きを変える U+202E など）・
# 行と段落の区切り（Zl・Zp）・対になっていないサロゲート（Cs）
_UNSAFE_CATEGORIES = frozenset(("Cc", "Cf", "Zl", "Zp", "Cs"))
_DOOR_HEADERS = (("x-content-type-options", "nosniff"), ("cache-control", "no-store"))


class Reply(NamedTuple):
    """真田丸が自分で返す答え。Castle.check が None を返した時は、本物の窓口へ通します。"""

    status: int
    content_type: str
    body: bytes
    headers: Tuple[Tuple[str, str], ...] = ()


FORBIDDEN = Reply(403, "text/plain; charset=utf-8", b"forbidden", (("cache-control", "no-store"),))


def _unsafe(ch: str) -> bool:
    return unicodedata.category(ch) in _UNSAFE_CATEGORIES


def _clean(value: object, limit: int) -> str:
    """記録に残す前に、改行・制御文字・表示の向きを変える文字などを「?」に替えて、長さをそろえる（記録の書き換えを防ぐ）。"""
    text = ("" if value is None else str(value))[:limit]
    return "".join("?" if _unsafe(ch) else ch for ch in text)


def _from_web_page(headers: Mapping[str, str]) -> bool:
    """よそのページ（や自分のページ）に埋め込まれた読み込み・リンクから来た問い合わせか。

    ブラウザは、画像・スクリプト・リンクの読み込みに `Sec-Fetch-Site`（cross-site・same-site・same-origin）を付けます。
    アドレス欄に打ち込んだ時だけ `none` です。古いブラウザは `Sec-Fetch-*` を送らないので、`Referer`・`Origin` も見ます。
    これらがある時は、閲覧者本人ではなく、ページを書いた誰かが読み込ませた可能性があるので、締め出しません。
    """
    site = (headers.get("sec-fetch-site") or "").strip().lower()
    if site and site != "none":
        return True
    return bool(headers.get("referer") or headers.get("origin"))


def _norm(path: str) -> str:
    """住所をそろえる（`//` を `/` に、最後の `/` を取る）。"""
    p = re.sub(r"/{2,}", "/", path or "/")
    if len(p) > 1 and p.endswith("/"):
        p = p.rstrip("/") or "/"
    return p


def _under(path: str, bases: Sequence[str]) -> bool:
    for b in bases:
        if path == b or path.startswith(b + "/"):
            return True
    return False


def _check_name(kind: str, value: str) -> None:
    if not isinstance(value, str) or not NAME_PATTERN.fullmatch(value):
        raise ValueError(f"{kind}は、英小文字・数字・_・- の32文字までにしてください：{value!r}")


class Castle:
    """偽の扉と偽の鍵を持つ出城。1つの Castle を、アプリ全体で共有します。

    すべての設定に、安全な側の既定があります。締め出し（ban）は既定でオフです。
    """

    def __init__(
        self,
        *,
        secret: Union[str, bytes, None] = None,
        doors: Optional[Mapping[str, Door]] = None,
        key_prefix: str = DEFAULT_KEY_PREFIX,
        key_headers: Sequence[str] = DEFAULT_KEY_HEADERS,
        ban: bool = False,
        ban_seconds: int = 86400,
        client_ip: str = "direct",
        trusted_hops: int = 1,
        never_block: Sequence[str] = DEFAULT_NEVER_BLOCK,
        trusted_proxies: Sequence[str] = (),
        alert: Optional[Callable[[dict], None]] = None,
        alert_cooldown: float = 3600.0,
        log_max: int = 500,
        ban_max: int = 10000,
        log_per_minute: int = 60,
    ) -> None:
        # まちがった設定のままでは動かさない（動き出してから気づくと、無関係な人を巻き込むため）
        if client_ip not in CLIENT_IP_MODES:
            raise ValueError(f"client_ip は {', '.join(CLIENT_IP_MODES)} のどれかにしてください：{client_ip!r}")
        if int(trusted_hops) < 1:
            raise ValueError("trusted_hops は1以上にしてください（前に立つ仕組みの数）")
        if not isinstance(key_prefix, str) or not _KEY_PREFIX_PATTERN.fullmatch(key_prefix):
            raise ValueError(f"key_prefix は、英数字と _ . - の2〜32文字にしてください：{key_prefix!r}")
        for foreign in FOREIGN_KEY_PREFIXES:
            if key_prefix.startswith(foreign):
                raise ValueError(f"key_prefix {key_prefix!r} は他社の鍵の形（{foreign}…）に似ています。"
                                 "自分のサービスの鍵に似せてください（docs/lines.md の 4）")
        if int(ban_seconds) <= 0 or int(log_max) <= 0 or int(ban_max) <= 0 or int(log_per_minute) <= 0:
            raise ValueError("ban_seconds・log_max・ban_max・log_per_minute は1以上にしてください")
        if isinstance(trusted_proxies, str):
            raise ValueError("trusted_proxies は範囲の一覧にしてください（例：[\"10.0.0.0/8\"]）")
        proxies = netaddr.networks(trusted_proxies)
        lifelines: List[str] = []
        for p in never_block:
            if not isinstance(p, str) or not p.startswith("/") or _norm(p) == "/":
                raise ValueError(f"never_block には「/」以外の住所を書いてください：{p!r}")
            lifelines.append(_norm(p))

        if secret is None:
            self._secret = secrets.token_bytes(32)
            self.secret_is_ephemeral = True
            logger.warning("[sanadamaru] secret が未設定です。起動のたびに偽の鍵が変わり、前の起動で持ち出された鍵は"
                           "照合できません（SANADAMARU_SECRET を設定してください）")
        else:
            raw = secret.encode("utf-8") if isinstance(secret, str) else bytes(secret)
            if len(raw) < 16:
                raise ValueError('secret は16バイト以上にしてください（作り方の例：'
                                 'python -c "import secrets; print(secrets.token_hex(32))"）')
            self._secret = raw
            self.secret_is_ephemeral = False

        self.key_prefix = key_prefix
        self.key_headers = tuple(h.lower() for h in key_headers)
        self.ban = bool(ban)
        self.ban_seconds = int(ban_seconds)
        self.client_ip_mode = client_ip
        self.trusted_hops = int(trusted_hops)
        self.trusted_proxies = proxies
        self.never_block = tuple(lifelines)
        self.alert = alert
        self.alert_cooldown = float(alert_cooldown)

        self._lock = threading.Lock()
        self._log: Deque[dict] = deque(maxlen=int(log_max))
        self._ban_max = int(ban_max)
        self._banned: Dict[str, float] = {}                 # 送り元の番号 -> 締め出しの期限（epoch 秒）
        self._alert_last: Dict[Tuple[str, str], float] = {}
        self._totals = {"door": 0, "bait_key": 0}
        self._by_door: Dict[str, int] = {}
        self._bait_by_marker: Dict[str, int] = {}
        self._blocked = 0
        self._log_per_minute = int(log_per_minute)
        self._log_window = 0.0               # 記録の行を数えている1分の始まり
        self._log_lines = 0                  # その1分に出した行の数
        self._log_suppressed = 0             # 出さずに数えた行の数（次に出す行に添える）
        self._log_suppressed_total = 0
        self._warned_unknown_ip = False
        self._keys: Dict[str, Tuple[str, str]] = {}        # 偽の鍵 -> (目印, 欄)
        self._key_pattern = re.compile(re.escape(key_prefix) + "[0-9a-f]{%d}" % _TOKEN_HEX)
        self._doors: Dict[str, Tuple[str, Reply]] = {}     # そろえた住所 -> (目印, 答え)
        for path, door in (default_doors() if doors is None else doors).items():
            self._add_door(path, door)

    # ------------------------------------------------------------------
    # 環境変数から作る
    # ------------------------------------------------------------------
    @classmethod
    def from_env(cls, environ: Optional[Mapping[str, str]] = None, **overrides) -> "Castle":
        """SANADAMARU_* の環境変数から作る。overrides に渡した設定が優先します。

        SANADAMARU_SECRET・SANADAMARU_BAN（1でオン）・SANADAMARU_BAN_SECONDS・SANADAMARU_CLIENT_IP・
        SANADAMARU_TRUSTED_HOPS・SANADAMARU_TRUSTED_PROXIES（カンマ区切りの範囲）・SANADAMARU_KEY_PREFIX・
        SANADAMARU_NEVER_BLOCK（カンマ区切り・/health に足す）・SANADAMARU_LOG_PER_MINUTE
        """
        env = os.environ if environ is None else environ
        kw: dict = {}
        if env.get("SANADAMARU_SECRET"):
            kw["secret"] = env["SANADAMARU_SECRET"]
        if env.get("SANADAMARU_BAN"):
            kw["ban"] = env["SANADAMARU_BAN"].strip() == "1"
        if env.get("SANADAMARU_BAN_SECONDS"):
            kw["ban_seconds"] = int(env["SANADAMARU_BAN_SECONDS"])
        if env.get("SANADAMARU_CLIENT_IP"):
            kw["client_ip"] = env["SANADAMARU_CLIENT_IP"].strip()
        if env.get("SANADAMARU_TRUSTED_HOPS"):
            kw["trusted_hops"] = int(env["SANADAMARU_TRUSTED_HOPS"])
        if env.get("SANADAMARU_TRUSTED_PROXIES"):
            kw["trusted_proxies"] = tuple(p.strip() for p in env["SANADAMARU_TRUSTED_PROXIES"].split(",") if p.strip())
        if env.get("SANADAMARU_LOG_PER_MINUTE"):
            kw["log_per_minute"] = int(env["SANADAMARU_LOG_PER_MINUTE"])
        if env.get("SANADAMARU_KEY_PREFIX"):
            kw["key_prefix"] = env["SANADAMARU_KEY_PREFIX"].strip()
        if env.get("SANADAMARU_NEVER_BLOCK"):
            extra = [p.strip() for p in env["SANADAMARU_NEVER_BLOCK"].split(",") if p.strip()]
            kw["never_block"] = tuple(DEFAULT_NEVER_BLOCK) + tuple(extra)
        kw.update(overrides)
        return cls(**kw)

    # ------------------------------------------------------------------
    # 扉と偽の鍵
    # ------------------------------------------------------------------
    def _add_door(self, path: str, door: Door) -> None:
        if not isinstance(door, Door):
            raise TypeError(f"{path!r} の扉は Door で作ってください")
        if (not isinstance(path, str) or not path.startswith("/") or any(c in path for c in "?# ")
                or any(_unsafe(c) for c in path)):
            raise ValueError(f"扉の住所が正しくありません：{path!r}")
        p = _norm(path)
        if p == "/":
            raise ValueError("「/」は扉にできません（すべての利用者が触れてしまいます）")
        if _under(p, self.never_block):
            raise ValueError(f"扉 {path} が、止めない窓口（never_block）と重なっています")
        body = door.template(self._key_maker(door.marker))
        if not isinstance(body, str):
            raise TypeError(f"{path!r} の扉の template は、文字列を返してください")
        self._doors[p] = (door.marker, Reply(200, door.content_type, body.encode("utf-8"), _DOOR_HEADERS))

    def _key_maker(self, marker: str) -> Callable[..., str]:
        def key(slot: str = "key") -> str:
            return self.bait_key(marker, slot)
        return key

    def bait_key(self, marker: str, slot: str = "key") -> str:
        """目印と欄ごとに決まる偽の鍵を作り、照合の一覧に載せる。

        同じ secret なら、何度呼んでも同じ鍵になります（本物の設定ファイルも、開くたびには変わらないため）。
        扉の外（偽の書類など）に置く鍵も、ここで作れば、使われた時に気づけます。
        """
        _check_name("目印", marker)
        _check_name("欄の名前", slot)
        mac = hmac.new(self._secret, f"sanadamaru/v1\x00{marker}\x00{slot}".encode("utf-8"), hashlib.sha256)
        key = self.key_prefix + mac.hexdigest()[:_TOKEN_HEX]
        with self._lock:
            self._keys[key] = (marker, slot)
        return key

    @property
    def doors(self) -> List[Tuple[str, str]]:
        """（住所, 目印）の一覧。"""
        return sorted((p, m) for p, (m, _) in self._doors.items())

    # ------------------------------------------------------------------
    # 1つの問い合わせを見る
    # ------------------------------------------------------------------
    def check(
        self,
        *,
        path: str,
        headers: Mapping[str, str],
        query: str = "",
        peer: Optional[str] = "",
        method: str = "GET",
        now: Optional[float] = None,
    ) -> Optional[Reply]:
        """1つの問い合わせを見て、真田丸が答える時は Reply を、本物の窓口へ通す時は None を返す。

        headers は、名前を小文字にした {名前: 値}。query は `?` より後ろ（URL のまま）。peer は直接の相手の番号。
        見る順番：① 締め出し中か ② 偽の扉か ③ 偽の鍵が出されたか。止めない窓口（never_block）は、①で止めず、③でも断りません。
        """
        now = time.time() if now is None else now
        p = _norm(path)
        ip = netaddr.client_ip(self.client_ip_mode, headers, peer, self.trusted_hops, self.trusted_proxies)
        if not ip and peer and not self._warned_unknown_ip and self.client_ip_mode != "direct":
            self._warned_unknown_ip = True
            logger.warning("[sanadamaru] 送り元の番号を確かめられませんでした。この問い合わせでは締め出しません"
                           "（client_ip・trusted_hops・trusted_proxies の設定を確かめてください：docs/deploy.md）")
        lifeline = _under(p, self.never_block)
        if self.ban and not lifeline and self._is_banned(ip, now):
            with self._lock:
                self._blocked += 1
            return FORBIDDEN
        door = self._doors.get(p)
        if door is not None:
            marker, reply = door
            self._record("door", path, p, marker, "", ip, headers, method, now)
            return reply
        hit = self._find_key(headers, query)
        if hit is not None:
            marker, slot = hit
            self._record("bait_key", path, p, marker, slot, ip, headers, method, now)
            return None if lifeline else FORBIDDEN
        return None

    def _find_key(self, headers: Mapping[str, str], query: str) -> Optional[Tuple[str, str]]:
        values = [v for v in (headers.get(name) for name in self.key_headers) if v]
        auth = headers.get("authorization") or ""
        if "authorization" in self.key_headers and auth[:6].lower() == "basic ":
            raw = auth[6:].strip()[:_SCAN_LIMIT]
            raw += "=" * (-len(raw) % 4)
            try:
                values.append(base64.b64decode(raw).decode("utf-8", "replace"))
            except (binascii.Error, ValueError):
                pass
        if query:
            values.append(unquote_plus(query[:_SCAN_LIMIT]))
        for value in values:
            value = value[:_SCAN_LIMIT]
            if self.key_prefix not in value:
                continue
            for m in self._key_pattern.finditer(value):
                hit = self._keys.get(m.group(0))
                if hit is not None:
                    return hit
        return None

    # ------------------------------------------------------------------
    # 記録・知らせ・締め出し
    # ------------------------------------------------------------------
    def _record(self, kind: str, raw_path: str, path: str, marker: str, slot: str, ip: str,
                headers: Mapping[str, str], method: str, now: float) -> dict:
        event = {
            "at": int(now),
            "kind": kind,
            "method": _clean(method, 10),
            "path": _clean(raw_path, 120),
            "marker": marker,
            "slot": slot,
            "ip": ip,
            "ip_prefix": netaddr.prefix(ip),
            "ua": _clean(headers.get("user-agent"), 120),
            "from_page": _from_web_page(headers),
            "banned": False,
        }
        with self._lock:
            # ページに埋め込まれた読み込みは、閲覧者本人の操作とは限らないので、締め出さない（docs/lines.md の 5）
            if self.ban and netaddr.banable(ip) and not event["from_page"]:
                event["banned"] = self._ban_locked(ip, now)
            self._log.append(event)
            self._totals[kind] += 1
            if kind == "door":
                self._by_door[path] = self._by_door.get(path, 0) + 1
            else:
                self._bait_by_marker[marker] = self._bait_by_marker.get(marker, 0) + 1
            emit, skipped = self._log_slot_locked(now)
        if emit:
            logger.warning("[sanadamaru] %s path=%s marker=%s%s from=%s%s%s%s", kind, event["path"], marker,
                           f" slot={slot}" if slot else "", event["ip_prefix"] or "?",
                           " from_page" if event["from_page"] else "",
                           " banned" if event["banned"] else "",
                           f" (+{skipped} not logged)" if skipped else "")
        self._maybe_alert(event, now)
        return event

    def _log_slot_locked(self, now: float) -> Tuple[bool, int]:
        """記録の行を出してよいか。1分に log_per_minute 行まで（同じ問い合わせの繰り返しで、記録の置き場を埋めさせない）。

        出さなかった行は数えておき、次に出す行に「(+N not logged)」と添えます。件数は report() にも残ります。
        """
        if now - self._log_window >= 60 or now < self._log_window:
            self._log_window = now
            self._log_lines = 0
        if self._log_lines >= self._log_per_minute:
            self._log_suppressed += 1
            self._log_suppressed_total += 1
            return False, 0
        self._log_lines += 1
        skipped, self._log_suppressed = self._log_suppressed, 0
        return True, skipped

    def _maybe_alert(self, event: dict, now: float) -> None:
        if self.alert is None:
            return
        k = (event["kind"], event["marker"])
        with self._lock:
            last = self._alert_last.get(k)
            if last is not None and now - last < self.alert_cooldown:
                return
            self._alert_last[k] = now
        payload = {k2: v for k2, v in event.items() if k2 != "ip"}   # 知らせには、番号の頭だけ
        try:
            self.alert(payload)
        except Exception as e:   # 知らせが失敗しても、守りは止めない
            logger.warning("[sanadamaru] 知らせを送れませんでした：%s", type(e).__name__)

    def _ban_locked(self, ip: str, now: float) -> bool:
        if ip not in self._banned and len(self._banned) >= self._ban_max:
            for k in [k for k, t in self._banned.items() if t <= now]:
                del self._banned[k]
            if len(self._banned) >= self._ban_max:
                return False   # 番号を変えて大量に来ても、メモリを食いつぶさない
        self._banned[ip] = now + self.ban_seconds
        return True

    def _is_banned(self, ip: str, now: float) -> bool:
        if not ip:
            return False
        with self._lock:
            until = self._banned.get(ip)
            if until is None:
                return False
            if until <= now:
                del self._banned[ip]
                return False
            return True

    # ------------------------------------------------------------------
    # 一覧
    # ------------------------------------------------------------------
    def report(self, now: Optional[float] = None) -> dict:
        """件数と、最近の50件（新しい順）。送り元の番号をそのまま含むので、管理の鍵で守った窓口からだけ出してください。"""
        now = time.time() if now is None else now
        with self._lock:
            log = list(self._log)
            return {
                "version": __version__,
                "ban_enabled": self.ban,
                "ban_seconds": self.ban_seconds,
                "client_ip": self.client_ip_mode,
                "secret_is_ephemeral": self.secret_is_ephemeral,
                "banned_now": sum(1 for t in self._banned.values() if t > now),
                "blocked": self._blocked,
                "log_lines_not_written": self._log_suppressed_total,
                "total": dict(self._totals),
                "by_door": dict(self._by_door),
                "bait_key_by_marker": dict(self._bait_by_marker),
                "sources": len({e["ip"] for e in log if e["ip"]}),
                "recent": [dict(e) for e in reversed(log[-50:])],
            }

    def reset(self) -> None:
        """記録と締め出しを空にする（テスト用）。偽の鍵と扉はそのまま。"""
        with self._lock:
            self._log.clear()
            self._banned.clear()
            self._alert_last.clear()
            self._totals = {"door": 0, "bait_key": 0}
            self._by_door.clear()
            self._bait_by_marker.clear()
            self._blocked = 0
            self._log_window = 0.0
            self._log_lines = 0
            self._log_suppressed = 0
            self._log_suppressed_total = 0


def log_alert(event: dict) -> None:
    """知らせを ERROR の記録として出す。Sentry などは ERROR を拾うので、これを alert に渡すと運営者に届きます。"""
    what = "偽の鍵が使われました" if event.get("kind") == "bait_key" else "偽の扉に触れました"
    logger.error("[sanadamaru] 知らせ：%s path=%s marker=%s from=%s", what, event.get("path"),
                 event.get("marker"), event.get("ip_prefix") or "?")
