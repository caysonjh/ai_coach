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
from app.services.athlete_context import me_markdown_path, read_me_markdown
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
            select(Activity).where(Activity.start_time >= datetime.combine(since, time.min)).order_by(Activity.start_time.asc())
        ).all()
        metrics = session.exec(select(HealthMetric).where(HealthMetric.metric_date >= since).order_by(HealthMetric.metric_date.asc())).all()
        planned = session.exec(select(PlannedWorkout).where(PlannedWorkout.planned_date >= week_start).order_by(PlannedWorkout.planned_date.asc())).all()
        constraints = session.exec(
            select(ScheduleConstraint).where(ScheduleConstraint.constraint_date >= week_start)
        ).all()
        memories = session.exec(select(CoachMemory).order_by(CoachMemory.importance.desc()).limit(12)).all()
        locations = session.exec(select(TrainingLocation).where(TrainingLocation.active == True)).all()  # noqa: E712
        feedback = session.exec(select(WorkoutLocationFeedback).order_by(WorkoutLocationFeedback.feedback_date.desc()).limit(50)).all()
        gear = session.exec(select(GearItem).where(GearItem.active == True)).all()  # noqa: E712
        me_markdown = read_me_markdown()

        summary = summarize_training(activities, metrics, planned, today=today)
        effective_aggressiveness = self._effective_aggressiveness(request.message, request.aggressiveness)
        suggested_places = {
            "run": rank_locations(locations, feedback, Sport.run, SportVariant.road_run, "easy"),
            "trail_run": rank_locations(locations, feedback, Sport.run, SportVariant.trail_run, "easy"),
            "ride": rank_locations(locations, feedback, Sport.bike, SportVariant.road_ride, "endurance"),
            "gravel": rank_locations(locations, feedback, Sport.bike, SportVariant.gravel_ride, "endurance"),
            "swim": rank_locations(locations, feedback, Sport.swim, SportVariant.pool_swim, "technique"),
        }
        request_intent = self._classify_request(request.message, request.conversation_history)
        context = {
            "current_date": today.isoformat(),
            "week_start": week_start.isoformat(),
            "request_intent": request_intent,
            "requested_aggressiveness": request.aggressiveness,
            "effective_aggressiveness": effective_aggressiveness,
            "aggressiveness_guidance": self._aggressiveness_guidance(effective_aggressiveness),
            "profile": profile.model_dump() if profile else {},
            "athlete_profile_markdown": me_markdown,
            "athlete_profile_markdown_path": str(me_markdown_path()) if me_markdown else "",
            "training_summary": summary,
            "past_7_days_activity_digest": self._activity_digest(activities, today - timedelta(days=7)),
            "recent_activities": [activity.model_dump() for activity in activities[-20:]],
            "recent_health_metrics": [metric.model_dump() for metric in metrics[-40:]],
            "planned_workouts": [workout.model_dump() for workout in planned[:30]],
            "schedule_constraints": [constraint.model_dump() for constraint in constraints],
            "training_locations": [location.model_dump() for location in locations],
            "recent_location_feedback": [item.model_dump() for item in feedback],
            "ranked_location_suggestions": suggested_places,
            "gear": [item.model_dump() for item in gear],
            "memories": [memory.content for memory in memories],
            "conversation_history": [
                {"role": item.role, "content": item.content}
                for item in request.conversation_history[-12:]
                if item.role in {"user", "assistant"} and item.content.strip()
            ],
            "controls": {
                "aggressiveness": effective_aggressiveness,
                "autonomy": request.autonomy,
            },
        }

        system = (
            "You are a precise triathlon coach for an aspiring elite age-group 70.3 athlete. "
            "Account for R-CPD GI risk, chronic fatigue syndrome, strength, climbing, sleep, "
            "manual Garmin-style health metrics, gear mileage, local training places, and schedule constraints. "
            "Treat athlete_profile_markdown in the user context as durable first-person background about the athlete's "
            "goals, constraints, preferences, location, and training history. Use it in every recommendation. "
            "Answer the user's actual latest request first. If request_intent is analysis, analyze the data that was asked about and set proposed_workouts to an empty array. "
            "Do not invent or recommend workouts unless the latest message or conversation clearly asks for a plan, schedule, next workout, or workout adjustment. "
            "If request_intent is planning, use aggressiveness_guidance as a hard planning constraint: higher aggressiveness should produce meaningfully more load, specificity, or intensity, while still respecting recovery flags. "
            "When asked to analyze a past week, cite specific activities, approximate durations/distances, discipline balance, load pattern, strengths, gaps, and recovery implications from recent_activities and past_7_days_activity_digest. "
            "Use only these sport values in proposed_workouts: swim, bike, run, strength, climb, mobility, rest, other. "
            "Use only these sport_variant values: road_run, trail_run, road_ride, gravel_ride, mtb_ride, tt_ride, pool_swim, open_water_swim, strength, climb, mobility, rest, other. "
            "Use trail running, gravel cycling, and MTB only as controlled substitutions that preserve the intended triathlon stimulus. "
            "For run and bike workouts, suggest gear when gear context exists. For workouts where place context exists, suggest a location. "
            f"Today is {today.isoformat()}; interpret relative dates like tomorrow from that date and do not propose past dates. "
            "do not assume approval. Return only valid JSON matching the schema."
        )
        result = await self.ollama.chat_json(
            [
                {"role": "system", "content": system},
                {
                    "role": "user",
                    "content": (
                        "Use the provided context and conversation_history to answer the latest message. "
                        "Maintain continuity with the chat while still basing training advice on current data.\n"
                        f"Latest message: {request.message}\nContext: {context}"
                    ),
                },
            ],
            COACH_SCHEMA,
        )

        used_ollama = result is not None
        if result is None:
            result = self._fallback_response(request, summary, week_start, activities, request_intent, effective_aggressiveness)
        elif request_intent == "analysis":
            result = self._ground_analysis_result(result, activities, summary, today)
        elif request_intent == "planning":
            result = self._ground_planning_result(
                result,
                request,
                summary,
                week_start,
                activities,
                today,
                effective_aggressiveness,
            )

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
                aggressiveness=effective_aggressiveness,
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

    def _classify_request(self, message: str, history: list[Any]) -> str:
        normalized = message.lower()
        analysis_terms = ("analyze", "analysis", "review", "past week", "last week", "how did", "what happened", "where am i")
        planning_terms = (
            "plan",
            "schedule",
            "propose",
            "workout",
            "workouts",
            "tomorrow",
            "next week",
            "more aggressive",
            "less aggressive",
            "adjust",
            "reschedule",
        )
        if any(term in normalized for term in planning_terms):
            return "planning"
        if any(term in normalized for term in analysis_terms):
            return "analysis"
        recent_user_text = " ".join(item.content.lower() for item in history[-4:] if getattr(item, "role", "") == "user")
        if any(term in recent_user_text for term in planning_terms):
            return "planning"
        if any(term in recent_user_text for term in analysis_terms):
            return "analysis"
        return "coaching_chat"

    def _aggressiveness_guidance(self, aggressiveness: float) -> str:
        if aggressiveness < 0.3:
            return (
                "Conservative: reduce planned load, avoid intensity unless clearly fresh, bias toward recovery and consistency."
            )
        if aggressiveness < 0.55:
            return (
                "Balanced: maintain sustainable triathlon frequency and add intensity only where recent recovery and load allow."
            )
        if aggressiveness < 0.8:
            return (
                "Assertive: if recovery flags are acceptable, increase planned load roughly 10-20%, include a clear key bike/run stimulus, and keep easy days easy."
            )
        return (
            "High: plan at the upper safe edge for an elite age-group build, with meaningful specificity and load, but do not ignore acute recovery flags."
        )

    def _effective_aggressiveness(self, message: str, slider_value: float) -> float:
        normalized = message.lower()
        if "more aggressive" in normalized or "harder" in normalized or "push" in normalized:
            return max(slider_value, 0.75)
        if "less aggressive" in normalized or "easier" in normalized or "back off" in normalized:
            return min(slider_value, 0.25)
        return slider_value

    def _activity_digest(self, activities: list[Activity], since: date) -> dict[str, Any]:
        recent = [activity for activity in activities if activity.start_time.date() >= since]
        by_sport: dict[str, dict[str, float]] = {}
        for activity in recent:
            sport = activity.sport.value
            bucket = by_sport.setdefault(sport, {"count": 0, "hours": 0.0, "distance_km": 0.0})
            bucket["count"] += 1
            bucket["hours"] += round(activity.duration_seconds / 3600, 2)
            bucket["distance_km"] += round((activity.distance_meters or 0) / 1000, 2)
        return {
            "activities": [
                {
                    "date": activity.start_time.date().isoformat(),
                    "sport": activity.sport.value,
                    "variant": activity.sport_variant.value,
                    "name": activity.name,
                    "duration_min": round(activity.duration_seconds / 60),
                    "distance_km": round((activity.distance_meters or 0) / 1000, 2),
                    "source": activity.source.value,
                }
                for activity in recent
            ],
            "by_sport": by_sport,
        }

    def _ground_analysis_result(
        self,
        result: dict[str, Any],
        activities: list[Activity],
        summary: dict,
        today: date,
    ) -> dict[str, Any]:
        digest = self._activity_digest(activities, today - timedelta(days=7))
        activity_summaries = [
            f"{item['date']} {item['sport']} {item['duration_min']} min {item['distance_km']} km ({item['name']})"
            for item in digest["activities"]
        ]
        data_summary = (
            f"Past 7 days from imported data: {summary['activities_7d']} activities, "
            f"{summary['volume_7d_hours']} hours, split={summary['discipline_hours_7d']}. "
            f"Sessions: {'; '.join(activity_summaries) if activity_summaries else 'none'}."
        )
        result["title"] = result.get("title") or "Past Week Training Analysis"
        result["summary"] = f"{data_summary}\n\n{result.get('summary', '')}".strip()
        result["proposed_workouts"] = []
        return result

    def _ground_planning_result(
        self,
        result: dict[str, Any],
        request: CoachRequest,
        summary: dict,
        week_start: date,
        activities: list[Activity],
        today: date,
        effective_aggressiveness: float,
    ) -> dict[str, Any]:
        if self._is_low_quality_plan(result, today):
            return self._fallback_response(
                request,
                summary,
                week_start,
                activities,
                request_intent="planning",
                effective_aggressiveness=effective_aggressiveness,
            )

        digest = self._activity_digest(activities, today - timedelta(days=7))
        data_summary = (
            f"Grounded on current data: {summary['activities_7d']} activities, "
            f"{summary['volume_7d_hours']} hours in the last 7 days, split={summary['discipline_hours_7d']}. "
            f"Effective aggressiveness={effective_aggressiveness}."
        )
        result["summary"] = f"{data_summary}\n\n{result.get('summary', '')}".strip()
        result["recommendations"] = [
            f"Recent 7-day sport balance: {digest['by_sport']}.",
            *[str(item) for item in result.get("recommendations", [])],
        ]
        result["proposed_workouts"] = [
            item
            for item in result.get("proposed_workouts", [])
            if self._planned_date(item) >= today
        ]
        if not result["proposed_workouts"]:
            return self._fallback_response(
                request,
                summary,
                week_start,
                activities,
                request_intent="planning",
                effective_aggressiveness=effective_aggressiveness,
            )
        return result

    def _is_low_quality_plan(self, result: dict[str, Any], today: date) -> bool:
        title = str(result.get("title", "")).lower()
        summary = str(result.get("summary", "")).lower()
        workouts = result.get("proposed_workouts", [])
        if not isinstance(workouts, list) or not workouts:
            return True
        if any(self._planned_date(item) < today for item in workouts):
            return True
        if "chronic fatigue syndrome" in title and "training plan" in title:
            return True
        if "designed to help the athlete build a stable week" in summary:
            return True
        if len(workouts) == 1:
            item = workouts[0]
            duration = int(item.get("duration_minutes") or 0)
            sport = str(item.get("sport", "")).lower()
            description = str(item.get("description", "")).lower()
            title = str(item.get("title", "")).lower()
            if duration <= 35 and sport in {"bike", "ride"} and "easy" in f"{title} {description}":
                return True
        return False

    def _planned_date(self, item: dict[str, Any]) -> date:
        try:
            return date.fromisoformat(str(item.get("planned_date")))
        except Exception:
            return date.min

    def _fallback_response(
        self,
        request: CoachRequest,
        summary: dict,
        week_start: date,
        activities: list[Activity],
        request_intent: str,
        effective_aggressiveness: float,
    ) -> dict[str, Any]:
        if request_intent == "analysis":
            digest = self._activity_digest(activities, date.today() - timedelta(days=7))
            activity_lines = [
                f"{item['date']} {item['sport']}: {item['name']} ({item['duration_min']} min, {item['distance_km']} km)"
                for item in digest["activities"]
            ]
            return {
                "title": "Past Week Training Analysis",
                "summary": (
                    f"Over the last 7 days you logged {summary['activities_7d']} activities and "
                    f"{summary['volume_7d_hours']} hours. Discipline split: {summary['discipline_hours_7d']}. "
                    f"Recent sessions: {'; '.join(activity_lines) if activity_lines else 'none imported'}."
                ),
                "recommendations": [
                    "Use this analysis as the baseline before changing the next training block.",
                    "Look for whether swim, bike, and run frequency are all represented before adding extra intensity.",
                ],
                "risks": summary.get("recovery_flags", []) + ["Ollama was unavailable, so this is rule-based."],
                "proposed_workouts": [],
            }

        recovery_bias = effective_aggressiveness < 0.35 or bool(summary.get("recovery_flags"))
        intensity = "easy" if recovery_bias else "moderate"
        volume_multiplier = 0.8 if effective_aggressiveness < 0.3 else 1.0 if effective_aggressiveness < 0.55 else 1.2 if effective_aggressiveness < 0.8 else 1.35
        today = date.today()
        anchor = max(week_start, today)
        final_date = self._planning_end_date(request.message, anchor)
        recommendations = [
            f"Use the last 7 days as the load anchor: {summary['volume_7d_hours']} hours across {summary['discipline_hours_7d']}.",
            f"Apply the current aggressiveness setting as: {self._aggressiveness_guidance(effective_aggressiveness)}",
            "Keep the remaining week specific enough to progress, but do not stack hard run and bike stress on back-to-back days.",
        ]
        if summary.get("recovery_flags"):
            recommendations.insert(0, "Treat current recovery flags as constraints, not trivia.")

        return {
            "title": "This Week's Training Focus",
            "summary": (
                f"From the imported data you have {summary['volume_7d_hours']} hours in the last 7 days and "
                f"{summary['volume_28d_hours']} hours in the last 28 days. This plan covers "
                f"{anchor.isoformat()} through {final_date.isoformat()} and uses recent sport balance, not a generic template."
            ),
            "recommendations": recommendations,
            "risks": summary.get("recovery_flags", []) + ["Ollama was unavailable, so this is rule-based."],
            "proposed_workouts": [
                workout for workout in [
                {
                    "planned_date": anchor.isoformat(),
                    "sport": "run",
                    "sport_variant": "road_run",
                    "title": "Aerobic Run",
                    "description": "Conversational Z2 run. Stop early if R-CPD pressure or CFS fatigue escalates.",
                    "duration_minutes": round((45 if recovery_bias else 60) * volume_multiplier),
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
                    "duration_minutes": round((75 if recovery_bias else 105) * volume_multiplier),
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
                ] if date.fromisoformat(workout["planned_date"]) <= final_date
            ],
        }

    def _planning_end_date(self, message: str, anchor: date) -> date:
        normalized = message.lower()
        if "rest of the week" in normalized or "rest of week" in normalized:
            return anchor + timedelta(days=6 - anchor.weekday())
        return anchor + timedelta(days=6)
