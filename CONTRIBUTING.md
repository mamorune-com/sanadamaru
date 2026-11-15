# 手伝ってくださる方へ

真田丸を育ててくださる方を歓迎します。どの変更も、[越えない線](docs/lines.md) に照らしてから取り込みます。

## 扉を足す・直す

1. [python/sanadamaru/doors.py](python/sanadamaru/doors.py) に、中身を作る関数と、`default_doors()` の住所を足します。
2. 中身は、次の約束を守ってください。
   - 文字だけ。スクリプトや、開くと重くなるファイルは入れない。
   - 作り物だけ。本物の鍵・設定・利用者の情報、実在の人に見える名前やメールアドレスは入れない。
   - 偽の鍵は `key("欄の名前")` で埋め込む。他社の鍵の形はまねない。
   - 開くたびに同じ中身にする（乱数や時刻を入れない）。
3. ふつうの Web アプリの本物の窓口と重ならない住所か、確かめてください。
4. Pull Request に、その住所が実際に探されている根拠を書いてください。公開されている調査や、ご自身のサーバーの記録の件数などです。送り元の番号は消してください。
5. `cd python && python -m pytest` が通ることを確かめてください。既定の扉は、テストが中身の約束を毎回確かめます。

## 別の言語・枠組みに移す

Express・Go・Rails などへの移植を歓迎します。[docs/how-it-works.md](docs/how-it-works.md) の「別の言語に移す時」に沿ってください。別のリポジトリで作っていただいても構いません。Issue で知らせていただければ、README からご案内します。

## 第2段（兵糧攻め）

[docs/stage2.md](docs/stage2.md) の条件を読み、まず Issue で設計から話し合いましょう。コードの Pull Request は、設計が決まってからお願いします。

## 審査について

送り元の読み方と締め出し（`netaddr.py`・`castle.py`）は、まちがえると無関係な人を締め出します。この部分の変更は、管理者がとくに注意して確かめます。越えない線を緩める変更は、取り込みません。

## 抜け道を見つけた時

公開の Issue や Pull Request には書かず、[SECURITY.md](SECURITY.md) の方法で、非公開でお知らせください。

---

## English

Contributions are welcome. Every change is checked against [the lines sanadamaru never crosses](docs/en/lines.md) before it is merged.

**Adding or fixing a door.** Add a content function and the path to `default_doors()` in [python/sanadamaru/doors.py](python/sanadamaru/doors.py). Content must be plain text only, entirely fake (no real keys, settings, user data, or names and emails that look like real people), use `key("field")` for bait keys (never another company's key format), and be identical on every read (no randomness or timestamps). Make sure the path does not collide with real endpoints in ordinary web apps. In the pull request, include evidence that the path is actually probed, such as published research or hit counts from your own server logs, with source addresses removed. Run `cd python && python -m pytest`; the tests check the content rules for every default door.

**Porting to another language or framework.** Ports to Express, Go, Rails and others are welcome. Follow "Porting to other languages" in [docs/en/how-it-works.md](docs/en/how-it-works.md). A port can live in its own repository; open an issue and we will link to it from the README.

**Stage 2 (the tarpit).** Read the conditions in [docs/en/stage2.md](docs/en/stage2.md) and start with a design discussion in an issue. Please send code only after the design is settled.

**Review.** Mistakes in client address handling and blocking (`netaddr.py`, `castle.py`) can lock out innocent people, so maintainers review changes there with particular care. Changes that loosen the lines will not be merged.

**Found a loophole?** Do not post it in a public issue or pull request. Report it privately as described in [SECURITY.md](SECURITY.md).
