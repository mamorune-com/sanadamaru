# 引き継ぎ資料（HANDOVER）— 真田丸（sanadamaru）

最終更新：2026-11-09。保守する人が交代する時に、次の保守者と AI が迷わず続けられるようにするための資料です。

## 1. これは何か

- AI が休まず探しに来る「よくある穴」（`/.env` など）に偽の扉を置き、触れた相手を確かめる守りの部品です（オープンソース・Python・依存なし）。
- 反撃はしません。締め出しは既定でオフです。
- 使っている所：MAMORUNE の共有の頭脳（環境変数 `SANADAMARU_BAN`・`SANADAMARU_BAN_SECONDS` で締め出しを切り替える）。

## 2. しくみ

| 場所 | 中身 |
|---|---|
| `python/` | 本体とテスト |
| `docs/` | `how-it-works.md`（しくみ）・`lines.md`（越えない線）・`deploy.md`（入れ方）・`stage2.md`（次の段階） |
| `examples/` | FastAPI・Flask などへの入れ方の例 |
| `CHANGELOG.md` | 版ごとの変更 |
| `.github/workflows/` | `ci.yml`（テスト）・`release-check.yml`（版の名札を付けた時の確かめ） |

試し：`python -m sanadamaru demo`（この機械の中だけで動く）。

## 3. 版を出す手順

1. 変更とテスト（CI が緑）。`CHANGELOG.md` に書く。
2. 版の番号を上げてから名札（`v0.x.y`）を付けてリリースを作る。
3. 共有の頭脳など、使っている側の版を上げてもらう。

## 4. 頼っている外部サービス

GitHub（リポジトリ・Actions・Releases）だけです。秘密の値はありません。

## 5. お金

収入も費用もありません。ライセンスは `LICENSE` と `NOTICE`。

## 6. 問題が届いた時

`SECURITY.md` の手順で受けます。本物の利用者を誤って締め出す報告は、いちばん優先して直します（越えない線は `docs/lines.md`）。

## 7. 未解決の課題（2026-11-09）

開いている Issue・プルリクエストはありません。次の段階の構想は `docs/stage2.md`。

## 8. 保守者が交代する時

- GitHub の組織 mamorune-com で、新しい保守者に Maintain 以上の権限を渡す。
- 続ける人がいない時は、README の先頭に「保守を止めました」と書いてリポジトリをアーカイブする。

## 9. AI に引き継ぐ時の最初の一言

> sanadamaru の HANDOVER.md と README.md を読んで、版を出す手順と、いま気をつけることをまとめてください。まだ何も変更しないでください。
