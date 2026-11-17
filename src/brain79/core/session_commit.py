"""Atomic session commit protocol and multi-phase pre-flight transaction pipeline.

Executes the entire end-of-session finalization workflow in a 4-phase transaction:
1. Pass 1: In-memory syntax/schema validation, verified_articles format check, and staging in virtual_fs.
2. Pass 2: Transaction lock (_transaction.lock), target validation (2a), anti-sprawl check (2a),
   digest stamping (2b), bottom-up verified_articles evaluation (Guards A, B, C) (2c),
   and Hard Session Ripple Gate (2d, unresolved_session_ripple).
3. Pass 3: Atomic disk persistence of articles, .drift_manifest.json, and INDEX.md navigation.
4. Pass 4: Post-persistence write_handoff() ensuring immediate 'fresh' handoff state.
"""

import json
from pathlib import Path
import subprocess
from typing import Any

from brain79.config import get_project_root, get_wiki_root
from brain79.core.drift import (
    WorkspaceIndex,
    check_article_drift,
    compute_applies_to_manifest,
    detect_all_drift,
    has_public_python_api_changes,
    load_drift_manifest,
    match_applies_to_pattern,
    save_drift_manifest,
)
from brain79.core.frontmatter import (
    INACTIVE_STATUSES,
    PRE_IMPLEMENTATION_STATUSES,
    ValidationError,
    dump_frontmatter,
    parse_frontmatter,
)
from brain79.core.handoff import validate_handoff_params, write_handoff
from brain79.core.locks import acquire_wiki_lock, normalize_posix_input, normalize_wiki_rel_path
from brain79.core.navigation import regenerate_index_navigation
from brain79.core.validation import check_anti_sprawl_overlap, validate_article_content
from brain79.core.wiki import (
    _safe_resolve,
    check_file_health,
    save_raw_session,
    write_article,
)


def commit_session(
    payload: dict[str, Any] | None = None,
    wiki_root: Path | None = None,
    timeout: float = 10.0,
    force_validation_skip: bool = False,
    writes: list[dict[str, Any]] | None = None,
    edits: list[dict[str, Any]] | None = None,
    handoff: dict[str, Any] | None = None,
    session_summary: str | None = None,
    instructions: str | None = None,
    verified_articles: list[dict[str, str]] | None = None,
    allow_partial_ripple: bool = False,
) -> dict[str, Any]:
    """Execute an atomic session commit transaction."""
    w_root = (wiki_root or get_wiki_root()).resolve()
    p_root = (w_root.parent or get_project_root()).resolve()

    if payload is None:
        payload = {}
    if writes is not None and "writes" not in payload:
        payload["writes"] = writes
    if edits is not None and "edits" not in payload:
        payload["edits"] = edits
    if handoff is not None and "handoff" not in payload:
        payload["handoff"] = handoff
    if session_summary is not None and "session_summary" not in payload:
        payload["session_summary"] = session_summary
    if instructions is not None and "instructions" not in payload:
        payload["instructions"] = instructions
    if verified_articles is not None and "verified_articles" not in payload:
        payload["verified_articles"] = verified_articles
    if "allow_partial_ripple" not in payload and allow_partial_ripple:
        payload["allow_partial_ripple"] = allow_partial_ripple

    writes_in = payload.get("writes") or []
    edits_in = payload.get("edits") or []
    handoff_in = payload.get("handoff")
    session_summary = payload.get("session_summary")
    instructions = payload.get("instructions")
    verified_articles_in = payload.get("verified_articles") or []
    allow_partial_ripple_in = bool(payload.get("allow_partial_ripple", False))

    # Reject completely empty session commits
    if not writes_in and not edits_in and not handoff_in and not session_summary and not verified_articles_in:
        raise ValueError(
            "Cannot commit an empty session: specify at least one write, edit, handoff, session_summary, or verified_article."
        )

    # =========================================================================
    # Pass 1: In-memory syntax/schema validation & staging in virtual_fs
    # =========================================================================
    validation_errors: list[str] = []
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
            rel_str = target.relative_to(w_root).as_posix()
            val_c = validate_article_content(
                rel_str,
                c,
                force_skip=force_validation_skip,
                check_workspace_targets=False,
                wiki_root=w_root,
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
            rel_str = target.relative_to(w_root).as_posix()

            if rel_str in virtual_fs:
                current_text = virtual_fs[rel_str]
            elif target.exists() and target.is_file():
                current_text = target.read_text(encoding="utf-8").replace("\r\n", "\n")
            else:
                validation_errors.append(f"Edit #{idx + 1}: File not found '{p}'.")
                continue

            for edit_idx, sub_edit in enumerate(edits_list):
                old_text = sub_edit.get("old_text") if sub_edit.get("old_text") is not None else sub_edit.get("oldText")
                new_text = sub_edit.get("new_text") if sub_edit.get("new_text") is not None else sub_edit.get("newText")
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
                rel_str,
                current_text,
                force_skip=force_validation_skip,
                check_workspace_targets=False,
                wiki_root=w_root,
            )
            virtual_fs[rel_str] = val_edited_content
            if rel_str not in written_article_keys and rel_str not in edited_article_keys:
                edited_article_keys.append(rel_str)
        except ValidationError as exc:
            validation_errors.append(f"[{p}]\n{exc.format_user_message()}")
        except Exception as exc:
            validation_errors.append(f"[{p}] {exc}")

    # 1.3 Validate verified_articles format
    for idx, v_item in enumerate(verified_articles_in):
        p = v_item.get("path")
        r = v_item.get("reason", "")
        if not p:
            validation_errors.append(f"Verified Article #{idx + 1}: Must specify 'path'.")
            continue
        try:
            target = _safe_resolve(p, wiki_root=w_root)
            if target.suffix != ".md":
                validation_errors.append(f"Verified Article #{idx + 1}: Path must end with .md, got '{p}'.")
                continue
            rel_str = target.relative_to(w_root).as_posix()
            if not target.is_file() and rel_str not in virtual_fs:
                validation_errors.append(f"Verified Article #{idx + 1}: File not found '{p}'.")
                continue
            if len(str(r).strip()) < 20:
                validation_errors.append(
                    f"Verified Article '{p}': Reason too short ({len(str(r).strip())} chars). Minimum 20 characters required explaining why documentation updates are not needed."
                )
        except Exception as exc:
            validation_errors.append(f"Verified Article #{idx + 1}: {exc}")

    # 1.4 Validate handoff parameters upfront
    normalized_handoff_params: dict[str, Any] | None = None
    if handoff_in:
        try:
            has_writes_in_commit = bool(written_article_keys or edited_article_keys or verified_articles_in)
            normalized_handoff_params = validate_handoff_params(
                session_type=handoff_in.get("session_type", ""),
                previous_handoff_ref=handoff_in.get("previous_handoff_ref", "latest"),
                summary=handoff_in.get("summary") or session_summary or "",
                session_summary=handoff_in.get("session_summary", ""),
                completed_work=handoff_in.get("completed_work"),
                pending_work=handoff_in.get("pending_work"),
                next_steps=handoff_in.get("next_steps"),
                pending_tasks=handoff_in.get("pending_tasks"),
                open_loops=handoff_in.get("open_loops"),
                action_items=handoff_in.get("action_items"),
                todo=handoff_in.get("todo"),
                knowledge_pending_promotion=handoff_in.get("knowledge_pending_promotion"),
                resources=handoff_in.get("resources"),
                gotchas=handoff_in.get("gotchas"),
                open_questions=handoff_in.get("open_questions"),
                open_issues=handoff_in.get("open_issues"),
                risks_and_blockers=handoff_in.get("risks_and_blockers"),
                blockers=handoff_in.get("blockers"),
                risks=handoff_in.get("risks"),
                resolved_issues=handoff_in.get("resolved_issues"),
                files_modified=handoff_in.get("files_modified"),
                boot_instruction=handoff_in.get("boot_instruction", ""),
                boot_instructions=handoff_in.get("boot_instructions", ""),
                decisions=handoff_in.get("decisions"),
                decisions_made=handoff_in.get("decisions_made"),
                key_decisions=handoff_in.get("key_decisions"),
                findings=handoff_in.get("findings"),
                wiki_deviation_justification=handoff_in.get("wiki_deviation_justification", ""),
                _has_session_writes=has_writes_in_commit,
                wiki_root=w_root,
            )
        except (ValueError, FileNotFoundError):
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
    # Pass 2: Transaction Lock, Target Check, Anti-Sprawl, Digest Stamping,
    #         Bottom-Up Verification & Hard Session Ripple Gate
    # =========================================================================
    tx_lock = acquire_wiki_lock(w_root, "_transaction.lock", timeout=timeout)
    with tx_lock:
        ws_index = WorkspaceIndex.build(p_root, w_root, overlay_fs=virtual_fs)
        manifest_data = load_drift_manifest(w_root)
        manifest_staging: dict[str, Any] = json.loads(json.dumps(manifest_data))
        manifest_staging.setdefault("articles", {})

        # Pass 2a: Target check (applies_to_target_missing) and Anti-Sprawl Guard
        for rel_str in list(written_article_keys) + list(edited_article_keys):
            content = virtual_fs[rel_str]
            meta, body = parse_frontmatter(content)
            st = str(meta.get("status", "")).lower()
            sp = str(meta.get("stability", "")).lower()
            non_active = INACTIVE_STATUSES | PRE_IMPLEMENTATION_STATUSES
            if st not in non_active and sp not in non_active:
                applies = meta.get("applies_to")
                if applies:
                    patterns = [str(x) for x in applies] if isinstance(applies, list) else [str(applies)]
                    for pat in patterns:
                        matches = ws_index.find_matching_files([pat])
                        if not matches:
                            raise ValidationError(
                                rule="applies_to_target_missing",
                                path=rel_str,
                                message=f"applies_to pattern '{pat}' does not match any file in workspace index.",
                                actionable="Verify that governed target files exist or declare pre-implementation status (e.g. planned/draft).",
                            )

            if rel_str in written_article_keys and not (w_root / rel_str).is_file():
                check_anti_sprawl_overlap(
                    meta, rel_str, w_root, overlay_fs=virtual_fs, workspace_index=ws_index
                )

        # Pass 2b: Fixed-point digest convergence in memory (2 iterations)
        touched_keys = list(written_article_keys) + list(edited_article_keys)
        for _ in range(2):
            for rel_str in touched_keys:
                content = virtual_fs[rel_str]
                meta, body = parse_frontmatter(content)
                applies = meta.get("applies_to")
                if applies:
                    patterns = [str(x) for x in applies] if isinstance(applies, list) else [str(applies)]
                    master_digest, count, targets = compute_applies_to_manifest(
                        patterns,
                        p_root,
                        w_root,
                        exclude_self_path=rel_str,
                        overlay_fs=virtual_fs,
                        workspace_index=ws_index,
                    )
                    if master_digest:
                        meta["applies_to_digest"] = master_digest
                        meta["applies_to_count"] = count
                        manifest_staging["articles"][rel_str] = {
                            "digest": master_digest,
                            "count": count,
                            "targets": targets,
                        }
                        virtual_fs[rel_str] = dump_frontmatter(meta, body)

        # Pass 2c: Bottom-up evaluation of verified_articles
        if verified_articles_in:
            leaf_verified: list[tuple[str, str, dict[str, Any]]] = []
            umbrella_verified: list[tuple[str, str, dict[str, Any]]] = []

            for v_item in verified_articles_in:
                v_path = normalize_wiki_rel_path(v_item["path"])
                v_reason = v_item["reason"]
                v_content = virtual_fs.get(v_path) or (w_root / v_path).read_text(encoding="utf-8")
                v_meta, _ = parse_frontmatter(v_content)
                v_applies = v_meta.get("applies_to", [])
                v_patterns = [str(x) for x in v_applies] if isinstance(v_applies, list) else [str(v_applies)]
                has_intra_wiki = any(
                    p.startswith(".brain-79/") or p.endswith(".md") or (p.split("/")[0] in ws_index.known_wiki_prefixes)
                    for p in v_patterns
                )
                if has_intra_wiki:
                    umbrella_verified.append((v_path, v_reason, v_meta))
                else:
                    leaf_verified.append((v_path, v_reason, v_meta))

            try:
                from brain79.core.locks import rel_posix
                wiki_rel = rel_posix(w_root, p_root)
            except ValueError:
                wiki_rel = ".brain-79"

            def _validate_and_stamp_verified(v_path: str, v_meta: dict[str, Any]) -> None:
                drifts = check_article_drift(
                    v_path,
                    wiki_root=w_root,
                    project_root=p_root,
                    workspace_index=ws_index,
                    overlay_fs=virtual_fs,
                    manifest_data=manifest_staging,
                )
                for d in drifts:
                    kind = d.get("drift_kind", "")
                    tgt = d.get("target_file", "")
                    # Guard B: Umbrella bypass forbidden
                    if kind == "transitive" or tgt.startswith(f"{wiki_rel}/") or (tgt.startswith(".brain-79/") and tgt.endswith(".md")):
                        raise ValidationError(
                            rule="verified_article_umbrella_bypass_forbidden",
                            path=v_path,
                            message=f"Cannot verify umbrella article '{v_path}': it has unresolved drift targeting intra-wiki articles ({d.get('message', kind)}).",
                            actionable="Resolve the underlying child article drift first or update the umbrella article in writes/edits.",
                        )
                    # Guard A: Structural change forbidden
                    if kind in ("added", "deleted", "missing"):
                        raise ValidationError(
                            rule="verified_article_structural_change_forbidden",
                            path=v_path,
                            message=f"Cannot verify article '{v_path}': governed files were added, deleted, or missing ({kind}: {tgt}). Real documentation update required.",
                            actionable="Update the article content in writes/edits to document added/deleted files instead of using verified_articles.",
                        )
                    # Guard C: AST public signature diff check
                    if kind == "modified" and tgt.endswith(".py"):
                        has_change, desc = has_public_python_api_changes(p_root, tgt, v_path, wiki_root=w_root)
                        if has_change:
                            raise ValidationError(
                                rule="verified_article_public_signature_changed",
                                path=v_path,
                                message=f"Cannot verify article '{v_path}' without documentation update: {desc}.",
                                actionable="Update the article content in writes or edits to document the public API changes.",
                            )

                # Verification passed: stamp digest in virtual_fs and manifest_staging
                v_content = virtual_fs.get(v_path) or (w_root / v_path).read_text(encoding="utf-8")
                meta_v, body_v = parse_frontmatter(v_content)
                applies_v = meta_v.get("applies_to", [])
                pats_v = [str(x) for x in applies_v] if isinstance(applies_v, list) else [str(applies_v)]
                m_dig, cnt, tgts = compute_applies_to_manifest(
                    pats_v,
                    p_root,
                    w_root,
                    exclude_self_path=v_path,
                    overlay_fs=virtual_fs,
                    workspace_index=ws_index,
                )
                if m_dig:
                    meta_v["applies_to_digest"] = m_dig
                    meta_v["applies_to_count"] = cnt
                    manifest_staging["articles"][v_path] = {"digest": m_dig, "count": cnt, "targets": tgts}
                    virtual_fs[v_path] = dump_frontmatter(meta_v, body_v)

            # 2c.1 Evaluate leaf verified articles first
            for v_path, v_reason, v_meta in leaf_verified:
                _validate_and_stamp_verified(v_path, v_meta)
            ws_index.drift_cache.clear()

            # 2c.2 Evaluate umbrella / hybrid verified articles
            for v_path, v_reason, v_meta in umbrella_verified:
                _validate_and_stamp_verified(v_path, v_meta)
            ws_index.drift_cache.clear()

        # Pass 2d: Hard Session Ripple Gate (unresolved_session_ripple)
        if not allow_partial_ripple_in:
            all_drifts = detect_all_drift(
                wiki_root=w_root,
                project_root=p_root,
                workspace_index=ws_index,
                overlay_fs=virtual_fs,
                manifest_data=manifest_staging,
            )

            is_pure_research = False
            if normalized_handoff_params:
                sess_type = normalized_handoff_params.get("session_type", "")
                if sess_type in ("research", "brainstorming", "analysis", "writing"):
                    touched_keys = list(written_article_keys) + list(edited_article_keys)
                    if all(k.startswith("topics/") or k.startswith("context/") for k in touched_keys):
                        is_pure_research = True

            dirty_git_paths: set[str] = set()
            if not is_pure_research:
                try:
                    res_git = subprocess.run(
                        ["git", "-c", "core.quotepath=false", "status", "--porcelain=v1", "-z"],
                        cwd=str(p_root),
                        capture_output=True,
                        check=False,
                        timeout=2.0,
                    )
                    if res_git.returncode == 0 and res_git.stdout:
                        raw_entries = res_git.stdout.split(b"\x00")
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
                                if norm_p and not norm_p.startswith(".brain-79/"):
                                    dirty_git_paths.add(norm_p)
                                if "R" in xy or "C" in xy:
                                    if idx < len(raw_entries) and raw_entries[idx]:
                                        orig_bytes = raw_entries[idx]
                                        idx += 1
                                        orig_str = orig_bytes.decode("utf-8", errors="replace")
                                        norm_orig = normalize_posix_input(orig_str).lstrip("/")
                                        if norm_orig and not norm_orig.startswith(".brain-79/"):
                                            dirty_git_paths.add(norm_orig)
                except Exception:
                    pass

            session_ripple_articles: set[str] = set()
            touched_wiki_articles = set(written_article_keys) | set(edited_article_keys)

            for d in all_drifts:
                art_path = d.get("article_path", "")
                if not art_path:
                    continue

                art_content = virtual_fs.get(art_path)
                if art_content is None and (w_root / art_path).is_file():
                    try:
                        art_content = (w_root / art_path).read_text(encoding="utf-8")
                    except Exception:
                        art_content = None
                if not art_content:
                    continue

                meta_art, _ = parse_frontmatter(art_content)
                st = str(meta_art.get("status", "")).lower()
                sp = str(meta_art.get("stability", "")).lower()
                non_active = INACTIVE_STATUSES | PRE_IMPLEMENTATION_STATUSES
                if st in non_active or sp in non_active:
                    continue

                applies_list = meta_art.get("applies_to", [])
                pats = [str(x) for x in applies_list] if isinstance(applies_list, list) else [str(applies_list)]

                # 1. Intra-wiki umbrella ripple
                governs_touched = False
                for pat in pats:
                    for touched in touched_wiki_articles:
                        cand_wiki = f".brain-79/{touched}"
                        if (
                            match_applies_to_pattern(
                                pat, cand_wiki, known_dirs=ws_index.known_dirs, known_wiki_prefixes=ws_index.known_wiki_prefixes
                            )
                            or match_applies_to_pattern(
                                pat, touched, known_dirs=ws_index.known_dirs, known_wiki_prefixes=ws_index.known_wiki_prefixes
                            )
                        ):
                            governs_touched = True
                            break
                    if governs_touched:
                        break

                if governs_touched:
                    session_ripple_articles.add(art_path)

                # 2. Modified working-tree code ripple
                if not is_pure_research and meta_art.get("applies_to_digest") and dirty_git_paths:
                    for pat in pats:
                        matched_dirty = [
                            df for df in dirty_git_paths
                            if match_applies_to_pattern(
                                pat, df, known_dirs=ws_index.known_dirs, known_wiki_prefixes=ws_index.known_wiki_prefixes
                            )
                        ]
                        if matched_dirty:
                            session_ripple_articles.add(art_path)
                            break

            if session_ripple_articles:
                sorted_ripples = sorted(session_ripple_articles)
                raise ValidationError(
                    rule="unresolved_session_ripple",
                    path=sorted_ripples[0],
                    message=f"Holistic update required: your session changes impacted governing/umbrella article(s) {sorted_ripples}, which remain drifted. Update their prose in 'edits' (or include eligible internal code refactors in 'verified_articles') within this same session_commit.",
                    actionable="Include the impacted articles in writes or edits, or verify non-breaking leaf refactors in verified_articles, or pass allow_partial_ripple=True if intentionally deferring.",
                )

        # =========================================================================
        # Pass 3: Disk Persistence (articles, manifest, index) with Rollback Safety
        # =========================================================================
        orig_states: dict[str, str | None] = {}
        for rel_str in virtual_fs:
            target_f = w_root / rel_str
            orig_states[rel_str] = target_f.read_text(encoding="utf-8") if target_f.is_file() else None

        manifest_file = w_root / ".drift_manifest.json"
        orig_manifest_text = manifest_file.read_text(encoding="utf-8") if manifest_file.is_file() else None

        try:
            save_drift_manifest(w_root, manifest_staging)

            raw_path: str | None = None
            if session_summary:
                raw_msg = save_raw_session(session_summary, instructions=instructions or "", wiki_root=w_root)
                if "_raw/sessions/" in raw_msg:
                    raw_path = "_raw/sessions/" + raw_msg.split("_raw/sessions/")[-1].strip()

            for rel_str, content in virtual_fs.items():
                write_article(
                    rel_str,
                    content,
                    timeout=timeout,
                    force_validation_skip=force_validation_skip,
                    _skip_nav_regen=True,
                    wiki_root=w_root,
                )

            has_indexable_changes = any(
                not p.startswith("_raw/") and not p.startswith("handoffs/") and p not in ("SCHEMA.md", "INDEX.md")
                for p in virtual_fs
            )
            if has_indexable_changes:
                try:
                    regenerate_index_navigation(w_root)
                except Exception:
                    pass
        except BaseException:
            # Transaction rollback: restore files to pre-commit state
            for rel_str, orig_content in orig_states.items():
                target_f = w_root / rel_str
                if orig_content is None:
                    target_f.unlink(missing_ok=True)
                else:
                    target_f.write_text(orig_content, encoding="utf-8", newline="\n")

            if orig_manifest_text is None:
                manifest_file.unlink(missing_ok=True)
            else:
                manifest_file.write_text(orig_manifest_text, encoding="utf-8", newline="\n")

            for tmp_file in w_root.rglob("*.tmp*"):
                tmp_file.unlink(missing_ok=True)
            raise

        # =========================================================================
        # Pass 4: Post-persistence write_handoff() (guarantees fresh handoff)
        # =========================================================================
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
                _has_session_writes=True,
                wiki_root=w_root,
            )
            if "handoffs/" in handoff_msg:
                handoff_path = "handoffs/" + handoff_msg.split("handoffs/")[-1].strip()

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
        "verified_articles": [v.get("path") for v in verified_articles_in],
        "handoff_path": handoff_path,
        "health_status": "warnings" if all_warnings else "ok",
        "warnings": all_warnings,
    }
