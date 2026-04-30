from datetime import datetime, timedelta, timezone
from typing import Any

from sqlmodel import Session, select

from app.models.entities import Activity, PlannedWorkout, SportVariant, WorkoutLocationFeedback


MATCH_WINDOW = timedelta(minutes=3)


def upsert_activity(session: Session, incoming: Activity) -> tuple[Activity, bool]:
    """Insert an activity or merge it into an existing duplicate."""
    existing = _find_duplicate(session, incoming)
    if existing is None:
        session.add(incoming)
        return incoming, True

    _merge_activity(existing, incoming)
    session.add(existing)
    return existing, False


def deduplicate_existing_activities(session: Session) -> int:
    activities = session.exec(select(Activity).order_by(Activity.start_time.asc(), Activity.id.asc())).all()
    removed = 0
    kept: list[Activity] = []
    for activity in activities:
        duplicate = next((candidate for candidate in kept if _is_same_activity(candidate, activity)), None)
        if duplicate is None:
            kept.append(activity)
            continue

        _merge_activity(duplicate, activity)
        _repoint_activity_references(session, from_id=activity.id, to_id=duplicate.id)
        session.delete(activity)
        session.add(duplicate)
        removed += 1
    if removed:
        session.commit()
    return removed


def _find_duplicate(session: Session, incoming: Activity) -> Activity | None:
    if incoming.source_id:
        exact = session.exec(
            select(Activity).where(Activity.source == incoming.source, Activity.source_id == incoming.source_id)
        ).first()
        if exact:
            return exact

    start = _normalize_time(incoming.start_time)
    window_start = start - MATCH_WINDOW
    window_end = start + MATCH_WINDOW
    candidates = session.exec(
        select(Activity).where(
            Activity.sport == incoming.sport,
            Activity.start_time >= window_start,
            Activity.start_time <= window_end,
        )
    ).all()
    return next((candidate for candidate in candidates if _is_same_activity(candidate, incoming)), None)


def _is_same_activity(left: Activity, right: Activity) -> bool:
    if left.id is not None and right.id is not None and left.id == right.id:
        return True
    if left.source_id and right.source_id and left.source == right.source and left.source_id == right.source_id:
        return True
    if left.sport != right.sport:
        return False

    left_start = _normalize_time(left.start_time)
    right_start = _normalize_time(right.start_time)
    if abs((left_start - right_start).total_seconds()) > MATCH_WINDOW.total_seconds():
        return False

    if not _close_enough(left.duration_seconds, right.duration_seconds, absolute=120, relative=0.05):
        return False

    if left.distance_meters and right.distance_meters:
        if not _close_enough(left.distance_meters, right.distance_meters, absolute=150, relative=0.03):
            return False

    return True


def _merge_activity(existing: Activity, incoming: Activity) -> None:
    existing.sport_variant = _prefer_variant(existing.sport_variant, incoming.sport_variant)
    existing.gear_id = existing.gear_id or incoming.gear_id
    existing.name = _prefer_name(existing.name, incoming.name)
    existing.duration_seconds = max(existing.duration_seconds or 0, incoming.duration_seconds or 0)

    for field in (
        "distance_meters",
        "elevation_meters",
        "avg_hr",
        "max_hr",
        "avg_power",
        "max_power",
        "avg_pace_seconds_per_km",
        "calories",
        "perceived_effort",
        "training_effect",
    ):
        current = getattr(existing, field)
        incoming_value = getattr(incoming, field)
        if current is None and incoming_value is not None:
            setattr(existing, field, incoming_value)

    if incoming.notes and incoming.notes not in existing.notes:
        existing.notes = f"{existing.notes}\n{incoming.notes}".strip()

    existing.raw_payload = _merge_raw_payload(existing, incoming)


def _merge_raw_payload(existing: Activity, incoming: Activity) -> dict[str, Any]:
    payload = dict(existing.raw_payload or {})
    sources = list(payload.get("merged_sources", []))
    for activity in (existing, incoming):
        source_record = {"source": activity.source.value, "source_id": activity.source_id}
        if source_record not in sources:
            sources.append(source_record)
    payload["merged_sources"] = sources

    imported_payloads = dict(payload.get("merged_payloads", {}))
    for activity in (existing, incoming):
        key = f"{activity.source.value}:{activity.source_id or 'no_source_id'}"
        imported_payloads[key] = activity.raw_payload
    payload["merged_payloads"] = imported_payloads
    return payload


def _prefer_variant(current: SportVariant, incoming: SportVariant) -> SportVariant:
    if current == SportVariant.other and incoming != SportVariant.other:
        return incoming
    return current


def _prefer_name(current: str, incoming: str) -> str:
    current_lower = current.lower()
    if current_lower.startswith("imported") and incoming and not incoming.lower().startswith("imported"):
        return incoming
    return current


def _close_enough(left: float | int | None, right: float | int | None, *, absolute: float, relative: float) -> bool:
    if left is None or right is None:
        return True
    delta = abs(float(left) - float(right))
    tolerance = max(absolute, max(abs(float(left)), abs(float(right))) * relative)
    return delta <= tolerance


def _normalize_time(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _repoint_activity_references(session: Session, *, from_id: int | None, to_id: int | None) -> None:
    if from_id is None or to_id is None:
        return
    workouts = session.exec(select(PlannedWorkout).where(PlannedWorkout.linked_activity_id == from_id)).all()
    for workout in workouts:
        workout.linked_activity_id = to_id
        session.add(workout)

    feedback_items = session.exec(
        select(WorkoutLocationFeedback).where(WorkoutLocationFeedback.activity_id == from_id)
    ).all()
    for feedback in feedback_items:
        feedback.activity_id = to_id
        session.add(feedback)
