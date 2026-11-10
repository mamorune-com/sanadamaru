# 真田丸（sanadamaru）

**AI が休まず探しに来る「よくある穴」に偽の扉を置き、触れた相手を確かめる、守りの部品です。**
反撃はしません。相手のシステムには、こちらから一切触れません。

- Python で書かれていて、ほかの部品に依存しません。FastAPI・Starlette・Flask に数行で入ります（ASGI か WSGI で動くものなら、Django などにも入ります）。
- 本物の利用者が決して開かない住所だけを扉にするので、誤検知がほとんどありません。
- 締め出しは、既定でオフです（見張るだけ）。前に立つ仕組みを確かめてから、オンにできます。

```text
$ python -m sanadamaru demo
真田丸の試し（この機械の中だけで動きます。外へは何も送りません）

1. ふつうの利用者が「/」を開く
   → 真田丸は何もせず、本物の窓口へ通します

2. 探りが「/.env」を開く
   → 偽の扉です。作り物の中身を返して、記録しました（目印 env）
     中身の一部：DB_PASSWORD=app_live_9e3941f9c…（偽の鍵）

3. 探りが、持ち出した偽の鍵で「/api/admin/users」を呼ぶ
   → 偽の鍵です。断って（403）、記録しました（目印 env・欄 db）
```

> **名前の由来**　真田丸は、大坂冬の陣（1614年）で真田信繁が大坂城の南に築いた出城です。城の外に張り出した砦が攻め手を引きつけ、城の本体を守りました。

## なにをするもの

| 守り | 中身 |
|---|---|
| 偽の扉 | `/.env`・`/.git/config`・`/wp-login.php` など、攻撃がまず探す住所に、作り物の中身を返します。触れたことを記録します。 |
| 目印入りの偽の鍵 | 扉の中に、扉と欄ごとに違う偽の鍵を置きます。その鍵があとで使われたら、どの扉のどの欄から持ち出されたかが分かります。使われた時は断ります。 |
| 記録と知らせ | 時刻・扉・目印・送り元・UA の頭だけを、メモリに残します（件数に上限があります）。知らせは、同じ扉（目印）につき1時間に1回までです。 |
| 締め出し | 既定はオフです。オンにすると、扉に触れた送り元を一定時間（既定は24時間）断ります。死活監視や緊急の窓口は止めません。 |

## なぜ効くのか

AI を使った攻撃は、人よりずっと多くの住所を、休まず試します。まず探すのは、うっかり公開された設定ファイル（`/.env`）、ソースコードの履歴（`/.git/`）、データベースの控え（`*.sql`）のような「よくある穴」です。

本物の利用者は、`/.env` を開きません。だから扉に触れた時点で、ほぼ確実に「探りに来た者」だと分かります。見張りの道具によくある「誤検知の山」が、ここでは起きにくいのです。

偽の鍵は、もう一歩先を教えてくれます。持ち出した鍵を使おうとしたなら、相手は「見て回った」だけでなく「中に入ろうとした」のです。

## 越えない線

真田丸は、守りのための部品です。次の線は越えません。くわしくは [docs/lines.md](docs/lines.md) にあります。

1. 相手のシステムに触れない（仕返しをしない）
2. 相手の機械で、何かを動かさない（扉の中身は文字だけ）
3. 本物を置かない
4. 他社の鍵の形をまねない
5. 無関係な人を締め出さない
6. 命綱を止めない
7. 記録は最小限にする
8. 反撃は、記録を使った通報とテイクダウン依頼で行う

## 使い方

### 入れる

```bash
pip install "git+https://github.com/mamorune-com/sanadamaru@v0.2.0#subdirectory=python"
python -m sanadamaru demo
```

### FastAPI・Starlette

```python
from fastapi import FastAPI
from sanadamaru import Castle, SanadamaruMiddleware, log_alert

# 締め出し中でも止めない窓口（死活監視・緊急の窓口）を never_block に書きます
castle = Castle.from_env(never_block=("/health", "/api/sos"), alert=log_alert)

app = FastAPI()
# … ほかのミドルウェアや窓口 …
app.add_middleware(SanadamaruMiddleware, castle=castle)   # いちばん外側に置くため、最後に足します
```

### Flask

```python
from flask import Flask
from sanadamaru import Castle, SanadamaruWSGI, log_alert

castle = Castle.from_env(alert=log_alert)
app = Flask(__name__)
app.wsgi_app = SanadamaruWSGI(app.wsgi_app, castle=castle)
```

Django は [docs/deploy.md](docs/deploy.md) にあります。動く例は [examples/](examples/) にあり、CI が毎回動かしています。

### 設定（環境変数）

| 名前 | 既定 | 意味 |
|---|---|---|
| `SANADAMARU_SECRET` | なし | 偽の鍵を作る種（16バイト以上）。必ず設定してください。無いと、起動のたびに鍵が変わります。 |
| `SANADAMARU_BAN` | `0` | `1` で締め出しをオンにします。 |
| `SANADAMARU_BAN_SECONDS` | `86400` | 締め出しの長さ（秒）。 |
| `SANADAMARU_CLIENT_IP` | `direct` | 送り元の読み方（`direct`・`cloudflare`・`x-forwarded-for`）。 |
| `SANADAMARU_TRUSTED_HOPS` | `1` | `x-forwarded-for` の時の、前に立つ仕組みの数。 |
| `SANADAMARU_TRUSTED_PROXIES` | | 前に立つ仕組みの番号の範囲（カンマ区切り。例：`10.0.0.0/8`）。この範囲から届いた時だけ、転送の見出しを読みます。 |
| `SANADAMARU_LOG_PER_MINUTE` | `60` | 記録の行（WARNING）を1分に出す上限。超えた分は数えて、次の行に添えます。 |
| `SANADAMARU_NEVER_BLOCK` | | 締め出し中でも止めない住所（カンマ区切り。`/health` は常に入ります）。 |
| `SANADAMARU_KEY_PREFIX` | `app_live_` | 偽の鍵の書き出し。自分のサービスの鍵に似せてください（他社の鍵の形は使えません）。 |

### 記録を見る

`castle.report()` が、件数と最近の50件を返します。送り元の番号をそのまま含むので、管理の鍵で守った窓口からだけ出してください（例：[examples/fastapi_app.py](examples/fastapi_app.py)）。

### 知らせを受け取る

`alert=log_alert` を渡すと、知らせが ERROR の記録として出ます。Sentry などの見張りは ERROR を拾うので、そのまま運営者に届きます。自分で関数を書けば、Slack などにも送れます。知らせには、送り元の番号の頭だけが入ります。

## 締め出しをオンにする前に

締め出しで、いちばん避けたいのは、無関係な人を締め出すことです。オンにする前に、[docs/deploy.md](docs/deploy.md) の手順で、送り元の番号が正しく読めているかを確かめてください。

- Cloudflare だけが前に立つなら `SANADAMARU_CLIENT_IP=cloudflare`
- 前に立つ仕組みが1つなら `x-forwarded-for`（`SANADAMARU_TRUSTED_HOPS=1`）
- Cloudflare の後ろにロードバランサー（Render など）なら `x-forwarded-for`（`SANADAMARU_TRUSTED_HOPS=2`）
- 何も前に立っていなければ `direct`

念のため、Cloudflare 自身の番号と、公開されていない番号（社内・ロードバランサーなど）は、どの読み方でも締め出しません。転送の見出し（`CF-Connecting-IP`・`X-Forwarded-For`）は、前に立つ仕組みから届いた時だけ読みます。よそのページに埋め込まれた読み込み（`<img src=".../.env">` など）で開かれた時は、閲覧者本人の操作とは限らないので、記録だけして締め出しません。

## 第2段（兵糧攻め）を、一緒に考えてくれる人を探しています

扉に触れた相手だけを終わりのない偽の迷路に案内して、相手の AI の計算代と時間を空回りさせる「兵糧攻め」を考えています。似た考えは、Cloudflare の [AI Labyrinth](https://blog.cloudflare.com/ja-jp/ai-labyrinth) などにもあります。

ただ、迷路は自分の側にも負担がかかり、越えない線にも気をつける必要があります。そこで、作る前に、設計を一緒に考えてくれる人を探しています。条件と論点は [docs/stage2.md](docs/stage2.md) にあります。

## できないこと

- 扉を探さずに、本物の窓口だけを狙う攻撃は見つけられません。真田丸は、ほかの守り（ログイン・権限・入力の確かめ）の代わりにはなりません。
- 扉の住所は、よく知られた住所です。真田丸を知っている相手は、扉を避けられます。偽の鍵は、導入ごとに違うものになります。
- 記録と締め出しはメモリだけです。再起動で消え、複数のプロセスやサーバーの間では共有しません。

## 参考書

- [docs/how-it-works.md](docs/how-it-works.md)：仕組み（見る順番・偽の鍵の作り方・送り元の読み方・別の言語に移す時）
- [docs/deploy.md](docs/deploy.md)：入れる時の確かめ方
- [docs/lines.md](docs/lines.md)：越えない線
- [docs/stage2.md](docs/stage2.md)：第2段（兵糧攻め）の呼びかけ
- [SECURITY.md](SECURITY.md)：抜け道を見つけた時
- [CONTRIBUTING.md](CONTRIBUTING.md)：扉を足す・別の言語に移す
- [CHANGELOG.md](CHANGELOG.md)：変更の記録

## ライセンス

Apache-2.0 です。商用でも、無料で使えます。

株式会社MAMORUNE が、自分たちのサービスを守るために作ったものを、誰でも使える形にしました。姉妹の部品に、届いた連絡の割符を照らし合わせる [勘合（kango）](https://github.com/mamorune-com/kango) があります。

---

## English

**sanadamaru** places decoy "doors" at the paths that automated, AI-driven attackers probe first (`/.env`, `/.git/config`, `/wp-login.php`, `*.sql`, …) and records whoever touches them. Real users never open these paths, so a touch is a near-certain sign of probing, with almost no false positives.

- Decoy doors return plausible, entirely fake content.
- Each door embeds marked bait keys (one per door and field). If a bait key is later presented (Authorization, X-API-Key, query string, …), the request is refused and you learn which door and field it was taken from.
- Records keep only the time, door, marker, source address and a short user agent, in memory with hard caps. Alerts are rate-limited per door.
- Blocking is **off by default**. When enabled, it blocks the source for a while (24h by default). It never blocks your health or emergency endpoints, never blocks Cloudflare's own addresses or non-public addresses, only reads forwarding headers from a trusted proxy, and does not block requests made by a web page (for example an embedded image), since the visitor may not have chosen to make them.

It never touches the attacker's systems: no hack-back, nothing that runs on the visitor's machine, no real secrets, and no look-alikes of other companies' key formats. See [docs/lines.md](docs/lines.md) (Japanese).

```bash
pip install "git+https://github.com/mamorune-com/sanadamaru@v0.2.0#subdirectory=python"
python -m sanadamaru demo
```

```python
from fastapi import FastAPI
from sanadamaru import Castle, SanadamaruMiddleware, log_alert

castle = Castle.from_env(never_block=("/health", "/api/sos"), alert=log_alert)
app = FastAPI()
app.add_middleware(SanadamaruMiddleware, castle=castle)  # add it last so it is the outermost layer
```

Pure Python, no dependencies, ASGI and WSGI. Apache-2.0. We are looking for people to help design "stage 2": a safe tarpit maze, only for visitors who touched a door. See [docs/stage2.md](docs/stage2.md). To report a vulnerability, use **Security → Report a vulnerability** ([SECURITY.md](SECURITY.md)).
