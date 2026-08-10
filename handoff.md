# Brain-79 — Handoff

> Estado al cierre de la sesión de diseño de handoff (2026-08-07).

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

---

## Lo que se construyó

### Paquete Python (`src/brain79/`)

| Archivo | Rol |
|---------|-----|
| `__main__.py` | Entry point: `brain79 init` o MCP server mode |
| `server.py` | FastMCP server con herramientas registradas |
| `config.py` | Resolución de `project_root` (arg > env > cwd) |
| `core/wiki.py` | Operaciones sobre `.brain-79/`: read, write, list, search, save_raw |
| `core/handoff.py` | Lógica de validación, escritura y lectura del historial de handoffs |
| `core/init_project.py` | Bootstrapea `.brain-79/`, `.agents/mcp_config.json`, `.mcp.json` y `AGENTS.md` |
| `core/lint.py` | Motor de análisis estático (links rotos, huérfanos, estructuras) |
| `core/context.py` | Motor TF-IDF y recuperador inteligente de contexto |
| `templates/SCHEMA.md` | Template de reglas de curación (el artefacto más crítico) |
| `templates/INDEX.md` | Template del entry point de la wiki |
| `templates/AGENTS.md` | Template de protocolo autocontenido universal para `AGENTS.md` |

### Herramientas MCP disponibles

- `brain79_index()` — devuelve `INDEX.md`
- `brain79_read(path)` — lee un artículo
- `brain79_write(path, content)` — escribe/actualiza un artículo
- `brain79_list(section?)` — lista artículos
- `brain79_search(query)` — búsqueda por keyword
- `brain79_ingest(summary, instructions?)` — guarda sesión en `_raw/` y devuelve workflow de curación
- `brain79_handoff_write(...)` — escribe un documento inmutable de traspaso de sesión
- `brain79_handoff_read(ref)` — lee un documento de traspaso y alerta sobre la promoción de conocimiento
- `brain79_lint()` — escanea la wiki y devuelve reporte estricto de links rotos, namespace violations, errores y huérfanos
- `brain79_context(task, top_n?)` — recupera los artículos de la wiki más relevantes para una tarea mediante ranking ponderado TF-IDF

---

## Lo que falta (ordenado por impacto)

### Alta prioridad

*(Vacío — Tareas principales de instalación local completadas)*

### Media prioridad

2. **Publicación en PyPI**
   - Permite `uvx brain79` sin path local
   - Simplifica la instalación a un solo comando
   - Prerequisito: bumper de versión y CI mínimo

### Baja prioridad / backlog

3. `brain79 update` — reinstala si el repo cambió (alternativa a `--editable`)
4. `uv.lock` — decidir si trackearlo o no (actualmente en `.gitignore`)

---

## Archivos clave

| Path | Descripción |
|------|-------------|
| `src/brain79/server.py` | FastMCP server — agregar herramientas acá |
| `src/brain79/core/wiki.py` | Lógica de operaciones sobre `.brain-79/` |
| `src/brain79/core/handoff.py` | Lógica y validación estricta de la memoria a corto plazo |
| `src/brain79/core/context.py` | Motor de recuperación inteligente de contexto (TF-IDF) |
| `src/brain79/core/init_project.py` | Lo que `brain79 init` crea (wiki, config, AGENTS.md, .mcp.json) |
| `src/brain79/templates/AGENTS.md` | Template de protocolo universal para el manifesto AGENTS.md |
| `tests/test_init_project.py` | Pruebas unitarias de inicialización e inyección idempotente |
| `tests/test_handoff.py` | Pruebas exhaustivas con cobertura para la funcionalidad de handoff |
| `tests/test_lint.py` | Pruebas unitarias adversariales de parseo, OOM, timeouts y grafos |
| `tests/test_context.py` | Pruebas unitarias completas de recuperación de contexto y TF-IDF |
| `src/brain79/templates/SCHEMA.md` | Template de reglas — el artefacto más crítico |
| `src/brain79/__main__.py` | Entry point y supresión de banner fastmcp |

---

## Próxima sesión sugerida

Preparar el empaquetado y CI/CD para publicación en PyPI (Modo Distribuido).
