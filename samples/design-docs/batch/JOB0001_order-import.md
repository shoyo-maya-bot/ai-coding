---
title: "注文ファイル取込"
id: "DOC-BATCH-JOB0001"
type: batch
status: approved
---

# JOB0001 注文ファイル取込

## 1. 概要

外部システムから受け取った注文 CSV を、注文テーブルに登録する日次バッチ。

| 項目 | 内容 |
|---|---|
| ジョブ ID | JOB0001 |
| 起動 | 毎日 2:00（EventBridge Scheduler → Step Functions） |
| 入力 | S3 `inbound/orders.csv`（UTF-8、BOM 可、1 行目は見出し） |
| 出力 | 注文テーブル（orders） |
| 実装クラス | `com.example.app.order.batch.OrderImportJob`、`com.example.app.order.OrderImportService` |
| 起動引数 | `--app.batch.job=JOB0001 --input=<s3://バケット/キー>` |

## 2. 処理

### STEP1 入力チェック

- 1 行目が見出し `order_no,member_id,product_code,quantity` であること。違えば異常終了（終了コード 8）
- 各行: 列数 4、order_no 必須、member_id は数値、product_code 必須、quantity は 1〜999
- 形式エラーの行は飛ばして続行し、行番号と理由を警告ログ（APPW0001）に出す

### STEP2 登録

- チェックを通った行を注文テーブルに登録する
- 注文番号が既にある場合は登録しない（再実行しても重複しない）

### STEP3 終了

| 結果 | 終了コード | メッセージ |
|---|---|---|
| 全行正常 | 0 | APPI0002（件数を出力） |
| 形式エラーの行あり | 4 | APPW0001 + APPI0002 |
| 入力が読めない・引数不足 | 8 | エラーログ |

## 3. メッセージ

| ID | 種別 | 本文 |
|---|---|---|
| APPI0001 | 情報 | 処理を開始します。 |
| APPI0002 | 情報 | 処理を終了します。 |
| APPW0001 | 警告 | 形式に誤りがある行を飛ばしました。 |
