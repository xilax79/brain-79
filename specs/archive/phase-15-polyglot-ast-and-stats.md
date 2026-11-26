---
spec_id: SPEC-015
title: Polyglot AST guards, context budget telemetry, and language-agnostic documentation
target_version: v0.16.0
status: implemented
owner: xilax
last_updated: 2026-11-24
related_wiki:
  - architecture/roadmap-industrial-scale.md
  - architecture/current-state.md
  - architecture/dispatcher.md
  - architecture/symmetry.md
  - features/transitive-drift-and-ripple-guards.md
  - features/version-governance.md
  - features/cli.md
  - features/project-upgrade-and-multi-harness-doctor.md
  - decisions/adr-010-orient-and-3-signal-context-ranking.md
  - decisions/adr-012-structural-quality-and-drift-detection.md
  - decisions/adr-019-external-specs-and-requirements-standard.md
  - decisions/adr-020-focused-mcp-surface-and-cli-superset.md
target_wiki:
  - decisions/adr-022-polyglot-ast-guards-and-context-stats.md
  - features/polyglot-ast-guards-and-stats.md
  - features/transitive-drift-and-ripple-guards.md
  - features/version-governance.md
  - features/cli.md
  - features/project-upgrade-and-multi-harness-doctor.md
  - architecture/dispatcher.md
  - architecture/symmetry.md
  - architecture/current-state.md
  - architecture/roadmap-industrial-scale.md
  - product/overview.md
  - changelog/v0-16-0.md
---

# SPEC-015 — Polyglot AST guards, context budget telemetry, and language-agnostic documentation

## Problem statement and goal

Although `brain-79`'s core memory protocol (SHA-256 Merkle drift tracking, DAG ripple gates, `orient()`, passive lifecycle hooks, and `ci-check`) is completely language-agnostic, Guard C (AST public API signature verification during `session_commit(verified_articles=...)`) is currently hardcoded to Python (`.py`) files in `session_commit.py` and `python_inspector.py`. In addition, developers and teams lack a deterministic CLI command to inspect wiki token budgets, `orient()` savings versus loading the full wiki or root instruction files, governance coverage, and active AST guard coverage. This phase generalizes Guard C across the pluggable `LanguageInspector` registry via a dedicated orchestrator module, ships an optional zero-core-impact `brain79[polyglot]` Tree-sitter extra providing 10 polyglot language parsers from 9 grammar packages (TypeScript, TSX, JavaScript/JSX, Go, Rust, Java, C#, PHP, Ruby, and Bash) alongside built-in Python (11 parsers total), introduces strictly read-only CLI telemetry (`brain79 stats`), and updates public documentation to clearly communicate `brain-79`'s language-agnostic architecture and extensible AST registry.

## Non-goals (out of scope)

- **No new MCP tools**: per [ADR-020](../.brain-79/decisions/adr-020-focused-mcp-surface-and-cli-superset.md), `MCP_TOOLS` remains fixed at 9 focused hot-path tools. `brain79 stats` is strictly a CLI-only subcommand (`WHITELIST` expands from 25 to 26 subcommands).
- **No mandatory Tree-sitter or tokenizer dependencies in core**: `[project].dependencies` in `pyproject.toml` MUST remain unchanged (`fastmcp`, `filelock`, `pyyaml`). `brain-79` MUST NOT require `tree-sitter`, `tiktoken`, or any compiled C extension for default installation; token estimates in `brain79 stats` use a deterministic zero-dependency heuristic (`math.ceil(chars / 4)` over LF-normalized text).
- **No full semantic type-checking or cross-file resolution**: Guard C inspects single-file syntax trees (`base_source` vs. `current_source`). It MUST NOT invoke external compilers (`tsc`, `go`, `cargo`, `javac`, `dotnet`, `php`, `ruby`, `shellcheck`), resolve cross-file imports, or execute target source code.
- **No dynamic metaprogramming inference**: for dynamic languages (Ruby `define_method`/`method_missing`, PHP `__call`, JavaScript runtime `Object.defineProperty`), Guard C inspects static AST declarations conservatively rather than guessing runtime mutations, prioritizing zero false positives.
- **No Phase 16 or Phase 17 deliverables**: longitudinal multi-session LLM anti-rot benchmarking (`Phase 16`, `v0.17.0`) and PyPI Trusted Publishers release automation (`Phase 17`, `v0.18.0`) are explicitly deferred to subsequent roadmap phases.

## Dependencies

- **Internal seams**:
  - `src/brain79/core/ast_guards/` (`LanguageInspector` protocol, `SignatureDiff`, `PythonInspector`, and extension registry shipped in Phase 10).
  - `src/brain79/core/session_commit.py` (Guard C enforcement during `verified_articles` validation).
  - `src/brain79/core/git_ops.py` (`GitSessionCache`, `git_last_commit_for_path`, `git_rev_parse_head`, `git_show_blob`).
  - `src/brain79/core/drift.py` (`WorkspaceIndex`, `detect_all_drift`, `match_applies_to_pattern`, `INACTIVE_STATUSES`, `PRE_IMPLEMENTATION_STATUSES`).
  - `src/brain79/core/orient.py` (`orient`, `MAX_ORIENT_INLINE_CHARS`).
  - `src/brain79/core/frontmatter.py` (`load_active_schema`, `parse_frontmatter`, `ValidationError`).
  - `src/brain79/core/validation.py` (`MAX_ARTICLE_BYTES`, `MAX_ARTICLE_LINES`).
  - `src/brain79/core/doctor.py` (`run_doctor`, `DoctorCheck`, 9 canonical check categories).
  - `src/brain79/cli/dispatch.py` and `src/brain79/__main__.py` (CLI whitelist and dispatcher).
- **External / optional**:
  - Core install: zero new dependencies.
  - Optional extra `brain79[polyglot]` declared under `[project.optional-dependencies]` in `pyproject.toml`: `tree-sitter>=0.25,<0.26` plus ABI-compatible version ranges for the 9 official grammar packages: `tree-sitter-typescript`, `tree-sitter-javascript`, `tree-sitter-go`, `tree-sitter-rust`, `tree-sitter-java`, `tree-sitter-c-sharp`, `tree-sitter-php`, `tree-sitter-ruby`, and `tree-sitter-bash`.

## Constraints and invariants

All requirements must preserve the repository's canonical invariants:

- **Versioning**: pre-GA minor bump (`0.16.0`) per [ADR-017](../.brain-79/decisions/adr-017-semantic-version-calibration-for-pre-ga-maturation.md) and single-source parity per [ADR-013](../.brain-79/decisions/adr-013-versioning-and-release-governance.md).
- **Concurrency and cross-platform I/O**: lock hierarchy, POSIX path normalization, and atomic LF writes per [ADR-014](../.brain-79/decisions/adr-014-centralized-locks-and-cross-platform-io.md). `brain79 stats` is strictly read-only on `.brain-79/` and the workspace (zero disk writes to `.brain-79/` or workspace files, including zero `.drift_manifest.json`, `.navigation_registry.json`, or `.locks/` creation).
- **CLI and MCP symmetry**: MCP-subset / CLI-superset invariant (`MCP_TOOLS` ⊂ `WHITELIST`, 9 MCP tools ⊂ 26 CLI subcommands) per [ADR-020](../.brain-79/decisions/adr-020-focused-mcp-surface-and-cli-superset.md) and [symmetry.md](../.brain-79/architecture/symmetry.md).
- **Exit codes**: POSIX exit code policy (`0`, `1`, `2`, `3`, `130`) per [dispatcher.md](../.brain-79/architecture/dispatcher.md).
- **Documentation style**: clean B2 English, sentence case first, and living manual rules (`<= 20 KB`, `<= 400` lines, zero temporal markers in living manual titles/overviews) per [ADR-015](../.brain-79/decisions/adr-015-sentence-case-first-policy.md) and [ADR-018](../.brain-79/decisions/adr-018-living-manuals-and-temporal-decontamination.md).
- **Zero-dependency core and graceful degradation invariant**: importing `brain79` or executing any CLI/MCP command MUST succeed identically with or without `brain79[polyglot]` installed. Missing grammar packages MUST degrade cleanly to SHA-256 hash-based drift tracking without raising `ImportError`, and `uv run mypy src tests` MUST pass cleanly in **both** core-only and polyglot-installed environments despite `warn_unused_ignores = true`.
- **Fail-closed operational integrity invariant (Guard C)**: when an AST inspector IS registered for a modified governed file, symlink escapes outside `project_root`, unreadable/non-UTF-8 files, Git operational/timeout failures, or unexpected parser runtime crashes MUST fail closed via `ValidationError` (blocked under `strict`/`balanced`, downgraded to warning only under `advisory`). Conversely, non-Git workspaces (`NotAGitRepoError`), empty `base_rev`, files without a registered inspector, and oversized generated/minified files (`> MAX_AST_SOURCE_BYTES`, evaluated on **either** base or current source before invoking any inspector) MUST degrade safely to `(False, "")`.
- **Doctor check count invariant**: on a clean repository (with or without `brain79[polyglot]` installed), `run_doctor()` MUST continue returning the 9 canonical check categories so existing CI and unit test contracts (`tests/test_project_upgrade_and_doctor.py`, `tests/test_ci_workflow.py`) remain unbroken.

## Open questions

All design decisions have been aligned with the `owner` (`xilax`):

- [x] **Q-1 (Normative polyglot language set)**: **`POLYGLOT_LANGUAGES` = 10 parsers from 9 grammar packages + built-in Python (11 parsers total)** — `("bash", "c_sharp", "go", "java", "javascript", "php", "ruby", "rust", "tsx", "typescript")` via `brain79[polyglot]` using a single declarative `TreeSitterInspector` engine over official PyPI `tree-sitter-*` grammar wheels, alongside zero-dependency stdlib `ast` Python (`"python"`).
- [x] **Q-2 (Token estimation strategy for `brain79 stats`)**: **Zero-dependency deterministic heuristic (`math.ceil(len(lf_text) / 4)`) paired with exact byte and character counts** — avoids adding `tiktoken` or model-specific BPE tables to core dependencies, keeps character/line/token counts identical across Windows/macOS/Linux via LF normalization, and reports exact on-disk bytes alongside estimated tokens.
- [x] **Q-3 (Roadmap decomposition for anti-rot and PyPI)**: **Split into dedicated subsequent phases** — Phase 15 (`v0.16.0`) delivers Polyglot AST + `brain79 stats` + language-agnostic documentation; Phase 16 (`v0.17.0`) owns the longitudinal multi-session LLM anti-rot release gate; Phase 17 (`v0.18.0`) owns automated PyPI distribution via GitHub Actions Trusted Publishers.

## Requirements (EARS)

To allow a developer agent to implement and verify Phase 15 cleanly without friction or regressions, requirements are organized into five sequential stages (`Stage 1` → `Stage 2` → `Stage 3` → `Stage 4` → `Stage 5`).

### Stage 1 — Language-agnostic Guard C orchestrator and AST registry (`src/brain79/core/ast_guards/`, `session_commit.py`, `drift.py`)

- **R-1.1**: THE new module `src/brain79/core/ast_guards/orchestrator.py` SHALL define `MAX_AST_SOURCE_BYTES = 2_097_152` (2 MB) and `has_public_api_changes(project_root: Path, rel_posix_path: str, article_path: str, current_content: str | None = None, wiki_root: Path | None = None, git_cache: GitSessionCache | None = None) -> tuple[bool, str]` (re-exported from `src/brain79/core/ast_guards/__init__.py` and `src/brain79/core/drift.py`, importing `git_last_commit_for_path`, `git_rev_parse_head`, and `git_show_blob` directly from `brain79.core.git_ops` to avoid circular imports) which:
  1. Looks up `inspector = get_inspector_for_path(rel_posix_path)`. If `inspector is None`, returns `(False, "")` immediately with zero filesystem reads and zero Git subprocess calls.
  2. Validates path containment inside `project_root.resolve()`, raising `ValidationError(rule="path_outside_project_root", ...)` on symlinks or `..` traversals escaping `project_root`.
  3. When `current_content is None`, returns `(False, "")` if the target file does not exist on disk; otherwise reads UTF-8 text, raising `ValidationError(rule="ast_verification_failed", ...)` on `OSError` or `UnicodeDecodeError`.
  4. Checks size BEFORE Git blob comparison for `current_content`: if `len(current_content.encode("utf-8")) > MAX_AST_SOURCE_BYTES`, returns `(False, "")` immediately across ALL inspectors (including `PythonInspector`).
  5. Resolves the baseline Git revision (`git_last_commit_for_path` for the governing article, falling back to `git_rev_parse_head`) and baseline blob (`git_show_blob`), reusing `git_cache` when provided. On `NotAGitRepoError`, returns `(False, "")`; if `not base_rev`, returns `(False, "")`; on `(GitTimeoutError, GitError, OSError)`, raises `ValidationError(rule="ast_verification_failed", ...)`.
  6. If `base_content is not None` and `len(base_content.encode("utf-8")) > MAX_AST_SOURCE_BYTES`, returns `(False, "")` immediately (preventing asymmetric-size false positives when a file crosses the 2 MB threshold between base and current).
  7. When `base_content is None` (file newly introduced after `base_rev`), calls `inspector.extract_signatures(current_content)` and returns `(True, f"new public symbol '{sorted(curr_sigs.keys())[0]}' in {rel_posix_path}")` if non-empty, else `(False, "")`.
  8. When `base_content is not None`, calls `inspector.compare_sources(base_content, current_content, rel_posix_path)` and returns `(diff.has_changes, diff.description)`.
  9. IF `inspector.extract_signatures()` or `inspector.compare_sources()` raises any unexpected exception (other than `ValidationError`), THEN `has_public_api_changes()` SHALL catch it and raise `ValidationError(rule="ast_verification_failed", path=article_path, ...)` (fail-closed).
- **R-1.2**: THE existing `has_public_python_api_changes(...)` function in `src/brain79/core/ast_guards/python_inspector.py` SHALL remain frozen in place and exported from `brain79.core.ast_guards`, `brain79.core.ast_guards.python_inspector`, and `brain79.core.drift` with 100% backward-compatible signature and module-level Git imports (preserving existing unit test patches such as `patch("brain79.core.ast_guards.python_inspector.git_last_commit_for_path", ...)` in `tests/test_drift.py`). `PythonInspector` SHALL also declare optional attribute `language: str = "python"` and iterate changed keys in deterministic `sorted()` order in `compare_sources()`.
- **R-1.3**: WHEN `commit_session()` in `src/brain79/core/session_commit.py` initializes its `WorkspaceIndex` and evaluates Guard C for modified governed targets under `verified_articles`, THE commit engine SHALL:
  1. Instantiate a session-scoped `git_cache = GitSessionCache()` and pass it into `WorkspaceIndex.build(p_root, w_root, git_cache=git_cache)` so `ws_index.git_cache` is always populated across multiple targets.
  2. Replace the hardcoded `.endswith(".py")` check with `get_inspector_for_path(target_path) is not None` and invoke `has_public_api_changes(p_root, target_path, v_path, wiki_root=w_root, git_cache=ws_index.git_cache)`.
  3. Enforce the existing tier policy (`strict`: raise `ValidationError(rule="verified_article_public_signature_changed", ...)`; `balanced` and `advisory`: record downgraded warning; `ValidationError` from `ast_verification_failed` / `path_outside_project_root`: raise under `strict`/`balanced`, downgrade to warning under `advisory`).
- **R-1.4**: THE registry in `src/brain79/core/ast_guards/__init__.py` SHALL preserve `LanguageInspector` in `base.py` untouched (do NOT add `language` to the `@runtime_checkable` `Protocol`, avoiding breaking third-party inspectors) and SHALL provide:
  1. Normative constant `POLYGLOT_LANGUAGES: tuple[str, ...] = ("bash", "c_sharp", "go", "java", "javascript", "php", "ruby", "rust", "tsx", "typescript")` (10 language parser identifiers backed by 9 optional Tree-sitter grammar packages).
  2. `register_inspector(inspector: LanguageInspector) -> None` (overriding existing registrations for declared extensions), `unregister_extensions(extensions: Iterable[str]) -> None`, `get_inspector_for_path(path: str | Path) -> LanguageInspector | None`, and `list_registered_extensions() -> tuple[str, ...]`.
  3. `get_ast_guard_capabilities() -> dict[str, Any]` reading inspector language identifiers via `getattr(inspector, "language", type(inspector).__name__.lower())` and returning deterministic keys:
     - `"built_in"`: `["python"]`
     - `"polyglot_runtime_available"`: `bool` (`importlib.util.find_spec("tree_sitter") is not None` and `tree_sitter` imports cleanly)
     - `"polyglot_installed"`: `bool` (`True` when `polyglot_runtime_available` is `True` and at least one `POLYGLOT_LANGUAGES` parser is validated and active)
     - `"active_languages"`: sorted `list[str]` of active language identifiers (always includes `"python"`, plus all validated polyglot languages and any registered custom inspectors)
     - `"missing_grammars"`: sorted `list[str]` of `POLYGLOT_LANGUAGES` entries whose optional runtime or grammar package is not installed (when `tree_sitter_typescript` is missing, both `"tsx"` and `"typescript"` appear in `missing_grammars`)
     - `"broken_grammars"`: `dict[str, str]` mapping any `POLYGLOT_LANGUAGES` entry whose package is installed but failed `Language(...)` initialization (non-`ImportError`/`ModuleNotFoundError`) to a concise error string
     - `"registered_extensions"`: sorted `list[str]` of all currently registered file extensions.

### Stage 2 — Optional `brain79[polyglot]` Tree-sitter engine and 10 polyglot parsers (`pyproject.toml`, `src/brain79/core/ast_guards/treesitter_inspector.py`, `polyglot.py`)

- **R-2.1**: THE `pyproject.toml` manifest SHALL:
  1. Keep `[project].dependencies` strictly unchanged (`fastmcp>=2.0.0`, `filelock>=3.32.2`, `pyyaml>=6.0.0`).
  2. Declare `[project.optional-dependencies] polyglot` pinned to an ABI-consistent `tree-sitter` minor range (`tree-sitter>=0.25,<0.26`) alongside compatible version bounds for the 9 official grammar packages (`tree-sitter-typescript`, `tree-sitter-javascript`, `tree-sitter-go`, `tree-sitter-rust`, `tree-sitter-java`, `tree-sitter-c-sharp`, `tree-sitter-php`, `tree-sitter-ruby`, `tree-sitter-bash`) verified against `uv sync --group dev --extra polyglot`, committing the regenerated `uv.lock`.
  3. Declare `[[tool.mypy.overrides]]` for `module = ["tree_sitter", "tree_sitter_*"]` with `ignore_missing_imports = true` and `follow_untyped_imports = false` so `uv run mypy src tests` passes cleanly in BOTH core-only and polyglot environments with `warn_unused_ignores = true`. Inline `# type: ignore[import-not-found]` comments on Tree-sitter imports are FORBIDDEN; dynamic grammar loading MUST use `importlib.import_module(...)` inside typed loader helpers returning `Any` / `object`.
- **R-2.2**: THE `src/brain79/core/ast_guards/treesitter_inspector.py` module SHALL implement a reusable, declarative `TreeSitterInspector` class conforming to `LanguageInspector` (with attribute `language: str`):
  1. Uses direct AST node traversal (`Node.children`, `Node.named_children`, `Node.child_by_field_name`, `Node.type`, `Node.text`) — MUST NOT rely on the version-volatile `tree_sitter.Query` / `QueryCursor` API.
  2. Uses `tree_sitter.Parser(tree_sitter.Language(lang_ptr))` compatible with `tree-sitter>=0.25,<0.26`.
  3. Produces canonical, deterministic `SignatureDiff` messages (sorting added, removed, and changed symbol keys):
     - Added symbol: `f"added public symbol '{sorted(added)[0]}' in {rel_path}"`
     - Removed symbol: `f"removed public symbol '{sorted(removed)[0]}' in {rel_path}"`
     - Changed symbol: `f"changed public signature for '{sorted(changed)[0]}' in {rel_path}"`
     - No public API change: `SignatureDiff(False, "")`
  4. Normalizes extracted signatures strictly via **AST child-node traversal** omitting comment node types (`comment`, `line_comment`, `block_comment`, `documentation_comment`) and collapsing whitespace runs to single spaces — MUST NOT apply regex comment stripping to raw source text (which would corrupt string literals such as `"http://example.com"`). Parameter default values and public decorators/annotations/attributes attached to a public declaration SHALL be included in its normalized signature string where structurally exposed by the grammar (matching `PythonInspector`).
  5. Enforces `MAX_AST_SOURCE_BYTES = 2_097_152` inside `extract_signatures()` as defense-in-depth (returning `{}` if exceeded).
  6. **Syntax-error semantics**:
     - During `extract_signatures()`, individual declarations whose signature header (name, modifiers, parameters, return type) contains `has_error` or `is_missing` SHALL be skipped while valid sibling declarations remain extracted.
     - During `compare_sources()`, IF `current_source.strip()` is non-empty, the parsed `current_tree.root_node.has_error` is `True`, and zero public symbols were extracted (`curr_sigs == {}`), THEN `compare_sources()` SHALL return `SignatureDiff(True, f"unparseable source in {rel_path}")` (avoiding misleading `"removed public symbol"` messages when a file becomes syntactically broken under `strict`); conversely, if `base_source.strip()` is non-empty, `base_tree.root_node.has_error` is `True`, and `base_sigs == {}`, while `curr_sigs` is non-empty, return `SignatureDiff(True, f"added public symbol '{sorted(curr_sigs)[0]}' in {rel_path}")`. If both are unparseable or empty with `{}` extracted, return `SignatureDiff(False, "")`.
- **R-2.3**: THE `src/brain79/core/ast_guards/polyglot.py` module SHALL define declarative specs for all 10 `POLYGLOT_LANGUAGES` parsers using **collision-free qualified symbol keys** (qualifying nested types with enclosing namespace/class/module names, qualifying methods with receiver/owner type, and disambiguating overloaded methods/constructors in TypeScript, Java, and C# by appending their normalized parameter-type list, e.g., `method Outer.Inner.parse(String, int)`):
  1. **`typescript`** (`.ts`, `.mts`, `.cts` → `tree_sitter_typescript.language_typescript()`) and **`tsx`** (`.tsx` → `tree_sitter_typescript.language_tsx()`):
     - Public symbols: `export` functions (`export [async] function`), `export default` functions/classes, `export class` (non-`private`/non-`protected`/non-`#` constructors, methods, properties, accessors), `export interface` (member signatures), `export type`, `export enum`, `export namespace` / `export module` / `declare module` (recursing into exported members), `export const`/`let`/`var` (arrow/function signatures or typed constants), `export { a, b as c } [from "..."]`, `export * [as ns] from "..."`, and `export = <ident>`.
     - Ignored: non-exported declarations, `private`/`protected`/`#` class members, function/method bodies, and comments.
  2. **`javascript`** (`.js`, `.mjs`, `.cjs`, `.jsx` → `tree_sitter_javascript.language()`):
     - Public symbols: `export` functions (`export [async] function`), `export default` functions/classes, `export class` (non-`#`/non-`_` constructors and methods), `export const`/`let`/`var` (arrow/function expressions or exported constants), `export { ... }`, `export * [as ns] from "..."`, and top-level CommonJS `exports.<name> = ...`, `module.exports.<name> = ...`, and `module.exports = { ... }` / `module.exports = function/class ...`.
     - Ignored: non-exported declarations, `#private` and `_`-prefixed class members, function/method bodies, and comments.
  3. **`go`** (`.go` → `tree_sitter_go.language()`):
     - Public symbols: top-level declarations whose identifier starts with an uppercase character (`name[0].isupper()`): `function_declaration` (`func Name`), `method_declaration` (`func (<NormalizedRecvType>) Name` — only when method name is uppercase), `type_declaration` (exported `struct` exported fields & types, exported `interface` method signatures, and exported type aliases/definitions), and top-level exported `const`/`var` declarations (name + explicit type if declared).
     - Ignored: lowercase (unexported) functions, methods, types, struct fields, variables, function bodies, and comments.
  4. **`rust`** (`.rs` → `tree_sitter_rust.language()`):
     - Public symbols: items with exact external `pub` visibility modifier (strictly excluding `pub(crate)`, `pub(super)`, `pub(in ...)`): `function_item` (generics, params, return type, `async`/`unsafe`/`const` qualifiers), `struct_item` (generics + `pub` fields), `enum_item` (generics + variants/payloads), `trait_item` (generics + trait method signatures), `type_item`, `const_item`/`static_item` (name + type), `impl_item` (`pub fn` methods qualified as `fn <Type>::name` or `fn <Type as Trait>::name`), and inline `pub mod <name> { ... }` (recursing with module prefix while NOT recursing into private `mod <name> { ... }`).
     - Ignored: private items, `pub(crate)`/`pub(super)`/`pub(in ...)` items, items inside private `mod` blocks, function/method bodies, and comments.
  5. **`java`** (`.java` → `tree_sitter_java.language()`):
     - Public symbols: `public` `class_declaration`, `interface_declaration`, `enum_declaration`, and `record_declaration` (with type parameters, record components, and nested `public` types qualified as `Outer.Inner`). Inside public classes/enums/records: `public` constructors, `public` methods (disambiguated by normalized parameter types), and `public` fields (type + name). Inside `public` interfaces: all methods and constants except `private` ones.
     - Ignored: `private`, `protected`, and package-private members, method bodies, and comments.
  6. **`c_sharp`** (`.cs` → `tree_sitter_c_sharp.language()`):
     - Public symbols: `public` `class_declaration`, `struct_declaration`, `record_declaration`, `interface_declaration`, `enum_declaration`, and `delegate_declaration` (at top level, inside block `namespace Foo { ... }`, or after file-scoped `namespace Foo;`, qualified by namespace and enclosing types). Inside public types: `public` constructors, `public` methods (disambiguated by normalized parameter types), `public` properties (type + name + public accessor presence), `public` fields, `public` events, and nested `public` types (plus non-`private`/non-`internal` interface members).
     - Ignored: `private`, `internal`, `protected`, and implicit-private members, method/accessor bodies, and comments.
  7. **`php`** (`.php` → `tree_sitter_php.language_php()` with fallback to `language()`):
     - Public symbols: top-level or namespaced `function_definition` (excluding `_`-prefixed names), `class_declaration`, `interface_declaration`, `trait_declaration`, and `enum_declaration` (qualified by namespace). Inside classes/interfaces/traits/enums: `method_declaration` with `public` or omitted visibility modifier (PHP default is public; excluding `private`/`protected` and `_`-prefixed names except `__construct`), `public` properties, and non-`private`/non-`protected` class constants.
     - Ignored: `private`/`protected` members, function/method bodies, and comments.
  8. **`ruby`** (`.rb` → `tree_sitter_ruby.language()`):
     - Public symbols: top-level `method` (`def`) excluding `_`-prefixed names; `module` and `class` declarations (qualified across nested `module`/`class` namespaces). Inside a `class`/`module` body: track section visibility linearly starting at `public` (`private`/`protected`/`module_function` switches subsequent methods until `public` resets it; inline `private def`/`protected def`, `private :sym`/`protected :sym`, and `private_class_method :sym` exclude those symbols; `module_function :sym` exposes a singleton method while making the instance method private); record public `def` (including `initialize`, excluding `_`-prefixed names), `def self.<name>`, methods inside `class << self` blocks (tracking visibility inside the eigenclass), and public `attr_reader`/`attr_writer`/`attr_accessor` declared symbol names.
     - Ignored: `private`/`protected` methods, `_`-prefixed methods, method bodies, dynamic metaprogramming calls (`define_method`, `method_missing`), and comments.
  9. **`bash`** (`.sh`, `.bash` → `tree_sitter_bash.language()`):
     - Public symbols: top-level `function_definition` (`foo() { ... }` and `function foo { ... }`) whose name does not start with `_`, top-level `export -f <name>` function exports (non-`_`), and top-level exported environment variables (`export VAR` / `export VAR=...` / `declare -x VAR` / `declare -x VAR=...`) whose variable name does not start with `_` (recording the exported variable name only, ignoring assigned value literals so internal default tweaks do not cause false positives).
     - Ignored: `_`-prefixed helper functions/variables, non-exported variables, commands inside function bodies, and comments.
- **R-2.4**: WHEN `brain79.core.ast_guards` is imported, THE loader SHALL use **metadata-only discovery** (`importlib.util.find_spec(...)`) without eagerly importing `tree_sitter` or any compiled grammar `.so`/`.pyd` module:
  1. When `find_spec("tree_sitter")` is `None`, register only `PythonInspector` (`.py`), raise zero errors/warnings, and report `polyglot_runtime_available: False`, `polyglot_installed: False`, `active_languages: ["python"]`, `missing_grammars: list(POLYGLOT_LANGUAGES)`, `broken_grammars: {}` via `get_ast_guard_capabilities()`.
  2. When `find_spec("tree_sitter")` is present, register lazy `TreeSitterInspector` instances only for those `POLYGLOT_LANGUAGES` whose grammar package spec (`find_spec(module_name)`) exists; grammars whose package spec is `None` are recorded in `missing_grammars`.
- **R-2.5**: WHEN a lazily registered polyglot grammar is first accessed via `get_inspector_for_path()` (for a matching extension) OR when `get_ast_guard_capabilities()` is invoked, THE loader SHALL validate and memoize `Language(ptr)` once under a `threading.Lock`:
  1. If `importlib.import_module(...)` raises `ImportError`/`ModuleNotFoundError`, record the language in `missing_grammars` and unregister its extensions (returning `None` from `get_inspector_for_path()`).
  2. If initialization raises any other exception (e.g., ABI mismatch `ValueError`/`RuntimeError`/`OSError`), record the concise error in `broken_grammars[lang]`, unregister its extensions, return `None` from `get_inspector_for_path()` (never crashing callers or preventing healthy grammars from working), and surface the broken grammar in `get_ast_guard_capabilities()` and `brain79 doctor`.
- **R-2.6**: THE `TreeSitterInspector` and `polyglot.py` loaders SHALL be safe for concurrent read-only invocations across threads: lazy `Language` validation/memoization is guarded by a `threading.Lock`, and each `extract_signatures()` call constructs or thread-isolates its `tree_sitter.Parser(language)` instance so concurrent threads never share mutable C parser state.

### Stage 3 — Read-only context budget telemetry engine (`src/brain79/core/stats.py`, `orient.py`) and CLI (`brain79 stats`)

- **R-3.1**: THE `src/brain79/core/stats.py` module (and optional keyword-only parameters on core `orient()` in `src/brain79/core/orient.py`) SHALL provide:
  1. `estimate_tokens(text: str) -> int` normalizing `\r\n` to `\n` and returning `0` for empty strings and `math.ceil(len(lf_text) / 4)` otherwise (documented deterministic cross-platform heuristic).
  2. Optional keyword-only parameters `workspace_index: Any = None, git_cache: Any = None` on core `orient()` in `src/brain79/core/orient.py` (leaving MCP `brain79_orient` in `src/brain79/server.py` completely unchanged): when `workspace_index` is supplied, `orient()` reuses `workspace_index` (including `workspace_index.project_root`) and `git_cache` instead of rebuilding a duplicate `WorkspaceIndex`.
  3. Typed dataclass `StatsReport` with `to_dict() -> dict[str, Any]` and `format_text() -> str`, and `compute_stats(project_root: Path | None = None, wiki_root: Path | None = None, *, task: str | None = None, paths: list[str] | None = None, max_articles: int = 4) -> StatsReport`.
  4. Strictly read-only execution inside `with project_context(p_root, w_root):` using one shared `GitSessionCache` and `WorkspaceIndex` across `stats`, `detect_all_drift()`, and `orient()`, making zero disk writes to `.brain-79/` or workspace files (never creating `.drift_manifest.json`, `.navigation_registry.json`, or `.locks/`).
  5. Explicit error signaling without swallowing I/O faults during stats' own file reads:
     - Raise `FileNotFoundError` with an actionable `"run brain79 init"` message ONLY when `.brain-79/` or `.brain-79/INDEX.md` does not exist.
     - Raise `PermissionError` / `OSError` directly (mapped to CLI exit `3`) if any wiki article or `INDEX.md` is unreadable.
     - Raise `ValidationError` (mapped to CLI exit `1`) if `.brain-79/SCHEMA.md` is malformed/unparseable.
     - Raise `ValueError` if `max_articles < 1`.
- **R-3.2**: THE `StatsReport.to_dict()` payload SHALL expose deterministic, JSON-serializable top-level sections (computing `chars`, `lines`, and `estimated_tokens` from LF-normalized text `raw_bytes.decode("utf-8").replace("\r\n", "\n")` while `bytes` reports exact on-disk byte length, and computing aggregate token sums as the sum of per-file `estimate_tokens()` values):
  1. `"wiki"`:
     - `profile`: active schema profile (`"software"` | `"general"`)
     - `enforcement`: active schema enforcement tier (`"strict"` | `"balanced"` | `"advisory"`)
     - `total_articles`: count of all governed `.md` articles under `.brain-79/` regardless of status (excluding `INDEX.md`, `SCHEMA.md`, `_raw/`, `.locks/`, `handoffs/`)
     - `active_articles`: count of governed articles whose `status` is not in `INACTIVE_STATUSES | PRE_IMPLEMENTATION_STATUSES` and whose `stability` is not in `{"archived", "deprecated"}`
     - `articles_by_type`: `dict[str, int]` sorted alphabetically by article `type` (articles with missing or unparseable frontmatter `type` are grouped under `"unknown"` without raising)
     - `total_bytes`, `total_chars`, `estimated_tokens`: summed across all governed articles
     - `index_lines`, `index_max_lines`, `index_bytes`, `index_chars`, `index_estimated_tokens`
     - `handoff_count`: count of `.md` files in `handoffs/`
     - `largest_articles`: up to 5 largest governed articles sorted descending by `bytes` (tie-broken ascending by `path`), each containing `{"path": str, "bytes": int, "lines": int, "estimated_tokens": int, "over_limit": bool}` where `over_limit` is `True` ONLY for living-manual types (`type` not in `{"decision", "changelog"}`, per ADR-018) exceeding `MAX_ARTICLE_BYTES` or `MAX_ARTICLE_LINES`.
  2. `"context_budget"`:
     - `token_estimator`: `"chars_div_4_ceil"`
     - `orient_chars`, `orient_bytes`, `orient_estimated_tokens` (measured from `orient(task=task, paths=paths, max_articles=max_articles, wiki_root=w_root, workspace_index=ws, git_cache=git_cache)`)
     - `orient_budget_chars`: `MAX_ORIENT_INLINE_CHARS` (`64000`)
     - `orient_budget_utilization_pct`: unclamped `round((orient_chars / MAX_ORIENT_INLINE_CHARS) * 100.0, 1)` (may exceed `100.0` if `INDEX.md` + handoff alone exceed 64 KB)
     - `full_wiki_chars`: `total_chars + index_chars`
     - `full_wiki_estimated_tokens`: `wiki["estimated_tokens"] + index_estimated_tokens`
     - `savings_vs_full_wiki_pct`: `round(((full_wiki_chars - orient_chars) / full_wiki_chars) * 100.0, 1)` when `full_wiki_chars > 0` else `0.0`
     - `instruction_files`: list of detected root instruction harnesses (`AGENTS.md`, `CLAUDE.md`, `.cursor/rules/brain79.mdc`, `.github/copilot-instructions.md`) with `{"path": str, "bytes": int, "chars": int, "estimated_tokens": int}`
     - `instruction_files_estimated_tokens`: sum of per-file `estimated_tokens` across `instruction_files`.
  3. `"coverage"`:
     - `total_workspace_files`: count of non-wiki files in `WorkspaceIndex.all_paths` (`not p.startswith(f"{wiki_rel}/")`)
     - `governed_workspace_files`: count of unique non-wiki files matched by `applies_to` of at least one active article (checking both `status not in (INACTIVE_STATUSES | PRE_IMPLEMENTATION_STATUSES)` and `stability not in {"archived", "deprecated"}`, reusing `match_applies_to_pattern` / `WorkspaceIndex`)
     - `ungoverned_workspace_files`: `total_workspace_files - governed_workspace_files`
     - `coverage_pct`: `round((governed_workspace_files / total_workspace_files) * 100.0, 1)` when `total_workspace_files > 0` else `0.0`
     - `drifted_articles_count`: count of unique drifted articles from `detect_all_drift(...)`
     - `drift_items_count`: total drift records from `detect_all_drift(...)`
     - `drifted_articles`: sorted `list[str]` of unique drifted article paths.
  4. `"ast_guards"`:
     - All fields from `get_ast_guard_capabilities()`
     - `governed_files_ast_covered`: count of `governed_workspace_files` for which `get_inspector_for_path(p) is not None`
     - `governed_files_ast_coverage_pct`: `round((governed_files_ast_covered / governed_workspace_files) * 100.0, 1)` when `governed_workspace_files > 0` else `0.0`.
- **R-3.3**: THE `StatsReport.format_text()` method SHALL render a concise, human-readable Markdown/plain-text report titled `# Brain-79 — Context and Governance Statistics` displaying wiki inventory (total & active articles), `orient()` token budget and utilization, full-wiki comparison & instruction file sizes, workspace & AST Guard C coverage, active/missing/broken polyglot parsers, drift summary, and largest articles (flagging any `over_limit` living manual).
- **R-3.4**: THE CLI dispatcher (`src/brain79/cli/dispatch.py` and `ROOT_HELP` in `src/brain79/__main__.py`) SHALL add `"stats"` to `WHITELIST` (26 subcommands total; `MCP_TOOLS` remains 9) with `prog="brain79 stats"`, honoring global `--project-root` and supporting:
  - `--format <text|json>` (default: `"text"`).
  - `--task <TEXT>` (optional task description passed to `orient()` simulation).
  - `--paths <PATH ...>` (`nargs="*"`, mirroring `brain79 orient --paths` at `dispatch.py:937` for consistent CLI UX; also splitting comma-separated elements if a user passes a single comma-joined token).
  - `--max-articles <INT>` validated directly in `argparse` via a custom `type=_positive_int` helper (rejecting `< 1` or non-integers with `argparse.ArgumentTypeError` → guaranteed POSIX exit code `2`, never falling through to `map_exception_to_exit_code(ValueError)` → `1`; default: `4`).
  - Exit codes: `0` on success, `1` on malformed `SCHEMA.md` (`ValidationError`), `2` on invalid arguments or missing `.brain-79/` / `INDEX.md` (`FileNotFoundError`), `3` on `PermissionError` / `OSError`.

### Stage 4 — Doctor diagnostics and CI polyglot verification (`src/brain79/core/doctor.py`, `.github/workflows/ci.yml`)

- **R-4.1**: WHEN `run_doctor()` executes the `binary_and_environment` check in `src/brain79/core/doctor.py`, THE diagnostic engine SHALL:
  1. Include the active AST Guard C summary inside the existing `binary_and_environment` check message derived dynamically from `POLYGLOT_LANGUAGES` and `get_ast_guard_capabilities()` (e.g., `AST guards: python (built-in); install brain79[polyglot] for 10 more language parsers` when polyglot is absent, or `AST guards: python + <N> polyglot parsers (<list>)` when active), preserving the exact 9 canonical check categories on clean repositories.
  2. IF `get_ast_guard_capabilities()["broken_grammars"]` is non-empty, THEN emit an additional `DoctorCheck(category="ast_guards", status="warning", ...)` with actionable reinstall guidance (`uv tool install --reinstall "brain79[polyglot]"`).
- **R-4.2**: THE repository CI workflow (`.github/workflows/ci.yml`) SHALL preserve `jobs.test` unchanged (verifying zero-dependency core across all 5 OS/Python matrix cells enforced by `tests/test_ci_workflow.py`) AND add a `test-polyglot` job with:
  - Matrix: `ubuntu-latest`, `macos-latest`, `windows-latest` on Python `3.12` (`fail-fast: false`, `timeout-minutes: 20`).
  - `defaults.run.shell: bash` and job-level `env: {BRAIN79_REQUIRE_POLYGLOT: "1", PYTHONUTF8: "1", BRAIN79_PERF_FACTOR: "3"}` (ensuring identical cross-platform execution on Windows and Unix).
  - Pinned action tags (`actions/checkout@v7`, `astral-sh/setup-uv@v10.4.0`, `actions/upload-artifact@v7`).
  - Steps: `uv sync --group dev --extra polyglot`, full suite `uv run pytest -q --basetemp="${RUNNER_TEMP:-/tmp}/.pytest_tmp"` (proving zero regressions across doctor/CLI/all 780+ tests when polyglot is installed), `uv run mypy src tests`, `uv run brain79 stats --format json | uv run python -c "import json, sys; json.load(sys.stdin)"`, and `if: failure()` artifact upload of `.pytest_tmp`.

### Stage 5 — Language-agnostic positioning, release `v0.16.0` parity, and living manual distillation

- **R-5.1**: THE public documentation (`README.md`, `USER_GUIDE.md`, `ARCHITECTURE.md`) SHALL be updated to:
  1. State prominently in `README.md` (above the fold and in `## Limitations and trade-offs`) that `brain-79` is **language-agnostic by design** (Merkle SHA-256 drift, `orient()`, hooks, and CI gates work in any repository regardless of programming language), while **AST Guard C** provides built-in Python verification plus optional deep signature guards for **10 additional language parsers (TypeScript, TSX, JavaScript/JSX, Go, Rust, Java, C#, PHP, Ruby, and Bash)** via `brain79[polyglot]`, and exposes a pluggable `LanguageInspector` registry for community language extensions.
  2. Update `"25-command"` / `"25"` CLI subcommand counts to `"26-command"` / `"26"` across `README.md`, `USER_GUIDE.md`, `ARCHITECTURE.md`, `src/brain79/templates/AGENTS.md`, and `src/brain79/templates/SKILL.md`, update the `README.md` version badge to `0.16.0`, document `brain79 stats`, and keep `"9 hot-path tools"`, `"Python 3.11+"`, `"AST Guard C"`, `"TF-IDF"`, and all 5 native harness paths intact.
  3. Update `USER_GUIDE.md` with `brain79[polyglot]` installation instructions, the supported 11-parser language matrix, `brain79 stats` usage examples, and a concise recipe for registering a custom `LanguageInspector`.
  4. Update `ARCHITECTURE.md` module map and AST subsystem documentation to reflect `orchestrator.py`, `treesitter_inspector.py`, `polyglot.py`, and `stats.py`.
- **R-5.2**: THE symmetry, CLI, CI, version, and release documentation tests (`tests/test_symmetry.py` including its docstring, `tests/test_phase14_ci_check_and_hooks.py` line 770 `len(WHITELIST) == 26`, `tests/test_phase11_release_docs.py`, `tests/test_ci_workflow.py`, `tests/test_version_governance.py`) and release metadata (`src/brain79/__init__.py` `__version__ = "0.16.0"`, `CHANGELOG.md`, `.brain-79/changelog/v0-16-0.md`, `src/brain79/templates/AGENTS.md`, `src/brain79/templates/SKILL.md`, and repository harness blocks via `brain79 update-project`) SHALL be synchronized to `0.16.0` with `len(WHITELIST) == 26` and `len(MCP_TOOLS) == 9`, keeping `src/brain79/templates/AGENTS.md` `<= 6,500` bytes.
- **R-5.3**: THE architectural decision (`decisions/adr-022-polyglot-ast-guards-and-context-stats.md`) and new/updated living manuals (`features/polyglot-ast-guards-and-stats.md`, `features/transitive-drift-and-ripple-guards.md` with explicit non-overlapping `ast_guards/` file paths replacing `ast_guards/**`, `features/version-governance.md`, `features/cli.md`, `features/project-upgrade-and-multi-harness-doctor.md`, `architecture/dispatcher.md`, `architecture/symmetry.md`, `architecture/current-state.md`, `architecture/roadmap-industrial-scale.md`, `product/overview.md`) SHALL be committed via `brain79_session_commit` (after `stats.py` and the new AST modules exist on disk) with zero documentation drift and zero overlapping `applies_to` violations.

## Interface and error contract

Aligned with [dispatcher.md](../.brain-79/architecture/dispatcher.md) (`0` success, `1` validation/operational failure, `2` invalid argument or `FileNotFoundError`, `3` `PermissionError`/`TimeoutError`/`OSError`, `130` interrupt).

| Interface / input | Failure or edge condition | Expected behavior (`fail-closed` / fallback) | Exit code / exception |
|---|---|---|---|
| `has_public_api_changes(...)` | Extension has no registered inspector (or `brain79[polyglot]` not installed) | Graceful no-op; zero disk reads and zero Git calls | Returns `(False, "")` |
| `has_public_api_changes(...)` | Symlink or `..` traversal escaping `project_root` | Fail closed; reject path | `ValidationError(rule="path_outside_project_root")` |
| `has_public_api_changes(...)` | Target file unreadable or invalid UTF-8 bytes | Fail closed; actionable error | `ValidationError(rule="ast_verification_failed")` |
| `has_public_api_changes(...)` | Base OR current source exceeds `MAX_AST_SOURCE_BYTES` (2 MB) | Safe fallback before calling any inspector (avoids asymmetric false blocks) | Returns `(False, "")` |
| `has_public_api_changes(...)` | Non-Git workspace (`NotAGitRepoError`) or empty `base_rev` | Graceful fallback; skip AST diff | Returns `(False, "")` |
| `has_public_api_changes(...)` | Git timeout, corrupt repo, or subprocess `OSError` | Fail closed under `strict`/`balanced`; warning under `advisory` | `ValidationError(rule="ast_verification_failed")` |
| `has_public_api_changes(...)` | Unexpected runtime exception inside inspector | Fail closed under `strict`/`balanced`; warning under `advisory` | `ValidationError(rule="ast_verification_failed")` |
| `TreeSitterInspector.compare_sources()` | Non-empty `current_source` is completely unparseable (`root.has_error` and `{}` extracted) | Emit explicit unparseable diff instead of misleading `"removed public symbol"` | `SignatureDiff(True, "unparseable source in <rel_path>")` |
| `brain79.core.ast_guards` import | `tree-sitter` or subset of `tree-sitter-*` grammars missing | Metadata-only discovery (`find_spec`); register Python + available lazy specs; report missing in capabilities | No exception |
| `get_inspector_for_path()` / `get_ast_guard_capabilities()` | Grammar package installed but raises non-`ImportError` on `Language()` init | Unregister broken grammar, record in `broken_grammars`, return `None`, surface warning in `doctor` | No exception at runtime; `doctor` exit `2` |
| `session_commit(verified_articles=...)` | Public signature changed in any registered language (`strict` tier) | Block commit; instruct agent to update governing article | `ValidationError(rule="verified_article_public_signature_changed")` / CLI exit `1` |
| `session_commit(verified_articles=...)` | Public signature changed (`balanced` / `advisory` tier) | Allow commit with downgraded warning in receipt | Exit `0` (with warning) |
| `brain79 stats` | Valid wiki (clean or drifted) | Emit text report (or JSON when `--format json`) to `stdout`; zero writes to `.brain-79/` or workspace | Exit `0` |
| `brain79 stats` | Malformed `.brain-79/SCHEMA.md` | Emit actionable stderr error; zero disk writes | `ValidationError` / Exit `1` |
| `brain79 stats` | Missing `.brain-79/` or `INDEX.md` | Emit actionable stderr error suggesting `brain79 init` | `FileNotFoundError` / Exit `2` |
| `brain79 stats --max-articles 0` | Non-positive `--max-articles` or unknown `--format` | Rejected directly by `argparse` (`type=_positive_int`); zero disk writes | Exit `2` |
| `brain79 stats` | Unreadable wiki file (`PermissionError` / `OSError`) | Emit actionable stderr error without swallowing read failure; zero disk writes | Exit `3` |

## Migration and rollout

- **Default behavior**: 100% backward-compatible. Repositories installing base `brain79` without `[polyglot]` continue running with Python built-in Guard C and zero new dependencies. Existing `has_public_python_api_changes()` callers, third-party `LanguageInspector` implementations, and `brain79 doctor` 9-check expectations remain unchanged.
- **Upgrade path**:
  - No wiki schema migration (`SCHEMA.md` stays at `schema_version: 2`).
  - Users wanting polyglot AST guards install `uv tool install --reinstall "brain79[polyglot]"` (or `pip install "brain79[polyglot]"`).
  - Running `brain79 update-project` refreshes managed `AGENTS.md` / `SKILL.md` protocol headers to `v0.16.0` (updating `"25-command"` to `"26-command"`).
- **Rollback safety**: downgrading from `v0.16.0` back to `v0.15.0` leaves `.brain-79/` 100% readable and valid (no new frontmatter fields, no new cache files).

## Acceptance criteria (Given / When / Then)

### AC-1 — Language-agnostic Guard C orchestrator, size guard, and backward compatibility
- **Verifies**: `R-1.1`, `R-1.2`, `R-1.4`
- **Method**: `test`
- **Test ref**: `tests/test_phase15_polyglot_ast.py::test_unregistered_extension_zero_disk_and_git_calls`, `tests/test_phase15_polyglot_ast.py::test_custom_inspector_routing_and_unregister_normalization`, `tests/test_phase15_polyglot_ast.py::test_has_public_api_changes_rejects_symlink_and_traversal`, `tests/test_phase15_polyglot_ast.py::test_has_public_api_changes_missing_and_unreadable_file`, `tests/test_phase15_polyglot_ast.py::test_has_public_api_changes_size_guard_both_directions`, `tests/test_phase15_polyglot_ast.py::test_has_public_api_changes_non_git_and_empty_base_rev`, `tests/test_phase15_polyglot_ast.py::test_has_public_api_changes_git_timeout_and_inspector_crash`, `tests/test_phase15_polyglot_ast.py::test_has_public_api_changes_new_file_base_content_none`, `tests/test_phase15_polyglot_ast.py::test_has_public_python_api_changes_backward_compatibility`, `tests/test_phase15_polyglot_ast.py::test_polyglot_languages_and_capabilities_determinism`, `tests/test_drift.py`
- **Given**: a Git repository with a registered custom `LanguageInspector` (`.custom`, cleaned up in fixture teardown), a `.py` file, and an unregistered `.txt` file.
- **When**: `has_public_api_changes()` is invoked for each file (and `has_public_python_api_changes()` is invoked for `.py` and `.custom`), including symlink escape, unreadable UTF-8, base-or-current `> 2 MB` crossing (`1.9 MB` base vs. `2.1 MB` current), empty `base_rev`, Git timeout, inspector crash, and non-Git workspace scenarios.
- **Then**: `.custom` routes through the registered inspector and detects added/removed/changed public symbols; `.txt` returns `(False, "")` with zero Git calls; crossing `MAX_AST_SOURCE_BYTES` on either base or current returns `(False, "")` without false blocks; symlink escape raises `ValidationError(rule="path_outside_project_root")`; unreadable UTF-8, Git timeout, and inspector crash raise `ValidationError(rule="ast_verification_failed")`; non-Git workspace and empty `base_rev` return `(False, "")`; `has_public_python_api_changes()` preserves existing `.py`-only behavior and `tests/test_drift.py` mock compatibility; `POLYGLOT_LANGUAGES` has 10 sorted identifiers and `get_ast_guard_capabilities()` returns all required keys deterministically.

### AC-2 — `session_commit` Guard C enforcement and `GitSessionCache` reuse for non-Python languages
- **Verifies**: `R-1.3`
- **Method**: `test`
- **Test ref**: `tests/test_phase15_polyglot_ast.py::test_session_commit_guard_c_git_cache_populated_and_reused`, `tests/test_phase15_polyglot_ast.py::test_session_commit_guard_c_non_python_tiers_and_git_cache`, `tests/test_phase15_polyglot_ast.py::test_session_commit_guard_c_fail_closed_tiers`
- **Given**: a Git repository initialized with `.brain-79/` governing non-Python source files (via a registered test inspector) whose public signatures were modified after the governing article was last committed.
- **When**: `commit_session(verified_articles=[{"path": "features/payments.md", "reason": "checked"}])` is called under `strict`, `balanced`, and `advisory` tiers, and again when only an internal body/comment changed.
- **Then**: `WorkspaceIndex` receives a populated `GitSessionCache` reused across Guard C calls; under `strict`, public signature changes raise `ValidationError(rule="verified_article_public_signature_changed")`; under `balanced` and `advisory`, the commit succeeds with a downgraded warning; body/comment-only edits succeed cleanly even under `strict`.

### AC-3 — Zero-dependency core, mypy dual-mode config, lazy discovery, and partial/broken grammar resilience
- **Verifies**: `R-2.1`, `R-2.4`, `R-2.5`
- **Method**: `test`
- **Test ref**: `tests/test_phase15_polyglot_ast.py::test_pyproject_polyglot_and_mypy_overrides_audit`, `tests/test_phase15_polyglot_ast.py::test_metadata_only_lazy_discovery_does_not_import_tree_sitter`, `tests/test_phase15_polyglot_ast.py::test_absent_tree_sitter_degrades_gracefully`, `tests/test_phase15_polyglot_ast.py::test_partial_grammar_install_reports_missing_including_tsx_and_typescript`, `tests/test_phase15_polyglot_ast.py::test_broken_grammar_lazy_init_failure_isolated`, `tests/test_phase15_polyglot_ast.py::test_polyglot_strict_ci_gate`
- **Given**: `pyproject.toml` plus simulated environments where (a) `tree_sitter` spec is absent, (b) `tree_sitter` and only `tree_sitter_go` are present, and (c) `tree_sitter_rust` spec exists but raises `RuntimeError("Incompatible Language version 15")` during lazy `Language()` validation.
- **When**: `pyproject.toml` dependencies and `[[tool.mypy.overrides]]` are inspected, and the loader + lazy validator run under each environment.
- **Then**: `[project].dependencies` contains only `fastmcp`, `filelock`, and `pyyaml`; `polyglot` declares `tree-sitter>=0.25,<0.26` and all 9 grammar packages; `[[tool.mypy.overrides]]` configures `ignore_missing_imports = true` and `follow_untyped_imports = false` for `tree_sitter*`; absent `tree_sitter` yields `polyglot_runtime_available=False`, `active_languages=["python"]`, and all 10 `POLYGLOT_LANGUAGES` in `missing_grammars`; partial install registers available lazy inspectors and lists missing ones (including both `"tsx"` and `"typescript"` when `tree_sitter_typescript` is missing); broken grammar validation unregisters `.rs`, returns `None` from `get_inspector_for_path("lib.rs")`, and records the error in `broken_grammars["rust"]` without affecting healthy grammars.

### AC-4 — TreeSitterInspector AST normalization, syntax-error safety, overload keys, and thread safety
- **Verifies**: `R-2.2`, `R-2.6`
- **Method**: `test`
- **Test ref**: `tests/test_phase15_polyglot_ast.py::test_treesitter_inspector_resilience_url_literals_size_syntax_and_threads`
- **Given**: a `TreeSitterInspector` instance tested against (a) whitespace/comment-only edits plus string literals containing `//` and `/*` (e.g. `"http://example.com"`), (b) a `> 2 MB` payload, (c) completely corrupt `current_source` vs. valid `base_source`, partially broken syntax alongside a valid sibling declaration, and (d) 8 concurrent worker threads calling `extract_signatures()` simultaneously.
- **When**: `compare_sources()` and `extract_signatures()` are executed.
- **Then**: whitespace/comment-only edits return `SignatureDiff(False, "")` without corrupting URL string literals; `> 2 MB` input returns `{}`; totally unparseable `current_source` returns `SignatureDiff(True, "unparseable source in ...")`; partial syntax errors preserve valid sibling symbols while skipping malformed headers; concurrent threads produce identical deterministic results with zero crashes or race errors.

### AC-5 — TypeScript, TSX, JavaScript, and JSX public API extraction
- **Verifies**: `R-2.3`
- **Method**: `test`
- **Test ref**: `tests/test_phase15_polyglot_ast.py::test_polyglot_10_language_matrix`, `tests/test_phase15_polyglot_ast.py::test_polyglot_language_specific_edge_cases`, `tests/test_phase15_polyglot_ast.py::test_polyglot_cycle1_regression_fixes`
- **Given**: `brain79[polyglot]` installed and `.ts`, `.tsx`, `.js`, `.jsx`, `.mjs`, `.cjs` fixtures covering `export function`, `export async function`, `export default`, `export class` (public vs. `private`/`protected`/`#` members and overloaded method signatures), `export interface`, `export type`, `export enum`, `export namespace` / `declare module`, `export const` arrow functions, `export { a, b as c }`, `export * from`, `export =`, and CommonJS `module.exports` / `exports.foo`.
- **When**: `compare_sources()` runs against body-only edits, private-member edits, added/removed exports, and signature changes.
- **Then**: body-only and private-only edits return `has_changes=False`; added/removed exports and public signature changes return `has_changes=True` with deterministic `SignatureDiff` descriptions.

### AC-6 — Go and Rust public API extraction
- **Verifies**: `R-2.3`
- **Method**: `test`
- **Test ref**: `tests/test_phase15_polyglot_ast.py::test_polyglot_10_language_matrix`, `tests/test_phase15_polyglot_ast.py::test_polyglot_language_specific_edge_cases`, `tests/test_phase15_polyglot_ast.py::test_polyglot_cycle1_regression_fixes`
- **Given**: `brain79[polyglot]` installed and `.go` and `.rs` fixtures covering exported vs. unexported Go functions, receiver methods on distinct receivers with the same method name, structs, interfaces, and consts/vars; and Rust `pub` vs. private/`pub(crate)`/`pub(super)` functions, structs, enums, traits, types, consts, multiple `impl` blocks (inherent and trait impls), inline `pub mod`, and `pub` items hidden inside a private `mod`.
- **When**: `compare_sources()` runs against body-only edits, unexported/`pub(crate)`/private-`mod` edits, and public symbol/signature changes.
- **Then**: body-only and non-public edits return `has_changes=False`; public additions, removals, and signature changes (including same-named methods on distinct Go receivers or Rust `impl` blocks) return `has_changes=True` without key collisions.

### AC-7 — Java and C# public API extraction
- **Verifies**: `R-2.3`
- **Method**: `test`
- **Test ref**: `tests/test_phase15_polyglot_ast.py::test_polyglot_10_language_matrix`, `tests/test_phase15_polyglot_ast.py::test_polyglot_language_specific_edge_cases`, `tests/test_phase15_polyglot_ast.py::test_polyglot_cycle1_regression_fixes`
- **Given**: `brain79[polyglot]` installed and `.java` and `.cs` fixtures covering `public` classes, interfaces, enums, records, structs (C#), delegates (C#), nested public types, file-scoped and block namespaces (C#), constructors, overloaded `public` methods, properties, and fields versus `private`/`protected`/`internal`/package-private members.
- **When**: `compare_sources()` runs against body-only edits, non-public edits, overload additions/changes, and public signature changes.
- **Then**: body-only and non-public edits return `has_changes=False`; overload additions/removals and public signature changes return `has_changes=True` with qualified, collision-free symbol keys.

### AC-8 — PHP, Ruby, and Bash public API extraction
- **Verifies**: `R-2.3`
- **Method**: `test`
- **Test ref**: `tests/test_phase15_polyglot_ast.py::test_polyglot_10_language_matrix`, `tests/test_phase15_polyglot_ast.py::test_polyglot_language_specific_edge_cases`, `tests/test_phase15_polyglot_ast.py::test_polyglot_cycle1_regression_fixes`
- **Given**: `brain79[polyglot]` installed and `.php`, `.rb`, and `.sh`/`.bash` fixtures covering PHP functions, namespaced classes/interfaces/traits/enums (explicit `public` + implicit public methods vs. `private`/`protected`), Ruby top-level `def`, nested modules/classes with linear `public`/`private`/`protected`/`module_function` sections, inline `private def`, `private :sym`, `private_class_method`, `def self.foo`, `class << self`, and `attr_reader`/`attr_writer`/`attr_accessor`, and Bash top-level functions (public vs. `_`-prefixed), `export -f`, and `export`/`declare -x` variables.
- **When**: `compare_sources()` runs against body-only edits, private/ignored edits (including Bash exported value changes and `_helper` edits), and public symbol/signature changes.
- **Then**: body-only and private/ignored edits return `has_changes=False`; public additions, removals, and signature changes return `has_changes=True`.

### AC-9 — End-to-end `session_commit` polyglot Guard C integration
- **Verifies**: `R-1.3`, `R-2.3`
- **Method**: `test`
- **Test ref**: `tests/test_phase15_polyglot_ast.py::test_session_commit_polyglot_e2e_guard_c`
- **Given**: a real Git repository with `brain79[polyglot]` installed and `.brain-79/` governing `.ts`, `.go`, `.rs`, and `.sh` files under `enforcement: strict`.
- **When**: a public signature is modified in each file and the agent attempts `commit_session(verified_articles=...)`, then reverts to a body-only edit and retries.
- **Then**: `verified_articles` is blocked with `verified_article_public_signature_changed` for every public signature change and succeeds for every body-only edit.

### AC-10 — Read-only `compute_stats()` accuracy, cross-platform determinism, and zero-mutation guarantee
- **Verifies**: `R-3.1`, `R-3.2`, `R-3.3`
- **Method**: `test`
- **Test ref**: `tests/test_phase15_stats.py::test_estimate_tokens_edge_cases`, `tests/test_phase15_stats.py::test_compute_stats_accuracy_and_edge_cases`, `tests/test_phase15_stats.py::test_compute_stats_unclamped_utilization_and_tie_break`, `tests/test_phase15_stats.py::test_compute_stats_single_workspace_index_and_read_only`, `tests/test_phase15_stats.py::test_compute_stats_error_contracts`
- **Given**: a repository with `.brain-79/` containing articles across multiple types (including one drifted article, one inactive/superseded article, one article with missing `type`, one oversized living manual, and one large immutable ADR/changelog), an `INDEX.md`, a handoff, root `AGENTS.md`/`CLAUDE.md`, and both governed and ungoverned workspace files (without a pre-existing `.drift_manifest.json` or `.navigation_registry.json`).
- **When**: `compute_stats(project_root, wiki_root, task="...", paths=[...], max_articles=4)` is invoked.
- **Then**: all `wiki`, `context_budget`, `coverage`, and `ast_guards` metrics match exact ground truth (`total_articles` vs. `active_articles`, missing `type` under `"unknown"`, `full_wiki_chars` emitted, per-file token sum, `over_limit=True` on oversized living manual and `False` on ADR/changelog, inactive articles excluded from coverage, unclamped `orient_budget_utilization_pct`); `orient()` reuses the shared `WorkspaceIndex` and `GitSessionCache`; `format_text()` renders all sections cleanly; zero files are created or modified inside `.brain-79/` or workspace (excluding `.git/`).

### AC-11 — CLI `brain79 stats` interface and error exit codes
- **Verifies**: `R-3.4`
- **Method**: `test`
- **Test ref**: `tests/test_phase15_stats.py::test_cli_brain79_stats_and_exit_codes`
- **Given**: a valid wiki workspace, a workspace with corrupt `SCHEMA.md`, an unreadable article (Unix non-Windows), and a directory without `.brain-79/`.
- **When**: `brain79 stats`, `brain79 stats --format json --task "auth" --paths src/a.py src/b.py --max-articles 2`, `brain79 stats --max-articles 0`, `brain79 --project-root <corrupt-schema-dir> stats`, `brain79 --project-root <unreadable-dir> stats`, and `brain79 --project-root <no-wiki-dir> stats` are executed via CLI.
- **Then**: valid invocations exit `0` (`--format json` emits valid JSON matching `StatsReport.to_dict()`); corrupt `SCHEMA.md` exits `1`; `--max-articles 0` and missing `.brain-79/` exit `2` with actionable stderr messages; unreadable file exits `3`; `"stats"` appears in `WHITELIST` and `ROOT_HELP`.

### AC-12 — Doctor capability reporting and broken-grammar diagnostics
- **Verifies**: `R-4.1`
- **Method**: `test`
- **Test ref**: `tests/test_phase15_stats.py::test_doctor_ast_guard_capabilities_and_broken_grammars`, `tests/test_project_upgrade_and_doctor.py`
- **Given**: a clean initialized repository tested under (a) core-only install, (b) healthy `brain79[polyglot]` install, and (c) simulated `broken_grammars={"go": "ABI mismatch"}`.
- **When**: `run_doctor()` executes in each state.
- **Then**: states (a) and (b) report exactly the 9 canonical check categories with `exit_code == 0` and include AST guard capability details derived from `POLYGLOT_LANGUAGES` inside `binary_and_environment`; state (c) emits an `ast_guards` warning (`exit_code == 2`) with actionable reinstall instructions.

### AC-13 — CI polyglot job and core matrix preservation
- **Verifies**: `R-4.2`
- **Method**: `test`
- **Test ref**: `tests/test_ci_workflow.py::test_ci_workflow_polyglot_job`, `tests/test_ci_workflow.py`
- **Given**: `.github/workflows/ci.yml`.
- **When**: `tests/test_ci_workflow.py` inspects `ci.yml`.
- **Then**: `jobs.test` preserves all 5 core zero-dependency matrix cells and required steps; `jobs.test-polyglot` exists with `ubuntu-latest`, `macos-latest`, and `windows-latest` on Python `3.12`, `defaults.run.shell: bash`, job-level `env.BRAIN79_REQUIRE_POLYGLOT == "1"`, pinned action versions, `uv sync --group dev --extra polyglot`, full `uv run pytest -q`, `uv run mypy src tests`, and JSON-parsed `brain79 stats --format json`.

### AC-14 — Symmetry, version parity, language-agnostic docs, and wiki distillation
- **Verifies**: `R-5.1`, `R-5.2`, `R-5.3`
- **Method**: `test`
- **Test ref**: `tests/test_symmetry.py`, `tests/test_phase14_ci_check_and_hooks.py`, `tests/test_phase11_release_docs.py`, `tests/test_version_governance.py`, `tests/test_specs_governance.py`
- **Given**: the completed repository at `v0.16.0`.
- **When**: `tests/test_symmetry.py`, `tests/test_phase14_ci_check_and_hooks.py`, `tests/test_phase11_release_docs.py`, `tests/test_version_governance.py`, `tests/test_specs_governance.py`, `brain79 lint --strict`, and `brain79 ci-check` run.
- **Then**: `len(WHITELIST) == 26`, `len(MCP_TOOLS) == 9`, `__version__ == "0.16.0"`, `README.md` (badge `0.16.0`, language-agnostic positioning, `brain79[polyglot]`, `brain79 stats`, `26-command`), `USER_GUIDE.md`, `ARCHITECTURE.md`, `templates/AGENTS.md` (`<= 6,500` bytes), and `templates/SKILL.md` are synchronized; ADR-022 and all `## Wiki impact map` living manuals exist with zero drift and zero overlapping `applies_to`.

## Test implementation guide

Implement tests across two dedicated Phase 15 test suites plus targeted updates to existing suites:

1. **`tests/test_phase15_polyglot_ast.py`** (covers `AC-1` through `AC-9`):
   - **Fixture hygiene**: every test calling `register_inspector()` or `unregister_extensions()` MUST restore global registry state in a `try ... finally` / pytest fixture teardown (ensuring `PythonInspector` remains registered for `.py`).
   - **Core / no-polyglot tests (MUST run unconditionally even without `brain79[polyglot]`)**:
     - Custom `LanguageInspector` registration/unregistration, `has_public_api_changes()` routing, unregistered extension zero-Git fast path, symlink escape (`path_outside_project_root`), unreadable/non-UTF-8 file (`ast_verification_failed`), asymmetric >2 MB size guard (`1.9 MB` base vs. `2.1 MB` current → `(False, "")`), empty `base_rev` → `(False, "")`, Git timeout (`ast_verification_failed`), inspector runtime exception (`ast_verification_failed`), non-Git workspace `(False, "")`, and `has_public_python_api_changes()` backward compatibility.
     - `commit_session(verified_articles=...)` with a custom non-`.py` inspector under `strict`, `balanced`, and `advisory` (verifying `GitSessionCache` reuse, public signature block vs. body-only pass).
     - `pyproject.toml` dependency & mypy override audit (core zero-dep invariant, `tree-sitter>=0.25,<0.26`, 9 grammar packages, `[[tool.mypy.overrides]]` for `tree_sitter*`).
     - Simulated absent `tree_sitter`, partial grammar install (verifying both `"tsx"` and `"typescript"` in `missing_grammars` when `tree_sitter_typescript` is absent), and broken grammar lazy `Language()` failure via `monkeypatch` / `importlib` mocking.
   - **Live Tree-sitter tests (auto-skipped via `pytest.mark.skipif(not POLYGLOT_AVAILABLE, ...)` in core-only `jobs.test`, and strictly enforced with zero skips in `jobs.test-polyglot`)**:
     - Mandatory strict CI gate test: `if os.environ.get("BRAIN79_REQUIRE_POLYGLOT") == "1": assert caps["polyglot_installed"] and not caps["missing_grammars"] and not caps["broken_grammars"]`.
     - Parametrized matrix across all 10 `POLYGLOT_LANGUAGES` parsers (`typescript`, `tsx`, `javascript`, `go`, `rust`, `java`, `c_sharp`, `php`, `ruby`, `bash`): for every parser, assert at minimum: (1) added public symbol → `has_changes=True`, (2) removed public symbol → `has_changes=True`, (3) modified public parameter/return/field signature → `has_changes=True`, (4) internal body edit → `has_changes=False`, (5) comment/whitespace-only edit (including URL string literal `"http://example.com"`) → `has_changes=False`, (6) private/unexported symbol addition/change → `has_changes=False`.
     - Language-specific edge cases: TS/JS re-exports (`export { a }`, `export * from`, `export namespace`, CommonJS `module.exports`), Go same-named methods on distinct receivers, Rust `pub(crate)` vs. `pub` and `pub` inside private `mod`, Java/C# method overloads and nested types + C# file-scoped namespaces, PHP implicit-public methods vs. `protected`/`private`, Ruby `attr_accessor`/`class << self`/`private :sym`/`module_function`, Bash `export -f` and exported variable value-change immunity.
     - Structural resilience: >2 MB source guard returns `{}`, unparseable `current_source` returns `SignatureDiff(True, "unparseable source in ...")`, partial syntax error preserves valid sibling declarations, 8-thread concurrent `extract_signatures()` stress test, and real Git `commit_session(verified_articles=...)` E2E test for `.ts`, `.go`, `.rs`, and `.sh`.
2. **`tests/test_phase15_stats.py`** (covers `AC-10`, `AC-11`, `AC-12`):
   - `estimate_tokens("") == 0`, `estimate_tokens("abcd") == 1`, `estimate_tokens("abcde") == 2`, and CRLF vs. LF parity (`estimate_tokens("a\r\nb") == estimate_tokens("a\nb")`).
   - `compute_stats()` accuracy on a multi-type wiki with active + superseded articles, missing `type` (`"unknown"`), drifted article, oversized living manual vs. large ADR/changelog (`over_limit`), handoff, root `AGENTS.md`/`CLAUDE.md`, and mixed governed/ungoverned workspace files.
   - Read-only verification: assert `.drift_manifest.json`, `.navigation_registry.json`, and `.locks/` are NOT created and all `.brain-79/` and workspace file mtimes/contents remain unchanged before and after `compute_stats()` and `brain79 stats` (excluding `.git/`).
   - CLI `brain79 stats` (`--format text`, `--format json`, `--task`, `--paths src/a.py src/b.py`, `--max-articles`, `--project-root`), plus failure exit codes (`SCHEMA.md` corrupt → `1`, `--max-articles 0` → `2`, missing `.brain-79/` → `2`, unreadable file → `3` with `pytest.mark.skipif(sys.platform == "win32", ...)` for `chmod 000`).
   - `run_doctor()` tests verifying 9-check count preserved with and without `polyglot`, `binary_and_environment` capability text derived from `POLYGLOT_LANGUAGES`, and `ast_guards` warning when `broken_grammars` is simulated.
3. **Existing test suites to update**:
   - `tests/test_symmetry.py`: assert `len(cli_subs) == 26`, `len(MCP_TOOLS) == 9`, and update docstring at line 11.
   - `tests/test_phase14_ci_check_and_hooks.py`: update `len(WHITELIST) == 26` assertion (line 770).
   - `tests/test_phase11_release_docs.py`: assert `"26-command"`, `"brain79[polyglot]"`, `"brain79 stats"`, and language-agnostic wording in `README.md`.
   - `tests/test_ci_workflow.py`: add assertions for `jobs.test-polyglot` (3 OSes, Python `3.12`, `defaults.run.shell: bash`, job-level `env.BRAIN79_REQUIRE_POLYGLOT == "1"`, pinned actions, `--extra polyglot`, full `uv run pytest -q`, `mypy`, and JSON validation of `brain79 stats --format json`).
   - `tests/test_version_governance.py`: verify `v0.16.0` parity across `__init__.py`, `README.md` version badge, `CHANGELOG.md`, and `.brain-79/changelog/v0-16-0.md`.

## Wiki impact map

Note: execute the `features/transitive-drift-and-ripple-guards.md` update (replacing `src/brain79/core/ast_guards/**` with explicit paths) in the same commit as creating `features/polyglot-ast-guards-and-stats.md`, and only AFTER `src/brain79/core/stats.py` and the new AST modules exist on disk, so zero `applies_to` overlap or anti-sprawl subsumption occurs.

| New or modified code paths | Target `.brain-79/` article | Action (`create` / `update` / `verify`) |
|---|---|---|
| `src/brain79/core/ast_guards/treesitter_inspector.py`, `src/brain79/core/ast_guards/polyglot.py`, `src/brain79/core/stats.py` | `features/polyglot-ast-guards-and-stats.md` | `create` |
| `src/brain79/core/ast_guards/__init__.py`, `src/brain79/core/ast_guards/base.py`, `src/brain79/core/ast_guards/orchestrator.py`, `src/brain79/core/ast_guards/python_inspector.py`, `src/brain79/core/session_commit.py`, `src/brain79/core/drift.py`, `src/brain79/core/orient.py` (replace `ast_guards/**` with explicit files) | `features/transitive-drift-and-ripple-guards.md` | `update` |
| `src/brain79/__init__.py`, `pyproject.toml` | `features/version-governance.md` | `update` |
| `src/brain79/core/doctor.py` | `features/project-upgrade-and-multi-harness-doctor.md` | `update` |
| `src/brain79/cli/dispatch.py`, `src/brain79/__main__.py` | `architecture/dispatcher.md` | `update` |
| `src/brain79/cli/dispatch.py`, `src/brain79/__main__.py` | `features/cli.md` | `update` |
| `src/brain79/cli/dispatch.py`, `src/brain79/server.py` | `architecture/symmetry.md` | `update` |
| `README.md`, `USER_GUIDE.md`, `ARCHITECTURE.md`, `.brain-79/features/*.md`, `src/brain79/__init__.py` | `architecture/current-state.md` | `update` |
| `.brain-79/SCHEMA.md`, `.brain-79/features/*.md`, `src/brain79/__init__.py` | `product/overview.md` | `update` |
| `.brain-79/features/*.md` | `architecture/roadmap-industrial-scale.md` | `update` |
| Architectural rationale (polyglot extra + zero-dep stats) | `decisions/adr-022-polyglot-ast-guards-and-context-stats.md` | `create` |
| Release `v0.16.0` summary | `changelog/v0-16-0.md` | `create` |

## Verification gate

All commands must pass with exit code `0` before transitioning status to `implemented`:

```bash
# Core zero-dependency verification
uv sync --group dev
uv run pytest -q
uv run mypy src tests
uv run brain79 lint --strict
uv run brain79 ci-check
uv run brain79 stats
uv run brain79 doctor

# Polyglot extra verification (zero skips allowed; bash shell)
uv sync --group dev --extra polyglot
BRAIN79_REQUIRE_POLYGLOT=1 uv run pytest -q
uv run mypy src tests
uv run brain79 stats --format json | uv run python -c "import json, sys; json.load(sys.stdin)"
```

## Amendments

| Date | Author | Change summary | Impacted IDs |
|---|---|---|---|
| 2026-11-24 | xilax / coordinator | Adversarial audit hardening (Claude Opus 5.5 Medium): normalized `POLYGLOT_LANGUAGES` (10 parsers / 9 grammar packages + Python = 11 total), added `[[tool.mypy.overrides]]` dual-mode config, separated metadata-only `find_spec` import discovery from lock-guarded lazy `Language()` validation, moved 2 MB size guard into `ast_guards/orchestrator.py`, fixed `--max-articles` argparse exit `2` + `SCHEMA.md` exit `1`, aligned `--paths nargs="*"`, specified overload-safe qualified symbol keys and AST comment-node stripping, tightened `stats` formulas (LF normalization, per-file token sum, `active_articles`, `full_wiki_chars`, ADR-018 `over_limit`), fixed `Wiki impact map` non-overlap (`ast_guards/**` split + `features/version-governance.md`), updated `test-polyglot` CI job for Windows bash/env + full pytest, and added `test_phase14_ci_check_and_hooks.py` to test updates. | `R-1.1`–`R-5.3`, `AC-1`–`AC-14` |
| 2026-11-24 | impl-stage-2..5 | Implementation amendments: listed explicit `tree_sitter` and 9 `tree_sitter_*` module names in `[[tool.mypy.overrides]]` because mypy 2.3.0 rejects `"tree_sitter_*"` wildcards; fixed pre-existing global registry leak in `tests/test_ast_guards.py` (`unregister_extensions([".dummy"])` in `try ... finally`); completed Stage 5 wiki distillation, `v0.16.0` release parity, and archival. | `R-2.1`, `R-5.2`, `R-5.3`, `AC-3`, `AC-14` |

## Wiki distillation checklist (post-implementation)

Every item MUST be checked (`[x]`) before setting `status: implemented` and moving this file to `specs/archive/`:

- [x] Execute every row in `## Wiki impact map` (ADR-018 compliant, `<= 20 KB`, non-overlapping `applies_to`).
- [x] Populate `Test ref` on every `AC-*` entry and ensure all amendments are recorded in `## Amendments`.
- [x] Record architectural decision in `.brain-79/decisions/adr-022-polyglot-ast-guards-and-context-stats.md`.
- [x] Add release notes in `CHANGELOG.md` and `.brain-79/changelog/v0-16-0.md`.
- [x] Update `.brain-79/architecture/roadmap-industrial-scale.md` status and archive link.
- [x] Set frontmatter `status: implemented` and move this file to `specs/archive/`.
