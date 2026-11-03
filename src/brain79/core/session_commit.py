"""Atomic session commit protocol for Brain-79 (Phase 3).

Executes the entire end-of-session finalization workflow in a single all-or-nothing transaction:
1. Pre-flight validation (writes, edits, and handoff).
2. All-or-nothing rollback on validation failure.
3. Raw session ingestion (if session_summary provided).
4. Synchronous file writes and edits.
5. Immutable handoff generation.
6. Unified navigation synchronization and inline health diagnostics.
"""

from pathlib import Path
from typing import Any

from brain79.config import get_wiki_root
from brain79.core.frontmatter import ValidationError
from brain79.core.handoff import write_handoff
from brain79.core.navigation import regenerate_index_navigation
from brain79.core.validation import validate_article_content
from brain79.core.wiki import (
    _safe_resolve,
    check_file_health,
    save_raw_session,
    write_article,
)


def commit_session(
    payload: dict[str, Any],
    wiki_root: Path | None = None,
    timeout: float = 5.0,
    force_validation_skip: bool = False,
) -> dict[str, Any]:
    """
    Execute an atomic session commit transaction.

    Args:
        payload: Dict containing:
            - session_summary: Optional string with high-level session summary for _raw/sessions/.
            - instructions: Optional string with user instructions for _raw/sessions/.
            - writes: Optional list of dicts [{"path": str, "content": str}].
            - edits: Optional list of dicts [{"path": str, "edits": [{"old_text": str, "new_text": str}]}].
            - handoff: Optional dict with arguments for write_handoff(...).
        wiki_root: Optional Path override for wiki root.
        timeout: Timeout in seconds for file locks.
        force_validation_skip: Whether to skip frontmatter schema validation.

    Returns:
        Dict receipt:
            - success: True
            - session_raw_path: str | None
            - written_articles: list[str]
            - edited_articles: list[str]
            - handoff_path: str | None
            - health_status: "ok" | "warnings"
            - warnings: list[str]
    """
    w_root = (wiki_root or get_wiki_root()).resolve()

    writes_in = payload.get("writes") or []
    edits_in = payload.get("edits") or []
    handoff_in = payload.get("handoff")
    session_summary = payload.get("session_summary")
    instructions = payload.get("instructions")

    # =========================================================================
    # Step 1: Pre-flight validation (in-memory simulations)
    # =========================================================================
    validation_errors: list[str] = []
    validated_writes: list[tuple[str, str]] = []

    # 1.1 Validate writes upfront
    for idx, write_item in enumerate(writes_in):
        p = write_item.get("path")
        c = write_item.get("content")
        if not p or c is None:
            validation_errors.append(f"Write #{idx + 1}: Must contain 'path' and 'content'.")
            continue

        try:
            target = _safe_resolve(p, wiki_root=w_root)
            if target.suffix != ".md":
                validation_errors.append(f"Write #{idx + 1}: Path must end with .md, got '{p}'.")
                continue
            rel_str = str(target.relative_to(w_root))
            val_c = validate_article_content(rel_str, c, force_skip=force_validation_skip)
            validated_writes.append((p, val_c))
        except ValidationError as exc:
            validation_errors.append(f"[{p}]\n{exc.format_user_message()}")
        except Exception as exc:
            validation_errors.append(f"[{p}] {exc}")

    # 1.2 Validate edits upfront (simulate text replacement in memory)
    simulated_edits: list[tuple[str, str]] = []
    for idx, edit_item in enumerate(edits_in):
        p = edit_item.get("path")
        edits_list = edit_item.get("edits")
        if not p or not edits_list:
            validation_errors.append(f"Edit #{idx + 1}: Must contain 'path' and non-empty 'edits' list.")
            continue

        try:
            target = _safe_resolve(p, wiki_root=w_root)
            if not target.exists() or not target.is_file():
                validation_errors.append(f"Edit #{idx + 1}: File not found '{p}'.")
                continue

            current_text = target.read_text(encoding="utf-8")
            # Apply edits in sequence in memory
            for edit_idx, sub_edit in enumerate(edits_list):
                old_text = sub_edit.get("old_text")
                new_text = sub_edit.get("new_text")
                if old_text is None or new_text is None:
                    validation_errors.append(f"Edit on '{p}' sub-edit #{edit_idx + 1}: Must contain 'old_text' and 'new_text'.")
                    continue
                if not old_text:
                    validation_errors.append(f"Edit on '{p}' sub-edit #{edit_idx + 1}: 'old_text' cannot be empty.")
                    continue

                count = current_text.count(old_text)
                if count == 0:
                    snippet = old_text[:60] + "..." if len(old_text) > 60 else old_text
                    validation_errors.append(f"Edit on '{p}' sub-edit #{edit_idx + 1}: 'old_text' not found: {snippet!r}")
                    continue
                if count > 1:
                    snippet = old_text[:60] + "..." if len(old_text) > 60 else old_text
                    validation_errors.append(f"Edit on '{p}' sub-edit #{edit_idx + 1}: ambiguous: matches {count} times: {snippet!r}")
                    continue

                current_text = current_text.replace(old_text, new_text, 1)

            rel_str = str(target.relative_to(w_root))
            val_edited_content = validate_article_content(rel_str, current_text, force_skip=force_validation_skip)
            simulated_edits.append((p, val_edited_content))
        except ValidationError as exc:
            validation_errors.append(f"[{p}]\n{exc.format_user_message()}")
        except Exception as exc:
            validation_errors.append(f"[{p}] {exc}")

    # 1.3 Validate handoff upfront
    if handoff_in:
        from brain79.core.handoff import get_valid_session_types

        s_type = (handoff_in.get("session_type") or "").strip().lower()
        valid_types = get_valid_session_types()
        if not s_type:
            validation_errors.append("Handoff: 'session_type' is required.")
        elif s_type not in valid_types:
            # Raise ValueError directly to match handoff contract
            raise ValueError(f"Invalid session_type '{s_type}'. Must be one of: {sorted(valid_types)}")

        h_summary = (handoff_in.get("summary") or "").strip()
        if not h_summary:
            validation_errors.append("Handoff: 'summary' cannot be empty.")

    if validation_errors:
        raise ValidationError(
            rule="session_commit_validation_failed",
            path="session_commit",
            message=f"Session commit validation failed for {len(validation_errors)} error(s):\n\n"
            + "\n\n".join(validation_errors),
            actionable="Resolve all validation errors before committing session.",
        )

    # =========================================================================
    # Step 2: Execution Pass (all pre-flight checks passed)
    # =========================================================================
    raw_path: str | None = None
    if session_summary:
        raw_msg = save_raw_session(session_summary, instructions=instructions or "")
        # Extract relative path from "Saved raw session to .brain-79/_raw/sessions/..."
        if "_raw/sessions/" in raw_msg:
            raw_path = "_raw/sessions/" + raw_msg.split("_raw/sessions/")[-1].strip()

    written_paths: list[str] = []
    for p, val_c in validated_writes:
        write_article(
            p,
            val_c,
            timeout=timeout,
            force_validation_skip=force_validation_skip,
            _skip_nav_regen=True,
        )
        written_paths.append(p)

    edited_paths: list[str] = []
    for p, val_edited in simulated_edits:
        write_article(
            p,
            val_edited,
            timeout=timeout,
            force_validation_skip=force_validation_skip,
            _skip_nav_regen=True,
        )
        edited_paths.append(p)

    handoff_path: str | None = None
    if handoff_in:
        handoff_msg = write_handoff(
            session_type=handoff_in["session_type"],
            previous_handoff_ref=handoff_in.get("previous_handoff_ref", "latest"),
            summary=handoff_in["summary"],
            completed_work=handoff_in.get("completed_work"),
            pending_work=handoff_in.get("pending_work"),
            knowledge_pending_promotion=handoff_in.get("knowledge_pending_promotion"),
            resources=handoff_in.get("resources"),
            gotchas=handoff_in.get("gotchas"),
            boot_instruction=handoff_in.get("boot_instruction", ""),
            wiki_deviation_justification=handoff_in.get("wiki_deviation_justification", ""),
        )
        if "handoffs/" in handoff_msg:
            handoff_path = "handoffs/" + handoff_msg.split("handoffs/")[-1].strip()

    # Regenerate index navigation once for all touched articles
    try:
        regenerate_index_navigation(w_root)
    except Exception:
        pass

    # Collect health diagnostics
    all_warnings: list[str] = []
    for p in written_paths:
        try:
            content = (w_root / p).read_text(encoding="utf-8")
            all_warnings.extend(check_file_health(w_root, p, content))
        except Exception:
            pass

    for p in edited_paths:
        try:
            content = (w_root / p).read_text(encoding="utf-8")
            all_warnings.extend(check_file_health(w_root, p, content))
        except Exception:
            pass

    return {
        "success": True,
        "session_raw_path": raw_path,
        "written_articles": written_paths,
        "edited_articles": edited_paths,
        "handoff_path": handoff_path,
        "health_status": "warnings" if all_warnings else "ok",
        "warnings": all_warnings,
    }
