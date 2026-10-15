# test-scaffold（ai-coding 同梱）

Excel（.xlsx）の **テスト仕様書から、JUnit 5 のテストクラスの雛形を作る** CLI です。フェーズ 3（テスト生成）の下準備に使います。
LLM は呼ばない決定論のツールで、同じ仕様書と設定からは同じソースができます。

- テスト対象クラスごとに 1 クラス（`MemberService` → `MemberServiceTest`）。パッケージは実装クラスの場所から決める
- テストメソッドごとに `@DisplayName`（項番 + 観点）と、要件 ID・観点・前提・入力・期待結果のコメントを書く
- 本体は `fail("未実装: <項番>")`。**雛形のままではテストが通らない**（下の「品質ゲートとの関係」）
- 既存のファイルは上書きしない。足りないメソッドだけ足す `--merge`、上書きする `--force` は明示したときだけ

```bash
python -m pip install -e "tools/test-scaffold[dev]" -c constraints.txt     # リポジトリのルートで
test-scaffold docs/会員テスト仕様書.xlsx --dry-run                           # 作る予定だけ表示（何も書かない）
test-scaffold docs/会員テスト仕様書.xlsx --trace traceability/specs --proofs-out build/test-scaffold/proofs.yaml
test-scaffold docs/会員テスト仕様書.xlsx --merge                             # 既存のテストクラスに、無いメソッドだけ足す
test-scaffold --print-config > scaffold.yaml                                 # 設定の既定値を書き出して直す
```

`python -m test_scaffold …` でも動きます（Windows で `test-scaffold` が PATH に無いとき）。

## 出力の例

テスト仕様書の行（架空）:

| 項番 | テスト対象クラス | テスト対象メソッド | 要件 ID | 種別 | 観点 | 前提条件 | 入力 | 期待結果 |
|---|---|---|---|---|---|---|---|---|
| 2 | MemberService | register | REQ-API0002-002 | 異常系 | メールの重複は大文字小文字を区別せずエラー | a@example.com が登録済み | メール「A@EXAMPLE.com」 | BusinessException（APPE0003） |

できるソース（`template/src/test/java/com/example/app/member/MemberServiceTest.java`）:

```java
    // 項番: 2（シート: 会員）
    // 要件 ID: REQ-API0002-002
    // 観点: メールの重複は大文字小文字を区別せずエラー
    // 前提: a@example.com が登録済み
    // 入力: メール「A@EXAMPLE.com」
    // 期待結果: BusinessException（APPE0003）
    @Test
    @DisplayName("2 メールの重複は大文字小文字を区別せずエラー")
    void register_case2() {
        fail("未実装: 2");
    }
```

`--proofs-out` を付けると、対応表（`traceability/specs/*.yaml`）の `proofs` にそのまま写せる形の候補を YAML で書きます。

```yaml
REQ-API0002-002:
- file: template/src/test/java/com/example/app/member/MemberServiceTest.java
  symbol: MemberServiceTest#register_case2
  type: abnormal
```

## オプション

| オプション | 内容 |
|---|---|
| `SPEC`（位置引数） | テスト仕様書（`.xlsx` / `.xlsm`。`.xls` は Excel で `.xlsx` に保存し直す） |
| `-c`, `--config` | 設定（YAML）。省略時は既定値（`--print-config` で表示） |
| `--root` | リポジトリのルート（既定: `.`）。出力はこの中だけ |
| `--out` | テストのソースの置き場（`--root` からの相対。既定: `template/src/test/java`） |
| `--dry-run` | 作る・足す予定のクラスとメソッドを表示するだけで、ファイルを書かない |
| `--merge` | 差分モード。既存のテストクラスに、まだ無いメソッドだけ足す（下記） |
| `--force` | 既存のテストクラスを上書きする（人が書いたテストも消える。`--merge` と同時には使えない） |
| `--strict` | 警告があれば終了コード 1（CI や事前確認向け） |
| `--trace PATH` | 対応表（ファイルかディレクトリ。複数可）。対応表に無い要件 ID を警告する |
| `--proofs-out PATH` | proofs の候補（要件 ID → `file` / `symbol` / `type`）を YAML で書く（`--root` の中だけ） |
| `--print-config` | 設定の既定値を表示して終わる |

## 終了コード

| コード | 意味 | 例 |
|---|---|---|
| 0 | 成功（`--strict` でなければ、警告があっても 0） | 雛形を作った・`--merge` で足すものが無かった |
| 1 | 警告あり（`--strict` のときだけ） | 要件 ID の無い行・形式の違う要件 ID・対応表に無い要件 ID・既存ファイルのため作らなかった・クラス名にできない行を飛ばした |
| 2 | 入力・設定・引数の誤り（何も書かない） | Excel が無い・読めない、`.xls`、見出し行が見つからない、設定の知らないキー・型の誤り、`--out`・`--proofs-out` がリポジトリの外、`--merge` と `--force` の同時指定 |
| 3 | 想定外のエラー | ツールの不具合。メッセージを添えて報告する |

警告は標準出力の最後に `警告 N 件:` として、`シート!セル` の位置付きで出します。`--strict` でもファイルは書きます（書かずに確かめるなら `--dry-run --strict`）。

## 設定（YAML）

書いた項目だけが既定値を置き換えます（`--print-config` の出力を直すのが早い）。知らないキー・型の誤りは終了コード 2 です。

```yaml
sheets: []                # 対象のシート名。空なら全シート（見出し行の無い表紙・改訂履歴などは飛ばす）
header_row: auto          # 見出し行（1 始まり）。auto なら先頭 header_search_rows 行から探す
header_search_rows: 20
columns:                  # 論理名 → 見出しの候補（NFKC・空白・大文字小文字を無視して比べる）
  id: [項番, 'No', No., テストNo, ケースNo]          # 必須
  target_class: [テスト対象クラス, 対象クラス, クラス]   # 必須。単純名か完全修飾名。「クラス#メソッド」も可
  target_method: [テスト対象メソッド, 対象メソッド, メソッド]
  requirement_id: [要件ID, 要件番号]                # 1 セルに複数書くときは , 、 改行 などで区切る
  viewpoint: [観点, テスト観点, 確認観点]             # 必須
  case_type: [種別, 区分, テスト種別]
  precondition: [前提, 前提条件]
  input: [入力, 入力値, 入力データ, 手順]
  expected: [期待結果, 期待値, 予想結果]
  # 列記号で指定するとき: target_class: {column: C}
requirement_id_pattern: '^REQ-[A-Z0-9]+-\d{3}$'    # 対応表の要件 ID（REQ-<機能 ID>-<連番 3 桁>）
case_types: {正常系: normal, 異常系: abnormal, 境界値: boundary}   # 種別 → proofs の type
java:
  package: com.example.app             # 実装クラスが見つからないときのパッケージ
  main_source: template/src/main/java  # 単純名のクラスはここから <クラス名>.java を探してパッケージを決める
  test_class_suffix: Test
```

- YAML では `No`・`Yes`・`On`・`Off` が真偽値になるので、見出しに使うときは `'No'` のように引用符で囲む
- 種別の列が無いときは、観点の先頭（`異常系: …`）で `type` を決める。決まらなければ `type` を書かない

## Excel の読み方

| 状況 | 扱い |
|---|---|
| 結合セル | 結合範囲のすべてのセルに左上の値があるものとして読む（縦に結合した「テスト対象クラス」など） |
| 空行 | 対応づけた列に、そのセル自身の値が 1 つも無い行は飛ばす（縦の結合が空行まで伸びていても行は増えない） |
| 複数シート | 順に読み、同じテスト対象クラスの行は 1 つのクラスにまとめる。見出し行の無いシートは飛ばす（`sheets` で明示したシートに見出しが無ければ終了コード 2） |
| 項番・テスト対象クラスが空 | 警告してその行を飛ばす |
| 数値・日付 | `1.0` は `1`、日付は `2026-10-01` の形で読む。数式は Excel が保存した計算結果を読む |

## 名前の決め方（Java の識別子として安全に）

| もの | 規則 | 例 |
|---|---|---|
| テストクラス | `<対象クラスの単純名><test_class_suffix>`。対象クラス名が英大文字で始まる英数字でなければ、その行を飛ばして警告 | `MemberServiceTest` |
| パッケージ | 完全修飾名ならそのパッケージ。単純名なら `java.main_source` の `<クラス名>.java` の場所、見つからなければ `java.package`（警告） | `com.example.app.member` |
| メソッド | `<対象メソッド>_case<項番の英数字>`。対象メソッドが英数字の識別子でなければ `case<項番>`。項番に英数字が無ければ `caseR<行番号>`。重複は `_2` を付ける | `register_case2`、`importLines_case1_1`、`caseNo_10_a` |
| 表示名 | `@DisplayName("<項番> <観点>")`。日本語の観点は表示名とコメントにだけ書く | `@DisplayName("2 メールの重複は…")` |

できるソースは Checkstyle（D2）の規則に合わせます: メソッド名の形（`^[a-z][a-zA-Z0-9]*(_[a-zA-Z0-9]+)*$`）、1 行 120 文字以内（長いコメント・表示名は折り返す）、
タブなし、改行は LF。セルの値は、コメントや文字列から抜け出せないようにエスケープします（`"`・`\`、Java がコメント中でも解釈する `\u000a` など）。

## 既存のファイルの扱い

| 指定 | テストクラスのファイルが無い | ある |
|---|---|---|
| なし（既定） | 作る | **作らない**（警告。`--strict` なら終了コード 1） |
| `--merge` | 作る | クラスの最後に、まだ無いメソッドだけ足す。足りない import も足す |
| `--force` | 作る | 上書きする |

`--merge` では、次のどちらかがあれば「既にある」とみなして足しません。

- 同じ名前のメソッド（`void register_case2(`）
- 雛形の目印のコメント `// 項番: 2（シート: 会員）`（メソッド名を変えても、目印を残せば足さない）

既存のクラスが別のライブラリの `fail`（AssertJ の `Assertions.fail` など）を static import しているときは、JUnit の `fail` を重ねて import しません。

## 出力先の検証

- `--out` と `--proofs-out` は `--root` の中だけ（`..`・絶対パス・シンボリックリンクで外に出るものは終了コード 2）
- 作るファイルは `--out` の中だけ（シンボリックリンクをたどった先も確かめる）
- ソースやレポートに、手元の絶対パスは書かない（仕様書はファイル名だけ書く）

## 品質ゲートとの関係

| ゲート | 雛形のまま | 本体を書いた後 |
|---|---|---|
| D2 Checkstyle（`checkstyleTest`） | 通る（上の名前と書式の規則） | 書いた内容による |
| D3 単体テスト | **失敗する**（`fail("未実装: …")`）。`@Disabled` で逃がさない（guidelines の禁止事項） | 設計書の期待値で通す |
| D7 テストの実在と検証 | spec-trace は `fail(` をアサーションに数えるので、静的な検査（`trace.proof_no_assert`）は通ってしまう。ただし CI と verify-gates は `--test-results` で実行結果を照合するので、proven にしても `trace.proof_failed` で落ちる | proofs に `クラス#メソッド` を書いて proven に。Gradle の結果ではテストの名前が `@DisplayName` の表示名になるが、spec-trace は表示名でも照合する（表示名を定数にしない・同じクラスで重複させない） |

雛形はテストを書く場所と観点の一覧を用意するだけです。期待値は設計書から決め（実装の動きに合わせない）、
`fail` を消したら必ず検証（`assertThat(…).isEqualTo(…)` など）を書きます。そのまま push すると D3 で CI が落ちます。

## テスト

```bash
python -m pytest -q tools/test-scaffold/tests
```

テスト用の仕様書（架空の会員・注文）はテストの中で openpyxl で作ります。生成したメソッドを spec-trace が `クラス#メソッド` で見つけられることも確かめます。
