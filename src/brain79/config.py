from pathlib import Path

_project_root: Path | None = None


def set_project_root(path: Path) -> None:
    """Set the project root at server startup."""
    global _project_root
    _project_root = path.resolve()


def get_project_root() -> Path:
    """Resolve project root from state, env var, or cwd (in that order)."""
    if _project_root is not None:
        return _project_root

    import os

    env_root = os.environ.get("BRAIN79_PROJECT_ROOT")
    if env_root:
        return Path(env_root).resolve()

    return Path.cwd().resolve()


def get_wiki_root() -> Path:
    return get_project_root() / ".brain-79"
