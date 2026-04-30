from pathlib import Path


MAX_ME_MD_CHARS = 20000


def read_me_markdown() -> str:
    me_path = _repo_root() / "me.md"
    if not me_path.exists():
        return ""
    return me_path.read_text(encoding="utf-8")[:MAX_ME_MD_CHARS]


def me_markdown_path() -> Path:
    return (_repo_root() / "me.md").resolve()


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]
