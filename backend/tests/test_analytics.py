from datetime import date, datetime

from app.models.entities import Activity, HealthMetric, MetricType, Source, Sport
from app.services.analytics import summarize_training


def test_summary_includes_recovery_flags_for_low_readiness() -> None:
    activity = Activity(
        source=Source.manual,
        sport=Sport.run,
        name="Run",
        start_time=datetime(2026, 4, 28, 8, 0),
        duration_seconds=3600,
    )
    metric = HealthMetric(
        metric_date=date(2026, 4, 29),
        metric_type=MetricType.training_readiness,
        value_num=30,
        unit="score",
    )
    summary = summarize_training([activity], [metric], [], today=date(2026, 4, 29))
    assert summary["volume_7d_hours"] == 1.0
    assert summary["recovery_flags"]
