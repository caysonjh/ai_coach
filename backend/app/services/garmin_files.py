from pathlib import Path

from sqlmodel import Session, select

from app.core.config import get_settings
from app.models.entities import Activity, HealthMetric, ImportJob, Source
from app.schemas.api import GarminImportStatus
from app.services.imports import (
    parse_activity_csv,
    parse_fit_if_available,
    parse_gpx,
    parse_health_metrics_csv,
    parse_tcx,
)

SUPPORTED_EXTENSIONS = [".csv", ".tcx", ".gpx", ".fit"]


def scan_garmin_directory(session: Session) -> GarminImportStatus:
    settings = get_settings()
    import_dir = Path(settings.garmin_import_dir).expanduser().resolve()
    import_dir.mkdir(parents=True, exist_ok=True)

    files = [
        path
        for path in sorted(import_dir.rglob("*"))
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
    ]

    imported_activities = 0
    imported_metrics = 0
    skipped = 0
    failed = 0

    for path in files:
        source_id = str(path.relative_to(import_dir))
        existing_job = session.exec(
            select(ImportJob).where(ImportJob.source == Source.file_import, ImportJob.filename == source_id)
        ).first()
        if existing_job and existing_job.status == "completed":
            skipped += 1
            continue

        job = existing_job or ImportJob(source=Source.file_import, filename=source_id)
        try:
            activities, metrics, message = _parse_file(path, source_id)
            for activity in activities:
                if not _activity_exists(session, activity.source_id):
                    session.add(activity)
                    imported_activities += 1
            for metric in metrics:
                session.add(metric)
                imported_metrics += 1
            job.status = "completed" if activities or metrics else "skipped"
            job.rows_imported = len(activities) + len(metrics)
            job.message = message
        except Exception as exc:
            failed += 1
            job.status = "failed"
            job.message = str(exc)
        session.add(job)

    session.commit()
    return GarminImportStatus(
        import_dir=str(import_dir),
        supported_extensions=SUPPORTED_EXTENSIONS,
        files_seen=len(files),
        imported_activities=imported_activities,
        imported_metrics=imported_metrics,
        skipped_files=skipped,
        failed_files=failed,
        message=(
            "Garmin import scan complete. CSV, TCX, GPX, and FIT files are supported when "
            "fitdecode is installed."
        ),
    )


def _parse_file(path: Path, source_id: str) -> tuple[list[Activity], list[HealthMetric], str]:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        content = path.read_text(encoding="utf-8-sig")
        header = content.splitlines()[0].lower() if content.splitlines() else ""
        if "metric_type" in header:
            metrics = parse_health_metrics_csv(content)
            return [], metrics, f"Imported {len(metrics)} health metrics from CSV."
        activities = parse_activity_csv(content)
        return activities, [], f"Imported {len(activities)} activities from CSV."
    if suffix == ".tcx":
        activities = parse_tcx(path.read_text(encoding="utf-8"), source_id)
        return activities, [], f"Imported {len(activities)} activities from TCX."
    if suffix == ".gpx":
        return [parse_gpx(path.read_text(encoding="utf-8"), source_id)], [], "Imported GPX activity."
    if suffix == ".fit":
        activity = parse_fit_if_available(path, source_id)
        if activity is None:
            return [], [], "Skipped FIT file because no FIT parser is available."
        return [activity], [], "Imported FIT activity."
    return [], [], "Unsupported extension."


def _activity_exists(session: Session, source_id: str | None) -> bool:
    if not source_id:
        return False
    return session.exec(
        select(Activity).where(Activity.source == Source.file_import, Activity.source_id == source_id)
    ).first() is not None
