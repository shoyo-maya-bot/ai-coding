---
name: message-ids
description: メッセージ ID の採番・追加・使い方。API のエラー応答やバッチのログにメッセージを出すときに使う
---

# メッセージ ID

- 形式: `APP` + 種別（`I` 情報 / `W` 警告 / `E` エラー）+ 4 桁の連番。例 `APPE0003`
- 追加の手順: ① `common/MessageIds.java` に定数 ② `messages.properties` に本文（埋め込みは `{0}`）③ 設計書のメッセージ表と一致させる
- API: `BusinessException(MessageIds.X, 値...)` を投げると `ApiExceptionHandler` が `{messageId, message, details}` にする
  - 400 → APPE0001（入力誤り）/ 404 → `NotFoundException` / 409 → `BusinessException`
- バッチ: `log.info("{} ...", MessageIds.X)` のようにログの先頭に ID を出す
- 実案件では社内のメッセージ体系・共通ライブラリに置き換える
