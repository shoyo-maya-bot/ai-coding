---
applyTo: "template/src/main/resources/mapper/**/*.xml"
---

- 値は `#{}` で渡す。`${}` は禁止（D9 で検出）
- 再実行されるバッチの登録は冪等にする（`ON CONFLICT DO NOTHING` など）
- 設計書のテーブル操作（CRUD）以外の SQL を書かない
