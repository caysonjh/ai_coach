from app.models.entities import MetricType
from app.services.metrics import metric_options


def test_metric_options_include_garmin_training_readiness() -> None:
    values = {option["value"] for option in metric_options()}
    assert MetricType.training_readiness.value in values
    assert MetricType.endurance_score.value in values
    assert MetricType.hill_score.value in values
