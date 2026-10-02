---
description: フェーズ 5 全ゲートの再実行と PR 本文の下書き
agent: orchestrator
argument-hint: 対象の機能 ID（例 JOB0001）
---

機能 ${input:feature:例 JOB0001} について、`scripts/verify-gates.sh`（Windows は `scripts\verify-gates.ps1`）を実行し、
結果と判定表をまとめた PR 本文の下書きを作ってください。push と PR 作成は人が行います。
