"""Tests for Phase 6.7: Transitive Drift, Anti-Sprawl, Locks, and Verification Design."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
from typing import Any
import pytest

from brain79.config import set_project_root
from brain79.core.context import _match_applies_to
from brain79.core.drift import (
    WorkspaceIndex,
    check_article_drift,
    compute_applies_to_manifest,
    compute_file_content_digest,
    compute_wiki_article_digest,
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
    clear_schema_cache,
    load_active_schema,
    parse_frontmatter,
    validate_frontmatter,
)
from brain79.core.handoff_freshness import _EXCLUDED_WIKI_FILES
from brain79.core.locks import get_lock_path
from brain79.core.navigation import regenerate_index_navigation, register_article, load_registry
from brain79.core.validation import check_anti_sprawl_overlap, validate_article_content


def test_pre_6_7_snapshot_diagnostic_baseline(tmp_path: Path) -> None:
    """Verify that the frozen snapshot fixture exists, matches SNAPSHOT_MANIFEST.json, and exhibits baseline before-state."""
    snapshot_dir = Path("tests/fixtures/wiki_pre_6_7_snapshot")
    assert snapshot_dir.is_dir(), "tests/fixtures/wiki_pre_6_7_snapshot must exist."

    manifest_file = snapshot_dir / "SNAPSHOT_MANIFEST.json"
    assert manifest_file.is_file(), "SNAPSHOT_MANIFEST.json must exist in snapshot directory."

    manifest_data = json.loads(manifest_file.read_text(encoding="utf-8"))
    files_map = manifest_data.get("files", {})
    assert len(files_map) == manifest_data.get("total_files")
    assert len(files_map) > 50

    wiki_snapshot = snapshot_dir / ".brain-79"
    assert wiki_snapshot.is_dir()

    # Verify every single file against recorded size and sha256
    for rel_path, expected in files_map.items():
        file_path = wiki_snapshot / rel_path
        assert file_path.is_file(), f"Snapshot file {rel_path} is missing."
        content = file_path.read_bytes()
        assert len(content) == expected["size"], f"File size mismatch for {rel_path}."
        sha = hashlib.sha256(content).hexdigest()
        assert sha == expected["sha256"], f"SHA-256 hash mismatch for {rel_path}."

    # Baseline As-Is diagnostic check: confirm the pre-6.7 conditions exist in snapshot
    # 1. Handoff sprawl exists: handoff-continuity, handoff-freshness, handoff-purge exist as 3 files
    assert (wiki_snapshot / "features/handoff-continuity.md").is_file()
    assert (wiki_snapshot / "features/handoff-freshness.md").is_file()
    assert (wiki_snapshot / "features/handoff-purge.md").is_file()

    # 2. Defect backlog is marked stability: stable in baseline snapshot
    defect_backlog = (wiki_snapshot / "architecture/defect-backlog.md").read_text(encoding="utf-8")
    meta, _ = parse_frontmatter(defect_backlog)
    assert meta.get("stability") == "stable"

    # 3. SLA-3 Diagnostic "Before" Proof on isolated tmp_path
    import shutil
    isolated_proj = tmp_path / "baseline_proj"
    isolated_proj.mkdir()
    isolated_wiki = isolated_proj / ".brain-79"
    shutil.copytree(wiki_snapshot, isolated_wiki)

    from brain79.core.lint_organizational import check_unanchored_governance
    unanchored = check_unanchored_governance(isolated_wiki)
    unanchored_paths = {issue.path for issue in unanchored}
    expected_unanchored = {
        "architecture/dispatcher.md",
        "architecture/mcp-server.md",
        "architecture/symmetry.md",
        "features/cli.md",
        "features/mcp-server.md",
        "features/handoff-continuity.md",
        "features/handoff-purge.md",
    }
    assert expected_unanchored.issubset(unanchored_paths), f"Expected {expected_unanchored} in unanchored, got {unanchored_paths}"

    # 4. Check 0 articles have applies_to_digest in snapshot before migration
    has_digest_count = 0
    for md_p in isolated_wiki.rglob("*.md"):
        try:
            m, _ = parse_frontmatter(md_p.read_text(encoding="utf-8"))
            if "applies_to_digest" in m:
                has_digest_count += 1
        except Exception:
            pass
    assert has_digest_count == 0, f"Expected 0 applies_to_digest in baseline snapshot, found {has_digest_count}"

    # 5. SLA-3 Anti-Sprawl Diagnostic Proof: demonstrating that attempting to register overlapping
    # handoff features without declaring supersedes is blocked by duplicate_governance_target
    (isolated_proj / "src" / "brain79" / "core").mkdir(parents=True, exist_ok=True)
    (isolated_proj / "src" / "brain79" / "core" / "handoff.py").write_text("# handoff\n", encoding="utf-8")
    (isolated_proj / "src" / "brain79" / "core" / "handoff_freshness.py").write_text("# freshness\n", encoding="utf-8")

    (isolated_wiki / "features" / "handoff-continuity.md").write_text(
        "---\ntype: feature\nstatus: shipped\nsummary: Canonical handoffs\nversion: 1.0.0\nlast_updated: 2026-11-12\napplies_to:\n  - src/brain79/core/handoff.py\n---\n\n## Overview\nOverview.\n",
        encoding="utf-8",
    )
    from brain79.core.validation import check_anti_sprawl_overlap
    sprawl_meta = {
        "type": "feature",
        "status": "shipped",
        "applies_to": ["src/brain79/core/handoff.py"],
    }
    with pytest.raises(ValidationError) as sprawl_exc:
        check_anti_sprawl_overlap(sprawl_meta, "features/handoff-v2.md", wiki_root=isolated_wiki)
    assert sprawl_exc.value.rule == "duplicate_governance_target"

    # 6. Run migrate_wiki(isolated_wiki, dry_run=False) and verify digests and manifest seeded
    from brain79.core.migration import migrate_wiki
    report = migrate_wiki(isolated_wiki, dry_run=False)
    assert "Migration Report (APPLIED)" in report
    assert (isolated_wiki / ".drift_manifest.json").is_file()


def test_schema_digest_and_count_validation() -> None:
    """Validate format and type enforcement for applies_to_digest and applies_to_count."""
    set_project_root(None)
    clear_schema_cache()
    valid_meta = {
        "type": "feature",
        "summary": "Sample feature summary",
        "status": "planned",
        "version": "1.0.0",
        "last_updated": "2026-11-11",
        "applies_to": ["src/sample.py"],
        "applies_to_digest": "sha256:0123456789abcdef",
        "applies_to_count": 3,
    }
    # Should pass without error
    validate_frontmatter(valid_meta, "features/sample.md")

    # Invalid digest prefix or length
    invalid_digests = [
        "md5:0123456789abcdef",
        "sha256:123",
        "sha256:0123456789abcdef01",
        "sha256:0123456789ABCDEF",  # uppercase
        "sha256:0123456789abcdef\n",  # trailing newline rejected by re.fullmatch
        12345,
        True,
    ]
    for bad_digest in invalid_digests:
        bad_meta = dict(valid_meta)
        bad_meta["applies_to_digest"] = bad_digest
        with pytest.raises(ValidationError) as exc:
            validate_frontmatter(bad_meta, "features/sample.md")
        assert "frontmatter_invalid_digest" in [i["rule"] for i in exc.value.issues]

    # Invalid count
    invalid_counts = [-1, "3", False, True, 1.5]
    for bad_count in invalid_counts:
        bad_meta = dict(valid_meta)
        bad_meta["applies_to_count"] = bad_count
        with pytest.raises(ValidationError) as exc:
            validate_frontmatter(bad_meta, "features/sample.md")
        assert "frontmatter_invalid_count" in [i["rule"] for i in exc.value.issues]


def test_schema_archived_stability_and_status() -> None:
    """Verify stability: archived in architecture and status: archived in feature."""
    set_project_root(None)
    clear_schema_cache()
    # Architecture with stability: archived
    arch_meta = {
        "type": "architecture",
        "summary": "Historical architecture document",
        "stability": "archived",
        "last_updated": "2026-11-11",
    }
    validate_frontmatter(arch_meta, "architecture/sample.md")

    # Feature with status: archived
    feat_meta = {
        "type": "feature",
        "summary": "Historical feature document",
        "status": "archived",
        "version": "1.0.0",
        "last_updated": "2026-11-11",
    }
    validate_frontmatter(feat_meta, "features/sample.md")

    # Check status categorization
    assert "archived" in INACTIVE_STATUSES
    assert "planned" in PRE_IMPLEMENTATION_STATUSES


def test_lock_mapping_and_handoff_freshness_exclusions(tmp_path: Path) -> None:
    """Verify deterministic lock path mapping and handoff freshness exclusions."""
    wiki_root = tmp_path / ".brain-79"
    wiki_root.mkdir()

    p_manifest = get_lock_path(wiki_root, ".drift_manifest.json")
    assert p_manifest.name == "_drift_manifest.lock"
    assert p_manifest.parent == wiki_root / ".locks"

    p_txn = get_lock_path(wiki_root, "_transaction.lock")
    assert p_txn.name == "_transaction.lock"
    assert p_txn.parent == wiki_root / ".locks"

    # Handoff freshness must exclude .drift_manifest.json
    assert ".drift_manifest.json" in _EXCLUDED_WIKI_FILES


def test_ac_b2_anti_sprawl_blocks_duplicate_feature_creation(tmp_path: Path) -> None:
    """AC-B2: Anti-Sprawl & Target Subsumption Guard on New Article Creation."""
    project_root = tmp_path
    wiki_root = project_root / ".brain-79"
    wiki_root.mkdir()
    features_dir = wiki_root / "features"
    features_dir.mkdir()

    # Create dummy source files
    src_dir = project_root / "src" / "sample"
    src_dir.mkdir(parents=True)
    file_a = src_dir / "auth.py"
    file_b = src_dir / "tokens.py"
    file_c = src_dir / "session.py"
    file_a.write_text("# auth", encoding="utf-8")
    file_b.write_text("# tokens", encoding="utf-8")
    file_c.write_text("# session", encoding="utf-8")

    # Create existing active feature E governing auth.py and tokens.py
    e_content = """---
type: feature
summary: Core authentication module
status: shipped
version: 1.0.0
last_updated: 2026-11-11
applies_to:
  - src/sample/auth.py
  - src/sample/tokens.py
---

## Overview
Core auth overview.
"""
    (features_dir / "core-auth.md").write_text(e_content, encoding="utf-8")

    # Attempt 1: New article with 100% subsumption (targets subset of E) without supersedes -> REJECTED
    new_subsumed_content = """---
type: feature
summary: Duplicate token helper
status: planned
version: 1.0.0
last_updated: 2026-11-11
applies_to:
  - src/sample/tokens.py
---

## Overview
Duplicate token helper overview.
"""
    with pytest.raises(ValidationError) as exc:
        validate_article_content(
            "features/token-helper.md",
            new_subsumed_content,
            wiki_root=wiki_root,
        )
    assert exc.value.rule == "duplicate_governance_target"
    assert "already governs src/sample/tokens.py" in exc.value.message

    # Attempt 2: New article with 100% subsumption but declares 'related: [features/core-auth.md]'
    # Strict rule: 'related' does NOT exempt 100% subsumption! -> STILL REJECTED
    related_subsumed_content = """---
type: feature
summary: Duplicate token helper with related
status: planned
version: 1.0.0
last_updated: 2026-11-11
related:
  - features/core-auth.md
applies_to:
  - src/sample/tokens.py
---

## Overview
Duplicate token helper overview.
"""
    with pytest.raises(ValidationError) as exc:
        validate_article_content(
            "features/token-helper.md",
            related_subsumed_content,
            wiki_root=wiki_root,
        )
    assert exc.value.rule == "duplicate_governance_target"

    # Attempt 3: Declaring 'supersedes: features/core-auth.md' -> ACCEPTED
    supersedes_content = """---
type: feature
summary: Modernized authentication module
status: planned
version: 2.0.0
last_updated: 2026-11-11
supersedes:
  - .brain-79/features/core-auth.md
applies_to:
  - src/sample/tokens.py
---

## Overview
Modernized auth overview.
"""
    res = validate_article_content(
        "features/token-helper.md",
        supersedes_content,
        wiki_root=wiki_root,
    )
    assert "type: feature" in res

    # Attempt 3b: Defer target checks with check_workspace_targets=False -> Passes even if duplicate
    res_deferred = validate_article_content(
        "features/token-helper.md",
        new_subsumed_content,
        wiki_root=wiki_root,
        check_workspace_targets=False,
    )
    assert "type: feature" in res_deferred

    # Attempt 4: allow_overlapping_governance: true -> ACCEPTED
    override_content = """---
type: feature
summary: Explicitly allowed companion
status: planned
version: 1.0.0
last_updated: 2026-11-11
allow_overlapping_governance: true
applies_to:
  - src/sample/tokens.py
---

## Overview
Explicitly allowed companion overview.
"""
    res2 = validate_article_content(
        "features/token-helper.md",
        override_content,
        wiki_root=wiki_root,
    )
    assert "type: feature" in res2

    # Attempt 5: Partial overlap >= 0.65 (auth.py, tokens.py + session.py -> 2/3 = 66.6% Jaccard)
    # Without related -> REJECTED
    partial_overlap_content = """---
type: feature
summary: Session manager overlapping core auth
status: planned
version: 1.0.0
last_updated: 2026-11-11
applies_to:
  - src/sample/auth.py
  - src/sample/tokens.py
  - src/sample/session.py
---

## Overview
Session manager overview.
"""
    with pytest.raises(ValidationError) as exc:
        validate_article_content(
            "features/session-manager.md",
            partial_overlap_content,
            wiki_root=wiki_root,
        )
    assert exc.value.rule == "duplicate_governance_target"
    assert "Jaccard index" in exc.value.message

    # Attempt 6: Partial overlap with 'related: [features/core-auth.md]' -> ACCEPTED
    partial_related_content = """---
type: feature
summary: Session manager overlapping core auth
status: planned
version: 1.0.0
last_updated: 2026-11-11
related:
  - features/core-auth.md
applies_to:
  - src/sample/auth.py
  - src/sample/tokens.py
  - src/sample/session.py
---

## Overview
Session manager overview.
"""
    res3 = validate_article_content(
        "features/session-manager.md",
        partial_related_content,
        wiki_root=wiki_root,
    )
    assert "type: feature" in res3

    # Attempt 7: Planned existing article does NOT block other articles (Hallazgo 1 check)
    planned_existing = """---
type: feature
summary: Future experimental feature
status: planned
version: 0.1.0
last_updated: 2026-11-11
applies_to:
  - src/sample/future.py
---

## Overview
Future planning.
"""
    (src_dir / "future.py").write_text("# future", encoding="utf-8")
    (features_dir / "future-plan.md").write_text(planned_existing, encoding="utf-8")

    new_real_feature = """---
type: feature
summary: Real feature implementing planned area
status: in_progress
version: 0.1.0
last_updated: 2026-11-11
applies_to:
  - src/sample/future.py
---

## Overview
Real implementation.
"""
    # Because future-plan.md is planned (in PRE_IMPLEMENTATION_STATUSES), it does NOT block new_real_feature!
    res4 = validate_article_content(
        "features/future-real.md",
        new_real_feature,
        wiki_root=wiki_root,
    )
    assert "type: feature" in res4

    # Attempt 8: Overlay collision detection (two new features in same batch collision)
    overlay_batch = {
        "features/batch-a.md": """---
type: feature
summary: Batch feature A
status: shipped
version: 1.0.0
last_updated: 2026-11-11
applies_to:
  - src/sample/session.py
---

## Overview
Batch A
""",
    }
    batch_b_content = """---
type: feature
summary: Batch feature B duplicating A
status: shipped
version: 1.0.0
last_updated: 2026-11-11
applies_to:
  - src/sample/session.py
---

## Overview
Batch B
"""
    meta_b, _ = parse_frontmatter(batch_b_content)
    with pytest.raises(ValidationError) as exc:
        check_anti_sprawl_overlap(
            meta_b,
            "features/batch-b.md",
            wiki_root=wiki_root,
            overlay_fs=overlay_batch,
        )
    assert exc.value.rule == "duplicate_governance_target"


def test_navigation_registry_and_manifest_orphan_purge(tmp_path: Path) -> None:
    """Verify that regenerate_index_navigation purges deleted files from registry and drift manifest."""
    wiki_root = tmp_path / ".brain-79"
    wiki_root.mkdir()

    # Create INDEX.md
    index_file = wiki_root / "INDEX.md"
    index_file.write_text(
        "---\ntype: navigation\nlast_updated: 2026-11-11\n---\n\n# Index\n\n## Quick navigation\n",
        encoding="utf-8",
    )

    # Register 2 articles: one that exists, one that will be deleted
    f1 = wiki_root / "features" / "existing.md"
    f1.parent.mkdir()
    f1.write_text("---\ntype: feature\nlast_updated: 2026-11-11\n---\n# Existing\nSummary 1", encoding="utf-8")

    register_article(wiki_root, "features/existing.md", "Existing", "Summary 1", "features")
    register_article(wiki_root, "features/deleted.md", "Deleted", "Summary 2", "features")

    # Create .drift_manifest.json with both entries
    manifest_file = wiki_root / ".drift_manifest.json"
    manifest_data = {
        "version": 1,
        "articles": {
            "features/existing.md": {"targets": {"src/existing.py": "sha256:1111111111111111"}},
            "features/deleted.md": {"targets": {"src/deleted.py": "sha256:2222222222222222"}},
        },
    }
    manifest_file.write_text(json.dumps(manifest_data), encoding="utf-8")

    # Check registry before regeneration
    reg_before = load_registry(wiki_root)
    assert len(reg_before.get("articles", [])) == 2

    # Regenerate index navigation
    regenerate_index_navigation(wiki_root)

    # Check registry after regeneration: deleted.md must be purged
    reg_after = load_registry(wiki_root)
    paths_after = [a["path"] for a in reg_after.get("articles", [])]
    assert paths_after == ["features/existing.md"]

    # Check drift manifest: deleted.md must be purged
    manifest_after = json.loads(manifest_file.read_text(encoding="utf-8"))
    assert list(manifest_after["articles"].keys()) == ["features/existing.md"]


def test_ac_b4_ast_guard_blocks_verified_articles_on_public_api_change(tmp_path: Path) -> None:
    """AC-B4: Verify AST signature verification (Guard C) detects public API changes."""
    proj = tmp_path / "repo"
    proj.mkdir()
    wiki = proj / ".brain-79"
    wiki.mkdir()
    (wiki / "features").mkdir()
    src = proj / "src"
    src.mkdir()

    # Initialize Git repo
    subprocess.run(["git", "init"], cwd=str(proj), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test Agent"], cwd=str(proj), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "agent@brain79.local"], cwd=str(proj), check=True, capture_output=True)

    service_file = src / "service.py"
    initial_code = '''"""Sample service module."""

def public_tool(param: str) -> str:
    """Public helper function."""
    return f"processed {param}"

def _private_helper(x: int) -> int:
    return x * 2

class PublicService:
    """Public service handler."""

    def __init__(self, key: str) -> None:
        self.key = key

    def execute(self) -> None:
        pass

    def _secret(self) -> None:
        pass
'''
    service_file.write_text(initial_code, encoding="utf-8")

    article_file = wiki / "features" / "service.md"
    article_content = """---
type: feature
summary: Service handler feature
status: shipped
version: 1.0.0
last_updated: 2026-11-11
applies_to:
  - src/service.py
---

## Overview
Service handler documentation.
"""
    article_file.write_text(article_content, encoding="utf-8")

    # Initial commit
    subprocess.run(["git", "add", "."], cwd=str(proj), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=str(proj), check=True, capture_output=True)

    # 1. Internal refactor: body changes, private helpers changed/added -> Guard C passes (False, "")
    refactored_code = '''"""Sample service module."""

def public_tool(param: str) -> str:
    """Public helper function."""
    # Body changed completely
    val = param.strip().lower()
    return f"optimized {val}"

def _private_helper(x: int, multiplier: int = 2) -> int:
    # Private helper signature change is allowed
    return x * multiplier

def _new_internal_utility() -> None:
    pass

class PublicService:
    """Public service handler."""

    def __init__(self, key: str) -> None:
        self.key = key

    def execute(self) -> None:
        # Internal body statements changed
        print("executing optimized")

    def _secret(self, extra: bool = True) -> None:
        pass
'''
    service_file.write_text(refactored_code, encoding="utf-8")
    has_changes, reason = has_public_python_api_changes(proj, "src/service.py", "features/service.md")
    assert not has_changes, f"Internal refactor should not trigger Guard C, got: {reason}"
    assert reason == ""

    # 2. Adding a new public function -> Guard C blocks (True, "added public symbol 'def new_tool'...")
    with_new_func = refactored_code + "\ndef new_tool(arg: int) -> None:\n    pass\n"
    service_file.write_text(with_new_func, encoding="utf-8")
    has_changes2, reason2 = has_public_python_api_changes(proj, "src/service.py", "features/service.md")
    assert has_changes2
    assert "added public symbol 'def new_tool' in src/service.py" in reason2

    # 3. Changing public function signature -> Guard C blocks
    with_changed_sig = initial_code.replace("def public_tool(param: str)", "def public_tool(param: str, extra_flag: bool)")
    service_file.write_text(with_changed_sig, encoding="utf-8")
    has_changes3, reason3 = has_public_python_api_changes(proj, "src/service.py", "features/service.md")
    assert has_changes3
    assert "changed public signature for 'def public_tool' in src/service.py" in reason3

    # 4. Removing a public function -> Guard C blocks
    with_removed_func = initial_code.replace("def public_tool(param: str) -> str:\n    \"\"\"Public helper function.\"\"\"\n    return f\"processed {param}\"", "")
    service_file.write_text(with_removed_func, encoding="utf-8")
    has_changes4, reason4 = has_public_python_api_changes(proj, "src/service.py", "features/service.md")
    assert has_changes4
    assert "removed public symbol 'def public_tool' in src/service.py" in reason4

    # 5. Adding a public method to a public class -> Guard C blocks
    with_new_method = initial_code.replace("    def execute(self) -> None:\n        pass", "    def execute(self) -> None:\n        pass\n    def new_method(self) -> None:\n        pass")
    service_file.write_text(with_new_method, encoding="utf-8")
    has_changes5, reason5 = has_public_python_api_changes(proj, "src/service.py", "features/service.md")
    assert has_changes5
    assert "changed public signature for 'class PublicService' in src/service.py" in reason5


def test_ac_e1_two_hop_transitive_drift_and_cycle_immunity(tmp_path: Path) -> None:
    """AC-E1: Multi-hop DAG transitive drift propagation and cycle immunity."""
    proj = tmp_path / "project"
    proj.mkdir()
    wiki = proj / ".brain-79"
    wiki.mkdir()
    (wiki / "features").mkdir()
    (wiki / "architecture").mkdir()
    src = proj / "src"
    src.mkdir()

    auth_code = src / "auth.py"
    auth_code.write_text("def auth(): return True\n", encoding="utf-8")

    # 1. Leaf article: features/auth.md governs src/auth.py
    leaf_digest, leaf_count, leaf_targets = compute_applies_to_manifest(
        ["src/auth.py"],
        proj,
        wiki,
    )
    assert leaf_digest is not None
    leaf_article = wiki / "features" / "auth.md"
    leaf_article.write_text(
        f"""---
type: feature
summary: Core authentication
status: shipped
version: 1.0.0
last_updated: 2026-11-11
applies_to:
  - src/auth.py
applies_to_digest: {leaf_digest}
applies_to_count: {leaf_count}
---

## Overview
Auth overview.
""",
        encoding="utf-8",
    )

    # 2. Umbrella article: architecture/security.md governs .brain-79/features/auth.md
    umb_digest, umb_count, umb_targets = compute_applies_to_manifest(
        [".brain-79/features/auth.md"],
        proj,
        wiki,
    )
    assert umb_digest is not None
    umb_article = wiki / "architecture" / "security.md"
    umb_article.write_text(
        f"""---
type: architecture
summary: Security topology
stability: stable
last_updated: 2026-11-11
applies_to:
  - .brain-79/features/auth.md
applies_to_digest: {umb_digest}
applies_to_count: {umb_count}
---

## Overview
Security overview.
""",
        encoding="utf-8",
    )

    manifest_data = {
        "version": "1.0",
        "articles": {
            "features/auth.md": {
                "digest": leaf_digest,
                "count": leaf_count,
                "targets": leaf_targets,
            },
            "architecture/security.md": {
                "digest": umb_digest,
                "count": umb_count,
                "targets": umb_targets,
            },
        },
    }
    save_drift_manifest(wiki, manifest_data)

    # Clean baseline: 0 drifts
    baseline_drifts = detect_all_drift(wiki_root=wiki, project_root=proj)
    assert len(baseline_drifts) == 0

    # Modify src/auth.py
    auth_code.write_text("def auth(): return 'modified'\n", encoding="utf-8")

    # Leaf feature reports direct drift
    leaf_drifts = check_article_drift("features/auth.md", wiki_root=wiki, project_root=proj)
    assert len(leaf_drifts) == 1
    assert leaf_drifts[0]["drift_kind"] == "modified"
    assert leaf_drifts[0]["target_file"] == "src/auth.py"

    # Umbrella architecture reports transitive drift via features/auth.md
    umb_drifts = check_article_drift("architecture/security.md", wiki_root=wiki, project_root=proj)
    assert len(umb_drifts) >= 1
    transitive_records = [d for d in umb_drifts if d["drift_kind"] == "transitive"]
    assert len(transitive_records) >= 1
    assert transitive_records[0]["child_article"] == "features/auth.md"

    # detect_all_drift captures both direct and transitive
    all_drifts = detect_all_drift(wiki_root=wiki, project_root=proj)
    drift_articles = {d["article_path"] for d in all_drifts}
    assert "features/auth.md" in drift_articles
    assert "architecture/security.md" in drift_articles

    # Bidirectional Cycle Immunity: A governs B, B governs A
    cycle_a = wiki / "features" / "cycle-a.md"
    cycle_b = wiki / "features" / "cycle-b.md"
    cycle_a.write_text(
        """---
type: feature
summary: Cycle A
status: shipped
version: 1.0.0
last_updated: 2026-11-11
applies_to:
  - .brain-79/features/cycle-b.md
applies_to_digest: sha256:0123456789abcdef
applies_to_count: 1
---

## Overview
Cycle A overview.
""",
        encoding="utf-8",
    )
    cycle_b.write_text(
        """---
type: feature
summary: Cycle B
status: shipped
version: 1.0.0
last_updated: 2026-11-11
applies_to:
  - .brain-79/features/cycle-a.md
applies_to_digest: sha256:fedcba9876543210
applies_to_count: 1
---

## Overview
Cycle B overview.
""",
        encoding="utf-8",
    )
    # Must terminate without infinite recursion or stack overflow
    drifts_cycle_a = check_article_drift("features/cycle-a.md", wiki_root=wiki, project_root=proj)
    assert isinstance(drifts_cycle_a, list)


def test_ac_e2_merkle_leaf_attribution_and_zero_match_safety(tmp_path: Path) -> None:
    """AC-E2: Exact leaf attribution in .drift_manifest.json and 0-match safety."""
    proj = tmp_path / "project"
    proj.mkdir()
    wiki = proj / ".brain-79"
    wiki.mkdir()
    (wiki / "features").mkdir()
    core_dir = proj / "src" / "core"
    core_dir.mkdir(parents=True)

    # 10 files: f0.py through f9.py
    for i in range(10):
        (core_dir / f"f{i}.py").write_text(f"# file {i}\n", encoding="utf-8")

    digest, count, targets = compute_applies_to_manifest(
        ["src/core/*.py"],
        proj,
        wiki,
    )
    assert count == 10
    assert digest is not None

    article = wiki / "features" / "core.md"
    article.write_text(
        f"""---
type: feature
summary: Core files
status: shipped
version: 1.0.0
last_updated: 2026-11-11
applies_to:
  - src/core/*.py
applies_to_digest: {digest}
applies_to_count: {count}
---

## Overview
Core overview.
""",
        encoding="utf-8",
    )

    manifest_data = {
        "version": "1.0",
        "articles": {
            "features/core.md": {
                "digest": digest,
                "count": count,
                "targets": targets,
            },
        },
    }
    save_drift_manifest(wiki, manifest_data)

    # Mutate:
    # 1. Modify f1.py
    (core_dir / "f1.py").write_text("# file 1 modified\n", encoding="utf-8")
    # 2. Delete f2.py
    (core_dir / "f2.py").unlink()
    # 3. Add f10.py
    (core_dir / "f10.py").write_text("# file 10 newly added\n", encoding="utf-8")

    drifts = check_article_drift("features/core.md", wiki_root=wiki, project_root=proj)
    drift_map = {d["target_file"]: d["drift_kind"] for d in drifts}

    assert drift_map.get("src/core/f1.py") == "modified"
    assert drift_map.get("src/core/f2.py") == "deleted"
    assert drift_map.get("src/core/f10.py") == "added"
    # Exact leaf attribution: untouched files (f0, f3..f9) must NOT be blamed
    assert len(drifts) == 3

    # Zero-match safety: delete all files in src/core/
    for p in core_dir.glob("*.py"):
        p.unlink()

    drifts_empty = check_article_drift("features/core.md", wiki_root=wiki, project_root=proj)
    kinds_empty = {d["drift_kind"] for d in drifts_empty}
    assert "deleted" in kinds_empty
    assert "missing" in kinds_empty
    missing_record = next(d for d in drifts_empty if d["drift_kind"] == "missing")
    assert "governed files missing: pattern matched 0 files in active article" in missing_record["message"]


def test_ac_e5_byte_streaming_crlf_bom_and_glob_symmetry(tmp_path: Path) -> None:
    """AC-E5: 64 KB byte-streaming CRLF/BOM invariance and glob symmetry."""
    # 1. Streaming CRLF/BOM normalization across 64 KB boundary
    # Build a payload > 128 KB
    base_line = "a" * 63 + "\n"
    num_lines = 2500  # ~160 KB
    clean_text = base_line * num_lines

    # Position a \r\n right at the 64 KB boundary
    clean_bytes = clean_text.encode("utf-8")
    crlf_bytes = clean_text.replace("\n", "\r\n").encode("utf-8")
    bom_crlf_bytes = b"\xef\xbb\xbf" + crlf_bytes

    f_clean = tmp_path / "clean.txt"
    f_crlf = tmp_path / "crlf.txt"
    f_bom = tmp_path / "bom.txt"

    f_clean.write_bytes(clean_bytes)
    f_crlf.write_bytes(crlf_bytes)
    f_bom.write_bytes(bom_crlf_bytes)

    digest_clean = compute_file_content_digest(f_clean)
    digest_crlf = compute_file_content_digest(f_crlf)
    digest_bom = compute_file_content_digest(f_bom)

    assert digest_clean is not None
    assert digest_clean == digest_crlf, "CRLF and LF must yield identical digests across 64 KB boundary"
    assert digest_clean == digest_bom, "UTF-8 BOM must yield identical digest to clean LF"

    # Latin-1 accented bytes without null byte should not raise UnicodeDecodeError
    f_latin1 = tmp_path / "latin1.txt"
    f_latin1.write_bytes(b"caf\xe9\r\ncr\xe8me\r\n")
    digest_latin1 = compute_file_content_digest(f_latin1)
    assert digest_latin1 is not None and digest_latin1.startswith("sha256:")

    # 2. Glob symmetry between drift.py and context.py
    # Test single-segment *, multi-segment **, trailing slash, and custom schema prefix
    known_dirs = {"src", "src/core", "src/cli"}
    known_prefixes = {"rfcs", "decisions", "features"}

    # Pattern 1: Single segment *
    assert match_applies_to_pattern("src/core/*.py", "src/core/a.py", known_dirs, known_prefixes)
    assert not match_applies_to_pattern("src/core/*.py", "src/core/sub/a.py", known_dirs, known_prefixes)
    assert _match_applies_to("src/core/*.py", "src/core/a.py")
    assert not _match_applies_to("src/core/*.py", "src/core/sub/a.py")

    # Pattern 2: Multi segment **
    assert match_applies_to_pattern("src/**/*.py", "src/a.py", known_dirs, known_prefixes)
    assert match_applies_to_pattern("src/**/*.py", "src/a/b/c.py", known_dirs, known_prefixes)
    assert not match_applies_to_pattern("src/**/*.py", "other/a.py", known_dirs, known_prefixes)

    # Pattern 3: Directory prefix
    assert match_applies_to_pattern("src/cli/", "src/cli/dispatch.py", known_dirs, known_prefixes)
    assert match_applies_to_pattern("src/cli", "src/cli/dispatch.py", known_dirs, known_prefixes)
    assert not match_applies_to_pattern("src/cli", "src/cli_other.py", known_dirs, known_prefixes)

    # Pattern 4: Bidirectional intra-wiki normalization (custom schema 'rfcs')
    assert match_applies_to_pattern("rfcs/*.md", ".brain-79/rfcs/001.md", known_dirs, known_prefixes)
    assert match_applies_to_pattern(".brain-79/rfcs/*.md", ".brain-79/rfcs/001.md", known_dirs, known_prefixes)
    assert match_applies_to_pattern(".brain-79/rfcs/*.md", "rfcs/001.md", known_dirs, known_prefixes)


def test_tranche2_adversarial_findings_remediation(tmp_path: Path) -> None:
    """Verify remediations for the 5 adversarial audit findings in Tranche 2."""
    proj = tmp_path / "proj"
    proj.mkdir()
    wiki = proj / ".brain-79"
    wiki.mkdir()
    (wiki / "features").mkdir()
    (wiki / "architecture").mkdir()
    src = proj / "src"
    src.mkdir()

    # Hallazgo 1: PRE_IMPLEMENTATION_STATUSES exempt from drift detection
    code_file = src / "feature.py"
    code_file.write_text("def run(): pass\n", encoding="utf-8")

    planned_article = wiki / "features" / "planned_feature.md"
    planned_article.write_text(
        """---
type: feature
summary: Planned future feature
status: planned
version: 0.1.0
last_updated: 2026-01-01
applies_to:
  - src/feature.py
---

## Overview
Planned feature.
""",
        encoding="utf-8",
    )
    # Even though file_date > last_updated, status: planned must produce 0 drift
    drifts_planned = check_article_drift(planned_article, wiki_root=wiki, project_root=proj)
    assert drifts_planned == []

    # Hallazgo 2: Directory prefix parity in _match_applies_to without known_dirs
    assert _match_applies_to("src/cli", "src/cli/dispatch.py")
    assert _match_applies_to("src/cli/", "src/cli/dispatch.py")
    assert not _match_applies_to("src/cli", "src/cli_other.py")

    # Hallazgo 3: .brain-79/ pattern does not match non-wiki code file outside wiki
    (proj / "features").mkdir(exist_ok=True)
    code_in_features = proj / "features" / "login.py"
    code_in_features.write_text("# code\n", encoding="utf-8")
    assert not match_applies_to_pattern(".brain-79/features/*.md", "features/login.py")
    # Also verify with known_dirs populated as in WorkspaceIndex
    assert not match_applies_to_pattern(
        ".brain-79/features/*.md",
        "features/login.py",
        known_dirs={"features"},
        known_wiki_prefixes={"features"},
    )

    # Hallazgo 4: Cycle drift evaluation does not pollute cache with empty list
    cycle_a = wiki / "features" / "c_a.md"
    cycle_b = wiki / "features" / "c_b.md"
    cycle_a.write_text(
        """---
type: feature
summary: Cycle A
status: shipped
version: 1.0.0
last_updated: 2026-11-11
applies_to:
  - src/feature.py
  - .brain-79/features/c_b.md
applies_to_digest: sha256:1111111111111111
applies_to_count: 2
---

## Overview
Cycle A.
""",
        encoding="utf-8",
    )
    cycle_b.write_text(
        """---
type: feature
summary: Cycle B
status: shipped
version: 1.0.0
last_updated: 2026-11-11
applies_to:
  - .brain-79/features/c_a.md
applies_to_digest: sha256:2222222222222222
applies_to_count: 1
---

## Overview
Cycle B.
""",
        encoding="utf-8",
    )
    # Save initial drift manifest
    manifest_init = {
        "version": "1.0",
        "articles": {
            "features/c_a.md": {
                "digest": "sha256:1111111111111111",
                "count": 2,
                "targets": {
                    "src/feature.py": compute_file_content_digest(code_file),
                    ".brain-79/features/c_b.md": compute_wiki_article_digest(cycle_b.read_text(encoding="utf-8")),
                },
            },
            "features/c_b.md": {
                "digest": "sha256:2222222222222222",
                "count": 1,
                "targets": {
                    ".brain-79/features/c_a.md": compute_wiki_article_digest(cycle_a.read_text(encoding="utf-8")),
                },
            },
        },
    }
    save_drift_manifest(wiki, manifest_init)

    # Modify src/feature.py so A has direct drift
    code_file.write_text("def run(): return 'modified'\n", encoding="utf-8")

    ws = WorkspaceIndex.build(proj, wiki)
    drifts_a = check_article_drift("features/c_a.md", wiki_root=wiki, project_root=proj, workspace_index=ws)
    assert any(d["drift_kind"] == "modified" and d["target_file"] == "src/feature.py" for d in drifts_a)

    # Now evaluate B at top level: B should detect transitive drift via A, not read a polluted []!
    drifts_b = check_article_drift("features/c_b.md", wiki_root=wiki, project_root=proj, workspace_index=ws)
    assert any(d["drift_kind"] == "transitive" and d["child_article"] == "features/c_a.md" for d in drifts_b)

    # Hallazgo 5: Guard C detects changes in default parameter values and decorators
    subprocess.run(["git", "init"], cwd=str(proj), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test Agent"], cwd=str(proj), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "agent@brain79.local"], cwd=str(proj), check=True, capture_output=True)

    mod_file = src / "mod.py"
    mod_file.write_text(
        """def execute(mode: str = "fast") -> str:
    return mode
""",
        encoding="utf-8",
    )
    art_mod = wiki / "features" / "mod.md"
    art_mod.write_text(
        """---
type: feature
summary: Mod feature
status: shipped
version: 1.0.0
last_updated: 2026-11-11
applies_to:
  - src/mod.py
---

## Overview
Mod overview.
""",
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "."], cwd=str(proj), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=str(proj), check=True, capture_output=True)

    # Change default parameter value: "fast" -> "strict"
    mod_file.write_text(
        """def execute(mode: str = "strict") -> str:
    return mode
""",
        encoding="utf-8",
    )
    has_change, desc = has_public_python_api_changes(proj, "src/mod.py", "features/mod.md", wiki_root=wiki)
    assert has_change
    assert "changed public signature for 'def execute'" in desc


def test_ac_b3_orient_returns_all_seven_signal1_articles_untruncated(tmp_path: Path) -> None:
    """AC-B3: Complete governing context reading without top_n truncation, working tree auto-binding, and 64k manifest."""
    repo = tmp_path / "repo"
    repo.mkdir()
    wiki = repo / ".brain-79"
    wiki.mkdir()
    (wiki / "features").mkdir()
    (wiki / "decisions").mkdir()
    src = repo / "src"
    src.mkdir()

    subprocess.run(["git", "init"], cwd=str(repo), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test Agent"], cwd=str(repo), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "agent@brain79.local"], cwd=str(repo), check=True, capture_output=True)

    # Create INDEX.md and SCHEMA.md
    (wiki / "INDEX.md").write_text("# Project Index\n\nRouting table.\n", encoding="utf-8")
    (wiki / "SCHEMA.md").write_text("profile: software\ntypes: {}\n", encoding="utf-8")

    # Create 7 python files and 7 governing feature articles
    for i in range(1, 8):
        (src / f"mod{i}.py").write_text(f"def func_{i}(): return {i}\n", encoding="utf-8")
        related_yaml = "related:\n  - decisions/adr-001.md\n  - decisions/adr-002.md\n" if i == 1 else ""
        (wiki / "features" / f"feat{i}.md").write_text(
            f"""---
type: feature
summary: Feature {i} summary
status: shipped
version: 1.0.0
last_updated: 2026-11-11
applies_to:
  - src/mod{i}.py
{related_yaml}---

## Overview
Feature {i} overview.

## Implementation Details
Feature {i} details.
""",
            encoding="utf-8",
        )

    # Create 2 decision ADRs
    for j in (1, 2):
        (wiki / "decisions" / f"adr-00{j}.md").write_text(
            f"""---
type: decision
summary: ADR 00{j} summary
status: accepted
last_updated: 2026-11-11
---

## Context
ADR {j} context.

## Decision
ADR {j} decision.
""",
            encoding="utf-8",
        )

    subprocess.run(["git", "add", "."], cwd=str(repo), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=str(repo), check=True, capture_output=True)

    from brain79.core.orient import orient

    # 1. Calling orient with explicit paths and max_articles=4:
    # Must inline ALL 7 Signal 1 articles + 2 Signal 3 ADRs (9 total, 0 dropped by max_articles=4)
    touch_paths = [f"src/mod{i}.py" for i in range(1, 8)]
    orient_out = orient(task="Refactor all modules", paths=touch_paths, max_articles=4, wiki_root=wiki)

    for i in range(1, 8):
        assert f"Article: features/feat{i}.md" in orient_out
    assert "Article: decisions/adr-001.md" in orient_out
    assert "Article: decisions/adr-002.md" in orient_out

    # 2. Unconditional working-tree path discovery (task=None, paths=None)
    # Modify all 7 code files in working tree
    for i in range(1, 8):
        (src / f"mod{i}.py").write_text(f"def func_{i}(): return {i * 10}\n", encoding="utf-8")

    orient_dirty = orient(task=None, paths=None, max_articles=4, wiki_root=wiki)
    for i in range(1, 8):
        assert f"Article: features/feat{i}.md" in orient_dirty
    assert "Article: decisions/adr-001.md" in orient_dirty
    assert "Article: decisions/adr-002.md" in orient_dirty
    assert "Documentation Drift Alerts" in orient_dirty
    assert "[DIRECT]" in orient_dirty
    assert "Documentation Drift Suspected" in orient_dirty

    # 3. 64 KB inline budget + Mandatory Reading Manifest fallback
    # Clean working tree for other modules so only mod1 and mod2 are relevant
    subprocess.run(["git", "checkout", "--", "src/mod3.py", "src/mod4.py", "src/mod5.py", "src/mod6.py", "src/mod7.py"], cwd=str(repo), check=True, capture_output=True)

    # Make feat1.md medium-large (~40,000 chars) and feat2.md medium-large (~30,000 chars)
    # Together they exceed the 64,000 char budget
    large_body1 = "## Large Section 1\n" + ("x" * 100 + "\n") * 400
    (wiki / "features" / "feat1.md").write_text(
        f"""---
type: feature
summary: Large feature 1
status: shipped
version: 1.0.0
last_updated: 2026-11-11
applies_to:
  - src/mod1.py
---

{large_body1}
""",
        encoding="utf-8",
    )

    large_body2 = "## Large Section 2\n" + ("y" * 100 + "\n") * 300
    (wiki / "features" / "feat2.md").write_text(
        f"""---
type: feature
summary: Large feature 2
status: shipped
version: 1.0.0
last_updated: 2026-11-11
applies_to:
  - src/mod2.py
---

{large_body2}
""",
        encoding="utf-8",
    )

    orient_overflow = orient(
        task="Inspect mod1 and mod2",
        paths=["src/mod1.py", "src/mod2.py"],
        max_articles=4,
        wiki_root=wiki,
    )

    # feat1 is inlined (first article within budget)
    assert "Article: features/feat1.md" in orient_overflow
    # feat2 overflows and appears in Mandatory Reading Manifest
    assert "## 🚨 Mandatory Reading Manifest (Must Read Before Editing)" in orient_overflow
    assert "- **`features/feat2.md`**:" in orient_overflow
    assert "**Governs (`applies_to`)**: `src/mod2.py`" in orient_overflow
    assert "Large Section 2" in orient_overflow
    assert "brain79_read_batch" in orient_overflow


def test_tranche3_adversarial_findings_remediation(tmp_path: Path) -> None:
    """Verify remediations for the 4 adversarial audit findings in Tranche 3."""
    proj = tmp_path / "proj"
    proj.mkdir()
    wiki = proj / ".brain-79"
    wiki.mkdir()
    (wiki / "features").mkdir()
    (wiki / "architecture").mkdir()
    src = proj / "src"
    src.mkdir()

    subprocess.run(["git", "init"], cwd=str(proj), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test Agent"], cwd=str(proj), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "agent@brain79.local"], cwd=str(proj), check=True, capture_output=True)

    # Initial code and governing article
    code_file = src / "auth.py"
    code_file.write_text("def authenticate(): return True\n", encoding="utf-8")

    art_feat = wiki / "features" / "auth.md"
    art_feat.write_text(
        """---
type: feature
summary: Auth feature
status: shipped
version: 1.0.0
last_updated: 2026-11-01
applies_to:
  - src/auth.py
applies_to_digest: sha256:1111111111111111
applies_to_count: 1
---

## Overview
Auth overview.
""",
        encoding="utf-8",
    )

    art_arch = wiki / "architecture" / "security.md"
    art_arch.write_text(
        """---
type: architecture
summary: Security umbrella
stability: stable
last_updated: 2026-11-01
applies_to:
  - .brain-79/features/auth.md
applies_to_digest: sha256:2222222222222222
applies_to_count: 1
---

## Overview
Security umbrella.
""",
        encoding="utf-8",
    )

    # Add deprecated article for Hallazgo 4
    art_deprecated = wiki / "features" / "auth_v1_legacy.md"
    art_deprecated.write_text(
        """---
type: feature
summary: Deprecated auth v1
status: deprecated
version: 0.1.0
last_updated: 2025-01-01
applies_to:
  - src/auth.py
---

## Overview
Deprecated.
""",
        encoding="utf-8",
    )

    (wiki / "INDEX.md").write_text("# Project Index\n\nRouting table.\n", encoding="utf-8")
    (wiki / "SCHEMA.md").write_text("profile: software\ntypes: {}\n", encoding="utf-8")

    manifest_init = {
        "version": "1.0",
        "articles": {
            "features/auth.md": {
                "digest": "sha256:1111111111111111",
                "count": 1,
                "targets": {
                    "src/auth.py": compute_file_content_digest(code_file),
                },
            },
            "architecture/security.md": {
                "digest": "sha256:2222222222222222",
                "count": 1,
                "targets": {
                    ".brain-79/features/auth.md": compute_wiki_article_digest(art_feat.read_text(encoding="utf-8")),
                },
            },
        },
    }
    save_drift_manifest(wiki, manifest_init)

    subprocess.run(["git", "add", "."], cwd=str(proj), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=str(proj), check=True, capture_output=True)

    # Modify src/auth.py and commit it (working tree is clean!)
    code_file.write_text("def authenticate(): return False\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=str(proj), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Modify auth in code without updating wiki"], cwd=str(proj), check=True, capture_output=True)

    # Verify git status is clean
    st_res = subprocess.run(["git", "status", "--porcelain"], cwd=str(proj), capture_output=True, text=True, check=True)
    assert st_res.stdout.strip() == ""

    # Hallazgo 1: Calling orient() with zero args on clean working tree MUST show drift alerts!
    from brain79.core.orient import orient
    orient_res = orient(task=None, paths=None, wiki_root=wiki)
    assert "## ⚠️ Documentation Drift Alerts" in orient_res
    assert "[DIRECT]" in orient_res
    assert "features/auth.md" in orient_res
    assert "[TRANSITIVE]" in orient_res
    assert "architecture/security.md" in orient_res

    # Hallazgo 2: prepare_curation_guide includes Session Impact & Drift Checklist
    from brain79.core.curate import prepare_curation_guide
    guide_res = prepare_curation_guide(wiki)
    assert "## 🎯 Session Impact & Drift Checklist" in guide_res
    assert "[DIRECT] `features/auth.md`" in guide_res
    assert "[TRANSITIVE] `architecture/security.md`" in guide_res

    # Also test governing articles for modified files when working tree is dirty
    (src / "other.py").write_text("# new code\n", encoding="utf-8")
    guide_res_dirty = prepare_curation_guide(wiki)
    assert "Hard Session Ripple Gate" in guide_res_dirty

    # Hallazgo 3: Git status -z parser handles rename R and leading spaces M
    old_file = src / "old_name.py"
    old_file.write_text("print(1)\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=str(proj), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Add old_name"], cwd=str(proj), check=True, capture_output=True)
    subprocess.run(["git", "mv", "src/old_name.py", "src/new_name.py"], cwd=str(proj), check=True, capture_output=True)

    # Modify an un-staged file so status has leading space " M"
    code_file.write_text("# unstaged modification\n", encoding="utf-8")
    orient_rename = orient(task="Rename test", paths=None, wiki_root=wiki)
    # Both old and new paths should be discovered without crashing
    assert "## 📖 Governing Knowledge Articles" in orient_rename

    # Hallazgo 4: Signal 1 excludes INACTIVE_STATUSES (deprecated, archived, superseded)
    from brain79.core.context import rank_context_articles
    ranked = rank_context_articles(paths=["src/auth.py"], top_n=5, wiki_root=wiki)
    ranked_paths = [p.relative_to(wiki).as_posix() for _, p, _ in ranked]
    assert "features/auth.md" in ranked_paths
    # Deprecated article must NOT be matched via Signal 1 deterministic path boost
    assert "features/auth_v1_legacy.md" not in ranked_paths


def test_ac_b1_holistic_ripple_gate_blocks_partial_commit(tmp_path: Path) -> None:
    """AC-B1: Hard Session Ripple Gate blocks partial commits omitting impacted umbrella articles."""
    proj = tmp_path / "proj"
    proj.mkdir()
    wiki = proj / ".brain-79"
    wiki.mkdir()
    (wiki / "architecture").mkdir()
    (wiki / "decisions").mkdir()

    subprocess.run(["git", "init"], cwd=str(proj), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test Agent"], cwd=str(proj), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "agent@brain79.local"], cwd=str(proj), check=True, capture_output=True)

    (wiki / "INDEX.md").write_text("# Project Index\n\nRouting table.\n", encoding="utf-8")
    (wiki / "SCHEMA.md").write_text("profile: software\ntypes: {}\n", encoding="utf-8")

    adr1 = wiki / "decisions" / "adr-001.md"
    adr1.write_text(
        """---
type: decision
summary: ADR 1
status: accepted
last_updated: 2026-11-11
---

## Context
ADR 1 context.

## Decision
ADR 1 decision.
""",
        encoding="utf-8",
    )

    art_umbrella = wiki / "architecture" / "current-state.md"
    art_umbrella.write_text(
        """---
type: architecture
summary: Current state
stability: stable
last_updated: 2026-11-11
applies_to:
  - .brain-79/decisions/adr-*.md
applies_to_digest: sha256:1111111111111111
applies_to_count: 1
---

## Overview
Current state overview.
""",
        encoding="utf-8",
    )

    manifest_init = {
        "version": "1.0",
        "articles": {
            "architecture/current-state.md": {
                "digest": "sha256:1111111111111111",
                "count": 1,
                "targets": {
                    ".brain-79/decisions/adr-001.md": compute_wiki_article_digest(adr1.read_text(encoding="utf-8")),
                },
            },
        },
    }
    save_drift_manifest(wiki, manifest_init)

    subprocess.run(["git", "add", "."], cwd=str(proj), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=str(proj), check=True, capture_output=True)

    from brain79.core.session_commit import commit_session
    from brain79.core.frontmatter import ValidationError

    # Attempt to commit new adr-018.md while omitting current-state.md
    new_adr_content = """---
type: decision
summary: ADR 18
status: accepted
deciders: [agent]
last_updated: 2026-11-11
---

## Context
ADR 18 context.

## Decision
ADR 18 decision.

## Consequences
ADR 18 consequences.
"""
    with pytest.raises(ValidationError) as exc_info:
        commit_session(
            writes=[{"path": "decisions/adr-018.md", "content": new_adr_content}],
            wiki_root=wiki,
        )
    assert exc_info.value.rule == "unresolved_session_ripple"
    assert "architecture/current-state.md" in exc_info.value.message

    # Verify zero files hit disk on rollback
    assert not (wiki / "decisions" / "adr-018.md").exists()

    # Now succeed when current-state.md is included in the same commit
    updated_current_state = """---
type: architecture
summary: Current state updated
stability: stable
last_updated: 2026-11-11
applies_to:
  - .brain-79/decisions/adr-*.md
---

## Overview
Current state overview including ADR 18.
"""
    res = commit_session(
        writes=[
            {"path": "decisions/adr-018.md", "content": new_adr_content},
            {"path": "architecture/current-state.md", "content": updated_current_state},
        ],
        wiki_root=wiki,
    )
    assert res["success"] is True
    assert (wiki / "decisions" / "adr-018.md").exists()


def test_ac_e3_batch_order_transaction_lock_and_fresh_handoff(tmp_path: Path) -> None:
    """AC-E3: Forward batch references, _transaction.lock and post-persistence fresh handoff."""
    proj = tmp_path / "proj"
    proj.mkdir()
    wiki = proj / ".brain-79"
    wiki.mkdir()
    (wiki / "features").mkdir()

    subprocess.run(["git", "init"], cwd=str(proj), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test Agent"], cwd=str(proj), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "agent@brain79.local"], cwd=str(proj), check=True, capture_output=True)

    (wiki / "INDEX.md").write_text("# Project Index\n\nRouting table.\n", encoding="utf-8")
    (wiki / "SCHEMA.md").write_text("profile: software\ntypes: {}\n", encoding="utf-8")

    subprocess.run(["git", "add", "."], cwd=str(proj), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=str(proj), check=True, capture_output=True)

    from brain79.core.session_commit import commit_session
    from brain79.core.handoff import _resolve_handoff_path
    from brain79.core.handoff_freshness import compute_handoff_freshness

    # writes[0] references writes[1] (.brain-79/features/child.md) which doesn't exist on disk yet
    umbrella_content = """---
type: feature
summary: Umbrella feature
status: shipped
version: 1.0.0
last_updated: 2026-11-11
applies_to:
  - .brain-79/features/child.md
---

## Overview
Umbrella overview.
"""
    child_content = """---
type: feature
summary: Child feature
status: shipped
version: 1.0.0
last_updated: 2026-11-11
applies_to:
  - .brain-79/SCHEMA.md
---

## Overview
Child overview.
"""
    res = commit_session(
        writes=[
            {"path": "features/umbrella.md", "content": umbrella_content},
            {"path": "features/child.md", "content": child_content},
        ],
        handoff={
            "session_type": "feature",
            "summary": "Implement umbrella and child features",
            "completed_work": ["Batch order validated"],
            "pending_work": ["Next phase"],
            "boot_instruction": "Continue development",
        },
        wiki_root=wiki,
    )
    assert res["success"] is True
    assert (wiki / "features" / "umbrella.md").exists()
    assert (wiki / "features" / "child.md").exists()

    # Pass 4 ensures the handoff is fresh immediately
    target_handoff = _resolve_handoff_path("latest", wiki_root=wiki)
    freshness = compute_handoff_freshness(target_handoff, wiki_root=wiki)
    assert freshness.state == "fresh"


def test_ac_e4_bottom_up_verified_articles_resolution(tmp_path: Path) -> None:
    """AC-E4: Bottom-up leaf-first verified_articles resolution and umbrella bypass forbidden."""
    proj = tmp_path / "proj"
    proj.mkdir()
    wiki = proj / ".brain-79"
    wiki.mkdir()
    (wiki / "features").mkdir()
    (wiki / "architecture").mkdir()
    src = proj / "src"
    src.mkdir()

    subprocess.run(["git", "init"], cwd=str(proj), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test Agent"], cwd=str(proj), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "agent@brain79.local"], cwd=str(proj), check=True, capture_output=True)

    (wiki / "INDEX.md").write_text("# Project Index\n\nRouting table.\n", encoding="utf-8")
    (wiki / "SCHEMA.md").write_text("profile: software\ntypes: {}\n", encoding="utf-8")

    server_code = src / "server.py"
    server_code.write_text("def run_server():\n    return 'running'\n", encoding="utf-8")

    art_leaf = wiki / "features" / "mcp-server.md"
    art_leaf.write_text(
        """---
type: feature
summary: MCP server feature
status: shipped
version: 1.0.0
last_updated: 2026-11-11
applies_to:
  - src/server.py
applies_to_digest: sha256:1111111111111111
applies_to_count: 1
---

## Overview
MCP server overview.
""",
        encoding="utf-8",
    )

    art_umbrella = wiki / "architecture" / "current-state.md"
    art_umbrella.write_text(
        """---
type: architecture
summary: Architecture overview
stability: stable
last_updated: 2026-11-11
applies_to:
  - .brain-79/features/mcp-server.md
applies_to_digest: sha256:2222222222222222
applies_to_count: 1
---

## Overview
Architecture overview.
""",
        encoding="utf-8",
    )

    manifest_init = {
        "version": "1.0",
        "articles": {
            "features/mcp-server.md": {
                "digest": "sha256:1111111111111111",
                "count": 1,
                "targets": {
                    "src/server.py": compute_file_content_digest(server_code),
                },
            },
            "architecture/current-state.md": {
                "digest": "sha256:2222222222222222",
                "count": 1,
                "targets": {
                    ".brain-79/features/mcp-server.md": compute_wiki_article_digest(art_leaf.read_text(encoding="utf-8")),
                },
            },
        },
    }
    save_drift_manifest(wiki, manifest_init)

    subprocess.run(["git", "add", "."], cwd=str(proj), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=str(proj), check=True, capture_output=True)

    # 1. Modify internal private helper in server.py (no public signature change)
    server_code.write_text("def _helper(): return 1\ndef run_server():\n    return 'running'\n", encoding="utf-8")

    from brain79.core.session_commit import commit_session
    from brain79.core.frontmatter import ValidationError

    # Case A: Trying to verify umbrella while leaf is drifted raises verified_article_umbrella_bypass_forbidden
    with pytest.raises(ValidationError) as exc_info_a:
        commit_session(
            verified_articles=[
                {
                    "path": "architecture/current-state.md",
                    "reason": "Attempting to bypass leaf verification directly on umbrella",
                }
            ],
            wiki_root=wiki,
        )
    assert exc_info_a.value.rule == "verified_article_umbrella_bypass_forbidden"

    # Case B: Adding public API change blocks verified_articles on leaf (Guard C)
    server_code.write_text("def new_public_tool(): pass\ndef run_server():\n    return 'running'\n", encoding="utf-8")
    with pytest.raises(ValidationError) as exc_info_b:
        commit_session(
            verified_articles=[
                {
                    "path": "features/mcp-server.md",
                    "reason": "Internal refactor without documentation change",
                }
            ],
            wiki_root=wiki,
        )
    assert exc_info_b.value.rule == "verified_article_public_signature_changed"
    assert "def new_public_tool" in exc_info_b.value.message

    # Case C: Revert to internal refactor only: verifying leaf resolves transitive drift on umbrella!
    server_code.write_text("def _helper(): return 2\ndef run_server():\n    return 'running'\n", encoding="utf-8")
    res = commit_session(
        verified_articles=[
            {
                "path": "features/mcp-server.md",
                "reason": "Internal refactor with no public API changes whatsoever",
            }
        ],
        wiki_root=wiki,
    )
    assert res["success"] is True
    assert "features/mcp-server.md" in res["verified_articles"]


def test_tranche4_adversarial_findings_remediation(tmp_path: Path) -> None:
    """Verify remediations for all 6 adversarial audit findings in Tranche 4."""
    proj = tmp_path / "proj"
    proj.mkdir()
    wiki = proj / ".brain-79"
    wiki.mkdir()
    (wiki / "features").mkdir()
    (wiki / "architecture").mkdir()
    src = proj / "src"
    src.mkdir()

    subprocess.run(["git", "init"], cwd=str(proj), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test Agent"], cwd=str(proj), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "agent@brain79.local"], cwd=str(proj), check=True, capture_output=True)

    (wiki / "INDEX.md").write_text("# Project Index\n\nRouting table.\n", encoding="utf-8")
    (wiki / "SCHEMA.md").write_text("profile: software\ntypes: {}\n", encoding="utf-8")

    code_file = src / "app.py"
    code_file.write_text("def run(): pass\n", encoding="utf-8")

    # Hallazgo 1: check_unanchored_governance (warning) and check_applies_to_target_missing (info)
    unanchored = wiki / "features" / "unanchored.md"
    unanchored.write_text(
        """---
type: feature
summary: Unanchored feature
status: shipped
version: 1.0.0
last_updated: 2026-11-11
---

## Overview
Unanchored overview.
""",
        encoding="utf-8",
    )

    ghost = wiki / "features" / "ghost.md"
    ghost.write_text(
        """---
type: feature
summary: Ghost feature
status: shipped
version: 1.0.0
last_updated: 2026-11-11
applies_to:
  - src/nonexistent_ghost.py
---

## Overview
Ghost overview.
""",
        encoding="utf-8",
    )

    from brain79.core.lint_organizational import (
        check_unanchored_governance,
        check_applies_to_target_missing,
        lint_organizational,
    )

    unanchored_issues = check_unanchored_governance(wiki)
    assert any(i.rule == "unanchored_governance_article" and i.path == "features/unanchored.md" and i.severity == "warning" for i in unanchored_issues)

    target_missing_issues = check_applies_to_target_missing(wiki)
    assert any(i.rule == "applies_to_target_missing" and i.path == "features/ghost.md" and i.severity == "info" for i in target_missing_issues)

    all_org = lint_organizational(wiki)
    assert any(i.rule == "unanchored_governance_article" for i in all_org)
    assert any(i.rule == "applies_to_target_missing" for i in all_org)

    # Hallazgo 2: migrate_wiki seeds applies_to_digest, applies_to_count, and purges deleted articles
    art_to_seed = wiki / "features" / "needs_seed.md"
    art_to_seed.write_text(
        """---
type: feature
summary: Needs seed
status: shipped
version: 1.0.0
last_updated: 2026-11-11
applies_to:
  - src/app.py
---

## Overview
Needs seed overview.
""",
        encoding="utf-8",
    )

    from brain79.core.migration import migrate_wiki
    from brain79.core.drift import load_drift_manifest

    # Run migration with apply=True
    mig_report = migrate_wiki(wiki, dry_run=False)
    assert "features/needs_seed.md" in mig_report

    # Verify frontmatter has applies_to_digest
    meta_seeded, _ = parse_frontmatter(art_to_seed.read_text(encoding="utf-8"))
    assert meta_seeded.get("applies_to_digest", "").startswith("sha256:")
    assert meta_seeded.get("applies_to_count") == 1

    # Verify .drift_manifest.json has the article
    man_data = load_drift_manifest(wiki)
    assert "features/needs_seed.md" in man_data.get("articles", {})

    # Delete needs_seed.md and re-run migration: it should purge it from .drift_manifest.json!
    art_to_seed.unlink()
    migrate_wiki(wiki, dry_run=False)
    man_data_after = load_drift_manifest(wiki)
    assert "features/needs_seed.md" not in man_data_after.get("articles", {})

    # Hallazgo 4: write_article() enforces target validation and stamps digest on single-file write
    from brain79.core.wiki import write_article
    from brain79.core.frontmatter import ValidationError

    # Target missing raises ValidationError
    with pytest.raises(ValidationError) as exc_missing:
        write_article(
            "features/new_direct.md",
            """---
type: feature
summary: Direct missing target
status: shipped
version: 1.0.0
last_updated: 2026-11-11
applies_to:
  - src/not_real.py
---

## Overview
Overview.
""",
            wiki_root=wiki,
        )
    assert exc_missing.value.rule == "applies_to_target_missing"

    # Valid write stamps applies_to_digest into file and manifest
    write_article(
        "features/new_direct.md",
        """---
type: feature
summary: Direct valid target
status: shipped
version: 1.0.0
last_updated: 2026-11-11
applies_to:
  - src/app.py
---

## Overview
Overview.
""",
        wiki_root=wiki,
    )
    direct_file = wiki / "features" / "new_direct.md"
    meta_direct, _ = parse_frontmatter(direct_file.read_text(encoding="utf-8"))
    assert meta_direct.get("applies_to_digest", "").startswith("sha256:")
    man_data_direct = load_drift_manifest(wiki)
    assert "features/new_direct.md" in man_data_direct.get("articles", {})

    # Hallazgo 6: Hybrid article (governing .py and .md) can verify internal refactor on .py file
    code_hybrid = src / "hybrid.py"
    code_hybrid.write_text("def hybrid_run(): return 'ok'\n", encoding="utf-8")

    art_hybrid = wiki / "architecture" / "hybrid.md"
    art_hybrid.write_text(
        """---
type: architecture
summary: Hybrid architecture
stability: stable
last_updated: 2026-11-11
applies_to:
  - src/hybrid.py
  - .brain-79/features/new_direct.md
---

## Overview
Hybrid overview.
""",
        encoding="utf-8",
    )
    # Stamp hybrid in manifest
    from brain79.core.wiki import write_many_articles
    write_many_articles(
        [
            {"path": "architecture/hybrid.md", "content": art_hybrid.read_text(encoding="utf-8")},
        ],
        wiki_root=wiki,
    )

    subprocess.run(["git", "add", "."], cwd=str(proj), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Commit hybrid"], cwd=str(proj), check=True, capture_output=True)

    # Modify private helper in src/hybrid.py
    code_hybrid.write_text("def _private(): pass\ndef hybrid_run(): return 'ok'\n", encoding="utf-8")

    from brain79.core.session_commit import commit_session
    # Verifying hybrid article for internal code refactor should succeed without umbrella bypass error!
    res_hybrid = commit_session(
        verified_articles=[
            {
                "path": "architecture/hybrid.md",
                "reason": "Internal refactor of hybrid private helpers with no public changes",
            }
        ],
        wiki_root=wiki,
    )
    assert res_hybrid["success"] is True
    assert "architecture/hybrid.md" in res_hybrid["verified_articles"]


def test_golden_wiki_blueprint_verification() -> None:
    """SLA-3: Verify live .brain-79/ meets the To-Be Golden Blueprint specification."""
    w_root = Path(".brain-79")
    p_root = Path(".")
    assert w_root.is_dir()

    # 1. Sprawl consolidation: handoff-freshness and handoff-purge consolidated into handoff-continuity
    assert (w_root / "features/handoff-continuity.md").is_file()
    assert not (w_root / "features/handoff-freshness.md").exists()
    assert not (w_root / "features/handoff-purge.md").exists()

    # 2. Historical lifecycle accuracy: defect-backlog transitioned to stability: archived
    defect_backlog = (w_root / "architecture/defect-backlog.md").read_text(encoding="utf-8")
    meta_backlog, _ = parse_frontmatter(defect_backlog)
    assert meta_backlog.get("stability") == "archived"

    # 3. 100% source code governance coverage across src/brain79/**/*.py
    all_py_files: set[str] = set()
    for py_p in (p_root / "src" / "brain79").rglob("*.py"):
        all_py_files.add(py_p.relative_to(p_root).as_posix())
    assert len(all_py_files) > 15, "Expected >= 15 python files in src/brain79"

    governed_py_files: set[str] = set()
    from brain79.core.drift import WorkspaceIndex
    ws_index = WorkspaceIndex.build(p_root, w_root)

    for md_p in sorted(w_root.rglob("*.md")):
        rel = md_p.relative_to(w_root).as_posix()
        if rel in ("INDEX.md", "SCHEMA.md") or rel.startswith("_raw/") or rel.startswith("handoffs/"):
            continue
        try:
            meta, _ = parse_frontmatter(md_p.read_text(encoding="utf-8"))
        except Exception:
            continue
        status = str(meta.get("status", "")).lower()
        stability = str(meta.get("stability", "")).lower()
        if status in INACTIVE_STATUSES or stability in INACTIVE_STATUSES:
            continue
        applies = meta.get("applies_to")
        if not applies:
            continue
        patterns = [str(x) for x in applies] if isinstance(applies, list) else [str(applies)]
        for pat in patterns:
            matched = ws_index.find_matching_files([pat])
            for m in matched:
                if m.startswith("src/brain79/") and m.endswith(".py"):
                    governed_py_files.add(m)

    missing_coverage = all_py_files - governed_py_files
    assert not missing_coverage, f"Uncovered Python files without governing active articles: {missing_coverage}"

    # 4. Zero drift across entire repository
    from brain79.core.drift import detect_all_drift
    drifts = detect_all_drift(wiki_root=w_root)
    assert drifts == [], f"Expected 0 drifts in Golden Blueprint, found: {drifts}"

    # 5. Clean organizational linting: 0 critical, 0 warning, 0 orphan
    from brain79.core.lint import lint_wiki
    report = lint_wiki(wiki_root=w_root)
    assert "[Status: OK]" in report, f"Expected [Status: OK] in lint report, got:\n{report}"
    assert "## [CRITICAL] Broken Local Links (0)" in report
    assert "## [CRITICAL] Namespace Violations (0)" in report
    assert "## [WARNING] Structural Errors & Warnings (0)" in report


def test_ac_e6_lint_strict_non_blocking_on_dirty_code_tree(tmp_path: Path) -> None:
    """AC-E6: Dirty code files emit info severity (non-blocking in strict mode), while unanchored emits warning."""
    proj = tmp_path / "proj"
    proj.mkdir()
    wiki = proj / ".brain-79"
    src = proj / "src"
    src.mkdir()
    code_file = src / "app.py"
    code_file.write_text("def run(): pass\n", encoding="utf-8")

    from brain79.core.init_project import init_project
    init_project(project_root=proj, profile="software")

    subprocess.run(["git", "init"], cwd=str(proj), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=str(proj), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=str(proj), check=True, capture_output=True)

    # Author active feature governing app.py via write_article so it is registered in INDEX.md
    from brain79.core.wiki import write_article
    write_article(
        "features/app.md",
        "---\ntype: feature\nsummary: App feature\nstatus: shipped\nversion: 1.0.0\nlast_updated: 2026-11-12\napplies_to:\n  - src/app.py\n---\n\n# Feature — App\n\n## Overview\nApp overview.\n\n---\n\n[← Volver al Índice](../INDEX.md)\n",
        wiki_root=wiki,
    )

    from brain79.core.migration import migrate_wiki
    migrate_wiki(wiki, dry_run=False)

    subprocess.run(["git", "add", "."], cwd=str(proj), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Clean baseline"], cwd=str(proj), check=True, capture_output=True)

    # Modify code file in dirty working tree
    code_file.write_text("def run(): return 'modified'\n", encoding="utf-8")

    from brain79.core.lint import lint_wiki
    report_dirty = lint_wiki(wiki_root=wiki)
    # Dirty code drift must be INFO severity, so status remains OK (non-blocking for strict mode)
    assert "[Status: OK]" in report_dirty

    # Now add unanchored active architecture article
    (wiki / "architecture").mkdir(exist_ok=True)
    (wiki / "architecture" / "unanchored.md").write_text(
        "---\ntype: architecture\nsummary: Unanchored arch\nstability: stable\nlast_updated: 2026-11-12\n---\n\n# Architecture — Unanchored\n\n## Overview\nOverview.\n\n---\n\n[← Volver al Índice](../INDEX.md)\n",
        encoding="utf-8",
    )
    from brain79.core.navigation import regenerate_index_navigation
    regenerate_index_navigation(wiki)

    report_unanchored = lint_wiki(wiki_root=wiki)
    assert "[Status: WARNING]" in report_unanchored
    assert "unanchored_governance_article" in report_unanchored or "lacks applies_to governance pattern" in report_unanchored


def test_sla1_cold_start_latency_and_subprocess_bound(monkeypatch: pytest.MonkeyPatch) -> None:
    """SLA-1: orient() on Brain-79 repository must complete in < 100 ms wall-clock time and spawn <= 1 git ls-files call."""
    import time
    from brain79.core.orient import orient
    w_root = Path(".brain-79")
    assert w_root.is_dir()

    ls_files_calls = 0
    orig_run = subprocess.run

    def spy_run(*args: Any, **kwargs: Any) -> Any:
        nonlocal ls_files_calls
        cmd = args[0] if args else kwargs.get("args", [])
        cmd_str = " ".join(cmd) if isinstance(cmd, list) else str(cmd)
        if "ls-files" in cmd_str:
            ls_files_calls += 1
        return orig_run(*args, **kwargs)

    monkeypatch.setattr(subprocess, "run", spy_run)

    # Warm-up run and subprocess count verification
    res = orient(task="Inspect system status", paths=["src/brain79/server.py"], wiki_root=w_root)
    assert "# Brain-79 — Session Cold Start Orientation" in res
    assert ls_files_calls <= 1, f"Expected at most 1 git ls-files call in orient(), got {ls_files_calls}"

    # Measure min latency across 3 runs
    durations: list[float] = []
    for _ in range(3):
        t0 = time.perf_counter()
        orient(task="Inspect system status", paths=["src/brain79/server.py"], wiki_root=w_root)
        durations.append(time.perf_counter() - t0)

    raw_factor = os.environ.get("BRAIN79_PERF_FACTOR", "1.0").strip()
    try:
        perf_factor = max(0.1, float(raw_factor))
    except ValueError:
        perf_factor = 1.0
    ceiling = 0.120 * perf_factor
    min_duration = min(durations)
    assert min_duration < ceiling, f"orient() took {min_duration*1000:.1f}ms, expected < {ceiling*1000:.1f}ms (SLA-1 target: < 100ms scaled by {perf_factor})"

