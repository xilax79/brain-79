# Brain-79 — Handoff

> Estado al cierre de la sesión de diseño de handoff (2026-08-07).

---

## Estado actual

**Fase 1 — MVP: COMPLETA y funcionando.**

El sistema está operativo end-to-end: instalación, MCP server, cold start, ingest manual, mid-session reads. 

**Fase 1.5 — Handoff: COMPLETA y funcionando.**

La especificación del esquema universal de handoff ha sido diseñada de forma blindada, implementada con sus dos herramientas simétricas (`brain79_handoff_write` y `brain79_handoff_read`), e integrada al FastMCP con coberturas estrictas contra alucinaciones (con validaciones en tiempo de ejecución, tests unitarios en `pytest` configurado con `mypy` y `ruff`).

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
| `core/init_project.py` | Bootstrapea `.brain-79/` (ahora incluye `handoffs/`) + config |
| `templates/SCHEMA.md` | Template de reglas de curación (el artefacto más crítico) |
| `templates/INDEX.md` | Template del entry point de la wiki |

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
- **Protocolo en reglas globales**: `/Users/xilax/.gemini/GEMINI.md`
  - Sección `<!-- gentle-ai:brain79 -->` con reglas de cold start y mid-session reads

---

## Aprendizajes críticos (no obvios)

1. **El config correcto de agy es `~/.gemini/config/mcp_config.json`**, no `settings.json`. Las dos rutas son distintas. `settings.json` lo usa Gemini CLI (no agy).

2. **El comando debe ser ruta absoluta**: `agy` spawea procesos con PATH restringido. `"brain79"` falla; `/Users/xilax/.local/bin/brain79"` funciona.

3. **fastmcp imprime un banner a stderr** al arrancar. Se suprime con `os.environ.setdefault("FASTMCP_SHOW_SERVER_BANNER", "false")` en `__main__.py` — debe setearse ANTES de importar fastmcp.

4. **El protocolo en `GEMINI.md` es lo que hace funcionar el cold start**, no el campo `instructions` del MCP server. Los modelos tratan `instructions` como sugerencia. El `GEMINI.md` es obligatorio.

5. **`brain79 init` ahora crea `.agents/mcp_config.json`** automáticamente (formato correcto para agy por proyecto), usando `shutil.which("brain79")` para encontrar el binario.

6. **El ingest manual funciona sin MCP**: el agente puede leer/escribir `.brain-79/` directamente si tiene acceso al filesystem. El MCP suma pero no es bloqueante.

---

## Lo que falta (ordenado por impacto)

### Alta prioridad

1. **Integración con `pi`**
   - El usuario usa `pi` (CLI de Orca con modelos Minimax) como segundo CLI principal
   - No se investigó cómo `pi` carga MCP servers ni si tiene un equivalente a `GEMINI.md`
   - Sin esto, el cold start solo funciona en `agy`

2. **Protocolo para otros CLIs (`opencode`, etc.)**
   - `GEMINI.md` solo aplica a `agy`
   - `opencode` usa `CLAUDE.md` — crear ese archivo como parte de `brain79 init`
   - Investigar si hay un archivo universal emergente (`AGENTS.md`)

### Media prioridad

4. **`brain79_lint` tool** (Fase 2)
   - Detectar contradicciones, artículos huérfanos, links rotos, contenido stale
   - Implementar como operación bajo demanda

5. **`brain79_context(task)` tool** (Fase 3)
   - Dado un task/pregunta, devuelve los artículos más relevantes
   - Útil para que el agente sepa qué leer antes de implementar algo

6. **Script de instalación (`install.sh`)**
   - El usuario preguntó por esto y nunca se construyó
   - Un script que ejecute `uv tool install --editable .` y genere el JSON para `mcp_config.json`

7. **Publicación en PyPI**
   - Permite `uvx brain79` sin path local
   - Simplifica la instalación a un solo comando
   - Prerequisito: bumper de versión y CI mínimo

### Baja prioridad / backlog

8. Tests unitarios generales (las funciones nuevas de handoff ya están 100% testeadas, pero `wiki.py` carece de tests)
9. `brain79 update` — reinstala si el repo cambió (alternativa a `--editable`)
10. `brain79_search` con ripgrep en lugar de Python puro (más rápido en repos grandes)
11. `uv.lock` — decidir si trackearlo o no (actualmente en `.gitignore`)
12. Compatibilidad con múltiples proyectos abiertos simultáneamente (concurrencia)

---

## Archivos clave

| Path | Descripción |
|------|-------------|
| `src/brain79/server.py` | FastMCP server — agregar herramientas acá |
| `src/brain79/core/wiki.py` | Lógica de operaciones sobre `.brain-79/` |
| `src/brain79/core/handoff.py` | Lógica y validación estricta de la memoria a corto plazo |
| `tests/test_handoff.py` | Pruebas exhaustivas con cobertura para la funcionalidad de handoff |
| `src/brain79/core/init_project.py` | Lo que `brain79 init` crea |
| `src/brain79/templates/SCHEMA.md` | Template de reglas — el artefacto más crítico |
| `src/brain79/__main__.py` | Entry point y supresión de banner fastmcp |
| `~/.gemini/GEMINI.md` | Protocolo global para agy (cold start + mid-session) |
| `~/.gemini/config/mcp_config.json` | Registro global del MCP en agy |

---

## Próxima sesión sugerida

Investigar y definir la integración con el CLI `pi` (Orca/Minimax) y crear el protocolo emergente o manifiesto universal para estandarizar el cold start en múltiples CLIs (`AGENTS.md` o similar), dado que la funcionalidad local ya está madura.
