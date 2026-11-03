# セキュリティの問題を見つけた時

真田丸は、探りに来た相手を確かめる守りの部品です。**真田丸のせいで、無関係な人が締め出される・本物の情報が漏れる・サービスが止まる**抜け道は、悪用されると、真田丸を入れた人や、その利用者を傷つけます。見つけた時は**公開の Issue には書かず**、次の方法で、非公開でお知らせください。

## 知らせ方

1. このリポジトリの「**Security**」タブを開き、「**Report a vulnerability**」から送ってください。GitHub の非公開の報告の仕組みで、報告した人と管理者だけが読めます。
2. 「Report a vulnerability」が見当たらない時は、公開の Issue に「セキュリティについて非公開で連絡したい」とだけ書いてください（中身は書かないでください）。非公開の連絡方法をお伝えします。

## セキュリティの問題として扱うもの

- 説明どおりに設定していても、送り元の番号を偽って、無関係な人を締め出させられる
- 止めない窓口（`never_block`）が止まる
- 問い合わせの工夫で、真田丸の中で例外が起きる・重くなる・メモリを食いつぶす
- 真田丸を使うと、本物の鍵・設定・利用者の情報が外へ出る、または記録に残る
- 記録の行を書き換えられる（改行の差し込みなど）
- 真田丸の配布物が改ざんされている疑い

## 公開の Issue でよいもの

- 扉の中身が、偽物だと見破られやすい（中身の改善の提案）
- 扉の追加・削除の提案
- 説明のまちがい

## 知らせる時のお願い

- 実在の人の番号や情報は、消してから送ってください。
- 他人のサービスで試した結果は送らないでください。ご自身の手元で確かめた方法を書いてください。
- 真田丸のどの版で起きたか（例：v0.1.0）を書いてください。

## こちらからのお返事

- 提供元は小さな会社のため、お返事までの日数はお約束できませんが、できるだけ早く確かめます。
- 直したら新しい版を出し、[変更の記録](CHANGELOG.md) とリリースの説明でお知らせします。ご希望があれば、見つけた方のお名前を載せます。
- 報奨金の制度はありません。

## 直す版

いちばん新しい版だけを直します。古い版を使っている時は、新しい版に上げてください。

## 真田丸の外のこと

- 真田丸を組み込んだサービスの問題は、そのサービスの提供元へお知らせください。
- 攻撃を受けている時は、警察の相談窓口や JPCERT/CC へご相談ください。

---

## English

Please do not report security issues in public issues. Use **Security → Report a vulnerability** (GitHub private vulnerability reporting). If that button is not available, open a public issue that only says you would like to report a security issue privately, without any details.

Security issues include: making sanadamaru block unrelated people despite a documented configuration; blocking a `never_block` endpoint; requests that crash it, slow it down or exhaust memory; real secrets or user data leaving the service or being logged; forging log lines; tampered distributions. Ideas to make decoys more convincing, door proposals and documentation fixes can be public issues. Please do not send results of tests against other people's services. Only the latest version receives fixes. There is no bug bounty.
