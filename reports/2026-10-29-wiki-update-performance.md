# Performance Report — End-of-Session Wiki Update

- **Date:** 2026-10-29
- **Scope:** Why "update the wiki at the end of the session" is slow, and what to change.
- **Audience:** Developer agent who will implement the fixes.
- **Codebase version:** v1.0.0 (`c93dbb8`), FastMCP 3.4.7 in the installed tool env.

---

## 1. Executive summary

The slowness is **not** in brain-79's Python code. Every server operation finishes in about 80–120 ms on the current wiki. More than 95% of the wall-clock time goes to **LLM round trips and output-token generation**. The tool design makes both worse:

1. **Validation is fail-fast and reports one error at a time.** Real session logs show **48% of `brain79_write` calls fail** (78/164) and **38% of `brain79_handoff_write` calls fail** (11/29). Each retry makes the LLM regenerate the **whole article**. A single decision article needed up to 6 sequential attempts.
2. **The schema is not visible to the agent before it writes.** `SCHEMA.md` lists types per directory, but not the required fields or enum values per type. Agents guess (`title`, `tags`, `created`, `status: implemented`, …) and get rejected.
3. **Writes are full-file only.** There is no patch, append, or batch tool, so every small change (INDEX "Current focus", a changelog line) means re-emitting the full article.
4. **The workflow needs too many separate calls:** ingest → read → write ×N → navigate → lint → handoff. Navigation regeneration and lint are never automatic.
5. **Every tool response is sent twice.** FastMCP returns both `content` and `structuredContent` for `-> str` tools, and the Pi adapter renders both. This doubles input tokens on every call.
6. **Bug: handoffs are registered in the navigation registry.** Each handoff adds a line to `INDEX.md` Quick navigation. INDEX grows without limit toward the 150-line cap, which then triggers more failures and cleanup work.

Fixing items 1, 2, 5 and 6 is low effort and should remove most of the latency. Items 3 and 4 cut the remaining round trips and output tokens.

---

## 2. Evidence

### 2.1 Server-side timings (current wiki, 16 articles)

Measured on a copy of `.brain-79/` in `/tmp`:

| Command | Wall time |
|---|---|
| `brain79 index` (warm) | ~110 ms |
| `brain79 lint --strict` | ~92 ms |
| `brain79 navigate --regenerate` | ~121 ms |
| `brain79 write …` | ~82 ms |
| `brain79 ingest …` | ~81 ms |
| MCP server cold import (`brain79.server`, mostly `fastmcp`) | ~640 ms, once per session |

**Conclusion:** at the current size, server time is negligible (< 1.5 s for a whole session close).

### 2.2 Server-side scalability (synthetic wikis, ~80 links per article)

| Articles | `lint_wiki` | `lint_organizational` | `prepare_curation_guide` (ingest) | `write_article` |
|---|---|---|---|---|
| 50 | 204 ms | 29 ms | 230 ms | 1.3 ms |
| 300 | 1 297 ms | 147 ms | 1 319 ms | 1.3 ms |
| 1 000 | 4 034 ms | 482 ms | 4 355 ms | 1.7 ms |

cProfile (300 articles): almost all `lint_wiki` time goes to `Path.resolve()` / `relative_to()` / `realpath` on each link (24k `resolve()` calls). This is a P2 concern: it only matters on large wikis.

### 2.3 Real agent behavior (Pi session logs, `~/.pi/agent/sessions`, all projects using brain79)

| Tool | Calls | Errors | Error rate |
|---|---|---|---|
| `brain79_write` | 164 | 78 | **48%** |
| `brain79_handoff_write` | 29 | 11 | **38%** |

- Output tokens spent on failed write arguments: **~65 000** (rough estimate: argument bytes / 4).
- End-of-session segments took 70–420 s, with 100k–320k input tokens re-sent across turns.
- Typical retry chain (one article, sequential, each with full content):
  `lacks required field date` → `lacks status` → `lacks deciders` → `status 'shipped' not in [...]` → `Unknown frontmatter key 'version'`.
- Another chain: `lacks last_updated` → `Unknown key 'title'` → `Unknown key 'created'` → `Unknown key 'tags'`.
- Handoff failures: `session_type 'development'` / `'one-off'`, `previous_handoff_ref 'initial'` / `None`, and the anti-hallucination keyword check.
- Agents shell out to `brain79 navigate --regenerate && brain79 lint --strict` through bash. The `AGENTS.md` template wrongly says lint has "no MCP equivalent", but `brain79_lint` exists.

> Caveat: some logs come from older builds (Aug 2026). The fail-fast behavior is still in the current code; I reproduced it today (`brain79 write` with a minimal feature frontmatter returns only `lacks required field status`).

### 2.4 Reproduced defects

- **Handoff pollution of INDEX:** running `brain79 handoff-write` and then `brain79 navigate --regenerate` adds a `### Handoffs` section to `INDEX.md` with one line per handoff.
- **Duplicated tool output:** `brain79_index` output in Pi contains the full INDEX twice (text + `structuredContent.result`). Verified with a minimal FastMCP 3.4.7 server: `@mcp.tool()` returns `structuredContent={'result': ...}`, while `@mcp.tool(output_schema=None)` returns `None`.
- **Lost actionable hints over MCP:** `server.brain79_write` returns `f"Error: {exc}"`. `ValidationError.__str__` is only `message`, so the `actionable` text never reaches the agent.

---

## 3. Root causes mapped to code

| # | Root cause | Location |
|---|---|---|
| R1 | Fail-fast validation (first error raises) | `core/frontmatter.py::validate_frontmatter`, `core/validation.py::validate_article_content` |
| R2 | `actionable` dropped in MCP error path | `server.py::brain79_write` (`f"Error: {exc}"`) |
| R3 | Required fields and enums per type not exposed to agents | `templates/SCHEMA.md`, `.brain-79/SCHEMA.md`, `brain79_write` docstring, `core/curate.py` guide |
| R4 | Deterministic fields must be supplied by the LLM (`type`, `last_updated`, `date`) | `core/validation.py` |
| R5 | No partial edit, append, or batch write | `core/wiki.py`, `server.py`, `cli/dispatch.py` |
| R6 | Navigation not regenerated on write; lint not run on write | `core/wiki.py::write_article`, `core/navigation.py` |
| R7 | Handoffs registered into navigation | `core/wiki.py::write_article` (registration excludes only INDEX/SCHEMA/_raw) |
| R8 | Duplicated `structuredContent` | `server.py` (all `@mcp.tool()` decorators) |
| R9 | Handoff tool schema too loose (`session_type: str`, required `previous_handoff_ref`, keyword-based anti-hallucination check) | `server.py::brain79_handoff_write`, `core/handoff.py::write_handoff` |
| R10 | Ingest response is verbose and redundant (echoes 50 lines of the summary back, runs `lint_organizational` twice) | `core/curate.py::prepare_curation_guide`, `analyze_wiki_state` |
| R11 | Docs drift: "lint has no MCP equivalent" | `templates/AGENTS.md`, project `AGENTS.md` |
| R12 | Lint re-reads files many times and calls `Path.resolve()` per link | `core/lint.py`, `core/lint_organizational.py` |

---

## 4. Recommendations (prioritized)

### P0 — High impact, low effort

**P0.1 Collect all validation errors in one pass (R1, R2)**
- Change `validate_frontmatter` to gather every violation (missing fields, enum errors, unknown keys, bad dates, location mismatch) and raise one `ValidationError` listing all of them. A new `issues: list[...]` attribute plus a combined message would work.
- In `server.py::brain79_write` (and the CLI write path), return `exc.format_user_message()` for `ValidationError`, not `str(exc)`.
- Append a **ready-to-paste frontmatter template** for the target type to the error. Example for `features/x.md`:
  ```yaml
  ---
  type: feature
  status: <planned|in_progress|shipped|deprecated|legacy>
  version: <x.y.z>
  last_updated: 2026-10-29
  ---
  ```
- Expected effect: at most 1 retry per article instead of up to 6.

**P0.2 Expose the schema before writing (R3)**
- Generate the per-type table (required fields, optional fields, enums, an example) **from `TYPE_SCHEMA`** so it cannot drift. Use it in:
  - `templates/SCHEMA.md` (and re-sync `.brain-79/SCHEMA.md`);
  - the `brain79_write` docstring (short form);
  - the `brain79_ingest` curation guide (short form).
- Optional: `brain79_schema(type?)` MCP tool plus `brain79 schema` CLI subcommand (keeps the symmetry test green).

**P0.3 Server fills in deterministic fields (R4)** — *requires amending ADR-004*
- If `type` is missing, infer it from `LOCATION_TO_TYPE`.
- Always set `last_updated` to today (UTC). The server knows this better than the LLM.
- For `decision`/`changelog`, default `date` to today if missing.
- Keep rejecting **semantic** fields the server cannot know: `status`, `stability`, `version`, `deciders`.
- For commonly hallucinated keys (`title`, `tags`, `created`), decide on one behavior (strip with a warning in the response, or allow as optional) and record it in the ADR amendment.

**P0.4 Disable `structuredContent` duplication (R8)**
- Use `@mcp.tool(output_schema=None)` on every tool, or a FastMCP server-level equivalent if one exists. Verified to work on FastMCP 3.4.7.
- Effect: roughly halves input tokens for every brain79 tool response in Pi.
- Pin `fastmcp` to a compatible range in `pyproject.toml` (currently `>=2.0.0`).

**P0.5 Exclude handoffs from the navigation registry (R7)**
- In `write_article`, skip `register_article` for `handoffs/`. Also drop existing `handoffs/*` entries during `regenerate_index_navigation` (self-healing).
- `check_navigation_freshness` should ignore handoffs too.
- Add a regression test: write a handoff, regenerate, and assert INDEX has no handoff lines.

### P1 — Fewer round trips and fewer output tokens

**P1.1 Auto-regenerate Quick navigation on write (R6)**
- After `register_article` succeeds for a non-INDEX article, call `regenerate_index_navigation`.
- At the same time, make `regenerate_index_navigation` **atomic** (tmp + replace) and **locked**: use the same `INDEX.md.lock` that `write_article` uses. Today it calls `index_path.write_text` without a lock and can race with an INDEX write.
- When the agent writes `INDEX.md` itself, keep the Quick navigation section server-generated: re-inject it after the write. This removes the `navigate --regenerate` step and the `navigation_desync` warnings.
- Record this as a new ADR (it changes write side effects).

**P1.2 Return a per-file health check in the write response (R6)**
- After writing, run the cheap per-file checks: H1 present, broken links from this file, decision leakage, atomicity. Append a 1–3 line status (`Written: features/x.md · lint OK` or a list of issues).
- This removes the separate final `lint` call in most sessions. Keep `brain79_lint` for the full scan.

**P1.3 Add partial edits (R5)**
- `brain79_edit(path, edits: list[{old_text, new_text}])` plus a `brain79 edit` CLI subcommand. Apply the edits in memory, run full validation on the result, then do the atomic write, registration and nav regeneration.
- Optional: `brain79_append(path, heading, text)` for changelog and "Known issues" style additions.
- Effect: INDEX "Current focus" updates and changelog entries drop from about 1–2k output tokens to about 50–150.

**P1.4 Batch writes (R5)**
- `brain79_write_many(articles: list[{path, content}])` plus a CLI equivalent. Validate **all** articles first and report every error at once. If valid, write all, regenerate nav once, and run one lint.
- Optional composite: `brain79_session_close(summary, articles?, edits?, handoff?)`. This runs ingest, the writes, nav and lint, plus an optional handoff, in **one call**. It is the biggest round-trip win, but also the largest API addition, so do it after P1.3/P1.4 if still needed.

**P1.5 Tighten the handoff tool schema (R9)**
- `session_type: Literal["feature","bugfix","research","brainstorming"]` so the JSON schema shows the enum to the LLM.
- `previous_handoff_ref: str = "latest"`. Treat `None`/`""`/`"none"`/`"initial"` as "no previous". If an explicit ref is not found, fall back to `latest` and add a warning instead of failing.
- List params default to `[]`.
- Replace the keyword-based anti-hallucination check (it depends on language and phrasing). Either auto-append a canonical "No pending tasks." line when `pending_work` is empty, or add an explicit `no_pending_work: bool`.

**P1.6 Slim the ingest response (R10)**
- Remove the "Session Input Snippet" echo (the agent just sent that text).
- Compute `lint_organizational` once and reuse it (`analyze_wiki_state` and `lint_wiki` both run it today).
- When status is OK, return a compact summary, not the full empty report.
- Also fix the CLI/MCP asymmetry: the CLI `ingest` prints only the saved path.

**P1.7 Fix documentation drift (R11)**
- `templates/AGENTS.md` and the project `AGENTS.md`: document `brain79_lint()` as the MCP equivalent.
- Add a short **"End-of-session recipe"** (target: 2–4 calls), for example: `brain79_ingest` → `brain79_write_many`/`brain79_edit` → `brain79_handoff_write`.
- Update `.brain-79/features/cli.md`, `features/mcp-server.md` and `architecture/mcp-server.md` for any new tools.

### P2 — Server scalability (only relevant for large wikis)

**P2.1 One-pass lint with a shared document cache (R12)**
- Walk `.brain-79/` once with `os.walk` and prune `_raw/` and `handoffs/` early. Today, `rglob` descends into `_raw/` (which gains one file per ingest and is never purged) before filtering.
- Read and parse each file once (content, frontmatter, masked content, links). Pass that cache to all checks in `lint_organizational` (today: 7 `rglob` traversals and up to 6 reads per file) and to `lint_wiki`.
- Resolve links with string math (`posixpath.normpath` against a precomputed `set` of existing relative paths), not `Path.resolve()` per link. Fall back to `resolve()` only for symlinks.
- Expected: 5–10× faster lint on 300+ articles.

**P2.2 Minor**
- `lint_wiki` acquires and releases a `FileLock` for every `.md.lock` that exists. Since every written article leaves a `.lock`, this is O(n) lock syscalls. Consider skipping it, or checking only files modified in the last few seconds.
- `.navigation_registry.json` rewrites `registered_at` on every write, which causes churn. Only update it when title, summary or section changes.

---

## 5. Expected impact (estimate)

| Change | Round trips saved per session close | Output tokens saved |
|---|---|---|
| P0.1 + P0.2 + P0.3 (no retry chains) | 3–10 | 3k–15k |
| P0.4 (no duplicate output) | 0 | 0 (input tokens roughly halved per tool result) |
| P0.5 (handoffs out of INDEX) | avoids later purge/fix sessions | INDEX stays small |
| P1.1 + P1.2 (auto-nav, inline lint) | 2 | small |
| P1.3 (edit) | 0–2 (no need to read then rewrite) | 1k–5k |
| P1.4 / session_close | 2–6 | small |
| P1.5 (handoff schema) | 1–4 | 0.5k–2k |

A realistic target is **2–4 tool calls and under 30–45 s** for a typical end-of-session update, down from about 8–20 calls and 70–400 s observed.

---

## 6. Implementation constraints and checklist

- **CLI/MCP symmetry** is enforced by `tests/test_symmetry.py` (`mcp_tools ⊆ cli_subs`, and `cli_subs − mcp_tools == {init, update}`). Every new MCP tool (`edit`, `write-many`, `schema`, `session-close`) needs a matching CLI subcommand in `cli/dispatch.py::WHITELIST`.
- **ADRs:** amend ADR-004 for the field auto-fill (P0.3). Add new ADRs for auto-navigation on write (P1.1) and for partial-edit and batch semantics (P1.3/P1.4).
- **Quality gates:** keep `mypy --strict`, `ruff`, and the current test coverage.
- **Tests to add:**
  - multi-error validation message contains every violation plus a template;
  - MCP write error includes `actionable`;
  - auto-fill of `type`/`last_updated`/`date`;
  - tools return `structuredContent is None`;
  - a handoff does not appear in INDEX;
  - nav regeneration is atomic and locked;
  - `edit` validates the resulting content;
  - `write_many` is all-or-nothing on validation;
  - handoff accepts `previous_handoff_ref=None`/`"initial"`;
  - lint performance benchmark (300 articles < 300 ms) as a non-blocking test.
- **Wiki:** after implementing, update the self-wiki (`features/`, `architecture/`, `changelog/v1.md` or a new `v1.1`), then run `brain79 lint --strict`.

## 7. Suggested order of work

1. P0.4 (one-line decorator change + test)
2. P0.5 (bug fix + regression test)
3. P0.1 + P0.2 (multi-error validation, schema exposure)
4. P0.3 + ADR-004 amendment
5. P1.5, P1.6, P1.7
6. P1.1 + P1.2 + ADR
7. P1.3, then P1.4 (with CLI equivalents)
8. P2.1 / P2.2
