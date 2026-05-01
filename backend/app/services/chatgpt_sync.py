from __future__ import annotations

from typing import Any

import httpx
from sqlmodel import Session, select

from app.models.entities import (
    Activity,
    AthleteProfile,
    GearItem,
    HealthMetric,
    PlannedWorkout,
    ScheduleConstraint,
    TrainingLocation,
    WorkoutLocationFeedback,
)
from app.schemas.api import ChatGPTSyncSnapshot, ChatGPTSyncSummary


def build_chatgpt_sync_snapshot(session: Session) -> ChatGPTSyncSnapshot:
    profile = session.exec(select(AthleteProfile).limit(1)).first()
    activities = session.exec(select(Activity).order_by(Activity.start_time.asc(), Activity.id.asc())).all()
    metrics = session.exec(select(HealthMetric).order_by(HealthMetric.metric_date.asc(), HealthMetric.id.asc())).all()
    workouts = session.exec(select(PlannedWorkout).order_by(PlannedWorkout.planned_date.asc(), PlannedWorkout.id.asc())).all()
    constraints = session.exec(
        select(ScheduleConstraint).order_by(ScheduleConstraint.constraint_date.asc(), ScheduleConstraint.id.asc())
    ).all()
    locations = session.exec(select(TrainingLocation).order_by(TrainingLocation.name.asc(), TrainingLocation.id.asc())).all()
    feedback = session.exec(
        select(WorkoutLocationFeedback).order_by(WorkoutLocationFeedback.feedback_date.desc(), WorkoutLocationFeedback.id.desc())
    ).all()
    gear = session.exec(select(GearItem).order_by(GearItem.gear_type.asc(), GearItem.name.asc())).all()

    return ChatGPTSyncSnapshot(
        athlete_profile=profile.model_dump(mode="json") if profile else None,
        activities=[item.model_dump(mode="json") for item in activities],
        health_metrics=[item.model_dump(mode="json") for item in metrics],
        planned_workouts=[item.model_dump(mode="json") for item in workouts],
        schedule_constraints=[item.model_dump(mode="json") for item in constraints],
        training_locations=[item.model_dump(mode="json") for item in locations],
        recent_location_feedback=[item.model_dump(mode="json") for item in feedback],
        gear=[item.model_dump(mode="json") for item in gear],
    )


def apply_chatgpt_sync_snapshot(session: Session, snapshot: ChatGPTSyncSnapshot) -> ChatGPTSyncSummary:
    _clear_sync_tables(session)

    profile_saved = False
    if snapshot.athlete_profile:
        session.add(AthleteProfile.model_validate(snapshot.athlete_profile))
        profile_saved = True

    for item in snapshot.activities:
        session.add(Activity.model_validate(item))
    for item in snapshot.health_metrics:
        session.add(HealthMetric.model_validate(item))
    for item in snapshot.planned_workouts:
        session.add(PlannedWorkout.model_validate(item))
    for item in snapshot.schedule_constraints:
        session.add(ScheduleConstraint.model_validate(item))
    for item in snapshot.training_locations:
        session.add(TrainingLocation.model_validate(item))
    for item in snapshot.recent_location_feedback:
        session.add(WorkoutLocationFeedback.model_validate(item))
    for item in snapshot.gear:
        session.add(GearItem.model_validate(item))

    session.commit()

    return ChatGPTSyncSummary(
        athlete_profile_saved=profile_saved,
        activities_applied=len(snapshot.activities),
        health_metrics_applied=len(snapshot.health_metrics),
        planned_workouts_applied=len(snapshot.planned_workouts),
        schedule_constraints_applied=len(snapshot.schedule_constraints),
        training_locations_applied=len(snapshot.training_locations),
        recent_location_feedback_applied=len(snapshot.recent_location_feedback),
        gear_applied=len(snapshot.gear),
    )


async def push_chatgpt_sync(
    snapshot: ChatGPTSyncSnapshot,
    remote_base_url: str,
    remote_token: str | None = None,
) -> ChatGPTSyncSummary:
    url = f"{remote_base_url.rstrip('/')}/api/chatgpt/sync"
    headers = {"Content-Type": "application/json"}
    if remote_token:
        headers["Authorization"] = f"Bearer {remote_token}"

    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(url, json=snapshot.model_dump(mode="json"), headers=headers)
        response.raise_for_status()
        payload = response.json()
        return ChatGPTSyncSummary.model_validate(payload["summary"] if "summary" in payload else payload)


def push_chatgpt_sync_sync(
    snapshot: ChatGPTSyncSnapshot,
    remote_base_url: str,
    remote_token: str | None = None,
) -> ChatGPTSyncSummary:
    url = f"{remote_base_url.rstrip('/')}/api/chatgpt/sync"
    headers = {"Content-Type": "application/json"}
    if remote_token:
        headers["Authorization"] = f"Bearer {remote_token}"

    with httpx.Client(timeout=60) as client:
        response = client.post(url, json=snapshot.model_dump(mode="json"), headers=headers)
        response.raise_for_status()
        payload = response.json()
        return ChatGPTSyncSummary.model_validate(payload["summary"] if "summary" in payload else payload)


def _clear_sync_tables(session: Session) -> None:
    for model in (
        WorkoutLocationFeedback,
        PlannedWorkout,
        TrainingLocation,
        GearItem,
        ScheduleConstraint,
        HealthMetric,
        Activity,
        AthleteProfile,
    ):
        for row in session.exec(select(model)).all():
            session.delete(row)
