# sanadamaru (Python)

A tiny, dependency-free honeypot for Python web apps. It puts decoy doors on the paths that automated scanners probe first (`/.env`, `/.git/config` and so on) and tells you who touched them. It never hacks back.

```bash
pip install "git+https://github.com/mamorune-com/sanadamaru@v0.2.1#subdirectory=python"
python -m sanadamaru doors
```

```python
from fastapi import FastAPI
from sanadamaru import Castle, SanadamaruMiddleware, log_alert

castle = Castle.from_env(never_block=("/health", "/api/sos"), alert=log_alert)
app = FastAPI()
app.add_middleware(SanadamaruMiddleware, castle=castle)   # add it last so it is the outermost layer
```

Usage, the lines it never crosses, and the checks to run before you turn blocking on are in the repository's [README](https://github.com/mamorune-com/sanadamaru#readme) and [docs/en/](https://github.com/mamorune-com/sanadamaru/tree/main/docs/en).

日本語の説明は [README.ja.md](https://github.com/mamorune-com/sanadamaru/blob/main/README.ja.md) にあります。

Apache-2.0 · MAMORUNE Inc.
