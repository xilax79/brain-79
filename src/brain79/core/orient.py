"""
1-Call Cold Start Orient Orchestrator (Phase 2).

Combines:
1. Routing Table (INDEX.md).
2. Active Handoff State (latest handoff summary, pending work, boot instruction, and promo warnings).
3. Governing Knowledge Articles (inlining content of top ranked articles via 3-signal context ranker).
"""

from pathlib import Path

from brain79.config import get_wiki_root
from brain79.core.context import rank_context_articles
from brain79.core.handoff import read_handoff
from brain79.core.wiki import get_index, read_article


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

    sections.extend(["", "---", "", "## ⏱️ Active Handoff State"])

    # 2. Latest Handoff
    try:
        handoff_content, has_promotion_pending = read_handoff("latest", wiki_root=w_root)
        if has_promotion_pending:
            sections.append(
                "> ⚠️ **Knowledge Pending Promotion**: The prior session noted critical insights "
                "pending distillation into the permanent wiki. Review and promote when appropriate."
            )
            sections.append("")
        sections.append(handoff_content.strip())
    except FileNotFoundError:
        sections.append(
            "No prior handoff found (`handoffs/` is empty). Ready for first session."
        )
    except Exception as exc:
        sections.append(f"*Could not load latest handoff: {exc}*")

    # 3. Governing Knowledge Articles (3-Signal Ranker)
    if task or paths:
        sections.extend(["", "---", "", "## 📖 Governing Knowledge Articles"])
        effective_max = max(1, max_articles) if max_articles > 0 else 4
        ranked = rank_context_articles(
            task=task,
            paths=paths,
            top_n=effective_max,
            wiki_root=w_root,
        )

        if not ranked:
            sections.append("No specific governing articles matched the task or paths.")
        else:
            # Check documentation drift for inlined governing articles
            from brain79.core.drift import check_article_drift

            seen_drifts: set[tuple[str, str]] = set()
            for _, article_p, _ in ranked:
                try:
                    drifts = check_article_drift(article_p, wiki_root=w_root)
                    for d in drifts:
                        key = (d["article_path"], d["workspace_file"])
                        if key not in seen_drifts:
                            seen_drifts.add(key)
                            sections.append(
                                f"> ⚠️ **Documentation Drift Suspected**: Article '{d['article_path']}' "
                                f"governs '{d['workspace_file']}' (modified {d['file_date']}), but article was "
                                f"last updated {d['article_date']}. Verify accuracy before proceeding."
                            )
                except Exception:
                    pass

            if seen_drifts:
                sections.append("")

            inlined_count = 0
            # Inline top candidates AND expanded 1-hop ADRs without truncation
            for score, article_p, reasons in ranked:
                try:
                    rel_p = str(article_p.relative_to(w_root))
                    if rel_p == "INDEX.md":
                        continue
                    content = read_article(rel_p, wiki_root=w_root)
                    reasons_str = ", ".join(reasons)
                    sections.append(f"### === Article: {rel_p} ===")
                    sections.append(f"*Relevance Score: {score:.1f} | Match Signals: {reasons_str}*")
                    sections.append("")
                    sections.append(content.strip())
                    sections.append("")
                    inlined_count += 1
                except Exception:
                    continue

            if inlined_count == 0:
                sections.append("No governing articles inlined.")

    return "\n".join(sections)
