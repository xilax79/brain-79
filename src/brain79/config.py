from pathlib import Path

_project_root: Path | None = None


def set_project_root(path: Path | None) -> None:
    """Set the project root at server startup or reset with None."""
    global _project_root
    if path is None:
        _project_root = None
    else:
        _project_root = path.resolve()


def get_project_root() -> Path:
    """Resolve project root from explicit override, BRAIN79_PROJECT_ROOT, or upward ancestor walk."""
    if _project_root is not None:
        return _project_root

    import os

    env_root = os.environ.get("BRAIN79_PROJECT_ROOT")
    if env_root:
        return Path(env_root).resolve()

    cwd = Path.cwd().resolve()
    if (cwd / ".brain-79").is_dir():
        return cwd

    if (cwd / ".git").exists():
        return cwd

    for parent in cwd.parents:
        if (parent / ".brain-79").is_dir():
            return parent
        if (parent / ".git").exists():
            return cwd

    return cwd


def get_wiki_root() -> Path:
    return get_project_root() / ".brain-79"
