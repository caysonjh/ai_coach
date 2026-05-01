# ChatGPT Actions Setup

## What this is

This app now treats ChatGPT as the main coach model. The backend supplies grounded training context and write-back actions, and ChatGPT handles the reasoning.

## Required environment

Set these before deploying the backend:

```bash
DATABASE_URL=postgresql+psycopg://user:pass@host:5432/ai_coach
CHATGPT_PUBLIC_BASE_URL=https://your-backend.example
CHATGPT_ACTION_TOKEN=your-long-random-token
```

`DATABASE_URL` can stay SQLite for local testing, but a persistent database is the better production choice.

## Backend endpoints for ChatGPT

- `GET /api/chatgpt/status`
- `GET /api/chatgpt/openapi.json`
- `POST /api/chatgpt/context`
- `POST /api/chatgpt/record`
- `POST /api/chatgpt/apply-workouts`

## Import flow

1. Deploy the backend to a public HTTPS URL.
2. Open `GET /api/chatgpt/openapi.json` on that URL.
3. Import that spec into a Custom GPT with actions.
4. Add the bearer token header using `CHATGPT_ACTION_TOKEN`.
5. Use the `context` action before answering, and the `record` action after producing a plan.

## Local verification

Run the backend locally, set a token, then execute:

```bash
BASE_URL=http://127.0.0.1:8000 CHATGPT_ACTION_TOKEN=dev-token ./scripts/chatgpt_smoke_test.sh
```

The script checks:

- the status endpoint,
- the trimmed OpenAPI document,
- a grounded coach context request.
