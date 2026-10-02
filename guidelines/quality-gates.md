# 品質ゲート

## 決定論ゲート（機械判定。CI とローカルで同じものを同じ順に回す）

`scripts/verify-gates.sh`（Windows は `scripts\verify-gates.ps1`）で全部、`./gradlew qualityGate` で Java の分だけ実行できます。

| ID | ゲート | 合格基準 | 実体 |
|---|---|---|---|
| D1 | コンパイル | エラー 0（Java 17 向け） | `compileJava` |
| D2 | コーディング規約 | Checkstyle の違反 0 | `checkstyleMain` / `checkstyleTest` |
| D3 | 単体テスト | 全件成功 | `test` |
| D4 | 分岐網羅 | Service・Job の分岐網羅率が閾値以上（既定 80%。目標 100% に向けて引き上げる） | `jacocoTestCoverageVerification`（`-PbranchCoverageMinimum=1.0`） |
| D5 | バグパターン | SpotBugs の指摘 0（除外は理由付きでレビュー） | `spotbugsMain` |
| D6 | 実装の実在 | implemented 以上の要件の実装箇所が実在 | `spec-trace check`（`trace.implements_*`） |
| D7 | テストの実在と検証 | proven の要件のテストが実在し、アサーション 1 件以上 | `spec-trace check`（`trace.proof_*`） |
| D8 | 設計書ドリフト | 承認時の設計書ハッシュと一致 | `spec-trace check --enforce-drift`（`trace.spec_drift`） |
| D9 | SQL の安全性 | Mapper XML に `${}` が無い | `verifyMapperSql` |
| D10 | 結合シナリオ | 対応表のシナリオが実在し、`@ignore` でなく、`Then` / `match` がある | `spec-trace check`（シナリオ） |
| D11 | ルールの裏付け | 全ゲートに根拠ルールがあり、機械で確かめるルールにゲートがある | `scripts/verify_authority.py` |

CI でマージ前に必須とするのは D1〜D11 全部です。完了時（PR 前）は `--require proven`（全要件がテスト済み）も付けます。

## 非決定論ゲート（AI レビュー。reviewer エージェントが判定表を出す）

機械では判定しきれない観点です。**補助** であり、最終判断は人（RP4）が行います。

| ID | 観点 | 判定のしかた |
|---|---|---|
| N1 | 設計書の処理手順が全て実装にあるか | 設計書の STEP ごとに、対応するメソッドを挙げる。無いものは指摘 |
| N2 | メッセージ ID の網羅 | 設計書のメッセージ表と `messages.properties`・コード上の使用箇所を突き合わせる |
| N3 | CRUD の網羅 | 設計書のテーブル操作と Mapper XML の SQL を突き合わせる |
| N4 | トランザクション境界 | 設計書のコミット単位と `@Transactional` の位置が合っているか |
| N5 | 命名・用語 | 設計書の用語とクラス・メソッド名が対応しているか |
| N6 | テストの妥当性 | テストの期待値が設計書由来か（実装をなぞっていないか）、異常系・境界値があるか |

判定表の形式: `| ID | 対象 | 判定（OK / NG / 要確認） | 根拠（設計書の箇所とコードの箇所） |`
