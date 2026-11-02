from concurrent.futures import ThreadPoolExecutor, as_completed
import fnmatch
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
from typing import Any
import unicodedata

__all__ = ["ThreadPoolExecutor", "as_completed"]

from brain79.config import get_wiki_root

_EXCLUDED_DIRS = {"_raw", "handoffs"}

_STOP_WORDS: set[str] = {
    # EN
    "the",
    "and",
    "that",
    "with",
    "for",
    "this",
    "from",
    "are",
    "was",
    "were",
    "have",
    "has",
    "had",
    "not",
    "but",
    "you",
    "they",
    "your",
    "their",
    # ES
    "que",
    "con",
    "para",
    "del",
    "los",
    "una",
    "hacer",
    "estar",
    "tener",
    "por",
    "las",
    "como",
    "mas",
    "más",
    "pero",
    "sus",
    "este",
    "esta",
    "está",
    "esté",
    "estés",
    "estén",
    "éste",
    "esto",
    "cómo",
    "qué",
    "aquí",
    "allí",
    # LLM
    "implement",
    "update",
    "create",
    "fix",
    "change",
    "add",
    "remove",
    "delete",
    "modify",
    "refactor",
    "review",
    "analyze",
}


def extract_keywords(task: str) -> list[str]:
    """
    Extract, normalize, deduplicate, and filter search keywords from task description.

    Steps:
    1. NFKC normalization and lowercase.
    2. Purge apostrophes (contractions).
    3. Alphanumeric tokenization (\\w+).
    4. Strict deduplication.
    5. Filter out tokens < 3 chars or in static stop-words list.
    """
    normalized = unicodedata.normalize("NFKC", task.lower())
    cleaned = normalized.replace("'", "").replace("’", "")
    tokens = re.findall(r"\w+", cleaned, re.UNICODE)

    seen: set[str] = set()
    keywords: list[str] = []
    for token in tokens:
        if token not in seen:
            seen.add(token)
            if len(token) >= 3 and token not in _STOP_WORDS:
                keywords.append(token)

    return keywords


def get_wiki_snapshot(wiki_root: Path | None = None) -> list[Path]:
    """
    Build in-memory snapshot of valid wiki articles.

    Filtering rules:
    - Ends with .md
    - File size: 0 < size <= 1MB
    - Excludes files inside _raw/ or handoffs/
    - Returns absolute resolved paths
    """
    w_root = (wiki_root or get_wiki_root()).resolve()
    if not w_root.exists():
        return []

    snapshot: list[Path] = []
    for p in w_root.rglob("*.md"):
        try:
            abs_path = p.resolve()
            rel = abs_path.relative_to(w_root)
            if any(part in _EXCLUDED_DIRS for part in rel.parts):
                continue
            if not abs_path.is_file():
                continue
            stat = abs_path.stat()
            if 0 < stat.st_size <= 1_048_576:
                snapshot.append(abs_path)
        except OSError:
            continue

    snapshot.sort(key=lambda x: str(x.relative_to(w_root)))
    return snapshot


def _search_keyword_rg(rg_path: str, kw: str, tmp_path: Path) -> dict[Path, int]:
    """
    Search keyword using ripgrep --json reading candidate files from tmp_path.

    Note on ripgrep invocation:
    Standard ripgrep binaries do not support `--files-from` (returning exit code 2:
    `rg: unrecognized flag --files-from`). Candidate paths read from tmp_path are
    chunked into positional arguments for maximum cross-platform compatibility.
    """
    is_short_alnum = len(kw) <= 4 and bool(re.match(r"^[a-z0-9]+$", kw))
    pattern = rf"\b{re.escape(kw)}\b" if is_short_alnum else re.escape(kw)

    try:
        file_paths = [
            line for line in tmp_path.read_text(encoding="utf-8").splitlines() if line
        ]
    except Exception:
        return {}

    if not file_paths:
        return {}

    matches: dict[Path, int] = {}
    chunk_size = 500
    for i in range(0, len(file_paths), chunk_size):
        chunk = file_paths[i : i + chunk_size]
        cmd = [
            rg_path,
            "--no-config",
            "--no-messages",
            "--json",
            "-i",
            pattern,
        ] + chunk

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=10,
            )
        except (subprocess.TimeoutExpired, Exception):
            continue

        for line in proc.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                data_obj = json.loads(line)
            except Exception:
                continue
            if not isinstance(data_obj, dict):
                continue
            if data_obj.get("type") == "end":
                data = data_obj.get("data")
                if isinstance(data, dict):
                    path_dict = data.get("path")
                    stats_dict = data.get("stats")
                    if isinstance(path_dict, dict) and isinstance(stats_dict, dict):
                        path_str = path_dict.get("text")
                        count = stats_dict.get("matches", 0)
                        if path_str and isinstance(count, int) and count > 0:
                            try:
                                abs_p = Path(path_str).resolve()
                                matches[abs_p] = matches.get(abs_p, 0) + count
                            except Exception:
                                pass
    return matches


def _search_keyword_python(kw: str, snapshot: list[Path]) -> dict[Path, int]:
    """Search keyword using pure Python regex matching."""
    is_short_alnum = len(kw) <= 4 and bool(re.match(r"^[a-z0-9]+$", kw))
    if is_short_alnum:
        pattern = re.compile(rf"\b{re.escape(kw)}\b", re.IGNORECASE)
    else:
        pattern = re.compile(re.escape(kw), re.IGNORECASE)

    matches: dict[Path, int] = {}
    for p in snapshot:
        try:
            content = p.read_text(encoding="utf-8", errors="ignore")
            count = len(pattern.findall(content))
            if count > 0:
                matches[p.resolve()] = count
        except Exception:
            continue
    return matches


def _search_keyword(
    kw: str, tmp_path: Path | None, snapshot: list[Path]
) -> dict[Path, int]:
    """Dispatch search to ripgrep or pure Python fallback."""
    rg_path = shutil.which("rg")
    if rg_path and tmp_path:
        return _search_keyword_rg(rg_path, kw, tmp_path)
    return _search_keyword_python(kw, snapshot)


def _safe_mtime_ns(p: Path) -> int:
    """Safe getter for st_mtime_ns."""
    try:
        return p.stat().st_mtime_ns
    except OSError:
        return 0


def _match_applies_to(path_pattern: str, target_path: str) -> bool:
    """Check if target_path matches an applies_to glob pattern or prefix."""
    pat = path_pattern.strip().lstrip("/")
    tgt = target_path.strip().lstrip("/")
    if pat == tgt:
        return True
    if fnmatch.fnmatch(tgt, pat):
        return True
    # If pat is a directory without wildcard (e.g. "src/auth/"), match prefix
    if pat.endswith("/") and tgt.startswith(pat):
        return True
    return False


def _extract_paths_from_text(text: str) -> list[str]:
    """Extract candidate workspace file paths or directory paths mentioned in free text."""
    if not text:
        return []
    # Match tokens with / (e.g. src/auth/jwt.py) or known code/doc extensions
    tokens = re.findall(r"(?:[a-zA-Z0-9_\-\.]+/+[a-zA-Z0-9_\-\./]+|[a-zA-Z0-9_\-]+\.(?:py|ts|js|md|json|toml|rs|go|yaml|yml))", text)
    paths: list[str] = []
    for t in tokens:
        cleaned = t.strip("`'\"(),;:")
        if cleaned and cleaned not in paths:
            paths.append(cleaned)
    return paths


def _count_keyword_occurrences(kw: str, text: str) -> int:
    """Count keyword occurrences using word boundaries for short tokens (<=4 chars)."""
    if not kw or not text:
        return 0
    is_short_alnum = len(kw) <= 4 and bool(re.match(r"^[a-z0-9]+$", kw))
    if is_short_alnum:
        pattern = re.compile(rf"\b{re.escape(kw)}\b", re.IGNORECASE)
        return len(pattern.findall(text))
    return text.lower().count(kw.lower())


def rank_context_articles(
    task: str | None = None,
    paths: list[str] | None = None,
    top_n: int = 4,
    wiki_root: Path | None = None,
) -> list[tuple[float, Path, list[str]]]:
    """
    3-Signal Deterministic Context Ranker:
    - Signal 1 (Deterministic Path Binding): Matches applies_to globs against touched paths or paths in task.
    - Signal 2 (Field-Weighted TF-IDF): Searches title/H1/H2/summary/content with word-boundary awareness.
    - Signal 3 (1-Hop ADR Reference Expansion): Pulls accepted ADRs linked from matched articles.

    Returns:
        List of tuples: (score, article_path, hit_reasons)
    """
    from brain79.core.frontmatter import parse_frontmatter
    from brain79.core.navigation import extract_title_and_summary, load_registry

    w_root = (wiki_root or get_wiki_root()).resolve()
    snapshot = get_wiki_snapshot(wiki_root=w_root)
    if not snapshot:
        return []

    registry = load_registry(w_root)
    registry_by_path = {a.get("path"): a for a in registry.get("articles", [])}

    scored_map: dict[Path, tuple[float, list[str]]] = {}

    # Gather explicit paths and paths mentioned in task description (Defect 5)
    extracted_from_task = _extract_paths_from_text(task or "")
    combined_paths = list(paths or [])
    for ep in extracted_from_task:
        if ep not in combined_paths:
            combined_paths.append(ep)

    normalized_paths = [p.strip().lstrip("/") for p in combined_paths if p.strip()]

    # SIGNAL 1: Deterministic Path Match via applies_to
    if normalized_paths:
        for p in snapshot:
            rel_str = str(p.relative_to(w_root))
            entry = registry_by_path.get(rel_str)
            applies_patterns: list[str] = []
            if entry and entry.get("applies_to"):
                applies_patterns = entry.get("applies_to", [])
            else:
                # Direct check in frontmatter if not in registry
                try:
                    c = p.read_text(encoding="utf-8")
                    if c.startswith("---\n"):
                        meta, _ = parse_frontmatter(c)
                        if meta and meta.get("applies_to"):
                            val = meta["applies_to"]
                            applies_patterns = [str(x) for x in val] if isinstance(val, list) else [str(val)]
                except Exception:
                    pass

            for pat in applies_patterns:
                for target_p in normalized_paths:
                    if _match_applies_to(pat, target_p):
                        curr_score, curr_reasons = scored_map.get(p, (0.0, []))
                        reason = f"path:{target_p} (applies_to `{pat}`)"
                        if reason not in curr_reasons:
                            curr_reasons.append(reason)
                        # High base score for deterministic path match (e.g., 100.0)
                        scored_map[p] = (curr_score + 100.0, curr_reasons)
                        break

    # SIGNAL 2: Field-Weighted TF-IDF (Keywords from task)
    keywords = extract_keywords(task or "")
    if keywords:
        n_docs = len(snapshot)
        # Search title (H1), H2 subheadings, summary, and content (Defect 2 & Defect 4)
        doc_contents: dict[Path, tuple[str, str, str, str, dict[str, Any]]] = {}
        df_map: dict[str, int] = {kw: 0 for kw in keywords}

        for p in snapshot:
            try:
                c = p.read_text(encoding="utf-8")
                rel_str = str(p.relative_to(w_root))
                reg_entry = registry_by_path.get(rel_str)

                # Extract H1 title and summary
                if reg_entry and reg_entry.get("title") and reg_entry.get("summary"):
                    title = reg_entry["title"]
                    summary = reg_entry["summary"]
                else:
                    title, summary = extract_title_and_summary(c)

                meta, body = parse_frontmatter(c) if c.startswith("---\n") else ({}, c)
                body_clean = body or ""

                # Extract H2 subheadings
                h2_lines = [
                    line.removeprefix("## ").strip()
                    for line in body_clean.splitlines()
                    if line.strip().startswith("## ")
                ]
                h2_text = " ".join(h2_lines)

                doc_contents[p] = (title.lower(), h2_text.lower(), summary.lower(), body_clean.lower(), meta or {})
            except Exception:
                doc_contents[p] = ("", "", "", "", {})

        for kw in keywords:
            for p, (t, h2, s, b, _) in doc_contents.items():
                if _count_keyword_occurrences(kw, t) > 0 or _count_keyword_occurrences(kw, h2) > 0 or _count_keyword_occurrences(kw, s) > 0 or _count_keyword_occurrences(kw, b) > 0:
                    df_map[kw] += 1

        idf_map: dict[str, float] = {}
        for kw in keywords:
            df = df_map[kw]
            idf_map[kw] = math.log((n_docs + 1) / (df + 1)) + 1.0 if df > 0 else 0.0

        for p, (t, h2, s, b, meta) in doc_contents.items():
            text_score = 0.0
            hits: list[str] = []
            for kw in keywords:
                tf_title = _count_keyword_occurrences(kw, t)
                tf_h2 = _count_keyword_occurrences(kw, h2)
                tf_summary = _count_keyword_occurrences(kw, s)
                tf_body = _count_keyword_occurrences(kw, b)

                # Field weighting: title 3x, H2 2x, summary 2x, body 1x
                weighted_count = (tf_title * 3) + (tf_h2 * 2) + (tf_summary * 2) + tf_body
                if weighted_count > 0:
                    tf = 1.0 + math.log(weighted_count)
                    text_score += tf * idf_map[kw]
                    hits.append(kw)

            # Deprioritize superseded/deprecated articles
            status = str(meta.get("status", "")).lower()
            if status in ("superseded", "deprecated"):
                text_score *= 0.1

            if text_score > 0:
                curr_score, curr_reasons = scored_map.get(p, (0.0, []))
                for h in hits:
                    if h not in curr_reasons:
                        curr_reasons.append(h)
                scored_map[p] = (curr_score + text_score, curr_reasons)

    # Initial ranking before Signal 3 expansion
    candidates = [
        (score, p, reasons)
        for p, (score, reasons) in scored_map.items()
        if score > 0.0
    ]
    candidates.sort(
        key=lambda item: (-item[0], str(item[1].relative_to(w_root)))
    )

    # SIGNAL 3: 1-Hop ADR Reference Graph Expansion (Anti-Omission Guard)
    top_candidates = candidates[:top_n]
    expanded_adrs: list[Path] = []
    already_selected = {p for _, p, _ in top_candidates}

    for _, p, _ in top_candidates:
        rel_str = str(p.relative_to(w_root))
        entry = registry_by_path.get(rel_str)
        linked_targets: list[str] = []
        if entry:
            linked_targets.extend(entry.get("related", []))
            linked_targets.extend(entry.get("outgoing_links", []))
        else:
            try:
                c = p.read_text(encoding="utf-8")
                from brain79.core.navigation import extract_graph_metadata
                gm = extract_graph_metadata(c, rel_path=rel_str)
                linked_targets.extend(gm.get("related", []))
                linked_targets.extend(gm.get("outgoing_links", []))
            except Exception:
                pass

        for target in linked_targets:
            # Check if target is a decision article
            norm_target = str(target).strip().lstrip("/")
            if norm_target.startswith("decisions/") or "/decisions/" in norm_target:
                candidate_path: Path = (w_root / norm_target).resolve()
                if not candidate_path.exists():
                    # Might be relative to article parent
                    candidate_path = (p.parent / norm_target).resolve()
                if candidate_path.exists() and candidate_path in snapshot and candidate_path not in already_selected:
                    # Check that decision is active (not superseded/rejected)
                    try:
                        c_adr = candidate_path.read_text(encoding="utf-8")
                        meta_adr, _ = parse_frontmatter(c_adr)
                        adr_status = str((meta_adr or {}).get("status", "")).lower()
                        if adr_status in ("accepted", "stable", ""):
                            expanded_adrs.append(candidate_path)
                            already_selected.add(candidate_path)
                    except Exception:
                        expanded_adrs.append(candidate_path)
                        already_selected.add(candidate_path)

    # Defect 1: Preserve top_candidates AND append expanded ADRs without truncation
    final_results: list[tuple[float, Path, list[str]]] = list(top_candidates)
    for adr_p in expanded_adrs:
        final_results.append((50.0, adr_p, ["graph:1-hop ADR expansion"]))

    return final_results


def get_context(
    task: str,
    top_n: int = 3,
    paths: list[str] | None = None,
    wiki_root: Path | None = None,
) -> str:
    """
    Retrieve top relevant wiki articles for a task using 3-signal context ranking.

    Args:
        task: User task or search prompt.
        top_n: Number of top articles to return (defaults to 3 if <= 0).
        paths: Optional list of workspace file paths being inspected/modified.
        wiki_root: Optional custom wiki root path.

    Returns:
        Formatted markdown report string.
    """
    w_root = (wiki_root or get_wiki_root()).resolve()
    snapshot = get_wiki_snapshot(wiki_root=w_root)
    if not snapshot:
        return "No hay artículos válidos en la wiki para analizar."

    effective_top_n = top_n if top_n > 0 else 3
    ranked = rank_context_articles(task=task, paths=paths, top_n=effective_top_n, wiki_root=w_root)

    # Fallback if no scored articles found
    if not ranked:
        keywords = extract_keywords(task)
        if not keywords and not paths:
            index_path = (w_root / "INDEX.md").resolve()
            has_index = index_path in snapshot

            if has_index:
                remaining = [p for p in snapshot if p != index_path]
                remaining.sort(
                    key=lambda x: (
                        -_safe_mtime_ns(x),
                        str(x.relative_to(w_root)),
                    )
                )
                fallback_items = [index_path] + remaining[: effective_top_n - 1]
            else:
                sorted_snapshot = sorted(
                    snapshot,
                    key=lambda x: (
                        -_safe_mtime_ns(x),
                        str(x.relative_to(w_root)),
                    ),
                )
                fallback_items = sorted_snapshot[:effective_top_n]

            lines = [
                "# Context Retrieval Report",
                "⚠️ FALLBACK MODE (query sin keywords válidas)",
                f'Query original: "{task}"',
                "Keywords detectados: (ninguno)",
                "",
                "## Artículos recientes (Fallback de Supervivencia):",
            ]
            for idx, item in enumerate(fallback_items, 1):
                rel = item.relative_to(w_root)
                lines.append(f"{idx}. `{rel}` (Score: N/A)")
            return "\n".join(lines)

    top_articles = ranked
    lines = [
        "# Context Retrieval Report",
        "<!-- Ranking matemático ponderado vía motor 3-Signal (Path + TF-IDF + Graph) -->",
        f'Query original: "{task}"',
    ]
    if paths:
        lines.append(f"Paths: {', '.join(f'`{p}`' for p in paths)}")
    lines.extend([
        "",
        "## Artículos de máxima relevancia:",
    ])

    if not top_articles:
        lines.append(
            "No se encontraron artículos con relevancia suficiente (Score >= 1.0)."
        )
    else:
        for idx, (score, p, hits) in enumerate(top_articles, 1):
            rel = p.relative_to(w_root)
            hits_formatted = ", ".join(f"`{h}`" for h in hits)
            lines.append(
                f"{idx}. `{rel}` (Score: {score:.2f}) - Hits: {hits_formatted}"
            )

    return "\n".join(lines)
