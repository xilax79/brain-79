# Propuesta de implementación y esquema universal para handoff

Este documento detalla la implementación de la funcionalidad de handoff para brain-79, asegurando un diseño a prueba de fallos mediante activación bajo demanda y preservación histórica.

## **Diseño adversarial:** delimitando responsabilidades entre memorias

- **Wiki (memoria a largo plazo):** actúa como la fuente de la verdad inmutable del proyecto. Aquí residen la arquitectura, las decisiones consolidadas y el contexto global.
- **Handoff (memoria a corto plazo):** es un documento táctico y efímero que captura el estado en transición de una tarea específica (sea código o investigación).
- **Resolución de conflictos:** la wiki gana siempre. Si el agente detecta una discrepancia, debe apegarse a la wiki, salvo que el handoff declare explícitamente y con justificación por qué se está desviando de manera temporal.

## **Ciclo de vida:** persistencia y gestión de archivos

- **Ubicación en el repositorio:** los handoffs deben crearse dentro de `.brain-79/handoffs/` siguiendo el patrón `handoff-<timestamp>.md`. Esto evita refactorizar el enrutamiento de la herramienta y previene colisiones en la raíz del proyecto.
- **Preservación histórica:** cada llamada a la herramienta genera un archivo nuevo. Al no existir sobrescritura silenciosa, se garantiza un audit trail inmutable y se elimina el riesgo de corrupción por escrituras incompletas.
- **Activación por demanda (simétrica):** tanto la creación como la lectura del handoff son manuales (iniciadas por un prompt explícito del usuario). No se deben alterar reglas globales (como `GEMINI.md`) para forzar lecturas automáticas.
- **Sinergia con init:** el comando `brain79 init` debe actualizarse para instanciar el directorio `.brain-79/handoffs/` por defecto.

## **Esquema universal:** campos aislados y sin solapamiento

Para garantizar que el LLM no divague, el esquema aísla conceptos mutuamente excluyentes:

- **Tipo de sesión (`session_type`):** clasificación estricta basada en un enum (ej: "feature", "bugfix", "research", "brainstorming").
- **Referencia anterior (`previous_handoff_ref`):** timestamp o nombre del handoff anterior del cual deriva el actual, permitiendo encadenar sesiones y construir linaje.
- **Contexto inmediato (`summary`):** resumen directo sobre el objetivo general que se intentaba lograr.
- **Trabajo completado (`completed_work`):** detalle exacto de qué partes de la tarea ya están resueltas.
- **Trabajo pendiente (`pending_work`):** detalle de lo que quedó a medias o falta hacer, claramente separado de lo completado.
- **Conocimiento pendiente de promoción (`knowledge_pending_promotion`):** descubrimientos empíricos o acuerdos que tomaron esfuerzo. Se etiqueta así para recordar al siguiente agente que su responsabilidad inmediata es consolidar esta información en la wiki (vía `brain79_ingest`).
- **Recursos (`resources`):** lista de rutas, URLs o documentos clave relevantes para la tarea.
- **Callejones sin salida (`gotchas`):** registro de intentos fallidos o errores recientes para evitar repeticiones.
- **Instrucción de arranque (`boot_instruction`):** el comando exacto o paso puntual por donde el siguiente agente debe comenzar. Si no quedó trabajo a medias ni hay un plan acordado, el campo debe reflejar explícitamente que no hay tareas pendientes (prohibido alucinar próximos pasos).

## **Diseño de herramientas MCP:** lógica de lectura y escritura

Para cumplir con la activación simétrica, se proponen dos herramientas vinculadas:

- **Herramienta de escritura:** la función `brain79_handoff_write(session_type: str, previous_handoff_ref: str, summary: str, completed_work: list[str], pending_work: list[str], knowledge_pending_promotion: list[str], resources: list[str], gotchas: list[str], boot_instruction: str)` forza al modelo a categorizar su tren de pensamiento y vuelca el contenido de forma determinista en el markdown.
- **Herramienta de lectura:** la función `brain79_handoff_read(handoff_ref: str = "latest")` permite al agente entrante consumir el archivo de forma estructurada, resolviendo automáticamente el archivo más reciente (o uno específico si se provee el timestamp), sin necesidad de explorar directorios manualmente.

## **Prompt base:** instrucciones para la escritura perfecta

El éxito de la herramienta de escritura depende de una directiva clara inyectada en su definición:

- **Instrucción del sistema:** estás a punto de cerrar tu sesión actual y debes generar un handoff. Sé extremadamente conciso. Si descubriste conocimiento valioso (hard-won data), colócalo en `knowledge_pending_promotion` para que el próximo agente lo ingiera en la wiki. Mantén `completed_work` y `pending_work` estrictamente separados. Respecto a la `boot_instruction`: si no quedaron tareas a mitad de camino ni existe un plan acordado, no inventes próximos pasos bajo ninguna circunstancia; indícalo explícitamente.
