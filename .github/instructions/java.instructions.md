---
applyTo: "template/src/main/**/*.java"
---

- `guidelines/coding-standards.md` と `guidelines/project-structure.md` に従う
- 層の責務: Controller は入力と応答だけ、Service に業務ロジックと `@Transactional`、SQL は Mapper XML
- エラーは `BusinessException` / `NotFoundException` + メッセージ ID。本文は `messages.properties`
- ログは `log`（SLF4J）。先頭にメッセージ ID。`System.out` 禁止。個人情報を出さない
- Java 17 の範囲で書く。1 メソッド 80 行・複雑度 12 以内
