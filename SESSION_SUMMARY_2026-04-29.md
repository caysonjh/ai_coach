# AI Coach Session Summary - 2026-04-29

## High-Level Summary

This session turned an empty project directory containing only `me.md` into a working local-first AI triathlon coach app. The app now has a FastAPI backend, React/Vite frontend, SQLite persistence, local Ollama integration, Strava/Garmin connector boundaries, Garmin file imports, manual Garmin-style health metrics, training calendar planning, coach context export, place/location feedback, gear tracking, and route/gear-aware coaching context.

The app is intended for Cayson Hamilton: aspiring elite age-group 70.3 triathlete, targeting a sub-5-hour 70.3 and eventual Ironman 70.3 World Championship qualification, while accounting for R-CPD, chronic fatigue syndrome, climbing/strength work, variable schedule, and GI-sensitive fueling.

## Prompt / Response Timeline

1. **Read `me.md`**
   - User asked to read local profile and understand athletic goals.
   - Assistant summarized the key context: elite age-group triathlon goal, sub-5 70.3 target, R-CPD/CFS constraints, FTP/VO2max markers, and flexible planning preferences.

2. **Plan the AI Coach App**
   - User described an app using local Ollama, Garmin, Strava, calendar planning, memory, and adaptive scheduling.
   - Assistant researched current Strava/Garmin/Ollama feasibility and produced a plan:
     - Personal MVP.
     - Python/FastAPI + React.
     - Strava primary source.
     - Garmin official adapter plus manual/import fallback.
     - In-app calendar.
     - AI changes require approval.

3. **Manual Garmin Health Metrics**
   - User requested manual input for Garmin metrics if connector data is unavailable.
   - Plan updated to include manual logging for sleep score, HRV, resting HR, VO2 Max, FTP, Training Readiness, Training Effect, Endurance Score, Lactate Threshold, Hill Score, Body Battery, stress, Pulse Ox, respiration, body metrics, and custom fields.

4. **Implement MVP**
   - User asked to implement the plan.
   - Assistant scaffolded full backend/frontend app:
     - FastAPI API.
     - SQLModel models.
     - SQLite default DB.
     - React UI.
     - Manual metrics form.
     - Calendar.
     - Coach endpoint.
     - Strava/Garmin boundaries.
     - Tests and README.
   - Backend tests and frontend build were made to pass.

5. **Ollama Startup + Model Choice**
   - User asked if app can ensure Ollama is running and asked which model is best.
   - Assistant added Ollama status/start endpoints and UI panel.
   - Default model changed to `gpt-oss:20b`, with `embeddinggemma` as embedding model.
   - Recommendation:
     - `gpt-oss:20b` default.
     - `qwen3:8b` lighter fallback.
     - `gpt-oss:120b` / `llama3.3:70b` only for large hardware.

6. **Install Ollama Models**
   - User asked to install recommended models.
   - Assistant started:
     - `ollama pull gpt-oss:20b`
     - `ollama pull embeddinggemma`
   - Network was extremely slow. Downloads were left running for a while, then noted as incomplete.
   - Current user later decided to resume later on a better connection.

7. **Local Garmin Directory + Coach Context Snapshot**
   - User suggested using a local directory for Garmin files and exporting AI coach state to a file.
   - Assistant implemented:
     - `./garmin_files/` directory scan on startup.
     - Manual scan endpoint/UI.
     - CSV/TCX/GPX/FIT import support.
     - `fitdecode` installed successfully for FIT parsing.
     - `coach_context.md` exported on startup and after coach interactions.

8. **Atlas Browser Feasibility**
   - User asked whether ChatGPT Atlas could automate Garmin Connect downloads.
   - Assistant used official OpenAI docs and answered:
     - Atlas Agent can use logged-in websites, but official release notes say it cannot download files or access local filesystem.
     - Recommendation: keep local automation/import directory as durable ingestion boundary instead of relying on Atlas.

9. **Testing Without Ollama**
   - User asked whether they were just waiting on Ollama.
   - Assistant clarified:
     - App can be tested now with fallback coach.
     - Full AI planning requires Ollama model availability.

10. **Manual Metrics UI Change**
    - User requested one entry box per metric and one submit button.
    - Assistant replaced dropdown metric entry with batch metric form:
      - One date.
      - One input per metric.
      - Shared notes.
      - Single `Save Filled Metrics` button.

11. **Strava `.env` Location**
    - User asked where to put Strava client credentials.
    - Assistant explained:
      - Copy `.env.example` to `.env` at repo root.
      - Fill `STRAVA_CLIENT_ID`, `STRAVA_CLIENT_SECRET`, and redirect URI.
      - Restart backend.

12. **Route Suggestions, Gear Mileage, Adventure Sessions**
    - User requested:
      - AI should suggest local places to run/ride/swim.
      - Learn from workout location feedback.
      - Track shoe/bike mileage from Strava gear.
      - Recommend gear per workout.
      - Include trail running, gravel cycling, and MTB when appropriate.
    - Plan choices:
      - Newport Beach default location.
      - Manual place library first.
      - Strava + local rules for gear.
      - Recommend gear only, do not update Strava.
      - Trail/gravel/MTB as controlled substitutions.
    - Assistant implemented models, APIs, UI, recommendation logic, and coach context integration.

13. **Session Summary**
    - User asked for this markdown file summarizing the session, files, functions, and future-session context.

## Created / Updated Files

### Root

- `.env.example`
  - Template for local configuration.
  - Includes app name, DB URL, Ollama model settings, Strava credentials, Garmin import dir, and coach context export path.

- `.gitignore`
  - Ignores `.env`, virtual envs, caches, SQLite DBs, frontend build/dependencies, `garmin_files/`, and `coach_context.md`.

- `README.md`
  - Quickstart instructions.
  - Ollama setup.
  - Local Garmin file workflow.
  - Recommended model notes.

- `pyproject.toml`
  - Python project config and dependencies.
  - Uses FastAPI, SQLModel, pydantic-settings, httpx, python-multipart, fitdecode, pytest, ruff.

- `coach_context.md`
  - Generated compact AI coach memory snapshot.
  - Ignored by git.
  - Includes athlete summary, training summary, recent activities, metrics, planned workouts, insights, durable memories, locations, feedback, and gear.

- `ai_coach.db`
  - Local SQLite database.
  - Ignored by git.

- `garmin_files/`
  - Local directory for Garmin exports.
  - Ignored by git.
  - App scans it on startup and via UI button.

- `SESSION_SUMMARY_2026-04-29.md`
  - This file.

### Backend

- `backend/app/main.py`
  - FastAPI app factory.
  - CORS setup.
  - Startup DB init.
  - Seeds profile from `me.md`.
  - Scans Garmin files and exports coach context on startup.

- `backend/app/core/config.py`
  - App settings loaded from `.env`.
  - Includes Ollama, Strava, Garmin import, and context export settings.

- `backend/app/db/session.py`
  - SQLModel engine/session.
  - Creates DB tables.
  - Contains lightweight SQLite column migration shim for new activity/workout fields.

- `backend/app/models/entities.py`
  - Core database models:
    - `AthleteProfile`
    - `OAuthAccount`
    - `Activity`
    - `HealthMetric`
    - `PlannedWorkout`
    - `ScheduleConstraint`
    - `PlanVersion`
    - `CoachMemory`
    - `CoachInsight`
    - `ImportJob`
    - `TrainingLocation`
    - `WorkoutLocationFeedback`
    - `GearItem`
    - `GearRecommendation`
  - Enums:
    - `Source`
    - `Sport`
    - `SportVariant`
    - `WorkoutStatus`
    - `MetricType`
    - `GearType`

- `backend/app/schemas/api.py`
  - Pydantic request/response schemas for activities, metrics, workouts, coach, settings, Ollama, Garmin import, context export, locations, feedback, and gear.

- `backend/app/api/routes.py`
  - Main API router.
  - Exposes:
    - Health/settings/profile/dashboard.
    - Activities.
    - Manual metrics.
    - Calendar workouts/constraints.
    - Coach.
    - Garmin file scan.
    - Context export.
    - Ollama status/start/recommendation.
    - Strava auth/sync/webhook/sync-gear.
    - Locations and location feedback.
    - Gear.

- `backend/app/connectors/strava.py`
  - Strava OAuth URL/callback token exchange.
  - Token refresh.
  - Recent activity sync.
  - Gear sync from Strava athlete payload.
  - Maps Strava sport types to local sport variants.

- `backend/app/connectors/garmin.py`
  - Garmin connector status.
  - Official API marked adapter-ready but unavailable until credentials/access.
  - Manual import available.

- `backend/app/services/analytics.py`
  - Training summaries:
    - 7d/28d volume.
    - Discipline split.
    - Latest health metrics.
    - Calendar adherence.
    - Recovery flags.

- `backend/app/services/coach.py`
  - Ollama-backed structured coach responses.
  - Rule-based fallback if Ollama unavailable.
  - Includes profile, activities, health metrics, plan, schedule constraints, memories, locations, feedback, and gear in context.
  - Exports coach context after interactions.

- `backend/app/services/garmin_files.py`
  - Scans configured Garmin import directory.
  - Imports CSV/TCX/GPX/FIT files.
  - Tracks import jobs and avoids re-importing completed files.

- `backend/app/services/imports.py`
  - Parsers for:
    - Activity CSV.
    - Health metric CSV.
    - GPX.
    - TCX.
    - FIT via `fitdecode`, with fallback attempt for `fitparse` if present.

- `backend/app/services/metrics.py`
  - Garmin-style manual metric definitions and labels.

- `backend/app/services/ollama.py`
  - Ollama status.
  - Start/ensure running.
  - Installed model detection.
  - Chat JSON call.
  - Embedding call.

- `backend/app/services/recommendations.py`
  - Ranks locations based on sport, variant, tags, intended stimulus, and feedback.
  - Recommends gear based on sport, variant, surface, mileage, and retirement threshold.

- `backend/app/services/state_export.py`
  - Exports compact coach context to `coach_context.md`.

### Backend Tests

- `backend/tests/test_analytics.py`
  - Verifies training summary and recovery flag behavior.

- `backend/tests/test_metrics.py`
  - Verifies metric options include important Garmin metrics.

- `backend/tests/test_imports.py`
  - Verifies health metric CSV parsing.
  - Verifies GPX activity parsing.

- `backend/tests/test_recommendations.py`
  - Verifies location ranking.
  - Verifies gear recommendation.

### Frontend

- `frontend/package.json`
  - React/Vite/TypeScript dependencies and scripts.

- `frontend/index.html`
  - Vite app entry HTML.

- `frontend/tsconfig.json`
  - TypeScript config.

- `frontend/vite.config.ts`
  - Vite config and API proxy to backend.

- `frontend/src/lib/api.ts`
  - TypeScript API client.
  - Types for dashboard, metrics, activities, workouts, coach, Ollama, Garmin scan, context export, locations, feedback, and gear.

- `frontend/src/main.tsx`
  - Single-page React app.
  - Panels:
    - Dashboard.
    - Coach.
    - Calendar.
    - Places + Feedback.
    - Manual Metrics batch entry.
    - Gear.
    - Local Files.
    - Ollama.
    - Connectors.
    - Recent Activities.
    - Metric Log.

- `frontend/src/styles/app.css`
  - App layout and component styling.
  - Responsive behavior.
  - Batch metric form, compact lists, Ollama status, places/gear panels.

## Implemented Functional Areas

### Local-First App

- Backend: FastAPI.
- Frontend: React + Vite + TypeScript.
- Database: SQLite by default.
- Local-first privacy: no external LLM required.

### Athlete Profile / Memory

- Seeds profile from `me.md`.
- Stores durable coach memories.
- Exports compact context to `coach_context.md`.

### Manual Garmin-Style Health Metrics

- Batch-entry UI with one input per metric.
- Supports numeric and text values.
- Metrics include:
  - Sleep score.
  - Sleep duration.
  - HRV.
  - HRV status.
  - Resting HR.
  - VO2 max.
  - FTP.
  - Training Readiness.
  - Training Status.
  - Acute Load.
  - Load Ratio.
  - Load Focus.
  - Recovery Time.
  - Aerobic/Anaerobic Training Effect.
  - Endurance Score.
  - Hill Score.
  - Lactate threshold HR/pace/power.
  - Body Battery.
  - Stress.
  - Pulse Ox.
  - Respiration.
  - Body weight/body fat.
  - Heat/altitude acclimation.
  - Fatigue and R-CPD notes.
  - Custom metric type.

### Calendar / Planning

- Create planned workouts.
- Mark workouts completed or missed.
- Coach can propose workouts.
- Proposed workouts require approval before being applied.
- Workouts now support sport variants, surface, location suggestion, and gear suggestion.

### Coach

- Uses Ollama when available.
- Falls back to rule-based coaching when Ollama is unavailable.
- Structured JSON response validation through Pydantic.
- Uses:
  - Profile.
  - Recent activities.
  - Health metrics.
  - Planned workouts.
  - Schedule constraints.
  - Memories.
  - Places.
  - Feedback.
  - Gear.

### Ollama Integration

- App can check Ollama status.
- App can attempt to start Ollama:
  - macOS: `open -a Ollama`.
  - Other systems: `ollama serve` if binary exists.
- Default configured model:
  - `gpt-oss:20b`.
- Default embedding model:
  - `embeddinggemma`.
- Pull commands are displayed in the UI.

### Strava

- OAuth URL generation.
- OAuth callback token exchange.
- Token refresh.
- Activity sync.
- Webhook verification/event endpoint.
- Gear sync endpoint.
- Strava activity import preserves:
  - Sport.
  - Sport variant.
  - Gear ID.
  - Distance/elevation/HR/power/calories/raw payload.

### Garmin

- Official API adapter status placeholder.
- Local file import directory:
  - `./garmin_files`.
- Startup scan.
- Manual scan UI.
- Supported import formats:
  - `.csv`
  - `.tcx`
  - `.gpx`
  - `.fit`
- FIT parsing uses `fitdecode`.

### Places / Route Suggestions

- Local place library.
- Default training base: Newport Beach.
- User can add run/ride/swim locations.
- Each place can store:
  - Name.
  - Sport.
  - Sport variant.
  - Surface.
  - Tags.
  - Notes.
  - Safety notes.
  - Optional link.
- User can add feedback:
  - Location.
  - Date.
  - Intended stimulus.
  - Rating 1-5.
  - Notes.
  - Optional linked workout/activity.
- Coach receives ranked location suggestions.

### Gear

- User can manually add shoes/bikes.
- Strava gear sync can import gear inventory/mileage.
- Gear stores:
  - Name.
  - Type.
  - Strava gear ID.
  - Mileage.
  - Retirement mileage.
  - Preferred sport variants.
  - Preferred surfaces.
  - Notes.
  - Source.
- Coach can use gear context to suggest shoes/bike for workouts.
- App does not automatically update Strava gear.

### Trail / Gravel / MTB

- Sport variants support:
  - `trail_run`
  - `gravel_ride`
  - `mtb_ride`
- Coach instruction:
  - Use these as controlled aerobic/endurance substitutions when they preserve the intended triathlon stimulus.
  - Do not replace race-specific TT/brick/threshold sessions unless appropriate.

## Current Runtime State

- Backend should run with:
  ```bash
  uvicorn app.main:app --app-dir backend --port 8000
  ```

- Frontend should run with:
  ```bash
  cd frontend
  npm run dev -- --port 5173
  ```

- App URL:
  ```text
  http://localhost:5173
  ```

- Backend URL:
  ```text
  http://127.0.0.1:8000
  ```

- Backend tests last passed:
  ```text
  6 passed
  ```

- Frontend build last passed.

## Ollama Status Notes

- Ollama had been started successfully.
- Installed models detected earlier:
  - `gemma4:e4b`
  - `gemma4:26b`
  - `llama3.1:latest`
- Recommended downloads were started but incomplete due to slow connection:
  - `gpt-oss:20b`
  - `embeddinggemma`
- User plans to resume later with better internet.

Check models with:

```bash
ollama list
```

Resume downloads with:

```bash
ollama pull gpt-oss:20b
ollama pull embeddinggemma
```

## Strava Setup Notes

- `.env` should live at repo root:
  ```text
  /Users/caysonhamilton/personal-projects/ai_coach/.env
  ```

- Important fields:
  ```env
  STRAVA_CLIENT_ID=
  STRAVA_CLIENT_SECRET=
  STRAVA_REDIRECT_URI=http://localhost:8000/api/connectors/strava/callback
  STRAVA_VERIFY_TOKEN=local-dev-token
  ```

- After editing `.env`, restart backend.

## Important Implementation Notes

- This project is not currently a git repo.
- `.env`, `ai_coach.db`, `coach_context.md`, `garmin_files/`, frontend build/dependencies, and Python caches are ignored.
- A lightweight SQLite migration shim was added for new columns, but there is no full Alembic migration setup yet.
- The frontend is currently a single large `main.tsx`; future refactor should split panels into components.
- Current UI is functional, not yet polished into a full multi-page app.
- Strava gear sync requires a connected Strava OAuth account.
- Location suggestions depend on manually entered places and feedback first.
- External route discovery/map integration has not been implemented yet.
- Atlas browser automation is not suitable for downloading Garmin files or moving them locally because official Atlas Agent limitations include no file download and no filesystem access.

## Recommended Next Steps

1. Finish Ollama downloads when internet is better:
   ```bash
   ollama pull gpt-oss:20b
   ollama pull embeddinggemma
   ```

2. Configure Strava `.env`, restart backend, connect Strava, then run:
   - Sync Activities.
   - Sync Gear.

3. Add initial Newport places:
   - Road run routes.
   - Trail run routes.
   - Road ride loops.
   - Gravel ride options.
   - Pool/open-water swim locations.

4. Add initial gear rules:
   - Road shoes.
   - Trail shoes.
   - TT/tri bike.
   - Road/gravel bike.
   - MTB if applicable.

5. Add 3-5 recent workout feedback entries so the coach has meaningful place preferences.

6. Ask the coach:
   ```text
   Plan my next training week. Include one trail or gravel aerobic session if it preserves the triathlon stimulus. Suggest locations and gear for each workout.
   ```

7. Future engineering improvements:
   - Split React panels into separate files.
   - Add Alembic migrations.
   - Add edit/delete endpoints for places/gear/feedback.
   - Add better route metadata fields.
   - Add Strava activity detail/stream fetching.
   - Add richer gear rotation rules.
   - Add map or route-link integration.
