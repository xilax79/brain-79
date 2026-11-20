"""Deterministic brownfield repository boundary mapper for `bootstrap --auto-map`.

Uses Python stdlib only (tomllib, json, re, os, pathlib) plus existing brain79 primitives
to detect module boundaries, rank them by manifest presence and Git churn, and guarantee
strict zero-overlap `applies_to` governance patterns by construction.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import re
import tomllib

from brain79.core.bootstrap import _EXCLUDED_DIRS
from brain79.core.drift import match_applies_to_pattern
from brain79.core.git_ops import GitError, GitTimeoutError, NotAGitRepoError, git_recent_file_churn

_AUTO_MAP_EXCLUDED_DIRS: frozenset[str] = _EXCLUDED_DIRS | frozenset({
    "tests",
    "test",
    "__tests__",
    "docs",
    ".github",
})

_SOURCE_EXTENSIONS: dict[str, str] = {
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".rs": "rust",
    ".go": "go",
    ".java": "java",
    ".kt": "kotlin",
    ".rb": "ruby",
    ".php": "php",
    ".cs": "csharp",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".c": "c",
    ".h": "c",
    ".swift": "swift",
    ".scala": "scala",
    ".ex": "elixir",
    ".exs": "elixir",
    ".sh": "shell",
}

_MANIFEST_FILENAMES: frozenset[str] = frozenset({
    "pyproject.toml",
    "package.json",
    "Cargo.toml",
    "go.mod",
})


@dataclass
class ModuleProposal:
    """Proposed wiki article governance boundary for a repository module."""

    slug: str
    article_path: str
    article_type: str
    applies_to: list[str]
    file_count: int
    recent_commits: int
    primary_language: str
    confidence: str
    signals: list[str] = field(default_factory=list)


@dataclass
class AutoMapReport:
    """Structured result of deterministic repository boundary analysis."""

    proposals: list[ModuleProposal]
    truncated_count: int
    git_available: bool
    total_code_files: int
    warnings: list[str] = field(default_factory=list)


def _slugify(raw: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", raw.strip().lower()).strip("-")
    return s or "module"


def _extract_manifest_name(dir_path: Path) -> tuple[str | None, str | None]:
    """Inspect supported manifests in dir_path using stdlib only. Returns (name, manifest_file)."""
    pyproject = dir_path / "pyproject.toml"
    if pyproject.is_file():
        try:
            data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
            proj = data.get("project", {})
            if isinstance(proj, dict) and isinstance(proj.get("name"), str) and proj["name"].strip():
                return proj["name"].strip(), "pyproject.toml"
            tool = data.get("tool", {})
            poetry = tool.get("poetry", {}) if isinstance(tool, dict) else {}
            if isinstance(poetry, dict) and isinstance(poetry.get("name"), str) and poetry["name"].strip():
                return poetry["name"].strip(), "pyproject.toml"
            return dir_path.name, "pyproject.toml"
        except Exception:
            return dir_path.name, "pyproject.toml"

    pkg_json = dir_path / "package.json"
    if pkg_json.is_file():
        try:
            data = json.loads(pkg_json.read_text(encoding="utf-8"))
            if isinstance(data, dict) and isinstance(data.get("name"), str) and data["name"].strip():
                raw_name = data["name"].strip().split("/")[-1]
                return raw_name, "package.json"
            return dir_path.name, "package.json"
        except Exception:
            return dir_path.name, "package.json"

    cargo = dir_path / "Cargo.toml"
    if cargo.is_file():
        try:
            data = tomllib.loads(cargo.read_text(encoding="utf-8"))
            pkg = data.get("package", {})
            if isinstance(pkg, dict) and isinstance(pkg.get("name"), str) and pkg["name"].strip():
                return pkg["name"].strip(), "Cargo.toml"
            return dir_path.name, "Cargo.toml"
        except Exception:
            return dir_path.name, "Cargo.toml"

    go_mod = dir_path / "go.mod"
    if go_mod.is_file():
        try:
            for line in go_mod.read_text(encoding="utf-8").splitlines():
                m = re.match(r"^\s*module\s+(\S+)", line)
                if m:
                    mod_name = m.group(1).strip().rstrip("/").split("/")[-1]
                    return mod_name, "go.mod"
            return dir_path.name, "go.mod"
        except Exception:
            return dir_path.name, "go.mod"

    return None, None


def _narrow_parent_patterns(
    dir_rel: str,
    direct_files: list[str],
    has_proposed_child: bool,
) -> list[str]:
    """Build applies_to patterns for dir_rel, narrowing to single-level globs when a child is also proposed."""
    if not has_proposed_child:
        if dir_rel == ".":
            exts = sorted({Path(f).suffix for f in direct_files if Path(f).suffix})
            return [f"*{ext}" for ext in exts] if exts else sorted(direct_files)
        return [f"{dir_rel}/**"]

    # Narrow parent to single-level globs so child subdirectories are never matched
    exts = sorted({Path(f).suffix for f in direct_files if Path(f).suffix})
    if not exts:
        return sorted(direct_files)
    if dir_rel == ".":
        return [f"*{ext}" for ext in exts]
    return [f"{dir_rel}/*{ext}" for ext in exts]


def analyze_repository_boundaries(
    project_root: Path,
    *,
    max_modules: int = 12,
    max_walk_files: int = 5000,
) -> AutoMapReport:
    """Deterministically analyze repository boundaries and emit zero-overlap ModuleProposals."""
    root = project_root.resolve()
    warnings: list[str] = []

    # 1. Git churn signal (degrades cleanly on non-Git or zero-commit repos)
    git_available = False
    churn_map: dict[str, int] = {}
    try:
        churn_map = git_recent_file_churn(root, max_commits=200, timeout=5.0)
        git_available = True
    except NotAGitRepoError:
        git_available = False
    except (GitTimeoutError, GitError, OSError) as exc:
        git_available = False
        warnings.append(f"Git churn unavailable: {exc}")

    # 2. Bounded directory walk (depth <= 3, followlinks=False, capped at max_walk_files)
    files_by_dir: dict[str, list[str]] = {}
    manifests_by_dir: dict[str, tuple[str, str]] = {}
    all_code_files: list[str] = []
    walked_count = 0

    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        curr_dir = Path(dirpath)
        try:
            rel_dir = curr_dir.relative_to(root)
        except ValueError:
            dirnames[:] = []
            continue

        depth = len(rel_dir.parts)
        dirnames[:] = sorted(
            d for d in dirnames
            if d not in _AUTO_MAP_EXCLUDED_DIRS and not d.startswith(".")
        )
        if depth >= 3:
            dirnames[:] = []

        rel_dir_str = "." if depth == 0 else rel_dir.as_posix()

        # Check manifests at this directory (skip root manifest when subdirs exist unless root has code)
        if any(f in _MANIFEST_FILENAMES for f in filenames):
            m_name, m_file = _extract_manifest_name(curr_dir)
            if m_name and m_file:
                manifests_by_dir[rel_dir_str] = (m_name, m_file)

        for fname in sorted(filenames):
            if walked_count >= max_walk_files:
                break
            walked_count += 1
            full_f = curr_dir / fname
            if full_f.is_symlink():
                continue
            try:
                resolved_f = full_f.resolve()
                if not resolved_f.is_relative_to(root):
                    continue
            except OSError:
                continue

            ext = full_f.suffix.lower()
            if ext not in _SOURCE_EXTENSIONS:
                continue

            rel_f = full_f.relative_to(root).as_posix()
            files_by_dir.setdefault(rel_dir_str, []).append(rel_f)
            all_code_files.append(rel_f)

        if walked_count >= max_walk_files:
            warnings.append(f"Walk capped at {max_walk_files} files.")
            break

    # 3. Build candidate modules for directories with >= 1 direct source file
    # Propagate non-root manifest metadata to nested source directories when the manifest
    # directory itself has no direct source files (e.g. crates/auth/Cargo.toml + crates/auth/src/lib.rs).
    for m_dir, m_info in list(manifests_by_dir.items()):
        if m_dir == "." or m_dir in files_by_dir:
            continue
        src_child = f"{m_dir}/src"
        if src_child in files_by_dir and src_child not in manifests_by_dir:
            manifests_by_dir[src_child] = m_info
            continue
        prefix = m_dir + "/"
        nested = sorted(
            (d for d in files_by_dir if d.startswith(prefix) and d not in manifests_by_dir),
            key=lambda d: (d.count("/"), d),
        )
        if nested:
            manifests_by_dir[nested[0]] = m_info

    candidate_dirs: set[str] = set(files_by_dir.keys())

    # Determine which candidate dirs have a proposed child directory
    def _has_child(d_str: str, all_dirs: set[str]) -> bool:
        if d_str == ".":
            return any(other != "." for other in all_dirs)
        prefix = d_str + "/"
        return any(other.startswith(prefix) for other in all_dirs)

    raw_candidates: list[tuple[bool, int, int, str, str, ModuleProposal]] = []
    used_slugs: set[str] = set()

    for dir_rel in sorted(candidate_dirs):
        direct_files = sorted(files_by_dir.get(dir_rel, []))
        if not direct_files:
            continue

        has_child = _has_child(dir_rel, candidate_dirs)
        patterns = _narrow_parent_patterns(dir_rel, direct_files, has_child)

        # Compute matched files for accurate file_count and churn
        matched_files = [
            f for f in all_code_files
            if any(match_applies_to_pattern(pat, f) for pat in patterns)
        ]
        if not matched_files:
            continue

        lang_counts = Counter(_SOURCE_EXTENSIONS.get(Path(f).suffix.lower(), "unknown") for f in matched_files)
        primary_lang = lang_counts.most_common(1)[0][0]
        recent_commits = sum(churn_map.get(f, 0) for f in matched_files)

        has_manifest = dir_rel in manifests_by_dir
        signals: list[str] = []
        if has_manifest:
            m_name, m_file = manifests_by_dir[dir_rel]
            base_slug = _slugify(m_name)
            signals.append(f"manifest:{m_file}")
        else:
            base_slug = _slugify(Path(dir_rel).name if dir_rel != "." else root.name)
            signals.append("directory-topology")

        if recent_commits > 0:
            signals.append(f"git-churn:{recent_commits}")

        slug = base_slug
        suffix = 2
        while slug in used_slugs:
            slug = f"{base_slug}-{suffix}"
            suffix += 1
        used_slugs.add(slug)

        article_type = "architecture" if has_manifest else "feature"
        article_dir = "architecture" if article_type == "architecture" else "features"
        confidence = "high" if has_manifest else ("medium" if recent_commits > 0 or len(matched_files) >= 2 else "low")

        proposal = ModuleProposal(
            slug=slug,
            article_path=f"{article_dir}/{slug}.md",
            article_type=article_type,
            applies_to=patterns,
            file_count=len(matched_files),
            recent_commits=recent_commits,
            primary_language=primary_lang,
            confidence=confidence,
            signals=signals,
        )
        raw_candidates.append((has_manifest, recent_commits, len(matched_files), slug, dir_rel, proposal))

    # 4. Sort by (has_manifest DESC, recent_commits DESC, file_count DESC, slug ASC)
    raw_candidates.sort(key=lambda item: (not item[0], -item[1], -item[2], item[3]))

    cap = max(1, int(max_modules))
    selected = [item[5] for item in raw_candidates[:cap]]
    truncated_count = max(0, len(raw_candidates) - len(selected))

    # 5. Pairwise zero-overlap verification pass (R-3.3 / AC-12.9)
    claimed_files: set[str] = set()
    final_proposals: list[ModuleProposal] = []
    for prop in selected:
        matched = {
            f for f in all_code_files
            if any(match_applies_to_pattern(pat, f) for pat in prop.applies_to)
        }
        overlap = matched & claimed_files
        if overlap:
            # Narrow to disjoint exact files to guarantee strictly 0 pairwise intersection
            disjoint = sorted(matched - claimed_files)
            if not disjoint:
                continue
            prop.applies_to = disjoint
            prop.file_count = len(disjoint)
            matched = set(disjoint)
        claimed_files.update(matched)
        final_proposals.append(prop)

    return AutoMapReport(
        proposals=final_proposals,
        truncated_count=truncated_count,
        git_available=git_available,
        total_code_files=len(all_code_files),
        warnings=warnings,
    )


def render_auto_map_section(report: AutoMapReport) -> str:
    """Render the Markdown `## Auto-mapped governance boundaries` section for bootstrap output."""
    lines = [
        "## Auto-mapped governance boundaries",
        "",
        f"- **Code files scanned**: {report.total_code_files}",
        f"- **Git churn available**: {'yes' if report.git_available else 'no'}",
        f"- **Proposed modules**: {len(report.proposals)}"
        + (f" ({report.truncated_count} additional candidates truncated)" if report.truncated_count else ""),
        "",
    ]
    if not report.proposals:
        lines.append("*No source code modules detected.*")
        return "\n".join(lines)

    lines.extend([
        "| Slug | Article path | Type | Files | Recent commits | Language | Confidence |",
        "|---|---|---|---:|---:|---|---|",
    ])
    for p in report.proposals:
        lines.append(
            f"| `{p.slug}` | `{p.article_path}` | `{p.article_type}` | {p.file_count} | {p.recent_commits} | {p.primary_language} | {p.confidence} |"
        )

    lines.extend([
        "",
        "### Ready-to-paste frontmatter blocks",
        "",
    ])
    for p in report.proposals:
        lines.append(f"#### `{p.article_path}`")
        lines.append("```yaml")
        lines.append("---")
        lines.append(f"type: {p.article_type}")
        lines.append(f"summary: governance overview for {p.slug} ({p.primary_language})")
        lines.append("applies_to:")
        for pat in p.applies_to:
            lines.append(f"  - {pat}")
        lines.append("---")
        lines.append("```")
        lines.append("")

    lines.extend([
        "### Next step",
        "",
        "Seed these articles atomically with `brain79_session_commit(writes=[...])` (or `brain79 write`). All proposed `applies_to` patterns are guaranteed pairwise disjoint (zero anti-sprawl overlap).",
    ])
    return "\n".join(lines)
