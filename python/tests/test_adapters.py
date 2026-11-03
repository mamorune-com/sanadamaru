"""ASGI と WSGI のつなぎのテスト（外の部品を使わず、仕様どおりの呼び方で確かめる）。"""
import asyncio
import io

import pytest

from sanadamaru import Castle, SanadamaruMiddleware, SanadamaruWSGI

SECRET = "test-secret-0123456789abcdef"


def castle(**kw):
    kw.setdefault("secret", SECRET)
    return Castle(**kw)


# ---------------------------------------------------------------- ASGI

async def real_asgi_app(scope, receive, send):
    if scope["type"] != "http":
        scope["seen"] = True
        return
    await send({"type": "http.response.start", "status": 200, "headers": [(b"content-type", b"text/plain")]})
    await send({"type": "http.response.body", "body": b"real"})


def call_asgi(mw, path, headers=(), query=b"", client=("5.6.7.8", 50000), method="GET"):
    scope = {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": method, "scheme": "https",
        "path": path, "raw_path": path.encode(), "query_string": query, "root_path": "",
        "headers": [(k.encode(), v.encode()) for k, v in headers], "client": client, "server": ("example", 443),
    }
    sent = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        sent.append(message)

    asyncio.run(mw(scope, receive, send))
    start = sent[0]
    return start["status"], {k.decode(): v.decode() for k, v in start["headers"]}, b"".join(m.get("body", b"") for m in sent[1:])


def test_asgi_door_and_pass_through():
    mw = SanadamaruMiddleware(real_asgi_app, castle=castle())
    status, headers, body = call_asgi(mw, "/.env")
    assert status == 200 and b"DB_PASSWORD=" in body
    assert headers["cache-control"] == "no-store" and headers["content-length"] == str(len(body))
    assert call_asgi(mw, "/") == (200, {"content-type": "text/plain"}, b"real")


def test_asgi_bait_key_and_duplicate_headers():
    c = castle()
    mw = SanadamaruMiddleware(real_asgi_app, castle=c)
    key = c.bait_key("env", "db")
    assert call_asgi(mw, "/api", headers=[("Authorization", f"Bearer {key}")])[0] == 403
    assert call_asgi(mw, "/api", query=f"key={key}".encode())[0] == 403
    # 同じ名前の見出しが2つあっても、つないで読む
    ban = castle(ban=True, client_ip="x-forwarded-for")
    mw2 = SanadamaruMiddleware(real_asgi_app, castle=ban)
    call_asgi(mw2, "/.env", headers=[("X-Forwarded-For", "1.2.3.4"), ("X-Forwarded-For", "5.6.7.8")], client=("10.0.0.2", 1))
    assert ban.report()["recent"][0]["ip"] == "5.6.7.8"


def test_asgi_head_has_no_body():
    mw = SanadamaruMiddleware(real_asgi_app, castle=castle())
    status, headers, body = call_asgi(mw, "/.env", method="HEAD")
    assert status == 200 and body == b"" and int(headers["content-length"]) > 0


@pytest.mark.parametrize("kind", ["websocket", "lifespan"])
def test_asgi_other_scopes_pass_through(kind):
    mw = SanadamaruMiddleware(real_asgi_app, castle=castle())
    scope = {"type": kind, "path": "/.env"}

    async def nothing():
        return {}

    asyncio.run(mw(scope, nothing, nothing))
    assert scope.get("seen") is True


def test_asgi_options_or_castle_not_both():
    with pytest.raises(TypeError):
        SanadamaruMiddleware(real_asgi_app, castle=castle(), ban=True)
    mw = SanadamaruMiddleware(real_asgi_app, secret=SECRET, ban=True)
    assert mw.castle.ban is True


# ---------------------------------------------------------------- WSGI

def real_wsgi_app(environ, start_response):
    start_response("200 OK", [("Content-Type", "text/plain")])
    return [b"real"]


def call_wsgi(mw, path, headers=None, query="", remote="5.6.7.8", method="GET"):
    environ = {
        "REQUEST_METHOD": method, "PATH_INFO": path, "QUERY_STRING": query, "REMOTE_ADDR": remote,
        "SERVER_NAME": "example", "SERVER_PORT": "443", "wsgi.input": io.BytesIO(b""), "wsgi.url_scheme": "https",
    }
    for k, v in (headers or {}).items():
        environ["HTTP_" + k.upper().replace("-", "_")] = v
    got = {}

    def start_response(status, response_headers, exc_info=None):
        got["status"], got["headers"] = status, dict(response_headers)

    body = b"".join(mw(environ, start_response))
    return got["status"], got["headers"], body


def test_wsgi_door_bait_and_pass_through():
    c = castle()
    mw = SanadamaruWSGI(real_wsgi_app, castle=c)
    status, headers, body = call_wsgi(mw, "/.git/config")
    assert status == "200 OK" and b"[remote" in body and headers["cache-control"] == "no-store"
    assert call_wsgi(mw, "/")[2] == b"real"
    key = c.bait_key("git", "deploy")
    assert call_wsgi(mw, "/api", headers={"X-Api-Key": key})[0] == "403 Forbidden"
    assert c.report()["total"] == {"door": 1, "bait_key": 1}


def test_wsgi_head_and_non_ascii_path():
    mw = SanadamaruWSGI(real_wsgi_app, castle=castle())
    status, headers, body = call_wsgi(mw, "/.env", method="HEAD")
    assert status == "200 OK" and body == b"" and int(headers["Content-Length"]) > 0
    # UTF-8 の住所（latin-1 で読まれた形）でも落ちない
    assert call_wsgi(mw, "/caf\xc3\xa9")[2] == b"real"
