# CI と同じ品質ゲートを同じ順でローカル実行する（Windows PowerShell）
#   .\scripts\verify-gates.ps1           全ゲート
#   .\scripts\verify-gates.ps1 -Final    完了時（全要件 proven を必須にする）
param([switch]$Final)
Set-Location (Split-Path $PSScriptRoot -Parent)
$py = if (Get-Command py -ErrorAction SilentlyContinue) { 'py' } else { 'python' }
$results = @()
function Run($name, [scriptblock]$cmd) {
    Write-Host "`n=== $name"
    & $cmd
    $script:results += [pscustomobject]@{ Gate = $name; Result = $(if ($LASTEXITCODE -eq 0) { 'PASS' } else { 'FAIL' }) }
}
Run 'D1-D5,D9 Java' { Push-Location template; .\gradlew.bat --no-daemon -q qualityGate; Pop-Location }
$req = if ($Final) { @('--require', 'proven') } else { @() }
Run 'D6-D8,D10 trace' { & $py -m spec_trace check traceability/specs --root . --enforce-drift @req }
Run 'D11 authority' { & $py scripts/verify_authority.py }
$results | Format-Table -AutoSize
if ($results.Result -contains 'FAIL') { Write-Host 'FAIL があります。原因を直してください（チェックを甘くして通さない）。' -ForegroundColor Red; exit 1 }
Write-Host 'すべてのゲートを通過しました。' -ForegroundColor Green
