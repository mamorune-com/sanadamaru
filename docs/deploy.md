# 入れる時の確かめ方

[English](en/deploy.md) ・ **日本語**

## 1. 扉の住所が、本物の窓口と重ならないか

`python -m sanadamaru doors` で既定の扉の一覧を見て、自分のアプリに同じ住所の本物の窓口が無いかを確かめます。あれば、その扉を消してください。重なったままだと、本物の利用者が記録され、締め出しがオンなら締め出されます。

```python
from sanadamaru import Castle, default_doors

doors = default_doors()
doors.pop("/actuator/env")          # 自分のアプリが使う住所なら消す
castle = Castle.from_env(doors=doors)
```

扉を足す時の約束は、[CONTRIBUTING.md](../CONTRIBUTING.md) にあります。

## 2. secret を決める

`SANADAMARU_SECRET` に、16バイト以上のでたらめな値を入れます。

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

- 本物の鍵と同じように、コードには書かず、環境変数に入れてください。
- secret を変えると、それまでに持ち出された偽の鍵は照合できなくなります。

## 3. いちばん外側に置く

ほかのミドルウェア（ログイン・CORS など）より外側に置きます。

```python
# FastAPI・Starlette：最後に add_middleware したものが、いちばん外側です
app.add_middleware(SanadamaruMiddleware, castle=castle)

# Flask
app.wsgi_app = SanadamaruWSGI(app.wsgi_app, castle=castle)

# Django（asgi.py）
application = SanadamaruMiddleware(get_asgi_application(), castle=castle)

# Django（wsgi.py）
application = SanadamaruWSGI(get_wsgi_application(), castle=castle)
```

## 4. 止めない窓口を書く

死活監視（`/health`）と、緊急の窓口を `never_block` に書きます。締め出し中でも通り、偽の鍵が出されても断りません。

```python
castle = Castle.from_env(never_block=("/health", "/api/sos"))
# または環境変数で：SANADAMARU_NEVER_BLOCK=/api/sos（/health は常に入ります）
```

## 5. 記録の窓口を、管理の鍵で守る

`castle.report()` は、送り元の番号をそのまま含みます。誰でも開ける住所には置かず、管理の鍵で守った窓口から出してください。鍵を比べる時は、時間の差で中身を推し量られないよう `hmac.compare_digest` を使います（例：[examples/fastapi_app.py](../examples/fastapi_app.py)）。

## 6. 知らせを、運営者に届ける

```python
from sanadamaru import Castle, log_alert
castle = Castle.from_env(alert=log_alert)   # ERROR の記録として出す。Sentry などが拾います
```

自分で関数を書けば、Slack などにも送れます。関数には、送り元の番号の頭だけが入った記録の1件が渡ります。

## 7. 締め出しは、見張って数日たってから

1. まずは、見張るだけ（既定）で入れます。
2. 自分で1回、扉を開きます（例：ブラウザで `https://自分のサービス/.env`）。
3. 記録の一覧（`report()` の `recent`）で、`ip` が自分の回線の番号になっているかを確かめます。
   - Cloudflare の番号（`104.16.` や `172.64.` などで始まる番号）になっていたら、読み方がまちがっています。
   - 空になっていたら、番号を読めていません。
4. 合っていたら、数日見張って、記録の数と中身を見ます。
5. 締め出しをオンにします（`SANADAMARU_BAN=1`）。

| 前に立つもの | `SANADAMARU_CLIENT_IP` | `SANADAMARU_TRUSTED_HOPS` |
|---|---|---|
| 何も無い | `direct` | |
| Cloudflare だけ（直接の相手が Cloudflare の番号） | `cloudflare` | |
| `X-Forwarded-For` の右端に相手の番号を足す仕組みが1つ | `x-forwarded-for` | `1` |
| 同じような仕組みが2つ（例：Cloudflare の後ろにロードバランサー。Render など） | `x-forwarded-for` | `2` |

- 転送の見出しは、直接の相手が前に立つ仕組みの時だけ読みます。`x-forwarded-for` では、公開されていない番号（同じ建物の中のロードバランサーなど）を前に立つ仕組みとみなします。公開されている番号のロードバランサーや CDN の後ろでは、`SANADAMARU_TRUSTED_PROXIES` にその範囲を書いてください。
- Cloudflare の後ろにロードバランサーがある構成で `cloudflare` を選ぶと、直接の相手がロードバランサーになるので、見出しを読みません（`ip` がロードバランサーの番号になり、締め出しません）。`x-forwarded-for` の `2` を選んでください。
- 段数がまちがっていると、`ip` が空になります（締め出しません）。3. の確かめで気づけます。

**オンにした後は、ご自身で扉を試さないでください。** 自分の回線も締め出されます（既定は24時間）。解く時は、アプリを再起動します（締め出しはメモリにあるため）。

## 8. 記録は、正しい道で使う

記録は、警察の相談窓口・JPCERT/CC・攻撃に使われた番号の持ち主の abuse 窓口への連絡に使います。相手へ仕返しはしません（[越えない線](lines.md)）。
