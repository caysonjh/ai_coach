from datetime import date, datetime
from types import SimpleNamespace

import pytest
from fastapi import BackgroundTasks, HTTPException
from fastapi.security import HTTPAuthorizationCredentials
import json
from sqlmodel import Session, SQLModel, create_engine, select

from app.api.routes import chatgpt_openapi, create_location, require_chatgpt_token
from app.models.entities import (
    Activity,
    AthleteProfile,
    GearItem,
    GearType,
    HealthMetric,
    MetricType,
    PlanVersion,
    PlannedWorkout,
    Source,
    Sport,
    SportVariant,
    TrainingLocation,
    WorkoutLocationFeedback,
)
from app.schemas.api import CoachRecordRequest, CoachRequest, PlannedWorkoutCreate, TrainingLocationCreate
from app.services.chatgpt_sync import apply_chatgpt_sync_snapshot, build_chatgpt_sync_snapshot
from app.services import coach as coach_module
from app.services.coach import CoachService
from app.main import sync_chatgpt_remote


def test_build_context_exposes_action_endpoints_and_summary(monkeypatch) -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(coach_module, "read_me_markdown", lambda: "Live profile text from me.md")

    with Session(engine) as session:
        session.add(
            AthleteProfile(
                name="Cayson Hamilton",
                goal_summary="Sub-5 70.3",
                goal_race="Boise 2026 70.3",
                target_time="sub-5:00",
            )
        )
        session.add(
            Activity(
                source=Source.strava,
                sport=Sport.run,
                sport_variant=SportVariant.road_run,
                name="Easy Run",
                start_time=datetime(2026, 4, 30, 7, 0),
                duration_seconds=3600,
                distance_meters=10000,
            )
        )
        session.add(
            HealthMetric(
                metric_date=date(2026, 4, 30),
                metric_type=MetricType.training_readiness,
                value_num=72,
                unit="score",
            )
        )
        session.commit()

        response = CoachService().build_context(
            session,
            CoachRequest(message="What should I focus on today?", aggressiveness=0.55),
        )

    assert response.athlete_profile["goal_summary"] == "Sub-5 70.3"
    assert response.athlete_profile_markdown == "Live profile text from me.md"
    assert response.request_intent == "coaching_chat"
    assert response.action_endpoints[0].path == "/api/chatgpt/context"
    assert response.coach_guidance
    assert response.training_summary["activities_7d"] >= 1
    assert len(response.recent_activities) <= 5
    assert all("raw_payload" not in item for item in response.recent_activities)
    assert len(json.dumps(response.model_dump(mode="json"))) < 20000


def test_record_coach_result_persists_workouts_and_plan_version() -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        result = CoachService().record_coach_result(
            session,
            CoachRecordRequest(
                source_message="Plan my week",
                title="Weekly Focus",
                summary="Build a controlled week around current load.",
                recommendations=["Keep the bike aerobic.", "Protect run freshness."],
                risks=["High fatigue"],
                proposed_workouts=[
                    PlannedWorkoutCreate(
                        planned_date=date(2026, 5, 1),
                        sport=Sport.run,
                        sport_variant=SportVariant.road_run,
                        title="Easy Run",
                        description="Easy running only.",
                        duration_minutes=45,
                        intensity="easy",
                    )
                ],
                rationale="Based on current training summary.",
                persist_workouts=True,
            ),
        )

        workouts = session.exec(select(PlannedWorkout)).all()
        versions = session.exec(select(PlanVersion)).all()

    assert result.saved_insight is True
    assert result.saved_plan_version is True
    assert result.applied_workouts == 1
    assert workouts and workouts[0].title == "Easy Run"
    assert versions and versions[0].status == "approved"


def test_chatgpt_token_guard_allows_blank_dev_and_rejects_wrong_token(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.api.routes.get_settings",
        lambda: SimpleNamespace(chatgpt_action_token=""),
    )
    require_chatgpt_token(None)

    monkeypatch.setattr(
        "app.api.routes.get_settings",
        lambda: SimpleNamespace(chatgpt_action_token="secret"),
    )

    with pytest.raises(HTTPException):
        require_chatgpt_token(None)

    require_chatgpt_token(HTTPAuthorizationCredentials(scheme="Bearer", credentials="secret"))


def test_chatgpt_openapi_is_trimmed_to_action_paths(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.api.routes.get_settings",
        lambda: SimpleNamespace(chatgpt_public_base_url="https://coach.example"),
    )

    response = chatgpt_openapi()
    spec = json.loads(response.body)

    assert spec["servers"] == [{"url": "https://coach.example"}]
    assert set(spec["paths"]) == {
        "/api/chatgpt/context",
        "/api/chatgpt/record",
        "/api/chatgpt/apply-workouts",
        "/api/chatgpt/status",
        "/api/chatgpt/openapi.json",
    }
    assert spec["components"]["securitySchemes"]["bearerAuth"]["scheme"] == "bearer"


def test_chatgpt_sync_snapshot_round_trip_preserves_core_context() -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        profile = AthleteProfile(name="Cayson Hamilton", goal_summary="Sub-5 70.3")
        session.add(profile)
        session.flush()

        activity = Activity(
            source=Source.strava,
            sport=Sport.run,
            sport_variant=SportVariant.road_run,
            name="Easy Run",
            start_time=datetime(2026, 4, 30, 7, 0),
            duration_seconds=3600,
            distance_meters=10000,
        )
        session.add(activity)
        session.flush()

        metric = HealthMetric(
            metric_date=date(2026, 4, 30),
            metric_type=MetricType.training_readiness,
            value_num=72,
            unit="score",
        )
        session.add(metric)

        location = TrainingLocation(
            name="Newport Loop",
            training_base="Newport Beach",
            sport=Sport.run,
            sport_variant=SportVariant.road_run,
        )
        session.add(location)
        session.flush()

        workout = PlannedWorkout(
            planned_date=date(2026, 5, 1),
            sport=Sport.run,
            sport_variant=SportVariant.road_run,
            title="Easy Run",
            description="Easy running only.",
            duration_minutes=45,
            intensity="easy",
            linked_activity_id=activity.id,
        )
        session.add(workout)
        session.flush()
        feedback = WorkoutLocationFeedback(
            location_id=location.id,
            activity_id=activity.id,
            planned_workout_id=workout.id,
            feedback_date=date(2026, 5, 1),
            intended_stimulus="easy aerobic",
            rating=5,
        )
        session.add(feedback)
        session.add(
            GearItem(
                name="Trail Shoe",
                gear_type=GearType.shoes,
                distance_meters=100 * 1609.344,
                preferred_sport_variants="trail_run",
                preferred_surfaces="trail",
                source=Source.manual,
            )
        )
        session.commit()

        snapshot = build_chatgpt_sync_snapshot(session)

    with Session(engine) as session:
        summary = apply_chatgpt_sync_snapshot(session, snapshot)
        activities = session.exec(select(Activity)).all()
        workouts = session.exec(select(PlannedWorkout)).all()
        feedback_rows = session.exec(select(WorkoutLocationFeedback)).all()

    assert summary.activities_applied == 1
    assert summary.health_metrics_applied == 1
    assert summary.planned_workouts_applied == 1
    assert summary.training_locations_applied == 1
    assert summary.recent_location_feedback_applied == 1
    assert activities and activities[0].name == "Easy Run"
    assert workouts and workouts[0].linked_activity_id == activities[0].id
    assert feedback_rows and feedback_rows[0].activity_id == activities[0].id


def test_create_location_queues_chatgpt_sync_when_target_configured(monkeypatch) -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(
        "app.api.routes.get_settings",
        lambda: SimpleNamespace(
            chatgpt_sync_target_url="https://remote.example",
            chatgpt_sync_target_token="sync-token",
        ),
    )

    with Session(engine) as session:
        background_tasks = BackgroundTasks()
        location = create_location(
            TrainingLocationCreate(
                name="Newport Loop",
                training_base="Newport Beach",
                sport=Sport.run,
                sport_variant=SportVariant.road_run,
            ),
            background_tasks,
            session,
        )

    assert location.id is not None
    assert len(background_tasks.tasks) == 1
    task = background_tasks.tasks[0]
    assert task.func.__name__ == "push_chatgpt_sync_sync"
    assert task.args[1] == "https://remote.example"


def test_startup_sync_pushes_full_snapshot_when_target_configured(monkeypatch) -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(
            Activity(
                source=Source.strava,
                sport=Sport.run,
                sport_variant=SportVariant.road_run,
                name="Easy Run",
                start_time=datetime(2026, 4, 30, 7, 0),
                duration_seconds=3600,
                distance_meters=10000,
            )
        )
        session.commit()

        captured = {}

        monkeypatch.setattr(
            "app.main.get_settings",
            lambda: SimpleNamespace(
                chatgpt_sync_target_url="https://remote.example",
                chatgpt_sync_target_token="sync-token",
            ),
        )
        monkeypatch.setattr(
            "app.main.push_chatgpt_sync_sync",
            lambda snapshot, remote_base_url, remote_token=None: captured.update(
                {
                    "activities": len(snapshot.activities),
                    "remote_base_url": remote_base_url,
                    "remote_token": remote_token,
                }
            ),
        )

        sync_chatgpt_remote(session)

    assert captured["activities"] == 1
    assert captured["remote_base_url"] == "https://remote.example"
    assert captured["remote_token"] == "sync-token"
