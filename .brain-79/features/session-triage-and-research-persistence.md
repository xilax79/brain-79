---
type: feature
summary: specification for Phase 6.5 — session knowledge triage (Amnesia Test), zero-code research persistence guard, profile-aware curation guide, path prefix normalization, and handoff schema ergonomics
status: shipped
version: 2.0.3
applies_to:
  - src/brain79/core/handoff.py
  - src/brain79/core/session_commit.py
  - src/brain79/core/curate.py
  - src/brain79/core/locks.py
  - src/brain79/server.py
  - src/brain79/templates/AGENTS.md
related:
  - architecture/roadmap-industrial-scale.md
  - architecture/defect-backlog.md
  - features/handoff-continuity.md
last_updated: 2026-11-05
---

# Feature — Session knowledge triage, research persistence guard and handoff ergonomics (Phase 6.5)

## Overview

During a clean greenfield evaluation (`/private/tmp/test-wiki`, non-Git research session on sports analytics/forecasts) and subsequent MCP tool execution, six interaction and ergonomic failure modes surfaced:
1. **Catastrophic loss of zero-code research:** the agent obeyed the legacy Rule 6 (*"No-Op Idempotence: first check `git status`... Wiki changes must strictly mirror real repository mutations"*). Because the directory was not a Git repo and zero `.py`/`.ts` code files were modified, the agent refused to write any wiki articles and discarded the entire research deliverable.
2. **Silent handoff-only escape hatch:** the agent called `brain79_handoff_write(session_type="research", ...)` directly without calling `brain79_session_commit` or persisting any permanent article in `.brain-79/` (e.g., `topics/`), treating an ephemeral handoff as a substitute for long-term wiki memory.
3. **MCP schema rejection on common LLM parameter aliases:** the agent passed `"decisions"`, `"open_questions"`, and `"next_steps"` to `brain79_handoff_write`. Because FastMCP exports a strict JSON Schema (`additionalProperties: false`), the MCP client rejected the call before reaching Python (`Failed to call tool: data must NOT have additional properties`).
4. **Rigid anti-hallucination keyword guard:** when `pending_work` was empty, the agent's natural closing phrase (`"Sesión consultiva finalizada sin modificaciones de código en el repositorio. Continuar según la siguiente solicitud del usuario."`) was rejected by `validate_handoff_params` because it lacked the exact substring `"no hay tareas"` or `"ninguna"`.
5. **Software-hardcoded curation guide (`curate.py`):** `prepare_curation_guide()` hardcoded software directories (`features/`, `decisions/`, `architecture/`, `product/`) even on `--profile general` wikis (`topics/`, `decisions/`, `entities/`, `sources/`, `notes/`) and lacked a decision tree for triaging durable knowledge vs. ephemeral chat.
6. **Redundant `.brain-79/` path prefix rejection (`locks.py` / `wiki.py`):** when an agent passes `path=".brain-79/features/foo.md"` or `"./.brain-79/topics/bar.md"` to `brain79_write`, `brain79_read`, or `brain79_edit`, `_safe_resolve` resolves it to `.brain-79/.brain-79/features/foo.md`, which fails with `Error: Cannot determine expected type for location '.brain-79'`.

Phase 6.5 eliminates all six failure modes through **deterministic engine guards, schema-level parameter ergonomics, redundant `.brain-79/` prefix stripping, profile-aware curation guidance, and the 3-way session knowledge triage protocol (the Amnesia Test)**.

---

## Technical approach

```
+-----------------------------------------------------------------------------------+
|               PHASE 6.5: SESSION KNOWLEDGE TRIAGE & PERSISTENCE                   |
+-----------------------------------------------------------------------------------+
|                                                                                   |
|  1. AGENT MANIFESTS (AGENTS.md + templates/AGENTS.md + ~/.pi/agent/AGENTS.md)     |
|     - Replace git-bound "No-Op Idempotence" with "The Amnesia Test"               |
|     - 3-way triage:                                                               |
|         Type A: ephemeral / read-only chat     -> true no-op (0 writes)           |
|         Type B: zero-code research / decisions -> persist in wiki (topics/, etc.) |
|         Type C: workspace / code mutation      -> sync governing wiki articles    |
|                                                                                   |
|  2. ENGINE GUARD: UNPERSISTED RESEARCH PROTECTION (handoff.py & session_commit.py)|
|     - If session_type in ("research", "brainstorming", "analysis", "writing")     |
|       AND 0 wiki articles written/edited recently (<30m) or in current commit     |
|       AND knowledge_pending_promotion is empty                                    |
|       AND wiki_deviation_justification is empty                                   |
|       --> reject with actionable error instructing agent to persist findings      |
|           into the active profile's directories via brain79_session_commit()      |
|                                                                                   |
|  3. HANDOFF SCHEMA ERGONOMICS & PATH PREFIX TOLERANCE (server.py, handoff.py,     |
|     locks.py)                                                                     |
|     - Explicit optional alias parameters on brain79_handoff_write & session_commit|
|       (decisions -> completed_work, next_steps -> pending_work,                   |
|        open_questions -> gotchas) so FastMCP JSON Schema accepts them natively    |
|     - Filter conversational filler ("Ninguna.", "None", "Atender la próxima...")  |
|       from next_steps / open_questions / pending_work so empty queues stay empty  |
|     - Expand anti_hallucination_keywords for natural consultative closures        |
|     - Strip redundant leading ".brain-79/" or "./.brain-79/" in                   |
|       normalize_posix_input() so path=".brain-79/topics/x.md" resolves cleanly    |
|                                                                                   |
|  4. PROFILE-AWARE CURATION GUIDE (curate.py)                                      |
|     - Read load_active_schema(wiki_root) in prepare_curation_guide()              |
|     - Emit profile-specific target directories (general vs software + custom)     |
|     - Include the Amnesia Test 3-way triage rubric in the curation output         |
+-----------------------------------------------------------------------------------+
```

---

### Pillar 1: Handoff schema ergonomics, filler filtering, consultative closure keywords and `.brain-79/` prefix tolerance (`src/brain79/core/handoff.py`, `src/brain79/server.py`, `src/brain79/cli/dispatch.py`, `src/brain79/core/locks.py`)

#### 1.1 Explicit parameter aliases in FastMCP, core and CLI (`decisions`, `next_steps`, `open_questions`)
FastMCP generates JSON Schemas with `additionalProperties: false` from Python function signatures. Using `**kwargs` is **forbidden** by FastMCP and does not expose properties in the MCP tool schema.
Furthermore, `tests/test_symmetry.py` enforces 1:1 parameter parity between CLI (`brain79 handoff-write`) and MCP (`brain79_handoff_write`).

Therefore, add explicit optional parameters to:
1. `validate_handoff_params()` and `write_handoff()` in `src/brain79/core/handoff.py`:
   - `decisions: list[str] | None = None`
   - `next_steps: list[str] | None = None`
   - `open_questions: list[str] | None = None`
2. `brain79_handoff_write()` in `src/brain79/server.py`:
   - `decisions: list[str] | None = None`
   - `next_steps: list[str] | None = None`
   - `open_questions: list[str] | None = None`
3. `commit_session()` in `src/brain79/core/session_commit.py`:
   - Pass `decisions=handoff_in.get("decisions")`, `next_steps=handoff_in.get("next_steps")`, and `open_questions=handoff_in.get("open_questions")` to `validate_handoff_params()` and `write_handoff()`.
4. `handoff-write` subparser in `src/brain79/cli/dispatch.py` (to maintain 100% CLI/MCP symmetry in `tests/test_symmetry.py`):
   - `--decisions` (`nargs="*"`, `action="extend"`, `default=[]`)
   - `--next-steps` (`nargs="*"`, `action="extend"`, `default=[]`)
   - `--open-questions` (`nargs="*"`, `action="extend"`, `default=[]`)

#### 1.2 Conversational filler and no-op placeholder filtering (`_is_noop_placeholder`)
When LLMs populate `next_steps`, `pending_work`, or `open_questions` at the end of a completed session, they frequently pass placeholder strings such as `"Ninguna."`, `"None."`, `"N/A"`, or `"Atender la próxima tarea técnica o de investigación del usuario."`.
If `next_steps` is merged blindly into `pending_work`, a session with zero real pending tasks gets polluted with a fake pending task.

Implement a deterministic helper `_is_noop_placeholder(text: str) -> bool` in `src/brain79/core/handoff.py`:
```python
_NOOP_EXACT_VALUES = frozenset({
    "ninguna",
    "ninguno",
    "nada",
    "none",
    "n/a",
    "na",
    "null",
    "sin pendientes",
    "sin tareas",
    "sin tareas pendientes",
    "no pending tasks",
    "no pending work",
    "no open questions",
    "sin preguntas abiertas",
})

_NOOP_SUBSTRING_PATTERNS = (
    "atender la próxima tarea",
    "atender la proxima tarea",
    "atender la siguiente solicitud",
    "continuar según la siguiente solicitud",
    "continuar segun la siguiente solicitud",
    "esperar la siguiente instrucción",
    "esperar la siguiente instruccion",
    "await next user request",
    "awaiting next user request",
    "wait for next user instruction",
    "respond to the next user",
)


def _is_noop_placeholder(text: str) -> bool:
    """Return True if the list item is an empty placeholder or generic 'wait for user' filler."""
    cleaned = text.strip().rstrip(".!").strip().lower()
    if not cleaned or cleaned in _NOOP_EXACT_VALUES:
        return True
    return any(pat in cleaned for pat in _NOOP_SUBSTRING_PATTERNS)
```

In `validate_handoff_params()`:
1. Merge `completed_work`:
   `raw_completed = list(completed_work or []) + list(decisions or [])`
   `norm_completed = [x for x in _normalize_list(raw_completed) if not _is_noop_placeholder(x)]`
2. Merge `pending_work`:
   `raw_pending = list(pending_work or []) + list(next_steps or [])`
   `norm_pending = [x for x in _normalize_list(raw_pending) if not _is_noop_placeholder(x)]`
3. Merge `gotchas`:
   `raw_gotchas = list(gotchas or []) + list(open_questions or [])`
   `norm_gotchas = [x for x in _normalize_list(raw_gotchas) if not _is_noop_placeholder(x)]`

#### 1.3 Expanded consultative and closure keywords in `validate_handoff_params()`
When `norm_pending` is empty (`not norm_pending`), expand `anti_hallucination_keywords` in `src/brain79/core/handoff.py` so natural Spanish and English session-closure phrases pass without false-positive rejections:
```python
anti_hallucination_keywords = [
    "no hay tareas",
    "nada pendiente",
    "no hay pendientes",
    "no hay trabajo",
    "sin tareas",
    "sin pendientes",
    "sin modificaciones",
    "sin cambios",
    "sesión finalizada",
    "sesion finalizada",
    "sesión concluida",
    "sesion concluida",
    "sesión cerrada",
    "sesion cerrada",
    "sesión consultiva",
    "sesion consultiva",
    "continuar según la siguiente",
    "continuar segun la siguiente",
    "próxima solicitud",
    "proxima solicitud",
    "siguiente solicitud",
    "no pending",
    "no pending tasks",
    "no remaining tasks",
    "no remaining work",
    "without pending",
    "session completed",
    "session concluded",
    "session closed",
    "session finished",
    "awaiting next",
    "ready for next",
    "none",
    "all done",
    "all complete",
    "ninguna",
    "ninguno",
]
```

#### 1.4 Redundant `.brain-79/` prefix stripping in `normalize_posix_input()` (`src/brain79/core/locks.py`)
Agents frequently pass `.brain-79/features/foo.md` or `./.brain-79/topics/bar.md` to `brain79_write`, `brain79_read`, or `brain79_edit` because workspace paths in git status or user prompts start with `.brain-79/`.
Update `normalize_posix_input(raw_path: str) -> str` in `src/brain79/core/locks.py` to strip a leading `./.brain-79/` or `.brain-79/` prefix:
```python
def normalize_posix_input(raw_path: str) -> str:
    """Normalize user or API input path by replacing Windows backslashes with forward slashes
    and stripping redundant leading '.brain-79/' or './.brain-79/' prefixes."""
    cleaned = raw_path.replace("\\", "/").strip()
    if cleaned.startswith("./.brain-79/"):
        cleaned = cleaned[len("./.brain-79/"):]
    elif cleaned.startswith(".brain-79/"):
        cleaned = cleaned[len(".brain-79/"):]
    return cleaned
```
This single 5-line improvement makes `brain79_read(".brain-79/INDEX.md")`, `brain79_write(".brain-79/topics/foo.md", ...)`, and `brain79_edit(".brain-79/features/bar.md", ...)` work seamlessly without erroring out with `Cannot determine expected type for location '.brain-79'`.

---

### Pillar 2: Engine guard against unpersisted research and discovery sessions (`src/brain79/core/handoff.py` & `src/brain79/core/session_commit.py`)

#### 2.1 The problem
When a user conducts a research, analysis, brainstorming, or writing session and says *"actualiza la wiki y cerramos la sesión"*, an agent must **never** close the session with only a handoff while leaving the wiki untouched—unless the session genuinely produced zero durable findings (and the agent explicitly justifies why in `wiki_deviation_justification`) or records the items in `knowledge_pending_promotion`.

#### 2.2 Recent wiki activity detection (`_has_recent_wiki_writes`)
In `src/brain79/core/handoff.py`, implement a helper `_has_recent_wiki_writes(wiki_root: Path, window_seconds: float = 1800.0) -> bool`:
- Scans `.brain-79/**/*.md` excluding `INDEX.md`, `SCHEMA.md`, `_raw/`, `handoffs/`, and `.locks/`.
- Returns `True` if at least one permanent wiki article has a filesystem `st_mtime` within `now - window_seconds` (default 30 minutes, configurable/mockable in tests), OR if `_has_session_writes: bool = False` is passed by `commit_session()`.
- **Important nuance for fresh wikis:** do not count `INDEX.md` or `SCHEMA.md` created by `brain79 init`; only count actual content articles in subdirectories (`topics/`, `decisions/`, `features/`, `architecture/`, `product/`, `entities/`, `sources/`, `notes/`, etc.) or non-protected root articles.

#### 2.3 Validation rule in `validate_handoff_params()`
Add a parameter `_has_session_writes: bool = False` to `validate_handoff_params()` (default `False`; `commit_session()` passes `_has_session_writes=bool(written_article_keys or edited_article_keys)`):
- Define knowledge-producing session types:
  `KNOWLEDGE_SESSION_TYPES = frozenset({"research", "brainstorming", "analysis", "writing"})`
- If `(w_root / "SCHEMA.md").exists()` and `session_type in KNOWLEDGE_SESSION_TYPES`:
  Check whether:
  1. `_has_session_writes` is `True`, OR
  2. `_has_recent_wiki_writes(w_root)` is `True`, OR
  3. `bool(norm_promotion)` is `True` (`knowledge_pending_promotion` is non-empty), OR
  4. `bool(wiki_deviation_justification.strip())` is `True`.
- If **all four are False**, raise a `ValueError` with a clear, self-correcting message that tells the agent the exact directories for the active schema profile:
  ```python
  schema = load_active_schema(w_root)
  valid_dirs = ", ".join(
      f"`{d}/`" for d in sorted(schema.directory_to_type.keys()) if d != "handoffs"
  )
  raise ValueError(
      f"Unpersisted '{session_type}' session detected: no permanent wiki articles were created or updated "
      f"in this session, and 'knowledge_pending_promotion' is empty. "
      f"Handoffs are temporary transition snapshots, NOT long-term wiki memory. "
      f"If this session produced research findings, analyses, forecasts, or decisions, you MUST first persist "
      f"them as structured wiki articles in {valid_dirs} (preferably in a single atomic call via "
      f"`brain79_session_commit(writes=[...], handoff={{...}})`). "
      f"If this session was purely trivial chat with zero durable findings to save, provide an explicit reason "
      f"in `wiki_deviation_justification`."
  )
  ```
- **Why checking `(w_root / "SCHEMA.md").exists()` is clean and surgical:** every project initialized via `brain79 init` has `SCHEMA.md` in `.brain-79/` (including `/private/tmp/test-wiki`), whereas minimal unit-test temp directories in `tests/test_handoff.py` that only test `handoffs/` formatting in isolation do not create `SCHEMA.md`. If any existing test in `tests/` creates `SCHEMA.md` with zero articles and calls `write_handoff(session_type="research")` without articles, update that test or verify its expectation.

---

### Pillar 3: Profile-aware curation guide and the Amnesia Test (`src/brain79/core/curate.py`)

#### 3.1 Fix `.locks` exclusion in `analyze_wiki_state()`
In `src/brain79/core/curate.py` line 25:
Change:
```python
articles = [f for f in wiki_root.rglob("*.md") if "_raw" not in f.parts]
```
to:
```python
articles = [f for f in wiki_root.rglob("*.md") if "_raw" not in f.parts and ".locks" not in f.parts]
```

#### 3.2 Dynamic schema profile and directory routing in `prepare_curation_guide()`
Load the active schema via `schema = load_active_schema(wiki_root)` inside `prepare_curation_guide(wiki_root, raw_content)`:
1. Display `- **Active Schema Profile**: \`{schema.profile}\`` in `## Current Wiki Health Overview`.
2. Build the target directory guide dynamically from `schema.directory_to_type`:
   - For `general` profile: `topics/` (`topic`), `decisions/` (`decision`), `entities/` (`entity`), `sources/` (`source`), `notes/` (`note`).
   - For `software` profile: `features/` (`feature`), `decisions/` (`decision`), `architecture/` (`architecture`), `product/` (`product`), `changelog/` (`changelog`).
   - Include any `custom_types` defined in `SCHEMA.md`.
3. Include a concise **`## Session Knowledge Triage (The Amnesia Test)`** section in the curation guide output:
   - **Type A (ephemeral / read-only chat):** greetings, syntax questions, or reading existing files without new findings $\rightarrow$ **no-op** (do not invent articles).
   - **Type B (zero-code research, analysis & decisions):** domain research, forecasts, comparisons, benchmarks, or decisions—even when **0 code files or Git commits changed** $\rightarrow$ **must persist** as structured articles in the active profile's directories (`topics/`, `decisions/`, etc.). Never dump raw chat logs; synthesize structured sections, tables, and conclusions.
   - **Type C (workspace / code mutation):** code or project files changed $\rightarrow$ **must sync** governing wiki articles.

---

### Pillar 4: Rewrite Rule 6 in all `AGENTS.md` manifests and expose explicit handoff signature

Update **all three** manifest files identically:
1. `src/brain79/templates/AGENTS.md`
2. `AGENTS.md` (repository root)
3. `/Users/xilax/.pi/agent/AGENTS.md` (global user harness manifest)

#### 4.1 Replace Rule 6 ("No-Op Idempotence") with "Session knowledge triage & persistence protocol (the Amnesia Test)"
Replace the old `git status`-coupled Rule 6 in `AGENTS.md` and `src/brain79/templates/AGENTS.md` with:

```markdown
6. **Session knowledge triage & persistence protocol (the Amnesia Test)**:
   - When asked to "update the wiki", "sync docs", or wrap up/close a session, evaluate the conversation using **the Amnesia Test**:
     *"If this session context were wiped right now, would the user lose valuable research findings, domain analysis, forecasts, decisions, or implementation context that took effort to produce?"*
   - Classify the session into one of three categories:
     - **Type A — Ephemeral / read-only consultation (true no-op)**: casual chat, greetings, or answering a quick question by reading existing files without generating new domain knowledge or code changes.
       -> **Action**: do NOT invent or artificially edit wiki articles. Verify health with `brain79_lint()` and state that no wiki modifications are required.
     - **Type B — Zero-code research, analysis & discovery (knowledge deliverable)**: domain research, web investigations, forecasts, benchmarks, trade-off analyses, or strategic decisions—**even when zero code files were modified and even in non-Git directories**.
       -> **Action**: in these sessions, **the distilled knowledge IS the deliverable**. You MUST synthesize the findings into structured wiki articles (e.g., `topics/<slug>.md`, `entities/<slug>.md`, `sources/<slug>.md`, or `decisions/<slug>.md` in `general` profile; `architecture/`, `product/`, `features/`, or `decisions/` in `software` profile) and commit them atomically via `brain79_session_commit(writes=[...], handoff={...})`. Never dump raw chat transcripts; distill clean headings, tables, conclusions, and sources.
     - **Type C — Code & workspace mutation**: source code, configuration, or tests were created or modified.
       -> **Action**: update or create the corresponding governing articles (`features/`, `architecture/`, `decisions/`, `changelog/`) and commit via `brain79_session_commit(...)`.
```

#### 4.2 Clarify tool signatures in `AGENTS.md` table
In the tool table of `AGENTS.md` and `src/brain79/templates/AGENTS.md`:
- Update the `brain79_session_commit` row to explicitly highlight that it is the **primary 1-call tool for closing sessions** (combining article writes/edits + handoff in one transaction).
- Update the `brain79_handoff_write` description/docstring in `src/brain79/server.py` to note:
  - Its exact parameters (`session_type`, `summary`, `completed_work`, `pending_work`, `knowledge_pending_promotion`, `resources`, `gotchas`, `boot_instruction`, `wiki_deviation_justification`, plus supported aliases `decisions`, `next_steps`, `open_questions`).
  - That if the session produced new wiki articles, `brain79_session_commit(writes=[...], handoff={...})` MUST be used instead of calling `brain79_handoff_write` alone.

---

## Implementation checklist for the builder agent

1. **`src/brain79/core/locks.py`**:
   - Update `normalize_posix_input(raw_path: str) -> str` to strip redundant leading `./.brain-79/` or `.brain-79/` prefixes so calls like `brain79_write(".brain-79/topics/foo.md", ...)` resolve cleanly to `topics/foo.md`.
2. **`src/brain79/core/handoff.py`**:
   - Implement `_is_noop_placeholder(text: str) -> bool` to strip conversational filler (`"Ninguna."`, `"None"`, `"Atender la próxima tarea..."`, `"Continuar según la siguiente solicitud..."`, etc.).
   - Add optional alias parameters `decisions: list[str] | None = None`, `next_steps: list[str] | None = None`, `open_questions: list[str] | None = None`, and `_has_session_writes: bool = False` to `validate_handoff_params()` and `write_handoff()`.
   - Merge non-placeholder `decisions` into `completed_work`, `next_steps` into `pending_work`, and `open_questions` into `gotchas`.
   - Expand `anti_hallucination_keywords` in `validate_handoff_params()` to support natural Spanish and English consultative closure phrases (`"sin modificaciones"`, `"sin tareas"`, `"sesión consultiva"`, `"sesión finalizada"`, `"continuar según la siguiente"`, `"próxima solicitud"`, `"session completed"`, `"awaiting next"`, etc.).
   - Implement `_has_recent_wiki_writes(wiki_root: Path, window_seconds: float = 1800.0) -> bool` (ignoring `INDEX.md`, `SCHEMA.md`, `_raw/`, `handoffs/`, `.locks/`) and enforce the **unpersisted research session guard** when `(w_root / "SCHEMA.md").exists()` and `session_type in ("research", "brainstorming", "analysis", "writing")` and no wiki articles were written/edited, `knowledge_pending_promotion` is empty, and `wiki_deviation_justification` is empty.
3. **`src/brain79/core/session_commit.py`**:
   - In `commit_session()`, pass `decisions=handoff_in.get("decisions")`, `next_steps=handoff_in.get("next_steps")`, `open_questions=handoff_in.get("open_questions")`, and `_has_session_writes=bool(written_article_keys or edited_article_keys)` into `validate_handoff_params()` and `write_handoff()`.
4. **`src/brain79/server.py` & `src/brain79/cli/dispatch.py`**:
   - Add `decisions: list[str] | None = None`, `next_steps: list[str] | None = None`, and `open_questions: list[str] | None = None` to `brain79_handoff_write()` signature in `src/brain79/server.py` and `--decisions`, `--next-steps`, `--open-questions` to `handoff-write` in `src/brain79/cli/dispatch.py` (preserving 1:1 CLI/MCP symmetry in `tests/test_symmetry.py`).
   - Update `brain79_handoff_write` and `brain79_session_commit` docstrings to emphasize persisting research findings via `brain79_session_commit(writes=[...], handoff={...})`.
5. **`src/brain79/core/curate.py`**:
   - Exclude `.locks` in `analyze_wiki_state()`.
   - Load `load_active_schema(wiki_root)` in `prepare_curation_guide()` to render the active profile (`general` vs `software`), dynamic target directories (`topics/`, `entities/`, `sources/`, `notes/`, `decisions/` for `general`), and the 3-way session knowledge triage rubric (the Amnesia Test).
6. **Agent manifests (`src/brain79/templates/AGENTS.md`, `AGENTS.md`, `/Users/xilax/.pi/agent/AGENTS.md`)**:
   - Replace Rule 6 (*No-Op Idempotence* tied to `git status`) with the **Session knowledge triage & persistence protocol (the Amnesia Test)** covering Type A (ephemeral chat), Type B (zero-code research & discovery), and Type C (code mutation), respecting ADR-015 sentence case policy.
7. **Tests (`tests/test_session_triage_and_handoff_ergonomics.py`)**:
   - **Exact reproduction test (Copa Libertadores scenario):** simulate a `--profile general` non-Git wiki where the agent calls `brain79_handoff_write` with `session_type="research"`, `decisions=[...]`, `open_questions=["Ninguna."]`, `next_steps=["Atender la próxima tarea técnica o de investigación del usuario."]`, and `boot_instruction="Sesión consultiva finalizada sin modificaciones de código en el repositorio. Continuar según la siguiente solicitud del usuario."`:
     - Verify that calling `brain79_handoff_write` **without** first persisting a research article is blocked by the **unpersisted research session guard** with a clear message pointing to `topics/`, `decisions/`, etc.
     - Verify that once the research article (`topics/copa-libertadores-2026.md`) is written (either via `brain79_session_commit(writes=[...], handoff={...})` or prior `brain79_write`), the exact same handoff payload succeeds on the first try: `decisions` is merged into `completed_work`, `"Ninguna."` and `"Atender la próxima tarea..."` are filtered out as no-op placeholders (leaving `pending_work=[]` and `gotchas=[]`), and `boot_instruction` passes the consultative closure check.
   - **Redundant `.brain-79/` path prefix test:** verify `write_article(".brain-79/topics/test.md", ...)` and `read_article("./.brain-79/topics/test.md")` strip the prefix and resolve to `topics/test.md` without raising `Cannot determine expected type for location '.brain-79'`.
   - **Explicit justification bypass test:** verify that a `research` session that genuinely produced zero durable findings succeeds when `wiki_deviation_justification` explains why no article was written.
   - **Profile-aware curation guide test:** verify `prepare_curation_guide()` on a `general` profile wiki outputs `topics/`, `entities/`, `sources/`, `notes/` and `The Amnesia Test`, and excludes `.locks/` files from `article_count`.

---

### Pillar 5: Adversarial audit remediations and zero-retry E2E suite

Following adversarial audit of Phase 6.5, four architectural defects were resolved:
1. **Isolated `normalize_wiki_rel_path()` from `normalize_posix_input()`:** `normalize_posix_input()` remains pure (preserving `.brain-79/` in `applies_to` workspace paths evaluated by `drift.py`), while `normalize_wiki_rel_path()` handles prefix stripping exclusively for wiki files.
2. **Normalized `rel_path` in `check_file_health()`:** eliminates false-positive broken link warnings when `.brain-79/` prefixed paths are passed to `brain79_write` or `brain79_edit`.
3. **General profile H2 structural flexibility:** in `--profile general`, `topic` and `context` accept any structured H2 section (e.g. `## Análisis y pronósticos`, `## Resumen`, `## Contexto`) without enforcing English `## Overview`.
4. **Accurate session boundary via latest handoff mtime:** `_has_recent_wiki_writes()` checks article modification against the latest handoff timestamp, eliminating cross-session blind windows.
5. **Real-agent E2E smoke runner (`scripts/run_e2e_smoke.py`):** automated test suite running `pi --models gemini-3.8-flash:low -p` across 3 canonical scenarios, validating the Zero-Retry MCP Metric.

---

[← Volver al Índice](../INDEX.md)
