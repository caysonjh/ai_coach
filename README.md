# AI Coach

Local-first AI triathlon coach for training planning, activity analysis, manual Garmin-style health metrics, and Ollama-based insights.

## Features

- Strava-first connector boundary with OAuth URL generation and webhook endpoint.
- Garmin adapter placeholders for official API, manual imports, and optional non-official connectors.
- Manual health metric entry for sleep score, HRV, resting HR, VO2 Max, FTP, Training Readiness, Training Effect, Endurance Score, Lactate Threshold, Hill Score, and custom metrics.
- Local Garmin file directory scan for CSV, TCX, GPX, and FIT activity files.
- In-app calendar for planned workouts and availability constraints.
- Coach endpoint that uses local Ollama when available and falls back to deterministic guidance when unavailable.
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

## Ollama

Install and run Ollama locally, then pull models:

```bash
ollama pull gpt-oss:20b
ollama pull embeddinggemma
```

The backend defaults to `http://localhost:11434`.

Recommended model: `gpt-oss:20b`. It is the best default for this app because training
planning needs structured output, reasoning, and tool-style workflows. Use `qwen3:8b`
if you need a lighter/faster local model, and consider `gpt-oss:120b` only on very
large hardware.

## Local Garmin Files

Drop Garmin exports into `./garmin_files`. The backend scans this folder on startup and
from the Local Files panel in the UI. CSV activity files should include columns such as
`sport`, `name`, `start_time`, and `duration_seconds`. CSV health metric files should
include `metric_date`, `metric_type`, `value_num` or `value`, and `unit`.

The app also exports a compact coach memory snapshot to `./coach_context.md`.
