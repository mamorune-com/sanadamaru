"""ASGI のつなぎ（FastAPI・Starlette・Django の ASGI など）。

    app.add_middleware(SanadamaruMiddleware, castle=castle)   # FastAPI・Starlette

いちばん外側に置いてください（FastAPI・Starlette では、最後に add_middleware したものが外側です）。
HTTP 以外（WebSocket・lifespan）は、そのまま通します。
"""
from __future__ import annotations

from typing import Dict, Optional

from .castle import Castle, Reply


class SanadamaruMiddleware:
    def __init__(self, app, castle: Optional[Castle] = None, **options) -> None:
        if castle is not None and options:
            raise TypeError("castle を渡す時は、ほかの設定は Castle の側に書いてください")
        self.app = app
        self.castle = castle if castle is not None else Castle(**options)

    async def __call__(self, scope, receive, send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        headers: Dict[str, str] = {}
        for name, value in scope.get("headers") or ():
            k = name.decode("latin-1").lower()
            v = value.decode("latin-1")
            headers[k] = f"{headers[k]}, {v}" if k in headers else v
        client = scope.get("client")
        method = scope.get("method", "GET")
        reply = self.castle.check(
            path=scope.get("path", "/"),
            headers=headers,
            query=(scope.get("query_string") or b"").decode("latin-1"),
            peer=client[0] if client else "",
            method=method,
        )
        if reply is None:
            await self.app(scope, receive, send)
            return
        await _send(send, reply, head=(method == "HEAD"))


async def _send(send, reply: Reply, head: bool) -> None:
    headers = [
        (b"content-type", reply.content_type.encode("latin-1")),
        (b"content-length", str(len(reply.body)).encode("latin-1")),
    ]
    headers += [(k.encode("latin-1"), v.encode("latin-1")) for k, v in reply.headers]
    await send({"type": "http.response.start", "status": reply.status, "headers": headers})
    await send({"type": "http.response.body", "body": b"" if head else reply.body})
