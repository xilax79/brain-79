# Brain-79 — Handoff

> Estado al cierre de la sesión de bootstrap (2026-08-10).

---

## Estado actual

**Fase 1 — MVP: COMPLETA y funcionando.**

El sistema está operativo end-to-end: instalación, MCP server, cold start, ingest manual, mid-session reads.

**Fase 1.5 — Handoff: COMPLETA y funcionando.**

La especificación del esquema universal de handoff ha sido diseñada de forma blindada, implementada con sus dos herramientas simétricas (`brain79_handoff_write` y `brain79_handoff_read`), e integrada al FastMCP con coberturas estrictas contra alucinaciones (con validaciones en tiempo de ejecución, tests unitarios en `pytest` configurado con `mypy` y `ruff`).

**Fase 1.7 — Integración Nativa Pi & Cold Start Universal (`AGENTS.md` + `.mcp.json`): COMPLETA y funcionando.**

Despliegue automático e idempotente del manifiesto universal `AGENTS.md` en la raíz del proyecto para estandarizar el protocolo cold start entre múltiples CLIs (`pi`, `agy`, `opencode`), e inyección segura e idempotente del registro de servidor MCP en `.mcp.json`. Pruebas unitarias completas agregadas en `tests/test_init_project.py`.

**Fase 3 — Recuperación de Contexto Inteligente (`brain79_context`): COMPLETA y funcionando.**

Motor TF-IDF de fiabilidad industrial implementado (`src/brain79/core/context.py`) y registrado como herramienta MCP (`brain79_context`). Incluye sanitización NFKC, purgado de contracciones, heurística de límites de palabra (exact match <= 4 caracteres alnum, substring libre para el resto), evacuación ARG_MAX con protección contra FD leaks via POSIX file descriptors, concurrencia paralela con `ThreadPoolExecutor`, fallback a regex puro en Python ante ausencia de `ripgrep`, y cortocircuito en Fallback Mode para queries sin keywords válidas. Cobertura de tests unitarios de 14 pruebas definitivas en `tests/test_context.py`.

**Fase 4 — Instalador Local Cross-Platform (`scripts/install.py`): COMPLETA y funcionando.**

Script de instalación puro minimalista que abstrae `uv tool install --editable .` sin acoplamiento global, incorporando mitigaciones de robustness fail-fast (detección de `uv`, path constraints) y pruebas unitarias sólidas (`tests/test_install.py`).

**Fase 5 — Comando de Actualización (`brain79 update`): COMPLETA y funcionando.**

Comando de CLI `brain79 update` que permite actualizar instalaciones editables directamente desde `origin` con validación estricta de estado git (dirty check, detached HEAD check, default branch check, `--ff-only` pull y rebuild automático con `uv tool install --force .`). Incluye suite de pruebas unitarias (`tests/test_update.py`).

**Fase 6 — Bootstrap de Wiki para Proyectos Legacy (`brain79_bootstrap`): COMPLETA y funcionando.**

Herramienta MCP que escanea proyectos sin historial de wiki y genera un **manifest estructurado** (markdown) para que el LLM escriba artículos semilla mediante `brain79_write`. Principio: *el LLM es la inteligencia, el scanner es los ojos*. El tool es 100% determinístico — no inventa contenido. Características:

- **Budget enforcement**: 80 KB total, 8 KB por archivo raíz, 4 KB por archivo de scope. Lee incremental para no cargar archivos grandes en memoria.
- **Detección de tipo de proyecto**: 12 tipos cerrados (python-package, python-script, node-package, rust-crate, go-module, java-maven, java-gradle, ruby-gem, docker-service, research-paper, documentation, unknown) evaluados en orden de prioridad.
- **Idempotencia**: estado JSON con `filelock` solo en check+write (el scan corre fuera del lock para no bloquear I/O lento). Sin corrupción nunca; reproducible scan en caso de carrera.
- **Seguridad**: validación de paths (out-of-bounds → silently dropped, in-bounds missing → warning), exclusiones (`.git`, `node_modules`, `.venv`, `.brain-79`, caches), skip de archivos binarios y presencia-only (lockfiles).
- **Frontmatter YAML** (`bootstrap: true`, `generated_by`, `generated_at`, `project_type`) en cada artículo generado para trazabilidad.
- **Scope opcional**: `scope="src/auth,src/payments"` para enfocar el scan en subsistemas específicos.

Suite de 69 pruebas unitarias en `tests/test_bootstrap.py` que cubren idempotencia, detección de tipo, scope handling, file budget, tree listing, manifest structure, error resilience, concurrencia, `_truncate_file`, `_resolve_scope_paths`, e integración MCP.

**Fase 7 — Organizational Enforcement: COMPLETA y funcionando.**

Sistema mecánico de enforcement organizacional para prevenir la degradación orgánica de wikis. 10 fases implementadas en el branch `feature/organizational-enforcement` y squash-merged en este handoff. Componentes:

- **Validación de frontmatter estricta** (`core/frontmatter.py`): parser YAML multi-línea con mitigación de BOM/CRLF, validación de campos requeridos por tipo, validación de tipo-ubicación, y 9 tipos cerrados (`navigation`, `handoff`, `product`, `architecture`, `feature`, `decision`, `changelog`, `raw_session`, `raw_commit`).
- **Validación estructural V5** (`core/validation.py`): regex estricto para detección de decision/TD leakage con masking de code fences CommonMark-compliant (tracking de `fence_char` 3+ para ` ``` ` y `~~~`).
- **Navigation registry thread-safe** (`core/navigation.py`): atomic write con `filelock.FileLock`, escape markdown completo de GFM inline chars (`_`, `<`, `>`, `|`, `~`, `` ` ``, `[`, `]`, `*`), validación de path traversal, dedup automático.
- **Lint extendido** (`core/lint_organizational.py`): 9 checks deterministas (`index_size`, `frontmatter_consistency`, `type_location`, `decision_leakage`, `article_atomicity`, `prohibited_content`, `navigation_freshness`, `legacy_articles`, `force_skipped_articles`) con `OrganizationalIssue` dataclass estructurado.
- **Migración progresiva V3** (`core/migration.py`): asignación por defecto de `status: legacy` y `stability: legacy` (preserva intención semántica sin corrupción), atomic write con UUID-based tmp files, `--dry-run` (default) / `--apply` (destructivo) / `--suggest-relocations`.
- **Git pre-commit hook** (`init_project.py` + `core/init_project.py`): hook ejecutable `.git/hooks/pre-commit` invoca `brain79 lint --strict` bloqueando commits con archivos `.brain-79/*.md` modificados. **Mitiga el vector V1** (bypass via edición directa).
- **Cura state-aware** (`core/curate.py`): `WikiStateReport` con violations específicas del wiki actual, integrado en `brain79_ingest` con cap de 500 líneas.
- **Templates reescritos** (`templates/SCHEMA.md`, `templates/INDEX.md`): cumplen las reglas que el propio linter impone (whitelist de headers H2, sin decision patterns).
- **AGENTS.md actualizado** (`templates/AGENTS.md`): documenta los nuevos subcomandos (CLI y MCP), workflow de remediación, política de migration safety, y permite fallback CLI cuando MCP no está conectado.

**Threat model V1-V5 completamente mitigado:**

- **V1** (bypass via edición directa) → git pre-commit hook
- **V2** (INDEX.md scalability catch-22) → Quick navigation auto-generada con registry thread-safe; límite de 150 solo para secciones manuales
- **V3** (migration semantic corruption) → `status: legacy` default preserva intención
- **V4** (YAML parser contradiction) → parser multi-línea con `csv.reader` para listas inline
- **V5** (regex false positives) → regex estricto + CommonMark-compliant fence masking

**Validación end-to-end con Truco Arena north-star:**

- Snapshot inmutable en `tests/fixtures/truco_arena_snapshot/` (21 artículos)
- 4 tests de integración en `tests/test_truco_arena_integration.py`: state violations conocidas, migration agrega `legacy` frontmatter, migration usa `legacy` status, full remediation pasa `lint --strict`
- Script manual de refresh: `tests/fixtures/refresh_truco_arena.sh`

**Quality gates finales:**

- 300/300 tests passing
- mypy strict: 0 errores en 41 source files
- ruff: 0 warnings
- symmetry 1:1 (estructural + semántica) entre CLI y MCP
- Idempotencia de `brain79 init` verificada (preserva contenido legacy existente)

**Fase 8 — Handoff Purge (`brain79_handoff_purge`): COMPLETA y funcionando.**

Comando destructivo para limpiar todos los handoffs de un wiki. Excepción
explícita a la inmutabilidad de handoffs (Phase 1.5), diseñado para cleanup
operacional (legacy wikis, demo projects, end-of-iteration flush).

- **CLI/MCP simétrico**: defaults a `--dry-run` / `apply=False` para safety.
- **Side effects**: desregistra entradas del navigation registry.
- **NO toca**: `_raw/sessions/`, `_raw/commits/`, otros artículos.
- **NO auto-fix**: los markdown links rotos en otros artículos son detectados
  por `brain79 lint` y corregidos por el agente vía `brain79_write`.


---

## Lo que se construyó

### Paquete Python (`src/brain79/`)

| Archivo | Rol |
|---------|-----|
| `__main__.py` | Entry point: `brain79 init`, `brain79 update` o MCP server mode |
| `server.py` | FastMCP server con herramientas registradas |
| `config.py` | Resolución de `project_root` (arg > env > cwd) |
| `core/wiki.py` | Operaciones sobre `.brain-79/`: read, write, list, search, save_raw |
| `core/handoff.py` | Lógica de validación, escritura y lectura del historial de handoffs |
| `core/init_project.py` | Bootstrapea `.brain-79/`, `.agents/mcp_config.json`, `.mcp.json` y `AGENTS.md` |
| `core/lint.py` | Motor de análisis estático (links rotos, huérfanos, estructuras) |
| `core/context.py` | Motor TF-IDF y recuperador inteligente de contexto |
| `core/update.py` | Lógica de actualización e integración con git y uv |
| `core/bootstrap.py` | Scanner determinístico y generador de manifest para seeding de wiki |
| `templates/SCHEMA.md` | Template de reglas de curación (el artefacto más crítico) |
| `templates/INDEX.md` | Template del entry point de la wiki |
| `templates/AGENTS.md` | Template de protocolo autocontenido universal para `AGENTS.md` |

### Herramientas MCP disponibles

- `brain79_index()` — devuelve `INDEX.md`
- `brain79_read(path)` — lee un artículo
- `brain79_write(path, content, force_validation_skip?)` — escribe/actualiza un artículo (con validación mecánica)
- `brain79_list(section?)` — lista artículos
- `brain79_search(query)` — búsqueda por keyword
- `brain79_ingest(summary, instructions?)` — guarda sesión en `_raw/` y devuelve guía de curación state-aware con violations específicas
- `brain79_handoff_write(...)` — escribe un documento inmutable de traspaso de sesión
- `brain79_handoff_read(ref)` — lee un documento de traspaso y alerta sobre la promoción de conocimiento
- `brain79_lint()` — escanea la wiki y devuelve reporte estricto (links rotos, namespace violations, errores estructurales, organizational health)
- `brain79_context(task, top_n?)` — recupera los artículos de la wiki más relevantes para una tarea mediante ranking ponderado TF-IDF
- `brain79_bootstrap(scope?, force?)` — escanea un proyecto legacy y devuelve un manifest determinístico para que el LLM siembre la wiki inicial
- `brain79_navigate(regenerate?)` — gestiona el registry de navegación y regenera Quick navigation en INDEX.md
- `brain79_migrate(dry_run?)` — añade frontmatter a artículos legacy (default: `status: legacy` para preservar intención semántica)

---

## Lo que falta (ordenado por impacto)

### Alta prioridad

*(Vacío — Tareas principales de instalación local completadas)*

### Media prioridad

2. **Publicación en PyPI**
   - Permite `uvx brain79` sin path local
   - Simplifica la instalación a un solo comando
   - Prerequisito: bumper de versión y CI mínimo

---

## Archivos clave

| Path | Descripción |
|------|-------------|
| `src/brain79/server.py` | FastMCP server — agregar herramientas acá |
| `src/brain79/core/wiki.py` | Lógica de operaciones sobre `.brain-79/` |
| `src/brain79/core/handoff.py` | Lógica y validación estricta de la memoria a corto plazo |
| `src/brain79/core/context.py` | Motor de recuperación inteligente de contexto (TF-IDF) |
| `src/brain79/core/update.py` | Lógica de actualización e integración con git y uv |
| `src/brain79/core/init_project.py` | Lo que `brain79 init` crea (wiki, config, AGENTS.md, .mcp.json) |
| `src/brain79/templates/AGENTS.md` | Template de protocolo universal para el manifesto AGENTS.md |
| `tests/test_init_project.py` | Pruebas unitarias de inicialización e inyección idempotente |
| `tests/test_handoff.py` | Pruebas exhaustivas con cobertura para la funcionalidad de handoff |
| `tests/test_lint.py` | Pruebas unitarias adversariales de parseo, OOM, timeouts y grafos |
| `tests/test_context.py` | Pruebas unitarias completas de recuperación de contexto y TF-IDF |
| `tests/test_update.py` | Pruebas unitarias completas del comando de actualización |
| `tests/test_bootstrap.py` | Pruebas unitarias del scanner de bootstrap (idempotencia, scope, concurrencia, etc.) |
| `src/brain79/templates/SCHEMA.md` | Template de reglas — el artefacto más crítico |
| `src/brain79/__main__.py` | Entry point y supresión de banner fastmcp |
| `src/brain79/core/frontmatter.py` | Schema, parser YAML multi-línea y validación de campos por tipo |
| `src/brain79/core/validation.py` | Validación de write-time con V5 strict regex y fence masking |
| `src/brain79/core/navigation.py` | Registry thread-safe con filelock y Quick navigation auto-generada |
| `src/brain79/core/lint_organizational.py` | 9 checks deterministas de salud organizacional |
| `src/brain79/core/migration.py` | Migración progresiva V3 con `status: legacy` defaults |
| `src/brain79/core/curate.py` | Guía de curación state-aware para ingest cycles |
| `tests/test_truco_arena_integration.py` | Tests north-star de validación end-to-end con snapshot inmutable |
| `tests/fixtures/truco_arena_snapshot/` | Snapshot inmutable de wiki legacy para tests de regresión |
| `tests/fixtures/refresh_truco_arena.sh` | Script manual para regenerar el snapshot |
| `.git/hooks/pre-commit` | Hook instalado por `brain79 init` que bloquea commits con wiki inválido |

---

## Próxima sesión sugerida

Preparar el empaquetado y CI/CD para publicación en PyPI (Modo Distribuido).
