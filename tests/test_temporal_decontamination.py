from pathlib import Path
import pytest

from brain79.core.lint_organizational import check_temporal_contamination


def test_temporal_contamination_detected_in_title(tmp_path: Path) -> None:
    w_root = tmp_path / ".brain-79"
    feat_dir = w_root / "features"
    feat_dir.mkdir(parents=True)

    article = feat_dir / "bad-feature.md"
    article.write_text(
        "---\n"
        "type: feature\n"
        "summary: timely delivery of component\n"
        "status: in_progress\n"
        "version: 0.1.0\n"
        "last_updated: 2026-11-13\n"
        "---\n\n"
        "# Feature — Component Engine (Phase 6.7)\n\n"
        "## Overview\n"
        "Timeless body.\n\n"
        "[← Volver al Índice](../INDEX.md)\n",
        encoding="utf-8",
    )

    issues = check_temporal_contamination(w_root)
    assert any(i.rule == "temporal_contamination_in_title" and "Phase 6.7" in i.message for i in issues)


def test_temporal_contamination_detected_in_summary(tmp_path: Path) -> None:
    w_root = tmp_path / ".brain-79"
    feat_dir = w_root / "features"
    feat_dir.mkdir(parents=True)

    article = feat_dir / "bad-summary.md"
    article.write_text(
        "---\n"
        "type: feature\n"
        "summary: specification for Phase 6.8 engine improvements\n"
        "status: planned\n"
        "version: 0.1.0\n"
        "last_updated: 2026-11-13\n"
        "---\n\n"
        "# Feature — Engine Improvements\n\n"
        "## Overview\n"
        "Timeless body.\n\n"
        "[← Volver al Índice](../INDEX.md)\n",
        encoding="utf-8",
    )

    issues = check_temporal_contamination(w_root)
    assert any(i.rule == "temporal_contamination_in_summary" and "Phase 6.8" in i.message for i in issues)


def test_temporal_contamination_detected_in_headings(tmp_path: Path) -> None:
    w_root = tmp_path / ".brain-79"
    arch_dir = w_root / "architecture"
    arch_dir.mkdir(parents=True)

    article = arch_dir / "bad-heading.md"
    article.write_text(
        "---\n"
        "type: architecture\n"
        "summary: system design and patterns\n"
        "stability: stable\n"
        "last_updated: 2026-11-13\n"
        "---\n\n"
        "# Architecture — Core Topology\n\n"
        "## Overview\n"
        "Overview.\n\n"
        "### Sprint 14 Deliverables\n"
        "Details.\n\n"
        "[← Volver al Índice](../INDEX.md)\n",
        encoding="utf-8",
    )

    issues = check_temporal_contamination(w_root)
    assert any(i.rule == "temporal_contamination_in_heading" and "Sprint 14" in i.message for i in issues)


def test_shipped_specification_title_flagged(tmp_path: Path) -> None:
    w_root = tmp_path / ".brain-79"
    feat_dir = w_root / "features"
    feat_dir.mkdir(parents=True)

    article = feat_dir / "shipped-spec.md"
    article.write_text(
        "---\n"
        "type: feature\n"
        "summary: core release engine\n"
        "status: shipped\n"
        "version: 1.0.0\n"
        "last_updated: 2026-11-13\n"
        "---\n\n"
        "# Feature — Versioning Specification\n\n"
        "## Overview\n"
        "Overview.\n\n"
        "[← Volver al Índice](../INDEX.md)\n",
        encoding="utf-8",
    )

    issues = check_temporal_contamination(w_root)
    assert any(i.rule == "shipped_specification_title" for i in issues)


def test_roadmap_articles_are_exempt(tmp_path: Path) -> None:
    w_root = tmp_path / ".brain-79"
    arch_dir = w_root / "architecture"
    arch_dir.mkdir(parents=True)

    roadmap = arch_dir / "roadmap-industrial-scale.md"
    roadmap.write_text(
        "---\n"
        "type: architecture\n"
        "summary: industrial roadmap covering core protocol phases (0-6.7) and adoption\n"
        "stability: stable\n"
        "last_updated: 2026-11-13\n"
        "---\n\n"
        "# Architecture — Industrial Roadmap\n\n"
        "## Completed foundation (Phases 0-6.7)\n"
        "- Phase 1\n"
        "- Phase 2\n\n"
        "### Phase 7: Multi-harness adoption\n"
        "Planned.\n\n"
        "[← Volver al Índice](../INDEX.md)\n",
        encoding="utf-8",
    )

    issues = check_temporal_contamination(w_root)
    assert issues == []


def test_immutable_audit_folders_are_exempt(tmp_path: Path) -> None:
    w_root = tmp_path / ".brain-79"
    dec_dir = w_root / "decisions"
    chan_dir = w_root / "changelog"
    dec_dir.mkdir(parents=True)
    chan_dir.mkdir(parents=True)

    adr = dec_dir / "adr-001.md"
    adr.write_text(
        "---\n"
        "type: decision\n"
        "summary: decision in Phase 2 for lock isolation\n"
        "status: accepted\n"
        "date: 2026-11-13\n"
        "deciders: [Architect]\n"
        "last_updated: 2026-11-13\n"
        "---\n\n"
        "# Decision — ADR-001: Architecture Decision (Phase 2)\n\n"
        "## Context\n"
        "Context.\n\n"
        "[← Volver al Índice](../INDEX.md)\n",
        encoding="utf-8",
    )

    chg = chan_dir / "v0-8-1.md"
    chg.write_text(
        "---\n"
        "type: changelog\n"
        "summary: release v0.8.1 completing Phase 6.8\n"
        "version: 0.8.1\n"
        "date: 2026-11-13\n"
        "last_updated: 2026-11-13\n"
        "---\n\n"
        "# Changelog — Release 0.8.1 (Phase 6.8)\n\n"
        "## Summary\n"
        "Notes.\n\n"
        "[← Volver al Índice](../INDEX.md)\n",
        encoding="utf-8",
    )

    issues = check_temporal_contamination(w_root)
    assert issues == []


def test_archived_articles_are_exempt(tmp_path: Path) -> None:
    w_root = tmp_path / ".brain-79"
    arch_dir = w_root / "architecture"
    arch_dir.mkdir(parents=True)

    backlog = arch_dir / "defect-backlog.md"
    backlog.write_text(
        "---\n"
        "type: architecture\n"
        "summary: historical defect backlog\n"
        "stability: archived\n"
        "last_updated: 2026-11-13\n"
        "---\n\n"
        "# Architecture — Defect Backlog\n\n"
        "## Historical Remediations (Phase 5.5 / 6)\n"
        "Archived notes.\n\n"
        "[← Volver al Índice](../INDEX.md)\n",
        encoding="utf-8",
    )

    issues = check_temporal_contamination(w_root)
    assert issues == []


def test_false_positive_protection_for_technical_phrases(tmp_path: Path) -> None:
    w_root = tmp_path / ".brain-79"
    feat_dir = w_root / "features"
    feat_dir.mkdir(parents=True)

    article = feat_dir / "transaction-engine.md"
    article.write_text(
        "---\n"
        "type: feature\n"
        "summary: transactional engine with 4-phase transaction pipeline\n"
        "status: shipped\n"
        "version: 1.0.0\n"
        "last_updated: 2026-11-13\n"
        "---\n\n"
        "# Feature — Two-Phase Commit and Transaction Engine\n\n"
        "## Overview\n"
        "Overview.\n\n"
        "## Subsystem Architecture\n"
        "The engine utilizes a 4-phase transaction pipeline.\n"
        "Handshake phase ensures mutual authentication.\n"
        "Phase-locked loops provide synchronization.\n"
        "Pass 1 and Pass 2 indexing execute in order.\n\n"
        "[← Volver al Índice](../INDEX.md)\n",
        encoding="utf-8",
    )

    issues = check_temporal_contamination(w_root)
    assert issues == []


def test_multilingual_detection(tmp_path: Path) -> None:
    w_root = tmp_path / ".brain-79"
    feat_dir = w_root / "features"
    feat_dir.mkdir(parents=True)

    article = feat_dir / "spanish-feature.md"
    article.write_text(
        "---\n"
        "type: feature\n"
        "summary: modulo de autenticacion\n"
        "status: in_progress\n"
        "version: 0.1.0\n"
        "last_updated: 2026-11-13\n"
        "---\n\n"
        "# Feature — Modulo Central (Fase 4)\n\n"
        "## Overview\n"
        "Texto.\n\n"
        "### Etapa 2 de Migración\n"
        "Detalles.\n\n"
        "[← Volver al Índice](../INDEX.md)\n",
        encoding="utf-8",
    )

    issues = check_temporal_contamination(w_root)
    assert any(i.rule == "temporal_contamination_in_title" and "Fase 4" in i.message for i in issues)
    assert any(i.rule == "temporal_contamination_in_heading" and "Etapa 2" in i.message for i in issues)
