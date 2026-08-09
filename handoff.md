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

---

## Lo que se construyó

### Paquete Python (`src/brain79/`)

| Archivo | Rol |
|---------|-----|
| `__main__.py` | Entry point: `brain79 init` o MCP server mode |
| `server.py` | FastMCP server con 6 herramientas registradas |
| `config.py` | Resolución de `project_root` (arg > env > cwd) |
| `core/wiki.py` | Operaciones sobre `.brain-79/`: read, write, list, search, save_raw |
| `core/handoff.py` | Lógica de validación, escritura y lectura del historial de handoffs |
| `core/init_project.py` | Bootstrapea `.brain-79/`, `.agents/mcp_config.json`, `.mcp.json` y `AGENTS.md` |
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

### Configuración aplicada en la máquina del usuario

- **Instalación global**: `uv tool install --editable /Users/xilax/Documents/GitHub/brain-79`
  - Binario en: `/Users/xilax/.local/bin/brain79`
- **MCP global para agy**: `/Users/xilax/.gemini/config/mcp_config.json`
- **MCP local para pi y otros CLIs**: Configurado idempotentemente vía `.mcp.json`
- **Manifiesto Universal**: Desplegado en `AGENTS.md` para cold start cross-CLI

---

## Aprendizajes críticos (no obvios)

1. **El config correcto de agy es `~/.gemini/config/mcp_config.json`**, no `settings.json`. Las dos rutas son distintas. `settings.json` lo usa Gemini CLI (no agy).

2. **El comando debe ser ruta absoluta**: `agy` spawea procesos con PATH restringido. `"brain79"` falla; `/Users/xilax/.local/bin/brain79"` funciona.

3. **fastmcp imprime un banner a stderr** al arrancar. Se suprime con `os.environ.setdefault("FASTMCP_SHOW_SERVER_BANNER", "false")` en `__main__.py` — debe setearse ANTES de importar fastmcp.

4. **El protocolo en `GEMINI.md` o `AGENTS.md` es lo que hace funcionar el cold start**, no el campo `instructions` del MCP server. Los modelos tratan `instructions` como sugerencia. El manifiesto de reglas (`AGENTS.md`/`GEMINI.md`) es obligatorio.

5. **`brain79 init` inyecta configuraciones idempotentes**: genera `.agents/mcp_config.json` para `agy`, `.mcp.json` para `pi` (precedencia de adaptadores), y `AGENTS.md` como estándar emergente multi-CLI.

6. **El ingest manual funciona sin MCP**: el agente puede leer/escribir `.brain-79/` directamente si tiene acceso al filesystem. El MCP suma pero no es bloqueante.

---

## Lo que falta (ordenado por impacto)

### Alta prioridad

1. **`brain79_lint` tool** (Fase 2)
   - Detectar contradicciones, artículos huérfanos, links rotos, contenido stale
   - Implementar como operación bajo demanda

2. **`brain79_context(task)` tool** (Fase 3)
   - Dado un task/pregunta, devuelve los artículos más relevantes
   - Útil para que el agente sepa qué leer antes de implementar algo

### Media prioridad

3. **Script de instalación (`install.sh`)**
   - Un script que ejecute `uv tool install --editable .` y genere el JSON para `mcp_config.json`

4. **Publicación en PyPI**
   - Permite `uvx brain79` sin path local
   - Simplifica la instalación a un solo comando
   - Prerequisito: bumper de versión y CI mínimo

### Baja prioridad / backlog

5. `brain79 update` — reinstala si el repo cambió (alternativa a `--editable`)
6. `uv.lock` — decidir si trackearlo o no (actualmente en `.gitignore`)

---

## Archivos clave

| Path | Descripción |
|------|-------------|
| `src/brain79/server.py` | FastMCP server — agregar herramientas acá |
| `src/brain79/core/wiki.py` | Lógica de operaciones sobre `.brain-79/` |
| `src/brain79/core/handoff.py` | Lógica y validación estricta de la memoria a corto plazo |
| `src/brain79/core/init_project.py` | Lo que `brain79 init` crea (wiki, config, AGENTS.md, .mcp.json) |
| `src/brain79/templates/AGENTS.md` | Template de protocolo universal para el manifesto AGENTS.md |
| `tests/test_init_project.py` | Pruebas unitarias de inicialización e inyección idempotente |
| `tests/test_handoff.py` | Pruebas exhaustivas con cobertura para la funcionalidad de handoff |
| `src/brain79/templates/SCHEMA.md` | Template de reglas — el artefacto más crítico |
| `src/brain79/__main__.py` | Entry point y supresión de banner fastmcp |

---

## Próxima sesión sugerida

Diseñar e implementar la herramienta `brain79_lint` (Fase 2) para análisis y diagnóstico automático del estado de salud de la wiki (links rotos, artículos obsoletos, o huérfanos).

