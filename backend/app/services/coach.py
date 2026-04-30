from datetime import date, datetime, time, timedelta
from typing import Any

from sqlmodel import Session, select

from app.models.entities import (
    Activity,
    AthleteProfile,
    CoachInsight,
    CoachMemory,
    HealthMetric,
    GearItem,
    PlanVersion,
    PlannedWorkout,
    ScheduleConstraint,
    Source,
    Sport,
    SportVariant,
    TrainingLocation,
    WorkoutLocationFeedback,
)
from app.schemas.api import CoachRequest, CoachResponse, PlannedWorkoutCreate
from app.services.analytics import summarize_training
from app.services.ollama import OllamaClient
from app.services.recommendations import rank_locations
from app.services.state_export import export_coach_context


COACH_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "summary": {"type": "string"},
        "recommendations": {"type": "array", "items": {"type": "string"}},
        "risks": {"type": "array", "items": {"type": "string"}},
        "proposed_workouts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "planned_date": {"type": "string"},
                    "sport": {"type": "string"},
                    "sport_variant": {"type": "string"},
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "duration_minutes": {"type": "integer"},
                    "distance_meters": {"type": ["number", "null"]},
                    "intensity": {"type": "string"},
                    "surface": {"type": ["string", "null"]},
                    "location_suggestion": {"type": ["string", "null"]},
                    "gear_suggestion": {"type": ["string", "null"]},
                    "status": {"type": "string"},
                    "source": {"type": "string"},
                },
                "required": ["planned_date", "sport", "title", "description", "duration_minutes", "intensity"],
            },
        },
    },
    "required": ["title", "summary", "recommendations", "risks", "proposed_workouts"],
}


class CoachService:
    def __init__(self) -> None:
        self.ollama = OllamaClient()

    async def respond(self, session: Session, request: CoachRequest) -> CoachResponse:
        today = date.today()
        week_start = request.week_start or today - timedelta(days=today.weekday())
        since = today - timedelta(days=56)

        profile = session.exec(select(AthleteProfile).limit(1)).first()
        activities = session.exec(
            select(Activity).where(Activity.start_time >= datetime.combine(since, time.min))
        ).all()
        metrics = session.exec(select(HealthMetric).where(HealthMetric.metric_date >= since)).all()
        planned = session.exec(select(PlannedWorkout).where(PlannedWorkout.planned_date >= week_start)).all()
        constraints = session.exec(
            select(ScheduleConstraint).where(ScheduleConstraint.constraint_date >= week_start)
        ).all()
        memories = session.exec(select(CoachMemory).order_by(CoachMemory.importance.desc()).limit(12)).all()
        locations = session.exec(select(TrainingLocation).where(TrainingLocation.active == True)).all()  # noqa: E712
        feedback = session.exec(select(WorkoutLocationFeedback).order_by(WorkoutLocationFeedback.feedback_date.desc()).limit(50)).all()
        gear = session.exec(select(GearItem).where(GearItem.active == True)).all()  # noqa: E712

        summary = summarize_training(activities, metrics, planned, today=today)
        suggested_places = {
            "run": rank_locations(locations, feedback, Sport.run, SportVariant.road_run, "easy"),
            "trail_run": rank_locations(locations, feedback, Sport.run, SportVariant.trail_run, "easy"),
            "ride": rank_locations(locations, feedback, Sport.bike, SportVariant.road_ride, "endurance"),
            "gravel": rank_locations(locations, feedback, Sport.bike, SportVariant.gravel_ride, "endurance"),
            "swim": rank_locations(locations, feedback, Sport.swim, SportVariant.pool_swim, "technique"),
        }
        context = {
            "current_date": today.isoformat(),
            "week_start": week_start.isoformat(),
            "profile": profile.model_dump() if profile else {},
            "training_summary": summary,
            "recent_activities": [activity.model_dump() for activity in activities[-20:]],
            "recent_health_metrics": [metric.model_dump() for metric in metrics[-40:]],
            "planned_workouts": [workout.model_dump() for workout in planned[:30]],
            "schedule_constraints": [constraint.model_dump() for constraint in constraints],
            "training_locations": [location.model_dump() for location in locations],
            "recent_location_feedback": [item.model_dump() for item in feedback],
            "ranked_location_suggestions": suggested_places,
            "gear": [item.model_dump() for item in gear],
            "memories": [memory.content for memory in memories],
            "controls": {
                "aggressiveness": request.aggressiveness,
                "autonomy": request.autonomy,
            },
        }

        system = (
            "You are a precise triathlon coach for an aspiring elite age-group 70.3 athlete. "
            "Account for R-CPD GI risk, chronic fatigue syndrome, strength, climbing, sleep, "
            "manual Garmin-style health metrics, gear mileage, local training places, and schedule constraints. "
            "Use only these sport values in proposed_workouts: swim, bike, run, strength, climb, mobility, rest, other. "
            "Use only these sport_variant values: road_run, trail_run, road_ride, gravel_ride, mtb_ride, tt_ride, pool_swim, open_water_swim, strength, climb, mobility, rest, other. "
            "Use trail running, gravel cycling, and MTB only as controlled substitutions that preserve the intended triathlon stimulus. "
            "For run and bike workouts, suggest gear when gear context exists. For workouts where place context exists, suggest a location. Propose changes but "
            f"Today is {today.isoformat()}; interpret relative dates like tomorrow from that date and do not propose past dates. "
            "do not assume approval. Return only valid JSON matching the schema."
        )
        result = await self.ollama.chat_json(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": f"Request: {request.message}\nContext: {context}"},
            ],
            COACH_SCHEMA,
        )

        used_ollama = result is not None
        if result is None:
            result = self._fallback_response(request, summary, week_start)

        response = self._coerce_response(result, used_ollama)
        insight = CoachInsight(
            insight_date=today,
            title=response.title,
            summary=response.summary,
            recommendations=response.recommendations,
            risks=response.risks,
            raw_payload=response.raw,
        )
        session.add(insight)
        session.add(
            CoachMemory(
                memory_type="coach_interaction",
                content=f"{request.message}\n{response.summary}",
                importance=0.65,
            )
        )
        session.add(
            PlanVersion(
                week_start=week_start,
                status="proposed",
                rationale=response.summary,
                aggressiveness=request.aggressiveness,
                autonomy=request.autonomy,
                payload=response.model_dump(mode="json"),
            )
        )
        session.commit()
        export_coach_context(session)
        return response

    def _coerce_response(self, result: dict[str, Any], used_ollama: bool) -> CoachResponse:
        workouts: list[PlannedWorkoutCreate] = []
        for item in result.get("proposed_workouts", []):
            try:
                workouts.append(
                    PlannedWorkoutCreate(
                        planned_date=date.fromisoformat(str(item["planned_date"])),
                        sport=self._coerce_sport(item.get("sport", "other")),
                        sport_variant=self._coerce_sport_variant(item.get("sport_variant", item.get("sport", "other"))),
                        title=item["title"],
                        description=item.get("description", ""),
                        duration_minutes=item.get("duration_minutes"),
                        distance_meters=item.get("distance_meters"),
                        intensity=item.get("intensity", "easy"),
                        surface=item.get("surface"),
                        location_suggestion=item.get("location_suggestion"),
                        gear_suggestion=item.get("gear_suggestion"),
                        source=Source.derived,
                    )
                )
            except Exception:
                continue

        return CoachResponse(
            title=str(result.get("title", "Training Focus")),
            summary=str(result.get("summary", "")),
            recommendations=[str(item) for item in result.get("recommendations", [])],
            risks=[str(item) for item in result.get("risks", [])],
            proposed_workouts=workouts,
            used_ollama=used_ollama,
            raw=result,
        )

    def _coerce_sport(self, value: str) -> Sport:
        normalized = str(value).lower().replace(" ", "_")
        aliases = {
            "ride": Sport.bike,
            "cycling": Sport.bike,
            "cycle": Sport.bike,
            "gravel": Sport.bike,
            "mtb": Sport.bike,
            "mountain_bike": Sport.bike,
            "running": Sport.run,
            "trail": Sport.run,
            "swimming": Sport.swim,
        }
        if normalized in aliases:
            return aliases[normalized]
        try:
            return Sport(normalized)
        except ValueError:
            return Sport.other

    def _coerce_sport_variant(self, value: str) -> SportVariant:
        normalized = str(value).lower().replace(" ", "_")
        aliases = {
            "ride": SportVariant.road_ride,
            "bike": SportVariant.road_ride,
            "cycling": SportVariant.road_ride,
            "gravel": SportVariant.gravel_ride,
            "gravel_ride": SportVariant.gravel_ride,
            "mtb": SportVariant.mtb_ride,
            "mountain_bike": SportVariant.mtb_ride,
            "run": SportVariant.road_run,
            "running": SportVariant.road_run,
            "trail": SportVariant.trail_run,
            "trail_run": SportVariant.trail_run,
            "swim": SportVariant.pool_swim,
            "swimming": SportVariant.pool_swim,
        }
        if normalized in aliases:
            return aliases[normalized]
        try:
            return SportVariant(normalized)
        except ValueError:
            return SportVariant.other

    def _fallback_response(self, request: CoachRequest, summary: dict, week_start: date) -> dict[str, Any]:
        recovery_bias = request.aggressiveness < 0.35 or bool(summary.get("recovery_flags"))
        intensity = "easy" if recovery_bias else "moderate"
        anchor = max(week_start, date.today())
        recommendations = [
            "Keep Strava as the activity truth source and manually log Garmin recovery metrics daily.",
            "Prioritize consistency across swim, bike, and run before adding intensity.",
            "Use the calendar approval flow to protect key sessions while adapting around fatigue.",
        ]
        if summary.get("recovery_flags"):
            recommendations.insert(0, "Treat current recovery flags as constraints, not trivia.")

        return {
            "title": "This Week's Training Focus",
            "summary": (
                f"You have {summary['volume_7d_hours']} hours in the last 7 days and "
                f"{summary['volume_28d_hours']} hours in the last 28 days. "
                "The next step is to build a stable week that preserves recovery while keeping "
                "triathlon frequency high."
            ),
            "recommendations": recommendations,
            "risks": summary.get("recovery_flags", []) + ["Ollama was unavailable, so this is rule-based."],
            "proposed_workouts": [
                {
                    "planned_date": anchor.isoformat(),
                    "sport": "run",
                    "sport_variant": "road_run",
                    "title": "Aerobic Run",
                    "description": "Conversational Z2 run. Stop early if R-CPD pressure or CFS fatigue escalates.",
                    "duration_minutes": 45 if recovery_bias else 60,
                    "distance_meters": None,
                    "intensity": intensity,
                    "surface": "road",
                    "location_suggestion": None,
                    "gear_suggestion": None,
                    "status": "planned",
                    "source": "derived",
                },
                {
                    "planned_date": (anchor + timedelta(days=2)).isoformat(),
                    "sport": "bike",
                    "sport_variant": "gravel_ride",
                    "title": "Controlled Bike Endurance",
                    "description": "Steady aerobic ride. Gravel is acceptable if it stays aerobic and does not replace race-specific TT work.",
                    "duration_minutes": 75 if recovery_bias else 105,
                    "distance_meters": None,
                    "intensity": intensity,
                    "surface": "gravel",
                    "location_suggestion": None,
                    "gear_suggestion": None,
                    "status": "planned",
                    "source": "derived",
                },
                {
                    "planned_date": (anchor + timedelta(days=4)).isoformat(),
                    "sport": "swim",
                    "sport_variant": "pool_swim",
                    "title": "Technique + Aerobic Swim",
                    "description": "Form-focused swim with relaxed breathing and low stress.",
                    "duration_minutes": 45,
                    "distance_meters": None,
                    "intensity": "easy",
                    "surface": "pool",
                    "location_suggestion": None,
                    "gear_suggestion": None,
                    "status": "planned",
                    "source": "derived",
                },
            ],
        }
