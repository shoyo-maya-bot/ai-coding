# spec-trace（ai-coding 同梱）

要件 → 実装 → テストの対応表（`../../traceability/specs/*.yaml`）を検証し、
**裏付けのない「実装済み」「テスト済み」と、設計書の更新漏れ（ドリフト）を検出する** ツールです。
品質ゲート D6〜D8・D10（[../../guidelines/quality-gates.md](../../guidelines/quality-gates.md)）の実体です。

```bash
pip install -e tools/spec-trace                 # リポジトリのルートで
spec-trace check traceability/specs --root . --require proven
spec-trace pin traceability/specs/order-import.yaml --root .   # 設計書の承認後に人が実行
spec-trace schema                                # 定義ファイルの JSON Schema
```

| rule_id | 内容 |
|---|---|
| `trace.implements_empty` / `trace.implements_missing` | 実装済みなのに実装箇所が無い・見つからない |
| `trace.proofs_empty` / `trace.proof_missing` | テスト済みなのにテストが無い・見つからない |
| `trace.proof_no_assert` | テストに検証（assert / verify / expect / Then 等）が無い |
| `trace.proof_ignored` | シナリオが `@ignore` 等で無効化されている |
| `trace.spec_drift` | 設計書が承認時から変わっている |
| `trace.source_unpinned` / `trace.source_missing` | 設計書のハッシュが未記録 / 設計書が見つからない |
| `trace.duplicate_id` / `trace.not_done` | 要件 ID の重複 / `--require` の状態に達していない |

Python は構文木、Java / Kotlin / TypeScript 等は宣言行と括弧の対応による近似、Gherkin（英語・日本語）に対応します。
保証するのは「存在」と「最低限の検証」までで、テストの意味的な妥当性は人がレビューします。
