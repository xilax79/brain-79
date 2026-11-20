"""
Deterministic Merkle leaf-manifest and multi-hop DAG code-to-wiki drift detection.

Monitors source code and intra-wiki files governed by wiki articles via the `applies_to` frontmatter field.
Provides:
- Operation-scoped WorkspaceIndex with unified globbing and dynamic wiki prefixes
- Merkle leaf manifest (.drift_manifest.json) with exact per-file attribution (modified, deleted, added, missing)
- Recursive memoized multi-hop transitive drift propagation closure with cycle immunity (AC-E1, AC-E2)
- 64 KB constant-memory byte-streaming hashing with CRLF/BOM invariance (AC-E5)
- AST Public API Diff Guard (Guard C, AC-B4)
"""

import ast
from datetime import UTC, date, datetime
import hashlib
import json
from pathlib import Path
import posixpath
import re
import subprocess
from typing import Any
import uuid

from brain79.config import get_project_root, get_wiki_root
from brain79.core.frontmatter import (
    INACTIVE_STATUSES,
    PRE_IMPLEMENTATION_STATUSES,
    ValidationError,
    parse_frontmatter,
)
from brain79.core.git_ops import (
    GitError,
    GitTimeoutError,
    NotAGitRepoError,
    git_last_commit_for_path,
    git_ls_files,
    git_rev_parse_head,
    git_show_blob,
    git_status_porcelain,
)
from brain79.core.locks import (
    acquire_wiki_lock,
    atomic_replace_with_retry,
    has_exact_case_path,
    normalize_posix_input,
    normalize_wiki_rel_path,
    rel_posix,
)

_IGNORED_DIRS: frozenset[str] = frozenset({
    ".git",
    "node_modules",
    ".venv",
    ".uv",
    "__pycache__",
    "dist",
    "build",
    ".pytest_cache",
    ".mypy_cache",
    ".pytest_tmp",
    "pytest_tmp",
})

_FILE_HASH_CACHE: dict[tuple[str, int, int], str] = {}
_GIT_DATE_CACHE: dict[str, str] = {}
MAX_DRIFT_FILE_SIZE = 10 * 1024 * 1024  # 10 MB

VOLATILE_FRONTMATTER_FIELDS: frozenset[str] = frozenset({
    "applies_to_digest",
    "applies_to_count",
    "last_updated",
})


def _is_ignored(path: Path, project_root: Path, allow_brain79: bool = False) -> bool:
    try:
        rel = path.relative_to(project_root)
        if allow_brain79:
            if rel.parts and rel.parts[0] == ".brain-79":
                if len(rel.parts) > 1 and rel.parts[1] in (".locks", "_raw", "handoffs"):
                    return True
                return False
        return any(part in _IGNORED_DIRS for part in rel.parts)
    except ValueError:
        return True


def glob_to_regex(pattern: str) -> re.Pattern[str]:
    """Translate glob pattern to regex with single-segment vs multi-segment awareness."""
    i = 0
    n = len(pattern)
    res: list[str] = ["^"]
    while i < n:
        c = pattern[i]
        if c == "*":
            if i + 1 < n and pattern[i + 1] == "*":
                if i + 2 < n and pattern[i + 2] == "/":
                    res.append(r"(?:.+/)?")
                    i += 3
                    continue
                else:
                    res.append(r".*")
                    i += 2
                    continue
            else:
                res.append(r"[^/]*")
                i += 1
                continue
        elif c == "?":
            res.append(r"[^/]")
            i += 1
            continue
        elif c in r"\.+^$()[]{}|":
            res.append(re.escape(c))
            i += 1
            continue
        else:
            res.append(c)
            i += 1
    res.append("$")
    return re.compile("".join(res))


def match_applies_to_pattern(
    pattern: str,
    candidate_project_rel_posix: str,
    known_dirs: set[str] | None = None,
    known_wiki_prefixes: set[str] | None = None,
    wiki_rel_posix: str = ".brain-79",
) -> bool:
    """Unified pattern matcher for applies_to rules.

    Supports:
    - Exact equality (case-sensitive)
    - Directory prefix parity ('src/cli/' or 'src/cli' matching children)
    - Segment-aware globbing (* for single segment, **/ for multi-segment)
    - Bidirectional .brain-79/ normalization
    """
    pat = normalize_posix_input(pattern).strip().lstrip("/")
    if pat.startswith("./"):
        pat = pat[2:]
    if not pat:
        return False

    norm_pat = posixpath.normpath(pat)
    if norm_pat.startswith("../") or norm_pat == "..":
        return False

    pat = norm_pat
    cand = normalize_posix_input(candidate_project_rel_posix).strip().lstrip("/")
    if cand.startswith("./"):
        cand = cand[2:]

    if not cand:
        return False

    if known_wiki_prefixes is None:
        known_wiki_prefixes = {
            "decisions", "features", "architecture", "product",
            "topics", "context", "changelog", "log",
        }

    cand_root_seg = cand.split("/")[0]
    cand_is_root_dir = known_dirs is not None and cand_root_seg in known_dirs
    cand_is_in_wiki = cand.startswith(f"{wiki_rel_posix}/") or (
        cand_root_seg in known_wiki_prefixes and not cand_is_root_dir
    )
    pat_is_in_wiki = pat.startswith(f"{wiki_rel_posix}/") or (
        pat.split("/")[0] in known_wiki_prefixes
    )

    # Bidirectional .brain-79/ normalization
    pat_first = pat.split("/")[0]
    norm_wiki_pat = pat
    if pat_first in known_wiki_prefixes and not pat.startswith(f"{wiki_rel_posix}/"):
        norm_wiki_pat = f"{wiki_rel_posix}/{pat}"

    cand_without_wiki = cand[len(wiki_rel_posix) + 1:] if cand.startswith(f"{wiki_rel_posix}/") else cand
    pat_without_wiki = pat[len(wiki_rel_posix) + 1:] if pat.startswith(f"{wiki_rel_posix}/") else pat

    # 1. Exact equality
    if cand == pat or cand == norm_wiki_pat:
        return True
    if cand_is_in_wiki and pat_is_in_wiki and cand_without_wiki == pat_without_wiki:
        return True

    # 2. Directory prefix matching
    has_wildcards = any(c in pat for c in ("*", "?", "["))
    if not has_wildcards:
        clean_prefix = pat.rstrip("/") + "/"
        clean_norm_prefix = norm_wiki_pat.rstrip("/") + "/"
        if cand.startswith(clean_prefix) or cand.startswith(clean_norm_prefix):
            return True
        if cand_is_in_wiki and pat_is_in_wiki:
            clean_no_wiki_prefix = pat_without_wiki.rstrip("/") + "/"
            if cand_without_wiki.startswith(clean_no_wiki_prefix):
                return True

    # 3. Glob matching (if pattern contains wildcards * or ? or [)
    if has_wildcards:
        try:
            rx = glob_to_regex(pat)
            if rx.match(cand):
                return True
            if norm_wiki_pat != pat:
                rx_norm = glob_to_regex(norm_wiki_pat)
                if rx_norm.match(cand):
                    return True
            if cand_is_in_wiki and pat_is_in_wiki and pat_without_wiki != pat:
                rx_no_wiki = glob_to_regex(pat_without_wiki)
                if rx_no_wiki.match(cand_without_wiki):
                    return True
        except Exception:
            pass

    return False


class WorkspaceIndex:
    """Operation-scoped in-memory index of workspace files.

    Eliminates O(A x W) subprocess and disk scanning overhead by collecting
    workspace paths once per top-level operation using at most one git ls-files call.
    """

    def __init__(
        self,
        project_root: Path,
        wiki_root: Path,
        all_paths: set[str],
        known_dirs: set[str],
        known_wiki_prefixes: set[str],
        overlay_fs: dict[str, str] | None = None,
        git_cache: Any = None,
    ) -> None:
        self.project_root = project_root
        self.wiki_root = wiki_root
        self.all_paths = all_paths
        self.known_dirs = known_dirs
        self.known_wiki_prefixes = known_wiki_prefixes
        self.overlay_fs = overlay_fs or {}
        self.git_cache = git_cache
        self.drift_cache: dict[str, list[dict[str, Any]]] = {}
        self._pattern_cache: dict[str, list[str]] = {}
        self._contained_path_cache: dict[str, Path | None] = {}

    def resolve_contained_path(self, rel_posix_path: str) -> Path:
        """Resolve and memoize a contained workspace path, rejecting escapes outside project_root."""
        if rel_posix_path in self._contained_path_cache:
            cached = self._contained_path_cache[rel_posix_path]
            if cached is None:
                raise ValueError(
                    f"Path '{rel_posix_path}' resolves outside project root '{self.project_root}'."
                )
            return cached
        try:
            resolved = _resolve_contained_path(
                self.project_root,
                rel_posix_path,
                resolved_root=self.project_root,
            )
            self._contained_path_cache[rel_posix_path] = resolved
            return resolved
        except ValueError:
            self._contained_path_cache[rel_posix_path] = None
            raise

    @classmethod
    def build(
        cls,
        project_root: Path,
        wiki_root: Path,
        overlay_fs: dict[str, str] | None = None,
        git_cache: Any = None,
    ) -> "WorkspaceIndex":
        p_root = project_root.resolve()
        w_root = wiki_root.resolve()

        try:
            wiki_rel = rel_posix(w_root, p_root)
        except ValueError:
            wiki_rel = ".brain-79"

        all_paths: set[str] = set()

        is_git_ok = False
        from brain79.core.handoff_freshness import is_git_workspace
        if is_git_workspace(p_root, git_cache=git_cache):
            try:
                ls_paths = git_ls_files(p_root, timeout=2.0)
                is_git_ok = True
                for p_str in ls_paths:
                    disk_target = p_root / p_str
                    if disk_target.is_dir():
                        for child in disk_target.rglob("*"):
                            if child.is_file() and not _is_ignored(child, p_root, allow_brain79=True):
                                try:
                                    all_paths.add(rel_posix(child, p_root))
                                except ValueError:
                                    pass
                    else:
                        all_paths.add(p_str)
            except (NotAGitRepoError, GitTimeoutError, GitError, OSError):
                is_git_ok = False

        if not is_git_ok:
            if p_root.exists():
                for child in p_root.rglob("*"):
                    if child.is_file() and not _is_ignored(child, p_root, allow_brain79=True):
                        try:
                            all_paths.add(rel_posix(child, p_root))
                        except ValueError:
                            pass

        if overlay_fs:
            for ov_path in overlay_fs.keys():
                clean_ov = normalize_posix_input(ov_path).lstrip("/")
                if clean_ov.startswith(f"{wiki_rel}/"):
                    all_paths.add(clean_ov)
                elif clean_ov.startswith(".brain-79/"):
                    all_paths.add(clean_ov)
                else:
                    all_paths.add(f"{wiki_rel}/{clean_ov}")

        ephemeral_prefixes = (
            f"{wiki_rel}/_raw/",
            f"{wiki_rel}/.locks/",
            f"{wiki_rel}/handoffs/",
        )
        ephemeral_files = {
            f"{wiki_rel}/INDEX.md",
            f"{wiki_rel}/.navigation_registry.json",
            f"{wiki_rel}/.drift_manifest.json",
        }

        all_paths = {
            p for p in all_paths
            if p not in ephemeral_files
            and not any(p.startswith(pref) for pref in ephemeral_prefixes)
            and not _is_ignored(p_root / p, p_root, allow_brain79=True)
        }

        known_wiki_prefixes: set[str] = set()
        try:
            from brain79.core.frontmatter import load_active_schema
            schema = load_active_schema(w_root)
            known_wiki_prefixes = {prefix.split("/")[0] for prefix in schema.location_to_type.keys()}
        except Exception:
            known_wiki_prefixes = {
                "decisions", "features", "architecture", "product",
                "topics", "context", "changelog", "log",
            }

        if w_root.exists():
            for sub in w_root.iterdir():
                if sub.is_dir() and not sub.name.startswith(".") and sub.name not in ("_raw", "handoffs", ".locks"):
                    known_wiki_prefixes.add(sub.name)

        known_dirs: set[str] = set()
        for p in all_paths:
            parts = p.split("/")
            for i in range(1, len(parts)):
                known_dirs.add("/".join(parts[:i]))

        return cls(
            project_root=p_root,
            wiki_root=w_root,
            all_paths=all_paths,
            known_dirs=known_dirs,
            known_wiki_prefixes=known_wiki_prefixes,
            overlay_fs=overlay_fs,
            git_cache=git_cache,
        )

    def find_matching_files(self, patterns: list[str]) -> list[str]:
        matched: set[str] = set()
        try:
            wiki_rel = rel_posix(self.wiki_root, self.project_root)
        except ValueError:
            wiki_rel = ".brain-79"

        for pat in patterns:
            pat_clean = normalize_posix_input(pat).lstrip("/")
            if not pat_clean:
                continue
            if pat_clean in self._pattern_cache:
                matched.update(self._pattern_cache[pat_clean])
                continue

            cur_matched: list[str] = []
            # Fast-path 1: Exact file in workspace
            if pat_clean in self.all_paths:
                cur_matched.append(pat_clean)
            elif "*" not in pat_clean:
                # Fast-path 2: Directory prefix
                dir_pref = pat_clean if pat_clean.endswith("/") else f"{pat_clean}/"
                for cand in self.all_paths:
                    if cand.startswith(dir_pref):
                        cur_matched.append(cand)
                # Also check intra-wiki normalization
                if not cur_matched:
                    for cand in self.all_paths:
                        if match_applies_to_pattern(
                            pat_clean,
                            cand,
                            known_dirs=self.known_dirs,
                            known_wiki_prefixes=self.known_wiki_prefixes,
                            wiki_rel_posix=wiki_rel,
                        ):
                            cur_matched.append(cand)
            else:
                for cand in self.all_paths:
                    if match_applies_to_pattern(
                        pat_clean,
                        cand,
                        known_dirs=self.known_dirs,
                        known_wiki_prefixes=self.known_wiki_prefixes,
                        wiki_rel_posix=wiki_rel,
                    ):
                        cur_matched.append(cand)

            self._pattern_cache[pat_clean] = cur_matched
            matched.update(cur_matched)

        return sorted(matched)

    def get_content(self, rel_posix_path: str) -> str | None:
        if self.overlay_fs and rel_posix_path in self.overlay_fs:
            return self.overlay_fs[rel_posix_path]
        try:
            wiki_rel = rel_posix(self.wiki_root, self.project_root)
            norm_wiki = rel_posix_path[len(wiki_rel) + 1:] if rel_posix_path.startswith(f"{wiki_rel}/") else rel_posix_path
            if self.overlay_fs and norm_wiki in self.overlay_fs:
                return self.overlay_fs[norm_wiki]
        except ValueError:
            pass

        disk_path = self.project_root / rel_posix_path
        if disk_path.is_file():
            try:
                return disk_path.read_text(encoding="utf-8")
            except Exception:
                return None
        return None


def compute_file_content_digest(
    file_path: Path | None,
    content_bytes: bytes | None = None,
) -> str | None:
    """Compute sha256:<16-hex> digest using 64 KB chunk byte-streaming.

    Normalizes \\r\\n -> \\n and strips UTF-8 BOM.
    Binary files (null byte in first 8KB) are hashed raw.
    """
    hasher = hashlib.sha256()

    if content_bytes is not None:
        if len(content_bytes) > MAX_DRIFT_FILE_SIZE:
            return None
        if b"\x00" in content_bytes[:8192]:
            hasher.update(content_bytes)
        else:
            b = content_bytes
            if b.startswith(b"\xef\xbb\xbf"):
                b = b[3:]
            b = b.replace(b"\r\n", b"\n")
            hasher.update(b)
        return "sha256:" + hasher.hexdigest()[:16]

    if file_path is None or not file_path.is_file():
        return None

    try:
        st = file_path.stat()
        if st.st_size > MAX_DRIFT_FILE_SIZE:
            return None
        cache_key = (file_path.as_posix(), st.st_mtime_ns, st.st_size)
        if cache_key in _FILE_HASH_CACHE:
            return _FILE_HASH_CACHE[cache_key]

        with open(file_path, "rb") as f:
            chunk0 = f.read(65536)
            if not chunk0:
                res = "sha256:" + hasher.hexdigest()[:16]
                _FILE_HASH_CACHE[cache_key] = res
                return res

            is_binary = b"\x00" in chunk0[:8192]
            if is_binary:
                hasher.update(chunk0)
                while True:
                    chunk = f.read(65536)
                    if not chunk:
                        break
                    hasher.update(chunk)
            else:
                if chunk0.startswith(b"\xef\xbb\xbf"):
                    chunk0 = chunk0[3:]

                carry_r = False
                if chunk0.endswith(b"\r"):
                    chunk0_norm = chunk0[:-1].replace(b"\r\n", b"\n")
                    carry_r = True
                else:
                    chunk0_norm = chunk0.replace(b"\r\n", b"\n")
                hasher.update(chunk0_norm)

                while True:
                    chunk = f.read(65536)
                    if not chunk:
                        if carry_r:
                            hasher.update(b"\r")
                        break

                    if carry_r:
                        if chunk.startswith(b"\n"):
                            hasher.update(b"\n")
                            chunk = chunk[1:]
                        else:
                            hasher.update(b"\r")
                        carry_r = False

                    if chunk.endswith(b"\r"):
                        chunk_norm = chunk[:-1].replace(b"\r\n", b"\n")
                        carry_r = True
                    else:
                        chunk_norm = chunk.replace(b"\r\n", b"\n")
                    hasher.update(chunk_norm)

        res = "sha256:" + hasher.hexdigest()[:16]
        _FILE_HASH_CACHE[cache_key] = res
        return res
    except OSError:
        return None


def compute_wiki_article_digest(content: str) -> str:
    """Compute deterministic content digest for an intra-wiki markdown article.

    Excludes volatile fields: applies_to_digest, applies_to_count, last_updated.
    """
    try:
        meta, body = parse_frontmatter(content)
        stable_meta = {
            k: v for k, v in meta.items()
            if k not in VOLATILE_FRONTMATTER_FIELDS
        }
        meta_json = json.dumps(stable_meta, sort_keys=True, ensure_ascii=False, default=str)
        norm_body = body.replace("\r\n", "\n").strip()
        payload = (meta_json + "\n" + norm_body).encode("utf-8")
        return "sha256:" + hashlib.sha256(payload).hexdigest()[:16]
    except Exception:
        norm = content.replace("\r\n", "\n").strip().encode("utf-8")
        return "sha256:" + hashlib.sha256(norm).hexdigest()[:16]


def _resolve_contained_path(
    project_root: Path,
    rel_posix_path: str,
    *,
    resolved_root: Path | None = None,
) -> Path:
    """Resolve `project_root / rel_posix_path` and verify it remains strictly inside `project_root`.

    Raises ValueError if the resolved path (including symlink targets or `..` traversals)
    escapes `project_root`.
    """
    p_root = resolved_root if resolved_root is not None else project_root.resolve()
    candidate = (p_root / rel_posix_path).resolve()
    if not candidate.is_relative_to(p_root):
        raise ValueError(
            f"Path '{rel_posix_path}' resolves outside project root '{p_root}' (resolved: '{candidate}')."
        )
    return candidate


def compute_applies_to_manifest(
    patterns: list[str],
    project_root: Path,
    wiki_root: Path,
    exclude_self_path: str | None = None,
    overlay_fs: dict[str, str] | None = None,
    workspace_index: WorkspaceIndex | None = None,
) -> tuple[str | None, int, dict[str, str]]:
    """Compute master digest, target count, and individual leaf target digests."""
    p_root = project_root.resolve()
    w_root = wiki_root.resolve()
    ws_index = workspace_index or WorkspaceIndex.build(p_root, w_root, overlay_fs=overlay_fs)

    try:
        wiki_rel = rel_posix(w_root, p_root)
    except ValueError:
        wiki_rel = ".brain-79"

    norm_self = normalize_wiki_rel_path(exclude_self_path) if exclude_self_path else None
    norm_self_proj = f"{wiki_rel}/{norm_self}" if norm_self else None

    matched = ws_index.find_matching_files(patterns)
    targets: dict[str, str] = {}

    for p in matched:
        if norm_self and (p == norm_self or p == norm_self_proj):
            continue

        d: str | None = None
        content_overlay: str | None = None
        if ws_index.overlay_fs:
            if p in ws_index.overlay_fs:
                content_overlay = ws_index.overlay_fs[p]
            elif p.startswith(f"{wiki_rel}/"):
                sub_p = p[len(wiki_rel) + 1:]
                if sub_p in ws_index.overlay_fs:
                    content_overlay = ws_index.overlay_fs[sub_p]

        if content_overlay is not None:
            if p.startswith(f"{wiki_rel}/") and p.endswith(".md"):
                d = compute_wiki_article_digest(content_overlay)
            else:
                d = compute_file_content_digest(None, content_bytes=content_overlay.encode("utf-8"))
        else:
            try:
                disk_p = ws_index.resolve_contained_path(p)
            except ValueError:
                continue
            if p.startswith(f"{wiki_rel}/") and p.endswith(".md"):
                try:
                    d = compute_wiki_article_digest(disk_p.read_text(encoding="utf-8"))
                except Exception:
                    d = compute_file_content_digest(disk_p)
            else:
                d = compute_file_content_digest(disk_p)

        if d is not None:
            targets[p] = d

    if not targets:
        return None, 0, {}

    canonical_manifest_str = "\n".join(f"{p}:{targets[p]}" for p in sorted(targets.keys()))
    master_digest = "sha256:" + hashlib.sha256(canonical_manifest_str.encode("utf-8")).hexdigest()[:16]
    return master_digest, len(targets), targets


def rebuild_drift_manifest(
    wiki_root: Path,
    project_root: Path | None = None,
    *,
    persist: bool = True,
    workspace_index: WorkspaceIndex | None = None,
) -> dict[str, Any]:
    """Deterministically hydrate .drift_manifest.json from active Markdown articles without masking drift.

    Zero-masking invariant: an article's `targets` map is hydrated ONLY when its current
    computed digest matches its frontmatter `applies_to_digest`. When `curr_digest != stored_digest`,
    the article is omitted from the manifest so real drift remains visible.
    """
    w_root = wiki_root.resolve()
    p_root = (project_root or w_root.parent or get_project_root()).resolve()
    ws_index = workspace_index or WorkspaceIndex.build(p_root, w_root)

    manifest: dict[str, Any] = {"version": "1.0", "articles": {}}
    non_active = INACTIVE_STATUSES | PRE_IMPLEMENTATION_STATUSES

    if w_root.is_dir():
        for md_file in sorted(w_root.rglob("*.md")):
            if md_file.is_symlink():
                continue
            try:
                rel = md_file.relative_to(w_root)
                rel_str = rel.as_posix()
                if rel_str in ("INDEX.md", "SCHEMA.md") or rel.parts[0] in ("_raw", ".locks", "handoffs"):
                    continue
            except ValueError:
                continue

            try:
                content = md_file.read_text(encoding="utf-8")
                meta, _ = parse_frontmatter(content)
            except Exception:
                continue

            status = str(meta.get("status", "")).lower()
            stability = str(meta.get("stability", "")).lower()
            if status in non_active or stability in non_active:
                continue

            applies_val = meta.get("applies_to")
            stored_digest = meta.get("applies_to_digest")
            if not applies_val or not stored_digest:
                continue

            patterns = (
                [applies_val] if isinstance(applies_val, str) else [str(x) for x in applies_val if x]
            )
            if not patterns:
                continue

            curr_digest, curr_count, curr_targets = compute_applies_to_manifest(
                patterns,
                p_root,
                w_root,
                exclude_self_path=rel_str,
                workspace_index=ws_index,
            )

            # Zero-masking invariant: hydrate ONLY when curr_digest == stored_digest
            if curr_digest is not None and curr_digest == stored_digest:
                manifest["articles"][rel_str] = {
                    "digest": curr_digest,
                    "count": curr_count,
                    "targets": curr_targets,
                }

    if persist:
        try:
            save_drift_manifest(w_root, manifest)
        except (PermissionError, OSError):
            pass

    return manifest


def load_drift_manifest(
    wiki_root: Path,
    *,
    auto_rebuild: bool = False,
    persist: bool = True,
    project_root: Path | None = None,
    workspace_index: WorkspaceIndex | None = None,
) -> dict[str, Any]:
    """Load .drift_manifest.json from wiki_root safely, optionally rebuilding on demand."""
    manifest_file = wiki_root / ".drift_manifest.json"
    if not manifest_file.is_file():
        if auto_rebuild:
            return rebuild_drift_manifest(
                wiki_root,
                project_root=project_root,
                persist=persist,
                workspace_index=workspace_index,
            )
        return {"version": "1.0", "articles": {}}
    try:
        data = json.loads(manifest_file.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            if auto_rebuild:
                return rebuild_drift_manifest(
                    wiki_root,
                    project_root=project_root,
                    persist=persist,
                    workspace_index=workspace_index,
                )
            return {"version": "1.0", "articles": {}}
        if "articles" not in data or not isinstance(data["articles"], dict):
            data["articles"] = {}
        return data
    except Exception:
        if auto_rebuild:
            return rebuild_drift_manifest(
                wiki_root,
                project_root=project_root,
                persist=persist,
                workspace_index=workspace_index,
            )
        return {"version": "1.0", "articles": {}}


def save_drift_manifest(wiki_root: Path, manifest_data: dict[str, Any]) -> None:
    """Save .drift_manifest.json with centralized locking and atomic rename."""
    manifest_file = wiki_root / ".drift_manifest.json"
    drift_lock = acquire_wiki_lock(wiki_root, ".drift_manifest.json", timeout=10.0)
    with drift_lock:
        from brain79.core.locks import create_temp_path

        content = json.dumps(manifest_data, indent=2, sort_keys=True) + "\n"
        tmp_file = create_temp_path(manifest_file)
        try:
            tmp_file.write_text(content, encoding="utf-8", newline="\n")
            atomic_replace_with_retry(tmp_file, manifest_file)
        finally:
            tmp_file.unlink(missing_ok=True)


def get_file_last_modified_date(file_path: Path, project_root: Path) -> str | None:
    """Get the last modification date (YYYY-MM-DD) for a workspace file."""
    if not file_path.exists() or not file_path.is_file():
        return None

    try:
        rel_str = file_path.relative_to(project_root).as_posix()
    except ValueError:
        rel_str = file_path.as_posix()

    if rel_str in _GIT_DATE_CACHE:
        return _GIT_DATE_CACHE[rel_str]

    try:
        commit_date = git_last_commit_for_path(project_root, rel_str, fmt="%cs", timeout=5.0)
        if commit_date and len(commit_date) == 10 and commit_date.count("-") == 2:
            try:
                status_res = git_status_porcelain(project_root, paths=[rel_str], timeout=5.0, check_repo=False)
                if status_res.returncode == 0 and status_res.stdout.strip():
                    mtime = file_path.stat().st_mtime
                    fs_date = datetime.fromtimestamp(mtime, tz=UTC).strftime("%Y-%m-%d")
                    if fs_date > commit_date:
                        return fs_date
            except (GitError, OSError):
                pass
            _GIT_DATE_CACHE[rel_str] = commit_date
            return commit_date
    except (NotAGitRepoError, GitTimeoutError, GitError, OSError, ValueError):
        pass

    try:
        mtime = file_path.stat().st_mtime
        return datetime.fromtimestamp(mtime, tz=UTC).strftime("%Y-%m-%d")
    except OSError:
        return None


def find_matching_workspace_files(
    patterns: list[str],
    project_root: Path,
    workspace_index: WorkspaceIndex | None = None,
) -> list[Path]:
    """Find all existing files in project_root that match the given applies_to patterns."""
    p_root = project_root.resolve()
    if workspace_index is not None:
        rel_paths = workspace_index.find_matching_files(patterns)
        return [p_root / p for p in rel_paths]

    w_root = (p_root / ".brain-79").resolve()
    ws = WorkspaceIndex.build(p_root, w_root)
    rel_paths = ws.find_matching_files(patterns)
    return [p_root / p for p in rel_paths]


def check_article_drift(
    article_path: Path | str,
    wiki_root: Path | None = None,
    project_root: Path | None = None,
    workspace_index: WorkspaceIndex | None = None,
    overlay_fs: dict[str, str] | None = None,
    manifest_data: dict[str, Any] | None = None,
    _visited: frozenset[str] = frozenset(),
) -> list[dict[str, Any]]:
    """Check if a wiki article has direct or transitive drift against governed targets.

    Supports exact per-file attribution (modified, deleted, added, missing) and
    recursive multi-hop transitive closure across intra-wiki child targets with cycle immunity.
    """
    w_root = (wiki_root or get_wiki_root()).resolve()
    p_root = (project_root or w_root.parent or get_project_root()).resolve()

    try:
        wiki_rel = rel_posix(w_root, p_root)
    except ValueError:
        wiki_rel = ".brain-79"

    if isinstance(article_path, Path):
        try:
            rel_article = article_path.resolve().relative_to(w_root).as_posix()
        except ValueError:
            rel_article = normalize_wiki_rel_path(str(article_path))
    else:
        p_str = str(article_path)
        if Path(p_str).is_absolute():
            try:
                rel_article = Path(p_str).resolve().relative_to(w_root).as_posix()
            except ValueError:
                rel_article = normalize_wiki_rel_path(p_str)
        else:
            rel_article = normalize_wiki_rel_path(p_str)

    if rel_article in _visited:
        return []

    article_disk = w_root / rel_article

    content: str | None = None
    if overlay_fs and rel_article in overlay_fs:
        content = overlay_fs[rel_article]
    elif article_disk.is_file():
        try:
            content = article_disk.read_text(encoding="utf-8")
        except Exception:
            return []
    else:
        return []

    try:
        meta, _ = parse_frontmatter(content)
    except Exception:
        return []

    status = str(meta.get("status", "")).lower()
    stability = str(meta.get("stability", "")).lower()
    non_active = INACTIVE_STATUSES | PRE_IMPLEMENTATION_STATUSES
    if status in non_active or stability in non_active:
        return []

    applies_val = meta.get("applies_to")
    if not applies_val:
        return []

    patterns = (
        [applies_val] if isinstance(applies_val, str) else [str(x) for x in applies_val if x]
    )
    if not patterns:
        return []

    if workspace_index is None:
        workspace_index = WorkspaceIndex.build(p_root, w_root, overlay_fs=overlay_fs)
    if manifest_data is None:
        manifest_data = load_drift_manifest(
            w_root,
            auto_rebuild=True,
            persist=False,
            project_root=p_root,
            workspace_index=workspace_index,
        )

    if rel_article in workspace_index.drift_cache and not _visited:
        return workspace_index.drift_cache[rel_article]

    curr_digest, curr_count, curr_targets = compute_applies_to_manifest(
        patterns,
        p_root,
        w_root,
        exclude_self_path=rel_article,
        overlay_fs=overlay_fs,
        workspace_index=workspace_index,
    )

    manifest_articles = manifest_data.get("articles", {})
    manifest_entry = manifest_articles.get(rel_article)
    stored_digest = meta.get("applies_to_digest")

    drifts: list[dict[str, Any]] = []

    # Step A: Direct Drift
    if stored_digest:
        if manifest_entry and isinstance(manifest_entry, dict) and "targets" in manifest_entry:
            manifest_targets: dict[str, str] = manifest_entry.get("targets", {})
            # Check modified and deleted targets
            for old_target, old_hash in sorted(manifest_targets.items()):
                if old_target not in curr_targets:
                    drifts.append({
                        "article_path": rel_article,
                        "target_file": old_target,
                        "workspace_file": old_target,
                        "drift_kind": "deleted",
                        "message": f"governed file deleted: {old_target}",
                    })
                elif curr_targets[old_target] != old_hash:
                    drifts.append({
                        "article_path": rel_article,
                        "target_file": old_target,
                        "workspace_file": old_target,
                        "drift_kind": "modified",
                        "message": f"governed file modified: {old_target}",
                    })
            # Check added targets
            for new_target in sorted(curr_targets.keys()):
                if new_target not in manifest_targets:
                    drifts.append({
                        "article_path": rel_article,
                        "target_file": new_target,
                        "workspace_file": new_target,
                        "drift_kind": "added",
                        "message": f"new file matched applies_to pattern: {new_target}",
                    })
            # Check missing (pattern matched 0 files in active article)
            if curr_count == 0:
                drifts.append({
                    "article_path": rel_article,
                    "target_file": patterns[0],
                    "workspace_file": patterns[0],
                    "drift_kind": "missing",
                    "message": "governed files missing: pattern matched 0 files in active article",
                })
        else:
            # Contingency fallback when manifest_targets is absent (R-1.4)
            if curr_digest != stored_digest:
                stored_count_raw = meta.get("applies_to_count")
                stored_count: int | None = None
                if stored_count_raw is not None:
                    try:
                        stored_count = int(stored_count_raw)
                    except (TypeError, ValueError):
                        stored_count = None

                if curr_count == 0:
                    fallback_kind = "missing"
                elif stored_count is not None and curr_count > stored_count:
                    fallback_kind = "added"
                elif stored_count is not None and curr_count < stored_count:
                    fallback_kind = "deleted"
                else:
                    fallback_kind = "modified"

                sorted_targets = sorted(curr_targets.keys())
                rep_target = sorted_targets[0] if sorted_targets else patterns[0]
                drifts.append({
                    "article_path": rel_article,
                    "target_file": rep_target,
                    "workspace_file": rep_target,
                    "drift_kind": fallback_kind,
                    "fallback_targets": sorted_targets,
                    "message": f"governed targets digest changed ({stored_digest} -> {curr_digest})",
                })
    else:
        # Fallback timestamp comparison for unhashed legacy articles without applies_to_digest
        last_updated_raw = meta.get("last_updated")
        if last_updated_raw:
            if isinstance(last_updated_raw, (date, datetime)):
                last_updated = last_updated_raw.strftime("%Y-%m-%d")
            else:
                last_updated = str(last_updated_raw).strip()[:10]

            if re.match(r"^\d{4}-\d{2}-\d{2}$", last_updated):
                for ws_rel in sorted(curr_targets.keys()):
                    ws_file = p_root / ws_rel
                    file_date = get_file_last_modified_date(ws_file, p_root)
                    if file_date and file_date > last_updated:
                        drifts.append({
                            "article_path": rel_article,
                            "target_file": ws_rel,
                            "workspace_file": ws_rel,
                            "file_date": file_date,
                            "article_date": last_updated,
                            "drift_kind": "modified",
                            "message": f"file modified ({file_date}) after article last_updated ({last_updated})",
                        })

    # Step B: Recursive multi-hop transitive closure
    for target_rel in sorted(curr_targets.keys()):
        if target_rel.startswith(f"{wiki_rel}/") and target_rel.endswith(".md"):
            child_rel = target_rel[len(wiki_rel) + 1:]
            if child_rel in ("INDEX.md", "SCHEMA.md") or child_rel.startswith("_raw/") or child_rel.startswith(".locks/"):
                continue
            if child_rel in _visited or child_rel == rel_article:
                continue

            if child_rel in workspace_index.drift_cache:
                child_drifts = workspace_index.drift_cache[child_rel]
            else:
                child_drifts = check_article_drift(
                    child_rel,
                    wiki_root=w_root,
                    project_root=p_root,
                    workspace_index=workspace_index,
                    overlay_fs=overlay_fs,
                    manifest_data=manifest_data,
                    _visited=_visited | {rel_article},
                )

            if child_drifts:
                for cd in child_drifts:
                    drifts.append({
                        "article_path": rel_article,
                        "target_file": target_rel,
                        "workspace_file": target_rel,
                        "drift_kind": "transitive",
                        "child_article": child_rel,
                        "child_drift": cd,
                        "message": f"transitive drift via child article {child_rel}: {cd.get('message', cd.get('drift_kind', 'modified'))}",
                    })

    if not _visited:
        workspace_index.drift_cache[rel_article] = drifts
    return drifts


def detect_all_drift(
    wiki_root: Path | None = None,
    md_files: list[Path] | None = None,
    project_root: Path | None = None,
    workspace_index: WorkspaceIndex | None = None,
    overlay_fs: dict[str, str] | None = None,
    manifest_data: dict[str, Any] | None = None,
    git_cache: Any = None,
) -> list[dict[str, Any]]:
    """Detect documentation drift across all active articles in the wiki."""
    w_root = (wiki_root or get_wiki_root()).resolve()
    p_root = (project_root or w_root.parent or get_project_root()).resolve()

    if workspace_index is None:
        workspace_index = WorkspaceIndex.build(
            p_root, w_root, overlay_fs=overlay_fs, git_cache=git_cache
        )
    if manifest_data is None:
        manifest_data = load_drift_manifest(
            w_root,
            auto_rebuild=True,
            persist=False,
            project_root=p_root,
            workspace_index=workspace_index,
        )

    files = md_files if md_files is not None else sorted(w_root.rglob("*.md"))
    all_drifts: list[dict[str, Any]] = []

    for md_file in files:
        try:
            rel = md_file.relative_to(w_root)
            rel_str = rel.as_posix()
            if rel_str in ("INDEX.md", "SCHEMA.md") or rel.parts[0] in ("_raw", ".locks", "handoffs"):
                continue
        except ValueError:
            continue

        drifts = check_article_drift(
            md_file,
            wiki_root=w_root,
            project_root=p_root,
            workspace_index=workspace_index,
            overlay_fs=overlay_fs,
            manifest_data=manifest_data,
        )
        all_drifts.extend(drifts)

    return all_drifts


# Backward-compatible re-exports from pluggable AST inspector subsystem (Phase 10 Stage 4: R-4.1)
from brain79.core.ast_guards import (
    extract_public_python_signatures,
    has_public_python_api_changes,
)
