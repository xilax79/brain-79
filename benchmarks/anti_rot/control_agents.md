# Repository engineering and documentation protocol

## Overview
This repository (`LedgerPulse`) contains a Python accounting/invoicing core (`src/ledgerpulse/`) and a JavaScript ESM report validator/CLI (`src/reporter/`). Maintain accurate, up-to-date Markdown documentation under `docs/` alongside all code changes.

## Documentation maintenance rules
1. **Keep `docs/` synchronized with code**: whenever you add, modify, rename, move, or remove public modules, functions, classes, constants, or business rules under `src/`, update the corresponding documentation in `docs/` in the same session.
2. **Accurate references**: verify that every file path, symbol name, signature, and constant documented in `docs/` matches the actual implementation on disk. Remove or mark superseded any outdated rules or renamed symbols.
3. **Architecture and decisions**: record significant bugfixes, business-rule changes, or architectural decisions in `docs/decisions/` with clear rationale and status (`active` or `superseded`).
4. **Module coverage**: ensure `docs/architecture.md` and `docs/modules/` reflect the current directory layout and public APIs of both `src/ledgerpulse/` and `src/reporter/`.

## Session triage discipline
Classify every task before editing documentation:
- **Read-only consultation (Type A)**: when asked only to answer questions, inspect code, or explain behavior without changing code or producing new research, make **zero** permanent edits to `docs/`, `README.md`, or `src/`.
- **Zero-code research and analysis (Type B)**: when asked to perform domain research, analysis, or design evaluation without modifying source code, make **zero** edits to `src/` and persist your findings in `docs/research/<slug>.md`.
- **Code and workspace changes (Type C)**: when modifying source code, tests, or configuration, update all affected `docs/` articles accurately and run the test suites (`pytest` and `node --test`) before finishing.

## Verification
- Python tests: `pytest`
- JavaScript tests: `node --test`
