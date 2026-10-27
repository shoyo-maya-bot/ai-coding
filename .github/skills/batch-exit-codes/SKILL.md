---
name: batch-exit-codes
description: バッチの起動方法・終了コード・ログの決まり。Job クラスを作る・テストするときに使う
---

# バッチの決まり

- Job は `ApplicationRunner` + `ExitCodeGenerator`、`@ConditionalOnProperty(name = "app.batch.job", havingValue = "JOBxxxx")`
- 起動: `--spring.profiles.active=<環境>,batch --app.batch.job=JOBxxxx --input=<場所>`（プロファイル batch で Web サーバーを起動しない）
- 終了コード: 0 正常 / 4 警告（一部の行を飛ばした）/ 8 異常（引数不足・入力が読めない・想定外の例外）。JOB0001 は、登録済みの番号で内容が違う行を 6（APPW0002. 4 より優先）で知らせる
- ログ: 開始（APPI0001）と終了（APPI0002 + 件数）を必ず出す。飛ばした行は APPW0001 + 行番号と理由
- テスト: 終了コード 0 / 4 / 8（使うなら 6 も）を、入力取得（Fetcher）をラムダで差し替えて確かめる
- クラウドでは EventBridge Scheduler → Step Functions → ECS タスクで起動される（dev-environment の cloud/）
