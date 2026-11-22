"""Mechanical governance tests for external feature specifications (ADR-019).

Enforces repository-level specification invariants in CI:
1. One-way reference boundary: no .brain-79/ article may match specs/ in applies_to.
2. Freeze legacy phase design docs inside .brain-79/architecture/ (no new spec-like docs).
3. Validate specs/TEMPLATE.md structure, naming/spec_id conventions, uniqueness,
   R-X.Y <-> AC-* traceability, related_wiki/target_wiki existence, and implemented
   distillation closure gates.
"""

from __future__ import annotations

from pathlib import Path
import re

import pytest

from brain79.core.drift import WorkspaceIndex, match_applies_to_pattern
from brain79.core.frontmatter import parse_frontmatter

REPO_ROOT = Path(__file__).resolve().parent.parent
WIKI_ROOT = REPO_ROOT / ".brain-79"
SPECS_ROOT = REPO_ROOT / "specs"

ACTIVE_SPEC_STATUSES = frozenset({"draft", "approved", "in_progress"})
CLOSED_SPEC_STATUSES = frozenset({"implemented", "superseded", "abandoned"})
VALID_VERIFICATION_METHODS = frozenset({"test", "inspection", "demo", "ci"})

# Emptied on 2026-11-21 upon completing specs/archive/2026-11-legacy-design-doc-migration.md
LEGACY_ARCHITECTURE_SPECS_ALLOWLIST: frozenset[str] = frozenset()

REQUIRED_TEMPLATE_SECTIONS = (
    "## Problem statement and goal",
    "## Non-goals (out of scope)",
    "## Dependencies",
    "## Constraints and invariants",
    "## Open questions",
    "## Requirements (EARS)",
    "## Interface and error contract",
    "## Migration and rollout",
    "## Acceptance criteria (Given / When / Then)",
    "## Wiki impact map",
    "## Verification gate",
    "## Amendments",
    "## Wiki distillation checklist (post-implementation)",
)

PHASE_FILENAME_RE = re.compile(r"^phase-(\d{2,3})-([a-z0-9]+(?:-[a-z0-9]+)*)\.md$")
ADHOC_FILENAME_RE = re.compile(r"^(\d{4})-(\d{2})-([a-z0-9]+(?:-[a-z0-9]+)*)\.md$")
REQ_ID_RE = re.compile(r"(?m)^-\s+\*\*(R-\d+\.\d+)\*\*:")
AC_HEADING_RE = re.compile(r"(?m)^###\s+(AC-[\w.-]+)\b")
VERIFIES_RE = re.compile(r"(?m)^-\s+\*\*Verifies\*\*:\s*(.+)$")
METHOD_RE = re.compile(r"(?m)^-\s+\*\*Method\*\*:\s*`?(test|inspection|demo|ci)`?(?:\s+#.*)?$")
TEST_REF_RE = re.compile(r"(?m)^-\s+\*\*Test ref\*\*:\s*(.+)$")
REQ_TOKEN_RE = re.compile(r"\bR-\d+\.\d+\b")
SPEC_LIKE_BODY_RE = re.compile(r"(?m)^(?:###\s+R-\d+\.\d+\b|-\s+\*\*R-\d+\.\d+\*\*:|##\s+Acceptance criteria\b)")


def _extract_section(body: str, heading: str) -> str:
    """Return text under a specific ## H2 heading up to the next ## H2 heading."""
    pattern = re.compile(rf"(?m)^{re.escape(heading)}\s*$")
    match = pattern.search(body)
    if not match:
        return ""
    rest = body[match.end() :]
    next_h2 = re.search(r"(?m)^##\s+", rest)
    return rest[: next_h2.start()] if next_h2 else rest


def _extract_impact_map_targets(body: str) -> list[str]:
    """Extract target .brain-79/ article paths from the ## Wiki impact map table."""
    section = _extract_section(body, "## Wiki impact map")
    targets: list[str] = []
    for raw_line in section.splitlines():
        line = raw_line.strip()
        if not line.startswith("|") or not line.endswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 2:
            continue
        # Skip header and divider rows
        if cells[0].lower().startswith("new or modified") or set(cells[0]) <= {"-", ":", " "}:
            continue
        target_cell = cells[1].strip("` ")
        if not target_cell or "<" in target_cell or target_cell in {"—", "-"}:
            continue
        targets.append(target_cell)
    return targets


def _validate_filename_and_spec_id(spec_path: Path, spec_id: str) -> list[str]:
    """Verify deterministic naming and spec_id <-> filename correspondence."""
    fname = spec_path.name
    phase_m = PHASE_FILENAME_RE.match(fname)
    if phase_m:
        phase_num = int(phase_m.group(1))
        expected_id = f"SPEC-{phase_num:03d}"
        if spec_id != expected_id:
            return [f"{fname}: spec_id '{spec_id}' does not match phase filename (expected '{expected_id}')."]
        return []

    adhoc_m = ADHOC_FILENAME_RE.match(fname)
    if adhoc_m:
        yyyy, mm, slug = adhoc_m.groups()
        expected_id = f"SPEC-{yyyy}{mm}-{slug}"
        if spec_id != expected_id:
            return [f"{fname}: spec_id '{spec_id}' does not match ad-hoc filename (expected '{expected_id}')."]
        return []

    return [
        f"{fname}: invalid spec filename; expected 'phase-<NN>-<slug>.md' or 'YYYY-MM-<slug>.md'."
    ]


def _normalize_list(value: object) -> list[str]:
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    return []


def validate_spec_file(
    spec_path: Path,
    *,
    wiki_root: Path,
    repo_root: Path,
    is_archived: bool,
) -> list[str]:
    """Validate a single ADR-019 specification file and return a list of violations."""
    errors: list[str] = []
    content = spec_path.read_text(encoding="utf-8").replace("\r\n", "\n")

    if not content.startswith("---\n"):
        return [f"{spec_path.name}: missing YAML frontmatter."]

    meta, body = parse_frontmatter(content)
    meta = meta or {}

    for field in ("spec_id", "title", "status", "owner", "last_updated", "related_wiki"):
        if not meta.get(field):
            errors.append(f"{spec_path.name}: missing required frontmatter field '{field}'.")

    spec_id = str(meta.get("spec_id", "")).strip()
    if spec_id:
        errors.extend(_validate_filename_and_spec_id(spec_path, spec_id))

    status = str(meta.get("status", "")).strip().lower()
    if is_archived:
        if status not in CLOSED_SPEC_STATUSES:
            errors.append(
                f"{spec_path.name}: archived spec must have status in {sorted(CLOSED_SPEC_STATUSES)}, got '{status}'."
            )
    else:
        if status not in ACTIVE_SPEC_STATUSES:
            errors.append(
                f"{spec_path.name}: active spec in specs/ must have status in {sorted(ACTIVE_SPEC_STATUSES)}, "
                f"got '{status}' (closed specs must be moved to specs/archive/)."
            )

    # related_wiki: must always be relative to .brain-79/ and exist
    for rel_str in _normalize_list(meta.get("related_wiki")):
        if rel_str.startswith(".brain-79/"):
            errors.append(
                f"{spec_path.name}: related_wiki entry '{rel_str}' must be relative to .brain-79/ (omit prefix)."
            )
        elif not (wiki_root / rel_str).is_file():
            errors.append(
                f"{spec_path.name}: related_wiki target '{rel_str}' does not exist under {wiki_root.name}/."
            )

    # target_wiki: relative format always checked; non-empty & existing required when status == implemented
    target_wiki = _normalize_list(meta.get("target_wiki"))
    if status == "implemented" and not target_wiki:
        errors.append(
            f"{spec_path.name}: implemented spec must declare at least one target_wiki entry to verify distillation."
        )
    for tgt_str in target_wiki:
        if tgt_str.startswith(".brain-79/"):
            errors.append(
                f"{spec_path.name}: target_wiki entry '{tgt_str}' must be relative to .brain-79/ (omit prefix)."
            )
        elif status == "implemented" and not (wiki_root / tgt_str).is_file():
            errors.append(
                f"{spec_path.name}: implemented spec target_wiki '{tgt_str}' does not exist under {wiki_root.name}/."
            )

    # Gate: approved/in_progress/implemented specs cannot retain unresolved open questions
    if status in {"approved", "in_progress", "implemented"}:
        open_q_section = _extract_section(body, "## Open questions")
        if re.search(r"(?m)^-\s+\[\s\]\s+", open_q_section):
            errors.append(
                f"{spec_path.name}: status '{status}' is forbidden while unresolved '- [ ]' items remain in ## Open questions."
            )

    # Requirements and Acceptance Criteria traceability
    req_ids = REQ_ID_RE.findall(body)
    if not req_ids:
        errors.append(f"{spec_path.name}: no requirements matching '- **R-X.Y**:' found.")
    req_id_set = set(req_ids)
    if len(req_ids) != len(req_id_set):
        errors.append(f"{spec_path.name}: duplicate requirement IDs detected.")

    ac_section = _extract_section(body, "## Acceptance criteria (Given / When / Then)")
    ac_matches = list(AC_HEADING_RE.finditer(ac_section))
    if not ac_matches:
        errors.append(f"{spec_path.name}: no acceptance criteria matching '### AC-*' found.")

    verified_reqs: set[str] = set()
    for idx, match in enumerate(ac_matches):
        ac_id = match.group(1)
        start = match.end()
        end = ac_matches[idx + 1].start() if idx + 1 < len(ac_matches) else len(ac_section)
        block = ac_section[start:end]

        verifies_match = VERIFIES_RE.search(block)
        if not verifies_match:
            errors.append(f"{spec_path.name}: {ac_id} is missing '- **Verifies**: R-X.Y'.")
        else:
            referenced = REQ_TOKEN_RE.findall(verifies_match.group(1))
            if not referenced:
                errors.append(f"{spec_path.name}: {ac_id} Verifies line contains no valid R-X.Y IDs.")
            for ref in referenced:
                if ref not in req_id_set:
                    errors.append(f"{spec_path.name}: {ac_id} references unknown requirement '{ref}'.")
                verified_reqs.add(ref)

        method_match = METHOD_RE.search(block)
        method_val = method_match.group(1) if method_match else ""
        if method_val not in VALID_VERIFICATION_METHODS:
            errors.append(
                f"{spec_path.name}: {ac_id} must declare '- **Method**:' in {sorted(VALID_VERIFICATION_METHODS)}."
            )

        # Closure gate for implemented specs: Test ref must be concrete (and exist on disk for Method: test)
        if status == "implemented":
            test_ref_match = TEST_REF_RE.search(block)
            if not test_ref_match:
                errors.append(f"{spec_path.name}: {ac_id} is missing '- **Test ref**:' required for implemented specs.")
            else:
                raw_ref = test_ref_match.group(1).split("#", 1)[0].strip()
                cleaned_ref = raw_ref.strip("` ")
                if not cleaned_ref or cleaned_ref.upper() == "TBD" or "<" in cleaned_ref:
                    errors.append(
                        f"{spec_path.name}: {ac_id} has unresolved Test ref '{cleaned_ref}' in implemented spec."
                    )
                elif method_val == "test":
                    # Support comma-separated node IDs (e.g., `tests/test_a.py::test_x`, `tests/test_b.py::test_y`)
                    for part in [p.strip("` ") for p in raw_ref.split(",") if p.strip("` ")]:
                        file_part = part.split("::", 1)[0].strip()
                        if not file_part or not (repo_root / file_part).is_file():
                            errors.append(
                                f"{spec_path.name}: {ac_id} Test ref file '{file_part}' does not exist."
                            )

    uncovered = sorted(req_id_set - verified_reqs)
    if uncovered:
        errors.append(f"{spec_path.name}: requirements not covered by any AC: {uncovered}.")

    # Closure gate for implemented specs: distillation checklist and wiki impact map
    if status == "implemented":
        checklist_section = _extract_section(body, "## Wiki distillation checklist (post-implementation)")
        if not re.search(r"(?m)^-\s+\[[xX]\]\s+", checklist_section):
            errors.append(
                f"{spec_path.name}: implemented spec must contain completed '- [x]' items in ## Wiki distillation checklist."
            )
        if re.search(r"(?m)^-\s+\[\s\]\s+", checklist_section):
            errors.append(
                f"{spec_path.name}: implemented spec still has unchecked '- [ ]' items in ## Wiki distillation checklist."
            )
        for impact_target in _extract_impact_map_targets(body):
            norm_tgt = impact_target.removeprefix(".brain-79/")
            if not (wiki_root / norm_tgt).is_file():
                errors.append(
                    f"{spec_path.name}: Wiki impact map target '{impact_target}' does not exist under {wiki_root.name}/."
                )

    return errors


def validate_specs_directory(specs_root: Path, *, wiki_root: Path, repo_root: Path) -> list[str]:
    """Validate all active and archived ADR-019 specs, allowed subdirs, and global spec_id uniqueness."""
    all_errors: list[str] = []
    seen_ids: dict[str, str] = {}

    for child in sorted(specs_root.iterdir()):
        if child.is_dir() and child.name != "archive":
            all_errors.append(
                f"Unexpected subdirectory 'specs/{child.name}/'; only 'specs/archive/' (and 'specs/archive/legacy/') are allowed."
            )

    archive_dir = specs_root / "archive"
    if archive_dir.is_dir():
        for child in sorted(archive_dir.iterdir()):
            if child.is_dir() and child.name != "legacy":
                all_errors.append(
                    f"Unexpected subdirectory 'specs/archive/{child.name}/'; only 'specs/archive/legacy/' is allowed."
                )

    candidates: list[tuple[Path, bool]] = []
    for spec_file in sorted(specs_root.glob("*.md")):
        if spec_file.name == "TEMPLATE.md":
            continue
        candidates.append((spec_file, False))

    if archive_dir.is_dir():
        for spec_file in sorted(archive_dir.glob("*.md")):
            candidates.append((spec_file, True))

    for spec_file, is_archived in candidates:
        all_errors.extend(
            validate_spec_file(spec_file, wiki_root=wiki_root, repo_root=repo_root, is_archived=is_archived)
        )
        content = spec_file.read_text(encoding="utf-8").replace("\r\n", "\n")
        if content.startswith("---\n"):
            meta, _ = parse_frontmatter(content)
            sid = str((meta or {}).get("spec_id", "")).strip()
            if sid:
                rel_name = spec_file.relative_to(specs_root).as_posix()
                if sid in seen_ids:
                    all_errors.append(f"Duplicate spec_id '{sid}' in '{seen_ids[sid]}' and '{rel_name}'.")
                else:
                    seen_ids[sid] = rel_name

    return all_errors


def _pattern_targets_specs(pattern: str, ws_index: WorkspaceIndex) -> bool:
    """Return True if an applies_to pattern explicitly or via broad glob matches specs/."""
    norm = re.sub(r"^(?:\./)+", "", pattern.strip().replace("\\", "/"))
    if (
        norm == "specs"
        or norm.startswith("specs/")
        or norm == ".brain-79/specs"
        or norm.startswith(".brain-79/specs/")
        or "/specs/" in norm
    ):
        return True
    probe_paths = ("specs/TEMPLATE.md", "specs/phase-13-probe.md", "specs/archive/phase-12-probe.md")
    return any(
        match_applies_to_pattern(
            pattern,
            probe,
            known_dirs=ws_index.known_dirs,
            known_wiki_prefixes=ws_index.known_wiki_prefixes,
        )
        for probe in probe_paths
    )


def test_wiki_applies_to_forbids_specs_directory() -> None:
    """No governed .brain-79/ article may match specs/ in applies_to (ADR-019 one-way boundary)."""
    ws_index = WorkspaceIndex.build(REPO_ROOT, WIKI_ROOT)
    violations: list[str] = []
    for md_file in sorted(WIKI_ROOT.rglob("*.md")):
        rel = md_file.relative_to(WIKI_ROOT)
        if rel.parts[0] in ("_raw", ".locks") or rel.as_posix() in ("INDEX.md", "SCHEMA.md"):
            continue
        content = md_file.read_text(encoding="utf-8").replace("\r\n", "\n")
        if not content.startswith("---\n"):
            continue
        meta, _ = parse_frontmatter(content)
        for pat in _normalize_list((meta or {}).get("applies_to")):
            if _pattern_targets_specs(pat, ws_index):
                violations.append(f"{rel.as_posix()}: applies_to pattern '{pat}' matches forbidden specs/ directory")
    assert not violations, "\n".join(violations)


def test_no_new_design_specs_in_living_wiki_dirs() -> None:
    """Prevent adding new phase/feature design specs inside living wiki directories."""
    violations: list[str] = []
    for folder in ("architecture", "features", "product", "topics"):
        target_dir = WIKI_ROOT / folder
        if not target_dir.is_dir():
            continue
        for md_file in sorted(target_dir.glob("*.md")):
            if folder == "architecture" and md_file.name in LEGACY_ARCHITECTURE_SPECS_ALLOWLIST:
                continue
            if md_file.name.endswith(("-design.md", "-spec.md")):
                violations.append(f"{folder}/{md_file.name}: forbidden spec/design filename inside .brain-79/{folder}/")
                continue
            content = md_file.read_text(encoding="utf-8").replace("\r\n", "\n")
            if SPEC_LIKE_BODY_RE.search(content):
                violations.append(
                    f"{folder}/{md_file.name}: contains specification markers (R-X.Y / Acceptance criteria); move to specs/"
                )
    assert not violations, "\n".join(violations)


def test_spec_template_exists_and_has_required_sections() -> None:
    """Verify specs/TEMPLATE.md exists and declares every normative ADR-019 section."""
    template_path = SPECS_ROOT / "TEMPLATE.md"
    assert template_path.is_file(), "specs/TEMPLATE.md is missing."
    content = template_path.read_text(encoding="utf-8")
    for heading in REQUIRED_TEMPLATE_SECTIONS:
        assert heading in content, f"specs/TEMPLATE.md is missing required section: {heading}"


def test_repository_specs_comply_with_adr_019() -> None:
    """Validate all active specs in specs/*.md and archived ADR-019 specs in specs/archive/*.md."""
    if not SPECS_ROOT.is_dir():
        pytest.skip("specs/ directory does not exist.")
    all_errors = validate_specs_directory(SPECS_ROOT, wiki_root=WIKI_ROOT, repo_root=REPO_ROOT)
    assert not all_errors, "\n".join(all_errors)


def _sample_spec_markdown(
    *,
    spec_id: str = "SPEC-013",
    status: str = "approved",
    related_wiki: str = "features/existing.md",
    target_wiki: str = "features/new-manual.md",
    open_q_checked: bool = True,
    test_ref: str = "TBD",
    checklist_checked: bool = False,
) -> str:
    q_box = "x" if open_q_checked else " "
    c_box = "x" if checklist_checked else " "
    return (
        "---\n"
        f"spec_id: {spec_id}\n"
        "title: Sample phase feature\n"
        "target_version: v0.14.0\n"
        f"status: {status}\n"
        "owner: maintainer\n"
        "last_updated: 2026-11-21\n"
        "related_wiki:\n"
        f"  - {related_wiki}\n"
        "target_wiki:\n"
        f"  - {target_wiki}\n"
        "---\n\n"
        f"# {spec_id} — Sample phase feature\n\n"
        "## Open questions\n\n"
        f"- [{q_box}] **Q-1**: design choice resolved\n\n"
        "## Requirements (EARS)\n\n"
        "- **R-1.1**: WHEN invoked, THE system SHALL emit deterministic output.\n"
        "- **R-1.2**: IF input is invalid, THEN THE system SHALL exit with code 2.\n\n"
        "## Acceptance criteria (Given / When / Then)\n\n"
        "### AC-1 — Happy path\n"
        "- **Verifies**: `R-1.1`\n"
        "- **Method**: `test`\n"
        f"- **Test ref**: `{test_ref}`\n"
        "- **Given**: valid repo\n"
        "- **When**: command runs\n"
        "- **Then**: deterministic output\n\n"
        "### AC-2 — Invalid input\n"
        "- **Verifies**: `R-1.2`\n"
        "- **Method**: `inspection`\n"
        f"- **Test ref**: `{test_ref}`\n"
        "- **Given**: invalid input\n"
        "- **When**: command runs\n"
        "- **Then**: exit code 2\n\n"
        "## Wiki impact map\n\n"
        "| New or modified code paths | Target `.brain-79/` article | Action (`create` / `update` / `verify`) |\n"
        "|---|---|---|\n"
        f"| `src/brain79/core/sample.py` | `{target_wiki}` | `create` |\n\n"
        "## Wiki distillation checklist (post-implementation)\n\n"
        f"- [{c_box}] Execute every row in `## Wiki impact map`.\n"
    )


def test_validate_spec_file_accepts_valid_active_and_implemented_specs(tmp_path: Path) -> None:
    """Positive tests: valid active approved spec and valid archived implemented spec both pass cleanly."""
    wiki = tmp_path / ".brain-79"
    (wiki / "features").mkdir(parents=True)
    (wiki / "features" / "existing.md").write_text("# Existing\n", encoding="utf-8")

    # 1. Active approved spec (target_wiki not yet created, Test ref still TBD)
    active_spec = tmp_path / "phase-13-sample.md"
    active_spec.write_text(_sample_spec_markdown(status="approved"), encoding="utf-8")
    assert validate_spec_file(active_spec, wiki_root=wiki, repo_root=tmp_path, is_archived=False) == []

    # 2. Archived implemented spec (target_wiki created, test file exists, checklist checked)
    (wiki / "features" / "new-manual.md").write_text("# New manual\n", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_sample.py").write_text("def test_ok(): pass\n", encoding="utf-8")

    impl_spec = tmp_path / "2026-11-adhoc-sample.md"
    impl_spec.write_text(
        _sample_spec_markdown(
            spec_id="SPEC-202611-adhoc-sample",
            status="implemented",
            test_ref="tests/test_sample.py::test_ok",
            checklist_checked=True,
        ),
        encoding="utf-8",
    )
    assert validate_spec_file(impl_spec, wiki_root=wiki, repo_root=tmp_path, is_archived=True) == []


def test_validate_spec_file_catches_negative_cases(tmp_path: Path) -> None:
    """Negative tests: missing related_wiki, open questions, broken R<->AC, naming mismatch, and incomplete closure."""
    wiki = tmp_path / ".brain-79"
    (wiki / "features").mkdir(parents=True)
    (wiki / "features" / "existing.md").write_text("# Existing\n", encoding="utf-8")

    # Case A: active spec with structural, traceability, and naming violations
    bad_spec = tmp_path / "phase-99-broken.md"
    bad_spec.write_text(
        "---\n"
        "spec_id: SPEC-123\n"
        "title: Broken spec\n"
        "status: approved\n"
        "owner: tester\n"
        "last_updated: 2026-11-21\n"
        "related_wiki:\n"
        "  - features/nonexistent.md\n"
        "---\n\n"
        "# SPEC-123 — Broken spec\n\n"
        "## Open questions\n\n"
        "- [ ] **Q-1**: still open\n\n"
        "## Requirements (EARS)\n\n"
        "- **R-1.1**: WHEN X, THE Y SHALL Z.\n"
        "- **R-1.2**: IF A, THEN THE B SHALL C.\n\n"
        "## Acceptance criteria (Given / When / Then)\n\n"
        "### AC-1 — Bad link\n"
        "- **Verifies**: `R-9.9`\n"
        "- **Method**: `magic`\n"
        "- **Given**: g\n"
        "- **When**: w\n"
        "- **Then**: t\n",
        encoding="utf-8",
    )
    errors_a = "\n".join(validate_spec_file(bad_spec, wiki_root=wiki, repo_root=tmp_path, is_archived=False))
    assert "does not match phase filename" in errors_a
    assert "does not exist" in errors_a
    assert "unresolved '- [ ]'" in errors_a
    assert "unknown requirement 'R-9.9'" in errors_a
    assert "must declare '- **Method**:'" in errors_a
    assert "not covered by any AC" in errors_a

    # Case B: implemented spec skipping distillation, Test ref, and target_wiki creation
    unclosed_spec = tmp_path / "phase-14-unclosed.md"
    unclosed_spec.write_text(
        _sample_spec_markdown(
            spec_id="SPEC-014",
            status="implemented",
            test_ref="TBD",
            checklist_checked=False,
        ),
        encoding="utf-8",
    )
    errors_b = "\n".join(validate_spec_file(unclosed_spec, wiki_root=wiki, repo_root=tmp_path, is_archived=True))
    assert "unresolved Test ref" in errors_b
    assert "unchecked '- [ ]' items in ## Wiki distillation checklist" in errors_b
    assert "target_wiki 'features/new-manual.md' does not exist" in errors_b
    assert "Wiki impact map target 'features/new-manual.md' does not exist" in errors_b

    # Case C: implemented spec with empty target_wiki (attempting to bypass distillation)
    empty_target_spec = tmp_path / "phase-15-empty-target.md"
    empty_target_spec.write_text(
        _sample_spec_markdown(
            spec_id="SPEC-015",
            status="implemented",
            target_wiki="",
            test_ref="tests/test_ok.py::test_x",
            checklist_checked=True,
        ).replace("target_wiki:\n  - \n", "target_wiki: []\n"),
        encoding="utf-8",
    )
    errors_c = "\n".join(validate_spec_file(empty_target_spec, wiki_root=wiki, repo_root=tmp_path, is_archived=True))
    assert "must declare at least one target_wiki entry" in errors_c


def test_validate_specs_directory_detects_duplicates_and_illegal_subdirs(tmp_path: Path) -> None:
    """Detect duplicate spec_id collisions and unauthorized subdirectories under specs/."""
    wiki = tmp_path / ".brain-79"
    (wiki / "features").mkdir(parents=True)
    (wiki / "features" / "existing.md").write_text("# Existing\n", encoding="utf-8")
    specs = tmp_path / "specs"
    (specs / "archive").mkdir(parents=True)
    (specs / "drafts").mkdir(parents=True)

    (specs / "phase-13-first.md").write_text(_sample_spec_markdown(spec_id="SPEC-013", status="draft"), encoding="utf-8")
    (specs / "archive" / "phase-13-second.md").write_text(
        _sample_spec_markdown(spec_id="SPEC-013", status="abandoned"), encoding="utf-8"
    )
    errors = "\n".join(validate_specs_directory(specs, wiki_root=wiki, repo_root=tmp_path))
    assert "Duplicate spec_id 'SPEC-013'" in errors
    assert "Unexpected subdirectory 'specs/drafts/'" in errors


def test_pattern_targets_specs_catches_relative_hidden_and_broad_globs() -> None:
    """Verify _pattern_targets_specs catches ./specs/, .brain-79/specs/, and broad **/*.md globs."""
    ws_index = WorkspaceIndex.build(REPO_ROOT, WIKI_ROOT)
    for forbidden in ("specs", "specs/*.md", "./specs/phase-13.md", ".brain-79/specs/foo.md", "**/*.md"):
        assert _pattern_targets_specs(forbidden, ws_index), f"Expected forbidden pattern: {forbidden}"
    for allowed in ("src/brain79/core/*.py", ".brain-79/features/*.md", "README.md"):
        assert not _pattern_targets_specs(allowed, ws_index), f"Unexpected match for safe pattern: {allowed}"
