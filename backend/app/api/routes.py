from datetime import date, datetime, time, timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, UploadFile
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from sqlmodel import Session, select

from app.connectors.garmin import garmin_status
from app.connectors.strava import StravaConnector
from app.core.config import get_settings
from app.db.session import get_session
from app.models.entities import (
    Activity,
    AthleteProfile,
    GearItem,
    HealthMetric,
    OAuthAccount,
    PlannedWorkout,
    ScheduleConstraint,
    TrainingLocation,
    WorkoutLocationFeedback,
)
from app.schemas.api import (
    ActivityCreate,
    CoachRequest,
    CoachResponse,
    CoachContextResponse,
    ChatGPTSyncSnapshot,
    ChatGPTSyncSummary,
    ChatGPTSyncPushRequest,
    ChatGPTSyncPushResponse,
    CoachRecordRequest,
    CoachRecordResponse,
    CoachApplyWorkoutsRequest,
    CoachApplyWorkoutsResponse,
    ChatGPTActionsStatus,
    ContextExportResponse,
    GarminImportStatus,
    GearItemCreate,
    HealthMetricCreate,
    ModelRecommendation,
    PlannedWorkoutCreate,
    ScheduleConstraintCreate,
    SettingsResponse,
    TrainingLocationCreate,
    WorkoutLocationFeedbackCreate,
)
from app.services.analytics import summarize_training
from app.services.activity_dedupe import upsert_activity
from app.services.chatgpt_sync import (
    apply_chatgpt_sync_snapshot,
    build_chatgpt_sync_snapshot,
    push_chatgpt_sync,
    push_chatgpt_sync_sync,
)
from app.services.coach import CoachService
from app.services.garmin_files import scan_garmin_directory
from app.services.imports import parse_activity_csv
from app.services.metrics import metric_options
from app.services.ollama import OllamaClient, OllamaStatus
from app.services.state_export import export_coach_context

router = APIRouter(prefix="/api")
chatgpt_bearer = HTTPBearer(auto_error=False)


def require_chatgpt_token(credentials: HTTPAuthorizationCredentials | None = Depends(chatgpt_bearer)) -> None:
    settings = get_settings()
    expected = settings.chatgpt_action_token.strip()
    if not expected:
        return
    if not credentials or credentials.scheme.lower() != "bearer" or credentials.credentials != expected:
        raise HTTPException(status_code=401, detail="Invalid ChatGPT action token")


def _queue_chatgpt_sync(background_tasks: BackgroundTasks, session: Session) -> None:
    settings = get_settings()
    remote_base_url = settings.chatgpt_sync_target_url.strip()
    if not remote_base_url:
        return
    background_tasks.add_task(
        push_chatgpt_sync_sync,
        build_chatgpt_sync_snapshot(session),
        remote_base_url,
        settings.chatgpt_sync_target_token,
    )


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/settings", response_model=SettingsResponse)
def settings() -> SettingsResponse:
    current = get_settings()
    return SettingsResponse(
        app_name=current.app_name,
        ollama_base_url=current.ollama_base_url,
        ollama_model=current.ollama_model,
        ollama_embed_model=current.ollama_embed_model,
        garmin_non_official_enabled=current.garmin_non_official_enabled,
        strava_configured=bool(current.strava_client_id and current.strava_client_secret),
    )


@router.get("/ollama/status", response_model=OllamaStatus)
async def ollama_status() -> OllamaStatus:
    return await OllamaClient().status()


@router.post("/ollama/ensure", response_model=OllamaStatus)
async def ollama_ensure() -> OllamaStatus:
    return await OllamaClient().ensure_running()


@router.get("/ollama/recommendation", response_model=ModelRecommendation)
def ollama_recommendation() -> ModelRecommendation:
    return ModelRecommendation(
        recommended="llama3.1:latest",
        rationale=(
            "Best reliable default for a 16 GB Apple Silicon laptop in this app. It is fast "
            "enough for interactive testing, supports structured JSON well enough for the coach, "
            "and avoids the local runner crashes seen with larger models on constrained memory."
        ),
        alternatives=[
            {
                "model": "qwen3:8b",
                "use_case": "Faster, lighter fallback if gpt-oss:20b is too slow.",
            },
            {
                "model": "gemma4:e4b",
                "use_case": "Installed local alternative worth testing for coaching tone and speed.",
            },
            {
                "model": "gpt-oss:20b",
                "use_case": "Higher-reasoning target, but likely too heavy for stable 16 GB laptop use.",
            },
            {
                "model": "gpt-oss:120b",
                "use_case": "Not recommended on this machine; requires much larger memory headroom.",
            },
        ],
    )


@router.get("/profile")
def profile(session: Session = Depends(get_session)) -> AthleteProfile | dict:
    profile_row = session.exec(select(AthleteProfile).limit(1)).first()
    return profile_row or {}


@router.get("/dashboard")
def dashboard(session: Session = Depends(get_session)) -> dict:
    today = date.today()
    since = today - timedelta(days=56)
    activities = session.exec(
        select(Activity).where(Activity.start_time >= datetime.combine(since, time.min))
    ).all()
    metrics = session.exec(select(HealthMetric).where(HealthMetric.metric_date >= since)).all()
    planned = session.exec(select(PlannedWorkout).where(PlannedWorkout.planned_date >= since)).all()
    return summarize_training(activities, metrics, planned, today=today)


@router.post("/garmin-files/scan", response_model=GarminImportStatus)
def scan_garmin_files(
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
) -> GarminImportStatus:
    result = scan_garmin_directory(session)
    _queue_chatgpt_sync(background_tasks, session)
    return result


@router.get("/garmin-files/status", response_model=GarminImportStatus)
def garmin_files_status(session: Session = Depends(get_session)) -> GarminImportStatus:
    return scan_garmin_directory(session)


@router.post("/coach/context/export", response_model=ContextExportResponse)
def export_context(session: Session = Depends(get_session)) -> ContextExportResponse:
    path, bytes_written = export_coach_context(session)
    return ContextExportResponse(
        path=str(path),
        bytes_written=bytes_written,
        message="Coach context snapshot exported.",
    )


@router.get("/activities")
def list_activities(
    limit: int = Query(default=50, le=500),
    session: Session = Depends(get_session),
) -> list[Activity]:
    return session.exec(select(Activity).order_by(Activity.start_time.desc()).limit(limit)).all()


@router.get("/locations")
def list_locations(session: Session = Depends(get_session)) -> list[TrainingLocation]:
    return session.exec(select(TrainingLocation).order_by(TrainingLocation.name.asc())).all()


@router.post("/locations", response_model=TrainingLocation)
def create_location(
    payload: TrainingLocationCreate,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
) -> TrainingLocation:
    location = TrainingLocation(**payload.model_dump())
    session.add(location)
    session.commit()
    session.refresh(location)
    _queue_chatgpt_sync(background_tasks, session)
    return location


@router.get("/locations/feedback")
def list_location_feedback(session: Session = Depends(get_session)) -> list[WorkoutLocationFeedback]:
    return session.exec(
        select(WorkoutLocationFeedback).order_by(WorkoutLocationFeedback.feedback_date.desc()).limit(100)
    ).all()


@router.post("/locations/feedback", response_model=WorkoutLocationFeedback)
def create_location_feedback(
    payload: WorkoutLocationFeedbackCreate,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
) -> WorkoutLocationFeedback:
    feedback = WorkoutLocationFeedback(**payload.model_dump())
    session.add(feedback)
    session.commit()
    session.refresh(feedback)
    _queue_chatgpt_sync(background_tasks, session)
    return feedback


@router.get("/gear")
def list_gear(session: Session = Depends(get_session)) -> list[GearItem]:
    return session.exec(select(GearItem).order_by(GearItem.gear_type.asc(), GearItem.name.asc())).all()


@router.post("/gear", response_model=GearItem)
def create_gear(
    payload: GearItemCreate,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
) -> GearItem:
    gear = GearItem(**payload.model_dump())
    session.add(gear)
    session.commit()
    session.refresh(gear)
    _queue_chatgpt_sync(background_tasks, session)
    return gear


@router.post("/activities", response_model=Activity)
def create_activity(
    payload: ActivityCreate,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
) -> Activity:
    activity = Activity(**payload.model_dump())
    activity, _ = upsert_activity(session, activity)
    session.commit()
    session.refresh(activity)
    _queue_chatgpt_sync(background_tasks, session)
    return activity


@router.post("/activities/import/csv")
async def import_activities_csv(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
) -> dict:
    content = (await file.read()).decode("utf-8")
    activities = parse_activity_csv(content)
    imported = 0
    for activity in activities:
        _, created = upsert_activity(session, activity)
        if created:
            imported += 1
    session.commit()
    _queue_chatgpt_sync(background_tasks, session)
    return {"imported": imported, "merged": len(activities) - imported}


@router.get("/metrics/options")
def metric_option_list() -> list[dict[str, str]]:
    return metric_options()


@router.get("/metrics")
def list_metrics(
    limit: int = Query(default=100, le=1000),
    session: Session = Depends(get_session),
) -> list[HealthMetric]:
    return session.exec(select(HealthMetric).order_by(HealthMetric.metric_date.desc()).limit(limit)).all()


@router.post("/metrics", response_model=HealthMetric)
def create_metric(
    payload: HealthMetricCreate,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
) -> HealthMetric:
    metric = HealthMetric(**payload.model_dump())
    session.add(metric)
    session.commit()
    session.refresh(metric)
    _queue_chatgpt_sync(background_tasks, session)
    return metric


@router.get("/calendar/workouts")
def list_workouts(session: Session = Depends(get_session)) -> list[PlannedWorkout]:
    return session.exec(select(PlannedWorkout).order_by(PlannedWorkout.planned_date.asc())).all()


@router.post("/calendar/workouts", response_model=PlannedWorkout)
def create_workout(
    payload: PlannedWorkoutCreate,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
) -> PlannedWorkout:
    workout = PlannedWorkout(**payload.model_dump())
    session.add(workout)
    session.commit()
    session.refresh(workout)
    _queue_chatgpt_sync(background_tasks, session)
    return workout


@router.patch("/calendar/workouts/{workout_id}", response_model=PlannedWorkout)
def update_workout(
    workout_id: int,
    payload: dict,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
) -> PlannedWorkout:
    workout = session.get(PlannedWorkout, workout_id)
    if not workout:
        raise HTTPException(status_code=404, detail="Workout not found")
    for key, value in payload.items():
        if hasattr(workout, key):
            setattr(workout, key, value)
    session.add(workout)
    session.commit()
    session.refresh(workout)
    _queue_chatgpt_sync(background_tasks, session)
    return workout


@router.post("/calendar/constraints", response_model=ScheduleConstraint)
def create_constraint(
    payload: ScheduleConstraintCreate,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
) -> ScheduleConstraint:
    constraint = ScheduleConstraint(**payload.model_dump())
    session.add(constraint)
    session.commit()
    session.refresh(constraint)
    _queue_chatgpt_sync(background_tasks, session)
    return constraint


@router.post("/coach", response_model=CoachResponse)
async def coach(
    payload: CoachRequest,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
) -> CoachResponse:
    response = await CoachService().respond(session, payload)
    _queue_chatgpt_sync(background_tasks, session)
    return response


@router.get("/chatgpt/status", response_model=ChatGPTActionsStatus)
def chatgpt_status() -> ChatGPTActionsStatus:
    """Describe the public ChatGPT action setup expected for this backend."""
    settings = get_settings()
    enabled = bool(settings.chatgpt_action_token.strip())
    base_url = settings.chatgpt_public_base_url.rstrip("/")
    sync_target = settings.chatgpt_sync_target_url.rstrip("/")
    return ChatGPTActionsStatus(
        enabled=enabled,
        auth_required=enabled,
        public_base_url=settings.chatgpt_public_base_url,
        openapi_url=f"{base_url}/openapi.json" if base_url else "/openapi.json",
        actions_openapi_url=f"{base_url}/api/chatgpt/openapi.json" if base_url else "/api/chatgpt/openapi.json",
        context_path="/api/chatgpt/context",
        record_path="/api/chatgpt/record",
        apply_workouts_path="/api/chatgpt/apply-workouts",
        sync_push_path="/api/sync/chatgpt/push",
        sync_target_configured=bool(sync_target),
        sync_target_url=settings.chatgpt_sync_target_url,
    )


@router.get("/chatgpt/openapi.json")
def chatgpt_openapi() -> JSONResponse:
    """Return a trimmed OpenAPI document for ChatGPT action import."""
    settings = get_settings()
    spec = get_openapi(
        title="AI Coach ChatGPT Actions",
        version="0.1.0",
        routes=[
            route
            for route in router.routes
            if getattr(route, "path", "").startswith("/api/chatgpt")
            and getattr(route, "path", "") != "/api/chatgpt/sync"
        ],
    )
    spec["servers"] = [{"url": settings.chatgpt_public_base_url.rstrip("/") or "http://localhost:8000"}]
    spec["paths"] = {
        path: operations
        for path, operations in spec["paths"].items()
        if path
        in {
            "/api/chatgpt/context",
            "/api/chatgpt/record",
            "/api/chatgpt/apply-workouts",
            "/api/chatgpt/sync",
            "/api/chatgpt/status",
            "/api/chatgpt/openapi.json",
        }
    }
    spec.setdefault("components", {})["securitySchemes"] = {
        "bearerAuth": {"type": "http", "scheme": "bearer"}
    }
    for path in ("/api/chatgpt/context", "/api/chatgpt/record", "/api/chatgpt/apply-workouts"):
        if path in spec["paths"]:
            for operation in spec["paths"][path].values():
                operation.setdefault("security", [{"bearerAuth": []}])
    return JSONResponse(spec)


@router.post("/chatgpt/context", response_model=CoachContextResponse, dependencies=[Depends(require_chatgpt_token)])
def chatgpt_context(payload: CoachRequest, session: Session = Depends(get_session)) -> CoachContextResponse:
    """Return grounded coach context for a ChatGPT action call."""
    return CoachService().build_context(session, payload)


@router.post("/chatgpt/record", response_model=CoachRecordResponse, dependencies=[Depends(require_chatgpt_token)])
def chatgpt_record(
    payload: CoachRecordRequest,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
) -> CoachRecordResponse:
    """Persist a ChatGPT-authored coach response and optional approved workouts."""
    response = CoachService().record_coach_result(session, payload)
    _queue_chatgpt_sync(background_tasks, session)
    return response


@router.post("/chatgpt/sync", response_model=ChatGPTSyncSummary, dependencies=[Depends(require_chatgpt_token)])
def chatgpt_sync(payload: ChatGPTSyncSnapshot, session: Session = Depends(get_session)) -> ChatGPTSyncSummary:
    """Apply a training snapshot from the local app into the ChatGPT backend."""
    return apply_chatgpt_sync_snapshot(session, payload)


@router.post("/sync/chatgpt/push", response_model=ChatGPTSyncPushResponse)
async def push_chatgpt_sync_snapshot(
    payload: ChatGPTSyncPushRequest | None = None,
    session: Session = Depends(get_session),
) -> ChatGPTSyncPushResponse:
    settings = get_settings()
    remote_base_url = (payload.remote_base_url if payload and payload.remote_base_url else settings.chatgpt_sync_target_url).strip()
    remote_token = payload.remote_token if payload and payload.remote_token is not None else settings.chatgpt_sync_target_token
    if not remote_base_url:
        raise HTTPException(status_code=400, detail="No ChatGPT sync target URL configured")

    try:
        summary = await push_chatgpt_sync(build_chatgpt_sync_snapshot(session), remote_base_url, remote_token)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"ChatGPT sync push failed: {exc}") from exc
    return ChatGPTSyncPushResponse(
        remote_base_url=remote_base_url,
        pushed=True,
        summary=summary,
        message="Local training state pushed to the ChatGPT backend.",
    )


@router.post("/coach/apply-workouts", response_model=CoachApplyWorkoutsResponse)
@router.post("/chatgpt/apply-workouts", response_model=CoachApplyWorkoutsResponse)
def apply_workouts(
    payload: CoachApplyWorkoutsRequest,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
) -> CoachApplyWorkoutsResponse:
    for item in payload.workouts:
        session.add(PlannedWorkout(**item.model_dump()))
    session.commit()
    _queue_chatgpt_sync(background_tasks, session)
    return CoachApplyWorkoutsResponse(applied=len(payload.workouts))


@router.get("/connectors/garmin/status")
def get_garmin_status() -> dict:
    return garmin_status().__dict__


@router.get("/connectors/strava/auth-url")
def strava_auth_url() -> dict:
    connector = StravaConnector()
    if not get_settings().strava_client_id:
        return {"configured": False, "url": None}
    return {"configured": True, "url": connector.authorization_url()}


@router.get("/connectors/strava/callback")
async def strava_callback(code: str, session: Session = Depends(get_session)) -> dict:
    account = await StravaConnector().exchange_code(session, code)
    return {"connected": True, "athlete_id": account.athlete_id}


@router.post("/connectors/strava/sync")
async def strava_sync(
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
) -> dict:
    account = session.exec(select(OAuthAccount).where(OAuthAccount.provider == "strava")).first()
    if not account:
        raise HTTPException(status_code=400, detail="Strava is not connected")
    imported = await StravaConnector().sync_recent_activities(session, account)
    _queue_chatgpt_sync(background_tasks, session)
    return {"imported": imported}


@router.post("/connectors/strava/sync-gear")
async def strava_sync_gear(
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
) -> dict:
    account = session.exec(select(OAuthAccount).where(OAuthAccount.provider == "strava")).first()
    if not account:
        raise HTTPException(status_code=400, detail="Strava is not connected")
    synced = await StravaConnector().sync_gear(session, account)
    _queue_chatgpt_sync(background_tasks, session)
    return {"synced": synced}


@router.get("/connectors/strava/webhook")
def strava_webhook_verify(
    hub_mode: str = Query(alias="hub.mode"),
    hub_challenge: str = Query(alias="hub.challenge"),
    hub_verify_token: str = Query(alias="hub.verify_token"),
) -> dict:
    settings = get_settings()
    if hub_mode == "subscribe" and hub_verify_token == settings.strava_verify_token:
        return {"hub.challenge": hub_challenge}
    raise HTTPException(status_code=403, detail="Invalid Strava webhook verification")


@router.post("/connectors/strava/webhook")
def strava_webhook_event(payload: dict) -> dict:
    return {"received": True, "event": payload}
