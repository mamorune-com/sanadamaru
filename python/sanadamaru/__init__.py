"""sanadamaru: a tiny, dependency-free honeypot for Python web apps.

Automated scanners, increasingly driven by AI, probe tirelessly for classic mistakes such as `/.env` and `/.git/config`.
sanadamaru puts decoy doors on paths your real users never open, and tells you who touched them.

- Decoy doors: return plausible, entirely fake content and record the hit.
- Marked bait keys: fake keys placed inside the doors are recorded and refused if anyone uses them later.
- Blocking: off by default (watch only). When on, a source that touched a door is refused for a while.

It never touches the other side's systems. The lines it never crosses are in docs/en/lines.md.
"""
from ._version import __version__
from .asgi import SanadamaruMiddleware
from .castle import FORBIDDEN, Castle, Reply, Store, log_alert
from .doors import Door, default_doors
from .wsgi import SanadamaruWSGI

__all__ = [
    "Castle",
    "Door",
    "FORBIDDEN",
    "Reply",
    "SanadamaruMiddleware",
    "SanadamaruWSGI",
    "Store",
    "__version__",
    "default_doors",
    "log_alert",
]
