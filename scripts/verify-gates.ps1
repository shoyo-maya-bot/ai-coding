# 品質ゲートを CI と同じ内容・同じ順で実行する（Windows PowerShell 5.1 / PowerShell 7）. CI の windows ジョブもこのスクリプトを呼ぶ.
#   .\scripts\verify-gates.ps1           PR と同じ（全要件 implemented 以上）
#   .\scripts\verify-gates.ps1 -Final    完了時・main と同じ（全要件 proven）
# ゲートの一覧と順番は verify-gates.sh と同じにする（tests/test_verify_gates.py が確かめる）.
# ゲートを通すためにチェックを甘くしないこと（guidelines/workflow.md の禁止事項）
# 前提: Java 17、Python 3.10 以上で python -m pip install -e "tools/spec-trace[dev]" -e "tools/test-scaffold[dev]" pyyaml -c constraints.txt
param([switch]$Final)
# 外部コマンド（gradle・pip など）が標準エラーに書いただけでは止めない（結果は終了コードで判定する）
$ErrorActionPreference = 'Continue'
# Python の出力を UTF-8 にする（パイプやファイルに出すとき、Windows の既定の文字コードでは日本語を書けず落ちるため）
$env:PYTHONUTF8 = '1'
Set-Location (Split-Path $PSScriptRoot -Parent)
# Python は $env:PYTHON → python の順で選ぶ. py ランチャーは使わない（py は PATH の python と別の版・別の環境を選ぶことがあり、
# python -m pip で入れた環境と違う Python でゲートを動かしてしまうため。手順書の python -m pip と同じ Python を使う）
$py = if ($env:PYTHON) { $env:PYTHON } else { 'python' }
$require = if ($Final) { 'proven' } else { 'implemented' }
$results = @()
function Invoke-Gate([string]$Name, [scriptblock]$Command) {
    Write-Output "`n=== $Name"
    $global:LASTEXITCODE = 0
    $ok = $true
    try { & $Command } catch { Write-Output $_; $ok = $false }
    if ($LASTEXITCODE -ne 0) { $ok = $false }
    $script:results += [pscustomobject]@{ Gate = $Name; Result = $(if ($ok) { 'PASS' } else { 'FAIL' }) }
}
# gate: java
Invoke-Gate 'D1-D5,D9 Java' { & .\template\gradlew.bat -p template --no-daemon --continue qualityGate }
# gate: pytest
Invoke-Gate 'tools tests' { & $py -m pytest -q tools/spec-trace/tests tools/test-scaffold/tests tests }
# gate: ruff
Invoke-Gate 'lint' {
    & $py -m ruff check tools scripts tests
    if ($LASTEXITCODE -eq 0) { & $py -m ruff format --check tools scripts tests }
}
# gate: trace
#   D10（Karate のシナリオ）は存在・@ignore でないこと・確認の有無までを見る. Karate は起動中のアプリが要るので CI では実行しない
Invoke-Gate 'D6-D8,D10 trace' {
    & $py -m spec_trace check traceability/specs --root . --enforce-drift --require $require `
        --test-results template/build/test-results/test -f markdown
}
# gate: authority
Invoke-Gate 'D11 authority' { & $py scripts/verify_authority.py }
# gate: docs
Invoke-Gate 'docs' { & $py scripts/check_docs.py }
# gate: drift
Invoke-Gate 'template drift' { & $py scripts/check_template_drift.py }
$results | Format-Table -AutoSize | Out-String | Write-Output
Write-Output "要件の状態: $require 以上を必須"
if ($results.Result -contains 'FAIL') {
    Write-Output 'FAIL があります。原因を直してください（チェックを甘くして通さない）。'
    exit 1
}
Write-Output 'すべてのゲートを通過しました。'
