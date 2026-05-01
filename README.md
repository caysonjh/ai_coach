# AI Coach

AI triathlon coach for training planning, activity analysis, manual Garmin-style health metrics, and ChatGPT-native coaching actions.

## Features

- Strava-first connector boundary with OAuth URL generation and webhook endpoint.
- Garmin adapter placeholders for official API, manual imports, and optional non-official connectors.
- Manual health metric entry for sleep score, HRV, resting HR, VO2 Max, FTP, Training Readiness, Training Effect, Endurance Score, Lactate Threshold, Hill Score, and custom metrics.
- Local Garmin file directory scan for CSV, TCX, GPX, and FIT activity files.
- In-app calendar for planned workouts and availability constraints.
- Coach workflow that exposes grounded context and write-back actions for a ChatGPT-native coach, with a deterministic local preview path in the web UI.
- Persistent memory model for goals, accepted plans, insights, and long-term training context.
- Coach context snapshot export to `coach_context.md` for compact future-session memory.

## Quickstart

One-command local launch:

```bash
./scripts/start_app.sh
```

This starts the backend and frontend, then opens `http://localhost:5173`.
Keep that terminal open while using the app. Press `Ctrl-C` in that terminal to stop both servers.

Stop both servers:

```bash
./scripts/stop_app.sh
```

Backend:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
uvicorn app.main:app --reload --app-dir backend
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`.

Production backend container:

```bash
docker build -t ai-coach-backend .
docker run -p 8000:8000 --env-file .env ai-coach-backend
```

## ChatGPT Actions

The main coach experience is meant to live inside ChatGPT using a Custom GPT with actions.
That uses your ChatGPT Plus session for the model and keeps this backend focused on context,
history, and write-back operations.

Set these environment variables for a deployed backend:

```bash
CHATGPT_PUBLIC_BASE_URL=https://your-domain.example
CHATGPT_ACTION_TOKEN=your-long-random-token
```

For a local app that pushes changes to that deployed backend, also set:

```bash
CHATGPT_SYNC_TARGET_URL=https://your-domain.example
CHATGPT_SYNC_TARGET_TOKEN=your-long-random-token
```

Then import the backend OpenAPI document into a Custom GPT and point its action calls at:

- `GET /api/chatgpt/openapi.json`
- `POST /api/chatgpt/context`
- `POST /api/chatgpt/record`
- `POST /api/chatgpt/apply-workouts`

The web UI keeps a deterministic local preview so you can still inspect the current data flow without ChatGPT.
See [docs/chatgpt-actions.md](docs/chatgpt-actions.md) for the import and smoke-test loop.

When `CHATGPT_SYNC_TARGET_URL` is configured, local writes auto-push to the remote backend after each mutation. The ChatGPT Actions panel still has a manual `Sync Now` button if you want to force a full refresh.

## Ollama

Ollama is now a legacy local preview path only. If you want to use it for offline experimentation,
install and run it manually, then pull models:

```bash
ollama pull llama3.1
ollama pull embeddinggemma
```

To verify the ChatGPT action path locally:

```bash
BASE_URL=http://127.0.0.1:8000 CHATGPT_ACTION_TOKEN=dev-token ./scripts/chatgpt_smoke_test.sh
```

## Local Garmin Files

Drop Garmin exports into `./garmin_files`. The backend scans this folder on startup and
from the Local Files panel in the UI. CSV activity files should include columns such as
`sport`, `name`, `start_time`, and `duration_seconds`. CSV health metric files should
include `metric_date`, `metric_type`, `value_num` or `value`, and `unit`.

The app also exports a compact coach memory snapshot to `./coach_context.md`.
