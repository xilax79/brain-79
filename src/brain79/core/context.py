from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unicodedata

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


def get_wiki_snapshot() -> list[Path]:
    """
    Build in-memory snapshot of valid wiki articles.

    Filtering rules:
    - Ends with .md
    - File size: 0 < size <= 1MB
    - Excludes files inside _raw/ or handoffs/
    - Returns absolute resolved paths
    """
    wiki_root = get_wiki_root().resolve()
    if not wiki_root.exists():
        return []

    snapshot: list[Path] = []
    for p in wiki_root.rglob("*.md"):
        try:
            abs_path = p.resolve()
            rel = abs_path.relative_to(wiki_root)
            if any(part in _EXCLUDED_DIRS for part in rel.parts):
                continue
            if not abs_path.is_file():
                continue
            stat = abs_path.stat()
            if 0 < stat.st_size <= 1_048_576:
                snapshot.append(abs_path)
        except OSError:
            continue

    snapshot.sort(key=lambda x: str(x.relative_to(wiki_root)))
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


def get_context(task: str, top_n: int = 3) -> str:
    """
    Retrieve top relevant wiki articles for a task using sublinear TF-IDF ranking.

    Args:
        task: User task or search prompt.
        top_n: Number of top articles to return (defaults to 3 if <= 0).

    Returns:
        Formatted markdown report string.
    """
    snapshot = get_wiki_snapshot()
    if not snapshot:
        return "No hay artículos válidos en la wiki para analizar."

    effective_top_n = top_n if top_n > 0 else 3
    keywords = extract_keywords(task)
    wiki_root = get_wiki_root().resolve()

    # Short-circuit: Fallback mode if no valid keywords extracted
    if not keywords:
        index_path = (wiki_root / "INDEX.md").resolve()
        has_index = index_path in snapshot

        if has_index:
            remaining = [p for p in snapshot if p != index_path]
            remaining.sort(
                key=lambda x: (
                    -_safe_mtime_ns(x),
                    str(x.relative_to(wiki_root)),
                )
            )
            fallback_items = [index_path] + remaining[: effective_top_n - 1]
        else:
            sorted_snapshot = sorted(
                snapshot,
                key=lambda x: (
                    -_safe_mtime_ns(x),
                    str(x.relative_to(wiki_root)),
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
            rel = item.relative_to(wiki_root)
            lines.append(f"{idx}. `{rel}` (Score: N/A)")
        return "\n".join(lines)

    # Concurrency and FD leak protection
    keyword_matches: dict[str, dict[Path, int]] = {}
    tmp_path: Path | None = None
    fd: int | None = None

    try:
        fd, tmp_file = tempfile.mkstemp(suffix=".txt")
        tmp_path = Path(tmp_file)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            fd = None  # Transferred FD ownership to open file context manager
            f.write("\n".join(str(p.resolve()) for p in snapshot))

        max_workers = min(8, len(keywords))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(_search_keyword, kw, tmp_path, snapshot): kw
                for kw in keywords
            }
            for future in as_completed(futures):
                kw = futures[future]
                try:
                    keyword_matches[kw] = future.result()
                except Exception:
                    keyword_matches[kw] = {}
    finally:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
        if tmp_path and tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass

    # Smoothed TF-IDF Calculation
    n_docs = len(snapshot)
    idf_map: dict[str, float] = {}
    for kw in keywords:
        matches_dict = keyword_matches.get(kw, {})
        df = sum(1 for p in snapshot if matches_dict.get(p, 0) > 0)
        if df > 0:
            idf_map[kw] = math.log((n_docs + 1) / (df + 1)) + 1.0
        else:
            idf_map[kw] = 0.0

    scored_articles: list[tuple[float, Path, list[str]]] = []
    for p in snapshot:
        doc_score = 0.0
        matched_kws: list[str] = []
        for kw in keywords:
            count = keyword_matches.get(kw, {}).get(p, 0)
            if count > 0:
                # Sublinear term frequency damping: 1 + log(count)
                tf = 1.0 + math.log(count)
                doc_score += tf * idf_map[kw]
                matched_kws.append(kw)
        if doc_score >= 1.0:
            scored_articles.append((doc_score, p, matched_kws))

    # Tie-breaking: (-score, relative_path)
    scored_articles.sort(
        key=lambda item: (-item[0], str(item[1].relative_to(wiki_root)))
    )

    top_articles = scored_articles[:effective_top_n]

    kw_formatted = ", ".join(f"`{kw}`" for kw in keywords)
    lines = [
        "# Context Retrieval Report",
        "<!-- Ranking matemático ponderado vía motor TF-IDF -->",
        f'Query original: "{task}"',
        f"Keywords detectados: {kw_formatted}",
        "",
        "## Artículos de máxima relevancia:",
    ]

    if not top_articles:
        lines.append(
            "No se encontraron artículos con relevancia suficiente (Score >= 1.0)."
        )
    else:
        for idx, (score, p, hits) in enumerate(top_articles, 1):
            rel = p.relative_to(wiki_root)
            hits_formatted = ", ".join(f"`{h}`" for h in hits)
            lines.append(
                f"{idx}. `{rel}` (Score: {score:.2f}) - Hits: {hits_formatted}"
            )

    return "\n".join(lines)
