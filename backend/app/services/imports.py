import csv
import xml.etree.ElementTree as ET
from datetime import timezone
from datetime import datetime
from io import StringIO
from pathlib import Path

from app.models.entities import Activity, HealthMetric, MetricType, Source, Sport


def parse_activity_csv(content: str) -> list[Activity]:
    reader = csv.DictReader(StringIO(content))
    activities: list[Activity] = []
    for row in reader:
        sport = Sport(row.get("sport", "other").lower())
        activities.append(
            Activity(
                source=Source.file_import,
                source_id=row.get("source_id") or None,
                sport=sport,
                name=row.get("name") or f"Imported {sport.value}",
                start_time=datetime.fromisoformat(row["start_time"]),
                duration_seconds=int(float(row.get("duration_seconds") or 0)),
                distance_meters=_float_or_none(row.get("distance_meters")),
                elevation_meters=_float_or_none(row.get("elevation_meters")),
                avg_hr=_float_or_none(row.get("avg_hr")),
                max_hr=_float_or_none(row.get("max_hr")),
                avg_power=_float_or_none(row.get("avg_power")),
                max_power=_float_or_none(row.get("max_power")),
                calories=_float_or_none(row.get("calories")),
                notes=row.get("notes") or "",
                raw_payload=row,
            )
        )
    return activities


def parse_health_metrics_csv(content: str) -> list[HealthMetric]:
    reader = csv.DictReader(StringIO(content))
    metrics: list[HealthMetric] = []
    for row in reader:
        metric_type = MetricType(row.get("metric_type", "custom"))
        value = row.get("value_num") or row.get("value") or ""
        metrics.append(
            HealthMetric(
                metric_date=datetime.fromisoformat(row["metric_date"]).date(),
                metric_type=metric_type,
                custom_name=row.get("custom_name") or None,
                value_num=_float_or_none(value),
                value_text=None if _float_or_none(value) is not None else value,
                unit=row.get("unit") or None,
                source=Source.file_import,
                confidence=_float_or_none(row.get("confidence")) or 0.9,
                notes=row.get("notes") or "",
            )
        )
    return metrics


def parse_gpx(content: str, source_id: str) -> Activity:
    root = ET.fromstring(content)
    ns = {"gpx": root.tag.split("}")[0].strip("{")} if root.tag.startswith("{") else {}

    def findall(path: str):
        return root.findall(path, ns) if ns else root.findall(path.replace("gpx:", ""))

    points = findall(".//gpx:trkpt")
    times: list[datetime] = []
    distance = 0.0
    prev: tuple[float, float] | None = None
    for point in points:
        lat = float(point.attrib.get("lat", "0"))
        lon = float(point.attrib.get("lon", "0"))
        time_node = point.find("gpx:time", ns) if ns else point.find("time")
        if time_node is not None and time_node.text:
            times.append(_parse_time(time_node.text))
        if prev:
            distance += _haversine(prev[0], prev[1], lat, lon)
        prev = (lat, lon)

    start = min(times) if times else datetime.now(timezone.utc)
    duration = int((max(times) - min(times)).total_seconds()) if len(times) > 1 else 0
    name_node = root.find(".//gpx:name", ns) if ns else root.find(".//name")
    return Activity(
        source=Source.file_import,
        source_id=source_id,
        sport=Sport.other,
        name=name_node.text if name_node is not None and name_node.text else "Imported GPX Activity",
        start_time=start,
        duration_seconds=max(duration, 0),
        distance_meters=distance or None,
        raw_payload={"source_file": source_id, "format": "gpx"},
    )


def parse_tcx(content: str, source_id: str) -> list[Activity]:
    root = ET.fromstring(content)
    ns = {"tcx": root.tag.split("}")[0].strip("{")} if root.tag.startswith("{") else {}

    def findall(path: str):
        return root.findall(path, ns) if ns else root.findall(path.replace("tcx:", ""))

    activities: list[Activity] = []
    for node in findall(".//tcx:Activity"):
        sport = _sport_from_string(node.attrib.get("Sport", "other"))
        lap_nodes = node.findall("tcx:Lap", ns) if ns else node.findall("Lap")
        start_text = node.attrib.get("StartTime")
        start = _parse_time(start_text) if start_text else datetime.now(timezone.utc)
        duration = 0
        distance = 0.0
        calories = 0.0
        avg_hr_values: list[float] = []
        max_hr_values: list[float] = []
        for lap in lap_nodes:
            duration += int(float(_text(lap, "TotalTimeSeconds", ns) or 0))
            distance += float(_text(lap, "DistanceMeters", ns) or 0)
            calories += float(_text(lap, "Calories", ns) or 0)
            avg_hr = _text(lap, "AverageHeartRateBpm/Value", ns)
            max_hr = _text(lap, "MaximumHeartRateBpm/Value", ns)
            if avg_hr:
                avg_hr_values.append(float(avg_hr))
            if max_hr:
                max_hr_values.append(float(max_hr))
        activities.append(
            Activity(
                source=Source.file_import,
                source_id=source_id,
                sport=sport,
                name=f"Imported Garmin {sport.value.title()}",
                start_time=start,
                duration_seconds=duration,
                distance_meters=distance or None,
                avg_hr=sum(avg_hr_values) / len(avg_hr_values) if avg_hr_values else None,
                max_hr=max(max_hr_values) if max_hr_values else None,
                calories=calories or None,
                raw_payload={"source_file": source_id, "format": "tcx"},
            )
        )
    return activities


def parse_fit_if_available(path: Path, source_id: str) -> Activity | None:
    decoded = _parse_fitdecode(path, source_id)
    if decoded:
        return decoded

    try:
        from fitparse import FitFile  # type: ignore
    except Exception:
        return None

    fitfile = FitFile(str(path))
    sessions = list(fitfile.get_messages("session"))
    if not sessions:
        return None

    values = {field.name: field.value for field in sessions[-1]}
    sport = _sport_from_string(str(values.get("sport", "other")))
    start = values.get("start_time") or datetime.now(timezone.utc)
    if isinstance(start, datetime) and start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    return Activity(
        source=Source.file_import,
        source_id=source_id,
        sport=sport,
        name=f"Imported Garmin FIT {sport.value.title()}",
        start_time=start,
        duration_seconds=int(values.get("total_timer_time") or values.get("total_elapsed_time") or 0),
        distance_meters=_float_or_none(values.get("total_distance")),
        elevation_meters=_float_or_none(values.get("total_ascent")),
        avg_hr=_float_or_none(values.get("avg_heart_rate")),
        max_hr=_float_or_none(values.get("max_heart_rate")),
        avg_power=_float_or_none(values.get("avg_power")),
        max_power=_float_or_none(values.get("max_power")),
        calories=_float_or_none(values.get("total_calories")),
        raw_payload={"source_file": source_id, "format": "fit", "session": str(values)},
    )


def _parse_fitdecode(path: Path, source_id: str) -> Activity | None:
    try:
        import fitdecode  # type: ignore
    except Exception:
        return None

    session_values: dict = {}
    with fitdecode.FitReader(str(path)) as fit:
        for frame in fit:
            if isinstance(frame, fitdecode.FitDataMessage) and frame.name == "session":
                for field in frame.fields:
                    session_values[field.name] = field.value

    if not session_values:
        return None

    sport = _sport_from_string(str(session_values.get("sport", "other")))
    start = session_values.get("start_time") or datetime.now(timezone.utc)
    if isinstance(start, datetime) and start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    return Activity(
        source=Source.file_import,
        source_id=source_id,
        sport=sport,
        name=f"Imported Garmin FIT {sport.value.title()}",
        start_time=start,
        duration_seconds=int(
            session_values.get("total_timer_time") or session_values.get("total_elapsed_time") or 0
        ),
        distance_meters=_float_or_none(session_values.get("total_distance")),
        elevation_meters=_float_or_none(session_values.get("total_ascent")),
        avg_hr=_float_or_none(session_values.get("avg_heart_rate")),
        max_hr=_float_or_none(session_values.get("max_heart_rate")),
        avg_power=_float_or_none(session_values.get("avg_power")),
        max_power=_float_or_none(session_values.get("max_power")),
        calories=_float_or_none(session_values.get("total_calories")),
        raw_payload={"source_file": source_id, "format": "fit", "session": str(session_values)},
    )


def _float_or_none(value: str | None) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _text(node: ET.Element, path: str, ns: dict[str, str]) -> str | None:
    query = "/".join(f"tcx:{part}" for part in path.split("/")) if ns else path
    found = node.find(query, ns) if ns else node.find(query)
    return found.text if found is not None else None


def _sport_from_string(value: str) -> Sport:
    normalized = value.lower()
    if "run" in normalized:
        return Sport.run
    if "bike" in normalized or "cycling" in normalized or "biking" in normalized:
        return Sport.bike
    if "swim" in normalized:
        return Sport.swim
    if "strength" in normalized:
        return Sport.strength
    if "climb" in normalized:
        return Sport.climb
    return Sport.other


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    from math import asin, cos, radians, sin, sqrt

    radius_m = 6371000
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * radius_m * asin(sqrt(a))
