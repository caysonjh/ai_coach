from datetime import date, timedelta

from app.models.entities import Activity, HealthMetric, MetricType, PlannedWorkout, Sport


def summarize_training(
    activities: list[Activity],
    health_metrics: list[HealthMetric],
    planned: list[PlannedWorkout],
    today: date | None = None,
) -> dict:
    today = today or date.today()
    start_7 = today - timedelta(days=7)
    start_28 = today - timedelta(days=28)

    def in_window(activity: Activity, start: date) -> bool:
        return activity.start_time.date() >= start

    weekly = [activity for activity in activities if in_window(activity, start_7)]
    monthly = [activity for activity in activities if in_window(activity, start_28)]

    discipline_seconds = {sport.value: 0 for sport in Sport}
    for activity in weekly:
        discipline_seconds[activity.sport.value] = (
            discipline_seconds.get(activity.sport.value, 0) + activity.duration_seconds
        )

    latest_metrics: dict[str, dict] = {}
    for metric in sorted(health_metrics, key=lambda item: item.metric_date):
        latest_metrics[metric.metric_type.value] = {
            "date": metric.metric_date.isoformat(),
            "value": metric.value_num if metric.value_num is not None else metric.value_text,
            "unit": metric.unit,
            "source": metric.source.value,
        }

    completed = sum(1 for workout in planned if workout.status.value == "completed")
    missed = sum(1 for workout in planned if workout.status.value == "missed")
    planned_count = len(planned)

    return {
        "volume_7d_hours": round(sum(a.duration_seconds for a in weekly) / 3600, 2),
        "volume_28d_hours": round(sum(a.duration_seconds for a in monthly) / 3600, 2),
        "activities_7d": len(weekly),
        "activities_28d": len(monthly),
        "discipline_hours_7d": {
            sport: round(seconds / 3600, 2)
            for sport, seconds in discipline_seconds.items()
            if seconds > 0
        },
        "latest_metrics": latest_metrics,
        "calendar_adherence": {
            "planned": planned_count,
            "completed": completed,
            "missed": missed,
        },
        "recovery_flags": recovery_flags(latest_metrics),
    }


def recovery_flags(latest_metrics: dict[str, dict]) -> list[str]:
    flags: list[str] = []

    readiness = latest_metrics.get(MetricType.training_readiness.value, {}).get("value")
    sleep = latest_metrics.get(MetricType.sleep_score.value, {}).get("value")
    resting_hr = latest_metrics.get(MetricType.resting_hr.value, {}).get("value")
    body_battery = latest_metrics.get(MetricType.body_battery.value, {}).get("value")

    if isinstance(readiness, (int, float)) and readiness < 45:
        flags.append("Training Readiness is low; bias toward aerobic maintenance or recovery.")
    if isinstance(sleep, (int, float)) and sleep < 60:
        flags.append("Sleep score is low; avoid stacking high intensity today.")
    if isinstance(body_battery, (int, float)) and body_battery < 35:
        flags.append("Body Battery is low; reduce session complexity and fueling risk.")
    if isinstance(resting_hr, (int, float)) and resting_hr > 55:
        flags.append("Resting HR is elevated relative to your usual low-40s baseline.")

    return flags
