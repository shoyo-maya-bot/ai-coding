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
| 下準備 | [tools/test-scaffold](tools/test-scaffold/) | Excel のテスト仕様書から JUnit 5 のテストの雛形を作る（LLM を使わない。本体は `fail` で、雛形のままでは通らない） |

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

テスト仕様書が Excel であるときは、フェーズ 3 の前に `/ai-test-scaffold`（[tools/test-scaffold](tools/test-scaffold/README.md)）で雛形を作れます。
今どこにいるか分からなくなったら `/ai-status`。運用中の障害調査には `/incident-investigate`。
詳細と差し戻し・自動修正の止め方は [guidelines/workflow.md](guidelines/workflow.md)。

## すぐ試す（同梱のサンプルで）

前提: [dev-environment](https://github.com/shoyo-maya-bot/dev-environment) のローカル環境（Java 17・Rancher Desktop）と Python 3.10 以上（CI は 3.12）。

```bash
git clone https://github.com/shoyo-maya-bot/ai-coding.git
cd ai-coding
python -m pip install -e "tools/spec-trace[dev]" -e "tools/test-scaffold[dev]" pyyaml -c constraints.txt   # 検証ツール・雛形ツールと、テスト・lint の道具（版は constraints.txt で固定）
git config core.hooksPath .githooks        # push の前にドキュメントの検査（禁止事項の複写の一致など）を実行する
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
│   ├── prompts/                  # /ai-plan … /ai-pr、/ai-test-scaffold、/ai-status、/incident-investigate
│   ├── instructions/             # ファイルの種類ごとのルール（Java・テスト・Mapper）
│   ├── skills/                   # 圧縮したドメイン知識（メッセージ ID・Mapper・バッチ）
│   └── workflows/ci.yml          # D1〜D11
├── guidelines/                   # ルールの唯一の正
├── template/                     # 生成先の Spring Boot プロジェクト（品質ゲート入り）
├── traceability/
│   ├── specs/                    # 要件 ↔ 実装 ↔ テストの対応表（1 機能 1 ファイル）
│   ├── authority.yaml            # ルール ↔ チェックの対応表
│   └── gate-config-baseline.yaml # D2・D5 の設定（checkstyle.xml・exclude.xml）の基準（D11 が弱体化を検出）
├── tools/spec-trace/             # 対応表の検証ツール
├── tools/test-scaffold/          # Excel のテスト仕様書 → JUnit 5 のテストの雛形
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
| D5 | SpotBugs | D11 | ルールとチェックの対応（越権・空文化の検出）と、ゲートの弱体化の検出 |
| D6 | 実装の実在 | N1〜N6 | AI レビュー（設計書との突合。補助） |

CI は `scripts/verify-gates.sh`（Linux）と `scripts\verify-gates.ps1`（Windows PowerShell 5.1）を呼ぶだけで、手元の verify-gates と同じ内容・同じ順に実行します
（中身は [guidelines/quality-gates.md](guidelines/quality-gates.md)）。PR は全要件 `implemented` 以上、main への push は `--final`（全要件 `proven`）です。
`proven` の要件は、テストが実在してアサーションがあるだけでなく、JUnit の結果 XML（`template/build/test-results/test`）で **実行されて成功した** ことも確かめます。
D10 の Karate シナリオは CI では実行しません（起動中のアプリが要るため。存在・有効性・確認の有無だけを見ます）。
ほかに `security` ジョブで bandit と pip-audit を流します。

### 分岐網羅（D4）の閾値と目標

- ガイドの **目標は 100%**（[guidelines/quality-gates.md](guidelines/quality-gates.md)）。ゲートで必須にしているのは **下限 80%**
  （`template/build.gradle` の `branchCoverageFloor`）で、目標に向けて段階的に引き上げます
- 引き上げは `-PbranchCoverageMinimum=0.9` などで試し、定着したら `branchCoverageFloor` と `scripts/verify_authority.py` の
  `MIN_BRANCH_COVERAGE` を同じ PR で上げます
- **下げることはできません**。`-PbranchCoverageMinimum`（`ORG_GRADLE_PROJECT_branchCoverageMinimum`・`gradle.properties` も）に
  下限より低い値を渡すと Gradle が失敗し、D11（`verify_authority.py`）も下限・既定値の引き下げ、verify-gates・ワークフロー・
  `gradle.properties`・実行時の環境変数での引き下げを error にします
- D11 は同じく、`qualityGate` の `dependsOn` からゲート（`spotbugsMain` など）を外す、`ignoreFailures`・`failOnViolation`・
  `maxWarnings`・ゲートのタスクの `enabled` をリテラルの `false`・`true`・`0`・`true` 以外にする（`!false` などの式も）、
  ゲートのタスクに `onlyIf` を付ける、も検出します
- D2・D5 の設定ファイル（`checkstyle.xml`・`exclude.xml`）も、基準（`traceability/gate-config-baseline.yaml`）より弱くすると
  D11 が検出します。強める変更はそのまま通り、設定値の変更・除外の追加はレビューの承認後に
  `python scripts/verify_authority.py --write-baseline` で基準を同じ PR で更新します

verify-gates の `docs` ゲートでは、ドキュメントと設定ファイルを検査します（`python scripts/check_docs.py`、ネットワーク不要）。

- Markdown の相対リンクとアンカー（`#見出し`）がリポジトリ内で解決できること
- `context-sources.yaml` の `roots` のフォルダと `types` のテンプレートが実在すること
- YAML・JSON がすべて読めること
- Copilot のファイルの Front Matter が読め、必須キーがあること（`*.instructions.md` は `applyTo`、`*.prompt.md`・`*.agent.md` は `description`、`SKILL.md` は `name`（フォルダ名と同じ）と `description`）
- Copilot のファイル（エージェント・プロンプト・指示）のコマンドに `&&` が無いこと（Windows PowerShell 5.1 で動かないため）
- 禁止事項（[guidelines/workflow.md](guidelines/workflow.md#禁止事項ゲートのこじ開け) の一覧と 1 行の要約）が、
  `.github/copilot-instructions.md` と `.github/agents/` の 5 ファイルにそのまま複写されていること（正を含めて 7 ファイル）

同じ検査を push の前にも実行できます（`git config core.hooksPath .githooks` で `.githooks/pre-push` を有効にする。clone ごとに 1 回）。

`template drift` ゲートでは、`template/` が写し元（dev-environment の `sample-app`）から、
[template/UPSTREAM.yaml](template/UPSTREAM.yaml) に理由を書いた差分以外ずれていないことを確かめます（`python scripts/check_template_drift.py`）。
依存ライブラリと Gradle の版は写し元で上げ、マージ後に `--ref main` で差分を見て取り込みます（手順は UPSTREAM.yaml の先頭）。
そのため Dependabot は、template の写し元と揃える依存を上げません（template にだけある SpotBugs などは上げます）。
写し元の main が進んで取り込むべき変更が溜まっていないかは、週 1 回の [template-drift](.github/workflows/template-drift.yml) が
`--ref main` で確かめ、ずれがあれば Issue を 1 件作ります（開いている Issue があればコメントを足し、直ったら閉じる）。

## 変更点

| 時期 | 変更 | 影響 |
|---|---|---|
| 2026-10 | template を写し元（dev-environment 7c81560）に合わせた: 内容の違う重複を終了コード 6（APPW0002）で知らせる、CSV の引用符に対応、409 の応答にメールアドレスを入れない、ジョブ ID の照合を `@ConditionalOnProperty` と同じに（大文字小文字を区別しない）、バッチの起動失敗も終了コード 8、Dockerfile の例を追加。Checkstyle・spec-trace に合わせた差分は template/UPSTREAM.yaml に理由付きで記録 | 重複の内容が違う行は 4 ではなく 6 で終わる。APPE0003 の文言が変わる |
| 2026-10（第 7 回） | D11: `ignoreFailures = !false` のような式・変数での弱体化（リテラル以外の値）、ゲートのタスクの `onlyIf { … }`、`checkstyle.xml` のモジュールの削除・設定の変更・抑止のフィルタ、SpotBugs の `exclude.xml` への除外の追加、`build.gradle` での設定ファイルの差し替えを検出（基準は `traceability/gate-config-baseline.yaml`）。test-scaffold の `--merge`: 項番を振り直した仕様書でも名前だけで照合せず、雛形の目印と観点で対応づける（項番が同じでも観点が違えば別のケースとして別名で足し、警告）。`--proofs-out` は既存のメソッドを既存の名前で書く | Checkstyle の設定値を変える・SpotBugs の除外を足す PR は、`--write-baseline` で基準も更新しないと D11 で落ちる。項番を振り直した仕様書で `--merge` すると、警告が出て（`--strict` なら終了コード 1）、新しいケースが `_2` 付きの名前で足される |
| 2026-10（第 6 回） | D11: ゲートの弱体化を `ignoreFailures.set(true)`・`X.enabled = false`・`onlyIf { false }`・`tasks.withType(Test) { enabled = false }` の書き方でも検出。`test` タスクでのテストの除外・絞り込み、D4 の対象（`coverageTargets`）の縮小・除外、verify-gates・ワークフローの `-x <ゲート>` も検出。D9: Mapper インターフェースの `@Select` 等の `${}` も検出。spec-trace: 行頭から始まる複数行の呼び出しをテストの宣言とみなさない（アサーションの無いテストが D7 を素通りしていた）。Python の結果の照合で、ファイル名だけの一致は同名のテストファイルがほかに無いときだけ。devtools-common の固定を 04f3915 に | これらの書き方でゲートを弱めた template・アサーションの無いテストは D11・D9・D7 で落ちる。pytest の rootdir をテストのフォルダにしていて、同名のテストファイルが複数あると `trace.proof_not_run`（rootdir をリポジトリのルートにする） |
| 2026-10 | Excel のテスト仕様書から JUnit 5 のテストの雛形を作る [tools/test-scaffold](tools/test-scaffold/README.md) と `/ai-test-scaffold` を追加。verify-gates の tools tests でそのテストも実行し、constraints.txt に openpyxl を追加。spec-trace の `--test-results` は `@DisplayName` の付いたテストを表示名でも照合する（Gradle の結果ではテストの名前が表示名になり、これまで `trace.proof_not_run` になっていた） | 手元で verify-gates を流すには `python -m pip install -e "tools/test-scaffold[dev]" -c constraints.txt` も要る（README の手順は更新済み） |
| 2026-10（第 5 回） | spec-trace: pin（`source_sha256`）の無い対応表は `--require proven`（`--final`・main）で error。spec-pin は pin の無い対応表の新規追加にも `spec-pin-approved` ラベルを求める。テスト結果はパッケージ付きのクラス名（Java は `package` 宣言、Python はファイルのパス）で照合する。D11 が `build.gradle` のゲートの弱体化（`qualityGate` からの除外・`ignoreFailures = true` など）と D4 の閾値の引き下げを検出。D4 の下限（80%）より低い `-PbranchCoverageMinimum` は Gradle が失敗する | pin の無い対応表は main で落ちる・新規追加の PR はラベルが要る。別のパッケージの同名のテストクラスの結果では proven にならない。D4 の閾値は上げられるが下げられない |
| 2026-10（第 4 回） | spec-trace: 対応表の `source:` を必須に（スキーマ・`--enforce-drift`）、spec-pin は `source:` の削除・差し替えにもラベルを求める。パラメータ化テストの結果を引数名の並びでメソッドごとに対応づける（別のメソッドの成功を数えない）。シナリオだけで裏付けた要件は、シナリオの実行結果が無ければ未証明（`trace.proof_unverified`）。AssertJ の `assertThat(x)` だけ（終端の検証なし）はアサーションに数えない。template を写し元（dev-environment e5705d7）に合わせた（S3 から読むときも不正な UTF-8 で例外→終了コード 8）。devtools-common の固定を 6a263b8 に。eval の記録の手順と例、AI 利用の上限を追記 | `source:` の無い対応表・`assertThat(x)` だけのテスト・シナリオだけの proven は D7・D8・D10 で落ちる。同じクラスに引数名の並びが同じパラメータ化テストが 2 つあると照合できない（引数名か表示名を変える） |
| 2026-10 | PR で設計書の承認ハッシュ（`source_sha256`）が変わったら `spec-pin-approved` ラベルを求める CI（spec-pin）を追加。spec-trace: アサーションの判定をライブラリの明示リストに（`toString` などを数えない）、`symbol` の無い proofs をエラーに（スキーマでも必須）、Feature 全体の `@ignore` とテキストブロックに対応。template を写し元（dev-environment 2002ca0）に合わせた（入力ファイルの大きさの上限 `app.batch.max-input-bytes`、DefaultFileFetcher・S3Config のテスト）。spec-trace の devtools-common の固定を cbe97d5 に | pin を変える PR は、承認した人がラベルを付けるまで spec-pin が赤になる。`toString()` などしか呼ばないテスト・`symbol` の無い proofs・Feature ごと `@ignore` したシナリオは D7・D10 で落ちる |
| 2026-10 | verify-gates.ps1 は `$env:PYTHON` → `python` の順で Python を選ぶ（`py` ランチャーを使わない）。手順は `python -m pip` | `py` だけで入れていた環境は、`python -m pip install …` で入れ直すか `$env:PYTHON` を指定する |
| 2026-10 | template を写し元（dev-environment f8ad74d）に合わせた: `local/docker-compose.yml` のイメージ（DB・S3 エミュレータ）を `タグ@sha256:digest` で固定。spec-trace の devtools-common の固定を 2e25f8a に | `docker compose pull` しても同じタグの別の中身に変わらない。イメージの更新は写し元の Dependabot の後に取り込む |
| 2026-10 | template を写し元（dev-environment f497a2c）に合わせた: ポートを 127.0.0.1 だけで公開、Gradle の配布物の SHA-256 を検証、upload-sample が local/.env を読む | 同じネットワークの他の PC から DB・S3 エミュレータにつながらなくなる |
| 2026-10 | 禁止事項の複写の一致を docs ゲートと pre-push で検査する | 禁止事項を変えるときは 7 ファイルを同じ PR で直す |
| 2026-10 | verify-gates の既定が `--require implemented` になり、pytest・ruff・template drift も実行する。CI は verify-gates を呼ぶ | 手元で verify-gates を流すと、以前より時間がかかり、テスト・lint・ずれでも失敗する（CI と同じ結果になる） |
| 2026-10 | spec-trace に `--test-results` を追加（CI と verify-gates で使用） | proven のテストが失敗・未実行・スキップなら D7 が落ちる |
| 2026-10 | エージェントは `spec-trace pin`・`git push`・PR 作成を、人の承認後でも実行しない | 以前の「人の承認後にだけ行う」から変更（guidelines/workflow.md の「人だけが行うこと」） |

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
