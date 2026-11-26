"""Tests for Stage 1 (SPEC-202611 AC-4): strict-mode unanchored_governance_article pre-flight parity."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from brain79.core.lint_organizational import check_unanchored_governance
from brain79.core.session_commit import commit_session
from brain79.core.validation import ValidationError
from brain79.core.wiki import (
    check_file_health,
    edit_article,
    write_article,
    write_many_articles,
)


def _setup_wiki(
    tmp_path: Path,
    *,
    profile: str = "software",
    enforcement: str = "strict",
) -> tuple[Path, Path]:
    """Create a minimal project + wiki root with SCHEMA.md and a source file."""
    project_root = tmp_path
    wiki_root = project_root / ".brain-79"
    wiki_root.mkdir(parents=True, exist_ok=True)
    (project_root / "src").mkdir(exist_ok=True)
    (project_root / "src" / "app.py").write_text("def run() -> None:\n    pass\n", encoding="utf-8")

    schema_content = (
        f"---\n"
        f"type: schema\n"
        f"profile: {profile}\n"
        f"enforcement: {enforcement}\n"
        f"last_updated: 2026-11-26\n"
        f"---\n\n"
        f"# Wiki schema\n"
    )
    (wiki_root / "SCHEMA.md").write_text(schema_content, encoding="utf-8")
    (wiki_root / "INDEX.md").write_text(
        "---\ntype: navigation\nlast_updated: 2026-11-26\n---\n\n# Project index\n\n## Quick navigation\n",
        encoding="utf-8",
    )
    return project_root, wiki_root


def _article_content(
    *,
    doc_type: str = "architecture",
    status: str | None = None,
    stability: str | None = None,
    applies_to: Any = None,
    include_applies_to_key: bool = False,
    title: str = "System architecture",
) -> str:
    """Build valid-skeleton living-manual markdown with configurable frontmatter."""
    lines = [
        "---",
        f"type: {doc_type}",
    ]
    if doc_type == "architecture":
        lines.append(f"stability: {stability or 'stable'}")
    else:
        lines.append(f"status: {status or 'shipped'}")
        if stability is not None:
            lines.append(f"stability: {stability}")
    if include_applies_to_key or applies_to is not None:
        if applies_to is None:
            lines.append("applies_to: null")
        elif isinstance(applies_to, list):
            if not applies_to:
                lines.append("applies_to: []")
            else:
                lines.append("applies_to:")
                for item in applies_to:
                    lines.append(f"  - {item!r}" if isinstance(item, str) and not item.strip() else f"  - {item}")
        else:
            lines.append(f"applies_to: {applies_to!r}")
    lines.extend([
        "last_updated: 2026-11-26",
        "summary: Concise living manual summary for testing",
        "---",
        "",
        f"# {title}",
        "",
        "## Overview",
        "",
        "Overview content.",
        "",
        "## Components" if doc_type == "architecture" else "## Behavior",
        "",
        "Details.",
        "",
        "## Key flows" if doc_type == "architecture" else "## Configuration",
        "",
        "Flows.",
        "",
        "[← Back to Index](../INDEX.md)",
        "",
    ])
    return "\n".join(lines)


class TestStrictPreflightParity:
    """Verify R-3.1, R-3.2, R-3.3, and R-3.4 across all write paths."""

    @pytest.mark.parametrize(
        "applies_kw",
        [
            {"applies_to": None, "include_applies_to_key": False},
            {"applies_to": None, "include_applies_to_key": True},
            {"applies_to": [], "include_applies_to_key": True},
            {"applies_to": ["", "   "], "include_applies_to_key": True},
            {"applies_to": "   ", "include_applies_to_key": True},
        ],
    )
    def test_write_article_rejects_unanchored_active_software_strict(
        self, tmp_path: Path, applies_kw: dict[str, Any]
    ) -> None:
        _, wiki_root = _setup_wiki(tmp_path, profile="software", enforcement="strict")
        content = _article_content(doc_type="architecture", status="shipped", **applies_kw)

        with pytest.raises(ValidationError) as exc_info:
            write_article("architecture/core.md", content, wiki_root=wiki_root)

        assert exc_info.value.rule == "unanchored_governance_article"
        assert "architecture/core.md" in exc_info.value.path
        assert "applies_to" in exc_info.value.actionable
        assert not (wiki_root / "architecture" / "core.md").exists()

    def test_edit_article_removing_applies_to_rejected_atomically(self, tmp_path: Path) -> None:
        _, wiki_root = _setup_wiki(tmp_path, profile="software", enforcement="strict")
        anchored = _article_content(
            doc_type="feature",
            status="shipped",
            applies_to=["src/app.py"],
            title="Core feature",
        )
        write_article("features/core.md", anchored, wiki_root=wiki_root)
        before_disk = (wiki_root / "features" / "core.md").read_text(encoding="utf-8")

        with pytest.raises(ValidationError) as exc_info:
            edit_article(
                "features/core.md",
                [{"old_text": "applies_to:\n  - src/app.py\n", "new_text": ""}],
                wiki_root=wiki_root,
            )

        assert exc_info.value.rule == "unanchored_governance_article"
        assert (wiki_root / "features" / "core.md").read_text(encoding="utf-8") == before_disk

    def test_write_many_articles_enumerates_all_offenders_with_zero_disk_mutation(
        self, tmp_path: Path
    ) -> None:
        _, wiki_root = _setup_wiki(tmp_path, profile="software", enforcement="strict")
        arch = _article_content(doc_type="architecture", status="shipped", title="Arch")
        feat = _article_content(doc_type="feature", status="shipped", title="Feat")
        valid = _article_content(
            doc_type="feature",
            status="shipped",
            applies_to=["src/app.py"],
            title="Valid feat",
        )

        with pytest.raises(ValidationError) as exc_info:
            write_many_articles(
                [
                    {"path": "architecture/a.md", "content": arch},
                    {"path": "features/b.md", "content": feat},
                    {"path": "features/c.md", "content": valid},
                ],
                wiki_root=wiki_root,
            )

        err = exc_info.value
        assert err.rule == "unanchored_governance_article"
        msg = err.format_user_message()
        assert "architecture/a.md" in msg
        assert "features/b.md" in msg
        assert "applies_to:" in msg
        assert not (wiki_root / "architecture" / "a.md").exists()
        assert not (wiki_root / "features" / "b.md").exists()
        assert not (wiki_root / "features" / "c.md").exists()

    def test_commit_session_writes_and_edits_enumerate_all_offenders_atomically(
        self, tmp_path: Path
    ) -> None:
        _, wiki_root = _setup_wiki(tmp_path, profile="software", enforcement="strict")
        anchored = _article_content(
            doc_type="feature",
            status="shipped",
            applies_to=["src/app.py"],
            title="Existing feature",
        )
        write_article("features/existing.md", anchored, wiki_root=wiki_root)
        before_disk = (wiki_root / "features" / "existing.md").read_text(encoding="utf-8")

        new_arch = _article_content(doc_type="architecture", status="shipped", title="New arch")

        with pytest.raises(ValidationError) as exc_info:
            commit_session(
                session_summary="Attempt unanchored writes and edit",
                writes=[{"path": "architecture/new-arch.md", "content": new_arch}],
                edits=[
                    {
                        "path": "features/existing.md",
                        "edits": [{"old_text": "applies_to:\n  - src/app.py\n", "new_text": ""}],
                    }
                ],
                wiki_root=wiki_root,
            )

        err = exc_info.value
        assert err.rule == "unanchored_governance_article"
        msg = err.format_user_message()
        assert "architecture/new-arch.md" in msg
        assert "features/existing.md" in msg
        assert "applies_to:" in msg
        assert not (wiki_root / "architecture" / "new-arch.md").exists()
        assert (wiki_root / "features" / "existing.md").read_text(encoding="utf-8") == before_disk

    @pytest.mark.parametrize("tier", ["balanced", "advisory"])
    def test_balanced_and_advisory_allow_and_surface_warning(
        self, tmp_path: Path, tier: str
    ) -> None:
        _, wiki_root = _setup_wiki(tmp_path, profile="software", enforcement=tier)
        arch = _article_content(doc_type="architecture", status="shipped", title="Arch")
        feat = _article_content(doc_type="feature", status="shipped", title="Feat")

        res_single = write_article("architecture/a.md", arch, wiki_root=wiki_root)
        assert "unanchored_governance_article" in res_single

        res_batch = write_many_articles(
            [{"path": "features/b.md", "content": feat}],
            wiki_root=wiki_root,
        )
        assert "unanchored_governance_article" in res_batch
        assert "lint OK" not in res_batch

        res_commit = commit_session(
            session_summary="Commit unanchored under non-strict",
            writes=[{"path": "features/c.md", "content": feat}],
            wiki_root=wiki_root,
        )
        assert res_commit["success"] is True
        assert res_commit["health_status"] == "warnings"
        assert any("unanchored_governance_article" in w for w in res_commit["warnings"])

    def test_force_validation_skip_allows_and_surfaces_warning(self, tmp_path: Path) -> None:
        _, wiki_root = _setup_wiki(tmp_path, profile="software", enforcement="strict")
        arch = _article_content(doc_type="architecture", status="shipped", title="Arch")
        feat = _article_content(doc_type="feature", status="shipped", title="Feat")

        res_single = write_article(
            "architecture/a.md", arch, force_validation_skip=True, wiki_root=wiki_root
        )
        assert "unanchored_governance_article" in res_single

        res_batch = write_many_articles(
            [{"path": "features/b.md", "content": feat}],
            force_validation_skip=True,
            wiki_root=wiki_root,
        )
        assert "unanchored_governance_article" in res_batch
        assert "lint OK" not in res_batch

        res_commit = commit_session(
            session_summary="Force skip commit",
            writes=[{"path": "features/c.md", "content": feat}],
            force_validation_skip=True,
            wiki_root=wiki_root,
        )
        assert res_commit["success"] is True
        assert res_commit["health_status"] == "warnings"
        assert any("unanchored_governance_article" in w for w in res_commit["warnings"])

    def test_general_profile_and_exempt_statuses_allowed_without_warning(
        self, tmp_path: Path
    ) -> None:
        _, gen_wiki = _setup_wiki(tmp_path / "gen", profile="general", enforcement="strict")
        # Even if a general-profile wiki defines custom_types including 'architecture',
        # unanchored_governance_article only applies to profile == "software".
        (gen_wiki / "SCHEMA.md").write_text(
            "---\n"
            "type: schema\n"
            "profile: general\n"
            "enforcement: strict\n"
            "last_updated: 2026-11-26\n"
            "custom_types:\n"
            "  architecture:\n"
            "    required: [type, summary, stability, last_updated]\n"
            "    optional: [applies_to]\n"
            "    enum: {}\n"
            "---\n\n# Wiki schema\n",
            encoding="utf-8",
        )
        arch = _article_content(doc_type="architecture", stability="stable", title="Arch")
        res_gen = write_article("architecture/a.md", arch, wiki_root=gen_wiki)
        assert "unanchored_governance_article" not in res_gen
        assert check_file_health(gen_wiki, "architecture/a.md", arch) == []

        _, sw_wiki = _setup_wiki(tmp_path / "sw", profile="software", enforcement="strict")
        for idx, (dtype, st, stab) in enumerate([
            ("feature", "planned", None),
            ("feature", "deprecated", None),
            ("feature", "archived", None),
            ("feature", "legacy", None),
            ("architecture", None, "archived"),
            ("architecture", None, "legacy"),
        ]):
            content = _article_content(
                doc_type=dtype, status=st, stability=stab, title=f"Exempt {idx}"
            )
            subdir = "features" if dtype == "feature" else "architecture"
            rel = f"{subdir}/exempt-{idx}.md"
            res = write_article(rel, content, wiki_root=sw_wiki)
            assert "unanchored_governance_article" not in res
            assert check_file_health(sw_wiki, rel, content) == []
            assert check_unanchored_governance(sw_wiki) == []

        from brain79.core.frontmatter import load_active_schema
        from brain79.core.lint_organizational import is_unanchored_governance_article

        sw_schema = load_active_schema(sw_wiki)
        assert not is_unanchored_governance_article(
            {"type": "feature", "status": "PLANNED"}, sw_schema, "features/x.md"
        )
        assert not is_unanchored_governance_article(
            {"type": "architecture", "stability": "Superseded"}, sw_schema, "architecture/x.md"
        )

    def test_check_file_health_emits_unanchored_governance_article(self, tmp_path: Path) -> None:
        _, wiki_root = _setup_wiki(tmp_path, profile="software", enforcement="balanced")
        arch = _article_content(doc_type="architecture", status="shipped", title="Arch")
        health = check_file_health(wiki_root, "architecture/a.md", arch)
        assert any("unanchored_governance_article" in w for w in health)

    def test_mcp_brain79_edit_never_reports_lint_ok_when_unanchored(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from brain79 import server

        project_root, wiki_root = _setup_wiki(tmp_path, profile="software", enforcement="balanced")
        monkeypatch.setenv("BRAIN79_PROJECT_ROOT", str(project_root))

        anchored = _article_content(
            doc_type="architecture",
            status="shipped",
            applies_to=["src/app.py"],
            title="Core arch",
        )
        write_article("architecture/core.md", anchored, wiki_root=wiki_root)

        resp = server.brain79_edit(
            path="architecture/core.md",
            edits=[{"old_text": "applies_to:\n  - src/app.py\n", "new_text": ""}],
        )
        assert "unanchored_governance_article" in resp
        assert "lint OK" not in resp
