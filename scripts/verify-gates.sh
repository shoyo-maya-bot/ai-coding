#!/usr/bin/env bash
# 品質ゲートを CI と同じ内容・同じ順で実行する（push・PR の前に）. CI（.github/workflows/ci.yml）もこのスクリプトを呼ぶ.
#   ./scripts/verify-gates.sh             PR と同じ（全要件 implemented 以上）
#   ./scripts/verify-gates.sh --final     完了時・main と同じ（全要件 proven）
# ゲートの一覧と順番は verify-gates.ps1 と同じにする（tests/test_verify_gates.py が確かめる）.
# ゲートを通すためにチェックを甘くしないこと（guidelines/workflow.md の禁止事項）
# 前提: Java 17、Python 3.10 以上で pip install -e "tools/spec-trace[dev]" pyyaml -c constraints.txt
set -uo pipefail
cd "$(dirname "$0")/.."
REQUIRE="implemented"
for arg in "$@"; do
  case "$arg" in
    --final) REQUIRE="proven" ;;
    *) echo "不明な引数: $arg（使えるのは --final だけ）" >&2; exit 2 ;;
  esac
done
PY="${PYTHON:-python3}"
results=()
run() {
  local name="$1"; shift
  echo; echo "=== $name: $*"
  if "$@"; then results+=("| $name | PASS |"); else results+=("| $name | FAIL |"); fi
}
# gate: java
run "D1-D5,D9 Java" template/gradlew -p template --no-daemon --continue qualityGate
# gate: pytest
run "tools tests" "$PY" -m pytest -q tools/spec-trace/tests tests
# gate: ruff
lint() {
  "$PY" -m ruff check tools scripts tests && "$PY" -m ruff format --check tools scripts tests
}
run "lint" lint
# gate: trace
#   D10（Karate のシナリオ）は存在・@ignore でないこと・確認の有無までを見る. Karate は起動中のアプリが要るので CI では実行しない
run "D6-D8,D10 trace" "$PY" -m spec_trace check traceability/specs --root . --enforce-drift --require "$REQUIRE" \
  --test-results template/build/test-results/test -f markdown
# gate: authority
run "D11 authority" "$PY" scripts/verify_authority.py
# gate: docs
run "docs" "$PY" scripts/check_docs.py
# gate: drift
run "template drift" "$PY" scripts/check_template_drift.py
echo; echo "| ゲート | 結果 |"; echo "|---|---|"; printf '%s\n' "${results[@]}"
echo; echo "要件の状態: $REQUIRE 以上を必須"
if printf '%s\n' "${results[@]}" | grep -q FAIL; then
  echo; echo "FAIL があります。原因を直してください（チェックを甘くして通さない）。"; exit 1
fi
echo; echo "すべてのゲートを通過しました。"
