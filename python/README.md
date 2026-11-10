# 真田丸（sanadamaru）・Python の部品

AI が休まず探しに来る「よくある穴」（`/.env`・`/.git/config` など）に偽の扉を置き、触れた相手を確かめる守りの部品です。反撃はしません。依存する部品はありません。

```bash
pip install "git+https://github.com/mamorune-com/sanadamaru@v0.2.0#subdirectory=python"
python -m sanadamaru demo
```

```python
from fastapi import FastAPI
from sanadamaru import Castle, SanadamaruMiddleware, log_alert

castle = Castle.from_env(never_block=("/health", "/api/sos"), alert=log_alert)
app = FastAPI()
app.add_middleware(SanadamaruMiddleware, castle=castle)   # いちばん外側に置くため、最後に足します
```

使い方・越えない線・締め出しをオンにする前の確かめ方は、リポジトリの [README](https://github.com/mamorune-com/sanadamaru#readme) と [docs/](https://github.com/mamorune-com/sanadamaru/tree/main/docs) にあります。

Apache-2.0 ・ 株式会社MAMORUNE
