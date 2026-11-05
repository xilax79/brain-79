"""Comprehensive test suite for Phase 6.5: Session knowledge triage,
zero-code research persistence guard, and handoff ergonomics.
"""

from pathlib import Path
from typing import Any
import pytest

from brain79.core.curate import analyze_wiki_state, prepare_curation_guide
from brain79.core.handoff import (
    _is_noop_placeholder,
    write_handoff,
)
from brain79.core.drift import find_matching_workspace_files
from brain79.core.init_project import init_project
from brain79.core.locks import normalize_posix_input, normalize_wiki_rel_path
from brain79.core.session_commit import commit_session
from brain79.core.wiki import read_article, write_article


def test_normalize_wiki_rel_path_strips_brain79_prefix() -> None:
    """normalize_wiki_rel_path removes redundant leading .brain-79/ or ./.brain-79/ or /.brain-79/."""
    assert normalize_wiki_rel_path(".brain-79/topics/libertadores.md") == "topics/libertadores.md"
    assert normalize_wiki_rel_path("./.brain-79/features/auth.md") == "features/auth.md"
    assert normalize_wiki_rel_path(r".brain-79\decisions\adr-001.md") == "decisions/adr-001.md"
    assert normalize_wiki_rel_path(r".\.brain-79\architecture\overview.md") == "architecture/overview.md"
    assert normalize_wiki_rel_path("/.brain-79/topics/copa.md") == "topics/copa.md"
    assert normalize_wiki_rel_path(".brain-79") == ""
    assert normalize_wiki_rel_path("topics/libertadores.md") == "topics/libertadores.md"
    assert normalize_wiki_rel_path("INDEX.md") == "INDEX.md"


def test_normalize_posix_input_preserves_workspace_brain79_paths(tmp_path: Path) -> None:
    """normalize_posix_input preserves .brain-79/ in applies_to workspace paths for drift detection."""
    assert normalize_posix_input(r".brain-79\SCHEMA.md") == ".brain-79/SCHEMA.md"
    assert normalize_posix_input(".brain-79/SCHEMA.md") == ".brain-79/SCHEMA.md"

    # Verify drift detection matches .brain-79/SCHEMA.md correctly
    init_project(tmp_path, profile="general", install_git_hooks_flag=False)
    matched = find_matching_workspace_files([".brain-79/SCHEMA.md"], tmp_path)
    assert (tmp_path / ".brain-79" / "SCHEMA.md") in matched


def test_redundant_brain79_prefix_tolerated_in_wiki_read_write(tmp_path: Path) -> None:
    """write_article and read_article seamlessly handle redundant .brain-79/ prefixes."""
    init_project(tmp_path, profile="general", install_git_hooks_flag=False)
    wiki_root = tmp_path / ".brain-79"

    article_content = (
        "---\n"
        "type: topic\n"
        "summary: research notes on copa libertadores 2026\n"
        "---\n"
        "# Copa libertadores 2026\n\n"
        "## Overview\n\n"
        "Research findings and odds analysis.\n\n"
        "[← Volver al Índice](../INDEX.md)\n"
    )

    # Write using .brain-79/ prefix
    rel_path = write_article(".brain-79/topics/copa-libertadores.md", article_content, wiki_root=wiki_root)
    assert "topics/copa-libertadores.md" in rel_path
    assert (wiki_root / "topics" / "copa-libertadores.md").is_file()

    # Read using ./.brain-79/ prefix
    read_back = read_article("./.brain-79/topics/copa-libertadores.md", wiki_root=wiki_root)
    assert "Research findings and odds analysis." in read_back

    # Finding 2 check: check_file_health must not falsely report broken link when given .brain-79/ prefix
    from brain79.core.wiki import check_file_health
    warnings = check_file_health(wiki_root, ".brain-79/topics/copa-libertadores.md", article_content)
    assert not any("Broken local link" in w for w in warnings)


def test_is_noop_placeholder_detection() -> None:
    """_is_noop_placeholder identifies conversational filler and empty placeholders."""
    # Exact values (case-insensitive, trailing punctuation stripped)
    assert _is_noop_placeholder("Ninguna.")
    assert _is_noop_placeholder("ninguna")
    assert _is_noop_placeholder("Ninguno.")
    assert _is_noop_placeholder("nada")
    assert _is_noop_placeholder("None.")
    assert _is_noop_placeholder("none")
    assert _is_noop_placeholder("N/A")
    assert _is_noop_placeholder("n/a.")
    assert _is_noop_placeholder("sin pendientes")
    assert _is_noop_placeholder("Sin tareas pendientes.")
    assert _is_noop_placeholder("no pending tasks")
    assert _is_noop_placeholder("no pending work.")
    assert _is_noop_placeholder("no open questions")
    assert _is_noop_placeholder("sin preguntas abiertas.")

    # Generic 'wait for user' filler patterns
    assert _is_noop_placeholder("Atender la próxima tarea técnica o de investigación del usuario.")
    assert _is_noop_placeholder("Atender la proxima tarea del usuario")
    assert _is_noop_placeholder("Continuar según la siguiente solicitud del usuario.")
    assert _is_noop_placeholder("Continuar segun la siguiente instrucción.")
    assert _is_noop_placeholder("Esperar la siguiente instrucción.")
    assert _is_noop_placeholder("Await next user request.")
    assert _is_noop_placeholder("Wait for next user instruction.")

    # Meaningful work should NOT be flagged as placeholder
    assert not _is_noop_placeholder("Implement payment webhook retry handler")
    assert not _is_noop_placeholder("Investigate penalty shootout statistics in 2024 final")
    assert not _is_noop_placeholder("Decide between SQLite WAL and Postgres for multi-tenant")


def test_unpersisted_research_guard_blocks_closing_without_articles(tmp_path: Path) -> None:
    """A research session in a project with SCHEMA.md cannot close if zero wiki articles exist."""
    init_project(tmp_path, profile="general", install_git_hooks_flag=False)
    wiki_root = tmp_path / ".brain-79"

    # Calling write_handoff on a fresh research session with 0 content articles
    with pytest.raises(ValueError) as excinfo:
        write_handoff(
            session_type="research",
            summary="Investigación de Copa Libertadores 2026.",
            decisions=["Decisión analítica clave."],
            boot_instruction="Sesión consultiva finalizada. Continuar según la siguiente solicitud.",
            wiki_root=wiki_root,
        )

    err_msg = str(excinfo.value)
    assert "Unpersisted 'research' session blocked" in err_msg
    assert "no permanent wiki articles were created or updated" in err_msg
    assert "`topics/`" in err_msg
    assert "`decisions/`" in err_msg
    assert "brain79_session_commit" in err_msg


def test_unpersisted_research_guard_blocks_justification_bypass(tmp_path: Path) -> None:
    """Explicit wiki_deviation_justification MUST NOT bypass the unpersisted research guard."""
    init_project(tmp_path, profile="general", install_git_hooks_flag=False)
    wiki_root = tmp_path / ".brain-79"

    with pytest.raises(ValueError) as excinfo:
        write_handoff(
            session_type="research",
            summary="Exploración preliminar sin hallazgos.",
            boot_instruction="Sesión consultiva finalizada sin tareas pendientes.",
            wiki_deviation_justification="La investigación fue inconclusa por falta de fuentes y no produjo conocimiento duradero.",
            wiki_root=wiki_root,
        )
    err = str(excinfo.value)
    assert "Unpersisted 'research' session blocked" in err
    assert "You cannot bypass this with wiki_deviation_justification" in err


def test_unpersisted_research_guard_blocks_pending_promotion_bypass(tmp_path: Path) -> None:
    """knowledge_pending_promotion alone MUST NOT bypass the unpersisted research guard."""
    init_project(tmp_path, profile="general", install_git_hooks_flag=False)
    wiki_root = tmp_path / ".brain-79"

    with pytest.raises(ValueError) as excinfo:
        write_handoff(
            session_type="research",
            summary="Research preliminar con notas para promover luego.",
            knowledge_pending_promotion=["Notas de fixture 2026 pendientes de estructurar."],
            boot_instruction="Sesión finalizada. Continuar con la siguiente solicitud.",
            wiki_root=wiki_root,
        )
    err = str(excinfo.value)
    assert "Unpersisted 'research' session blocked" in err
    assert "A 'research' session MUST persist its findings" in err


def test_software_profile_supports_topics_and_flexible_h2(tmp_path: Path) -> None:
    """Software profile must support topics/ (type: topic) and accept flexible H2 headers."""
    init_project(tmp_path, profile="software", install_git_hooks_flag=False)
    wiki_root = tmp_path / ".brain-79"

    topic_content = (
        "---\n"
        "type: topic\n"
        "summary: Comparative benchmark of serialization formats\n"
        "status: active\n"
        "last_updated: 2026-11-05\n"
        "---\n\n"
        "# Serialization benchmark\n\n"
        "## Benchmark results\n\n"
        "Protobuf is faster than JSON for high-throughput messaging.\n\n"
        "---\n\n"
        "[← Volver al Índice](../INDEX.md)\n"
    )

    write_article("topics/serialization-benchmark.md", topic_content, wiki_root=wiki_root)
    assert (wiki_root / "topics" / "serialization-benchmark.md").exists()

    # Now a research handoff must succeed because a topic was written
    rel_path = write_handoff(
        session_type="research",
        summary="Researched serialization formats in software project.",
        boot_instruction="Review topics/serialization-benchmark.md before choosing protocol.",
        completed_work=["Benchmarked JSON vs Protobuf"],
        wiki_root=wiki_root,
    )
    assert rel_path.startswith("handoffs/handoff-")


def test_zero_code_research_persistence_and_handoff_ergonomics(tmp_path: Path) -> None:
    """Validate zero-code research session triage and handoff ergonomics:
    1. Agent runs in non-git general profile.
    2. Agent attempts handoff with decisions, open_questions=['None.'], next_steps=['Await next user request.'].
    3. Engine blocks unpersisted research.
    4. Agent persists topic article via session_commit or write_article.
    5. Handoff succeeds seamlessly on first attempt:
       - decisions merged into completed_work
       - fillers filtered out
       - consultative closure accepted.
    """
    init_project(tmp_path, profile="general", install_git_hooks_flag=False)
    wiki_root = tmp_path / ".brain-79"

    handoff_params: dict[str, Any] = {
        "session_type": "research",
        "summary": "Competitive research on multi-tenant SaaS pricing models and tier structures.",
        "decisions": [
            "Adopt tiered usage-based model over flat-rate pricing for scalability."
        ],
        "boot_instruction": "Consult topics/saas-pricing-models.md when scoping billing infrastructure.",
        "open_questions": ["None."],
        "next_steps": [
            "Await next user instruction."
        ],
    }

    # Step 1: Must be rejected because research article has not been written
    with pytest.raises(ValueError) as excinfo:
        write_handoff(wiki_root=wiki_root, **handoff_params)
    assert "Unpersisted 'research' session blocked" in str(excinfo.value)

    # Step 2: Agent writes the research article into topics/
    topic_content = (
        "---\n"
        "type: topic\n"
        "summary: multi-tenant saas pricing models and tier structures\n"
        "---\n"
        "# SaaS pricing models\n\n"
        "## Market analysis and tier structures\n\n"
        "- Tier 1: Starter freemium with 10k events.\n"
        "- Tier 2: Pro usage-based with overage caps.\n"
    )
    write_article("topics/saas-pricing-models.md", topic_content, wiki_root=wiki_root)

    # Health check accepts natural structured H2 section in general profile without warnings
    from brain79.core.wiki import check_file_health
    warnings = check_file_health(wiki_root, "topics/saas-pricing-models.md", topic_content)
    assert warnings == []

    # Step 3: Now the exact same handoff succeeds on the first try
    rel_path = write_handoff(wiki_root=wiki_root, **handoff_params)
    assert rel_path.startswith("handoffs/handoff-")

    # Inspect the saved handoff content
    handoff_text = (wiki_root / rel_path).read_text(encoding="utf-8")
    # Verify decisions was merged into Completed Work
    assert "Adopt tiered usage-based model" in handoff_text
    # Verify filler from open_questions was NOT added to Gotchas
    assert "None." not in handoff_text
    # Verify filler from next_steps was NOT added to Pending Work
    assert "Await next user instruction" not in handoff_text
    # Verify pending work section is omitted because next_steps filler was filtered out
    assert "Trabajo pendiente" not in handoff_text


def test_session_commit_with_research_article_and_aliases(tmp_path: Path) -> None:
    """commit_session atomically writes topic article and handles alias handoff params."""
    init_project(tmp_path, profile="general", install_git_hooks_flag=False)
    wiki_root = tmp_path / ".brain-79"

    topic_content = (
        "---\n"
        "type: topic\n"
        "summary: investigación de mercado saas 2026\n"
        "---\n"
        "# Mercado saas 2026\n\n"
        "## Análisis de mercado\n\n"
        "Análisis de competidores y modelos de suscripción.\n"
    )

    handoff_dict = {
        "session_type": "research",
        "summary": "Investigación de modelos SaaS completada.",
        "decisions": ["Adoptar modelo de precios freemium con límite de seats."],
        "boot_instruction": "Sesión consultiva finalizada. Listo para la próxima solicitud.",
        "open_questions": ["Ninguna."],
        "next_steps": ["Esperar la siguiente instrucción."],
    }

    receipt = commit_session(
        wiki_root=wiki_root,
        writes=[{"path": "topics/mercado-saas.md", "content": topic_content}],
        handoff=handoff_dict,
        session_summary="Investigación de SaaS completada.",
    )

    assert receipt["success"] is True
    assert "topics/mercado-saas.md" in receipt["written_articles"]
    assert receipt["handoff_path"] is not None
    assert receipt["handoff_path"].startswith("handoffs/handoff-")
    assert receipt["health_status"] == "ok"
    assert receipt["warnings"] == []


def test_session_commit_concatenates_pending_aliases_without_loss(tmp_path: Path) -> None:
    """commit_session forwards all pending aliases (pending_work, next_steps, pending_tasks) without loss."""
    init_project(tmp_path, profile="general", install_git_hooks_flag=False)
    wiki_root = tmp_path / ".brain-79"

    topic_content = (
        "---\n"
        "type: topic\n"
        "summary: task pipeline\n"
        "---\n"
        "# Task pipeline\n\n"
        "## Overview\n\n"
        "Pipeline details.\n"
    )

    handoff_dict = {
        "session_type": "research",
        "summary": "Research with combined task aliases.",
        "pending_work": ["Task from pending_work"],
        "next_steps": ["Task from next_steps"],
        "pending_tasks": ["Task from pending_tasks"],
        "boot_instruction": "Continue with pipeline tasks.",
    }

    receipt = commit_session(
        wiki_root=wiki_root,
        writes=[{"path": "topics/pipeline.md", "content": topic_content}],
        handoff=handoff_dict,
    )

    assert receipt["success"] is True
    handoff_text = (wiki_root / receipt["handoff_path"]).read_text(encoding="utf-8")
    assert "Task from pending_work" in handoff_text
    assert "Task from next_steps" in handoff_text
    assert "Task from pending_tasks" in handoff_text

    # Also test placeholder in pending_work does not shadow real task in next_steps
    handoff_placeholder_dict = {
        "session_type": "research",
        "summary": "Placeholder test.",
        "pending_work": ["None."],
        "next_steps": ["Real unshadowed task"],
        "boot_instruction": "Resume real task.",
    }
    receipt2 = commit_session(
        wiki_root=wiki_root,
        writes=[{"path": "topics/pipeline2.md", "content": topic_content}],
        handoff=handoff_placeholder_dict,
    )
    handoff_text2 = (wiki_root / receipt2["handoff_path"]).read_text(encoding="utf-8")
    assert "Real unshadowed task" in handoff_text2
    assert "None." not in handoff_text2


def test_has_recent_wiki_writes_respects_previous_handoff_session_boundary(tmp_path: Path) -> None:
    """_has_recent_wiki_writes uses latest handoff as session boundary, avoiding blind 30m window."""
    import time
    init_project(tmp_path, profile="general", install_git_hooks_flag=False)
    wiki_root = tmp_path / ".brain-79"

    # Session 1: create topic and close session with handoff
    write_article(
        "topics/session-1.md",
        "---\ntype: topic\nsummary: session 1 notes\n---\n# Session 1\n\n## Overview\nNotes.",
        wiki_root=wiki_root,
    )
    h1 = write_handoff(
        session_type="general",
        summary="Session 1 completed.",
        boot_instruction="No pending tasks.",
        wiki_root=wiki_root,
    )
    assert h1.startswith("handoffs/")

    # Ensure timestamp advances
    time.sleep(0.05)

    # Session 2: no new articles written. A research handoff attempt must trigger unpersisted research guard!
    with pytest.raises(ValueError) as excinfo:
        write_handoff(
            session_type="research",
            summary="Session 2 unpersisted research attempt.",
            boot_instruction="Sesión finalizada.",
            wiki_root=wiki_root,
        )
    assert "Unpersisted 'research' session blocked" in str(excinfo.value)

    # Now Session 2 writes a new article
    time.sleep(0.05)
    write_article(
        "topics/session-2.md",
        "---\ntype: topic\nsummary: session 2 findings\n---\n# Session 2\n\n## Overview\nFindings.",
        wiki_root=wiki_root,
    )
    # Now it succeeds!
    h2 = write_handoff(
        session_type="research",
        summary="Session 2 completed.",
        boot_instruction="Sesión finalizada.",
        wiki_root=wiki_root,
    )
    assert h2.startswith("handoffs/")


def test_autofill_defaults_for_common_types(tmp_path: Path) -> None:
    """autofill_deterministic_fields populates sensible defaults (status, version, stability)."""
    from brain79.core.frontmatter import autofill_deterministic_fields

    # Topic default status: active
    meta_topic = autofill_deterministic_fields({"type": "topic", "summary": "test"}, "topics/test.md")
    assert meta_topic["status"] == "active"

    # Feature default status: planned, version: 0.1.0
    meta_feature = autofill_deterministic_fields({"type": "feature", "summary": "test"}, "features/test.md")
    assert meta_feature["status"] == "planned"
    assert meta_feature["version"] == "0.1.0"

    # Architecture default stability: experimental
    meta_arch = autofill_deterministic_fields({"type": "architecture", "summary": "test"}, "architecture/test.md")
    assert meta_arch["stability"] == "experimental"


def test_prepare_curation_guide_profile_aware_general(tmp_path: Path) -> None:
    """prepare_curation_guide outputs general profile directories and the Amnesia Test."""
    init_project(tmp_path, profile="general", install_git_hooks_flag=False)
    wiki_root = tmp_path / ".brain-79"

    # Create dummy .lock file to verify it is excluded from article count
    locks_dir = wiki_root / ".locks"
    locks_dir.mkdir(parents=True, exist_ok=True)
    (locks_dir / "index.lock.md").write_text("locked", encoding="utf-8")

    report = analyze_wiki_state(wiki_root)
    # INDEX.md and SCHEMA.md are present (2 files); .locks/index.lock.md must be excluded!
    assert report.article_count == 2  # .locks excluded!

    guide = prepare_curation_guide(wiki_root)
    assert "Active Schema Profile: `general`" in guide or "Active Schema Profile" in guide
    assert "`topics/`" in guide
    assert "`decisions/`" in guide
    assert "`context/`" in guide
    assert "The Amnesia Test" in guide
    assert "Type A" in guide
    assert "Type B" in guide
    assert "Type C" in guide


def test_prepare_curation_guide_profile_aware_software(tmp_path: Path) -> None:
    """prepare_curation_guide outputs software profile directories."""
    init_project(tmp_path, profile="software", install_git_hooks_flag=False)
    wiki_root = tmp_path / ".brain-79"

    guide = prepare_curation_guide(wiki_root)
    assert "Active Schema Profile: `software`" in guide or "Active Schema Profile" in guide
    assert "`features/`" in guide
    assert "`architecture/`" in guide
    assert "`decisions/`" in guide
    assert "`product/`" in guide
    assert "`topics/`" in guide  # Software profile now supports topics!


def test_server_tools_unpack_nested_proxy_args(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """FastMCP server tools unpack nested args dictionary passed by LLM proxy wrappers."""
    from brain79.config import set_project_root
    from brain79.server import brain79_read, brain79_session_commit, brain79_write

    init_project(tmp_path, profile="general", install_git_hooks_flag=False)
    monkeypatch.chdir(tmp_path)
    set_project_root(tmp_path)

    # 1. brain79_write with args wrapper
    write_res = brain79_write(
        args={
            "path": "topics/proxy-test.md",
            "content": "---\ntype: topic\nsummary: proxy test topic\nstatus: active\nlast_updated: 2026-11-05\n---\n# Proxy test\n\n## Overview\nTest.",
        }
    )
    assert "INDEX.md auto-synced" in write_res

    # 2. brain79_read with args wrapper
    read_res = brain79_read(args={"path": "topics/proxy-test.md"})
    assert "Proxy test" in read_res

    # 3. brain79_session_commit with double-nested proxy wrapper {"tool": "...", "args": {...}}
    nested_call = {
        "tool": "brain79_session_commit",
        "args": {
            "writes": [
                {
                    "path": "topics/nested-commit.md",
                    "content": "---\ntype: topic\nsummary: nested commit test\nstatus: active\nlast_updated: 2026-11-05\n---\n# Nested commit\n\n## Overview\nCommit payload.",
                }
            ],
            "handoff": {
                "session_type": "research",
                "summary": "Nested proxy call test.",
                "completed_work": ["Validated nested args unwrapping"],
                "boot_instruction": "Session completed.",
            },
        },
    }
    commit_res = brain79_session_commit(args=nested_call)
    assert "✅ Transaction Committed Successfully" in commit_res


def test_extended_handoff_aliases_merged_without_loss(tmp_path: Path) -> None:
    """open_loops/action_items/todo merge into pending_work, blockers/risks into gotchas, findings/key_decisions into completed_work."""
    init_project(tmp_path, profile="general", install_git_hooks_flag=False)
    wiki_root = tmp_path / ".brain-79"

    # Write a topic first to satisfy unpersisted research guard
    write_article(
        "topics/market-findings.md",
        "---\ntype: topic\nsummary: market findings\nstatus: active\nlast_updated: 2026-11-05\n---\n# Findings\n\n## Overview\nMarket analysis.",
        wiki_root=wiki_root,
    )

    handoff_dict = {
        "session_type": "research",
        "summary": "Market research session.",
        "findings": ["Finding 1: High customer demand"],
        "key_decisions": ["Decision 1: Focus on enterprise"],
        "open_loops": ["Loop 1: Follow up on survey"],
        "action_items": ["Action 1: Prepare report"],
        "todo": ["Todo 1: Share slides"],
        "risks_and_blockers": ["Risk 1: Survey fatigue"],
        "blockers": ["Blocker 1: Data access pending"],
        "risks": ["Risk 2: Timeline slippage"],
        "boot_instruction": "Review topics/market-findings.md before planning launch.",
    }

    from brain79.core.session_commit import commit_session
    receipt = commit_session(
        {"handoff": handoff_dict},
        wiki_root=wiki_root,
    )
    assert receipt["handoff_path"] is not None

    handoff_file = wiki_root / receipt["handoff_path"]
    content = handoff_file.read_text(encoding="utf-8")

    # Completed work contains findings and key decisions
    assert "Finding 1: High customer demand" in content
    assert "Decision 1: Focus on enterprise" in content

    # Pending work contains open loops, action items, todo
    assert "Loop 1: Follow up on survey" in content
    assert "Action 1: Prepare report" in content
    assert "Todo 1: Share slides" in content

    # Gotchas contains risks and blockers
    assert "Risk 1: Survey fatigue" in content
    assert "Blocker 1: Data access pending" in content
    assert "Risk 2: Timeline slippage" in content


def test_normalize_bullet_colons_sentence_case() -> None:
    """normalize_bullet_colons places colons outside bold and lowercases common verbs/adjectives while preserving proper nouns."""
    from brain79.core.frontmatter import normalize_bullet_colons

    raw = (
        "- **Palmeiras:** Llego a la final tras empatar 2-2\n"
        "- **Estudiantes de La Plata:** Logro romper la hegemonia\n"
        "- **Fundamento:** Mayor profundidad de plantel\n"
        "- **Finalistas:** Palmeiras y Boca Juniors\n"
        "- **Campeon proyectado:** Boca Juniors\n"
        "- **Plataforma:** Linux o macOS\n"
        "- **Standard:** ADR-015 compliant\n"
        "1. **Cold Start**: At the start of a session\n"
        "```markdown\n"
        "- **Inside Code:** Preserved\n"
        "```\n"
    )

    norm = normalize_bullet_colons(raw)

    assert "- **Palmeiras**: llego a la final tras empatar 2-2\n" in norm
    assert "- **Estudiantes de La Plata**: logro romper la hegemonia\n" in norm
    assert "- **Fundamento**: mayor profundidad de plantel\n" in norm
    assert "- **Finalistas**: Palmeiras y Boca Juniors\n" in norm
    assert "- **Campeon proyectado**: Boca Juniors\n" in norm
    assert "- **Plataforma**: Linux o macOS\n" in norm
    assert "- **Standard**: ADR-015 compliant\n" in norm
    assert "1. **Cold Start**: at the start of a session\n" in norm
    assert "- **Inside Code:** Preserved\n" in norm
