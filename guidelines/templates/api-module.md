# API 1 本の作り方

例: [API0001 / API0002 会員照会・登録](../../samples/design-docs/api/API0001-0002_member.md) → `template/src/main/java/com/example/app/member/`

## 必要なファイル

| ファイル | 内容 |
|---|---|
| `<業務>/<業務>Controller.java` | `@RestController`。入力は record + Bean Validation |
| `<業務>/<業務>Service.java` | 業務ロジック。エラーは `BusinessException` / `NotFoundException` |
| `<業務>/<業務>Mapper.java` + XML | SQL |
| テスト | Service（インメモリ Mapper）、Controller（MockMvc standalone + 例外ハンドラ） |
| `src/test/resources/karate/<業務>.feature` | 結合テストのシナリオ（正常・業務エラー・該当なし） |

## 決まりごと

| 結果 | ステータス | 本文 |
|---|---|---|
| 照会成功 | 200 | エンティティ |
| 登録成功 | 201 + `Location` | 登録したエンティティ |
| 入力誤り | 400 | `{ messageId: APPE0001, message, details[] }` |
| 該当なし | 404 | `{ messageId, message, details: [] }` |
| 業務エラー（重複など） | 409 | 同上 |

- パスは `/api/v1/<業務の複数形>`。版を上げるときは `/v2` を並べる
- OpenAPI がある場合は、実装と OpenAPI の食い違いを design-diff で確かめる
