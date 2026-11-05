"""Handoff freshness, provenance, and authority decay evaluation.

Provides deterministic digest calculation, git provenance extraction,
and freshness classification to prevent stale handoffs from masquerading
as active instructions.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import os
from pathlib import Path
import re
import subprocess

from brain79.core.frontmatter import parse_frontmatter


@dataclass(frozen=True)
class HandoffFreshness:
    """Evaluation result for a handoff's freshness and authority."""

    state: str  # "fresh" | "stale" | "unverified" | "foreign_branch"
    reasons: list[str]
    age_seconds: float
    commits_since: int | None
    handoff_branch: str
    current_branch: str
    changed_wiki_articles: list[str]
    code_changed: bool | None


_EXCLUDED_WIKI_SUBDIRS = ("handoffs", "_raw", ".locks")
_EXCLUDED_WIKI_FILES = ("INDEX.md", ".navigation_registry.json")


def _run_git(args: list[str], cwd: Path, timeout: float = 3.0) -> str:
    """Execute a git command with strict timeout and clean failure handling."""
    res = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=True,
    )
    return res.stdout.strip()


def is_git_workspace(project_root: Path) -> bool:
    """Check if project root is inside a git working directory."""
    if (project_root / ".git").exists():
        return True
    try:
        out = _run_git(["rev-parse", "--is-inside-work-tree"], cwd=project_root)
        return out.lower() == "true"
    except Exception:
        return False


def get_git_branch(project_root: Path) -> str:
    """Return the current git branch name, 'detached', or 'none'/'unknown'."""
    if not is_git_workspace(project_root):
        return "none"
    try:
        branch = _run_git(["symbolic-ref", "--short", "HEAD"], cwd=project_root)
        return branch if branch else "detached"
    except subprocess.CalledProcessError:
        return "detached"
    except Exception:
        return "unknown"


def get_git_head(project_root: Path) -> str:
    """Return the current git commit SHA or 'none'/'unknown'."""
    if not is_git_workspace(project_root):
        return "none"
    try:
        return _run_git(["rev-parse", "HEAD"], cwd=project_root)
    except Exception:
        return "unknown"


def compute_wiki_digest(wiki_root: Path) -> str:
    """Compute sha256 over sorted (posix_rel_path, sha256(bytes)) pairs of permanent wiki articles.

    Excludes handoffs/, _raw/, .locks/, INDEX.md, and .navigation_registry.json.
    Independent of filesystem mtime.
    """
    if not wiki_root.exists():
        return hashlib.sha256(b"").hexdigest()

    entries: list[tuple[str, str]] = []
    for p in wiki_root.rglob("*.md"):
        if not p.is_file():
            continue
        rel = p.relative_to(wiki_root).as_posix()
        parts = rel.split("/")
        if parts[0] in _EXCLUDED_WIKI_SUBDIRS or rel in _EXCLUDED_WIKI_FILES:
            continue
        try:
            content_hash = hashlib.sha256(p.read_bytes()).hexdigest()
            entries.append((rel, content_hash))
        except OSError:
            continue

    entries.sort(key=lambda x: x[0])
    hasher = hashlib.sha256()
    for rel, chash in entries:
        hasher.update(f"{rel}:{chash}\n".encode("utf-8"))
    return hasher.hexdigest()


def compute_code_digest(project_root: Path) -> str:
    """Compute sha256 over sorted (path, blob_sha) pairs outside .brain-79.

    Uses git index + untracked files to be commit-independent (commit of same tree yields same hash).
    Tolerates deleted files in working tree, submodules, and symlinks.
    Returns 'none' outside git, 'unknown' on error.
    """
    if not (project_root / ".git").exists() and not is_git_workspace(project_root):
        return "none"

    try:
        out = _run_git(
            ["-c", "core.quotepath=false", "ls-files", "--cached", "--others", "--exclude-standard"],
            cwd=project_root,
        )
        raw_files = [f.strip().strip('"').strip("'") for f in out.splitlines() if f.strip()]
        files: list[str] = []
        for f in raw_files:
            norm = f.replace("\\", "/")
            if norm.startswith(".brain-79/") or norm.startswith(".git/") or norm == ".brain-79" or norm == ".git":
                continue
            files.append(norm)

        if not files:
            return hashlib.sha256(b"empty").hexdigest()

        existing_files: list[str] = []
        deleted_files: list[str] = []
        special_tokens: list[tuple[str, str]] = []

        for f in sorted(set(files)):
            f_path = project_root / f
            if f_path.is_symlink():
                try:
                    target = str(os.readlink(f_path))
                    special_tokens.append((f, f"symlink:{target}"))
                except OSError:
                    special_tokens.append((f, "symlink:broken"))
            elif not f_path.exists():
                deleted_files.append(f)
            elif f_path.is_dir():
                # Git submodule
                try:
                    sub_head = _run_git(["rev-parse", "HEAD"], cwd=f_path)
                    special_tokens.append((f, f"submodule:{sub_head}"))
                except Exception:
                    special_tokens.append((f, "submodule:unknown"))
            elif f_path.is_file():
                existing_files.append(f)

        file_hashes: list[tuple[str, str]] = []
        if existing_files:
            proc = subprocess.run(
                ["git", "hash-object", "--stdin-paths"],
                input="\n".join(existing_files) + "\n",
                cwd=project_root,
                capture_output=True,
                text=True,
                timeout=3.0,
                check=True,
            )
            hashes = [h.strip() for h in proc.stdout.splitlines() if h.strip()]
            if len(hashes) != len(existing_files):
                return "unknown"
            for f, h in zip(existing_files, hashes):
                file_hashes.append((f, h))

        for d in deleted_files:
            special_tokens.append((d, "deleted"))

        all_entries = sorted(file_hashes + special_tokens, key=lambda x: x[0])
        hasher = hashlib.sha256()
        for f, h in all_entries:
            hasher.update(f"{f}:{h}\n".encode("utf-8"))
        return hasher.hexdigest()
    except Exception:
        return "unknown"


def _parse_created_at(raw_str: str, file_path: Path) -> datetime:
    """Parse created_at ISO 8601 timestamp or fallback to filename timestamp."""
    if raw_str:
        cleaned = raw_str.strip().replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(cleaned)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
            return dt
        except ValueError:
            pass

    # Fallback to filename: handoff-YYYY-MM-DD-HHMMSS-mmm.md
    stem = file_path.stem
    if stem.startswith("handoff-"):
        parts = stem.split("-")
        if len(parts) >= 5:
            date_str = f"{parts[1]}-{parts[2]}-{parts[3]}"
            time_str = parts[4]
            if len(time_str) >= 6:
                try:
                    hour = int(time_str[0:2])
                    minute = int(time_str[2:4])
                    second = int(time_str[4:6])
                    dt = datetime.strptime(f"{date_str} {hour:02d}:{minute:02d}:{second:02d}", "%Y-%m-%d %H:%M:%S")
                    return dt.replace(tzinfo=UTC)
                except ValueError:
                    pass

    return datetime.fromtimestamp(file_path.stat().st_mtime, tz=UTC)


def compute_handoff_freshness(handoff_path: Path, wiki_root: Path | None = None) -> HandoffFreshness:
    """Evaluate handoff freshness and calculate authority decay indicators deterministically."""
    if wiki_root is None:
        wiki_root = handoff_path.parent.parent
    project_root = wiki_root.parent

    content = handoff_path.read_text(encoding="utf-8")
    frontmatter, _ = parse_frontmatter(content)

    created_at_dt = _parse_created_at(str(frontmatter.get("created_at") or ""), handoff_path)
    now_dt = datetime.now(UTC)
    age_seconds = max(0.0, (now_dt - created_at_dt).total_seconds())

    h_branch = str(frontmatter.get("git_branch") or "").strip()
    h_head = str(frontmatter.get("git_head") or "").strip()
    h_wiki_digest = str(frontmatter.get("wiki_digest") or "").strip()
    h_code_digest = str(frontmatter.get("code_digest") or "").strip()

    cur_branch = get_git_branch(project_root)
    cur_wiki_digest = compute_wiki_digest(wiki_root)
    cur_code_digest = compute_code_digest(project_root)

    reasons: list[str] = []
    commits_since: int | None = None
    changed_wiki_articles: list[str] = []
    code_changed: bool | None = None

    is_valid_sha = bool(re.fullmatch(r"[0-9a-fA-F]{7,64}", h_head))

    # Calculate commits_since
    if is_git_workspace(project_root) and is_valid_sha:
        try:
            count_str = _run_git(["rev-list", "--count", f"{h_head}..HEAD"], cwd=project_root)
            commits_since = int(count_str)
        except Exception:
            commits_since = None

    # Calculate changed wiki articles (informational only)
    if is_git_workspace(project_root) and is_valid_sha:
        try:
            diff_out = _run_git(
                ["-c", "core.quotepath=false", "diff", "--relative", "--name-only", h_head, "--", ".brain-79/"],
                cwd=project_root,
            )
            for line in diff_out.splitlines():
                line = line.strip().strip('"').replace("\\", "/")
                if line.startswith(".brain-79/"):
                    sub_rel = line[len(".brain-79/"):]
                    parts = sub_rel.split("/")
                    if parts[0] not in _EXCLUDED_WIKI_SUBDIRS and sub_rel not in _EXCLUDED_WIKI_FILES and sub_rel.endswith(".md"):
                        if sub_rel not in changed_wiki_articles:
                            changed_wiki_articles.append(sub_rel)
            # Check untracked files
            untracked_out = _run_git(
                ["-c", "core.quotepath=false", "ls-files", "--others", "--exclude-standard", ".brain-79/"],
                cwd=project_root,
            )
            for line in untracked_out.splitlines():
                line = line.strip().strip('"').replace("\\", "/")
                if line.startswith(".brain-79/"):
                    sub_rel = line[len(".brain-79/"):]
                    parts = sub_rel.split("/")
                    if parts[0] not in _EXCLUDED_WIKI_SUBDIRS and sub_rel not in _EXCLUDED_WIKI_FILES and sub_rel.endswith(".md"):
                        if sub_rel not in changed_wiki_articles:
                            changed_wiki_articles.append(sub_rel)
        except Exception:
            pass
    else:
        # Non-git or unknown HEAD: check mtime compared to created_at_dt
        for p in wiki_root.rglob("*.md"):
            if not p.is_file():
                continue
            sub_rel = p.relative_to(wiki_root).as_posix()
            parts = sub_rel.split("/")
            if parts[0] in _EXCLUDED_WIKI_SUBDIRS or sub_rel in _EXCLUDED_WIKI_FILES:
                continue
            if p.stat().st_mtime > created_at_dt.timestamp() + 0.1:
                changed_wiki_articles.append(sub_rel)

    # Check code changed
    if h_code_digest and h_code_digest not in ("none", "unknown") and cur_code_digest not in ("none", "unknown"):
        code_changed = (h_code_digest != cur_code_digest)
    elif h_code_digest == "none" and cur_code_digest == "none":
        code_changed = False
    else:
        code_changed = None

    # Determine State according to Precedence
    state: str = "fresh"

    # Precedence 1: foreign_branch
    if (
        h_branch
        and cur_branch
        and h_branch not in ("none", "unknown", "detached", "")
        and cur_branch not in ("none", "unknown", "detached", "")
        and h_branch != cur_branch
    ):
        state = "foreign_branch"
        reasons.append(f"handoff recorded on branch '{h_branch}', current branch is '{cur_branch}'")
        return HandoffFreshness(
            state=state,
            reasons=reasons,
            age_seconds=age_seconds,
            commits_since=commits_since,
            handoff_branch=h_branch,
            current_branch=cur_branch,
            changed_wiki_articles=changed_wiki_articles,
            code_changed=code_changed,
        )

    # Precedence 2: stale
    wiki_differs = bool(h_wiki_digest and cur_wiki_digest and h_wiki_digest != cur_wiki_digest)
    code_differs = bool(code_changed is True)

    if wiki_differs or code_differs:
        state = "stale"
        if wiki_differs:
            reasons.append("wiki content modified since handoff")
        if code_differs:
            reasons.append("codebase modified since handoff")
        return HandoffFreshness(
            state=state,
            reasons=reasons,
            age_seconds=age_seconds,
            commits_since=commits_since,
            handoff_branch=h_branch or "none",
            current_branch=cur_branch,
            changed_wiki_articles=changed_wiki_articles,
            code_changed=code_changed,
        )

    # Precedence 3: unverified (legacy or unknown required digests)
    handoff_was_in_git = (
        (h_code_digest and h_code_digest not in ("none", "unknown"))
        or (h_head and h_head not in ("none", "unknown") and is_valid_sha)
    )
    # cur_head is legitimately unknown in a fresh repository without commits
    git_status_unknown = (cur_code_digest == "unknown" or cur_branch == "unknown")
    if (
        not h_wiki_digest
        or cur_wiki_digest == "unknown"
        or cur_code_digest == "unknown"
        or (handoff_was_in_git and git_status_unknown)
    ):
        state = "unverified"
        if not h_wiki_digest:
            reasons.append("legacy handoff lacking content provenance digests")
        else:
            reasons.append("unable to compute workspace digest")
        return HandoffFreshness(
            state=state,
            reasons=reasons,
            age_seconds=age_seconds,
            commits_since=commits_since,
            handoff_branch=h_branch or "none",
            current_branch=cur_branch,
            changed_wiki_articles=changed_wiki_articles,
            code_changed=code_changed,
        )

    # Precedence 4: fresh
    return HandoffFreshness(
        state="fresh",
        reasons=["all content digests match exactly"],
        age_seconds=age_seconds,
        commits_since=commits_since,
        handoff_branch=h_branch or "none",
        current_branch=cur_branch,
        changed_wiki_articles=[],
        code_changed=False,
    )
