# 取込バッチ用のサンプル CSV を S3 エミュレータに置く（Windows PowerShell。AWS CLI 不要）
#   先に local で docker compose up -d --wait を実行しておく
#   ポートとバケット名は、環境変数 → local/.env → 既定値 の順で決める（docker compose と同じ優先順位）
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

# .env から 1 つの値を読む（無ければ $null）
function Get-EnvFileValue([string]$Name) {
    if (-not (Test-Path ".env")) { return $null }
    $value = $null
    foreach ($line in Get-Content ".env" -Encoding UTF8) {
        if ($line -match "^\s*$Name\s*=\s*(.*)$") {
            $value = $Matches[1].Trim().Trim('"').Trim("'")
        }
    }
    return $value
}

$bucket = if ($env:S3_BUCKET) { $env:S3_BUCKET } elseif (Get-EnvFileValue "S3_BUCKET") { Get-EnvFileValue "S3_BUCKET" } else { "sample-bucket" }
$port = if ($env:S3_PORT) { $env:S3_PORT } elseif (Get-EnvFileValue "S3_PORT") { Get-EnvFileValue "S3_PORT" } else { "9090" }
try {
    # -UseBasicParsing: Windows PowerShell 5.1 で「Security Warning: Script Execution Risk」の確認で止まらないようにする
    Invoke-WebRequest -UseBasicParsing -Method Put -InFile "data/orders.csv" -Uri "http://localhost:$port/$bucket/orders.csv" | Out-Null
} catch {
    Write-Host "アップロードに失敗しました: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "S3 エミュレータが起動しているか確かめてください（docker compose ps で s3 が healthy）" -ForegroundColor Red
    exit 1
}
Write-Host "uploaded: s3://$bucket/orders.csv"
