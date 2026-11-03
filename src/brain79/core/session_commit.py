"""Atomic session commit protocol for Brain-79 (Phase 3).

Executes the entire end-of-session finalization workflow in a single all-or-nothing transaction:
1. Pre-flight validation (writes, edits, and handoff).
2. All-or-nothing rollback on validation failure (zero files hit disk).
3. Raw session ingestion (if session_summary provided).
4. Synchronous file writes and edits via unified virtual filesystem state.
5. Immutable handoff generation.
6. Unified navigation synchronization and inline health diagnostics.
"""

from pathlib import Path
from typing import Any

from brain79.config import get_wiki_root
from brain79.core.frontmatter import ValidationError
from brain79.core.handoff import validate_handoff_params, write_handoff
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

    # Guard: Reject completely empty session commits (Defect 6)
    if not writes_in and not edits_in and not handoff_in and not session_summary:
        raise ValueError("Cannot commit an empty session: specify at least one write, edit, handoff, or session_summary.")

    # =========================================================================
    # Step 1: Pre-flight validation (Virtual FS simulation)
    # =========================================================================
    validation_errors: list[str] = []

    # Virtual FS tracks relative path -> simulated content across writes and edits (Defect 4)
    # virtual_fs maps normalized rel_str -> content string
    virtual_fs: dict[str, str] = {}
    written_article_keys: list[str] = []
    edited_article_keys: list[str] = []

    # 1.1 Simulate writes in virtual_fs
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
            val_c = validate_article_content(
                rel_str, c, force_skip=force_validation_skip, wiki_root=w_root
            )
            virtual_fs[rel_str] = val_c
            if rel_str not in written_article_keys:
                written_article_keys.append(rel_str)
        except ValidationError as exc:
            validation_errors.append(f"[{p}]\n{exc.format_user_message()}")
        except Exception as exc:
            validation_errors.append(f"[{p}] {exc}")

    # 1.2 Simulate edits in virtual_fs
    for idx, edit_item in enumerate(edits_in):
        p = edit_item.get("path")
        edits_list = edit_item.get("edits")
        if not p or not edits_list:
            validation_errors.append(f"Edit #{idx + 1}: Must contain 'path' and non-empty 'edits' list.")
            continue

        try:
            target = _safe_resolve(p, wiki_root=w_root)
            rel_str = str(target.relative_to(w_root))

            # Base text: virtual_fs first (if created/modified by an earlier write/edit), else disk
            if rel_str in virtual_fs:
                current_text = virtual_fs[rel_str]
            elif target.exists() and target.is_file():
                current_text = target.read_text(encoding="utf-8")
            else:
                validation_errors.append(f"Edit #{idx + 1}: File not found '{p}'.")
                continue

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

            val_edited_content = validate_article_content(
                rel_str, current_text, force_skip=force_validation_skip, wiki_root=w_root
            )
            virtual_fs[rel_str] = val_edited_content
            if rel_str not in written_article_keys and rel_str not in edited_article_keys:
                edited_article_keys.append(rel_str)
        except ValidationError as exc:
            validation_errors.append(f"[{p}]\n{exc.format_user_message()}")
        except Exception as exc:
            validation_errors.append(f"[{p}] {exc}")

    # 1.3 Validate handoff completely upfront (Defect 1 & Defect 5)
    normalized_handoff_params: dict[str, Any] | None = None
    if handoff_in:
        try:
            normalized_handoff_params = validate_handoff_params(
                session_type=handoff_in.get("session_type", ""),
                previous_handoff_ref=handoff_in.get("previous_handoff_ref", "latest"),
                summary=handoff_in.get("summary", ""),
                completed_work=handoff_in.get("completed_work"),
                pending_work=handoff_in.get("pending_work"),
                knowledge_pending_promotion=handoff_in.get("knowledge_pending_promotion"),
                resources=handoff_in.get("resources"),
                gotchas=handoff_in.get("gotchas"),
                boot_instruction=handoff_in.get("boot_instruction", ""),
                wiki_deviation_justification=handoff_in.get("wiki_deviation_justification", ""),
                wiki_root=w_root,
            )
        except (ValueError, FileNotFoundError):
            # Raise ValueError / FileNotFoundError directly to preserve handoff contract
            raise

    if validation_errors:
        raise ValidationError(
            rule="session_commit_validation_failed",
            path="session_commit",
            message=f"Session commit validation failed for {len(validation_errors)} error(s):\n\n"
            + "\n\n".join(validation_errors),
            actionable="Resolve all validation errors before committing session.",
        )

    # =========================================================================
    # Step 2: Execution Pass (all pre-flight checks passed, mutate disk)
    # =========================================================================
    raw_path: str | None = None
    if session_summary:
        raw_msg = save_raw_session(session_summary, instructions=instructions or "", wiki_root=w_root)
        if "_raw/sessions/" in raw_msg:
            raw_path = "_raw/sessions/" + raw_msg.split("_raw/sessions/")[-1].strip()

    # Write each touched article once from virtual_fs
    for rel_str, content in virtual_fs.items():
        write_article(
            rel_str,
            content,
            timeout=timeout,
            force_validation_skip=force_validation_skip,
            _skip_nav_regen=True,
            wiki_root=w_root,
        )

    handoff_path: str | None = None
    if normalized_handoff_params:
        handoff_msg = write_handoff(
            session_type=normalized_handoff_params["session_type"],
            previous_handoff_ref=normalized_handoff_params["previous_handoff_ref"],
            summary=normalized_handoff_params["summary"],
            completed_work=normalized_handoff_params["completed_work"],
            pending_work=normalized_handoff_params["pending_work"],
            knowledge_pending_promotion=normalized_handoff_params["knowledge_pending_promotion"],
            resources=normalized_handoff_params["resources"],
            gotchas=normalized_handoff_params["gotchas"],
            boot_instruction=normalized_handoff_params["boot_instruction"],
            wiki_deviation_justification=normalized_handoff_params["wiki_deviation_justification"],
            wiki_root=w_root,
        )
        if "handoffs/" in handoff_msg:
            handoff_path = "handoffs/" + handoff_msg.split("handoffs/")[-1].strip()

    # Regenerate index navigation ONLY if indexable articles were touched (Defect 6)
    has_indexable_changes = any(
        not p.startswith("_raw/") and not p.startswith("handoffs/") and p not in ("SCHEMA.md", "INDEX.md")
        for p in virtual_fs
    )
    if has_indexable_changes:
        try:
            regenerate_index_navigation(w_root)
        except Exception:
            pass

    # Collect health diagnostics
    all_warnings: list[str] = []
    for rel_str in virtual_fs:
        try:
            content = (w_root / rel_str).read_text(encoding="utf-8")
            all_warnings.extend(check_file_health(w_root, rel_str, content))
        except Exception:
            pass

    return {
        "success": True,
        "session_raw_path": raw_path,
        "written_articles": written_article_keys,
        "edited_articles": edited_article_keys,
        "handoff_path": handoff_path,
        "health_status": "warnings" if all_warnings else "ok",
        "warnings": all_warnings,
    }
