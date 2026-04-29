from datetime import date, datetime, time, timedelta
from pathlib import Path

from sqlmodel import Session, select

from app.core.config import get_settings
from app.models.entities import (
    Activity,
    AthleteProfile,
    CoachInsight,
    CoachMemory,
    GearItem,
    HealthMetric,
    PlannedWorkout,
    TrainingLocation,
    WorkoutLocationFeedback,
)
from app.services.analytics import summarize_training


def export_coach_context(session: Session) -> tuple[Path, int]:
    settings = get_settings()
    path = Path(settings.coach_context_export_path).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)

    today = date.today()
    since = today - timedelta(days=90)
    profile = session.exec(select(AthleteProfile).limit(1)).first()
    activities = session.exec(
        select(Activity).where(Activity.start_time >= datetime.combine(since, time.min))
    ).all()
    metrics = session.exec(select(HealthMetric).where(HealthMetric.metric_date >= since)).all()
    workouts = session.exec(select(PlannedWorkout).where(PlannedWorkout.planned_date >= since)).all()
    insights = session.exec(select(CoachInsight).order_by(CoachInsight.created_at.desc()).limit(8)).all()
    memories = session.exec(select(CoachMemory).order_by(CoachMemory.importance.desc()).limit(16)).all()
    locations = session.exec(select(TrainingLocation).where(TrainingLocation.active == True)).all()  # noqa: E712
    feedback = session.exec(select(WorkoutLocationFeedback).order_by(WorkoutLocationFeedback.feedback_date.desc()).limit(20)).all()
    gear = session.exec(select(GearItem).where(GearItem.active == True)).all()  # noqa: E712
    summary = summarize_training(activities, metrics, workouts, today=today)

    content = _render_context(
        profile,
        summary,
        activities[-12:],
        metrics[-30:],
        workouts[-30:],
        insights,
        memories,
        locations,
        feedback,
        gear,
    )
    path.write_text(content, encoding="utf-8")
    return path, len(content.encode("utf-8"))


def _render_context(
    profile: AthleteProfile | None,
    summary: dict,
    activities: list[Activity],
    metrics: list[HealthMetric],
    workouts: list[PlannedWorkout],
    insights: list[CoachInsight],
    memories: list[CoachMemory],
    locations: list[TrainingLocation],
    feedback: list[WorkoutLocationFeedback],
    gear: list[GearItem],
) -> str:
    lines = [
        "# AI Coach Context Snapshot",
        "",
        "Use this file as compact long-term context for local coaching sessions.",
        "",
        "## Athlete",
        f"- Name: {profile.name if profile else 'Cayson Hamilton'}",
        f"- Goal: {profile.goal_summary if profile else 'Elite age-group 70.3 triathlon progression'}",
        f"- Goal race: {profile.goal_race if profile else 'TBD'}",
        f"- Target time: {profile.target_time if profile else 'TBD'}",
        "- Constraints: R-CPD GI risk, chronic fatigue syndrome, ADHD/depression, variable schedule.",
        "",
        "## Current Training Summary",
        f"- 7-day volume: {summary['volume_7d_hours']} hours",
        f"- 28-day volume: {summary['volume_28d_hours']} hours",
        f"- 7-day activities: {summary['activities_7d']}",
        f"- 28-day activities: {summary['activities_28d']}",
        f"- Discipline split 7d: {summary['discipline_hours_7d']}",
        f"- Calendar adherence: {summary['calendar_adherence']}",
        f"- Recovery flags: {summary['recovery_flags'] or 'none'}",
        "",
        "## Latest Health Metrics",
    ]
    for key, value in summary["latest_metrics"].items():
        lines.append(f"- {key}: {value['value']} {value.get('unit') or ''} on {value['date']} ({value['source']})")
    if not summary["latest_metrics"]:
        lines.append("- No health metrics logged yet.")

    lines.extend(["", "## Recent Activities"])
    for activity in activities:
        lines.append(
            f"- {activity.start_time.date()} {activity.sport.value}: {activity.name}, "
            f"{round(activity.duration_seconds / 60)} min, source={activity.source.value}"
        )
    if not activities:
        lines.append("- No recent activities imported or synced.")

    lines.extend(["", "## Recent Planned Workouts"])
    for workout in workouts:
        lines.append(
            f"- {workout.planned_date} {workout.sport_variant.value}: {workout.title}, "
            f"{workout.duration_minutes or '?'} min, {workout.intensity}, "
            f"location={workout.location_suggestion or 'none'}, gear={workout.gear_suggestion or 'none'}, "
            f"status={workout.status.value}"
        )
    if not workouts:
        lines.append("- No planned workouts yet.")

    lines.extend(["", "## Training Locations"])
    for location in locations:
        lines.append(
            f"- {location.name}: {location.sport_variant.value}, surface={location.surface or 'n/a'}, "
            f"base={location.training_base}, tags={location.tags}, notes={location.location_notes}"
        )
    if not locations:
        lines.append("- No training locations saved yet.")

    lines.extend(["", "## Location Feedback"])
    for item in feedback:
        lines.append(
            f"- {item.feedback_date}: location_id={item.location_id}, stimulus={item.intended_stimulus}, "
            f"rating={item.rating}/5, use_again={item.use_again}, notes={item.notes}"
        )
    if not feedback:
        lines.append("- No location feedback saved yet.")

    lines.extend(["", "## Gear"])
    for item in gear:
        lines.append(
            f"- {item.name}: {item.gear_type.value}, {round(item.distance_meters / 1609.344, 1)} mi, "
            f"retire={round(item.retire_distance_meters / 1609.344, 1) if item.retire_distance_meters else 'n/a'} mi, "
            f"variants={item.preferred_sport_variants}, surfaces={item.preferred_surfaces}, source={item.source.value}"
        )
    if not gear:
        lines.append("- No gear saved or synced yet.")

    lines.extend(["", "## Coach Insights"])
    for insight in insights:
        lines.append(f"- {insight.insight_date}: {insight.title} - {insight.summary}")
    if not insights:
        lines.append("- No saved insights yet.")

    lines.extend(["", "## Durable Memories"])
    for memory in memories:
        lines.append(f"- [{memory.memory_type}, importance={memory.importance}] {memory.content}")
    return "\n".join(lines) + "\n"
