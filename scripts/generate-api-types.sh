#!/bin/bash
# 从后端 OpenAPI schema 自动生成前端 TypeScript 类型
# 使用 openapi-typescript 将 /openapi.json 转为 types/api.d.ts
#
# 前置条件: npm install -D openapi-typescript
# 运行方式: bash scripts/generate-api-types.sh
#           或 npm run gen:api-types

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
OUTPUT_FILE="$PROJECT_ROOT/src/types/api-generated.d.ts"

echo "[gen-api-types] 从后端获取 OpenAPI schema..."

# 1. 获取 OpenAPI JSON（后端需运行在 8000 端口）
API_URL="${VITE_API_BASE_URL:-http://localhost:8000}"
curl -s "$API_URL/openapi.json" -o /tmp/openapi.json

echo "[gen-api-types] 生成 TypeScript 类型..."

# 2. 使用 openapi-typescript 生成类型
npx openapi-typescript /tmp/openapi.json -o "$OUTPUT_FILE"

echo "[gen-api-types] 完成 → $OUTPUT_FILE"
rm -f /tmp/openapi.json
