"""Centralized Git execution layer and per-session lookup cache.

Consolidates all `git` subprocess invocations into a single typed, defensive module:
- Always passes `-c core.quotepath=false` for path-returning commands.
- Always terminates options with `--` before repository pathspecs.
- Never uses `shell=True`.
- Distinguishes expected non-git workspaces (`NotAGitRepoError`) from operational
  failures (`GitTimeoutError`, `OSError`).
- Supports optional per-session caching (`GitSessionCache`) of `HEAD`, last-commit,
  and file-blob lookups.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
import subprocess

from brain79.core.locks import normalize_posix_input


class GitError(Exception):
    """Base exception for Git operational errors."""


class NotAGitRepoError(GitError):
    """Raised when a Git command is executed outside a Git repository/worktree."""


class GitTimeoutError(GitError):
    """Raised when a Git subprocess exceeds its timeout."""


@dataclass(frozen=True)
class GitResult:
    """Structured result of a Git subprocess invocation."""

    returncode: int
    stdout: str
    stderr: str


@dataclass(frozen=True)
class GitBytesResult:
    """Structured binary result of a Git subprocess invocation."""

    returncode: int
    stdout: bytes
    stderr: bytes


@dataclass
class GitSessionCache:
    """Optional per-session cache for HEAD, per-path commit, repo status, and blob lookups."""

    head_by_root: dict[tuple[Path, str], str] = field(default_factory=dict)
    last_commit_by_key: dict[tuple[Path, str, str], str | None] = field(default_factory=dict)
    blob_by_key: dict[tuple[Path, str, str], str | None] = field(default_factory=dict)
    is_git_repo_by_root: dict[Path, bool] = field(default_factory=dict)


def _is_not_a_git_repo_stderr(stderr_text: str) -> bool:
    lowered = stderr_text.lower()
    return (
        "not a git repository" in lowered
        or "must be run in a work tree" in lowered
    )


def run_git(
    args: Sequence[str],
    cwd: Path,
    *,
    timeout: float = 5.0,
    input_data: str | None = None,
    check_repo: bool = False,
) -> GitResult:
    """Execute a git command returning decoded UTF-8 text."""
    cmd = ["git", *args]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            input=input_data,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise GitTimeoutError(f"Git command timed out after {timeout}s: {' '.join(cmd)}") from exc

    if check_repo and proc.returncode != 0 and _is_not_a_git_repo_stderr(proc.stderr):
        raise NotAGitRepoError(proc.stderr.strip() or f"Not a git repository: {cwd}")

    return GitResult(returncode=proc.returncode, stdout=proc.stdout, stderr=proc.stderr)


def run_git_bytes(
    args: Sequence[str],
    cwd: Path,
    *,
    timeout: float = 5.0,
    check_repo: bool = False,
) -> GitBytesResult:
    """Execute a git command returning raw bytes (for NUL-delimited `-z` output)."""
    cmd = ["git", *args]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise GitTimeoutError(f"Git command timed out after {timeout}s: {' '.join(cmd)}") from exc

    if check_repo and proc.returncode != 0:
        stderr_text = proc.stderr.decode("utf-8", errors="replace")
        if _is_not_a_git_repo_stderr(stderr_text):
            raise NotAGitRepoError(stderr_text.strip() or f"Not a git repository: {cwd}")

    return GitBytesResult(returncode=proc.returncode, stdout=proc.stdout, stderr=proc.stderr)


def git_rev_parse_head(
    cwd: Path,
    *,
    ref: str = "HEAD",
    timeout: float = 2.0,
    cache: GitSessionCache | None = None,
) -> str:
    """Return the commit SHA for `ref` (default `HEAD`). Raises NotAGitRepoError or GitTimeoutError."""
    resolved = cwd.resolve()
    if cache is not None:
        key = (resolved, ref)
        if key in cache.head_by_root:
            return cache.head_by_root[key]

    res = run_git(["rev-parse", ref], cwd=resolved, timeout=timeout, check_repo=True)
    if res.returncode != 0:
        if _is_not_a_git_repo_stderr(res.stderr):
            raise NotAGitRepoError(res.stderr.strip())
        raise GitError(res.stderr.strip() or f"git rev-parse {ref} failed (rc={res.returncode})")

    sha = res.stdout.strip()
    if cache is not None:
        cache.head_by_root[(resolved, ref)] = sha
    return sha


def git_current_branch(cwd: Path, *, timeout: float = 3.0) -> str:
    """Return the current branch name (or empty string on detached HEAD)."""
    res = run_git(["symbolic-ref", "--short", "HEAD"], cwd=cwd, timeout=timeout, check_repo=True)
    if res.returncode == 0:
        return res.stdout.strip()
    return ""


def git_status_porcelain(
    cwd: Path,
    *,
    paths: Sequence[str] | None = None,
    untracked: str | None = None,
    timeout: float = 5.0,
    check_repo: bool = True,
) -> GitResult:
    """Run `git -c core.quotepath=false status --porcelain` with optional pathspecs."""
    args: list[str] = ["-c", "core.quotepath=false", "status", "--porcelain"]
    if untracked is not None:
        args.append(f"--untracked-files={untracked}")
    if paths:
        args.append("--")
        args.extend(paths)
    return run_git(args, cwd=cwd, timeout=timeout, check_repo=check_repo)


def git_dirty_paths(
    cwd: Path,
    *,
    exclude_prefix: str | None = ".brain-79/",
    timeout: float = 2.0,
) -> list[str]:
    """Return normalized dirty working-tree paths via `status --porcelain=v1 -z`.

    Raises NotAGitRepoError if `cwd` is not a Git repository, and GitTimeoutError on timeout.
    """
    res = run_git_bytes(
        ["-c", "core.quotepath=false", "status", "--porcelain=v1", "-z"],
        cwd=cwd,
        timeout=timeout,
        check_repo=True,
    )
    if res.returncode != 0:
        stderr_text = res.stderr.decode("utf-8", errors="replace")
        if _is_not_a_git_repo_stderr(stderr_text):
            raise NotAGitRepoError(stderr_text.strip())
        raise GitError(stderr_text.strip() or f"git status failed (rc={res.returncode})")

    discovered: list[str] = []
    if not res.stdout:
        return discovered

    raw_entries = res.stdout.split(b"\x00")
    idx = 0
    while idx < len(raw_entries):
        entry_bytes = raw_entries[idx]
        idx += 1
        if not entry_bytes:
            continue
        entry_str = entry_bytes.decode("utf-8", errors="replace")
        if len(entry_str) >= 4 and entry_str[2] == " ":
            xy = entry_str[:2]
            p_str = entry_str[3:]
            norm_p = normalize_posix_input(p_str).lstrip("/")
            if norm_p and norm_p not in discovered:
                if not exclude_prefix or not norm_p.startswith(exclude_prefix):
                    discovered.append(norm_p)
            if "R" in xy or "C" in xy:
                if idx < len(raw_entries) and raw_entries[idx]:
                    orig_bytes = raw_entries[idx]
                    idx += 1
                    orig_str = orig_bytes.decode("utf-8", errors="replace")
                    norm_orig = normalize_posix_input(orig_str).lstrip("/")
                    if norm_orig and norm_orig not in discovered:
                        if not exclude_prefix or not norm_orig.startswith(exclude_prefix):
                            discovered.append(norm_orig)
    return discovered


def git_last_commit_for_path(
    cwd: Path,
    rel_path: str,
    *,
    fmt: str = "%H",
    timeout: float = 2.0,
    cache: GitSessionCache | None = None,
) -> str | None:
    """Return the last commit attribute (`fmt`, default `%H`) for `rel_path`, or None if untracked."""
    resolved = cwd.resolve()
    if cache is not None:
        key = (resolved, rel_path, fmt)
        if key in cache.last_commit_by_key:
            return cache.last_commit_by_key[key]

    res = run_git(
        ["log", "-1", f"--format={fmt}", "--", rel_path],
        cwd=resolved,
        timeout=timeout,
        check_repo=True,
    )
    value: str | None = res.stdout.strip() if (res.returncode == 0 and res.stdout.strip()) else None
    if cache is not None:
        cache.last_commit_by_key[(resolved, rel_path, fmt)] = value
    return value


def git_show_blob(
    cwd: Path,
    rev: str,
    rel_path: str,
    *,
    timeout: float = 2.0,
    cache: GitSessionCache | None = None,
) -> str | None:
    """Return file content at `rev:rel_path`, or None if the path did not exist at `rev`."""
    resolved = cwd.resolve()
    if cache is not None:
        key = (resolved, rev, rel_path)
        if key in cache.blob_by_key:
            return cache.blob_by_key[key]

    res = run_git(["show", f"{rev}:{rel_path}"], cwd=resolved, timeout=timeout, check_repo=True)
    blob: str | None = res.stdout if res.returncode == 0 else None
    if cache is not None:
        cache.blob_by_key[(resolved, rev, rel_path)] = blob
    return blob


def git_diff_names(
    cwd: Path,
    rev_range: str | None = None,
    *,
    paths: Sequence[str] | None = None,
    timeout: float = 3.0,
) -> list[str]:
    """Return list of changed file paths via `git -c core.quotepath=false diff --name-only`."""
    args: list[str] = ["-c", "core.quotepath=false", "diff", "--name-only"]
    if rev_range:
        args.append(rev_range)
    if paths:
        args.append("--")
        args.extend(paths)
    res = run_git(args, cwd=cwd, timeout=timeout, check_repo=True)
    if res.returncode != 0:
        return []
    return [line.strip() for line in res.stdout.splitlines() if line.strip()]


def git_ls_files(
    cwd: Path,
    *,
    include_others: bool = True,
    timeout: float = 2.0,
) -> list[str]:
    """Return tracked (and optionally non-ignored untracked) workspace paths via `ls-files -z`."""
    args = ["-c", "core.quotepath=false", "ls-files", "-z", "--cached"]
    if include_others:
        args.extend(["--others", "--exclude-standard"])
    res = run_git_bytes(
        args,
        cwd=cwd,
        timeout=timeout,
        check_repo=True,
    )
    if res.returncode != 0:
        return []
    paths: list[str] = []
    for raw_path in res.stdout.split(b"\x00"):
        if not raw_path:
            continue
        p_str = raw_path.decode("utf-8", errors="replace").strip()
        if p_str:
            paths.append(p_str)
    return paths


def git_hash_object_stdin_paths(
    cwd: Path,
    paths: Sequence[str],
    *,
    timeout: float = 3.0,
) -> list[str]:
    """Hash multiple workspace files in a single `git hash-object --stdin-paths` invocation."""
    if not paths:
        return []
    res = run_git(
        ["hash-object", "--stdin-paths"],
        cwd=cwd,
        input_data="\n".join(paths) + "\n",
        timeout=timeout,
        check_repo=True,
    )
    if res.returncode != 0:
        raise GitError(res.stderr.strip() or f"git hash-object failed (rc={res.returncode})")
    return [h.strip() for h in res.stdout.splitlines() if h.strip()]


def git_init(cwd: Path, *, timeout: float = 5.0) -> GitResult:
    """Initialize a new Git repository at `cwd`."""
    return run_git(["init"], cwd=cwd, timeout=timeout, check_repo=False)


def _validate_git_ref_arg(value: str, label: str) -> str:
    """Reject option-like values starting with '-' to prevent Git option injection."""
    if not value or value.startswith("-"):
        raise ValueError(f"Invalid Git {label} '{value}': must not start with '-'.")
    return value


def git_remote_get_url(cwd: Path, remote: str = "origin", *, timeout: float = 5.0) -> GitResult:
    """Return the configured URL for `remote`."""
    _validate_git_ref_arg(remote, "remote")
    return run_git(["remote", "get-url", "--", remote], cwd=cwd, timeout=timeout, check_repo=False)


def git_symbolic_ref(
    cwd: Path,
    ref: str,
    *,
    short: bool = False,
    timeout: float = 5.0,
) -> GitResult:
    """Resolve a symbolic ref."""
    _validate_git_ref_arg(ref, "ref")
    args = ["symbolic-ref"]
    if short:
        args.append("--short")
    args.append(ref)
    return run_git(args, cwd=cwd, timeout=timeout, check_repo=False)


def git_fetch(cwd: Path, remote: str = "origin", *, timeout: float = 60.0) -> GitResult:
    """Fetch updates from `remote`."""
    _validate_git_ref_arg(remote, "remote")
    return run_git(["fetch", remote], cwd=cwd, timeout=timeout, check_repo=False)


def git_pull_ff_only(
    cwd: Path,
    remote: str,
    branch: str,
    *,
    timeout: float = 60.0,
) -> GitResult:
    """Fast-forward pull `branch` from `remote`."""
    _validate_git_ref_arg(remote, "remote")
    _validate_git_ref_arg(branch, "branch")
    return run_git(["pull", "--ff-only", remote, branch], cwd=cwd, timeout=timeout, check_repo=False)


def git_config_get_local(
    cwd: Path,
    key: str,
    *,
    timeout: float = 5.0,
) -> str | None:
    """Read a repository-local Git config key (`git config --local --get`). Returns None if unset."""
    _validate_git_ref_arg(key, "config key")
    res = run_git(["config", "--local", "--get", key], cwd=cwd, timeout=timeout, check_repo=True)
    if res.returncode != 0:
        return None
    val = res.stdout.strip()
    return val if val else None


def git_config_set_local(
    cwd: Path,
    key: str,
    value: str,
    *,
    timeout: float = 5.0,
) -> None:
    """Set a repository-local Git config key (`git config --local`). Never uses shell=True."""
    _validate_git_ref_arg(key, "config key")
    res = run_git(["config", "--local", key, value], cwd=cwd, timeout=timeout, check_repo=True)
    if res.returncode != 0:
        raise GitError(res.stderr.strip() or f"git config --local {key} failed (rc={res.returncode})")


def git_recent_file_churn(
    cwd: Path,
    *,
    max_commits: int = 200,
    timeout: float = 5.0,
) -> dict[str, int]:
    """Count recent commit touches per file via `git log -n <N> --name-only --pretty=format:`.

    Raises NotAGitRepoError outside Git repositories; returns {} on zero-commit repositories.
    """
    n = max(1, int(max_commits))
    res = run_git(
        ["-c", "core.quotepath=false", "log", "-n", str(n), "--name-only", "--pretty=format:"],
        cwd=cwd,
        timeout=timeout,
        check_repo=True,
    )
    if res.returncode != 0:
        stderr_lower = res.stderr.lower()
        if "does not have any commits yet" in stderr_lower or "your current branch" in stderr_lower:
            return {}
        if _is_not_a_git_repo_stderr(res.stderr):
            raise NotAGitRepoError(res.stderr.strip())
        return {}

    counts: dict[str, int] = {}
    for raw_line in res.stdout.splitlines():
        cleaned = normalize_posix_input(raw_line).lstrip("/")
        if cleaned:
            counts[cleaned] = counts.get(cleaned, 0) + 1
    return counts
