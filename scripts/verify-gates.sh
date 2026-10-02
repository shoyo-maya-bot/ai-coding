#!/usr/bin/env bash
# CI と同じ品質ゲートを同じ順でローカル実行する（push・PR の前に）
#   ./scripts/verify-gates.sh             全ゲート
#   ./scripts/verify-gates.sh --final     完了時（全要件 proven を必須にする）
# ゲートを通すためにチェックを甘くしないこと（guidelines/workflow.md の禁止事項）
set -uo pipefail
cd "$(dirname "$0")/.."
REQUIRE=""
[ "${1:-}" = "--final" ] && REQUIRE="--require proven"
PY="${PYTHON:-python3}"
results=()
run() {
  local name="$1"; shift
  echo; echo "=== $name: $*"
  if "$@"; then results+=("| $name | PASS |"); else results+=("| $name | FAIL |"); fi
}
run "D1-D5,D9 Java" bash -c "cd template && ./gradlew --no-daemon -q qualityGate"
run "D6-D8,D10 trace" "$PY" -m spec_trace check traceability/specs --root . --enforce-drift $REQUIRE
run "D11 authority" "$PY" scripts/verify_authority.py
echo; echo "| ゲート | 結果 |"; echo "|---|---|"; printf '%s\n' "${results[@]}"
if printf '%s\n' "${results[@]}" | grep -q FAIL; then
  echo; echo "FAIL があります。原因を直してください（チェックを甘くして通さない）。"; exit 1
fi
echo; echo "すべてのゲートを通過しました。"
