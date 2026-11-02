"""
Adversarial test suite for Phase 2 hardening (Defects 1 through 7).

Covers:
1. Defect 1: 1-Hop ADR Expansion must NEVER be truncated by top_candidates or [:effective_max].
   Linked ADRs must be inlined alongside the articles that reference them or preserved in the output.
2. Defect 2: Title & H2 weighting must extract actual H1 and H2 headers (since 'title' is stripped from frontmatter).
3. Defect 3: Relative Markdown links across subfolders (e.g., `../decisions/adr-001.md`) must be normalized
   relative to the referencing article's parent directory.
4. Defect 4: Short keywords (<=4 chars, e.g., 'auth', 'cli', 'api') must use regex word boundaries
   (\b{kw}\b) so 'auth' does NOT match 'authentic' or 'author'.
5. Defect 5: Task mentioning a file path (e.g. task="fix bug in src/auth/jwt.py") must activate Signal 1
   even when paths is not explicitly passed.
6. Defect 6: orient(wiki_root=custom) and rank_context_articles(wiki_root=custom) must respect custom wiki_root
   without falling back to global state or raising ValueError.
7. Defect 7: Symmetry and paths parameter in brain79_context (MCP and CLI).
"""

from pathlib import Path
import pytest

from brain79.config import set_project_root
from brain79.core.context import rank_context_articles
from brain79.core.frontmatter import clear_schema_cache
from brain79.core.init_project import init_project
from brain79.core.navigation import extract_graph_metadata
from brain79.core.orient import orient
from brain79.core.wiki import write_article
from brain79.server import brain79_context


@pytest.fixture
def adversarial_wiki(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    clear_schema_cache()
    project_root = tmp_path / "project"
    project_root.mkdir()
    wiki_root = project_root / ".brain-79"
    monkeypatch.chdir(project_root)
    monkeypatch.setenv("BRAIN79_WIKI_PATH", str(wiki_root))
    set_project_root(project_root)
    init_project(project_root=project_root, profile="software")
    clear_schema_cache()
    return wiki_root


def test_defect_1_adr_expansion_never_truncated_by_effective_max(adversarial_wiki: Path) -> None:
    """Defect 1: When 4 articles match paths/keywords, a 1-hop linked ADR MUST still appear in orient() and context."""
    # Write an accepted ADR
    write_article(
        "decisions/adr-042-security.md",
        """---
type: decision
summary: Strict token validation protocol
status: accepted
date: 2026-11-02
deciders: [security]
last_updated: 2026-11-02
---

# ADR-042 — Security Mandate
All auth tokens must be signed with RS256.
""",
    )

    # Write 4 features that match the query
    for i in range(1, 5):
        related_line = "related:\n  - decisions/adr-042-security.md" if i == 1 else ""
        write_article(
            f"features/auth-part{i}.md",
            f"""---
type: feature
summary: Authentication subsystem part {i}
status: shipped
version: 1.0.0
last_updated: 2026-11-02
{related_line}
---

# Feature — Auth Subsystem {i}
Handles authentication flow step {i}.
""",
        )

    # Call orient with max_articles=4
    res = orient(task="authentication flow step", max_articles=4)
    # The governing ADR-042 MUST be present in the output, not dropped as a 5th item!
    assert "decisions/adr-042-security.md" in res
    assert "All auth tokens must be signed with RS256" in res


def test_defect_2_h1_and_h2_weighting_works_without_frontmatter_title(adversarial_wiki: Path) -> None:
    """Defect 2: Article with keyword in # H1 or ## H2 must outrank an article that only mentions it once in body."""
    # Article A: keyword 'encryption' only in H1 and H2
    write_article(
        "architecture/crypto.md",
        """---
type: architecture
summary: Core cryptography overview
stability: stable
last_updated: 2026-11-02
---

# Architecture — Encryption Core

## Symmetric Encryption
Details about algorithms.
""",
    )

    # Article B: keyword 'encryption' mentioned in the body
    write_article(
        "features/storage.md",
        """---
type: feature
summary: Local database storage
status: shipped
version: 1.0.0
last_updated: 2026-11-02
---

# Feature — Local Storage
We store data securely using encryption on the device.
""",
    )

    ranked = rank_context_articles(task="encryption", top_n=2)
    assert len(ranked) >= 2
    # Article A (in H1 & H2) MUST have a strictly higher score than Article B
    assert str(ranked[0][1].relative_to(adversarial_wiki)) == "architecture/crypto.md"


def test_defect_3_relative_markdown_links_normalized_from_subfolder(adversarial_wiki: Path) -> None:
    """Defect 3: Markdown link `../decisions/adr-001.md` inside `features/auth.md` must resolve to `decisions/adr-001.md`."""
    content = """---
type: feature
summary: Subfolder test article
status: shipped
version: 1.0.0
last_updated: 2026-11-02
---

# Feature — Auth
See governing decision in [ADR-001](../decisions/adr-001-hybrid-cli.md).
"""
    gm = extract_graph_metadata(content, rel_path="features/auth.md")
    # Must be normalized to decisions/adr-001-hybrid-cli.md without leading ../
    assert "decisions/adr-001-hybrid-cli.md" in gm.get("outgoing_links", [])
    assert not any(link.startswith("../") for link in gm.get("outgoing_links", []))


def test_defect_4_word_boundary_for_short_keywords(adversarial_wiki: Path) -> None:
    """Defect 4: Searching 'auth' must NOT match 'author' or 'authentic'."""
    write_article(
        "features/publishing.md",
        """---
type: feature
summary: Author management and authentic documents
status: shipped
version: 1.0.0
last_updated: 2026-11-02
---

# Feature — Publishing
Manage authors and verify authentic books.
""",
    )

    ranked = rank_context_articles(task="auth", top_n=2)
    # publishing.md should have 0 hits for 'auth'
    assert not any("features/publishing.md" in str(p) for _, p, _ in ranked)


def test_defect_5_task_mentioning_file_path_activates_signal_1(adversarial_wiki: Path) -> None:
    """Defect 5: Task mentioning a path (e.g. 'Fix bug in src/auth/jwt.py') activates Signal 1 without paths arg."""
    write_article(
        "architecture/token-spec.md",
        """---
type: architecture
summary: Token generation specification
stability: stable
last_updated: 2026-11-02
applies_to:
  - "src/auth/jwt.py"
---

# Architecture — Token Spec
Token details.
""",
    )

    # User passes task containing the file path, but paths=None
    ranked = rank_context_articles(task="Fix bug in src/auth/jwt.py", paths=None, top_n=2)
    assert len(ranked) >= 1
    assert str(ranked[0][1].relative_to(adversarial_wiki)) == "architecture/token-spec.md"
    assert any("path:" in reason for reason in ranked[0][2])


def test_defect_6_explicit_wiki_root_propagation(tmp_path: Path) -> None:
    """Defect 6: Calling orient(wiki_root=custom) on a different directory without setting env var must not fail."""
    custom_project = tmp_path / "custom_project"
    custom_project.mkdir()
    custom_wiki = custom_project / ".brain-79"
    init_project(project_root=custom_project, profile="software")

    write_article_custom = custom_wiki / "features/custom.md"
    write_article_custom.parent.mkdir(parents=True, exist_ok=True)
    write_article_custom.write_text(
        """---
type: feature
summary: Custom feature
status: shipped
version: 1.0.0
last_updated: 2026-11-02
---

# Feature — Custom
Custom feature description.
""",
        encoding="utf-8",
    )

    # orient with explicit wiki_root
    res = orient(task="custom feature", wiki_root=custom_wiki)
    assert "features/custom.md" in res
    assert "Custom feature description" in res


def test_defect_7_symmetry_and_paths_in_brain79_context() -> None:
    """Defect 7: brain79_context MCP tool must accept paths and dispatch command must support --paths."""
    from brain79.cli.dispatch import dispatch_cmd

    # MCP tool signature check
    import inspect
    sig = inspect.signature(brain79_context)
    assert "paths" in sig.parameters

    # CLI context dispatch should parse --paths without error
    # (running against current wiki with empty result is fine, code 0 is expected)
    code = dispatch_cmd("context", ["test", "--paths", "src/brain79/core/orient.py"])
    assert code == 0
