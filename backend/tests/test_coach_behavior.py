from datetime import date, datetime

from app.models.entities import Activity, Source, Sport
from app.schemas.api import CoachRequest
from app.services.coach import CoachService


def test_analysis_request_does_not_create_fallback_workouts() -> None:
    service = CoachService()
    request = CoachRequest(message="Analyze my past week of workouts", aggressiveness=0.45)
    summary = {
        "activities_7d": 2,
        "volume_7d_hours": 2.5,
        "volume_28d_hours": 8.0,
        "discipline_hours_7d": {"run": 1.0, "bike": 1.5},
        "recovery_flags": [],
    }
    activities = [
        Activity(
            source=Source.strava,
            sport=Sport.run,
            name="Tempo Run",
            start_time=datetime(2026, 4, 29, 8, 0),
            duration_seconds=3600,
            distance_meters=10000,
        )
    ]

    response = service._fallback_response(
        request,
        summary,
        date(2026, 4, 27),
        activities,
        request_intent="analysis",
        effective_aggressiveness=0.45,
    )

    assert response["title"] == "Past Week Training Analysis"
    assert response["proposed_workouts"] == []
    assert "Tempo Run" in response["summary"]


def test_more_aggressive_message_increases_effective_aggressiveness() -> None:
    service = CoachService()

    assert service._effective_aggressiveness("Make the training plan more aggressive", 0.45) == 0.75
    assert service._effective_aggressiveness("Make it easier", 0.45) == 0.25


def test_analysis_guard_strips_model_workouts_and_adds_data_summary() -> None:
    service = CoachService()
    model_result = {
        "title": "Generic Training Plan",
        "summary": "Build a stable week.",
        "recommendations": ["Do a short ride."],
        "risks": [],
        "proposed_workouts": [
            {
                "planned_date": "2026-04-30",
                "sport": "bike",
                "title": "Easy Bike",
                "description": "Ride easy.",
                "duration_minutes": 30,
                "intensity": "easy",
            }
        ],
    }
    summary = {
        "activities_7d": 1,
        "volume_7d_hours": 1.0,
        "discipline_hours_7d": {"run": 1.0},
    }
    activities = [
        Activity(
            source=Source.strava,
            sport=Sport.run,
            name="First Newport Run",
            start_time=datetime(2026, 4, 27, 8, 0),
            duration_seconds=3600,
            distance_meters=10000,
        )
    ]

    grounded = service._ground_analysis_result(model_result, activities, summary, date(2026, 4, 30))

    assert grounded["proposed_workouts"] == []
    assert "Past 7 days from imported data" in grounded["summary"]
    assert "First Newport Run" in grounded["summary"]


def test_planning_guard_replaces_stale_generic_ollama_plan() -> None:
    service = CoachService()
    request = CoachRequest(message="Plan the rest of the week", aggressiveness=0.45)
    model_result = {
        "title": "Training Plan for Athlete with Chronic Fatigue Syndrome and ADHD/Depression",
        "summary": "The training plan is designed to help the athlete build a stable week.",
        "recommendations": ["Start with a short bike workout tomorrow."],
        "risks": [],
        "proposed_workouts": [
            {
                "planned_date": "2023-02-20",
                "sport": "Bike",
                "title": "Easy Bike Ride",
                "description": "30 minutes of easy bike riding.",
                "duration_minutes": 30,
                "intensity": "easy",
            }
        ],
    }
    summary = {
        "activities_7d": 4,
        "volume_7d_hours": 6.1,
        "volume_28d_hours": 34.4,
        "discipline_hours_7d": {"run": 1.0, "bike": 2.0, "swim": 0.4, "strength": 0.6},
        "recovery_flags": [],
    }

    grounded = service._ground_planning_result(
        model_result,
        request,
        summary,
        date(2026, 4, 27),
        [],
        date(2026, 4, 30),
        effective_aggressiveness=0.45,
    )

    assert grounded["title"] == "This Week's Training Focus"
    assert all(date.fromisoformat(item["planned_date"]) >= date(2026, 4, 30) for item in grounded["proposed_workouts"])
    assert all(date.fromisoformat(item["planned_date"]) <= date(2026, 5, 3) for item in grounded["proposed_workouts"])
    assert grounded["proposed_workouts"][0]["duration_minutes"] > 30
