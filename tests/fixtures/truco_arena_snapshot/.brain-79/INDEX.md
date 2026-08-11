# Truco Arena Project Index

> **Read this first at the start of every session.**
> This is the entry point to the project's wiki. It reflects the current state of the project.
>
> Wiki structure and curation rules: see [SCHEMA.md](SCHEMA.md).

---

## Project

**Name:** Truco Arena
**Purpose:** Competitive 1v1 online Argentine Truco web application featuring Cyber-Billiard green aesthetics and Baraja Española card engine.
**Status:** **Rules Engine COMPLETE** (Phase 1–3 of `concept/engine-plan.md`). TUI and UI next.

---

## Current focus

- **Canonical rules of Argentine Truco COMPLETE** in `concept/truco-rules.md` (951 lines) — source of truth for the rules engine.
- **13 real-card simulation scenarios** in `concept/truco-simulations.md` as oracle for engine validation (includes SIM-08b for Contra Flor chain).
- **Rules engine COMPLETE** in `engine/` (7 modules, ~1900 lines TS):
  - `engine/types.ts`, `engine/events.ts`, `engine/errors.ts` — contracts
  - `engine/deck.ts` — deterministic shuffle with seed
  - `engine/scoring.ts` — Envido/Flor/Truco Quiero/No quiero tables
  - `engine/state.ts` — state machine (~1170 lines, see Technical Debt)
  - `engine/index.ts` — `Match` class + `createMatch()` API
- **39 tests passing** (13 SIM + 15 adversarial + 11 edge cases), zero flakiness.
- **§16 + Appendix D all closed**. Oracles audited against `truco-rules.md §1.2` hierarchy.
- **Apéndices A–F**: regional variants, simulation oracles, source discrepancies, product decisions, online adaptations, obsolete presencial rules.
- Next: TUI (Phase 4 of `engine-plan.md`) and refactor of `state.ts` into modules.

---

## Recent decisions

### Engine architecture
- **Stack**: TypeScript strict + Vitest + Ink (TUI, Phase 4). No DOM, no React, no network in `engine/`.
- **Determinism**: deck accepts seed; tests reproducible (`tests/helpers.ts:createMatchWithHands`).
- **Result<Ok, Err>** for invalid actions — engine does NOT mutate on error.
- **Engine owns the timer** — client calls `dispatch({type:'TIMER_EXPIRED'})`. Anti-cheat by design.
- **Match scope**: 30 points only (no 15, no Mejor de 3), 1v1 only (no teams).
- **Flor always active** in MVP; configurable per room later.

### Truco chain (§8)
- **Quiero / No quiero table**: Truco=2/1, Retruco=3/2, Vale Cuatro=4/3.
- **"Tener el quiero" rule enforced** (§8.3): only `quieroHolderId` can raise. After raise, transfers to opponent.
- **Raise timing is NOT immediate** (§8.3.1): team with "el quiero" can raise at any point during the hand.
- **Vale Cuatro is the maximum**: no further raises allowed.
- **Mal Truco ladder**: Mal Truco=1, Mal Retruco=2, Mal VC=3 (level−1). Envido independent.

### Envido chain (§6)
- **Quiero = sum of bets in cycle**. No quiero = sum minus last bet (Wikipedia/Ludoteka confirmed).
- **Idempotency** (D.9): each team sings each canto type at most once. "Repetition" comes from the rival singing the same/higher canto.
- **Envido mandatory state tracking**: `active` flag distinguishes "never sung" vs "sung-and-resolved" vs "sung-pending".
- **Falta Envido dinámico**: ambos en Malas → partido completo; one/both en Buenas → distancia a 30. Closes match instantly if leader wins.
- **Mazo post-envido**: 1 truco (envido ya cobrado). Mazo pre-envido: 2 pts (1 envido implícito + 1 truco).
- **Mazo con truco cantado**: paga valor del QUIERO (2/3/4), no del no-quiero. Si truco fue cantado, anula envido implícito.

### Flor chain (§7)
- **Flor levels are discrete** (3 → 4 → 6 → dynamic), NOT additive like Envido.
- **No quiero pays previous level's value** (1, 1, 3, 6), not cumulative sum.
- **Auto-resolve when rival has no Flor**: 3 pts automáticos al cantor (spec §7.3). NO pending response required.
- **Contra Flor / Contra Flor al Resto**: solo cuando ambos equipos tienen Flor.
- **MANO wins ties** in Flor declaration (mano mata a pie universal).

### Hand resolution (§5)
- **Parda decision table** (8 rows): all 3 pardas → MANO; otherwise first non-parda wins.
- **Round starter**: R1 starts with MANO. R2/R3 starts with R1/R2 winner; if parda, MANO starts.
- **No "non-starter parda credit"** (rejected — was an invention, not in truco rules).
- **Card hierarchy** (15 ranks): Anchos falsos (1O, 1C) tied at rank 7. All 12/11/10 tied within their rank.
- **Card notation**: E=Espadas, B=Bastos, O=Oros, C=Copas. No emojis in code.

### Source materials
- **TrucoGame.com**: primary source for reglas.
- **Wikipedia (es)**: cross-reference, especially for seña table and decision matrix.
- **Ludoteka**: confirmed envido idempotency ("La primera apuesta de envido puede ser revocada con un nuevo envido").

---

## Quick navigation

### Core knowledge
- [Product overview](product/overview.md)
- [Game Table Architecture](architecture/game-table.md)

### Repo references (canonical specs live in git, not in the wiki)
These are part of the repository under `concept/` and `engine/`. They are referenced here for discoverability but live as code artifacts:

- `concept/truco-rules.md` — official Truco rules (951 lines, source of truth)
- `concept/truco-simulations.md` — 13 simulation oracles
- `concept/engine-plan.md` — engine roadmap (5 phases)
- `concept/engine-spec.md` — engine executable contract
- `concept/table-spec.md` — table UI specification
- `concept/mocks/index.html` — interactive table mockup
- `concept/draft.md` — product concept draft

### Engine source
- `engine/{types,events,errors,deck,scoring,state,index}.ts`

### Tests
- `tests/sim/sim-all.test.ts` — 13 SIM tests against oracles
- `tests/adversarial.test.ts` — 15 adversarial tests covering edge cases
- `tests/adv-final.test.ts` — 11 final-pass tests (untracked; for review sessions)

---

## Technical debt

Known issues carried over from the rules engine iteration. Each item has a recommended resolution path.

### TD-1: `engine/state.ts` is monolithic (1170 lines, single file)

**Impact**: hard to navigate, hard to test in isolation, reviewer fatigue.
**Cause**: Iterative development prioritized correctness over structure.
**Recommendation**: split into `engine/state/hand.ts` (hand lifecycle), `state/envido.ts`, `state/truco.ts`, `state/flor.ts`, `state/mazo.ts`, `state/index.ts` (orchestrator). Estimated 4–6 hours.
**Priority**: medium (block for Phase 4+ work if not addressed).

### TD-2: Tests not split per SIM (spec §9 violation)

**Impact**: harder to locate failures, harder to attribute test runs to specific oracles.
**Cause**: worker put all 13 SIM in one file (`sim-all.test.ts`) instead of 13 separate files.
**Recommendation**: split into `tests/sim/sim-01.test.ts` through `sim-12b.test.ts` (13 files). Mechanical refactor.
**Priority**: low (cosmetic; tests pass).

### TD-3: Edge case undocumented: truco NO querido + mazo

**Impact**: the engine currently charges trucoPts again when mazo happens after truco no quiero. Engine behavior is debatable.
**Cause**: not specified in truco-rules.md; engine interprets "truco cantado" as including no-querido cases.
**Recommendation**: clarify in `truco-rules.md §9.2` whether truco is "closed" after no quiero. If yes, mazo after no quiero should not re-charge truco.
**Priority**: low (edge case; documented in `INDEX.md` §Recent decisions as known interpretation).

### TD-4: Flor auto-detect omission not enforced (F.4 fair play)

**Impact**: a player can omit Flor intentionally without auto-sanction. Relies on rival noticing.
**Cause**: hard to detect "intentional omission" in online mode; falls under F.4 fair play.
**Recommendation**: Apéndice F.5 marks this as "must implement" but worker didn't add it. Future work: at start of R1, if player has Flor and rival hasn't sung, force a declaration event or apply auto-sanction.
**Priority**: medium (security/integrity).

### TD-5: Truco `accepted` field unused in `EnvidoBetState`

**Impact**: dead state field; `active` is used instead.
**Cause**: defensive design in `types.ts` not cleaned up.
**Recommendation**: remove `accepted` field or document why it exists.
**Priority**: low.

### TD-6: Three-phase canto identification not enforced strictly

**Impact**: cantos can be sung in some non-canonical orders (e.g., Real Envido before Envido is valid, but FE before RE without Envido first is not validated in some paths).
**Cause**: canto validation is mostly idempotency-based, not strict sequence-based.
**Recommendation**: add explicit sequence validation in `handleEnvidoCanto`: reject FE if no prior Envido/RE.
**Priority**: medium (correctness).

### TD-7: Hand history events not included in event stream

**Impact**: observers (TUI, audit log) don't see `HAND_RESOLVED` with full context.
**Cause**: worker emits `HAND_RESOLVED` but doesn't include `envidoPts`, `trucoPts`, `florPts` consistently in all paths.
**Recommendation**: ensure every `HAND_RESOLVED` event includes all 3 point fields (with 0 if N/A).
**Priority**: low.

### TD-8: No snapshot tests for engine state

**Impact**: regressions in state shape would not be caught by exact-equality tests.
**Cause**: tests use `expect(score).toBe(X)` but don't capture full state.
**Recommendation**: add snapshot tests for representative hands.
**Priority**: low.

### TD-9: Timer not actually implemented (state flag only)

**Impact**: `timer` field exists in `HandState` but no automatic expiration; client must dispatch `TIMER_EXPIRED`.
**Cause**: client-driven timer (per D.1 decision). Functional but no self-test.
**Recommendation**: add tests that dispatch `TIMER_EXPIRED` and verify auto-IR-AL-MAZO behavior.
**Priority**: medium.

### TD-10: Mal Envido detection limited

**Impact**: a player can declare `tantos` incorrectly; engine should validate.
**Cause**: declared `tantos` accepted without verification against actual cards.
**Recommendation**: at FLOR_RESOLVED / ENVIDO_RESOLVED, validate declared tantos against actual cards. If mismatch, apply Mal Envido sanction.
**Priority**: high (correctness — but covered by test SIM-09 currently).

---

## Roadmap

### Now (immediate)
- ✅ **Rules Engine COMPLETE** (this iteration).
- Squash-merge `feat/truco-rules-engine` into `main`.
- Update `package.json` scripts to include `test:adversarial` and `test:all` aliases.

### Next sprint (Phase 4 — TUI)
- **TUI mínima con Ink**: render mesa + cartas + anotador + timer, input via keyboard.
- **CLI flags**: `--sim=N` (run a specific SIM), `--play` (interactive), `--seed=42`.
- **Audit log writer**: dump all events to a file for replay/debugging.
- **Resolve TD-1**: split `state.ts` into modules before adding TUI complexity.

### Phase 5 (Polish)
- **Snapshot tests** for state shape (TD-8).
- **Performance**: profile state machine with 10k hand simulation.
- **Documentation**: README with how-to-run, how-to-add-new-SIM.
- **Resolve TD-2**: split tests into 13 files.

### Future (post-engine)
- **WebSocket layer** for multiplayer sync (TBD — needs design).
- **Web UI integration**: connect engine to `concept/table-spec.md` UI components.
- **Replay system**: persist hand history, allow replay with deterministic seeds.
- **ELO ranking system**: track wins/losses per user.
- **Spectator mode**: passive viewer with delay.
- **Multi-language support**: interface in Spanish (default) + English.

### Speculative (research)
- **Bot AI**: train or rule-based bot for solo practice.
- **Variant support**: Pata de Gallo (3-player), 6-player Pica-Pica (per Wikipedia §2.1). Requires re-architecting types for teams.
- **Auto-detect Flor omission** (TD-4): requires "did the player see their cards?" tracking. Complex but high integrity value.

### Out of scope (explicit)
- Teams (2v2, 3v3) — Truco Arena is 1v1 only.
- 15-point or "Mejor de 3" matches — only 30-point matches.
- Chat, emotes, anti-cheat ML — deferred to platform layer.

---

## Known issues / gotchas

- **Production Build Rule**: The top navigation bar `nav.proto-controls` ("DEMO ESCENARIOS") in `concept/mocks/index.html` is strictly a prototype controller for testing game scenarios in the browser. It **MUST BE OMITTED** when building the production `GAME_TABLE` screen.
- Player hand cards must be centered using `margin: 0 auto`. The `IR AL MAZO` button must be positioned with `left: calc(50% + 175px)` so it doesn't disturb the centered hand axis.
- **`npm test`** may not include `tests/adversarial.test.ts` depending on shell glob expansion. Use `npx vitest run` to be sure.
- **`state.ts` is 1170 lines** — see TD-1. Refactor before adding TUI.
- **Don't remove `accepted` field from `EnvidoBetState`** without checking — it's referenced in tests even if not used.
- **`tests/adv-final.test.ts` is untracked** — review-session only. Not part of CI.