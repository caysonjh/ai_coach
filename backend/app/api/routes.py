from datetime import date, datetime, time, timedelta

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
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
from app.services.coach import CoachService
from app.services.garmin_files import scan_garmin_directory
from app.services.imports import parse_activity_csv
from app.services.metrics import metric_options
from app.services.ollama import OllamaClient, OllamaStatus
from app.services.state_export import export_coach_context

router = APIRouter(prefix="/api")


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
def scan_garmin_files(session: Session = Depends(get_session)) -> GarminImportStatus:
    return scan_garmin_directory(session)


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
    session: Session = Depends(get_session),
) -> TrainingLocation:
    location = TrainingLocation(**payload.model_dump())
    session.add(location)
    session.commit()
    session.refresh(location)
    return location


@router.get("/locations/feedback")
def list_location_feedback(session: Session = Depends(get_session)) -> list[WorkoutLocationFeedback]:
    return session.exec(
        select(WorkoutLocationFeedback).order_by(WorkoutLocationFeedback.feedback_date.desc()).limit(100)
    ).all()


@router.post("/locations/feedback", response_model=WorkoutLocationFeedback)
def create_location_feedback(
    payload: WorkoutLocationFeedbackCreate,
    session: Session = Depends(get_session),
) -> WorkoutLocationFeedback:
    feedback = WorkoutLocationFeedback(**payload.model_dump())
    session.add(feedback)
    session.commit()
    session.refresh(feedback)
    return feedback


@router.get("/gear")
def list_gear(session: Session = Depends(get_session)) -> list[GearItem]:
    return session.exec(select(GearItem).order_by(GearItem.gear_type.asc(), GearItem.name.asc())).all()


@router.post("/gear", response_model=GearItem)
def create_gear(payload: GearItemCreate, session: Session = Depends(get_session)) -> GearItem:
    gear = GearItem(**payload.model_dump())
    session.add(gear)
    session.commit()
    session.refresh(gear)
    return gear


@router.post("/activities", response_model=Activity)
def create_activity(payload: ActivityCreate, session: Session = Depends(get_session)) -> Activity:
    activity = Activity(**payload.model_dump())
    session.add(activity)
    session.commit()
    session.refresh(activity)
    return activity


@router.post("/activities/import/csv")
async def import_activities_csv(
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
) -> dict:
    content = (await file.read()).decode("utf-8")
    activities = parse_activity_csv(content)
    for activity in activities:
        session.add(activity)
    session.commit()
    return {"imported": len(activities)}


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
def create_metric(payload: HealthMetricCreate, session: Session = Depends(get_session)) -> HealthMetric:
    metric = HealthMetric(**payload.model_dump())
    session.add(metric)
    session.commit()
    session.refresh(metric)
    return metric


@router.get("/calendar/workouts")
def list_workouts(session: Session = Depends(get_session)) -> list[PlannedWorkout]:
    return session.exec(select(PlannedWorkout).order_by(PlannedWorkout.planned_date.asc())).all()


@router.post("/calendar/workouts", response_model=PlannedWorkout)
def create_workout(
    payload: PlannedWorkoutCreate,
    session: Session = Depends(get_session),
) -> PlannedWorkout:
    workout = PlannedWorkout(**payload.model_dump())
    session.add(workout)
    session.commit()
    session.refresh(workout)
    return workout


@router.patch("/calendar/workouts/{workout_id}", response_model=PlannedWorkout)
def update_workout(
    workout_id: int,
    payload: dict,
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
    return workout


@router.post("/calendar/constraints", response_model=ScheduleConstraint)
def create_constraint(
    payload: ScheduleConstraintCreate,
    session: Session = Depends(get_session),
) -> ScheduleConstraint:
    constraint = ScheduleConstraint(**payload.model_dump())
    session.add(constraint)
    session.commit()
    session.refresh(constraint)
    return constraint


@router.post("/coach", response_model=CoachResponse)
async def coach(payload: CoachRequest, session: Session = Depends(get_session)) -> CoachResponse:
    return await CoachService().respond(session, payload)


@router.post("/coach/apply-workouts")
def apply_workouts(
    payload: list[PlannedWorkoutCreate],
    session: Session = Depends(get_session),
) -> dict:
    for item in payload:
        session.add(PlannedWorkout(**item.model_dump()))
    session.commit()
    return {"applied": len(payload)}


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
async def strava_sync(session: Session = Depends(get_session)) -> dict:
    account = session.exec(select(OAuthAccount).where(OAuthAccount.provider == "strava")).first()
    if not account:
        raise HTTPException(status_code=400, detail="Strava is not connected")
    imported = await StravaConnector().sync_recent_activities(session, account)
    return {"imported": imported}


@router.post("/connectors/strava/sync-gear")
async def strava_sync_gear(session: Session = Depends(get_session)) -> dict:
    account = session.exec(select(OAuthAccount).where(OAuthAccount.provider == "strava")).first()
    if not account:
        raise HTTPException(status_code=400, detail="Strava is not connected")
    synced = await StravaConnector().sync_gear(session, account)
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
