# 取込バッチ用のサンプル CSV を S3 エミュレータに置く（Windows PowerShell。AWS CLI 不要）
#   先に local で docker compose up -d --wait を実行しておく
$ErrorActionPreference = "Stop"
$bucket = if ($env:S3_BUCKET) { $env:S3_BUCKET } else { "sample-bucket" }
$port = if ($env:S3_PORT) { $env:S3_PORT } else { "9090" }
Set-Location (Split-Path $PSScriptRoot -Parent)
try {
    # -UseBasicParsing: Windows PowerShell 5.1 で「Security Warning: Script Execution Risk」の確認で止まらないようにする
    Invoke-WebRequest -UseBasicParsing -Method Put -InFile "data/orders.csv" -Uri "http://localhost:$port/$bucket/orders.csv" | Out-Null
} catch {
    Write-Host "アップロードに失敗しました: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "S3 エミュレータが起動しているか確かめてください（docker compose ps で s3 が healthy）" -ForegroundColor Red
    exit 1
}
Write-Host "uploaded: s3://$bucket/orders.csv"
