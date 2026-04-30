from types import SimpleNamespace

from sqlmodel import Session, SQLModel, create_engine

from app.models.entities import AthleteProfile
from app.services import state_export


def test_context_export_includes_live_me_markdown(monkeypatch, tmp_path) -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    export_path = tmp_path / "coach_context.md"

    monkeypatch.setattr(
        state_export,
        "get_settings",
        lambda: SimpleNamespace(coach_context_export_path=str(export_path)),
    )
    monkeypatch.setattr(state_export, "read_me_markdown", lambda: "Cayson profile goals from me.md")
    monkeypatch.setattr(state_export, "me_markdown_path", lambda: tmp_path / "me.md")

    with Session(engine) as session:
        session.add(AthleteProfile(name="Cayson Hamilton", goal_summary="70.3 goals"))
        session.commit()

        path, bytes_written = state_export.export_coach_context(session)

    content = path.read_text(encoding="utf-8")
    assert path == export_path.resolve()
    assert bytes_written > 0
    assert "## me.md Profile" in content
    assert "Cayson profile goals from me.md" in content
