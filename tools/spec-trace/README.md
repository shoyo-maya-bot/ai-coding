# spec-trace（ai-coding 同梱）

要件 → 実装 → テストの対応表（`../../traceability/specs/*.yaml`）を検証し、
**裏付けのない「実装済み」「テスト済み」と、設計書の更新漏れ（ドリフト）を検出する** ツールです。
品質ゲート D6〜D8・D10（[../../guidelines/quality-gates.md](../../guidelines/quality-gates.md)）の実体です。

```bash
python -m pip install -e tools/spec-trace       # リポジトリのルートで
spec-trace check traceability/specs --root . --require proven
spec-trace pin traceability/specs/order-import.yaml --root .   # 設計書の承認後に人が実行
spec-trace schema                                # 定義ファイルの JSON Schema
```

| rule_id | 内容 |
|---|---|
| `trace.implements_empty` / `trace.implements_missing` | 実装済みなのに実装箇所が無い・見つからない |
| `trace.proofs_empty` / `trace.proof_missing` | テスト済みなのにテストが無い・見つからない |
| `trace.proof_symbol_missing` | テスト（proofs）にテスト関数（`symbol`）もシナリオ（`scenario`）も書かれていない（スキーマでも必須） |
| `trace.proof_no_assert` | テストに検証（下の「アサーションとみなす呼び出し」・Then 等）が無い |
| `trace.proof_ignored` | シナリオ、またはそのシナリオを含む Feature 全体が `@ignore` / `@skip` / `@wip` / `@disabled` で無効化されている |
| `trace.spec_drift` | 設計書が承認時から変わっている |
| `trace.source_unpinned` / `trace.source_missing` | 設計書のハッシュが未記録 / 設計書が見つからない（`source_unpinned` は通常は警告、`--require proven`（verify-gates の `--final`・main）では error） |
| `trace.source_unspecified` | 対応表に根拠の設計書（`source:`）が無い（スキーマでも必須。スキーマを通さないときも `--enforce-drift` ならエラー） |
| `trace.duplicate_id` / `trace.not_done` | 要件 ID の重複 / `--require` の状態に達していない |
| `trace.proof_failed` / `trace.proof_not_run` / `trace.proof_skipped` | （`--test-results` のとき）テストが失敗した / 結果に無い（実行されていない）/ スキップされた |
| `trace.proof_result_unchecked` | （`--test-results` のとき・警告）シナリオ（.feature）の実行結果が無く照合していない（単体テストでも裏付けている要件） |
| `trace.proof_unverified` | （`--test-results` のとき）シナリオ（.feature）だけで裏付けている要件で、そのシナリオの実行結果が無い（未証明） |

## テストが「実行されて成功した」ことも確かめる（--test-results）

既定の検査は「テストが実在し、アサーションがある」までで、テストが通ったかは見ません。
`--test-results` に JUnit 形式の結果（Gradle の `build/test-results/test`、`pytest --junitxml` など。ファイルかディレクトリ、複数可）を渡すと、
proven の要件のテストごとに、結果の中に **実行されて成功した記録があること** も求めます。CI と verify-gates はこれを使います。

```bash
./template/gradlew -p template test
spec-trace check traceability/specs --root . --require proven --test-results template/build/test-results/test
```

- 照合は **パッケージ付きのクラス名** とメソッド名で行う。Java / Kotlin 等はテストのソースの `package` 宣言 + クラス名
  （`com.example.app.order.OrderImportServiceTest`。`package` が無ければ無名パッケージ）、Python はテストファイルのパス
  （`tests/test_x.py` → `tests.test_x`。pytest の rootdir の違いで先頭が増減しても照合できるよう、短い方が長い方の末尾に一致すればよい）。
  別のパッケージ・モジュールにある同名のテストクラスの結果は数えない。TypeScript などは従来どおりクラス名（単純名）で照合する
- パラメータ化テスト（`parseRejects(String, String)[1]` など）は、全実行分が成功していれば成功
- pytest の `parametrize`（結果の名前が `test_x[case1]` など）も同じく、全実行分が成功していれば成功。対応表の `symbol` に
  `test_x[case1]`（`Class#method[2]`）と 1 件だけ書くと、その id の実行分だけを照合する（id の中の `.` や `::` はそのまま書ける）
- クラスの外の関数（`test_x`）は、別のクラスの同名のメソッドの結果と混ぜない
- Gradle 9 の結果では、パラメータ化テスト（`@ParameterizedTest` など）の 1 回分の名前が `[1] line = "…", message = "…"` になり、
  メソッド名が出ない。そのため、テストのソースにこれらのアノテーションがあるメソッドは、同じクラスの `[番号] 引数名 = 値, …` のうち
  **引数名の並びがそのメソッドの引数と同じ** 結果だけを、そのメソッドの実行分とみなす（別のパラメータ化テストの成功・失敗を混ぜない）
  - `@TempDir` などの拡張が渡す引数は表示名に出ないので、引数名の比較に使わない
  - 引数名の並びが同じパラメータ化テストが同じクラスに 2 つ以上あると、結果から区別できないので照合しない（`trace.proof_not_run`）。
    引数名を変えるか、`@ParameterizedTest(name = "メソッド名 [{index}] {arguments}")` のように表示名の先頭にメソッド名を入れる
  - 表示名に引数名が無い結果（`[1] a, b`. `-parameters` を付けずにコンパイルした・表示名を独自に付けた）は、どのメソッドの分か
    分からないので数えない
- JUnit 5 の `@DisplayName("…")` が付いたテストは、Gradle の結果ではテストの名前がメソッド名ではなく表示名になる。
  そのため、メソッド名の結果が無いときは、同じクラスの **表示名と一致する** 結果をそのメソッドの実行分とみなす
  （test-scaffold の雛形も `@DisplayName` を付ける）。表示名が文字列リテラル（`+` での連結も可）でないもの（定数など）、
  同じクラスに同じ表示名のメソッドが 2 つ以上あるものは、結果から区別できないので照合しない（`trace.proof_not_run`）
- 結果のファイルが無い・XML として読めないときは、黙って通さず終了コード 2 にする
- Karate などのシナリオ（`.feature`）は、Karate の JUnit XML（テスト名がシナリオ名. 先頭の `[1:5]` などの番号は外して比べる）が
  `--test-results` にあれば、失敗・スキップを照合する。結果が無いとき:
  - そのシナリオだけで裏付けている要件は **未証明**（`trace.proof_unverified`. エラー）。シナリオは「書いてある」だけでは proven にしない
  - 単体テストでも裏付けている要件は、単体テストの結果で判断し、シナリオは `trace.proof_result_unchecked` の警告にとどめる

Python は構文木、Java / Kotlin / TypeScript 等は宣言行と括弧の対応による近似、Gherkin（英語・日本語）に対応します。
Java のテキストブロック・Kotlin の raw 文字列（`"""…"""`）の中身は文字列として外して数えます。

### アサーションとみなす呼び出し（Python 以外）

`toString()`・`toList()`・`toUpperCase()` のような普通の呼び出しを数えないよう、テストライブラリの名前を明示しています（`code.py` の `_ASSERT_NAMES`）。

| ライブラリ | 数える呼び出し |
|---|---|
| JUnit・TestNG・Hamcrest・AssertJ・kotlin.test | `assertXxx(…)`（`assertEquals`・`assertThat`・`assertThatThrownBy`・`assertThrows` など）、`assert(…)`、`fail(…)`。ただし AssertJ の `assertThat(x)` は、後ろに `isEqualTo(…)` などの検証の呼び出しがあるときだけ数える（`as(…)`・`describedAs(…)`・`extracting(…)` などだけでは数えない。Hamcrest の `assertThat(x, matcher)` は引数 2 つで検証） |
| xUnit・NUnit・MSTest・testify | `Assert.Xxx(…)`・`assert.Xxx(…)`・`require.Xxx(…)` |
| Mockito・BDDMockito | `verify(…)`・`verifyNoInteractions(…)`・`verifyNoMoreInteractions(…)`、`.should(…)`・`.shouldHaveNoInteractions(…)` |
| Spring MockMvc・WebTestClient | `.andExpect(…)`・`.andExpectAll(…)`、`.expectStatus()`・`.expectBody(…)`・`.expectHeader()` |
| Jest・Vitest・Chai | `expect(…)`（後ろの `.toBe(…)` などは数えない。1 つの `expect` で 1 件） |
| Kotest | `shouldXxx(…)`（`shouldBe`・`shouldThrow<…>` など） |
| Go の testing | `t.Error(…)`・`t.Errorf(…)`・`t.Fatal(…)`・`t.Fatalf(…)`・`t.Fail()` |
保証するのは「存在」と「最低限の検証」までで、テストの意味的な妥当性は人がレビューします。
