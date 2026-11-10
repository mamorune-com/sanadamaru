# 変更の記録

版ごとの変更です。日付は [リリースの一覧](https://github.com/mamorune-com/sanadamaru/releases) にあります。

## v0.2.0

外部のレビューで見つかった点を直しました。締め出し（既定はオフ）を使う時に、無関係な人を巻き込まないための変更が中心です。

- よそのページに埋め込まれた読み込み（`<img src=".../.env">` など）で扉や偽の鍵に触れた時は、記録だけして締め出しません。`Sec-Fetch-Site`（`none` 以外）・`Referer`・`Origin` で見分けます。記録に `from_page` が加わりました。
- 転送の見出しは、前に立つ仕組みから届いた時だけ読みます。`cloudflare` は直接の相手が Cloudflare の番号の時、`x-forwarded-for` は `trusted_proxies`（新しい設定・`SANADAMARU_TRUSTED_PROXIES`）の範囲か、指定が無ければ公開されていない番号の時です。
- `x-forwarded-for` で段数が合わない時（見出しが短い・間の番号が前に立つ仕組みでない）は、左側を読まずに空にします（締め出しません）。
- 記録の行（WARNING）に1分あたりの上限を付けました（`log_per_minute`・既定60・`SANADAMARU_LOG_PER_MINUTE`）。出さなかった数は次の行と `report()` の `log_lines_not_written` に残ります。
- 記録に残す住所と UA で、見えない書式文字（表示の向きを変える U+202E など）と行・段落の区切りも「?」に替えます。
- `%scope` などの飾りが付いた番号は読みません。

**気をつけること：** Cloudflare の後ろにロードバランサーがある構成（Render など）で `cloudflare` を使っていた時は、`x-forwarded-for` と `SANADAMARU_TRUSTED_HOPS=2` に切り替えてください（[docs/deploy.md](docs/deploy.md)）。そのままでは見出しを読まず、締め出しも働きません（無関係な人を巻き込む側には倒れません）。

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
