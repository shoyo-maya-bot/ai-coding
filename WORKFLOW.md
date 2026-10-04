# WORKFLOW — 設計書から実装・単体テスト・PR までの実務の流れ

このページは **入り口と早見表** です。ルールの正は [guidelines/workflow.md](guidelines/workflow.md)（5 フェーズ・差し戻し・自動修正の止め方・禁止事項）と
[guidelines/review-checklists.md](guidelines/review-checklists.md)（人のレビュー RP1〜RP5）です。食い違ったら guidelines が正しいとし、このページを直します。

## いつ使うか

| きっかけ | 始め方 |
|---|---|
| 新しいバッチ・API の設計書が承認された | フェーズ 1 から（`/ai-plan <設計書の id>`） |
| 設計書が改訂された（CI が `trace.spec_drift` で失敗） | 差分を確かめ、影響する要件を pending に戻してフェーズ 1 から |
| 途中で中断した・どこまで進んだか分からない | `/ai-status` |
| 運用中に障害が起きた | `/incident-investigate`（原因の候補と確認手順。コードは直さない） |

設計書が Excel・Word のときは、先に doc-to-markdown で Markdown にして `id` を付けます（[doc-to-markdown の WORKFLOW](https://github.com/shoyo-maya-bot/doc-to-markdown/blob/main/WORKFLOW.md)）。

## 早見表

| # | Copilot Chat で | AI がやること | 人が確かめること（ここで止まる） | 通らないとき |
|---|---|---|---|---|
| 1 | `/ai-plan DOC-BATCH-JOB0001` | 生成ファイル一覧と対応表（全要件 pending）、確認事項 | **RP1**: 要件の漏れ・大きさ、確認事項。承認したら人が `spec-trace pin` | 確認事項が残る → 設計者に聞く。推測で埋めさせない |
| 2 | `/ai-code traceability/specs/<機能>.yaml` | ソースを作り、D1・D2・D5・D9 を通す（自動修正は最大 3 回） | **RP2**: 層の責務、例外・メッセージ ID、SQL、トランザクション、除外の追加が無いか | 3 回で通らない・同じエラーが続く → AI が止まって人に戻す（下記） |
| 3 | `/ai-test traceability/specs/<機能>.yaml` | 単体テスト・Karate を作り、対応表を proven に | **RP3**: 期待値が設計書由来か、異常系・境界値、アサーションが弱くないか | 分岐網羅（D4）が足りない → 理由を説明させる。閾値は下げない |
| 4 | `/ai-review traceability/specs/<機能>.yaml` | 設計書とコードの判定表（N1〜N6）。コードは直さない | **RP4**: NG・要確認を全部判断。設計書の誤りは修正依頼を起票 | NG → フェーズ 2 か 3 に差し戻す |
| 5 | `/ai-pr JOB0001` | 全ゲート（D1〜D11）を再実行し、PR 本文を下書き | **RP5**: CI 全通過、PR 本文、変更範囲が計画どおり | CI の失敗 → 該当フェーズに戻る |

ゲートの中身（D1〜D11、N1〜N6）は [guidelines/quality-gates.md](guidelines/quality-gates.md)。ローカルで CI と同じ順に流すには:

```bash
./scripts/verify-gates.sh            # Windows: .\scripts\verify-gates.ps1
./scripts/verify-gates.sh --final    # 完了時（全要件 proven を必須にする）
```

## AI が止まって人に戻ってきたとき

AI は次のどれかで自動修正をやめ、各回の修正内容・エラーの推移・止めた理由を添えて戻ってきます（[guidelines/workflow.md](guidelines/workflow.md)）。

| 戻ってきた理由 | 人がすること |
|---|---|
| 3 回直しても通らない／同じエラーが 2 回続いた | エラーの原因を読み、設計書の不足か、規約・テンプレートの不足かを見分ける。前者は設計者へ、後者は guidelines を直す PR |
| A → B → A と行き来している | 2 つの要件か規約がぶつかっている。どちらを優先するかを決めて指示する |
| 直すたびにエラーが増えている | そのフェーズを捨ててやり直す（計画が悪いことが多いのでフェーズ 1 から） |

**ゲートを甘くして通すのは禁止** です（期待値を実装に合わせる、アサーションを消す、除外を足す、テストを無効にする、閾値を下げる）。

## 出てくるものの見方

| 見るもの | 意味 |
|---|---|
| `verify-gates` の表で FAIL | その行のゲートの出力を読む。D6〜D8・D10 は spec-trace のメッセージに要件 ID が出る |
| `trace.spec_drift` | 承認後に設計書が変わった。差分を確かめ、影響する要件を pending に戻す。直したあとの `spec-trace pin` は人がレビュー後に行う |
| reviewer の判定表の「要確認」 | AI が設計書だけでは決められなかった点。人が決めて、必要なら設計書を直す |
| PR の AI レビュー（auto-review を入れた場合） | 下書き。「検証済み」の MUST から見る。却下された指摘は折りたたまれている（[agent-lab/auto-review](https://github.com/shoyo-maya-bot/agent-lab/tree/main/auto-review)） |

## 次に渡すもの

| 次にやること | ツール |
|---|---|
| レビューの指摘（RP1〜RP5・PR）の傾向を見て、ルールを育てる | quality-analytics（`qa collect` → `qa classify` → `qa analyze`） |
| AI 生成と人の実装を比べて、プロンプトと guidelines を直す | [eval/](eval/README.md) の評価ループ |
| 設計書の改訂を追う | design-diff（Excel の新旧差分）→ このページの「いつ使うか」の 2 行目へ |

## 守ること

- **AI の生成物は β 版**。人の全量レビュー（RP1〜RP5）を前提にする
- `spec-trace pin`、PR のマージは **人が** 行う
- 業務の設計書を AI に渡してよい範囲は、社内の規程と Copilot の契約で確かめる
