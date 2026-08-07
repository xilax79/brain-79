# Propuesta de implementación y esquema universal para handoff

Este documento detalla la implementación de la funcionalidad de handoff para brain-79, asegurando que sea útil tanto para desarrollo de software como para tareas abstractas (investigación, brainstorming o análisis complejo).

## **Diseño adversarial:** delimitando responsabilidades entre memorias

- **Wiki (memoria a largo plazo):** actúa como la fuente de la verdad inmutable del proyecto. Aquí residen la arquitectura, las decisiones consolidadas, conclusiones finales de investigaciones y el contexto global.
- **Handoff (memoria a corto plazo):** es un documento táctico, efímero y de alta volatilidad. Su objetivo exclusivo es capturar el estado en transición de una tarea específica, sin importar si es una sesión de código o un debate abierto.
- **Resolución de conflictos:** si hay discrepancias entre la wiki y el handoff, la información del handoff tiene prioridad estricta para la tarea inmediata, asumiendo que representa la línea de pensamiento más reciente.

## **Ciclo de vida:** persistencia y gestión del archivo

- **Ubicación en el repositorio:** el documento debe generarse como `handoff.md` en la raíz del proyecto.
- **Modelo de reemplazo único:** no deben existir múltiples archivos de handoff. Cada vez que se genera uno nuevo, sobrescribe al anterior, funcionando como un testigo que se pasa al siguiente eslabón.
- **Consumo durante el cold start:** el agente entrante debe estar fuertemente instruido desde las reglas globales para buscar y leer este archivo de inmediato al iniciar la sesión.
- **Limpieza y finalización:** una vez que el agente completa el objetivo heredado, el contenido de `handoff.md` pierde validez táctica y debe ser reemplazado al final de esa sesión si aún queda trabajo pendiente.

## **Esquema universal:** propuesta para handoff.md

Para que el handoff funcione a la perfección en cualquier contexto (desarrollo, investigación o ideación), el archivo generado debe tener una estructura agnóstica pero accionable.

- **Tipo de sesión:** clasificación del trabajo en curso (ej: desarrollo de software, investigación profunda, brainstorming, refactorización).
- **Contexto inmediato:** resumen directo sobre el objetivo general y lo que se estaba intentando lograr antes de la desconexión.
- **Estado actual:** delimitación clara de qué partes de la tarea se lograron completar y cuáles quedaron pendientes, a medias o en debate.
- **Conocimiento destilado (hard-won data):** descubrimientos empíricos, resultados de experimentos, acuerdos mutuos con el usuario o hallazgos de research que costó tiempo obtener. Esta sección condensada es vital para no perder el esfuerzo invertido y evitar repetir validaciones o debates en la siguiente sesión.
- **Recursos y focos (archivos/links):** lista de rutas exactas (`view_file`), URLs o documentos clave que el siguiente agente necesita inspeccionar de inmediato. En código serían archivos fuente; en research, documentos o papers.
- **Callejones sin salida (gotchas):** registro vital sobre intentos fallidos, bugs recientes o ideas descartadas. Esto evita que el nuevo agente repita errores o proponga soluciones que ya se rechazaron en la sesión previa.
- **Instrucción de arranque:** el comando exacto, script, pregunta abierta o paso puntual por donde el siguiente agente debe comenzar a trabajar. Si no quedó nada pendiente ni existe un plan real por completar, no se deben inventar pasos; el campo debe reflejar explícitamente que no hay tareas pendientes.

## **Diseño de la herramienta MCP:** lógica y arquitectura

- **Firma propuesta:** la herramienta `brain79_handoff(session_type: str, summary: str, in_progress: list[str], distilled_knowledge: list[str], resources: list[str], gotchas: list[str], next_steps: list[str])` forza al LLM a categorizar y estructurar la salida según el esquema universal.
- **Generación determinista:** la herramienta solo toma los argumentos estructurados y vuelca su contenido en un archivo markdown formateado, sin requerir inferencia extra.

## **Prompt base:** instrucciones para generar un handoff perfecto

El éxito del handoff depende de que el LLM extraiga la información correcta sin generar ruido. El siguiente es el prompt ideal que debe inyectarse o usarse al llamar a la herramienta `brain79_handoff`.

- **Instrucción del sistema:** estás a punto de cerrar tu sesión actual. Tu objetivo es generar un documento de handoff perfecto para el agente que continuará tu trabajo. Debes ser extremadamente conciso pero exhaustivo con los datos críticos. Presta especial atención a destilar el conocimiento: incluye todo acuerdo que hayas alcanzado con el usuario, configuraciones experimentales exitosas o hallazgos de investigación que hayan tomado iteraciones descubrir. No obligues al próximo agente a redescubrir lo que tú ya sabes. Omite formalidades y ve directamente al grano. Respecto al próximo paso a seguir: si no quedaron tareas a mitad de camino ni hay un plan acordado pendiente, no alucines ni inventes próximos pasos bajo ninguna circunstancia; indícalo explícitamente.
