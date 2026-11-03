"""真田丸（sanadamaru）

AI を使う攻撃は、`/.env` や `/.git/config` のような「よくある穴」を、休まず大量に探しに来ます。
真田丸は、本物の利用者が決して開かない住所に「偽の扉」を置き、触れた相手を確かめる守りの部品です。

- 偽の扉：作り物の中身を返し、触れたことを記録します。
- 目印入りの偽の鍵：扉の中に置いた偽の鍵が、あとで使われたら記録して断ります。
- 締め出し：既定はオフ（見張るだけ）。オンにすると、扉に触れた送り元を一定時間断ります。

相手のシステムには、こちらから一切触れません。越えない線は docs/lines.md にあります。
"""
from ._version import __version__
from .asgi import SanadamaruMiddleware
from .castle import FORBIDDEN, Castle, Reply, log_alert
from .doors import Door, default_doors
from .wsgi import SanadamaruWSGI

__all__ = [
    "Castle",
    "Door",
    "FORBIDDEN",
    "Reply",
    "SanadamaruMiddleware",
    "SanadamaruWSGI",
    "__version__",
    "default_doors",
    "log_alert",
]
