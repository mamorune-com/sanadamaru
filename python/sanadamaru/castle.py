"""The core of sanadamaru: decoy doors, marked bait keys, records and alerts, and blocking.

It does not depend on any web framework (FastAPI, Flask and so on). The adapters are asgi.py and wsgi.py.
When porting to another language, copy the flow of Castle.check (docs/en/how-it-works.md).
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

# Prefixes of other companies' real keys. Bait keys that look like these would confuse their scanners and incident response (rule 4 in docs/en/lines.md).
FOREIGN_KEY_PREFIXES = (
    "AKIA", "ASIA",                                    # AWS
    "AIza",                                            # Google
    "sk_live_", "sk_test_", "rk_live_", "rk_test_",    # Stripe
    "pk_live_", "pk_test_", "whsec_",
    "ghp_", "gho_", "ghu_", "ghs_", "ghr_", "github_pat_",   # GitHub
    "glpat-",                                          # GitLab
    "xoxa-", "xoxb-", "xoxp-", "xoxr-",                # Slack
    "sk-",                                             # OpenAI, Anthropic and others
    "SG.",                                             # SendGrid
    "npm_",                                            # npm
    "hf_",                                             # Hugging Face
)

_KEY_PREFIX_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{1,31}")
_TOKEN_HEX = 32              # length of a bait key after its prefix (hex characters)
_SCAN_LIMIT = 16384          # how far to search for bait keys in one value (so huge requests stay cheap)
# Character categories never written to records: control characters (Cc), invisible formatting characters
# (Cf, such as U+202E which reverses text direction), line and paragraph separators (Zl, Zp) and lone surrogates (Cs)
_UNSAFE_CATEGORIES = frozenset(("Cc", "Cf", "Zl", "Zp", "Cs"))
_DOOR_HEADERS = (("x-content-type-options", "nosniff"), ("cache-control", "no-store"))


class Reply(NamedTuple):
    """A response sanadamaru returns itself. When Castle.check returns None, the request goes on to your real endpoints."""

    status: int
    content_type: str
    body: bytes
    headers: Tuple[Tuple[str, str], ...] = ()


FORBIDDEN = Reply(403, "text/plain; charset=utf-8", b"forbidden", (("cache-control", "no-store"),))


def _unsafe(ch: str) -> bool:
    return unicodedata.category(ch) in _UNSAFE_CATEGORIES


def _clean(value: object, limit: int) -> str:
    """Before recording, replace line breaks, control characters, direction-changing characters and so on with "?" and cap the length (so records cannot be forged)."""
    text = ("" if value is None else str(value))[:limit]
    return "".join("?" if _unsafe(ch) else ch for ch in text)


def _from_web_page(headers: Mapping[str, str]) -> bool:
    """Whether a request may have come from something embedded in a page (someone else's or your own).

    Browsers send `Sec-Fetch-Site` (cross-site, same-site, same-origin) when loading images, scripts and links.
    It is `none` only when the address was typed in. Older browsers do not send `Sec-Fetch-*`, so `Referer` and `Origin` are checked too.

    However, loads of http:// addresses carry no `Sec-Fetch-*`, and a page with `referrerpolicy="no-referrer"`
    sends no `Referer`. So when there are no marks at all but the user agent identifies itself as a browser (`Mozilla/…`),
    we cannot rule out a page load, and the source is not blocked. Tools that fake a browser user agent escape blocking,
    but are still recorded. We choose not to catch uninvolved visitors (rule 5 in docs/en/lines.md).
    """
    site = (headers.get("sec-fetch-site") or "").strip().lower()
    if site and site != "none":
        return True
    if headers.get("referer") or headers.get("origin"):
        return True
    if site == "none":
        return False                     # typed in or opened from a bookmark (a page cannot produce this)
    return (headers.get("user-agent") or "").lstrip().lower().startswith("mozilla/")


def _norm(path: str) -> str:
    """Normalize a path (`//` becomes `/`, a trailing `/` is removed)."""
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
        raise ValueError(f"{kind} must be up to 32 lowercase letters, digits, _ or -: {value!r}")


class Castle:
    """The outpost that holds the decoy doors and bait keys. Share one Castle across the whole app.

    Every setting has a safe default. Blocking (ban) is off by default.
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
        # Refuse to start with a wrong setting (finding out after it runs could catch uninvolved people)
        if client_ip not in CLIENT_IP_MODES:
            raise ValueError(f"client_ip must be one of {', '.join(CLIENT_IP_MODES)}: {client_ip!r}")
        if int(trusted_hops) < 1:
            raise ValueError("trusted_hops must be 1 or more (the number of proxies in front of the app)")
        if not isinstance(key_prefix, str) or not _KEY_PREFIX_PATTERN.fullmatch(key_prefix):
            raise ValueError(f"key_prefix must be 2 to 32 letters, digits, _, . or -: {key_prefix!r}")
        for foreign in FOREIGN_KEY_PREFIXES:
            if key_prefix.startswith(foreign):
                raise ValueError(f"key_prefix {key_prefix!r} looks like another company's key format ({foreign}…). "
                                 "Make it look like your own service's keys (see rule 4 in docs/en/lines.md)")
        if int(ban_seconds) <= 0 or int(log_max) <= 0 or int(ban_max) <= 0 or int(log_per_minute) <= 0:
            raise ValueError("ban_seconds, log_max, ban_max and log_per_minute must be 1 or more")
        if isinstance(trusted_proxies, str):
            raise ValueError("trusted_proxies must be a list of ranges (for example [\"10.0.0.0/8\"])")
        proxies = netaddr.networks(trusted_proxies)
        lifelines: List[str] = []
        for p in never_block:
            if not isinstance(p, str) or not p.startswith("/") or _norm(p) == "/":
                raise ValueError(f"never_block paths must not be \"/\": {p!r}")
            lifelines.append(_norm(p))

        if secret is None:
            self._secret = secrets.token_bytes(32)
            self.secret_is_ephemeral = True
            logger.warning("[sanadamaru] no secret is set. Bait keys will change on every start, and keys taken before a restart "
                           "cannot be matched (set SANADAMARU_SECRET)")
        else:
            raw = secret.encode("utf-8") if isinstance(secret, str) else bytes(secret)
            if len(raw) < 16:
                raise ValueError('secret must be at least 16 bytes (to make one: '
                                 'python -c "import secrets; print(secrets.token_hex(32))")')
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
        self._banned: Dict[str, float] = {}                 # source address -> block expiry (epoch seconds)
        self._alert_last: Dict[Tuple[str, str], float] = {}
        self._totals = {"door": 0, "bait_key": 0}
        self._by_door: Dict[str, int] = {}
        self._bait_by_marker: Dict[str, int] = {}
        self._blocked = 0
        self._log_per_minute = int(log_per_minute)
        self._log_window = 0.0               # start of the minute in which log lines are counted
        self._log_lines = 0                  # log lines written in that minute
        self._log_suppressed = 0             # lines counted but not written (reported on the next line)
        self._log_suppressed_total = 0
        self._warned_unknown_ip = False
        self._keys: Dict[str, Tuple[str, str]] = {}        # bait key -> (marker, field)
        self._key_pattern = re.compile(re.escape(key_prefix) + "[0-9a-f]{%d}" % _TOKEN_HEX)
        self._doors: Dict[str, Tuple[str, Reply]] = {}     # normalized path -> (marker, reply)
        for path, door in (default_doors() if doors is None else doors).items():
            self._add_door(path, door)

    # ------------------------------------------------------------------
    # Building from environment variables
    # ------------------------------------------------------------------
    @classmethod
    def from_env(cls, environ: Optional[Mapping[str, str]] = None, **overrides) -> "Castle":
        """Build from SANADAMARU_* environment variables. Settings passed in overrides take precedence.

        SANADAMARU_SECRET, SANADAMARU_BAN (1 = on), SANADAMARU_BAN_SECONDS, SANADAMARU_CLIENT_IP,
        SANADAMARU_TRUSTED_HOPS, SANADAMARU_TRUSTED_PROXIES (comma-separated ranges), SANADAMARU_KEY_PREFIX,
        SANADAMARU_NEVER_BLOCK (comma-separated, added to /health), SANADAMARU_LOG_PER_MINUTE
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
    # Doors and bait keys
    # ------------------------------------------------------------------
    def _add_door(self, path: str, door: Door) -> None:
        if not isinstance(door, Door):
            raise TypeError(f"the door for {path!r} must be a Door")
        if (not isinstance(path, str) or not path.startswith("/") or any(c in path for c in "?# ")
                or any(_unsafe(c) for c in path)):
            raise ValueError(f"invalid door path: {path!r}")
        p = _norm(path)
        if p == "/":
            raise ValueError("\"/\" cannot be a door (every user would touch it)")
        if _under(p, self.never_block):
            raise ValueError(f"door {path} overlaps a never_block path")
        body = door.template(self._key_maker(door.marker))
        if not isinstance(body, str):
            raise TypeError(f"the template of the door for {path!r} must return a string")
        self._doors[p] = (door.marker, Reply(200, door.content_type, body.encode("utf-8"), _DOOR_HEADERS))

    def _key_maker(self, marker: str) -> Callable[..., str]:
        def key(slot: str = "key") -> str:
            return self.bait_key(marker, slot)
        return key

    def bait_key(self, marker: str, slot: str = "key") -> str:
        """Make the bait key for a marker and field, and add it to the list of keys to watch for.

        With the same secret it always returns the same key (a real config file does not change between reads either).
        Keys you plant outside the doors (in a fake document, for example) can be made here too, so you notice when they are used.
        """
        _check_name("marker", marker)
        _check_name("field name", slot)
        mac = hmac.new(self._secret, f"sanadamaru/v1\x00{marker}\x00{slot}".encode("utf-8"), hashlib.sha256)
        key = self.key_prefix + mac.hexdigest()[:_TOKEN_HEX]
        with self._lock:
            self._keys[key] = (marker, slot)
        return key

    @property
    def doors(self) -> List[Tuple[str, str]]:
        """List of (path, marker) pairs."""
        return sorted((p, m) for p, (m, _) in self._doors.items())

    # ------------------------------------------------------------------
    # Checking one request
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
        """Check one request. Returns a Reply when sanadamaru answers, or None to pass the request to your real endpoints.

        headers is {name: value} with lowercase names. query is everything after `?` (still URL-encoded). peer is the direct peer's address.
        Order of checks: (1) is the source blocked, (2) is this a decoy door, (3) was a bait key presented.
        never_block paths are not stopped at (1) and not refused at (3).
        """
        now = time.time() if now is None else now
        p = _norm(path)
        ip = netaddr.client_ip(self.client_ip_mode, headers, peer, self.trusted_hops, self.trusted_proxies)
        if not ip and peer and not self._warned_unknown_ip and self.client_ip_mode != "direct":
            self._warned_unknown_ip = True
            logger.warning("[sanadamaru] could not determine the client address, so this source cannot be banned "
                           "(decoy doors and bait keys still answer as usual; check client_ip, trusted_hops and "
                           "trusted_proxies: docs/en/deploy.md)")
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
    # Records, alerts and blocking
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
            # A load embedded in a page is not necessarily the visitor's own action, so do not block it (rule 5 in docs/en/lines.md)
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
        """Whether a log line may be written. Up to log_per_minute lines per minute (so repeated requests cannot flood your logs).

        Lines not written are counted and the next line ends with "(+N not logged)". The count also appears in report().
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
        payload = {k2: v for k2, v in event.items() if k2 != "ip"}   # alerts get only the first part of the address
        try:
            self.alert(payload)
        except Exception as e:   # a failed alert never stops the defense
            logger.warning("[sanadamaru] failed to send an alert: %s", type(e).__name__)

    def _ban_locked(self, ip: str, now: float) -> bool:
        if ip not in self._banned and len(self._banned) >= self._ban_max:
            for k in [k for k, t in self._banned.items() if t <= now]:
                del self._banned[k]
            if len(self._banned) >= self._ban_max:
                return False   # rotating addresses cannot exhaust memory
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
    # Reports
    # ------------------------------------------------------------------
    def report(self, now: Optional[float] = None) -> dict:
        """Counts and the 50 most recent records (newest first). Contains full source addresses, so only serve it behind an admin key."""
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
        """Clear records and blocks (for tests). Bait keys and doors stay."""
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
    """Log an alert at ERROR level. Tools such as Sentry pick up ERROR logs, so passing this as alert gets it to the people who run the service."""
    what = "a bait key was used" if event.get("kind") == "bait_key" else "a decoy door was touched"
    logger.error("[sanadamaru] ALERT: %s path=%s marker=%s from=%s", what, event.get("path"),
                 event.get("marker"), event.get("ip_prefix") or "?")
