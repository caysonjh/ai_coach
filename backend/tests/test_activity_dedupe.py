from datetime import datetime, timezone

from sqlmodel import Session, SQLModel, create_engine, select

from app.models.entities import Activity, Source, Sport, SportVariant
from app.services.activity_dedupe import deduplicate_existing_activities, upsert_activity


def test_upsert_reuses_same_strava_activity() -> None:
    with _session() as session:
        first = Activity(
            source=Source.strava,
            source_id="123",
            sport=Sport.run,
            name="Morning Run",
            start_time=datetime(2026, 4, 30, 14, 0, tzinfo=timezone.utc),
            duration_seconds=3600,
            distance_meters=10000,
        )
        second = Activity(
            source=Source.strava,
            source_id="123",
            sport=Sport.run,
            sport_variant=SportVariant.trail_run,
            gear_id="shoe-1",
            name="Morning Run",
            start_time=datetime(2026, 4, 30, 14, 0, tzinfo=timezone.utc),
            duration_seconds=3600,
            distance_meters=10000,
            avg_hr=145,
        )

        _, first_created = upsert_activity(session, first)
        merged, second_created = upsert_activity(session, second)
        session.commit()

        assert first_created is True
        assert second_created is False
        assert merged.gear_id == "shoe-1"
        assert merged.avg_hr == 145
        assert len(session.exec(select(Activity)).all()) == 1


def test_upsert_merges_strava_and_garmin_file_activity() -> None:
    with _session() as session:
        strava = Activity(
            source=Source.strava,
            source_id="strava-123",
            sport=Sport.bike,
            sport_variant=SportVariant.gravel_ride,
            gear_id="bike-1",
            name="Gravel Tempo",
            start_time=datetime(2026, 4, 30, 15, 0, tzinfo=timezone.utc),
            duration_seconds=5400,
            distance_meters=42000,
            raw_payload={"id": "strava-123"},
        )
        garmin = Activity(
            source=Source.file_import,
            source_id="activity.fit",
            sport=Sport.bike,
            name="Imported Garmin FIT Bike",
            start_time=datetime(2026, 4, 30, 15, 1, tzinfo=timezone.utc),
            duration_seconds=5420,
            distance_meters=42100,
            avg_power=230,
            max_power=612,
            raw_payload={"source_file": "activity.fit"},
        )

        _, strava_created = upsert_activity(session, strava)
        merged, garmin_created = upsert_activity(session, garmin)
        session.commit()

        assert strava_created is True
        assert garmin_created is False
        assert merged.name == "Gravel Tempo"
        assert merged.gear_id == "bike-1"
        assert merged.avg_power == 230
        assert merged.max_power == 612
        assert merged.raw_payload["merged_sources"] == [
            {"source": "strava", "source_id": "strava-123"},
            {"source": "file_import", "source_id": "activity.fit"}
        ]
        assert len(session.exec(select(Activity)).all()) == 1


def test_deduplicate_existing_activities_removes_prior_duplicates() -> None:
    with _session() as session:
        session.add(
            Activity(
                source=Source.strava,
                source_id="strava-123",
                sport=Sport.run,
                name="Run",
                start_time=datetime(2026, 4, 30, 14, 0, tzinfo=timezone.utc),
                duration_seconds=1800,
                distance_meters=5000,
            )
        )
        session.add(
            Activity(
                source=Source.file_import,
                source_id="run.fit",
                sport=Sport.run,
                name="Imported Garmin FIT Run",
                start_time=datetime(2026, 4, 30, 14, 2, tzinfo=timezone.utc),
                duration_seconds=1810,
                distance_meters=5020,
                avg_hr=150,
            )
        )
        session.commit()

        removed = deduplicate_existing_activities(session)

        activities = session.exec(select(Activity)).all()
        assert removed == 1
        assert len(activities) == 1
        assert activities[0].avg_hr == 150


def _session() -> Session:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return Session(engine)
