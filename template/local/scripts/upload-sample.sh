#!/usr/bin/env bash
# 取込バッチ用のサンプル CSV を S3 エミュレータに置く（AWS CLI 不要）
#   ポートとバケット名は、環境変数 → local/.env → 既定値 の順で決める（docker compose と同じ優先順位）
set -euo pipefail
cd "$(dirname "$0")/.."

# .env から 1 つの値を読む（source はしない: .env の中身をシェルとして実行しないため）
env_file_value() {
  [ -f .env ] || return 0
  sed -n "s/^[[:space:]]*$1[[:space:]]*=[[:space:]]*//p" .env | tail -n 1 | tr -d '\r' | sed -e 's/^"\(.*\)"$/\1/' -e "s/^'\(.*\)'\$/\1/"
}

BUCKET="${S3_BUCKET:-$(env_file_value S3_BUCKET)}"
BUCKET="${BUCKET:-sample-bucket}"
PORT="${S3_PORT:-$(env_file_value S3_PORT)}"
PORT="${PORT:-9090}"
curl -sf -X PUT --upload-file data/orders.csv "http://localhost:${PORT}/${BUCKET}/orders.csv"
echo "uploaded: s3://${BUCKET}/orders.csv"
