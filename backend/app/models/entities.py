from datetime import date, datetime
from enum import Enum
from typing import Any

from sqlalchemy import Column, JSON
from sqlmodel import Field, SQLModel


class Source(str, Enum):
    manual = "manual"
    strava = "strava"
    garmin_official = "garmin_official"
    file_import = "file_import"
    non_official = "non_official"
    derived = "derived"


class Sport(str, Enum):
    swim = "swim"
    bike = "bike"
    run = "run"
    strength = "strength"
    climb = "climb"
    mobility = "mobility"
    rest = "rest"
    other = "other"


class SportVariant(str, Enum):
    road_run = "road_run"
    trail_run = "trail_run"
    road_ride = "road_ride"
    gravel_ride = "gravel_ride"
    mtb_ride = "mtb_ride"
    tt_ride = "tt_ride"
    pool_swim = "pool_swim"
    open_water_swim = "open_water_swim"
    strength = "strength"
    climb = "climb"
    mobility = "mobility"
    rest = "rest"
    other = "other"


class WorkoutStatus(str, Enum):
    planned = "planned"
    completed = "completed"
    missed = "missed"
    skipped = "skipped"


class MetricType(str, Enum):
    sleep_score = "sleep_score"
    sleep_duration_hours = "sleep_duration_hours"
    hrv_ms = "hrv_ms"
    hrv_status = "hrv_status"
    resting_hr = "resting_hr"
    vo2_max = "vo2_max"
    ftp = "ftp"
    training_readiness = "training_readiness"
    training_status = "training_status"
    acute_load = "acute_load"
    load_ratio = "load_ratio"
    load_focus = "load_focus"
    recovery_time_hours = "recovery_time_hours"
    aerobic_training_effect = "aerobic_training_effect"
    anaerobic_training_effect = "anaerobic_training_effect"
    endurance_score = "endurance_score"
    hill_score = "hill_score"
    lactate_threshold_hr = "lactate_threshold_hr"
    lactate_threshold_pace = "lactate_threshold_pace"
    lactate_threshold_power = "lactate_threshold_power"
    body_battery = "body_battery"
    stress = "stress"
    pulse_ox = "pulse_ox"
    respiration_rate = "respiration_rate"
    body_weight = "body_weight"
    body_fat_percent = "body_fat_percent"
    heat_acclimation = "heat_acclimation"
    altitude_acclimation = "altitude_acclimation"
    fatigue_note = "fatigue_note"
    rcpd_symptom_note = "rcpd_symptom_note"
    custom = "custom"


class AthleteProfile(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str = "Cayson Hamilton"
    goal_summary: str = ""
    goal_race: str | None = None
    target_time: str | None = None
    notes: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class OAuthAccount(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    provider: str = Field(index=True)
    athlete_id: str | None = Field(default=None, index=True)
    access_token: str = ""
    refresh_token: str = ""
    expires_at: datetime | None = None
    scopes: str = ""
    raw_payload: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class Activity(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    source: Source = Field(index=True)
    source_id: str | None = Field(default=None, index=True)
    sport: Sport = Field(index=True)
    sport_variant: SportVariant = SportVariant.other
    gear_id: str | None = Field(default=None, index=True)
    name: str
    start_time: datetime = Field(index=True)
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
    raw_payload: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=datetime.utcnow)


class HealthMetric(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    metric_date: date = Field(index=True)
    metric_type: MetricType = Field(index=True)
    custom_name: str | None = None
    value_num: float | None = None
    value_text: str | None = None
    unit: str | None = None
    source: Source = Source.manual
    confidence: float = Field(default=1.0, ge=0, le=1)
    notes: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)


class PlannedWorkout(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    planned_date: date = Field(index=True)
    sport: Sport = Field(index=True)
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
    linked_activity_id: int | None = Field(default=None, foreign_key="activity.id")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class ScheduleConstraint(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    constraint_date: date = Field(index=True)
    label: str
    available_minutes: int | None = None
    unavailable: bool = False
    notes: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)


class PlanVersion(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    week_start: date = Field(index=True)
    status: str = "proposed"
    rationale: str = ""
    aggressiveness: float = Field(default=0.45, ge=0, le=1)
    autonomy: str = "suggest_then_approve"
    payload: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=datetime.utcnow)


class CoachMemory(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    memory_type: str = Field(index=True)
    content: str
    importance: float = Field(default=0.5, ge=0, le=1)
    embedding: list[float] | None = Field(default=None, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=datetime.utcnow)


class CoachInsight(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    insight_date: date = Field(index=True)
    title: str
    summary: str
    recommendations: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    risks: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    raw_payload: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=datetime.utcnow)


class TrainingLocation(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    training_base: str = "Newport Beach"
    sport: Sport = Field(index=True)
    sport_variant: SportVariant = SportVariant.other
    surface: str | None = None
    distance_meters: float | None = None
    elevation_meters: float | None = None
    location_notes: str = ""
    safety_notes: str = ""
    link_url: str | None = None
    tags: str = ""
    active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class WorkoutLocationFeedback(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    location_id: int = Field(foreign_key="traininglocation.id", index=True)
    activity_id: int | None = Field(default=None, foreign_key="activity.id")
    planned_workout_id: int | None = Field(default=None, foreign_key="plannedworkout.id")
    feedback_date: date = Field(index=True)
    intended_stimulus: str
    rating: int = Field(ge=1, le=5)
    conditions: str = ""
    notes: str = ""
    use_again: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)


class GearType(str, Enum):
    shoes = "shoes"
    bike = "bike"
    other = "other"


class GearItem(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    strava_gear_id: str | None = Field(default=None, index=True)
    name: str = Field(index=True)
    gear_type: GearType = Field(index=True)
    distance_meters: float = 0
    retire_distance_meters: float | None = None
    active: bool = True
    preferred_sport_variants: str = ""
    preferred_surfaces: str = ""
    notes: str = ""
    source: Source = Source.manual
    raw_payload: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class GearRecommendation(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    planned_workout_id: int = Field(foreign_key="plannedworkout.id", index=True)
    gear_item_id: int = Field(foreign_key="gearitem.id", index=True)
    rationale: str = ""
    confidence: float = Field(default=0.5, ge=0, le=1)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ImportJob(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    source: Source
    filename: str
    status: str = "pending"
    rows_imported: int = 0
    message: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)
