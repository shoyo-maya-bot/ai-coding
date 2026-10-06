# ai-coding

設計書（Markdown）から Spring Boot のバッチ・API の **コードと単体テストを AI（GitHub Copilot のエージェント）で β 版として作り**、
**品質ゲート（機械判定）と人のレビュー** で品質を担保するための仕組み（ハーネス）です。今後の開発プロセスの中心として使います。

> 特定の企業・案件の写しではなく、一般的な構成で作り直したものです。サンプルの業務（会員・注文）と ID はすべて架空です。

## 考え方

| 役割 | 置き場 | 内容 |
|---|---|---|
| ルール（唯一の正） | [guidelines/](guidelines/README.md) | 規約・構成・品質ゲート・レビュー観点・AI 活用の原則。AI も人もここだけを根拠にする |
| 検証 | [template/build.gradle](template/build.gradle)、[tools/spec-trace](tools/spec-trace/)、[scripts/](scripts/) | 決定論ゲート D1〜D11（コンパイル・規約・テスト・分岐網羅・バグパターン・SQL・対応表の実在・設計書ドリフト・ルールの裏付け） |
| 実行 | [.github/agents/](.github/agents/)、[.github/prompts/](.github/prompts/) | 役割別のエージェント（計画・実装・テスト・突合・進行） |

**AI の生成物は β 版です。人の全量レビューを前提にします。** 品質担保の 5 原則は [guidelines/ai-principles.md](guidelines/ai-principles.md)。

## 進め方（5 フェーズ）

**実務での使い方の早見表（いつ使うか・人が止まるところ・通らないとき）は [WORKFLOW.md](WORKFLOW.md)。**

| フェーズ | Copilot Chat で | やること | 区切りの人のレビュー |
|---|---|---|---|
| 1 計画 | `/ai-plan DOC-BATCH-JOB0001` | 生成ファイル一覧と対応表（全要件 pending）を作る | RP1 計画 → 承認後 `spec-trace pin` |
| 2 コード生成 | `/ai-code traceability/specs/<機能>.yaml` | ソースを作り、D1・D2・D5・D9 を通す | RP2 コード |
| 3 テスト生成 | `/ai-test traceability/specs/<機能>.yaml` | 単体テスト・Karate を作り、対応表を proven に | RP3 テスト |
| 4 突合 | `/ai-review traceability/specs/<機能>.yaml` | 設計書とコードの判定表（N1〜N6）を作る | RP4 最終確認 |
| 5 CI + PR | `/ai-pr JOB0001` | 全ゲートを再実行し、PR 本文を下書き | RP5 PR |

今どこにいるか分からなくなったら `/ai-status`。運用中の障害調査には `/incident-investigate`。
詳細と差し戻し・自動修正の止め方は [guidelines/workflow.md](guidelines/workflow.md)。

## すぐ試す（同梱のサンプルで）

前提: [dev-environment](https://github.com/shoyo-maya-bot/dev-environment) のローカル環境（Java 17・Rancher Desktop）と Python 3.12。

```bash
git clone https://github.com/shoyo-maya-bot/ai-coding.git && cd ai-coding
pip install -e tools/spec-trace            # 対応表の検証ツール
./scripts/verify-gates.sh --final          # Windows: .\scripts\verify-gates.ps1 -Final
```

同梱のサンプル（[JOB0001 注文ファイル取込](samples/design-docs/batch/JOB0001_order-import.md)、
[API0001/0002 会員照会・登録](samples/design-docs/api/API0001-0002_member.md)）は、5 フェーズを終えた状態（全要件 proven）です。
`template/` のコードを少し壊して `verify-gates.sh` を実行すると、どのゲートで止まるかを確かめられます。

## 実案件で使う

1. このリポジトリを会社の GitHub に複製する
2. `template/` の `com.example.app` を自分たちのパッケージに、`common/` を社内の共通ライブラリに置き換える
3. 設計書リポジトリを隣に clone し、[context-sources.yaml](context-sources.yaml) の `roots` を書き換える（CI での D8 は [設計書を別リポジトリに置くとき](guidelines/quality-gates.md#設計書を別リポジトリに置くときd8)）
4. `guidelines/` をチームの規約に合わせて直す（`traceability/authority.yaml` も合わせて直し、D11 を通す）
5. `samples/` と `traceability/specs/` のサンプルを消し、1 本目の設計書でフェーズ 1 から始める
6. [eval/](eval/README.md) の評価ループで、AI 生成と人の実装を比べてルールを育てる

## 構成

```text
ai-coding/
├── .github/
│   ├── copilot-instructions.md   # 全体の約束（禁止事項・止め方）
│   ├── agents/                   # planner / coder / tester / reviewer / orchestrator
│   ├── prompts/                  # /ai-plan … /ai-pr、/ai-status、/incident-investigate
│   ├── instructions/             # ファイルの種類ごとのルール（Java・テスト・Mapper）
│   ├── skills/                   # 圧縮したドメイン知識（メッセージ ID・Mapper・バッチ）
│   └── workflows/ci.yml          # D1〜D11
├── guidelines/                   # ルールの唯一の正
├── template/                     # 生成先の Spring Boot プロジェクト（品質ゲート入り）
├── traceability/
│   ├── specs/                    # 要件 ↔ 実装 ↔ テストの対応表（1 機能 1 ファイル）
│   └── authority.yaml            # ルール ↔ チェックの対応表
├── tools/spec-trace/             # 対応表の検証ツール
├── scripts/                      # verify-gates（CI と同じ順）、verify_authority、check_docs、check_template_drift
├── samples/design-docs/          # 架空の設計書（Front Matter の id で参照）
├── samples/ci/                   # 設計書を別リポジトリに置くときの CI の例
├── eval/                         # 評価ループ（ラン記録・指標）
└── context-sources.yaml          # 設計書の置き場と参照ルール
```

## 品質ゲート

| ID | 内容 | ID | 内容 |
|---|---|---|---|
| D1 | コンパイル（Java 17） | D7 | テストの実在とアサーション |
| D2 | Checkstyle | D8 | 設計書ドリフト |
| D3 | 単体テスト | D9 | Mapper XML の `${}` 禁止 |
| D4 | 分岐網羅（Service・Job） | D10 | Karate シナリオの実在・有効性 |
| D5 | SpotBugs | D11 | ルールとチェックの対応（越権・空文化の検出） |
| D6 | 実装の実在 | N1〜N6 | AI レビュー（設計書との突合。補助） |

このほか CI の `docs` ジョブで、ドキュメントと設定ファイルを検査します（`python scripts/check_docs.py`、ネットワーク不要）。

- Markdown の相対リンクとアンカー（`#見出し`）がリポジトリ内で解決できること
- `context-sources.yaml` の `roots` のフォルダと `types` のテンプレートが実在すること
- YAML・JSON がすべて読めること
- Copilot のファイルの Front Matter が読め、必須キーがあること（`*.instructions.md` は `applyTo`、`*.prompt.md`・`*.agent.md` は `description`、`SKILL.md` は `name`（フォルダ名と同じ）と `description`）

`template-drift` ジョブでは、`template/` が写し元（dev-environment の `sample-app`）から、
[template/UPSTREAM.yaml](template/UPSTREAM.yaml) に理由を書いた差分以外ずれていないことを確かめます（`python scripts/check_template_drift.py`）。

CI の Actions はコミット SHA で固定し（横にバージョンを書く）、権限は `contents: read` だけにしています。
更新は Dependabot（[.github/dependabot.yml](.github/dependabot.yml)）が月 1 回 PR で提案します。

## 関連リポジトリ

- [dev-environment](https://github.com/shoyo-maya-bot/dev-environment): ローカル・クラウドの開発環境（template はここのサンプルアプリが元）
- [doc-to-markdown](https://github.com/shoyo-maya-bot/doc-to-markdown): Excel 等の設計書を Markdown に
- [office-review](https://github.com/shoyo-maya-bot/office-review): 設計書のレビュー
- [quality-analytics](https://github.com/shoyo-maya-bot/quality-analytics): レビュー指摘の分析

## セキュリティ・ライセンス

- 脆弱性を見つけたら、公開の Issue ではなく [SECURITY.md](SECURITY.md) の方法で知らせてください
- ライセンスは [MIT](LICENSE) です
