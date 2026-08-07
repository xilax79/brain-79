# Brain-79 — Handoff

> Estado al cierre de la sesión de fundación (2026-08-07).

---

## Estado actual

**Fase 1 — MVP: COMPLETA y funcionando.**

El sistema está operativo end-to-end: instalación, MCP server, cold start, ingest manual, mid-session reads. Validado con un proyecto real (Neon Arkanoid en `/Users/xilax/orca/projects/test-project`).

---

## Lo que se construyó

### Paquete Python (`src/brain79/`)

| Archivo | Rol |
|---------|-----|
| `__main__.py` | Entry point: `brain79 init` o MCP server mode |
| `server.py` | FastMCP server con 6 herramientas registradas |
| `config.py` | Resolución de `project_root` (arg > env > cwd) |
| `core/wiki.py` | Operaciones sobre `.brain-79/`: read, write, list, search, save_raw |
| `core/init_project.py` | Bootstrapea `.brain-79/` + `.agents/mcp_config.json` |
| `templates/SCHEMA.md` | Template de reglas de curación (el artefacto más crítico) |
| `templates/INDEX.md` | Template del entry point de la wiki |

### Herramientas MCP disponibles

- `brain79_index()` — devuelve `INDEX.md`
- `brain79_read(path)` — lee un artículo
- `brain79_write(path, content)` — escribe/actualiza un artículo
- `brain79_list(section?)` — lista artículos
- `brain79_search(query)` — búsqueda por keyword
- `brain79_ingest(summary, instructions?)` — guarda sesión en `_raw/` y devuelve workflow de curación

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

1. **`brain79_handoff` tool** *(feature solicitada por el usuario)*
   - Crear un archivo `handoff.md` en la raíz del proyecto al cerrar sesión
   - "Memoria de corto plazo" vs la wiki como "memoria de largo plazo"
   - El handoff captura: qué estaba en curso, decisiones aún no en wiki, archivos tocados, gotchas de la sesión
   - A demanda del usuario, no automático
   - Definir adversarialmente: qué va en handoff vs qué va en wiki
   - El `brain79_ingest()` llama al LLM para curar wiki; `brain79_handoff()` produce un doc de estado condensado para el próximo agente

2. **Integración con `pi`**
   - El usuario usa `pi` (CLI de Orca con modelos Minimax) como segundo CLI principal
   - No se investigó cómo `pi` carga MCP servers ni si tiene un equivalente a `GEMINI.md`
   - Sin esto, el cold start solo funciona en `agy`

3. **Protocolo para otros CLIs (`opencode`, etc.)**
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

8. Tests unitarios (actualmente cero)
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
| `src/brain79/core/init_project.py` | Lo que `brain79 init` crea |
| `src/brain79/templates/SCHEMA.md` | Template de reglas — el artefacto más crítico |
| `src/brain79/__main__.py` | Entry point y supresión de banner fastmcp |
| `~/.gemini/GEMINI.md` | Protocolo global para agy (cold start + mid-session) |
| `~/.gemini/config/mcp_config.json` | Registro global del MCP en agy |

---

## Próxima sesión sugerida

Diseño adversarial de `brain79_handoff`: definir exactamente qué información pertenece al handoff vs a la wiki, cuántos handoffs coexisten (¿uno por sesión? ¿siempre el mismo archivo?), y cómo el agente entrante prioriza entre handoff y wiki cuando hay información en ambos.
