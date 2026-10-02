#!/usr/bin/env bash
# 取込バッチ用のサンプル CSV を S3 エミュレータに置く（AWS CLI 不要）
set -euo pipefail
cd "$(dirname "$0")/.."
BUCKET="${S3_BUCKET:-sample-bucket}"
PORT="${S3_PORT:-9090}"
curl -sf -X PUT --upload-file data/orders.csv "http://localhost:${PORT}/${BUCKET}/orders.csv"
echo "uploaded: s3://${BUCKET}/orders.csv"
