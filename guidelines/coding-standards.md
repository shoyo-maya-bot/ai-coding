# コーディング規約

機械で確かめられるものは Checkstyle（`template/config/checkstyle/checkstyle.xml`）と SpotBugs で検査します（D2・D5）。
ここでは、機械では確かめにくいものも含めて書きます。

## 命名

| 対象 | 規則 | 例 |
|---|---|---|
| パッケージ | `com.example.app.<業務>`（小文字のみ） | `com.example.app.order` |
| クラス | UpperCamelCase。役割を接尾辞に | `OrderImportService`、`MemberController`、`OrderMapper` |
| メソッド・変数 | lowerCamelCase。動詞から始める | `importLines`、`findById` |
| 定数 | UPPER_SNAKE_CASE（ロガーだけ `log`） | `HEADER`、`MEMBER_NOT_FOUND` |
| テストメソッド | `対象_条件_期待` または期待を文で | `register_rejectsDuplicateEmailIgnoringCase` |
| ID | API `API` + 4 桁、ジョブ `JOB` + 4 桁、メッセージ `APP` + I/W/E + 4 桁 | `API0001`、`JOB0001`、`APPE0002` |

## 層の責務

| 層 | 責務 | してはいけないこと |
|---|---|---|
| Controller | 入力の受け取り・形式チェック（Bean Validation）・応答の組み立て | 業務ロジック、SQL |
| Service | 業務ロジックとトランザクション（`@Transactional`） | HTTP の概念（ステータスコード等）を扱う |
| Mapper（+ XML） | SQL | 業務判断 |
| Job（バッチ） | 起動引数の解釈、Service の呼び出し、終了コード | 業務ロジックを直接書く |

## 例外とメッセージ

- 業務エラーは `BusinessException`（メッセージ ID と埋め込み値）で投げる。該当なしは `NotFoundException`
- メッセージ本文は `messages.properties` に置き、コードには ID だけを書く
- 例外を握りつぶさない（空の catch 禁止）。捕まえたら必ずログか再送出

## ログ

- `System.out` / `printStackTrace` は使わない（Checkstyle で検出）。SLF4J のロガー `log` を使う
- ログの先頭にメッセージ ID を書く（例: `log.info("{} JOB0001 開始", MessageIds.IMPORT_STARTED)`）
- 個人情報・パスワード・トークンをログに出さない

## SQL（MyBatis）

- SQL は Mapper XML に書く。値は `#{}` で渡し、`${}` は使わない（D9 で検出。SQL インジェクション対策）
- 再実行される処理（バッチの登録）は冪等にする（例: `ON CONFLICT DO NOTHING`）

## テスト

- 単体テストは DB・外部サービスを使わない（Mapper はインメモリ実装やラムダで差し替える）
- 1 テスト 1 観点。アサーションを必ず書く（D7: 0 件のテストは裏付けにならない）
- 正常系・異常系・境界値をそろえる。境界値は `@ParameterizedTest` でまとめる
- API は MockMvc（standalone）で Controller と例外ハンドラの組み合わせを確かめ、結合は Karate で確かめる
- テストの期待値は **設計書** から決める（実装の動きに合わせない）

## その他

- Java 17 の範囲で書く（`record`、`switch` 式、テキストブロックは可）
- 1 メソッド 80 行以内、循環的複雑度 12 以内（Checkstyle）。超えるなら分割する
- 公開クラス・メソッドには、何をするかを日本語の Javadoc で 1 行以上書く
