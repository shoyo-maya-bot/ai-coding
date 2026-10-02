---
name: mybatis-mapper
description: MyBatis の Mapper インタフェースと XML の書き方。テーブル操作を実装・テストするときに使う
---

# MyBatis Mapper

- インタフェース `<業務>Mapper.java`（`@Mapper`）と XML `resources/mapper/<業務>Mapper.xml` を対で作る。`namespace` は完全修飾名
- 列名はスネークケース、Java はキャメルケース（`map-underscore-to-camel-case: true`）
- 1 件取得は `Optional<T>`、存在確認は `boolean`（`SELECT EXISTS(...)`）、登録の採番は `useGeneratedKeys="true" keyProperty="id"`
- 値は `#{}`。`${}` は使わない（D9）
- 冪等な登録: `INSERT ... ON CONFLICT (<一意キー>) DO NOTHING` → 戻り値 1 = 登録、0 = 既にある
- 単体テストでは Mapper をインメモリ実装（Map）やラムダで差し替える。SQL そのものは結合テスト（Karate + ローカル DB）で確かめる
