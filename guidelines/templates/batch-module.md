# バッチ 1 本の作り方

例: [JOB0001 注文ファイル取込](../../samples/design-docs/batch/JOB0001_order-import.md) → `template/src/main/java/com/example/app/order/`

## 必要なファイル

| ファイル | 内容 |
|---|---|
| `<業務>/batch/<名前>Job.java` | `ApplicationRunner` + `ExitCodeGenerator`。`@ConditionalOnProperty(name = "app.batch.job", havingValue = "JOBxxxx")` |
| `<業務>/<名前>Service.java` | 業務ロジック（入力チェック・登録）。`@Transactional` |
| `<業務>/<名前>Mapper.java` + XML | SQL。再実行に備えて冪等に |
| `<業務>/batch/<入力>Fetcher.java` | 入力の取得（S3・ファイル）。テストで差し替えられるようインタフェースにする |
| テスト | Service（正常・形式エラー・重複（内容が同じ／違う）・見出し不正）、Job（終了コード 0 / 4 / 6 / 8） |

## 決まりごと

- 起動: `--spring.profiles.active=<環境>,batch --app.batch.job=JOBxxxx --input=<場所>`
- 終了コード: 0 正常 / 4 警告あり（一部の行を飛ばした）/ 8 異常終了。JOB0001 は、登録済みの番号で内容が違う行（黙って捨てると訂正に気づけない）を 6 で知らせる（4 と 6 の両方なら 6）。実案件では運用設計の体系に合わせる
- 開始・終了のログをメッセージ ID 付きで出し、件数（処理・登録・スキップ・エラー）を終了ログに必ず含める
- 形式エラーの行は止めずに飛ばすか、全体を止めるかを設計書に従う（書いていなければ planner が確認事項に挙げる）
