"""
1-Call Cold Start Orient Orchestrator (Phase 2).

Combines:
1. Routing Table (INDEX.md).
2. Active Handoff State (latest handoff summary, pending work, boot instruction, and promo warnings).
3. Governing Knowledge Articles (inlining content of top ranked articles via 3-signal context ranker).
"""

from pathlib import Path
import subprocess

from brain79.config import get_project_root, get_wiki_root
from brain79.core.context import rank_context_articles
from brain79.core.frontmatter import parse_frontmatter
from brain79.core.handoff import (
    HANDOFF_ESCALATION_AGE_DAYS,
    HANDOFF_ESCALATION_COMMITS,
    _resolve_handoff_path,
    read_handoff,
)
from brain79.core.handoff_freshness import compute_handoff_freshness
from brain79.core.locks import normalize_posix_input
from brain79.core.navigation import extract_title_and_summary
from brain79.core.wiki import get_index, read_article

MAX_ORIENT_INLINE_CHARS = 64_000


def orient(
    task: str | None = None,
    paths: list[str] | None = None,
    max_articles: int = 4,
    wiki_root: Path | None = None,
) -> str:
    """
    Execute 1-call cold start orientation.

    Args:
        task: Optional high-level goal or task description.
        paths: Optional list of workspace file paths the agent intends to touch.
        max_articles: Maximum number of governing articles to inline (default: 4).
        wiki_root: Optional custom wiki root path.

    Returns:
        Structured markdown combining navigation, handoff state, and governing articles.
    """
    w_root = (wiki_root or get_wiki_root()).resolve()
    p_root = (w_root.parent if w_root.parent.exists() else get_project_root()).resolve()

    sections: list[str] = [
        "# Brain-79 — Session Cold Start Orientation",
        "",
        "## 🗺️ Project Index (Routing Table)",
    ]

    # 1. INDEX.md / Routing Table
    try:
        index_content = get_index(wiki_root=w_root)
        sections.append(index_content.strip())
    except Exception as exc:
        sections.append(f"*Could not read INDEX.md: {exc}*")

    # 2. Active Schema Summary
    sections.extend(["", "---", "", "## 📐 Active Schema Summary"])
    try:
        from brain79.core.frontmatter import load_active_schema

        active_schema = load_active_schema(w_root)
        sections.append(f"- **Profile:** `{active_schema.profile}`")
        sections.append("- **Managed Directories:**")
        for loc, tname in sorted(active_schema.location_to_type.items()):
            tcfg = active_schema.types.get(tname, {})
            req_fields = ", ".join(f"`{f}`" for f in tcfg.get("required", []))
            sections.append(f"  - `{loc}/` → type: `{tname}` (required: {req_fields})")
    except Exception as exc:
        sections.append(f"*Could not load active schema: {exc}*")

    sections.extend(["", "---", ""])

    # Operation-scoped WorkspaceIndex (built once per orient invocation)
    from brain79.core.drift import WorkspaceIndex, detect_all_drift
    ws = WorkspaceIndex.build(p_root, w_root)

    # 3. Latest Handoff
    try:
        target_handoff = _resolve_handoff_path("latest", wiki_root=w_root)
        freshness = compute_handoff_freshness(target_handoff, wiki_root=w_root, workspace_index=ws)
        handoff_content, has_promotion_pending = read_handoff(
            "latest",
            wiki_root=w_root,
            for_orient=True,
            freshness=freshness,
        )
        if has_promotion_pending:
            sections.append(
                "> ⚠️ **Knowledge pending promotion**: the prior session noted critical insights "
                "pending distillation into the permanent wiki. Review and promote when appropriate.\n"
            )
        sections.append(handoff_content.strip())

        # Escalation of aging pending work (R5)
        raw_handoff_text = target_handoff.read_text(encoding="utf-8")
        has_pending_work = (
            "## Pending work" in raw_handoff_text
            or "## Trabajo pendiente" in raw_handoff_text
        )
        age_exceeded = freshness.age_seconds >= 86400 * HANDOFF_ESCALATION_AGE_DAYS
        commits_exceeded = (
            freshness.commits_since is not None
            and freshness.commits_since >= HANDOFF_ESCALATION_COMMITS
        )
        if has_pending_work and (age_exceeded or (commits_exceeded and freshness.state != "fresh")):
            sections.append(
                "\n> ⚠️ **Pending work in this handoff is aging**: promote long-lived items "
                "to the roadmap or backlog (architecture/ or topics/), or run `brain79 handoff-purge`."
            )
    except FileNotFoundError:
        sections.extend([
            "## ⏱️ Active handoff state",
            "No prior handoff found (`handoffs/` is empty). Ready for first session.",
        ])
    except Exception as exc:
        sections.extend([
            "## ⏱️ Active handoff state",
            f"*Could not load latest handoff: {exc}*",
        ])

    # 3. Governing Knowledge Articles (3-Signal Ranker)
    p_root = (w_root.parent if w_root.parent.exists() else get_project_root()).resolve()

    # Unconditional Git working-tree path discovery (even when task=None, paths=None)
    discovered_paths: list[str] = []
    try:
        res = subprocess.run(
            ["git", "-c", "core.quotepath=false", "status", "--porcelain=v1", "-z"],
            cwd=str(p_root),
            capture_output=True,
            check=False,
            timeout=2.0,
        )
        if res.returncode == 0 and res.stdout:
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
                    if norm_p and norm_p not in discovered_paths and not norm_p.startswith(".brain-79/"):
                        discovered_paths.append(norm_p)
                    if "R" in xy or "C" in xy:
                        if idx < len(raw_entries) and raw_entries[idx]:
                            orig_bytes = raw_entries[idx]
                            idx += 1
                            orig_str = orig_bytes.decode("utf-8", errors="replace")
                            norm_orig = normalize_posix_input(orig_str).lstrip("/")
                            if norm_orig and norm_orig not in discovered_paths and not norm_orig.startswith(".brain-79/"):
                                discovered_paths.append(norm_orig)
                    if len(discovered_paths) >= 50:
                        break
    except Exception:
        discovered_paths = []

    effective_paths: list[str] = []
    if paths:
        for p in paths:
            clean_p = normalize_posix_input(p).lstrip("/")
            if clean_p and clean_p not in effective_paths:
                effective_paths.append(clean_p)
    for dp in discovered_paths:
        if dp not in effective_paths:
            effective_paths.append(dp)

    # Unconditional Drift Detection across entire wiki (Pilar 6.1)
    all_drifts = detect_all_drift(wiki_root=w_root, project_root=p_root, workspace_index=ws)

    seen_drifts: set[tuple[str, str, str]] = set()
    drift_alerts: list[str] = []
    for d in all_drifts:
        art_path = d.get("article_path", "")
        ws_file = d.get("workspace_file", d.get("target_file", ""))
        kind = d.get("drift_kind", "modified").upper()
        key = (art_path, ws_file, kind)
        if key not in seen_drifts:
            seen_drifts.add(key)
            tag = "[TRANSITIVE]" if kind == "TRANSITIVE" else "[DIRECT]"
            msg = d.get("message", f"governed file {ws_file} modified")
            drift_alerts.append(
                f"> ⚠️ **Documentation Drift Suspected** ({tag}): Article '{art_path}' governs '{ws_file}' "
                f"({msg}). Verify accuracy before proceeding."
            )

    if drift_alerts:
        sections.extend([
            "",
            "---",
            "",
            "## ⚠️ Documentation Drift Alerts",
            *drift_alerts,
            "",
            "> **Action**: Update drifted articles via `brain79_edit`/`brain79_write`, or pass eligible "
            "internal leaf code refactors in `verified_articles=[{\"path\": \"...\", \"reason\": \"...\"}]` "
            "during `brain79_session_commit`.",
        ])

    if task or effective_paths:
        sections.extend(["", "---", "", "## 📖 Governing Knowledge Articles"])
        effective_max = max(1, max_articles) if max_articles > 0 else 4
        ranked = rank_context_articles(
            task=task,
            paths=effective_paths if effective_paths else None,
            top_n=effective_max,
            wiki_root=w_root,
        )

        if not ranked:
            sections.append("No specific governing articles matched the task or paths.")
        else:
            inlined_count = 0
            manifest_articles: list[tuple[str, str, str, str]] = []
            current_chars = sum(len(s) for s in sections)

            for score, article_p, reasons in ranked:
                try:
                    rel_p = article_p.relative_to(w_root).as_posix()
                    if rel_p == "INDEX.md":
                        continue
                    content = read_article(rel_p, wiki_root=w_root)
                    reasons_str = ", ".join(reasons)
                    article_header = f"### === Article: {rel_p} ===\n*Relevance Score: {score:.1f} | Match Signals: {reasons_str}*\n\n"
                    article_block = article_header + content.strip() + "\n\n"

                    if manifest_articles or (current_chars + len(article_block) > MAX_ORIENT_INLINE_CHARS):
                        meta, body = parse_frontmatter(content)
                        summary = str(meta.get("summary") or "").strip()
                        if not summary:
                            _, summary = extract_title_and_summary(content)
                        applies = meta.get("applies_to", [])
                        applies_list = [str(x) for x in applies] if isinstance(applies, list) else ([str(applies)] if applies else [])
                        applies_str = ", ".join(f"`{a}`" for a in applies_list) if applies_list else "*(none)*"

                        h2_headers = [
                            line.removeprefix("## ").strip()
                            for line in body.splitlines()
                            if line.strip().startswith("## ")
                        ]
                        h2_str = ", ".join(h2_headers) if h2_headers else "*(none)*"
                        manifest_articles.append((rel_p, summary, applies_str, h2_str))
                    else:
                        sections.append(f"### === Article: {rel_p} ===")
                        sections.append(f"*Relevance Score: {score:.1f} | Match Signals: {reasons_str}*")
                        sections.append("")
                        sections.append(content.strip())
                        sections.append("")
                        current_chars += len(article_block)
                        inlined_count += 1
                except Exception:
                    continue

            if inlined_count == 0 and not manifest_articles:
                sections.append("No governing articles inlined.")

            if manifest_articles:
                sections.extend([
                    "---",
                    "",
                    "## 🚨 Mandatory Reading Manifest (Must Read Before Editing)",
                    "",
                    "The governing context exceeds the 64,000-character inline budget. The following governing articles "
                    "must be read using `brain79_read_batch(requests=[...])` before modifying code or documentation:",
                    "",
                ])
                for rel_p, summary, applies_str, h2_str in manifest_articles:
                    sections.append(f"- **`{rel_p}`**: {summary}")
                    sections.append(f"  - **Governs (`applies_to`)**: {applies_str}")
                    sections.append(f"  - **Key Sections**: {h2_str}")

    return "\n".join(sections)


orient_session = orient

