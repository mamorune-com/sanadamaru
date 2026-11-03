"""コマンド：python -m sanadamaru demo ・ python -m sanadamaru doors ・ python -m sanadamaru --version

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


def _demo(out: TextIO) -> int:
    lib_logger = logging.getLogger("sanadamaru")
    before = lib_logger.level
    lib_logger.setLevel(logging.ERROR)   # 試しの間は、記録の行を出さない
    try:
        castle = Castle(secret=_DEMO_SECRET)

        def say(s: str = "") -> None:
            print(s, file=out)

        say("真田丸の試し（この機械の中だけで動きます。外へは何も送りません）")
        say()
        say("1. ふつうの利用者が「/」を開く")
        r = castle.check(path="/", headers={"user-agent": "Mozilla/5.0"}, peer=_DEMO_PEER)
        if r is not None:
            return 1
        say("   → 真田丸は何もせず、本物の窓口へ通します")
        say()
        say("2. 探りが「/.env」を開く")
        r = castle.check(path="/.env", headers={"user-agent": "scanner/1.0"}, peer=_DEMO_PEER)
        if r is None or r.status != 200:
            return 1
        line = next(l for l in r.body.decode("utf-8").splitlines() if l.startswith("DB_PASSWORD="))
        say("   → 偽の扉です。作り物の中身を返して、記録しました（目印 env）")
        say(f"     中身の一部：{line[:30]}…（偽の鍵）")
        say()
        key = castle.bait_key("env", "db")
        say("3. 探りが、持ち出した偽の鍵で「/api/admin/users」を呼ぶ")
        r = castle.check(path="/api/admin/users", headers={"authorization": f"Bearer {key}"}, peer=_DEMO_PEER)
        if r is None or r.status != 403:
            return 1
        say("   → 偽の鍵です。断って（403）、記録しました（目印 env・欄 db）")
        say()
        rep = castle.report()
        say("4. 記録のまとめ")
        say(f"   扉に触れた回数 {rep['total']['door']}・偽の鍵が使われた回数 {rep['total']['bait_key']}"
            f"・送り元 {rep['sources']}か所")
        say("   締め出しは、既定でオフです（ban=True にすると、扉に触れた送り元を一定時間断ります）。")
        return 0
    finally:
        lib_logger.setLevel(before)


def _doors(out: TextIO) -> int:
    lib_logger = logging.getLogger("sanadamaru")
    before = lib_logger.level
    lib_logger.setLevel(logging.ERROR)
    try:
        castle = Castle(secret=_DEMO_SECRET)
    finally:
        lib_logger.setLevel(before)
    print("既定の扉（住所・目印）", file=out)
    for path, marker in castle.doors:
        print(f"  {path:<22} {marker}", file=out)
    return 0


def main(argv: Optional[List[str]] = None, out: Optional[TextIO] = None) -> int:
    out = out or sys.stdout
    parser = argparse.ArgumentParser(prog="python -m sanadamaru", description="真田丸：偽の扉で、探りに来た相手を確かめる守りの部品")
    parser.add_argument("--version", action="version", version=f"sanadamaru {__version__}")
    parser.add_argument("command", choices=["demo", "doors"], help="demo＝動きを順に見せる・doors＝既定の扉の一覧")
    args = parser.parse_args(argv)
    return _demo(out) if args.command == "demo" else _doors(out)


if __name__ == "__main__":
    sys.exit(main())
