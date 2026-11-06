# AI Coding Harness v2: Architecture & Refactoring Specification

> **For GitHub Copilot Agent / Developers:**
> このドキュメントは、既存の仕様駆動×受入テスト駆動AIコーディング基盤（`batch-ai-coding` / API生成ハーネス）のボトルネック（実行時間6時間化、修正ループの発散、テスト件数の変動、ブラックボックス観点の欠落）を解消するためのアーキテクチャ改修仕様書です。
> ハーネスの改修時は、本仕様書の定義に従って `WORKFLOW.md`、`quality-gates.md`、`.github/agents/*.md`、`build.gradle`、および検証スクリプト群を更新してください。

---

## 1. 改修の目的とKGI（目標指標）

1. **リードタイム短縮:** 1バッチあたりの生成・検証時間を「約6時間」から「**30分以内**」へ短縮する。
2. **修正ループの確実な収束:** 無限ループ・モグラ叩きを防止し、各フェーズの自動修正上限を「10回」から「**最大3回（停滞時は2回で即時中断）**」へ制限する。
3. **テスト再現性の100%保証:** 実行（`runId`）ごとにテスト件数が変わる問題を根絶し、設計書の決定表（Decision Table）および境界値リストからテスト件数を一意に固定する。
4. **内的品質と外的品質の両立（脱AIレビュー・報酬ハッキング防止）:**
   - **外的品質（仕様充足）:** 実装前にブラックボックステストを生成・ハッシュロックし、`coder` によるテスト改ざん（Test Tampering）を物理的に禁止する。
   - **内的品質（構造・規約）:** Phase 4でAI（`reviewer`）が判定していた `R1〜R6` および `STYLE1〜6` を、**ArchUnit**・**Checkstyle**・**AST/YAML突合スクリプト**（D系機械ゲート）へ移行し、CI上で数秒で決定論的に判定する。

---

## 2. ワークフローの再設計（`WORKFLOW.md` 改修仕様）

### 2.1 フェーズ順序の逆転（真のATDD化とブラックボックス隔離）
従来の「Phase 2（実装）→ Phase 3（テスト）」の順序を逆転させ、**「テスト先行・実装後追い・ホワイトボックス補強分離」**のパイプラインへ変更する。

```text
[設計書/DDL] ──(自動取得・SSOTロック)──> input/
  │
  ├─ Phase 1: 計画 & テスト仕様構造化 (planner) [上限3回]
  │    ├─ 要件対応表 (traceability/specs/*.yaml) の生成
  │    ├─ 決定表・同値分割・境界値マトリクス (traceability/test-matrix.yaml) の生成
  │    ├─ 人間確認用の決定表サマリー (traceability/decision-table.md) の出力
  │    └─ ゲート: D10 (verifySpecDrift), Testability Index チェック
  │
  ├─ Phase 2A: ブラックボックステスト先行生成 (blackbox-tester) [上限3回]
  │    ├─ 入力: 設計書、DDL、test-matrix.yaml、スタブ定義のみ（実装コードは非公開）
  │    ├─ 出力: 受入テスト (*AcceptanceTest.java / Karate) & 仕様単体テスト (*SpecTest.java)
  │    ├─ ゲート: D1(TestCompile), D7(Traceability), D8(Assertion), D13(Matrix件数完全一致)
  │    └─ ★完了時にブラックボックステストのハッシュを記録し Read-Only ロック (D14)
  │
  ├─ Phase 2B: 本番コード実装 (coder) [上限3回 / Stagnation Guard: 2回]
  │    ├─ 入力: 設計書、DDL、ロックされたブラックボックステスト
  │    ├─ 出力: Entity -> Mapper -> Job/Step/Tasklet 実装
  │    └─ ゲート:
  │         [Inner Loop (毎修正時・高速)] D1(Compile), D2(Checkstyle), D5(Spotless), D15(ArchUnit: 旧STYLE1-5), D16(SpecCompliance: 旧R1-R6), 単体テスト実行
  │         [Outer Loop (フェーズ出口のみ)] D3(H2受入テスト全体), D11(SpotBugs/FindSecBugs/SQL検査), D14(Test改ざん0件検証)
  │
  ├─ Phase 3: ホワイトボックステスト補強 & 変異検証 (whitebox-tester) [上限3回]
  │    ├─ 入力: 実装コード、JaCoCo未到達分岐レポート
  │    ├─ 出力: 異常系・モック必須経路の単体テスト追加 (*WhiteBoxTest.java) ※既存テスト変更不可
  │    └─ ゲート: D3(全テスト), D4(JaCoCo C1 100%), D9(PIT ミューテーションスコア >= 80% 必須化), D12(Karate), D14(Test改ざん0件)
  │
  ├─ Phase 4: 最終意味突合 (reviewer) [上限1回]
  │    ├─ 機械ゲート(D1〜D16)を通過したコードに対し、静的解析で検出不能な業務意味論の矛盾のみを1回検査
  │    └─ NG時は自動ループでこね回さず、差分レポートを出して RP4 へエスカレーション
  │
  ├─ 👤 RP4: 最終確認 (Human-in-the-Loop)
  │    └─ 人は Java テストコードではなく `decision-table.md` の期待値と設計書項番のみを突合（5分以内）
  │
  ├─ Phase 5: CI + PR作成
  │    └─ D1〜D16 (Coverity D6 含む) の再現実行
  │
  └─ 👤 RP5: PRレビュー & マージ
```

### 2.2 `WORKFLOW.md` から削除・修正すべき矛盾記述
- 旧方式の承認ポイント（`RP1〜RP3`）に関する残存記述をすべて削除し、承認ポイントは `RP4` と `RP5` のみであることを明記する。
- 自動修正の上限回数に関する記述を `quality-gates.md` の定義（**最大3回**）に完全統一し、「最大10回」の記述をすべて撤廃する。

---

## 3. 品質ゲートの再定義と機械化仕様（`quality-gates.md` 改修仕様）

### 3.1 新規・変更される機械的品質ゲート（D1〜D16）

| ID | 内容 | ツール / コマンド | 合格条件 | 実行タイミング | 改修ポイント |
| :--- | :--- | :--- | :--- | :--- | :--- |
| D1 | コンパイル | `compileJava` / `compileTestJava` | エラー 0 | Phase 2A, 2B, 3 | `clean` を外しビルドキャッシュを有効化 |
| D2 | コーディング規約 | Checkstyle | 違反 0 | Phase 2B (Inner) | `MagicNumber` 等（旧STYLE5）を統合 |
| D3 | テスト実行 | `testFast` (Inner) / `test` (Outer) | 失敗 0 | Phase 2B, 3 | InnerはMockito単体のみ、OuterでH2受入を実行 |
| D4 | C1（分岐）カバレッジ | JaCoCo | 100%（除外対象除く） | Phase 3 | Phase 2BではなくPhase 3の出口で判定 |
| D5 | フォーマット | Spotless | 差分 0 | Phase 2A, 2B, 3 | 変更なし |
| D6 | 静的解析 | Coverity | High以上 0 | Phase 5 (CI) | 変更なし |
| D7 | 要件対応表の検証 | `verifyTraceability` | 根拠ファイル・テスト実在 | Phase 2A〜3, CI | 変更なし |
| D8 | アサーションの有無 | `verifyTraceability` | 有効な assert/verify 1つ以上 | Phase 2A, 3, CI | `assertTrue(true)` 等の無意味アサーションを正規表現で禁止 |
| **D9** | **ミューテーションテスト** | **PIT (`pitest`)** | **スコア 80%以上** | **Phase 3 (必須)** | **「任意」から「必須ゲート」へ昇格（報酬ハッキング防止）** |
| D10 | 設計書の変更検知 | `verifySpecDrift` | 記録ハッシュと一致 | Phase 1, CI | 入力取得スクリプトでロックファイルを自動生成 |
| D11 | セキュリティ静的解析 | SpotBugs + FindSecBugs + `verifyMapperSql` | HIGH 0件、`${}` 0件 | Phase 2B (Outer), CI | Innerループから外しフェーズ出口で1回実行 |
| D12 | E2E受入テスト | `verifyKarateProofs` | シナリオ実在、assertあり、`@Ignore` なし | Phase 3 (Outer), CI | フェーズ出口で実行 |
| **D13** | **テスト件数・決定表一致** | **`verifyTestMatrixCount` (新規)** | **`test-matrix.yaml` のケース数と `@SpecCase` 数が完全一致** | **Phase 2A, 3, CI** | **テスト件数の変動（再現性欠如）と旧STYLE6を機械保証** |
| **D14** | **テスト改ざん検知** | **`verifyTestIntegrity` (新規)** | **Phase 2A完了時のテストハッシュと完全一致** | **Phase 2B, 3, CI** | **`coder` による受入テスト書き換え・削除・`@Disabled` をブロック** |
| **D15** | **アーキテクチャ・STYLE規約** | **ArchUnit (`checkArchitecture`) (新規)** | **旧 STYLE1〜5 の違反 0件** | **Phase 2B (Inner), CI** | **AIレビュー（STYLE系）をJUnit/ArchUnitへ完全置換** |
| **D16** | **設計書構造突合** | **`verifySpecCompliance` (新規)** | **旧 R1〜R6 の構造不一致 0件** | **Phase 2B (Inner), CI** | **AIレビュー（R系）をYAML×AST/XML照合スクリプトへ置換** |

### 3.2 旧 `STYLE1〜6` の ArchUnit / Checkstyle 実装仕様（D15への移行）
`src/test/java/.../architecture/BatchArchitectureTest.java` を作成し、以下のルールを実装する（一度ロードした `JavaClasses` をキャッシュし1秒以内で実行すること）。

1. **STYLE1（命名規則）:**
   - `..job..` パッケージのクラスは `*JobConfig`、`*Tasklet`、`*Processor`、`*Reader`、`*Writer` のいずれかで終わること。
   - `..mapper..` パッケージのインターフェースは `*Mapper` で終わること。
   - `..entity..` パッケージのクラスは `*Entity` で終わること。
2. **STYLE2（共通部品の使い方）:**
   - `java.time.LocalDateTime.now()`、`LocalDate.now()`、`System.currentTimeMillis()` の直接呼び出しを禁止し、`TimeProvider` 経由の呼び出しのみを許可する（`noClasses().should().callMethod(...)`）。
   - `System.out`、`System.err`、`org.slf4j.LoggerFactory` の直接呼び出しを禁止し、`MessageLogger` の使用を強制する。
   - ジョブコンテキスト情報の取得は `JobContext` 経由に限定する。
3. **STYLE3（トランザクション制御の書き方）:**
   - 設計書YAMLの `txMode: CHUNK_OR_ALL`（一括）の場合、対象メソッド/Taskletに宣言的トランザクション規定が適用され、手動コミット（`PlatformTransactionManager.commit` 等の直接呼び出し）が存在しないことを検証。
   - `txMode: SEQUENTIAL`（逐次）の場合、指定のトランザクション制御テンプレート部品が呼び出されていることを検証。
4. **STYLE4（ログ出力）:**
   - 各Job/Taskletのエントリーメソッドが `MessageLogger` の開始・終了・件数出力メソッドへの呼び出し参照（`getMethodCallsFromSelf()`）を持つことを検証。
5. **STYLE5（定数化）:**
   - Checkstyleの `MagicNumber` および `MultipleStringLiterals` チェックを有効化し、数値・文字列リテラルの直書きをコンパイル直後に検知する。
6. **STYLE6（テストの網羅）:**
   - カスタムアノテーション `@SpecCase(id = "RULE-01")` を定義し、Phase 1の `test-matrix.yaml` に記載された全ルールIDおよび境界値IDが、テストクラス群の `@SpecCase` に漏れなく1対1で付与されているかを `verifyTestMatrixCount` (D13) で検証する。

### 3.3 旧 `R1〜R6` の構造化YAML×AST/XML突合スクリプト実装仕様（D16への移行）
Phase 1で設計書から以下のスキーマを持つ `traceability/specs/{jobId}.yaml` を生成させ、Gradleタスク `verifySpecCompliance` でソースコード・XMLと機械突合する。

```yaml
jobId: "B001"
steps: # R1: STEP構成と処理順
  - stepOrder: 1
    stepId: "STEP01"
    className: "B001Step01Tasklet"
messageIds: # R2: 使用メッセージID一覧
  - "MSG_B001_I001"
  - "MSG_B001_E001"
crudMatrix: # R3: 入出力CRUD表
  - tableName: "T_MARKETING_USER"
    operations: ["SELECT", "UPDATE"]
parameters: # R4: 起動パラメーターと検証ルール
  - name: "targetDate"
    required: true
    format: "yyyyMMdd"
transactionMode: "ALL" # R5: ALL (一括) or SEQUENTIAL (逐次)
exitCodes: # R6: 終了コード条件
  normal: 0
  abnormal: 1
```

- **R1検証:** Job定義クラスのStep構築順序と `steps` 配列の順序が一致しているか検査。
- **R2検証:** `messageIds` の全IDがJavaコードまたは定数クラス内で参照されているか、および未定義のメッセージIDが使われていないか検査。
- **R3検証:** MyBatisの `Mapper.xml` 内の `<select>`, `<insert>`, `<update>`, `<delete>` タグのSQL対象テーブルをパースし、`crudMatrix` の定義と完全一致するか検査。
- **R4検証:** `parameters` の全パラメーター名に対する取得・バリデーション呼び出しが存在するか検査。
- **R5/R6検証:** `transactionMode` と終了コード返却値（正常時 `0`、異常時 `1`）の定数マッピングおよび受入テストケースの存在を検査。

---

## 4. 収束制御・ビルド高速化・運用課題の改修仕様

### 4.1 自動修正ループの収束制御（Stagnation Guard & Lineage Memory）
オーケストレーターおよび各エージェントのループ制御を以下のように変更する。
1. **3-Attempt Limit:** 各フェーズの最大リトライ回数を **3回** に制限する。
2. **Stagnation Guard（停滞ガード）:**
   - 各イテレーション終了時、「失敗したゲートIDの集合」と「コンパイルエラー箇所／失敗テストメソッド名の集合」を記録する。
   - **直前の試行と同一のエラー集合が2回連続で発生した場合**、または**失敗テスト数が前回より増加した場合**は、3回目を待たずにループを即時中断（または直前の最良コミットへ `git checkout` ロールバック）する。
3. **Attempt History（失敗履歴メモリ）の注入:**
   - リトライ時は、エージェントに「前回どのパッチ（`git diff`）を当てて、どのゲートがなぜ失敗したか」の履歴リストを渡し、「前回失敗したアプローチと同一の修正を行うな」という制約プロンプトを付与する。
   - ファイル全体の再生成を禁止し、失敗箇所に対する局所差分編集のみを行わせる。

### 4.2 Gradle ビルドの2段階分離（Inner Loop 高速化）
`build.gradle` を改修し、エージェントが修正ループ内で毎ターン実行するコマンドを軽量化する。
- **禁止事項:** ループ内での `./gradlew clean` の実行を厳禁とする。`gradle.properties` で `org.gradle.caching=true`、`org.gradle.parallel=true`、`org.gradle.daemon=true` を有効化する。
- **`./gradlew fastVerify` タスクの新設（Inner Loop用・目標10〜15秒）:**
  - `spotlessApply` -> `compileJava` -> `compileTestJava` -> `checkstyleMain` -> `testUnitFast`（Springコンテキストを起動しない Mockito 単体テストと ArchUnit のみ実行）-> `verifySpecCompliance` (D16) を直列実行する。
- **`./gradlew fullVerify` タスクの新設（Phase出口用・Outer Loop）:**
  - `fastVerify` 通過後に1回だけ実行。`@SpringBootTest` + H2 受入テスト、`@MybatisTest`、JaCoCo (D4)、SpotBugs (D11)、PIT (D9)、Karate (D12) を実行する。

### 4.3 品質レポートの100%強制出力（`gen01` / `gen05` 未生成問題の解消）
- `collectMetrics` および品質レポート生成処理をAIエージェントのタスクから切り離す。
- `build.gradle` において `check.finalizedBy(collectMetrics)` を設定し、さらに実行スクリプト（`scripts/prepare-output.ps1` 等）の `try ... finally` ブロック内で `collectMetrics` を呼び出すことで、途中失敗やタイムアウト終了時でも必ず実行ログと品質レポートが出力される構造にする。

### 4.4 周辺運用課題（入力SSOT化・脱vendor・マルチリポジトリ展開）の解消仕様
1. **入力のSSOT化（手作業コピーと `決定事項.md` の廃止）:**
   - `決定事項.md` による差分パッチ運用を廃止し、設計書の変更は上流の設計書MD自体へ統合してから実行する。
   - `context-sources.yaml` を読み取り、設計書リポジトリおよびDDLリポジトリから対象ファイルを自動取得して `input/` に配置し、SHA-256ハッシュを `input-lock.json` に記録する取得スクリプトを実装する。
2. **共通部品の `vendor` 同梱廃止:**
   - `MessageLogger`、`JobContext`、`TimeProvider` 等の共通部品ソースコードをリポジトリ内にコピー（vendor同梱）する方式を廃止し、バージョン付きの共通ライブラリ依存（JAR / マルチプロジェクトの `implementation project(':common')` 等）へ切り替える。これによりAIによる共通部品の不正改変とビルド時間の増大を同時に防ぐ。
3. **パッケージ構造の業務ドメイン・ジョブ単位隔離（マージ衝突の防止）:**
   - 各サービスリポジトリへ展開する際、`entity/`、`mapper/`、`job/` のような技術レイヤー直下に全ジョブのクラスを混在させない。
   - `com.example.{service}.batch.{jobId}.{domain|infra|job}` のように**トップをジョブID（または業務ドメイン）で区画**し、ArchUnitで他ジョブパッケージへの直接依存を禁止する。DDLやテストデータもジョブIDごとのディレクトリに分割し、並行開発・マージ時のコンフリクトをゼロにする。

---

## 5. GitHub Copilot Agent 用 段階的実装タスクリスト

このドキュメントを参照した Copilot Agent は、以下の順序で改修を実施してください。

- [ ] **Step 1: ドキュメントとループ上限の即時修正 (Quick Win)**
  - `WORKFLOW.md` と `quality-gates.md` のリトライ上限をすべて「最大3回」に統一し、旧 `RP1〜RP3` の記述を削除する。
  - `scripts/prepare-output.ps1`（および関連スクリプト）に `try / finally` を追加し、失敗時でも `collectMetrics` が必ず実行されるように修正する。
- [ ] **Step 2: Gradle 高速化タスク (`fastVerify`) と ArchUnit (D15) の導入**
  - `build.gradle` に ArchUnit (`com.tngtech.archunit:archunit-junit5`) と PIT (`info.solidsoft.pitest`) を設定し、ループ内から `clean` を除去した `fastVerify` タスクを作成する。
  - `BatchArchitectureTest.java` を作成し、`STYLE1〜5` を機械判定するルールを実装する。
- [ ] **Step 3: 設計書突合スクリプト (`verifySpecCompliance` / D16) とテスト改ざん防止 (D13/D14) の実装**
  - `R1〜R6` を検査する `verifySpecCompliance` タスクと、テスト件数一致・ハッシュロックを検査する `verifyTestMatrixCount` / `verifyTestIntegrity` タスクを実装する。
- [ ] **Step 4: エージェント定義 (`.github/agents/*.md`) の順序逆転とプロンプト改修**
  - `planner.agent.md`: 決定表・境界値マトリクス (`test-matrix.yaml` と `decision-table.md`) の出力を必須化。
  - `tester.agent.md` を `blackbox-tester.agent.md`（Phase 2A：実装前の受入テスト生成・ロック）と `whitebox-tester.agent.md`（Phase 3：未到達分岐のモック単体テスト追加）に分割。
  - `coder.agent.md`: ロックされたテストの編集禁止、`fastVerify` による高速検証、Stagnation Guard（同一エラー2回で停止）のルールを反映。
  - `reviewer.agent.md`: `R1〜R6` および `STYLE1〜6` のチェック責務を機械ゲート(D15/D16)へ委譲し、上限1回の意味論チェックのみに軽量化。
