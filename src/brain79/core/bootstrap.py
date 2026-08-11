"""Core module for project bootstrapping manifest generation."""

from datetime import UTC, datetime
import json
import os
from pathlib import Path

import filelock

from brain79.config import get_project_root, get_wiki_root

# Absolute maximum bytes of file content to include in the manifest
_TOTAL_CONTENT_BUDGET_BYTES: int = 80_000

# Max bytes for any single file in root signals
_MAX_FILE_BYTES: int = 8_000

# Max entries in the depth-1 tree listing
_TREE_MAX_ENTRIES: int = 60

# Max files collected per scope path
_SCOPE_FILES_PER_PATH: int = 15

# Max bytes per scope file
_SCOPE_FILE_MAX_BYTES: int = 4_000

# Directories always excluded from any walk
_EXCLUDED_DIRS: frozenset[str] = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        "__pycache__",
        ".mypy_cache",
        ".ruff_cache",
        ".pytest_cache",
        "node_modules",
        ".venv",
        "venv",
        "env",
        ".env",
        "dist",
        "build",
        "target",
        ".next",
        ".nuxt",
        ".brain-79",
    }
)

# Binary file extensions — skip entirely (no content, not even in tree key files)
_BINARY_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".bmp",
        ".ico",
        ".svg",
        ".pdf",
        ".doc",
        ".docx",
        ".xls",
        ".xlsx",
        ".ppt",
        ".pptx",
        ".zip",
        ".tar",
        ".gz",
        ".bz2",
        ".xz",
        ".7z",
        ".rar",
        ".exe",
        ".dll",
        ".so",
        ".dylib",
        ".a",
        ".o",
        ".pyc",
        ".pyo",
        ".whl",
        ".egg",
        ".mp3",
        ".mp4",
        ".avi",
        ".mov",
        ".wav",
        ".db",
        ".sqlite",
        ".sqlite3",
    }
)

# Files whose content is skipped (presence in tree is noted; no content in manifest)
_PRESENCE_ONLY_FILES: frozenset[str] = frozenset(
    {
        ".gitignore",
        ".gitattributes",
        ".editorconfig",
        ".prettierrc",
        ".eslintrc",
        "uv.lock",
        "package-lock.json",
        "yarn.lock",
        "Pipfile.lock",
        "poetry.lock",
    }
)


def _truncate_file(path: Path, max_bytes: int) -> tuple[str, bool]:
    """Read up to max_bytes from a regular file.

    Never loads full file into memory if size exceeds max_bytes.
    Returns (content, was_truncated).
    Returns ("", False) on any OS error or empty file.
    """
    try:
        size = path.stat().st_size
    except OSError:
        return ("", False)

    if size == 0:
        return ("", False)

    if size <= max_bytes:
        try:
            return (path.read_text(encoding="utf-8", errors="replace"), False)
        except OSError:
            return ("", False)

    try:
        with path.open("rb") as f:
            raw = f.read(max_bytes)
    except OSError:
        return ("", False)

    text = raw.decode("utf-8", errors="replace")
    marker = f"\n\n[truncated at {max_bytes // 1000}k — full file is {size // 1000}k]"
    return (text + marker, True)


def _normalize_scope(scope: str | None) -> str | None:
    if scope is None:
        return None
    s = scope.strip()
    if not s or s == ".":
        return None
    return s


def _load_bootstrap_state(wiki_root: Path) -> dict:
    state_path = wiki_root / ".bootstrap_state.json"
    if not state_path.exists() or not state_path.is_file():
        return {}
    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
        return {}
    except Exception:
        return {}


def _save_bootstrap_state(wiki_root: Path, state: dict) -> None:
    import uuid

    tmp_path = wiki_root / f".bootstrap_state.json.tmp.{uuid.uuid4().hex}"
    target_path = wiki_root / ".bootstrap_state.json"
    tmp_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
    try:
        tmp_path.replace(target_path)
    finally:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass


def _format_idempotency_warning(state: dict) -> str:
    last_run = state.get("last_run_iso", "unknown")
    return (
        f"[--] brain79_bootstrap has already been run at {last_run}.\n"
        "Pass force=True to override and re-scan the project."
    )


def _resolve_scope_paths(
    project_root: Path, scope_str: str
) -> tuple[list[Path], list[str]]:
    raw_parts = [part.strip() for part in scope_str.split(",") if part.strip()]
    unique_parts = list(dict.fromkeys(raw_parts))
    resolved_root = project_root.resolve(strict=False)

    valid_paths: list[Path] = []
    missing_warnings: list[str] = []

    for part in unique_parts:
        resolved = (project_root / part).resolve(strict=False)
        try:
            if not resolved.is_relative_to(resolved_root):
                continue
        except ValueError:
            continue
        if not resolved.exists():
            missing_warnings.append(f"Scope path does not exist: {part}")
            continue
        valid_paths.append(resolved)
    return valid_paths, missing_warnings


def _detect_project_type(key_files: dict[str, str], tree: list[str]) -> str:
    all_names = set(key_files.keys()).union(set(tree))

    def has_file(name: str) -> bool:
        return name in all_names

    def has_ext(ext: str) -> bool:
        return any(item.endswith(ext) for item in all_names)

    # 1. python-package
    if has_file("pyproject.toml") or has_file("setup.py"):
        return "python-package"

    # 2. python-script
    if has_ext(".py"):
        return "python-script"

    # 3. node-package
    if has_file("package.json"):
        return "node-package"

    # 4. rust-crate
    if has_file("Cargo.toml"):
        return "rust-crate"

    # 5. go-module
    if has_file("go.mod"):
        return "go-module"

    # 6. java-maven
    if has_file("pom.xml"):
        return "java-maven"

    # 7. java-gradle
    if has_file("build.gradle"):
        return "java-gradle"

    # 8. ruby-gem
    if has_file("Gemfile"):
        return "ruby-gem"

    # 9. docker-service
    if has_file("Dockerfile"):
        return "docker-service"

    # 10. research-paper
    if has_ext(".tex") or has_ext(".bib"):
        return "research-paper"

    # 11. documentation
    if (
        has_file("mkdocs.yml")
        or has_file("mkdocs.yaml")
        or has_file("_config.yml")
        or "docs/" in all_names
        or "docs" in all_names
    ):
        return "documentation"

    # 12. unknown
    return "unknown"


def _collect_root_signals(project_root: Path, warnings: list[str]) -> dict:
    tree: list[str] = []
    try:
        with os.scandir(project_root) as it:
            entries = sorted(it, key=lambda e: e.name)
            for entry in entries:
                name = entry.name
                if name in _EXCLUDED_DIRS:
                    continue
                try:
                    is_dir = entry.is_dir(follow_symlinks=False)
                except OSError:
                    continue
                if is_dir and name.startswith("."):
                    continue
                if len(tree) >= _TREE_MAX_ENTRIES:
                    break
                tree.append(f"{name}/" if is_dir else name)
    except OSError as e:
        warnings.append(f"Error scanning directory tree: {e}")

    candidate_files: list[str] = []

    # Priority 1
    for f in ["README.md", "README.rst", "README.txt", "README.adoc", "README"]:
        if (project_root / f).is_file():
            candidate_files.append(f)

    # Priority 2
    for f in [
        "pyproject.toml",
        "setup.py",
        "setup.cfg",
        "package.json",
        "Cargo.toml",
        "go.mod",
        "go.sum",
        "Gemfile",
        "build.gradle",
        "pom.xml",
        "CMakeLists.txt",
    ]:
        if (project_root / f).is_file():
            candidate_files.append(f)

    # Priority 3
    for f in ["Dockerfile", "docker-compose.yml", "docker-compose.yaml"]:
        if (project_root / f).is_file():
            candidate_files.append(f)

    # Priority 4
    root_mds = sorted(
        [
            p.name
            for p in project_root.glob("*.md")
            if p.is_file() and p.name.upper() != "README.MD"
        ]
    )[:3]
    candidate_files.extend(root_mds)

    # Priority 5
    workflows_dir = project_root / ".github" / "workflows"
    if workflows_dir.is_dir():
        try:
            wf_files = sorted([p for p in workflows_dir.iterdir() if p.is_file()])
            if wf_files:
                rel_wf = str(wf_files[0].relative_to(project_root))
                candidate_files.append(rel_wf)
        except OSError:
            pass

    # Priority 6
    for f in ["mkdocs.yml", "mkdocs.yaml", "_config.yml", "conf.py", "Makefile"]:
        if (project_root / f).is_file():
            candidate_files.append(f)

    unique_candidates = list(dict.fromkeys(candidate_files))

    key_files: dict[str, str] = {}
    files_scanned = 0
    bytes_consumed = 0

    for rel_path_str in unique_candidates:
        file_path = project_root / rel_path_str
        suffix = file_path.suffix.lower()
        filename = file_path.name

        if suffix in _BINARY_EXTENSIONS:
            continue

        if filename in _PRESENCE_ONLY_FILES or rel_path_str in _PRESENCE_ONLY_FILES:
            continue

        content, _ = _truncate_file(file_path, _MAX_FILE_BYTES)
        if not content and not file_path.exists():
            continue

        content_bytes = len(content.encode("utf-8"))

        if bytes_consumed + content_bytes > _TOTAL_CONTENT_BUDGET_BYTES:
            warnings.append(f"Budget exhausted, skipping: {rel_path_str}")
            continue

        key_files[rel_path_str] = content
        bytes_consumed += content_bytes
        files_scanned += 1

    return {
        "tree": tree,
        "key_files": key_files,
        "files_scanned": files_scanned,
        "bytes_consumed": bytes_consumed,
    }


def _collect_scope_files(
    project_root: Path,
    scope_paths: list[Path],
    warnings: list[str],
) -> dict[str, list[dict]]:
    results: dict[str, list[dict]] = {}
    for scope_path in scope_paths:
        files: list[dict] = []
        try:
            rel_key = str(scope_path.relative_to(project_root))
        except ValueError:
            continue

        try:
            for root, dirs, file_list in os.walk(scope_path, onerror=None):
                dirs[:] = sorted(
                    d for d in dirs if d not in _EXCLUDED_DIRS and not d.startswith(".")
                )
                for f in sorted(file_list):
                    if len(files) >= _SCOPE_FILES_PER_PATH:
                        break
                    file_path = Path(root) / f
                    if file_path.suffix.lower() in _BINARY_EXTENSIONS:
                        continue
                    if f in _PRESENCE_ONLY_FILES:
                        continue
                    content, _ = _truncate_file(file_path, _SCOPE_FILE_MAX_BYTES)
                    if not content:
                        continue
                    files.append(
                        {
                            "path": str(file_path.relative_to(project_root)),
                            "content": content,
                        }
                    )
        except (PermissionError, OSError) as e:
            warnings.append(f"Cannot walk {rel_key}: {e}")

        results[rel_key] = files
        if not files:
            warnings.append(f"No readable files found in scope path: {rel_key}")
    return results


def _count_wiki_articles(wiki_root: Path) -> int:
    if not wiki_root.exists() or not wiki_root.is_dir():
        return 0
    count = 0
    try:
        for p in wiki_root.glob("**/*.md"):
            rel = p.relative_to(wiki_root)
            if not str(rel).startswith("_raw"):
                count += 1
    except OSError:
        return 0
    return count


def _build_manifest(
    project_root: Path,
    scope_str: str | None,
    root_signals: dict,
    scope_files: dict,
    project_type: str,
    warnings: list[str],
) -> str:
    now_iso = datetime.now(UTC).isoformat()
    scope_label = scope_str if scope_str else "auto"

    tree_text = "\n".join(root_signals.get("tree", []))

    key_files_blocks: list[str] = []
    for fname, content in root_signals.get("key_files", {}).items():
        key_files_blocks.append(f"### {fname}\n```\n{content}\n```")
    key_files_text = (
        "\n\n".join(key_files_blocks) if key_files_blocks else "No key files found."
    )

    scope_section = ""
    if scope_str and scope_files:
        scope_blocks: list[str] = []
        for rel_scope_path, file_entries in scope_files.items():
            file_count = len(file_entries)
            block_lines = [
                f"### {rel_scope_path}",
                f"Files sampled: {file_count} / {_SCOPE_FILES_PER_PATH}\n",
            ]
            for fe in file_entries:
                block_lines.append(f"#### {fe['path']}\n```\n{fe['content']}\n```\n")
            scope_blocks.append("\n".join(block_lines))
        if scope_blocks:
            scope_section = "\n---\n\n## Scope Analysis\n\n" + "\n".join(scope_blocks)

    conditional_scope_articles = ""
    if scope_str and scope_files:
        scope_article_items = []
        for rel_scope_path in scope_files.keys():
            base_name = Path(rel_scope_path).name or "feature"
            scope_article_items.append(
                f"- `features/{base_name}.md` — [for scope path {rel_scope_path}]"
            )
        conditional_scope_articles = "\n" + "\n".join(scope_article_items)

    warnings_section = ""
    if warnings:
        warn_lines = [f"- {w}" for w in warnings]
        warnings_section = "\n---\n\n## Warnings\n" + "\n".join(warn_lines)

    manifest = f"""# brain-79 Bootstrap Manifest
Generated: {now_iso}
Project root: {project_root}
Project type: {project_type}
Scope: {scope_label}

---

## Project Structure (depth 1)
{tree_text}

---

## Key Files

{key_files_text}{scope_section}

---

## Bootstrap Instructions

You have received a project scan manifest. Follow these steps exactly:

1. Call `brain79_read("SCHEMA.md")` to review curation rules.
2. Write the following wiki articles using `brain79_write`. Use ONLY information
   present in this manifest. Do not invent details not shown here.
   If a section has insufficient data, write what is known and mark gaps
   with `<!-- insufficient data: <reason> -->`.
3. Every article you write MUST start with this exact YAML frontmatter block:

   ---
   bootstrap: true
   generated_by: brain79_bootstrap
   generated_at: {now_iso}
   project_type: {project_type}
   ---

4. After writing all articles, call `brain79_lint()` to verify structural integrity.

**Required articles:**
- `architecture/overview.md` — Project structure, purpose, main components.
- `INDEX.md` — Update with project name, one-sentence purpose, and link to overview.
  (INDEX.md already exists; update it in place, preserving its structure.)

**Conditional articles (write only if evidence exists in this manifest):**
- `architecture/stack.md` — [include if tech stack signals detected]
- `product/domain.md` — [include if domain entities mentioned in README/docs]{conditional_scope_articles}{warnings_section}"""

    return manifest


def run_bootstrap(scope: str | None = None, force: bool = False) -> str:
    """Scan project and return a structured manifest for wiki bootstrapping."""
    wiki_root = get_wiki_root()

    # Guard 1: wiki must be initialized
    if not wiki_root.exists() or not wiki_root.is_dir():
        raise FileNotFoundError(
            "wiki not initialized. Run `brain79 init --project-root <path>` first."
        )

    project_root = get_project_root()
    lock_path = wiki_root / ".bootstrap_state.json.lock"

    # Guard 2: idempotency check
    try:
        with filelock.FileLock(str(lock_path), timeout=10):
            state = _load_bootstrap_state(wiki_root)
            if state and not force:
                return _format_idempotency_warning(state)
    except filelock.Timeout as exc:
        raise OSError(
            "another bootstrap is already running. Retry in a few seconds."
        ) from exc


    scope_str = _normalize_scope(scope)
    warnings: list[str] = []
    scope_paths, scope_warnings = (
        _resolve_scope_paths(project_root, scope_str) if scope_str else ([], [])
    )
    warnings.extend(scope_warnings)

    root_signals = _collect_root_signals(project_root, warnings)
    scope_files = (
        _collect_scope_files(project_root, scope_paths, warnings) if scope_paths else {}
    )
    project_type = _detect_project_type(root_signals["key_files"], root_signals["tree"])

    manifest = _build_manifest(
        project_root,
        scope_str,
        root_signals,
        scope_files,
        project_type,
        warnings,
    )

    existing_articles = _count_wiki_articles(wiki_root)
    try:
        with filelock.FileLock(str(lock_path), timeout=10):
            _save_bootstrap_state(
                wiki_root,
                {
                    "last_run_iso": datetime.now(UTC).isoformat(),
                    "scope": scope_str,
                    "project_type": project_type,
                    "files_scanned": root_signals["files_scanned"],
                    "bytes_consumed": root_signals["bytes_consumed"],
                    "existing_articles_count": existing_articles,
                },
            )
    except filelock.Timeout:
        pass

    return manifest
