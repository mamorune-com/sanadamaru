# 変更の記録

版ごとの変更です。日付は [リリースの一覧](https://github.com/mamorune-com/sanadamaru/releases) にあります。

## v0.1.0

はじめての版です。

- 偽の扉：攻撃がまず探す19の住所（`/.env`・`/.git/config`・`/wp-login.php`・`*.sql`・`/actuator/env` など）。中身はすべて作り物で、開くたびに同じです。
- 目印入りの偽の鍵：扉と欄ごとに違う鍵。`Authorization`（Bearer・Basic）・`X-API-Key` などと `?` より後ろで使われたら、記録して断ります。扉の外に置く鍵も作れます（`castle.bait_key`）。
- 記録と知らせ：メモリだけ・件数に上限・記録の行と知らせには番号の頭だけ・知らせは同じ扉につき1時間に1回まで（`log_alert` で ERROR として出せます）。
- 締め出し：既定はオフ。期限付き・止めない窓口（`never_block`）は止めない・Cloudflare 自身と公開されていない番号は締め出さない。
- 送り元の読み方：`direct`・`cloudflare`・`x-forwarded-for`（右から数える）。
- つなぎ：ASGI（FastAPI・Starlette・Django）と WSGI（Flask・Django）。
- 他社の鍵の形に似た書き出し（`AKIA`・`sk_live_` など）では起動しません。
- コマンド：`python -m sanadamaru demo`・`python -m sanadamaru doors`
- 参考書：越えない線・仕組み・入れる時の確かめ方・第2段の呼びかけ
