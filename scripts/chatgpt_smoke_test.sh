#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"
TOKEN="${CHATGPT_ACTION_TOKEN:-}"

if [[ -z "${TOKEN}" ]]; then
  echo "CHATGPT_ACTION_TOKEN is required." >&2
  exit 1
fi

auth_header="Authorization: Bearer ${TOKEN}"

echo "Checking ChatGPT actions status..."
curl -fsS "${BASE_URL}/api/chatgpt/status" -H "${auth_header}" >/dev/null

echo "Fetching action OpenAPI..."
curl -fsS "${BASE_URL}/api/chatgpt/openapi.json" -H "${auth_header}" >/dev/null

echo "Requesting coach context..."
curl -fsS "${BASE_URL}/api/chatgpt/context" \
  -H "${auth_header}" \
  -H "Content-Type: application/json" \
  -d '{"message":"Analyze my last week of training","aggressiveness":0.45,"autonomy":"suggest_then_approve","conversation_history":[]}' >/dev/null

echo "Smoke test complete."
