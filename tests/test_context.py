from pathlib import Path
import subprocess
import time
from unittest.mock import MagicMock, patch

import pytest

from brain79.config import set_project_root
from brain79.core import context as context_ops
from brain79.server import brain79_context


@pytest.fixture
def temp_project(tmp_path: Path) -> Path:
    """Fixture providing a temporary project directory with a initialized wiki root."""
    set_project_root(tmp_path)
    wiki_root = tmp_path / ".brain-79"
    wiki_root.mkdir(parents=True, exist_ok=True)
    return tmp_path


def test_1_tfidf_asymmetry(temp_project: Path) -> None:
    """Test 1: Asimetría TF-IDF (bug vs jwt). Rare term jwt scores higher than frequent term bug."""
    wiki_root = temp_project / ".brain-79"

    # Create 10 docs, 9 contain 'bug', 1 contains 'jwt'
    for i in range(1, 10):
        (wiki_root / f"doc_{i}.md").write_text(
            f"This is document {i} with a bug report.", encoding="utf-8"
        )

    (wiki_root / "doc_jwt.md").write_text(
        "This is a jwt authentication token document with a bug.",
        encoding="utf-8",
    )

    report = context_ops.get_context("jwt bug", top_n=5)
    assert "# Context Retrieval Report" in report
    assert "doc_jwt.md" in report

    # Extract score lines
    lines = report.splitlines()
    jwt_score = None
    bug_doc_score = None

    for line in lines:
        if "`doc_jwt.md`" in line:
            score_part = line.split("(Score: ")[1].split(")")[0]
            jwt_score = float(score_part)
        elif "`doc_1.md`" in line:
            score_part = line.split("(Score: ")[1].split(")")[0]
            bug_doc_score = float(score_part)

    assert jwt_score is not None
    assert bug_doc_score is not None
    assert jwt_score > bug_doc_score


def test_sublinear_tf_damping(temp_project: Path) -> None:
    """CRIT-1: Sublinear TF damping prevents keyword repetition spamming."""
    wiki_root = temp_project / ".brain-79"

    # Single match doc
    (wiki_root / "single.md").write_text("auth system", encoding="utf-8")
    # Spam 100 matches doc
    (wiki_root / "spam.md").write_text(" ".join(["auth"] * 100), encoding="utf-8")

    report = context_ops.get_context("auth", top_n=2)

    score_single = None
    score_spam = None

    for line in report.splitlines():
        if "`single.md`" in line:
            score_single = float(line.split("(Score: ")[1].split(")")[0])
        elif "`spam.md`" in line:
            score_spam = float(line.split("(Score: ")[1].split(")")[0])

    assert score_single is not None
    assert score_spam is not None
    # Sublinear: 100 matches score ratio should be around 5.6x, NOT 100x
    assert score_spam < (score_single * 10.0)


def test_accented_spanish_stopwords() -> None:
    """CRIT-3 / NIT-1: Accented Spanish stop words are properly filtered."""
    kws = context_ops.extract_keywords("más allí el sistema está esté estés estén")
    assert "más" not in kws
    assert "allí" not in kws
    assert "está" not in kws
    assert "esté" not in kws
    assert "estés" not in kws
    assert "estén" not in kws
    assert "sistema" in kws


def test_2_boundary_heuristics() -> None:
    """Test 2: Boundary heuristic short vs long tokens."""
    kws = context_ops.extract_keywords("v2 auth architecture")
    assert "v2" not in kws  # len 2 removed
    assert "auth" in kws  # len 4 alnum
    assert "architecture" in kws  # len > 4

    snapshot = [Path("/fake/auth_doc.md")]

    with patch.object(
        Path,
        "read_text",
        return_value="auth authentic author authentication",
    ):
        matches_short = context_ops._search_keyword_python("auth", snapshot)
        assert matches_short.get(snapshot[0]) == 1

    with patch.object(
        Path,
        "read_text",
        return_value="architectures architectures2 architect",
    ):
        matches_long = context_ops._search_keyword_python("architecture", snapshot)
        assert matches_long.get(snapshot[0]) == 2


def test_3_nfkc_normalization_and_deduplication() -> None:
    """Test 3: Normalización NFKC y deduplicación."""
    kws = context_ops.extract_keywords("AUTH auth \ufb01x")
    assert kws == ["auth"]


def test_4_empty_extraction_fallback(temp_project: Path) -> None:
    """Test 4: Extracción vacía/Fallback when query contains only stop-words."""
    wiki_root = temp_project / ".brain-79"
    (wiki_root / "INDEX.md").write_text("# Index", encoding="utf-8")
    (wiki_root / "doc1.md").write_text("# Doc 1", encoding="utf-8")

    with patch("brain79.core.context.ThreadPoolExecutor") as mock_executor:
        report = context_ops.get_context("the in it")
        assert "⚠️ FALLBACK MODE" in report
        assert "Keywords detectados: (ninguno)" in report
        assert "INDEX.md" in report
        mock_executor.assert_not_called()


def test_5_empty_wiki(temp_project: Path) -> None:
    """Test 5: N == 0 (wiki vacía)."""
    result = context_ops.get_context("auth")
    assert result == "No hay artículos válidos en la wiki para analizar."


def test_6_file_race_condition(temp_project: Path) -> None:
    """Test 6: File race (file deleted mid-search)."""
    wiki_root = temp_project / ".brain-79"
    doc = wiki_root / "temp_doc.md"
    doc.write_text("auth system", encoding="utf-8")

    snapshot = context_ops.get_wiki_snapshot()
    assert doc.resolve() in snapshot

    doc.unlink()

    matches = context_ops._search_keyword_python("auth", snapshot)
    assert doc.resolve() not in matches


def test_7_timeout_cleanup() -> None:
    """Test 7: TimeoutExpired kill-signal cleanup in ripgrep execution."""
    tmp_path = Path("/tmp/fake_tmp.txt")

    with patch(
        "subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd=["rg"], timeout=10),
    ):
        matches = context_ops._search_keyword_rg("rg", "auth", tmp_path)
        assert matches == {}


def test_8_score_truncation_and_top_n_defaults(
    temp_project: Path,
) -> None:
    """Test 8: Truncamiento score < 1.0 y top_n defaults (top_n <= 0 evalúa a 3)."""
    wiki_root = temp_project / ".brain-79"

    for i in range(1, 6):
        (wiki_root / f"doc_{i}.md").write_text(
            "authentication auth token", encoding="utf-8"
        )

    report = context_ops.get_context("auth", top_n=0)
    lines = [
        line
        for line in report.splitlines()
        if line.startswith("1. ")
        or line.startswith("2. ")
        or line.startswith("3. ")
        or line.startswith("4. ")
    ]
    assert len(lines) == 3


def test_9_deterministic_tie_breaking(temp_project: Path) -> None:
    """Test 9: Tie-breaking determinista (score, path vs mtime_ns, path)."""
    wiki_root = temp_project / ".brain-79"
    (wiki_root / "b_doc.md").write_text("auth system", encoding="utf-8")
    (wiki_root / "a_doc.md").write_text("auth system", encoding="utf-8")

    report = context_ops.get_context("auth", top_n=2)
    pos_a = report.find("a_doc.md")
    pos_b = report.find("b_doc.md")
    assert pos_a != -1 and pos_b != -1
    assert pos_a < pos_b

    report_fb = context_ops.get_context("the in it", top_n=2)
    pos_a_fb = report_fb.find("a_doc.md")
    pos_b_fb = report_fb.find("b_doc.md")
    assert pos_a_fb != -1 and pos_b_fb != -1
    assert pos_a_fb < pos_b_fb


def test_10_mcp_handler_response_type(temp_project: Path) -> None:
    """Test 10: MCP Handler Response (Validación string)."""
    wiki_root = temp_project / ".brain-79"
    (wiki_root / "doc.md").write_text("auth system", encoding="utf-8")

    response = brain79_context("auth")
    assert isinstance(response, str)
    assert "# Context Retrieval Report" in response


def test_11_json_parse_resilience() -> None:
    """Test 11: Resiliencia ante Excepciones de Parseo JSON."""
    fake_stdout = "\n".join(
        [
            "invalid json line",
            '{"type": "begin"}',
            '{"type": "match", "data": {}}',
            "{corrupted: json",
            '{"type": "end", "data": {"path": {"text": "/path/valid.md"}, "stats": {"matches": 5}}}',
            "",
        ]
    )

    mock_proc = MagicMock()
    mock_proc.stdout = fake_stdout

    tmp_file = Path("/tmp/dummy_test11.txt")
    tmp_file.write_text("/path/valid.md\n", encoding="utf-8")

    try:
        with patch("subprocess.run", return_value=mock_proc):
            matches = context_ops._search_keyword_rg("rg", "auth", tmp_file)
            assert len(matches) == 1
            assert matches[Path("/path/valid.md")] == 5
    finally:
        if tmp_file.exists():
            tmp_file.unlink()


def test_12_absolute_paths_and_raw_isolation(
    temp_project: Path,
) -> None:
    """Test 12: Rutas absolutas (resolve()) y aislamiento _raw/ y handoffs/."""
    wiki_root = temp_project / ".brain-79"
    (wiki_root / "features" / "auth.md").parent.mkdir(parents=True, exist_ok=True)
    (wiki_root / "_raw" / "sessions").mkdir(parents=True, exist_ok=True)
    (wiki_root / "handoffs").mkdir(parents=True, exist_ok=True)

    valid_doc = wiki_root / "features" / "auth.md"
    raw_doc = wiki_root / "_raw" / "sessions" / "raw1.md"
    handoff_doc = wiki_root / "handoffs" / "handoff-1.md"

    valid_doc.write_text("auth feature", encoding="utf-8")
    raw_doc.write_text("raw session auth", encoding="utf-8")
    handoff_doc.write_text("handoff auth", encoding="utf-8")

    snapshot = context_ops.get_wiki_snapshot()
    assert valid_doc.resolve() in snapshot
    assert raw_doc.resolve() not in snapshot
    assert handoff_doc.resolve() not in snapshot
    assert all(p.is_absolute() for p in snapshot)


def test_13_performance_arg_max_1000_files(
    temp_project: Path,
) -> None:
    """Test 13: Rendimiento con 1000 archivos reales ejecutando en < 10s."""
    wiki_root = temp_project / ".brain-79"
    articles_dir = wiki_root / "articles"
    articles_dir.mkdir(parents=True, exist_ok=True)

    for i in range(1000):
        content = f"Article {i} discussing authentication and database scaling."
        (articles_dir / f"art_{i}.md").write_text(content, encoding="utf-8")

    start_time = time.perf_counter()
    report = context_ops.get_context("authentication scaling", top_n=5)
    elapsed = time.perf_counter() - start_time

    assert "# Context Retrieval Report" in report
    assert elapsed < 10.0


def test_14_pure_python_fallback_monkeypatch(
    temp_project: Path,
) -> None:
    """Test 14: Comportamiento fallback de Python puro (Monkeypatch de shutil.which devolviendo None)."""
    wiki_root = temp_project / ".brain-79"
    (wiki_root / "auth.md").write_text("auth system login", encoding="utf-8")

    with patch("shutil.which", return_value=None):
        report = context_ops.get_context("auth system")
        assert "# Context Retrieval Report" in report
        assert "auth.md" in report
