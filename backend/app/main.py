from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session, select

from app.api.routes import router
from app.db.session import engine, init_db
from app.models.entities import AthleteProfile, CoachMemory
from app.services.activity_dedupe import deduplicate_existing_activities
from app.services.garmin_files import scan_garmin_directory
from app.services.state_export import export_coach_context


def create_app() -> FastAPI:
    app = FastAPI(title="AI Coach", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router)

    @app.on_event("startup")
    def on_startup() -> None:
        init_db()
        seed_profile()
        with Session(engine) as session:
            deduplicate_existing_activities(session)
            scan_garmin_directory(session)
            export_coach_context(session)

    return app


def seed_profile() -> None:
    with Session(engine) as session:
        existing = session.exec(select(AthleteProfile).limit(1)).first()
        if existing:
            return
        me_path = Path(__file__).resolve().parents[2] / "me.md"
        notes = me_path.read_text(encoding="utf-8") if me_path.exists() else ""
        profile = AthleteProfile(
            name="Cayson Hamilton",
            goal_summary=(
                "Aspiring elite age-group triathlete targeting Ironman 70.3 World "
                "Championship qualification and a sub-5-hour 70.3."
            ),
            goal_race="Boise 2026 70.3",
            target_time="sub-5:00",
            notes=notes[:12000],
        )
        session.add(profile)
        session.add(
            CoachMemory(
                memory_type="profile",
                content=(
                    "Cayson has R-CPD, chronic fatigue syndrome, ADHD/depression, "
                    "FTP >300 W, VO2max around 60, and wants flexible A/B training "
                    "that adapts around fatigue and life constraints."
                ),
                importance=1.0,
            )
        )
        session.commit()


app = create_app()
