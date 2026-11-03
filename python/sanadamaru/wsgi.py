"""WSGI のつなぎ（Flask・Django など）。

    app.wsgi_app = SanadamaruWSGI(app.wsgi_app, castle=castle)   # Flask
    application = SanadamaruWSGI(get_wsgi_application(), castle=castle)   # Django（wsgi.py）
"""
from __future__ import annotations

from typing import Dict, Optional

from .castle import Castle

_REASONS = {200: "OK", 403: "Forbidden"}


class SanadamaruWSGI:
    def __init__(self, app, castle: Optional[Castle] = None, **options) -> None:
        if castle is not None and options:
            raise TypeError("castle を渡す時は、ほかの設定は Castle の側に書いてください")
        self.app = app
        self.castle = castle if castle is not None else Castle(**options)

    def __call__(self, environ, start_response):
        headers: Dict[str, str] = {}
        for k, v in environ.items():
            if k.startswith("HTTP_"):
                headers[k[5:].replace("_", "-").lower()] = v
        path = environ.get("PATH_INFO") or "/"
        try:   # WSGI の PATH_INFO は latin-1 で読まれた UTF-8 なので、読み直す
            path = path.encode("latin-1").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass
        method = environ.get("REQUEST_METHOD", "GET")
        reply = self.castle.check(
            path=path,
            headers=headers,
            query=environ.get("QUERY_STRING", ""),
            peer=environ.get("REMOTE_ADDR", ""),
            method=method,
        )
        if reply is None:
            return self.app(environ, start_response)
        out = [("Content-Type", reply.content_type), ("Content-Length", str(len(reply.body)))]
        out += list(reply.headers)
        start_response(f"{reply.status} {_REASONS.get(reply.status, '')}".strip(), out)
        return [] if method == "HEAD" else [reply.body]
