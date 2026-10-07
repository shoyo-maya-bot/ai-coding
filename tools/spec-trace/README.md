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
| `trace.proof_failed` / `trace.proof_not_run` / `trace.proof_skipped` | （`--test-results` のとき）テストが失敗した / 結果に無い（実行されていない）/ スキップされた |
| `trace.proof_result_unchecked` | （`--test-results` のとき・警告）シナリオ（.feature）の実行結果は照合していない |

## テストが「実行されて成功した」ことも確かめる（--test-results）

既定の検査は「テストが実在し、アサーションがある」までで、テストが通ったかは見ません。
`--test-results` に JUnit 形式の結果（Gradle の `build/test-results/test`、`pytest --junitxml` など。ファイルかディレクトリ、複数可）を渡すと、
proven の要件のテストごとに、結果の中に **実行されて成功した記録があること** も求めます。CI と verify-gates はこれを使います。

```bash
./template/gradlew -p template test
spec-trace check traceability/specs --root . --require proven --test-results template/build/test-results/test
```

- 照合はクラス名（単純名）とメソッド名で行う。パラメータ化テスト（`parseRejects(String, String)[1]` など）は、全実行分が成功していれば成功
- 結果のファイルが無い・XML として読めないときは、黙って通さず終了コード 2 にする
- Karate などのシナリオ（`.feature`）は照合せず、`trace.proof_result_unchecked` の警告を出す

Python は構文木、Java / Kotlin / TypeScript 等は宣言行と括弧の対応による近似、Gherkin（英語・日本語）に対応します。
保証するのは「存在」と「最低限の検証」までで、テストの意味的な妥当性は人がレビューします。
