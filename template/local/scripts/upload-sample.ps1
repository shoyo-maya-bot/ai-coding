# 取込バッチ用のサンプル CSV を S3 エミュレータに置く（Windows PowerShell。AWS CLI 不要）
$bucket = if ($env:S3_BUCKET) { $env:S3_BUCKET } else { "sample-bucket" }
$port = if ($env:S3_PORT) { $env:S3_PORT } else { "9090" }
Set-Location (Split-Path $PSScriptRoot -Parent)
Invoke-WebRequest -Method Put -InFile "data/orders.csv" -Uri "http://localhost:$port/$bucket/orders.csv" | Out-Null
Write-Host "uploaded: s3://$bucket/orders.csv"
