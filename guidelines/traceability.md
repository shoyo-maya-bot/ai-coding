# トレーサビリティ（対応表）

## 2 つのグラフ

| グラフ | つなぐもの | ファイル | 確かめる道具 |
|---|---|---|---|
| 仕様のグラフ | 設計書の要件 → 実装 → テスト | `traceability/specs/<機能>.yaml` | `tools/spec-trace` |
| 権限のグラフ | ガイドラインのルール ↔ 品質ゲートのチェック | `traceability/authority.yaml` | `scripts/verify_authority.py` |

仕様のグラフは「作ったと言っているものが本当にあるか」、権限のグラフは「チェックに根拠があるか・ルールが空文化していないか」を確かめます。

## 対応表の書き方（1 機能 = 1 ファイル）

書式は `spec-trace schema` の JSON Schema が正です。例: [JOB0001](../traceability/specs/JOB0001_order-import.yaml)

```yaml
spec_id: "FEAT-JOB0001"
source: "samples/design-docs/batch/JOB0001_order-import.md"   # 必須（無いとドリフトを検知できない。消すと spec-pin がラベルを求める）
source_sha256: "..."            # 人が承認後に spec-trace pin で記録
requirements:
  - id: "REQ-JOB0001-003"        # REQ-<機能 ID>-<連番 3 桁>
    source: "JOB0001_order-import.md#STEP2"
    type: "business-rule"         # step / validation / crud / message / parameter / business-rule
    description: "登録済みの注文番号は登録しない"
    status: "proven"
    implements:
      - file: "template/src/main/java/com/example/app/order/OrderImportService.java"
        symbol: "OrderImportService#importLines"
    proofs:
      - file: "template/src/test/java/com/example/app/order/OrderImportServiceTest.java"
        symbol: "OrderImportServiceTest#rerunIsIdempotent"
```

## 状態の決め方

| 状態 | 誰が付けるか | 条件（spec-trace が確かめる） |
|---|---|---|
| pending | planner | なし |
| implemented | coder | implements のファイルと関数が実在する |
| proven | tester | proofs のテストが実在し、アサーションがある（シナリオは有効で Then / match がある）。`--test-results` では実行されて成功していること（シナリオだけで裏付ける要件は、シナリオの実行結果があること） |

状態を上げるのはエージェントでもよいですが、条件を満たさなければ CI が失敗します。状態を下げる（実装を消した等）のも同じ PR で行います。

## 設計書との関係

- 設計書は Front Matter に `id` を持ち、対応表の `source` から参照する
- 承認時の設計書のハッシュを `source_sha256` に記録する（`spec-trace pin`。人が実行）
- 設計書が変わると D8 で検知される。差分を見て、影響する要件を pending に戻してやり直す
