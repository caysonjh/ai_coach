from datetime import date, datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
import json
from sqlmodel import Session, SQLModel, create_engine, select

from app.api.routes import chatgpt_openapi, require_chatgpt_token
from app.models.entities import Activity, AthleteProfile, HealthMetric, MetricType, PlanVersion, PlannedWorkout, Source, Sport, SportVariant
from app.schemas.api import CoachRecordRequest, CoachRequest, PlannedWorkoutCreate
from app.services import coach as coach_module
from app.services.coach import CoachService


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
