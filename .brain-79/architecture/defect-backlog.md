---
type: architecture
summary: Master defect backlog, forensic root-cause analysis, and specification for bug fixes, agent efficiency, and on-demand handoff policy
stability: stable
applies_to:
  - src/brain79/templates/SCHEMA.md
  - src/brain79/templates/SCHEMA_GENERAL.md
  - src/brain79/templates/AGENTS.md
  - src/brain79/core/frontmatter.py
  - src/brain79/core/lint_organizational.py
  - src/brain79/core/orient.py
  - src/brain79/server.py
  - AGENTS.md
related:
  - architecture/roadmap-industrial-scale.md
  - architecture/current-state.md
  - features/cross-platform-and-lock-isolation.md
last_updated: 2026-11-04
---

# Architecture — Defect Backlog & Agent Efficiency Deep Dive

## Overview

This document consolidates the root-cause analysis and engineering specification for defects and LLM agent inefficiencies discovered during live evaluation on greenfield projects (`/private/tmp/test-wiki`, session `01a1a200-0721-762e-bffb-64991a00140d`). It also formalizes the **On-Demand Handoff Policy** to prevent per-turn handoff spam during multi-turn interactive sessions.

---

## 1. Critical Technical Bugs (Engine & Templates)

### BUG-001: Broken Local Link in `SCHEMA_GENERAL.md` and Root Backlink Normalization
* **Severity:** Critical (`[CRITICAL] Broken Local Links`).
* **Location:** `src/brain79/templates/SCHEMA_GENERAL.md:64` and `src/brain79/core/frontmatter.py:539`.
* **Symptom:** Immediately after running `brain79 init --profile general`, running `brain79 lint --strict` fails with:
  ```text
  [CRITICAL] Broken Local Links (1)
  - SCHEMA.md → ../INDEX.md: target not found
  ```
* **Deep-Dive Root Cause:**
  1. `SCHEMA_GENERAL.md` ends with `[← Volver al Índice](../INDEX.md)`. Because `SCHEMA.md` lives at the root of `.brain-79/` (`.brain-79/SCHEMA.md`), `../INDEX.md` resolves one level *above* `.brain-79/` into the project workspace root, which does not exist.
  2. In `src/brain79/core/frontmatter.py`, `normalize_backlink_footer(body, rel_path)` immediately returns `body` untouched when `len(parts) <= 1`. If an agent writes or edits a root-level wiki file containing `](../INDEX.md)`, the normalizer does not rewrite it to `](INDEX.md)`.
* **Exact Remediation:**
  1. In `src/brain79/templates/SCHEMA_GENERAL.md` (and `src/brain79/templates/SCHEMA.md`), replace any root-level `../INDEX.md` footer link with `[← Volver al Índice](INDEX.md)`.
  2. In `normalize_backlink_footer()` (`frontmatter.py`), when `len(parts) == 1` and `clean_rel == "SCHEMA.md"`, rewrite any trailing `](../INDEX.md)` to `](INDEX.md)`.
  3. Add an invariant test in `tests/test_init_project.py` that initializes both `software` and `general` profiles and asserts `lint_wiki()` returns `[Status: OK]` out of the box.

---

### BUG-002: Rigid `article_not_atomic` H2 Threshold & Missing Code-Fence Masking
* **Severity:** Moderate (`WARN: Article has X H2 sections (max recommended: 7)`).
* **Location:** `src/brain79/core/lint_organizational.py:251` (`check_article_atomicity`).
* **Symptom:** Structured reference documents, checklists, or topic outlines (e.g., `topics/checklist-investigacion-libro.md` with 9 short H2 sections) trigger `article_not_atomic` warnings despite being concise and well-organized.
* **Deep-Dive Root Cause:**
  1. **Unmasked Code Fences:** `check_article_atomicity` counts `line.startswith("## ")` on raw `content.splitlines()` *without* calling `_mask_code_fences(content)`. Markdown examples inside ```` ```markdown ```` blocks falsely inflate the H2 count.
  2. **Context-Blind Threshold:** A flat limit of `> 7` H2 sections penalizes short, structured checklists, roadmaps, backlogs, and `general` profile `topic` outlines that use H2 headers to group compact bullet items.
* **Exact Remediation:**
  1. Mask code fences via `_mask_code_fences(content)` before counting `## ` headings in `check_article_atomicity`.
  2. Apply a composite heuristic:
     - Exempt compact articles (`len(lines) <= 150`) from `article_not_atomic` unless H2 count exceeds `12`.
     - For checklist/reference/roadmap/backlog articles (detected via filename/tags containing `checklist`, `roadmap`, `backlog`, `glossary`, or body containing $\ge 5$ task checkboxes `- [ ]` / `- [x]`), raise the maximum recommended H2 threshold from `7` to `15`.
     - For standard prose articles (`> 150` lines), raise the threshold from `7` to `10` H2 sections.

---

## 2. Agent Behavioral Inefficiencies & Protocol Alignment

### INEF-001: Redundant `brain79_write` $\rightarrow$ `brain79_navigate` $\rightarrow$ `brain79_index` Loop
* **Observed Waste:** 8 redundant tool calls across 4 turns.
* **Deep-Dive Root Cause:**
  1. `brain79_write`, `brain79_edit`, and `brain79_write_many` already execute `regenerate_index_navigation()` atomically under lock.
  2. However, their return string is simply `Written: <path> · lint OK`. Because the receipt does not mention that `INDEX.md` was already updated, and because `AGENTS.md` (and `~/.pi/agent/AGENTS.md`) contained legacy instructions saying *"after writing articles, run brain79 navigate --regenerate"*, the agent dutifully called `navigate` and `index` after every single write.
* **Exact Remediation:**
  1. **Self-Documenting Tool Receipts (`src/brain79/server.py`):** Update the return message of `brain79_write`, `brain79_edit`, and `brain79_write_many` to:
     `Written: <path> · INDEX.md auto-synced · lint OK`
  2. **Tool Docstring Clarification (`src/brain79/server.py`):** Update `brain79_navigate` docstring to state: *"Note: brain79_write, brain79_edit, brain79_write_many, and brain79_session_commit automatically sync INDEX.md. Only call brain79_navigate(regenerate=True) after manual filesystem edits outside MCP."*
  3. **Remove Misleading Instruction in `AGENTS.md`:** In `src/brain79/templates/AGENTS.md`, `./AGENTS.md`, and `~/.pi/agent/AGENTS.md`, clarify that `navigate --regenerate` is only for manual/CLI bulk fixes, never after MCP writes.

---

### INEF-002: Skipping `brain79_orient` in Favor of `brain79_index` + `brain79_read("SCHEMA.md")`
* **Observed Waste:** Multiple sequential cold-start calls instead of 1 turn.
* **Deep-Dive Root Cause:**
  1. **Contradictory Prompt & Tool Docstring:** The global `~/.pi/agent/AGENTS.md` (line 49) and the docstring of `brain79_index()` in `src/brain79/server.py` (line 55) both say: *"Always call this first at the start of a session"*, directly contradicting `brain79_orient()`.
  2. **Missing Schema Summary in `orient()`:** When `brain79_orient()` is called on a fresh or general-profile wiki without matching articles, it returns `INDEX.md` and `handoffs/`, but does not summarize the active ontology profile (`software` vs `general`) and valid directories/required fields. This forces the agent to make an extra call to `brain79_read("SCHEMA.md")` or `brain79_schema()`.
* **Exact Remediation:**
  1. **Compact Active Schema Header in `orient()` (`src/brain79/core/orient.py`):** Include a concise `## 📐 Active Schema Summary` section in `orient()` output listing the active profile (`software` or `general`) and each directory's `type` and `required` fields (5–8 lines).
  2. **Fix `brain79_index` Docstring (`src/brain79/server.py`):** Change docstring to: *"Return INDEX.md routing table only. For session cold start, prefer `brain79_orient` which loads index, schema summary, latest handoff, and governing articles in a single call."*
  3. **Sync Global `~/.pi/agent/AGENTS.md`:** Update rule 1 in `~/.pi/agent/AGENTS.md` from `brain79_index()` to `brain79_orient()`.

---

### INEF-003 (Corrected): On-Demand Handoff Policy (Preventing Per-Turn Handoff Spam)
* **Initial Misdiagnosis in Forensics:** The prior forensic note flagged the absence of a `handoff_write` at the end of an interactive turn as an error.
* **Architectural Policy Decision (User-Governed Handoffs):**
  Handoffs (`brain79_handoff_write` or the `handoff` field in `brain79_session_commit`) **MUST NOT** be executed automatically at the end of every conversational turn. In a 20-turn interactive session, writing a handoff after each turn would pollute `.brain-79/handoffs/` with 20 redundant snapshots and waste thousands of output tokens.
* **Enforced Rules for Handoffs & Session Commits:**
  1. **Interactive Human-in-the-Loop Sessions:**
     - During normal turns, the agent updates wiki articles directly (`brain79_write`, `brain79_edit`, or `brain79_session_commit` *without* the `handoff` payload) when concrete project knowledge changes.
     - The agent **ONLY** writes a handoff (`brain79_handoff_write` or `brain79_session_commit(handoff=...)`) when **explicitly requested by the user** (e.g., *"save handoff"*, *"wrap up session"*, *"close session"*, *"haz handoff"*).
  2. **Autonomous / Headless Sub-Agent Sessions:**
     - When an autonomous worker agent (with no human in the loop) is spawned to execute a bounded task and terminate its process/context window, it writes a single handoff right before terminating to hand over state to the next agent or human.
* **Exact Remediation:**
  - Explicitly codify this **On-Demand Handoff Rule** in `src/brain79/templates/AGENTS.md`, `./AGENTS.md`, `~/.pi/agent/AGENTS.md`, and in the docstrings of `brain79_handoff_write` and `brain79_session_commit` in `src/brain79/server.py`.

---

### INEF-004: Post-Mutation Broken Link Detection in Inline Health Checks
* **Observed Issue:** Individual article writes reported `lint OK`, leaving a broken link in `SCHEMA.md` unnoticed until a full `brain79 lint` was run.
* **Deep-Dive Root Cause:**
  `check_file_health()` in `src/brain79/core/wiki.py` checks H1 presence, leakage rules, and broken links *inside the written file*, which is fast and O(1). However, `SCHEMA.md` was broken at `init` time (`BUG-001`), not during `write`. Once `BUG-001` is fixed and `check_file_health` validates outgoing links from any written/edited file, inline health checks remain fast while catching broken links immediately on write.

---

## 3. Implementation Checklist (Pre-Phase 6 Bugfix & Protocol Polish)

1. **`src/brain79/templates/SCHEMA_GENERAL.md` & `SCHEMA.md`:** Fix root backlink to `[← Volver al Índice](INDEX.md)`.
2. **`src/brain79/core/frontmatter.py`:** Ensure `normalize_backlink_footer` normalizes `](../INDEX.md)` to `](INDEX.md)` for root-level files (`len(parts) == 1`).
3. **`src/brain79/core/lint_organizational.py`:** Mask code fences in `check_article_atomicity` and apply the composite H2 threshold (10 for prose >150 lines, 15 for checklists/roadmaps/compact outlines).
4. **`src/brain79/core/orient.py`:** Add the compact `## 📐 Active Schema Summary` block so cold-start orientation includes valid directories and required fields in 1 call.
5. **`src/brain79/server.py`:**
   - Update `brain79_write`, `brain79_edit`, and `brain79_write_many` receipts to include `· INDEX.md auto-synced · lint OK`.
   - Update docstrings on `brain79_index`, `brain79_navigate`, `brain79_handoff_write`, and `brain79_session_commit` (enforcing the **On-Demand Handoff Policy**).
6. **`src/brain79/templates/AGENTS.md`, `./AGENTS.md`, & `~/.pi/agent/AGENTS.md`:** Align cold-start (`brain79_orient`), auto-synced navigation, and the **On-Demand Handoff Policy**.
7. **Tests:** Add regression tests for `init --profile general` + `lint --strict`, checklist H2 atomicity exemptions, and `orient` active schema summary.

---

[← Volver al Índice](../INDEX.md)
