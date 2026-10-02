# guidelines — ルールの唯一の正（SSOT）

AI エージェントも人も、ここに書いたルールだけを根拠にします。プロンプト・エージェント定義・CI に同じルールを **書き写さない**
（参照する）ことで、ルールの食い違いを防ぎます。ルールを変えるときはこのフォルダを PR で変更します。

| ファイル | 内容 | 主に使う人 |
|---|---|---|
| [ai-principles.md](ai-principles.md) | AI 活用の位置づけ、品質担保の 5 原則、工程ごとの使い方 | 全員（最初に読む） |
| [workflow.md](workflow.md) | 5 フェーズの進め方、人のレビュー、差し戻し、自動修正の止め方 | 実行する人・エージェント |
| [coding-standards.md](coding-standards.md) | コーディング規約（命名・例外・ログ・SQL・テスト） | coder / tester / レビュアー |
| [project-structure.md](project-structure.md) | パッケージ構成、生成ファイルの置き場、生成順序 | planner / coder |
| [templates/batch-module.md](templates/batch-module.md) | バッチ 1 本に必要なファイルと書き方 | coder / tester |
| [templates/api-module.md](templates/api-module.md) | API 1 本に必要なファイルと書き方 | coder / tester |
| [quality-gates.md](quality-gates.md) | 品質ゲート（決定論 D1〜D10、非決定論 N1〜N6）と合格基準 | 全員 |
| [review-checklists.md](review-checklists.md) | 人のレビュー観点（RP1〜RP5） | レビュアー |
| [traceability.md](traceability.md) | 要件 ↔ 実装 ↔ テストの対応表の書き方と状態の決め方 | planner / tester / レビュアー |
| [design-doc-requirements.md](design-doc-requirements.md) | AI が実装に使う設計書に書いておくべきこと | 設計者 |
