---
applyTo: "template/src/test/**"
---

- 期待値は設計書から決める（実装の動きに合わせない）。1 テスト 1 観点、アサーション必須
- 単体テストは DB・外部サービスを使わない（Mapper はインメモリ実装・ラムダで差し替え）
- Controller は MockMvc standalone + `ApiExceptionHandler`。結合は Karate（`src/test/resources/karate/`）
- 書いたテストは対応表の `proofs` に `クラス#メソッド` で記録する
- アサーションを消す・弱める、`@Disabled` は禁止
