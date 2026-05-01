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
from app.schemas.api import (
    CoachActionEndpoint,
    CoachContextResponse,
    CoachRecordRequest,
    CoachRecordResponse,
    CoachRequest,
    CoachResponse,
    PlannedWorkoutCreate,
)
from app.services.analytics import summarize_training
from app.services.athlete_context import me_markdown_path, read_me_markdown
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
        self.action_endpoints = [
            CoachActionEndpoint(
                name="coach_context",
                method="POST",
                path="/api/chatgpt/context",
                purpose="Fetch grounded training context, summary, and recent training data before answering.",
            ),
            CoachActionEndpoint(
                name="coach_record",
                method="POST",
                path="/api/chatgpt/record",
                purpose="Persist a ChatGPT-authored coach response, insight, and proposed plan.",
            ),
            CoachActionEndpoint(
                name="apply_workouts",
                method="POST",
                path="/api/coach/apply-workouts",
                purpose="Apply approved workouts to the calendar after the user accepts a plan.",
            ),
        ]

    async def respond(self, session: Session, request: CoachRequest) -> CoachResponse:
        workspace = self._build_workspace(session, request)
        response = self._preview_response(request, workspace)
        insight = CoachInsight(
            insight_date=workspace["today"],
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
                week_start=workspace["week_start"],
                status="proposed",
                rationale=response.summary,
                aggressiveness=workspace["effective_aggressiveness"],
                autonomy=request.autonomy,
                payload=response.model_dump(mode="json"),
            )
        )
        session.commit()
        export_coach_context(session)
        return response

    def build_context(self, session: Session, request: CoachRequest) -> CoachContextResponse:
        workspace = self._build_workspace(session, request)
        return CoachContextResponse(
            generated_at=datetime.utcnow(),
            current_date=workspace["today"],
            week_start=workspace["week_start"],
            request_intent=workspace["request_intent"],
            effective_aggressiveness=workspace["effective_aggressiveness"],
            athlete_profile=self._compact_profile(workspace["profile"]),
            athlete_profile_markdown=self._truncate_text(workspace["athlete_profile_markdown"], 800),
            training_summary=workspace["summary"],
            past_7_days_activity_digest=workspace["past_7_days_activity_digest"],
            recent_activities=[self._compact_activity(activity) for activity in workspace["activities"][-5:]],
            recent_health_metrics=[self._compact_metric(metric) for metric in workspace["metrics"][-8:]],
            planned_workouts=[self._compact_workout(workout) for workout in workspace["planned"][:8]],
            schedule_constraints=[self._compact_constraint(constraint) for constraint in workspace["constraints"][:5]],
            training_locations=[self._compact_location(location) for location in workspace["locations"][:5]],
            recent_location_feedback=[self._compact_feedback(item) for item in workspace["feedback"][:8]],
            ranked_location_suggestions=self._compact_ranked_locations(workspace["ranked_location_suggestions"]),
            gear=[self._compact_gear(item) for item in workspace["gear"][:5]],
            memories=[self._truncate_text(memory.content, 240) for memory in workspace["memories"][:3]],
            coach_guidance=self._coach_guidance(workspace),
            action_endpoints=self.action_endpoints,
        )

    def record_coach_result(self, session: Session, request: CoachRecordRequest) -> CoachRecordResponse:
        today = date.today()
        week_start = today - timedelta(days=today.weekday())
        applied = 0

        insight = CoachInsight(
            insight_date=today,
            title=request.title,
            summary=request.summary,
            recommendations=request.recommendations,
            risks=request.risks,
            raw_payload={
                "source_message": request.source_message,
                "rationale": request.rationale,
                "autonomy": request.autonomy,
                "aggressiveness": request.aggressiveness,
                "proposed_workouts": [item.model_dump(mode="json") for item in request.proposed_workouts],
                "persist_workouts": request.persist_workouts,
            },
        )
        session.add(insight)
        session.add(
            CoachMemory(
                memory_type="chatgpt_result",
                content=f"{request.source_message}\n{request.summary}",
                importance=0.7,
            )
        )
        session.add(
            PlanVersion(
                week_start=week_start,
                status="approved" if request.persist_workouts else "proposed",
                rationale=request.rationale or request.summary,
                aggressiveness=request.aggressiveness,
                autonomy=request.autonomy,
                payload={
                    "title": request.title,
                    "summary": request.summary,
                    "recommendations": request.recommendations,
                    "risks": request.risks,
                    "proposed_workouts": [item.model_dump(mode="json") for item in request.proposed_workouts],
                },
            )
        )
        if request.persist_workouts:
            for workout in request.proposed_workouts:
                session.add(PlannedWorkout(**workout.model_dump()))
                applied += 1
        session.commit()
        export_coach_context(session)
        return CoachRecordResponse(
            saved_insight=True,
            saved_plan_version=True,
            applied_workouts=applied,
            message="Coach result recorded.",
        )

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

    def _build_workspace(self, session: Session, request: CoachRequest) -> dict[str, Any]:
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
        return {
            "today": today,
            "week_start": week_start,
            "profile": profile,
            "activities": activities,
            "metrics": metrics,
            "planned": planned,
            "constraints": constraints,
            "memories": memories,
            "locations": locations,
            "feedback": feedback,
            "gear": gear,
            "summary": summary,
            "effective_aggressiveness": effective_aggressiveness,
            "ranked_location_suggestions": suggested_places,
            "request_intent": request_intent,
            "athlete_profile_markdown": me_markdown,
            "past_7_days_activity_digest": self._activity_digest(activities, today - timedelta(days=7)),
        }

    def _compact_profile(self, profile: AthleteProfile | None) -> dict[str, Any]:
        if not profile:
            return {}
        return {
            "name": profile.name,
            "goal_summary": profile.goal_summary,
            "goal_race": profile.goal_race,
            "target_time": profile.target_time,
            "notes": self._truncate_text(profile.notes, 240),
        }

    def _compact_activity(self, activity: Activity) -> dict[str, Any]:
        return {
            "id": activity.id,
            "sport": activity.sport.value,
            "sport_variant": activity.sport_variant.value,
            "name": activity.name,
            "start_time": activity.start_time.isoformat(),
            "duration_minutes": round(activity.duration_seconds / 60, 1),
            "distance_meters": activity.distance_meters,
            "perceived_effort": activity.perceived_effort,
            "source": activity.source.value,
        }

    def _compact_metric(self, metric: HealthMetric) -> dict[str, Any]:
        value = metric.value_num if metric.value_num is not None else metric.value_text
        return {
            "id": metric.id,
            "metric_date": metric.metric_date.isoformat(),
            "metric_type": metric.metric_type.value,
            "custom_name": metric.custom_name,
            "value": value,
            "unit": metric.unit,
            "source": metric.source.value,
        }

    def _compact_workout(self, workout: PlannedWorkout) -> dict[str, Any]:
        return {
            "id": workout.id,
            "planned_date": workout.planned_date.isoformat(),
            "sport": workout.sport.value,
            "sport_variant": workout.sport_variant.value,
            "title": workout.title,
            "duration_minutes": workout.duration_minutes,
            "intensity": workout.intensity,
            "status": workout.status.value,
            "location_suggestion": workout.location_suggestion,
            "gear_suggestion": workout.gear_suggestion,
        }

    def _compact_constraint(self, constraint: ScheduleConstraint) -> dict[str, Any]:
        return {
            "id": constraint.id,
            "constraint_date": constraint.constraint_date.isoformat(),
            "label": constraint.label,
            "available_minutes": constraint.available_minutes,
            "unavailable": constraint.unavailable,
        }

    def _compact_location(self, location: TrainingLocation) -> dict[str, Any]:
        return {
            "id": location.id,
            "name": location.name,
            "sport": location.sport.value,
            "sport_variant": location.sport_variant.value,
            "surface": location.surface,
            "tags": self._truncate_text(location.tags, 120),
            "active": location.active,
        }

    def _compact_feedback(self, feedback: WorkoutLocationFeedback) -> dict[str, Any]:
        return {
            "id": feedback.id,
            "location_id": feedback.location_id,
            "activity_id": feedback.activity_id,
            "planned_workout_id": feedback.planned_workout_id,
            "feedback_date": feedback.feedback_date.isoformat(),
            "intended_stimulus": feedback.intended_stimulus,
            "rating": feedback.rating,
            "use_again": feedback.use_again,
        }

    def _compact_gear(self, gear: GearItem) -> dict[str, Any]:
        return {
            "id": gear.id,
            "name": gear.name,
            "gear_type": gear.gear_type.value,
            "distance_miles": round(gear.distance_meters / 1609.344, 1),
            "retire_distance_miles": round(gear.retire_distance_meters / 1609.344, 1) if gear.retire_distance_meters else None,
            "active": gear.active,
            "preferred_sport_variants": self._truncate_text(gear.preferred_sport_variants, 120),
            "preferred_surfaces": self._truncate_text(gear.preferred_surfaces, 120),
        }

    def _compact_ranked_locations(self, ranked: dict[str, Any]) -> dict[str, Any]:
        compact: dict[str, Any] = {}
        for key, entries in ranked.items():
            compact[key] = [
                {
                    "name": entry.get("name"),
                    "score": entry.get("score"),
                    "sport": entry.get("sport"),
                    "sport_variant": entry.get("sport_variant"),
                    "surface": entry.get("surface"),
                    "recent_feedback_count": len(entry.get("recent_feedback", [])),
                }
                for entry in entries[:3]
            ]
        return compact

    def _truncate_text(self, value: str | None, limit: int) -> str:
        if not value:
            return ""
        if len(value) <= limit:
            return value
        return value[: max(0, limit - 1)] + "…"

    def _coach_guidance(self, workspace: dict[str, Any]) -> list[str]:
        summary = workspace["summary"]
        guidance = [
            f"Current training load: {summary['volume_7d_hours']} hours in 7 days, {summary['volume_28d_hours']} hours in 28 days.",
            f"Request intent classified as {workspace['request_intent']}; use that mode before generating a reply.",
            f"Current aggressiveness target: {self._aggressiveness_guidance(workspace['effective_aggressiveness'])}",
            "Prefer specific guidance grounded in recent activities, metrics, places, gear, and constraints.",
        ]
        if summary.get("recovery_flags"):
            guidance.append("Recovery flags are present, so caution should override generic progression.")
        return guidance

    def _preview_response(self, request: CoachRequest, workspace: dict[str, Any]) -> CoachResponse:
        request_intent = workspace["request_intent"]
        summary = workspace["summary"]
        activities = workspace["activities"]
        week_start = workspace["week_start"]
        today = workspace["today"]
        effective_aggressiveness = workspace["effective_aggressiveness"]

        if request_intent == "analysis":
            result = self._fallback_response(
                request,
                summary,
                week_start,
                activities,
                request_intent=request_intent,
                effective_aggressiveness=effective_aggressiveness,
            )
            return self._coerce_response(result, used_ollama=False)

        if request_intent == "planning":
            result = self._fallback_response(
                request,
                summary,
                week_start,
                activities,
                request_intent=request_intent,
                effective_aggressiveness=effective_aggressiveness,
            )
            return self._coerce_response(result, used_ollama=False)

        result = {
            "title": "Current Training Briefing",
            "summary": (
                f"Your current load is {summary['volume_7d_hours']} hours over the last 7 days and "
                f"{summary['volume_28d_hours']} hours over the last 28 days. "
                f"The latest request '{request.message.strip()}' was treated as a coaching conversation rather than a plan request. "
                f"Use {today.isoformat()} as the anchor date and keep the advice grounded in recent activities, health metrics, places, and constraints."
            ),
            "recommendations": self._chat_recommendations(workspace),
            "risks": summary.get("recovery_flags", []) or ["No recovery flags detected in the current summary."],
            "proposed_workouts": [],
        }
        return self._coerce_response(result, used_ollama=False)

    def _chat_recommendations(self, workspace: dict[str, Any]) -> list[str]:
        summary = workspace["summary"]
        recommendations = [
            f"Recent sport balance: {summary['discipline_hours_7d']}.",
            "Use the action context to generate an answer that cites specific recent sessions and current readiness.",
        ]
        if not summary["discipline_hours_7d"].get("swim"):
            recommendations.append("Swim volume is currently absent or low relative to the rest of the week.")
        if workspace["past_7_days_activity_digest"]["by_sport"].get("run", {}).get("hours", 0) > workspace["past_7_days_activity_digest"]["by_sport"].get("bike", {}).get("hours", 0) * 1.2:
            recommendations.append("Run load is outpacing bike load; watch lower-leg fatigue when increasing intensity.")
        return recommendations

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
        if any(term in normalized for term in analysis_terms):
            return "analysis"
        if any(term in normalized for term in planning_terms):
            return "planning"
        recent_user_text = " ".join(item.content.lower() for item in history[-4:] if getattr(item, "role", "") == "user")
        if any(term in recent_user_text for term in analysis_terms):
            return "analysis"
        if any(term in recent_user_text for term in planning_terms):
            return "planning"
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
        result["title"] = "Past Week Training Analysis"
        result["summary"] = self._analysis_summary(data_summary, result)
        result["recommendations"] = self._analysis_recommendations(digest, summary)
        result["risks"] = summary.get("recovery_flags", [])
        result["proposed_workouts"] = []
        return result

    def _analysis_summary(self, data_summary: str, result: dict[str, Any]) -> str:
        model_summary = str(result.get("summary", "")).strip()
        generic_fragments = (
            "training plan is designed",
            "build a stable week",
            "propose a simple",
            "workout for tomorrow",
        )
        if not model_summary or any(fragment in model_summary.lower() for fragment in generic_fragments):
            return data_summary
        return f"{data_summary}\n\nCoach interpretation: {model_summary}"

    def _analysis_recommendations(self, digest: dict[str, Any], summary: dict) -> list[str]:
        by_sport = digest["by_sport"]
        recommendations = [
            f"Sport balance this week: {by_sport}.",
            "Use this review to decide what the next block needs; do not add workouts until you ask for planning.",
        ]
        if not by_sport.get("swim"):
            recommendations.append("Swim frequency is absent in the last 7 days, so note that as a triathlon-specific gap.")
        if by_sport.get("run", {}).get("hours", 0) > by_sport.get("bike", {}).get("hours", 0) * 1.2:
            recommendations.append("Run load is relatively high versus bike load; watch lower-leg fatigue before adding intensity.")
        if summary.get("recovery_flags"):
            recommendations.append("Recovery flags are present, so interpret the week through fatigue and readiness first.")
        return recommendations

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
