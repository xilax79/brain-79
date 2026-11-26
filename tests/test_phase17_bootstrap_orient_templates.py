"""Phase 17 Stage 3 TDD tests: governance-complete bootstrap, clean orient/context, and template guidance (AC-1, AC-2)."""

from __future__ import annotations

import io
from pathlib import Path

import pytest

import brain79.config as config
from brain79.cli.dispatch import dispatch_cmd
from brain79.core.bootstrap import run_bootstrap
from brain79.core.context import rank_context_articles
from brain79.core.frontmatter import (
    ActiveSchema,
    GENERAL_LOCATION_TO_TYPE,
    GENERAL_PROFILE_SCHEMA,
    SOFTWARE_LOCATION_TO_TYPE,
    SOFTWARE_PROFILE_SCHEMA,
    ValidationError,
    generate_frontmatter_template,
)
from brain79.core.init_project import init_project
from brain79.core.orient import MAX_ORIENT_INLINE_CHARS, orient
from brain79.server import brain79_bootstrap, brain79_orient


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def _make_article(
    wiki_root: Path,
    rel_path: str,
    *,
    doc_type: str = "feature",
    summary: str = "Feature summary",
    status_line: str = "status: shipped\nversion: 1.0.0",
    applies_to: list[str] | None = None,
    body: str = "## Overview\nDetails here.\n",
) -> None:
    lines = [
        "---",
        f"type: {doc_type}",
        f"summary: {summary}",
    ]
    if status_line:
        lines.append(status_line)
    if applies_to:
        lines.append("applies_to:")
        for p in applies_to:
            lines.append(f"  - {p}")
    lines.extend([
        "last_updated: 2026-11-26",
        "---",
        "",
        f"# {rel_path}",
        "",
        body.rstrip(),
        "",
        "---",
        "",
        "[← Back to Index](../INDEX.md)",
        "",
    ])
    _write(wiki_root / rel_path, "\n".join(lines))


# =============================================================================
# AC-1: Profile-aware auto_map default, disjoint bootstrap examples, templates
# =============================================================================


class TestAC1BootstrapAndTemplates:
    def test_r1_1_auto_map_profile_defaults_and_opt_out(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # 1. Software profile: auto_map=None -> resolves to True
        sw_dir = tmp_path / "sw_repo"
        sw_dir.mkdir()
        init_project(sw_dir, profile="software", auto_git_init=False, install_git_hooks_flag=False)
        _write(sw_dir / "src" / "pkg" / "core.py", "def run(x: int) -> int:\n    return x\n")
        monkeypatch.setattr(config, "_project_root", sw_dir)

        core_out = run_bootstrap()
        assert "## Auto-mapped governance boundaries" in core_out

        mcp_out = brain79_bootstrap(force=True)
        assert "## Auto-mapped governance boundaries" in mcp_out

        buf = io.StringIO()
        monkeypatch.setattr("sys.stdout", buf)
        rc = dispatch_cmd("bootstrap", ["--force"])
        assert rc == 0
        assert "## Auto-mapped governance boundaries" in buf.getvalue()

        # Software profile explicit opt-out: auto_map=False / --no-auto-map
        opt_out_core = run_bootstrap(force=True, auto_map=False)
        assert "## Auto-mapped governance boundaries" not in opt_out_core

        buf2 = io.StringIO()
        monkeypatch.setattr("sys.stdout", buf2)
        rc2 = dispatch_cmd("bootstrap", ["--force", "--no-auto-map"])
        assert rc2 == 0
        assert "## Auto-mapped governance boundaries" not in buf2.getvalue()

        # 2. General profile: auto_map=None -> resolves to False
        gen_dir = tmp_path / "gen_repo"
        gen_dir.mkdir()
        init_project(gen_dir, profile="general", auto_git_init=False, install_git_hooks_flag=False)
        _write(gen_dir / "src" / "app.py", "def main(): pass\n")
        monkeypatch.setattr(config, "_project_root", gen_dir)

        gen_default = run_bootstrap()
        assert "## Auto-mapped governance boundaries" not in gen_default

        # Explicit --auto-map still works on general profile
        buf3 = io.StringIO()
        monkeypatch.setattr("sys.stdout", buf3)
        rc3 = dispatch_cmd("bootstrap", ["--force", "--auto-map"])
        assert rc3 == 0
        assert "## Auto-mapped governance boundaries" in buf3.getvalue()

    def test_r1_2_disjoint_bootstrap_examples_src_flat_and_empty(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Repo A: standard src/ + README.md + pyproject.toml
        repo_a = tmp_path / "repo_a"
        repo_a.mkdir()
        init_project(repo_a, profile="software", auto_git_init=False, install_git_hooks_flag=False)
        _write(repo_a / "README.md", "# Repo A\n")
        _write(repo_a / "pyproject.toml", '[project]\nname = "repo-a"\n')
        _write(repo_a / "src" / "billing" / "invoice.py", "TAX_RATE = 0.21\n")
        monkeypatch.setattr(config, "_project_root", repo_a)

        out_a = brain79_bootstrap()
        assert ".brain-79/features/*.md" in out_a
        assert "README.md" in out_a
        assert "src/**" not in out_a
        assert "allow_overlapping_governance: true" in out_a
        assert "pyproject.toml" in out_a
        # Sentence case check on overview.md summary example
        for line in out_a.splitlines():
            if line.strip().startswith("summary:"):
                val = line.split("summary:", 1)[1].strip()
                assert not val.istitle(), f"Title Case summary found: {val}"

        # Repo B: flat non-src repo, no README.md, no pyproject.toml
        repo_b = tmp_path / "repo_b"
        repo_b.mkdir()
        init_project(repo_b, profile="software", auto_git_init=False, install_git_hooks_flag=False)
        _write(repo_b / "app.py", "def start(): pass\n")
        monkeypatch.setattr(config, "_project_root", repo_b)

        out_b = brain79_bootstrap()
        assert ".brain-79/features/*.md" in out_b
        assert "src/**" not in out_b
        # Must not cite non-existent README.md or pyproject.toml in applies_to examples
        instructions_b = out_b.split("## Bootstrap Instructions", 1)[1]
        assert "README.md" not in instructions_b
        assert "pyproject.toml" not in instructions_b

        # Repo C: completely empty repo (total_code_files == 0) + force=True
        repo_c = tmp_path / "repo_c"
        repo_c.mkdir()
        init_project(repo_c, profile="software", auto_git_init=False, install_git_hooks_flag=False)
        monkeypatch.setattr(config, "_project_root", repo_c)

        out_c = brain79_bootstrap(force=True)
        assert "No source code modules detected" in out_c
        assert "allow_overlapping_governance: true" in out_c
        instructions_c = out_c.split("## Bootstrap Instructions", 1)[1]
        assert "src/**" not in instructions_c
        assert "README.md" not in instructions_c
        assert "pyproject.toml" not in instructions_c

    def test_r1_4_r1_5_frontmatter_template_and_authoring_guidance(self) -> None:
        sw_schema = ActiveSchema(
            profile="software",
            enforcement="strict",
            types=SOFTWARE_PROFILE_SCHEMA,
            location_to_type=SOFTWARE_LOCATION_TO_TYPE,
        )
        gen_schema = ActiveSchema(
            profile="general",
            enforcement="advisory",
            types=GENERAL_PROFILE_SCHEMA,
            location_to_type=GENERAL_LOCATION_TO_TYPE,
        )

        # Software profile includes applies_to placeholder on architecture & feature
        arch_tpl = generate_frontmatter_template("architecture", schema=sw_schema)
        feat_tpl = generate_frontmatter_template("feature", schema=sw_schema)
        assert "applies_to:" in arch_tpl
        assert "applies_to:" in feat_tpl

        # General profile does NOT inject applies_to
        topic_gen_tpl = generate_frontmatter_template("topic", schema=gen_schema)
        assert "applies_to:" not in topic_gen_tpl
        arch_gen_tpl = generate_frontmatter_template("architecture", schema=gen_schema)
        assert "applies_to:" not in arch_gen_tpl

        # Preserves existing ValidationError.format_user_message() format
        err = ValidationError(
            rule="missing_frontmatter",
            path="features/auth.md",
            message="Missing YAML frontmatter.",
            actionable="Add frontmatter.",
            target_type="feature",
        )
        formatted = err.format_user_message()
        assert "Missing YAML frontmatter." in formatted
        assert "Action: Add frontmatter." in formatted
        assert "Ready-to-paste frontmatter template for 'feature':" in formatted

        # Check packaged templates (SCHEMA.md, AGENTS.md)
        repo_root = Path(__file__).resolve().parent.parent
        schema_tpl = (repo_root / "src" / "brain79" / "templates" / "SCHEMA.md").read_text(encoding="utf-8")
        agents_tpl = (repo_root / "src" / "brain79" / "templates" / "AGENTS.md").read_text(encoding="utf-8")

        assert "applies_to:" in schema_tpl
        assert "parameter" in schema_tpl.lower() or "signature" in schema_tpl.lower()
        assert "constant" in schema_tpl.lower() or "threshold" in schema_tpl.lower()

        assert "signature" in agents_tpl.lower()
        assert "parameter" in agents_tpl.lower()
        assert "constant" in agents_tpl.lower() or "threshold" in agents_tpl.lower()


# =============================================================================
# AC-2: brain79_orient schema parity, slot-stealing fix, bounded reminder
# =============================================================================


class TestAC2OrientContextAndTemplates:
    def test_r1_3_orient_active_schema_summary_applies_to_parity(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Strict software wiki
        sw_strict = tmp_path / "sw_strict"
        sw_strict.mkdir()
        init_project(sw_strict, profile="software", auto_git_init=False, install_git_hooks_flag=False)
        monkeypatch.setattr(config, "_project_root", sw_strict)

        out_strict = brain79_orient()
        assert "## 📐 Active Schema Summary" in out_strict
        assert "applies_to" in out_strict
        assert "strict-required" in out_strict.lower() or "required under `enforcement: strict`" in out_strict.lower()

        # Balanced software wiki -> recommended, not strict-required
        schema_path = sw_strict / ".brain-79" / "SCHEMA.md"
        schema_path.write_text(
            schema_path.read_text(encoding="utf-8").replace("enforcement: strict", "enforcement: balanced"),
            encoding="utf-8",
        )
        out_balanced = orient(wiki_root=sw_strict / ".brain-79")
        assert "applies_to" in out_balanced
        assert "recommended" in out_balanced.lower()

    def test_r2_4_read_batch_paths_guidance_in_templates_and_orient(self) -> None:
        repo_root = Path(__file__).resolve().parent.parent
        agents_tpl = (repo_root / "src" / "brain79" / "templates" / "AGENTS.md").read_text(encoding="utf-8")
        skill_tpl = (repo_root / "src" / "brain79" / "templates" / "SKILL.md").read_text(encoding="utf-8")

        assert "brain79_read_batch(paths=" in agents_tpl
        assert "brain79_read_batch(paths=" in skill_tpl

    def test_r4_1_context_excludes_index_schema_and_prefers_active(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        proj = tmp_path / "proj"
        proj.mkdir()
        init_project(proj, profile="software", auto_git_init=False, install_git_hooks_flag=False)
        wiki_root = proj / ".brain-79"
        monkeypatch.setattr(config, "_project_root", proj)

        # Make INDEX.md and SCHEMA.md heavily match the query keywords
        _write(
            wiki_root / "INDEX.md",
            "---\ntype: navigation\nlast_updated: 2026-11-26\n---\n\n# Project index\n\n"
            "pricing pricing pricing late fee rules\n",
        )
        schema_file = wiki_root / "SCHEMA.md"
        schema_file.write_text(
            schema_file.read_text(encoding="utf-8") + "\n<!-- pricing late fee rules pricing -->\n",
            encoding="utf-8",
        )

        # 6 active articles + 1 superseded article
        for i in range(1, 7):
            _make_article(
                wiki_root,
                f"features/mod-{i}.md",
                doc_type="feature",
                summary=f"Pricing and late fee module {i}",
                status_line="status: shipped\nversion: 1.0.0",
                applies_to=[f"src/mod_{i}.py"],
                body=f"## Overview\nHandles pricing and late fee rules for module {i}.\n",
            )
            _write(proj / "src" / f"mod_{i}.py", f"FEE_{i} = {i}\n")

        _make_article(
            wiki_root,
            "features/old-pricing.md",
            doc_type="feature",
            summary="Superseded pricing and late fee rules",
            status_line="status: superseded\nversion: 0.1.0",
            body="## Overview\npricing late fee rules pricing late fee rules pricing.\n",
        )

        # 1. rank_context_articles must exclude INDEX.md and SCHEMA.md BEFORE top_n truncation
        ranked = rank_context_articles(task="review pricing and late fee rules", top_n=4, wiki_root=wiki_root)
        ranked_rels = [p.relative_to(wiki_root).as_posix() for _, p, _ in ranked]
        assert "INDEX.md" not in ranked_rels
        assert "SCHEMA.md" not in ranked_rels
        assert len(ranked_rels) == 4
        assert "features/old-pricing.md" not in ranked_rels

        # 2. orient(task=...) inlines up to max_articles active articles and appends bounded reminder
        out = orient(task="review pricing and late fee rules", max_articles=4, wiki_root=wiki_root)
        assert "### === Article: SCHEMA.md ===" not in out
        assert "### === Article: INDEX.md ===" not in out
        assert "### === Article: features/old-pricing.md ===" not in out
        assert "brain79_read_batch(paths=[" in out
        assert "features/old-pricing.md" not in out.split("brain79_read_batch(paths=[", 1)[1]

    def test_r4_1_orient_large_wiki_reminder_capped_at_20(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        proj = tmp_path / "large_proj"
        proj.mkdir()
        init_project(proj, profile="software", auto_git_init=False, install_git_hooks_flag=False)
        wiki_root = proj / ".brain-79"
        monkeypatch.setattr(config, "_project_root", proj)

        # 25 active articles matching pricing
        for i in range(1, 26):
            _make_article(
                wiki_root,
                f"features/rule-{i:02d}.md",
                doc_type="feature",
                summary=f"Pricing rule {i:02d}",
                status_line="status: shipped\nversion: 1.0.0",
                applies_to=[f"src/rule_{i:02d}.py"],
                body=f"## Overview\nPricing rule {i:02d} details.\n",
            )
            _write(proj / "src" / f"rule_{i:02d}.py", f"RULE_{i} = {i}\n")

        out = orient(task="review pricing rules", max_articles=3, wiki_root=wiki_root)
        assert "brain79_read_batch(paths=[" in out
        # 25 active - 3 inlined = 22 remaining -> capped at 20 with (+2 more in INDEX.md)
        assert "(+2 more in INDEX.md)" in out
        reminder_line = [ln for ln in out.splitlines() if "brain79_read_batch(paths=[" in ln][0]
        paths_payload = reminder_line.split("brain79_read_batch(paths=[", 1)[1].split("])", 1)[0]
        assert paths_payload.count(".md") == 20
        assert len(out) <= MAX_ORIENT_INLINE_CHARS + 10_000
