from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field

from app.models.entities import GearType, MetricType, Source, Sport, SportVariant, WorkoutStatus


class ActivityCreate(BaseModel):
    source: Source = Source.manual
    source_id: str | None = None
    sport: Sport
    sport_variant: SportVariant = SportVariant.other
    gear_id: str | None = None
    name: str
    start_time: datetime
    duration_seconds: int
    distance_meters: float | None = None
    elevation_meters: float | None = None
    avg_hr: float | None = None
    max_hr: float | None = None
    avg_power: float | None = None
    max_power: float | None = None
    avg_pace_seconds_per_km: float | None = None
    calories: float | None = None
    perceived_effort: int | None = Field(default=None, ge=1, le=10)
    training_effect: float | None = None
    notes: str = ""
    raw_payload: dict[str, Any] = {}


class HealthMetricCreate(BaseModel):
    metric_date: date
    metric_type: MetricType
    custom_name: str | None = None
    value_num: float | None = None
    value_text: str | None = None
    unit: str | None = None
    source: Source = Source.manual
    confidence: float = Field(default=1.0, ge=0, le=1)
    notes: str = ""


class PlannedWorkoutCreate(BaseModel):
    planned_date: date
    sport: Sport
    sport_variant: SportVariant = SportVariant.other
    title: str
    description: str = ""
    duration_minutes: int | None = None
    distance_meters: float | None = None
    intensity: str = "easy"
    surface: str | None = None
    location_suggestion: str | None = None
    gear_suggestion: str | None = None
    status: WorkoutStatus = WorkoutStatus.planned
    source: Source = Source.manual


class ScheduleConstraintCreate(BaseModel):
    constraint_date: date
    label: str
    available_minutes: int | None = None
    unavailable: bool = False
    notes: str = ""


class CoachChatMessage(BaseModel):
    role: str
    content: str


class CoachRequest(BaseModel):
    message: str
    conversation_history: list[CoachChatMessage] = Field(default_factory=list)
    week_start: date | None = None
    aggressiveness: float = Field(default=0.45, ge=0, le=1)
    autonomy: str = "suggest_then_approve"


class CoachResponse(BaseModel):
    title: str
    summary: str
    recommendations: list[str]
    risks: list[str]
    proposed_workouts: list[PlannedWorkoutCreate] = Field(default_factory=list)
    used_ollama: bool
    raw: dict[str, Any] = Field(default_factory=dict)


class CoachActionEndpoint(BaseModel):
    name: str
    method: str
    path: str
    purpose: str


class CoachContextResponse(BaseModel):
    generated_at: datetime
    current_date: date
    week_start: date
    request_intent: str
    effective_aggressiveness: float
    athlete_profile: dict[str, Any]
    athlete_profile_markdown: str
    training_summary: dict[str, Any]
    past_7_days_activity_digest: dict[str, Any]
    recent_activities: list[dict[str, Any]]
    recent_health_metrics: list[dict[str, Any]]
    planned_workouts: list[dict[str, Any]]
    schedule_constraints: list[dict[str, Any]]
    training_locations: list[dict[str, Any]]
    recent_location_feedback: list[dict[str, Any]]
    ranked_location_suggestions: dict[str, Any]
    gear: list[dict[str, Any]]
    memories: list[str]
    coach_guidance: list[str]
    action_endpoints: list[CoachActionEndpoint]


class CoachRecordRequest(BaseModel):
    source_message: str
    title: str
    summary: str
    recommendations: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    proposed_workouts: list[PlannedWorkoutCreate] = Field(default_factory=list)
    rationale: str = ""
    autonomy: str = "suggest_then_approve"
    aggressiveness: float = Field(default=0.45, ge=0, le=1)
    persist_workouts: bool = False


class CoachRecordResponse(BaseModel):
    saved_insight: bool
    saved_plan_version: bool
    applied_workouts: int
    message: str


class CoachApplyWorkoutsRequest(BaseModel):
    workouts: list[PlannedWorkoutCreate] = Field(default_factory=list)


class CoachApplyWorkoutsResponse(BaseModel):
    applied: int


class ChatGPTActionsStatus(BaseModel):
    enabled: bool
    auth_required: bool
    public_base_url: str
    openapi_url: str
    actions_openapi_url: str
    context_path: str
    record_path: str
    apply_workouts_path: str
    sync_push_path: str
    sync_target_configured: bool
    sync_target_url: str


class ChatGPTSyncSnapshot(BaseModel):
    athlete_profile: dict[str, Any] | None = None
    activities: list[dict[str, Any]] = Field(default_factory=list)
    health_metrics: list[dict[str, Any]] = Field(default_factory=list)
    planned_workouts: list[dict[str, Any]] = Field(default_factory=list)
    schedule_constraints: list[dict[str, Any]] = Field(default_factory=list)
    training_locations: list[dict[str, Any]] = Field(default_factory=list)
    recent_location_feedback: list[dict[str, Any]] = Field(default_factory=list)
    gear: list[dict[str, Any]] = Field(default_factory=list)


class ChatGPTSyncSummary(BaseModel):
    athlete_profile_saved: bool
    activities_applied: int
    health_metrics_applied: int
    planned_workouts_applied: int
    schedule_constraints_applied: int
    training_locations_applied: int
    recent_location_feedback_applied: int
    gear_applied: int


class ChatGPTSyncPushRequest(BaseModel):
    remote_base_url: str | None = None
    remote_token: str | None = None


class ChatGPTSyncPushResponse(BaseModel):
    remote_base_url: str
    pushed: bool
    summary: ChatGPTSyncSummary
    message: str


class SettingsResponse(BaseModel):
    app_name: str
    ollama_base_url: str
    ollama_model: str
    ollama_embed_model: str
    garmin_non_official_enabled: bool
    strava_configured: bool


class ModelRecommendation(BaseModel):
    recommended: str
    alternatives: list[dict[str, str]]
    rationale: str


class GarminImportStatus(BaseModel):
    import_dir: str
    supported_extensions: list[str]
    files_seen: int
    imported_activities: int
    imported_metrics: int
    skipped_files: int
    failed_files: int
    message: str


class ContextExportResponse(BaseModel):
    path: str
    bytes_written: int
    message: str


class TrainingLocationCreate(BaseModel):
    name: str
    training_base: str = "Newport Beach"
    sport: Sport
    sport_variant: SportVariant = SportVariant.other
    surface: str | None = None
    distance_meters: float | None = None
    elevation_meters: float | None = None
    location_notes: str = ""
    safety_notes: str = ""
    link_url: str | None = None
    tags: str = ""
    active: bool = True


class WorkoutLocationFeedbackCreate(BaseModel):
    location_id: int
    activity_id: int | None = None
    planned_workout_id: int | None = None
    feedback_date: date
    intended_stimulus: str
    rating: int = Field(ge=1, le=5)
    conditions: str = ""
    notes: str = ""
    use_again: bool = True


class GearItemCreate(BaseModel):
    strava_gear_id: str | None = None
    name: str
    gear_type: GearType
    distance_meters: float = 0
    retire_distance_meters: float | None = None
    active: bool = True
    preferred_sport_variants: str = ""
    preferred_surfaces: str = ""
    notes: str = ""
    source: Source = Source.manual
