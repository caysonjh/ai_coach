# AI Coach Session Summary - 2026-04-30

## High-Level Summary

This session moved the app away from Ollama as the primary coach engine and toward a ChatGPT-native workflow that uses the user’s Plus subscription for reasoning while keeping this repo focused on grounded context, persistence, and write-back actions. The backend was refactored to expose ChatGPT action endpoints, a trimmed OpenAPI document for Custom GPT import, a production Docker image, and a local push-sync path so local edits can be mirrored into the remote backend that ChatGPT reads from.

By the end of the session, the app had:

- ChatGPT action endpoints for coach context, result recording, workout application, and sync apply.
- A trimmed OpenAPI export suitable for Custom GPT import.
- Auth handling for public action calls.
- A Dockerfile and deployment docs for hosting the backend publicly.
- A local push-sync flow so the local app can send its latest training data to the remote backend.
- Passing backend tests and frontend build checks after the schema and sync refactors.

## Prompt / Response Timeline

1. **Why the coach was repeating the same response**
   - User reported that the AI coach seemed to generate the same default response to any query.
   - Assistant traced the request path through `backend/app/services/coach.py` and `backend/app/services/ollama.py`, identified the silent `None` fallback, and explained that:
     - Ollama failures were swallowed.
     - Non-analysis requests fell back to a canned weekly training plan.
     - The frontend explicitly surfaced the fallback state.

2. **Whether to stay local or move to cloud**
   - User asked whether to continue with local Ollama or move to a cloud-hosted model.
   - Assistant recommended a cloud-hosted model for the main coach experience, while noting that ChatGPT Plus itself is not API access.
   - User clarified that they wanted to use their ChatGPT Plus subscription if possible.
   - Assistant explained that Plus cannot be used directly as an app backend and redirected the plan toward a ChatGPT-native workflow.

3. **Choosing the ChatGPT-native direction**
   - User selected:
     - ChatGPT-native assistant.
     - Custom GPT with actions.
     - Public HTTPS backend.
   - Assistant produced a proposed plan centered on:
     - A public backend.
     - Custom GPT action import.
     - Grounded context and write-back endpoints.
     - Persisting approved plans.

4. **Implementing the ChatGPT action backend**
   - User asked to implement the plan.
   - Assistant refactored the backend and UI to support ChatGPT actions:
     - Added config for `CHATGPT_PUBLIC_BASE_URL` and `CHATGPT_ACTION_TOKEN`.
     - Added action endpoints:
       - `POST /api/chatgpt/context`
       - `POST /api/chatgpt/record`
       - `GET /api/chatgpt/status`
     - Added a trimmed action OpenAPI export.
     - Replaced the UI Ollama panel with a ChatGPT Actions panel.
     - Added tests for the new action contract.
   - Assistant also added a production `Dockerfile`, a smoke test script, and `docs/chatgpt-actions.md` so the repo described the deployment/import flow.

5. **Preparing instructions for the Custom GPT**
   - User asked for Instructions text for the Custom GPT model.
   - Assistant wrote a prompt for a precise triathlon coach that:
     - Always grounds responses in the action context.
     - Analyzes training history when asked.
     - Plans only when planning is requested.
     - Uses the record/apply actions after producing a plan.

6. **Fixing the action import schema**
   - User reported Custom GPT importer errors:
     - Raw array request body on `/api/coach/apply-workouts`.
     - Multiple security schemes.
   - Assistant refactored the OpenAPI surface:
     - Wrapped workout application in an object request schema.
     - Added a matching object response schema.
     - Trimmed the exported OpenAPI doc to one bearer security scheme.
     - Added a ChatGPT-facing `/api/chatgpt/apply-workouts` alias.
   - Backend tests and frontend build passed after the fix.
   - The updated spec was pushed to GitHub so the user could re-import it.

7. **Why ChatGPT saw zero activities**
   - User connected the Custom GPT successfully but it reported zero activities in current training context while the local frontend showed the correct data.
   - Assistant explained the likely cause:
     - The local app and the public ChatGPT backend were using different databases.
     - The context endpoint only reads the remote backend’s DB.
   - Assistant clarified that a GET endpoint cannot push local changes to remote by itself.

8. **Implementing sync from local to remote**
   - User asked to implement a sync mechanism.
   - Assistant added:
     - `CHATGPT_SYNC_TARGET_URL`
     - `CHATGPT_SYNC_TARGET_TOKEN`
     - A full training snapshot builder.
     - A remote apply endpoint:
       - `POST /api/chatgpt/sync`
     - A local push endpoint:
       - `POST /api/sync/chatgpt/push`
     - A frontend button to push local changes to the remote backend.
   - The sync covers:
     - Athlete profile.
     - Activities.
     - Health metrics.
     - Planned workouts.
     - Schedule constraints.
     - Training locations.
     - Location feedback.
     - Gear.
   - After a serialization issue was discovered in tests, the importer was updated to use `model_validate(...)` so ISO timestamps were correctly converted back into Python datetime objects.
   - Backend tests and frontend build passed again after the fix.

9. **Pushing updates to GitHub**
   - User requested Git pushes after the major implementation and again after the schema fix.
   - Assistant staged only the intended files, left the pre-existing `me.md` worktree change alone, committed the changes, and pushed them to `origin/main`.

10. **Backend state discrepancy troubleshooting**
    - User asked why the GPT still saw no activities even though the local frontend showed the correct ones.
    - Assistant explained the separation between:
      - Local SQLite / local backend.
      - Public ChatGPT backend.
    - Assistant then explained that syncing requires an explicit push or a shared persistent DB, not a GET trigger.

11. **Current session log request**
    - User asked for a markdown log of the prompts, responses, and other info from this recent session, modeled after the prior summary file.
    - This file records the work from the point where the app was already built and the ChatGPT migration began.

## Created / Updated Files

### Root

- `README.md`
  - Updated to describe the ChatGPT-native workflow, Docker deployment, sync settings, and the action import path.

- `.env.example`
  - Added ChatGPT action and sync settings:
    - `CHATGPT_PUBLIC_BASE_URL`
    - `CHATGPT_ACTION_TOKEN`
    - `CHATGPT_SYNC_TARGET_URL`
    - `CHATGPT_SYNC_TARGET_TOKEN`

- `Dockerfile`
  - Production container for the backend.

- `SESSION_SUMMARY_2026-04-30.md`
  - This session log.

### Backend

- `backend/app/core/config.py`
  - Added ChatGPT action and sync config fields.

- `backend/app/schemas/api.py`
  - Added:
    - `CoachActionEndpoint`
    - `CoachContextResponse`
    - `CoachRecordRequest`
    - `CoachRecordResponse`
    - `CoachApplyWorkoutsRequest`
    - `CoachApplyWorkoutsResponse`
    - `ChatGPTActionsStatus`
    - `ChatGPTSyncSnapshot`
    - `ChatGPTSyncSummary`
    - `ChatGPTSyncPushRequest`
    - `ChatGPTSyncPushResponse`

- `backend/app/api/routes.py`
  - Added ChatGPT action endpoints.
  - Added trimmed action OpenAPI export.
  - Added remote snapshot apply endpoint.
  - Added local push-sync endpoint.

- `backend/app/services/coach.py`
  - Refactored into workspace/context-building methods.
  - Added action endpoint metadata.
  - Added local preview output and record persistence behavior.

- `backend/app/services/chatgpt_sync.py`
  - New sync service that builds and applies mirrored training snapshots.

- `backend/tests/test_chatgpt_actions.py`
  - Added coverage for:
    - context response structure,
    - record persistence,
    - auth guard,
    - trimmed OpenAPI output,
    - snapshot round-trip sync.

### Frontend

- `frontend/src/lib/api.ts`
  - Added ChatGPT action and sync types.
  - Updated `applyWorkouts` to match the new object body.

- `frontend/src/main.tsx`
  - Replaced Ollama-centric status UI with ChatGPT Actions status and push-sync controls.

### Docs / Scripts

- `docs/chatgpt-actions.md`
  - Added import, deployment, and smoke-test guidance.

- `scripts/chatgpt_smoke_test.sh`
  - Added a local verification script for the action surface.

## Verification

The following checks passed after the refactors:

- `python -m pytest backend/tests/test_chatgpt_actions.py backend/tests/test_coach_behavior.py backend/tests/test_state_export.py backend/tests/test_recommendations.py backend/tests/test_imports.py`
- `python -m compileall backend/app backend/tests`
- `npm run build` in `frontend/`

## Notes

- The `me.md` symlink/type change remained in the worktree and was not touched.
- The remote GPT can only see local changes after they are pushed through the sync path or written into the same hosted database.
- The trimmed action spec remains available at `GET /api/chatgpt/openapi.json`.
