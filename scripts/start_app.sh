#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"
BACKEND_URL="http://127.0.0.1:${BACKEND_PORT}"
FRONTEND_URL="http://localhost:${FRONTEND_PORT}"

wait_for_url() {
  local url="$1"
  local label="$2"
  for _ in {1..40}; do
    if curl -fsS "${url}" >/dev/null 2>&1; then
      return 0
    fi
    sleep 0.5
  done
  echo "Timed out waiting for ${label} at ${url}" >&2
  return 1
}

cleanup() {
  trap - EXIT INT TERM
  echo
  echo "Stopping AI Coach servers..."
  if [[ -n "${BACKEND_PID:-}" ]]; then kill "${BACKEND_PID}" 2>/dev/null || true; fi
  if [[ -n "${FRONTEND_PID:-}" ]]; then kill "${FRONTEND_PID}" 2>/dev/null || true; fi
}

trap cleanup EXIT INT TERM

cd "${ROOT_DIR}"

echo "Starting backend on ${BACKEND_URL}"
uvicorn app.main:app --app-dir backend --port "${BACKEND_PORT}" > "${ROOT_DIR}/backend.log" 2>&1 &
BACKEND_PID=$!

echo "Starting frontend on ${FRONTEND_URL}"
(
  cd "${ROOT_DIR}/frontend"
  npm run dev -- --port "${FRONTEND_PORT}" > "${ROOT_DIR}/frontend.log" 2>&1
) &
FRONTEND_PID=$!

wait_for_url "${BACKEND_URL}/api/health" "backend"
wait_for_url "${FRONTEND_URL}" "frontend"

echo "AI Coach is ready: ${FRONTEND_URL}"
echo "Logs: ${ROOT_DIR}/backend.log and ${ROOT_DIR}/frontend.log"
echo "Press Ctrl-C in this terminal to stop both servers."

if [[ "${OPEN_BROWSER:-1}" == "1" ]]; then
  if command -v open >/dev/null 2>&1; then
    open "${FRONTEND_URL}"
  else
    echo "Open ${FRONTEND_URL} in your browser."
  fi
fi

wait
