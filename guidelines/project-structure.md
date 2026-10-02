# プロジェクト構成と生成順序

## パッケージ

```text
template/src/main/java/com/example/app/
├── AppApplication.java          # 起動クラス（API / バッチをプロファイルで切替）
├── common/                      # 例外・メッセージ ID・例外ハンドラ（業務で共通）
├── <業務>/                       # 例: member, order
│   ├── <業務>Controller.java     # API
│   ├── <業務>Service.java        # 業務ロジック
│   ├── <業務>Mapper.java         # SQL のインタフェース
│   ├── <エンティティ>.java        # record
│   └── batch/                   # その業務のバッチ（Job・入出力）
template/src/main/resources/
├── mapper/<業務>Mapper.xml
├── messages.properties
└── application*.yml             # local / batch / cloud プロファイル
template/src/test/java/...       # main と同じパッケージにテスト
template/src/test/resources/karate/<業務>.feature
```

実案件で社内の共通ライブラリ（ジョブ基盤・ログ・メッセージ）がある場合は、`common/` を置き換えて使います。

## 生成順序（coder が守る）

依存される側から作ると、途中でもコンパイルが通り、ゲートで早く間違いに気づけます。

1. メッセージ ID（`MessageIds` と `messages.properties`）
2. エンティティ（record）
3. Mapper インタフェースと XML
4. Service
5. Controller または Job
6. 設定（`application*.yml`）

テストは同じ順に、tester が作ります。

## 設計書の参照

設計書は別リポジトリに置き、[../context-sources.yaml](../context-sources.yaml) で場所を設定します。
エージェントは設計書を **Front Matter の `id`** で特定します（ファイル名に頼らない）。
