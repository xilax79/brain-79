# Brain-79 — Estado de sesión inicial

## Qué es
Sistema de memoria persistente por proyecto basado en el método LLM-Wiki de Karpathy. Nombre clave: **brain-79**. Repo: `/Users/xilax/Documents/GitHub/brain-79` (vacío, solo `.git`).

## Decisiones tomadas

### Arquitectura
- **Por proyecto**: un MCP server por repo, no global
- La wiki vive en `.brain-79/` dentro del repo → versionada con git
- Tres capas: raw sources (`_raw/`), wiki (markdown), schema (`SCHEMA.md`)
- Entry point del agente: `INDEX.md` (siempre se lee primero, barato)

### Flujo de ingest
- **Manual y controlado**: el usuario pide explícitamente "actualizá la wiki"
- Puede dar precisiones: ignorar partes, focalizarse en código, etc.
- El usuario es el editor jefe; el agente compila, el usuario aprueba

### Stack técnico
- Python + `fastmcp` (MCP server)
- `uv` para dependencias, `uvx` para ejecución
- Distribución: `uvx brain79`
- Config MCP: `{"command": "uvx", "args": ["brain79", "--project-root", "."]}`
- Almacenamiento: markdown puro en `.brain-79/`
- Búsqueda: ripgrep / grep (sin dependencias extra)

### Estructura de `.brain-79/`
```
.brain-79/
├── SCHEMA.md        ← reglas para el LLM (el artefacto más crítico)
├── INDEX.md         ← entry point, estado actual del proyecto
├── product/
├── architecture/
├── features/
├── changelog/
├── decisions/
└── _raw/
    ├── sessions/
    └── commits/
```

### Herramientas MCP planeadas
- `brain79_read(path)` → lee artículo
- `brain79_write(path, content)` → escribe/actualiza
- `brain79_list(section?)` → lista artículos
- `brain79_search(query)` → búsqueda keywords
- `brain79_ingest(session_summary)` → pipeline ingest
- `brain79_lint()` → detecta problemas
- `brain79_index()` → devuelve INDEX.md

## Fases de desarrollo

### Fase 1 — MVP (PRÓXIMA)
- Paquete Python con `uv` + `fastmcp`
- Comando `brain79 init` → bootstrappea `.brain-79/` en cualquier proyecto
- Templates de `SCHEMA.md` e `INDEX.md`
- Herramientas MCP: read, write, list, index, ingest (básico)
- `mcp.json` de ejemplo

### Fase 2 — Ingest pipeline
- `brain79_ingest` completo
- `brain79_lint`
- Validación con `agy`

### Fase 3 — Query inteligente
- `brain79_search`
- `brain79_context(task)` → artículos relevantes dado un task
- Prompt templates para cold start

### Fase 4 — Automatización (futuro)
- Hooks git
- Integración opencode / pi

## Preguntas abiertas
1. Formato del resumen de sesión para ingest (texto libre vs. estructurado)
2. Conflictos de concurrencia (2 sesiones en el mismo proyecto)
3. Privacidad (tokens/passwords en transcripts)
4. Tamaño máximo de artículo
5. Versioning de la wiki (git tags?)

## Artefacto de diseño
`/Users/xilax/.gemini/antigravity-cli/brain/51c73877-58ab-4d33-a531-548646c2fc7b/brain79_design.md`
