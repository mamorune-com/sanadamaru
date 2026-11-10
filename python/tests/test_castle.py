"""Castle（本体）のテスト。番号は、テスト用に「公開されている形」の番号を使います（相手に届くことはありません）。"""
import base64
import logging
from urllib.parse import quote

import pytest

from sanadamaru import FORBIDDEN, Castle, Door, default_doors
from sanadamaru.castle import FOREIGN_KEY_PREFIXES

SECRET = "test-secret-0123456789abcdef"
PROBER = "5.6.7.8"
NEIGHBOR = "1.2.3.4"


def make(**kw):
    kw.setdefault("secret", SECRET)
    return Castle(**kw)


def ask(c, path, headers=None, query="", peer=PROBER, method="GET", now=1000.0):
    return c.check(path=path, headers=headers or {}, query=query, peer=peer, method=method, now=now)


# ---------------------------------------------------------------- 偽の扉

def test_door_returns_fake_page_and_records():
    c = make()
    r = ask(c, "/.env", headers={"user-agent": "scanner/1.0"})
    assert r.status == 200
    assert r.content_type.startswith("text/plain")
    assert b"DB_PASSWORD=app_live_" in r.body
    assert ("cache-control", "no-store") in r.headers
    assert ("x-content-type-options", "nosniff") in r.headers
    rep = c.report()
    assert rep["total"] == {"door": 1, "bait_key": 0}
    assert rep["by_door"] == {"/.env": 1}
    e = rep["recent"][0]
    assert (e["kind"], e["marker"], e["ip"], e["ip_prefix"], e["ua"]) == ("door", "env", PROBER, "5.6.x.x", "scanner/1.0")


def test_real_pages_pass_through():
    c = make()
    for path in ("/", "/api/users", "/login", "/.envx", "/.ENV", "/static/app.js"):
        assert ask(c, path) is None, path
    assert c.report()["total"] == {"door": 0, "bait_key": 0}


def test_door_path_variants():
    c = make()
    for path in ("/wp-admin", "/wp-admin/", "//.env", "/.env/", "/.git//config"):
        r = ask(c, path)
        assert r is not None and r.status == 200, path


def test_every_default_door_answers_with_text_only():
    c = make()
    for path, _marker in c.doors:
        r = ask(c, path)
        assert r.status == 200
        assert b"<script" not in r.body.lower()   # 相手の機械で何かを動かさない（docs/lines.md の 2）
        assert r.body.decode("utf-8")              # 文字として読める


def test_door_pages_are_stable_and_depend_on_secret():
    a, b = make(), make()
    assert ask(a, "/.env").body == ask(a, "/.env").body == ask(b, "/.env").body   # 開くたびに同じ
    other = make(secret="another-secret-0123456789")
    assert ask(other, "/.env").body != ask(a, "/.env").body                     # 導入ごとに違う鍵


def test_door_pages_do_not_imitate_other_companies_keys():
    c = make()
    for path, _marker in c.doors:
        body = ask(c, path).body.decode("utf-8")
        for foreign in FOREIGN_KEY_PREFIXES:
            assert foreign not in body, (path, foreign)


def test_custom_doors_replace_defaults():
    c = make(doors={"/old-admin/": Door("admin", "text/html; charset=utf-8", lambda key: f"<input value='{key('csrf')}'>")})
    assert ask(c, "/.env") is None
    r = ask(c, "/old-admin")
    assert r.status == 200 and b"app_live_" in r.body
    assert c.doors == [("/old-admin", "admin")]


# ---------------------------------------------------------------- 目印入りの偽の鍵

def test_bait_key_in_bearer_is_refused_and_recorded():
    c = make()
    key = c.bait_key("env", "db")
    assert key.encode() in ask(c, "/.env").body
    c.reset()
    assert ask(c, "/api/admin/users", headers={"authorization": f"Bearer {key}"}) == FORBIDDEN
    rep = c.report()
    assert rep["total"] == {"door": 0, "bait_key": 1}
    assert rep["bait_key_by_marker"] == {"env": 1}
    e = rep["recent"][0]
    assert (e["kind"], e["marker"], e["slot"], e["path"]) == ("bait_key", "env", "db", "/api/admin/users")


def test_bait_key_in_basic_auth_password():
    c = make()
    key = c.bait_key("wpconfig", "db")
    token = base64.b64encode(f"wp_user:{key}".encode()).decode().rstrip("=")   # 末尾の = が無くても読む
    assert ask(c, "/admin", headers={"authorization": f"Basic {token}"}) == FORBIDDEN


@pytest.mark.parametrize("header", ["x-api-key", "x-admin-key", "x-auth-token", "x-access-token"])
def test_bait_key_in_key_headers(header):
    c = make()
    assert ask(c, "/api", headers={header: c.bait_key("sql", "admin")}) == FORBIDDEN


def test_bait_key_in_query_string_even_when_encoded():
    c = make()
    key = c.bait_key("actuator", "api")
    assert ask(c, "/api", query=f"api_key={key}") == FORBIDDEN
    assert ask(c, "/api", query="token=" + quote(f" {key} ")) == FORBIDDEN


def test_look_alike_keys_are_not_bait():
    c = make()
    key = c.bait_key("env", "db")
    fake = "app_live_" + "0" * 32
    assert ask(c, "/api", headers={"authorization": f"Bearer {fake}"}) is None
    assert ask(c, "/api", headers={"authorization": f"Bearer {key.upper()}"}) is None
    assert ask(c, "/api", headers={"x-api-key": key[:-1]}) is None
    other = make(secret="another-secret-0123456789")
    assert ask(other, "/api", headers={"x-api-key": key}) is None   # 別の導入の鍵は、照合しない


def test_bait_key_on_lifeline_is_recorded_but_not_refused():
    c = make(never_block=("/health", "/api/sos"))
    key = c.bait_key("env", "api")
    assert ask(c, "/api/sos", headers={"x-api-key": key}) is None
    assert c.report()["total"]["bait_key"] == 1


def test_keys_placed_outside_doors_are_also_watched():
    c = make()
    key = c.bait_key("vault", "note")   # 扉の外（偽の書類など）に置く鍵
    assert ask(c, "/api", headers={"x-api-key": key}) == FORBIDDEN
    assert c.report()["recent"][0]["marker"] == "vault"


def test_bait_key_names_are_checked():
    c = make()
    for bad in ("", "Bad", "a b", "x" * 33, "../env"):
        with pytest.raises(ValueError):
            c.bait_key(bad)


# ---------------------------------------------------------------- 締め出し

def test_ban_is_off_by_default():
    c = make()
    ask(c, "/.env")
    assert ask(c, "/", now=1001.0) is None
    rep = c.report()
    assert rep["ban_enabled"] is False and rep["banned_now"] == 0
    assert rep["recent"][0]["banned"] is False


def test_ban_blocks_only_the_prober_and_never_the_lifelines():
    c = make(ban=True, never_block=("/health", "/api/sos"))
    ask(c, "/.env")
    assert ask(c, "/", now=1001.0) == FORBIDDEN
    assert ask(c, "/", peer=NEIGHBOR, now=1001.0) is None
    assert ask(c, "/health", now=1001.0) is None
    assert ask(c, "/api/sos", now=1001.0) is None
    assert ask(c, "/api/sos/", now=1001.0) is None
    rep = c.report(now=1001.0)
    assert rep["banned_now"] == 1 and rep["blocked"] == 1
    assert rep["recent"][0]["banned"] is True


def test_ban_expires():
    c = make(ban=True, ban_seconds=60)
    ask(c, "/.env", now=1000.0)
    assert ask(c, "/", now=1059.0) == FORBIDDEN
    assert ask(c, "/", now=1060.0) is None


@pytest.mark.parametrize("peer", ["104.16.0.1", "2606:4700::1", "10.0.0.5", "192.168.1.2", "127.0.0.1",
                                  "::1", "100.64.0.1", "203.0.113.9", "", "not-an-ip"])
def test_never_bans_shared_or_internal_addresses(peer):
    c = make(ban=True)
    ask(c, "/.env", peer=peer)
    assert c.report()["banned_now"] == 0
    assert ask(c, "/", peer=peer, now=1001.0) is None


def test_ban_memory_is_capped():
    c = make(ban=True, ban_max=3, ban_seconds=60)
    for i in range(5):
        ask(c, "/.env", peer=f"5.6.7.{i + 1}", now=1000.0)
    assert c.report(now=1000.0)["banned_now"] == 3
    ask(c, "/.env", peer="5.6.8.1", now=2000.0)          # 期限切れを捨てて、新しい相手を入れる
    assert ask(c, "/", peer="5.6.8.1", now=2001.0) == FORBIDDEN


# ---------------------------------------------------------------- 送り元の読み方

def test_direct_mode_ignores_forwarded_headers():
    c = make(ban=True)
    ask(c, "/.env", headers={"x-forwarded-for": NEIGHBOR, "cf-connecting-ip": NEIGHBOR})
    assert c.report()["recent"][0]["ip"] == PROBER
    assert ask(c, "/", peer=NEIGHBOR, now=1001.0) is None


def test_cloudflare_mode_reads_cf_connecting_ip():
    c = make(ban=True, client_ip="cloudflare")
    ask(c, "/.env", headers={"cf-connecting-ip": PROBER}, peer="104.16.0.1")
    assert c.report()["recent"][0]["ip"] == PROBER
    assert ask(c, "/", headers={"cf-connecting-ip": PROBER}, peer="104.16.0.2", now=1001.0) == FORBIDDEN
    assert ask(c, "/", headers={"cf-connecting-ip": NEIGHBOR}, peer="104.16.0.1", now=1001.0) is None


def test_forwarded_for_mode_uses_the_proxy_side_and_ignores_spoofed_left_side():
    c = make(ban=True, client_ip="x-forwarded-for")
    # 探りが左に隣の人の番号を書いても、前に立つ仕組みが足した右端（本当の相手）で締め出す
    ask(c, "/.env", headers={"x-forwarded-for": f"{NEIGHBOR}, {PROBER}"}, peer="10.0.0.2")
    assert c.report()["recent"][0]["ip"] == PROBER
    assert ask(c, "/", headers={"x-forwarded-for": NEIGHBOR}, peer="10.0.0.2", now=1001.0) is None
    assert ask(c, "/", headers={"x-forwarded-for": PROBER}, peer="10.0.0.2", now=1001.0) == FORBIDDEN


def test_forwarded_for_mode_with_two_proxies():
    c = make(client_ip="x-forwarded-for", trusted_hops=2)
    ask(c, "/.env", headers={"x-forwarded-for": f"{NEIGHBOR}, {PROBER}, 104.16.0.1"}, peer="10.0.0.2")
    assert c.report()["recent"][0]["ip"] == PROBER


def test_cloudflare_header_is_ignored_when_not_from_cloudflare():
    # Cloudflare を通らずに直接届いた相手が CF-Connecting-IP を書いても、隣の人を締め出させない
    c = make(ban=True, client_ip="cloudflare")
    ask(c, "/.env", headers={"cf-connecting-ip": NEIGHBOR}, peer=PROBER)
    assert c.report()["recent"][0]["ip"] == PROBER
    assert ask(c, "/", peer=NEIGHBOR, now=1001.0) is None
    assert ask(c, "/", peer=PROBER, now=1001.0) == FORBIDDEN


def test_cloudflare_header_through_a_listed_proxy():
    c = make(ban=True, client_ip="cloudflare", trusted_proxies=["10.0.0.0/8"])
    ask(c, "/.env", headers={"cf-connecting-ip": PROBER}, peer="10.0.0.2")
    assert c.report()["recent"][0]["ip"] == PROBER


def test_forwarded_for_header_is_ignored_from_a_public_peer():
    # 前に立つ仕組みを通らずに直接届いた相手が X-Forwarded-For を書いても、隣の人を締め出させない
    c = make(ban=True, client_ip="x-forwarded-for")
    ask(c, "/.env", headers={"x-forwarded-for": NEIGHBOR}, peer=PROBER)
    assert c.report()["recent"][0]["ip"] == PROBER
    assert ask(c, "/", peer=NEIGHBOR, now=1001.0) is None


def test_forwarded_for_with_listed_proxies_only_trusts_them():
    c = make(ban=True, client_ip="x-forwarded-for", trusted_proxies=["203.0.113.0/24"])
    ask(c, "/.env", headers={"x-forwarded-for": NEIGHBOR}, peer="10.0.0.2")    # 一覧に無い相手
    assert c.report()["recent"][0]["ip"] == "10.0.0.2" and c.report()["recent"][0]["banned"] is False
    ask(c, "/.env", headers={"x-forwarded-for": PROBER}, peer="203.0.113.5", now=1001.0)
    assert c.report()["recent"][0]["ip"] == PROBER


def test_forwarded_for_with_too_many_hops_does_not_read_the_left_side(caplog):
    # trusted_hops=2 なのに、本当は前に立つ仕組みが1つ：左（呼び手が書いた所）を読まず、締め出さない
    c = make(ban=True, client_ip="x-forwarded-for", trusted_hops=2)
    with caplog.at_level(logging.WARNING, logger="sanadamaru"):
        ask(c, "/.env", headers={"x-forwarded-for": f"{NEIGHBOR}, {PROBER}"}, peer="10.0.0.2")
        ask(c, "/.env", headers={"x-forwarded-for": PROBER}, peer="10.0.0.2", now=1001.0)
    assert [e["ip"] for e in c.report()["recent"]] == ["", ""]
    assert c.report()["banned_now"] == 0
    assert caplog.text.count("送り元の番号を確かめられませんでした") == 1


@pytest.mark.parametrize("value", ["2001:4860::1%scope\tFORGED", "1.2.3.4\tFORGED", "fe80::1%eth0", "１.２.３.４"])
def test_addresses_with_decorations_are_not_read(value):
    c = make(client_ip="x-forwarded-for")
    ask(c, "/.env", headers={"x-forwarded-for": value}, peer="10.0.0.2")
    e = c.report()["recent"][0]
    assert e["ip"] == "" and "\t" not in str(e)


@pytest.mark.parametrize("proxies", [["::ffff:1.2.3.0/120"], ["1.2.3.0/24"]])
def test_ipv4_mapped_proxy_ranges_match_ipv4_peers(proxies):
    # 直接の相手 ::ffff:1.2.3.4 は 1.2.3.4 として読む。範囲を IPv6 の形で書いても、同じように一致させる
    c = make(ban=True, client_ip="x-forwarded-for", trusted_proxies=proxies)
    ask(c, "/.env", headers={"x-forwarded-for": PROBER}, peer="::ffff:1.2.3.4")
    assert c.report()["recent"][0]["ip"] == PROBER
    assert ask(c, "/", headers={"x-forwarded-for": NEIGHBOR}, peer="::ffff:1.2.3.4", now=1001.0) is None
    assert ask(c, "/", headers={"x-forwarded-for": PROBER}, peer="::ffff:1.2.3.4", now=1001.0) == FORBIDDEN


def test_bad_trusted_proxies_refuse_to_start():
    with pytest.raises(ValueError):
        make(trusted_proxies=["not-a-network"])
    with pytest.raises(ValueError):
        make(trusted_proxies="10.0.0.0/8")


# ---------------------------------------------------------------- よそのページからの読み込み

@pytest.mark.parametrize("headers", [
    {"sec-fetch-site": "cross-site", "sec-fetch-dest": "image"},   # よそのページの <img src=".../.env">
    {"sec-fetch-site": "same-site"},
    {"sec-fetch-site": "same-origin"},
    {"referer": "https://example.net/page"},                       # Sec-Fetch-* を送らない古いブラウザ
    {"origin": "https://example.net"},
])
def test_requests_from_a_web_page_are_recorded_but_not_banned(headers):
    c = make(ban=True)
    assert ask(c, "/.env", headers=headers).status == 200
    e = c.report()["recent"][0]
    assert e["from_page"] is True and e["banned"] is False
    assert ask(c, "/", now=1001.0) is None                         # 閲覧者は、ふつうに使い続けられる


def test_bait_key_loaded_by_a_web_page_does_not_ban_the_viewer():
    c = make(ban=True)
    key = c.bait_key("env", "db")
    assert ask(c, "/x", query=f"api_key={key}", headers={"sec-fetch-site": "cross-site"}) == FORBIDDEN
    assert c.report()["recent"][0]["banned"] is False
    assert ask(c, "/", now=1001.0) is None


def test_browser_without_any_page_signal_is_not_banned():
    # http:// への埋め込み＋ referrerpolicy="no-referrer" では、Sec-Fetch-*・Referer・Origin のどれも届かない
    c = make(ban=True)
    ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
    assert ask(c, "/.env", headers={"user-agent": ua, "accept": "image/avif,image/webp,*/*"}).status == 200
    e = c.report()["recent"][0]
    assert e["from_page"] is True and e["banned"] is False
    assert ask(c, "/", now=1001.0) is None


@pytest.mark.parametrize("ua", ["", "curl/8.4.0", "python-requests/2.32", "Go-http-client/1.1"])
def test_tools_without_page_signals_are_still_banned(ua):
    c = make(ban=True)
    ask(c, "/.env", headers={"user-agent": ua} if ua else {})
    assert c.report()["recent"][0]["banned"] is True


def test_typed_address_still_bans():
    c = make(ban=True)
    ask(c, "/.env", headers={"sec-fetch-site": "none", "sec-fetch-mode": "navigate", "user-agent": "Mozilla/5.0"})
    assert c.report()["recent"][0]["banned"] is True
    assert ask(c, "/", now=1001.0) == FORBIDDEN


# ---------------------------------------------------------------- 記録と知らせ

def test_log_is_capped_but_totals_keep_counting():
    c = make(log_max=5)
    for i in range(10):
        ask(c, "/.env", now=1000.0 + i)
    rep = c.report()
    assert len(rep["recent"]) == 5 and rep["total"]["door"] == 10
    assert rep["recent"][0]["at"] == 1009


def test_alert_has_cooldown_per_door_and_no_full_address():
    sent = []
    c = make(alert=sent.append, alert_cooldown=60)
    ask(c, "/.env", now=1000.0)
    ask(c, "/.env.local", now=1010.0)         # 同じ目印（env）＝知らせない
    ask(c, "/.git/config", now=1010.0)        # 別の目印＝知らせる
    ask(c, "/.env", now=1061.0)               # 60秒たった＝知らせる
    assert [e["marker"] for e in sent] == ["env", "git", "env"]
    assert all("ip" not in e and e["ip_prefix"] == "5.6.x.x" for e in sent)
    assert c.report()["total"]["door"] == 4   # 知らせを絞っても、記録はすべて残す


def test_alert_failure_does_not_stop_the_guard(caplog):
    def broken(event):
        raise RuntimeError("down")
    c = make(alert=broken)
    with caplog.at_level(logging.WARNING, logger="sanadamaru"):
        assert ask(c, "/.env").status == 200
    assert "RuntimeError" in caplog.text


def test_log_line_has_only_the_address_prefix(caplog):
    c = make()
    with caplog.at_level(logging.WARNING, logger="sanadamaru"):
        ask(c, "/.env")
    assert "[sanadamaru] door path=/.env marker=env from=5.6.x.x" in caplog.text
    assert PROBER not in caplog.text


def test_control_characters_cannot_forge_log_lines(caplog):
    c = make()
    key = c.bait_key("env", "db")
    with caplog.at_level(logging.WARNING, logger="sanadamaru"):
        ask(c, "/x\n[sanadamaru] fake\r", headers={"x-api-key": key, "user-agent": "a\nb"})
    e = c.report()["recent"][0]
    assert e["path"] == "/x?[sanadamaru] fake?" and e["ua"] == "a?b"
    assert caplog.text.count("[sanadamaru] fake") == 1 and "\n[sanadamaru] fake" not in caplog.text


def test_log_lines_are_capped_per_minute(caplog):
    c = make(ban=True, log_max=5, log_per_minute=5)
    key = c.bait_key("env", "db")
    with caplog.at_level(logging.WARNING, logger="sanadamaru"):
        for i in range(21):
            ask(c, "/health", query=f"api_key={key}", now=1000.0 + i)
        ask(c, "/health", query=f"api_key={key}", now=1061.0)       # 次の1分
    lines = [r for r in caplog.records if r.getMessage().startswith("[sanadamaru] bait_key")]
    assert len(lines) == 6
    assert "(+16 not logged)" in lines[-1].getMessage()
    rep = c.report()
    assert rep["total"]["bait_key"] == 22 and rep["log_lines_not_written"] == 16


@pytest.mark.parametrize("ch", ["\u202e", "\u202a", "\u2066", "\u200b", "\u200f", "\ufeff", "\u2028", "\u0085"])
def test_invisible_and_direction_characters_are_replaced(caplog, ch):
    c = make()
    key = c.bait_key("env", "db")
    with caplog.at_level(logging.WARNING, logger="sanadamaru"):
        ask(c, f"/x{ch}FAKE", headers={"x-api-key": key, "user-agent": f"ua{ch}x"})
    e = c.report()["recent"][0]
    assert e["path"] == "/x?FAKE" and e["ua"] == "ua?x"
    assert ch not in caplog.text


def test_log_alert_writes_an_error(caplog):
    from sanadamaru import log_alert
    c = make(alert=log_alert)
    with caplog.at_level(logging.ERROR, logger="sanadamaru"):
        ask(c, "/.env")
    errors = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert len(errors) == 1 and "偽の扉に触れました" in errors[0].getMessage()


# ---------------------------------------------------------------- 設定

@pytest.mark.parametrize("kw", [
    {"client_ip": "x-real-ip"},
    {"trusted_hops": 0},
    {"key_prefix": ""},
    {"key_prefix": "a"},
    {"key_prefix": "has space_"},
    {"ban_seconds": 0},
    {"never_block": ("/",)},
    {"never_block": ("health",)},
    {"secret": "short"},
    {"doors": {"/": Door("root", "text/plain", lambda key: "")}},
    {"doors": {"/a?b": Door("q", "text/plain", lambda key: "")}},
    {"doors": {"/health/x": Door("h", "text/plain", lambda key: "")}},
    {"doors": {"/x": "not a door"}},
])
def test_wrong_settings_are_refused(kw):
    kw.setdefault("secret", SECRET)
    with pytest.raises((ValueError, TypeError)):
        Castle(**kw)


@pytest.mark.parametrize("prefix", ["AKIA", "sk_live_", "sk-ant-", "ghp_", "xoxb-", "AIza", "SG.", "hf_"])
def test_other_companies_key_shapes_are_refused(prefix):
    with pytest.raises(ValueError):
        make(key_prefix=prefix)


def test_door_names_are_checked():
    with pytest.raises(ValueError):
        Door("Env", "text/plain", lambda key: "")
    with pytest.raises(ValueError):
        Door("env", "text/plain\r\nx-evil: 1", lambda key: "")


def test_missing_secret_still_works_but_warns(caplog):
    with caplog.at_level(logging.WARNING, logger="sanadamaru"):
        c = Castle()
    assert "SANADAMARU_SECRET" in caplog.text
    assert c.report()["secret_is_ephemeral"] is True
    assert ask(c, "/.env").status == 200


def test_from_env():
    c = Castle.from_env({
        "SANADAMARU_SECRET": SECRET, "SANADAMARU_BAN": "1", "SANADAMARU_BAN_SECONDS": "120",
        "SANADAMARU_CLIENT_IP": "cloudflare", "SANADAMARU_TRUSTED_HOPS": "2",
        "SANADAMARU_KEY_PREFIX": "svc_", "SANADAMARU_NEVER_BLOCK": "/api/sos, /status",
    })
    assert (c.ban, c.ban_seconds, c.client_ip_mode, c.trusted_hops, c.key_prefix) == (True, 120, "cloudflare", 2, "svc_")
    assert c.never_block == ("/health", "/api/sos", "/status")
    assert c.secret_is_ephemeral is False
    assert Castle.from_env({"SANADAMARU_SECRET": SECRET, "SANADAMARU_BAN": "1"}, ban=False).ban is False


def test_default_doors_is_a_fresh_copy():
    d = default_doors()
    d.pop("/.env")
    assert "/.env" in default_doors()
