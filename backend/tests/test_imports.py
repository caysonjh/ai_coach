from app.models.entities import MetricType
from app.services.imports import parse_gpx, parse_health_metrics_csv


def test_parse_health_metrics_csv() -> None:
    content = "\n".join(
        [
            "metric_date,metric_type,value_num,unit,notes",
            "2026-04-29,training_readiness,72,score,solid recovery",
        ]
    )
    metrics = parse_health_metrics_csv(content)
    assert len(metrics) == 1
    assert metrics[0].metric_type == MetricType.training_readiness
    assert metrics[0].value_num == 72


def test_parse_gpx_activity() -> None:
    content = """<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="test" xmlns="http://www.topografix.com/GPX/1/1">
  <trk>
    <name>Morning Run</name>
    <trkseg>
      <trkpt lat="40.0" lon="-111.0"><time>2026-04-29T12:00:00Z</time></trkpt>
      <trkpt lat="40.001" lon="-111.001"><time>2026-04-29T12:05:00Z</time></trkpt>
    </trkseg>
  </trk>
</gpx>
"""
    activity = parse_gpx(content, "sample.gpx")
    assert activity.name == "Morning Run"
    assert activity.duration_seconds == 300
    assert activity.distance_meters
