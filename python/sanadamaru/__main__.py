"""コマンド：python -m sanadamaru demo ・ python -m sanadamaru doors ・ python -m sanadamaru --version
（表示は英語。--lang ja で日本語）

demo は、この機械の中だけで、真田丸の動きを順に見せます（ネットワークには出ません）。
"""
from __future__ import annotations

import argparse
import logging
import sys
from typing import List, Optional, TextIO

from ._version import __version__
from .castle import Castle

_DEMO_SECRET = "demo-only-secret-do-not-use-in-production"
_DEMO_PEER = "203.0.113.7"   # 説明用の番号（RFC 5737。実在の相手ではありません）


_TEXT = {
    "en": {
        "title": "sanadamaru demo (runs only on this machine; nothing is sent anywhere)",
        "s1": "1. A normal user opens \"/\"",
        "s1r": "   -> sanadamaru does nothing and passes the request to your app",
        "s2": "2. A scanner opens \"/.env\"",
        "s2r": "   -> A decoy door. Fake contents returned and the hit recorded (marker: env)",
        "s2c": "     Part of the contents: {line}... (a bait key)",
        "s3": "3. The scanner calls \"/api/admin/users\" with the bait key it took",
        "s3r": "   -> A bait key. Refused (403) and recorded (marker: env, field: db)",
        "s4": "4. Summary of the records",
        "s4r": "   Door hits: {door}, bait key uses: {bait}, sources: {sources}",
        "s4b": "   Blocking is off by default (with ban=True, a source that touched a door is refused for a while).",
        "doors": "Default decoy doors (path, marker)",
    },
    "ja": {
        "title": "真田丸の試し（この機械の中だけで動きます。外へは何も送りません）",
        "s1": "1. ふつうの利用者が「/」を開く",
        "s1r": "   → 真田丸は何もせず、本物の窓口へ通します",
        "s2": "2. 探りが「/.env」を開く",
        "s2r": "   → 偽の扉です。作り物の中身を返して、記録しました（目印 env）",
        "s2c": "     中身の一部：{line}…（偽の鍵）",
        "s3": "3. 探りが、持ち出した偽の鍵で「/api/admin/users」を呼ぶ",
        "s3r": "   → 偽の鍵です。断って（403）、記録しました（目印 env・欄 db）",
        "s4": "4. 記録のまとめ",
        "s4r": "   扉に触れた回数 {door}・偽の鍵が使われた回数 {bait}・送り元 {sources}か所",
        "s4b": "   締め出しは、既定でオフです（ban=True にすると、扉に触れた送り元を一定時間断ります）。",
        "doors": "既定の扉（住所・目印）",
    },
}


def _demo(out: TextIO, lang: str = "en") -> int:
    t = _TEXT[lang]
    lib_logger = logging.getLogger("sanadamaru")
    before = lib_logger.level
    lib_logger.setLevel(logging.ERROR)   # 試しの間は、記録の行を出さない
    try:
        castle = Castle(secret=_DEMO_SECRET)

        def say(s: str = "") -> None:
            print(s, file=out)

        say(t["title"])
        say()
        say(t["s1"])
        r = castle.check(path="/", headers={"user-agent": "Mozilla/5.0"}, peer=_DEMO_PEER)
        if r is not None:
            return 1
        say(t["s1r"])
        say()
        say(t["s2"])
        r = castle.check(path="/.env", headers={"user-agent": "scanner/1.0"}, peer=_DEMO_PEER)
        if r is None or r.status != 200:
            return 1
        line = next(l for l in r.body.decode("utf-8").splitlines() if l.startswith("DB_PASSWORD="))
        say(t["s2r"])
        say(t["s2c"].format(line=line[:30]))
        say()
        key = castle.bait_key("env", "db")
        say(t["s3"])
        r = castle.check(path="/api/admin/users", headers={"authorization": f"Bearer {key}"}, peer=_DEMO_PEER)
        if r is None or r.status != 403:
            return 1
        say(t["s3r"])
        say()
        rep = castle.report()
        say(t["s4"])
        say(t["s4r"].format(door=rep["total"]["door"], bait=rep["total"]["bait_key"], sources=rep["sources"]))
        say(t["s4b"])
        return 0
    finally:
        lib_logger.setLevel(before)


def _doors(out: TextIO, lang: str = "en") -> int:
    lib_logger = logging.getLogger("sanadamaru")
    before = lib_logger.level
    lib_logger.setLevel(logging.ERROR)
    try:
        castle = Castle(secret=_DEMO_SECRET)
    finally:
        lib_logger.setLevel(before)
    print(_TEXT[lang]["doors"], file=out)
    for path, marker in castle.doors:
        print(f"  {path:<22} {marker}", file=out)
    return 0


def main(argv: Optional[List[str]] = None, out: Optional[TextIO] = None) -> int:
    out = out or sys.stdout
    parser = argparse.ArgumentParser(prog="python -m sanadamaru",
                                     description="sanadamaru: decoy doors that reveal who is probing your web app")
    parser.add_argument("--version", action="version", version=f"sanadamaru {__version__}")
    parser.add_argument("--lang", choices=sorted(_TEXT), default="en", help="language of the output (default: en)")
    parser.add_argument("command", choices=["demo", "doors"], help="demo: walk through what it does; doors: list the default doors")
    args = parser.parse_args(argv)
    return _demo(out, args.lang) if args.command == "demo" else _doors(out, args.lang)


if __name__ == "__main__":
    sys.exit(main())
