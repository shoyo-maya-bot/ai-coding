---
title: "会員照会・登録 API"
id: "DOC-API-API0001"
type: api
status: approved
---

# API0001 / API0002 会員照会・登録

## 1. 概要

| API ID | メソッド | パス | 内容 |
|---|---|---|---|
| API0001 | GET | `/api/v1/members/{id}` | 会員を 1 件照会する |
| API0002 | POST | `/api/v1/members` | 会員を登録する |

実装クラス: `com.example.app.member.MemberController`、`MemberService`、`MemberMapper`

## 2. API0001 会員照会

- 入力: パス `id`（数値）
- 出力: 200 `{ id, name, email }`
- 該当なし: 404、メッセージ ID APPE0002「会員が見つかりません（会員ID: {0}）。」

## 3. API0002 会員登録

### 入力

| 項目 | 必須 | 形式 | 桁 |
|---|---|---|---|
| name | ○ | 文字列（前後の空白は除く） | 50 |
| email | ○ | メールアドレス（小文字にそろえて保存） | 254 |

### 処理

1. 入力チェック。誤りは 400、メッセージ ID APPE0001、項目別のエラーを details に入れる
2. メールアドレスの重複チェック（大文字小文字を区別しない）。重複は 409、APPE0003
3. 会員テーブルに登録し、採番した ID を返す

### 出力

201、`Location: /api/v1/members/{id}`、本文 `{ id, name, email }`
