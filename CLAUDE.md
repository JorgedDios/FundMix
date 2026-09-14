# FundMix: Motor Cuantitativo y Optimizador de Carteras

Optimizador de carteras basado en minimización de Tracking Error usando Programación Cuadrática. 

## Documentación y Contexto
- **Visión General:** Lee el `README.md` en la raíz para entender el propósito global y las características del proyecto.
- **Misión y Visión:** Lee obligatoriamente `constitution/mission.md`.
- **Stack Técnico y Límites:** Lee obligatoriamente `constitution/tech-stack.md`.
- Tu comportamiento y decisiones deben alinearse al 100% con estos tres documentos antes de escribir una sola línea de código.

## Estructura del proyecto
- `constitution/` — Reglas de negocio y arquitectura inmutables.
- `skills/` — Scripts de auditoría y herramientas auxiliares (MCP, BBDD).
- `features/` — Tareas activas y hoja de ruta. Aquí encontrarás lo que debes hacer hoy.

## Comandos y Skills
- `python skills/db_inspector.py` — Ejecuta esto para auditar la integridad de SQLite y validar el Data Shielding.
- `python skills/check_dcp.py` — Ejecuta esto SIEMPRE que modifiques el optimizador para validar que las matemáticas siguen siendo convexas.
- `python skills/ingest_csv.py` — Ejecuta esto para volcar el CSV a la base de datos de forma segura.
- `python app.py` — Arranca la interfaz visual.
- `python skills/auditar_huecos.py` — Informe de qué fondos están completos y qué columnas le faltan a cada uno.
- `python skills/procesar_pdfs.py extract|apply|estado` — Pipeline de factsheets PDF → CSV (Feature 002).
- `python skills/rellenar_manual.py <ISIN>` — Relleno asistido por consola de las celdas vacías de un fondo.
- `python skills/limpiar_csv.py` — Reparación estructural del CSV (entrecomillado, ISINs, duplicados). Idempotente.

## No hagas (Reglas estrictas de alto nivel)
- **Matemáticas y Seguridad:** NUNCA rompas las reglas de Programación Convexa Disciplinada (DCP) ni las normas de inyección SQL detalladas en el `tech-stack.md`.
- **Data Shielding:** Aplica siempre la defensa activa definida en la Constitución ante datos faltantes. 
- **Ingesta:** NUNCA inventes datos financieros. Utiliza herramientas (MCP) o los datos estáticos del CSV maestro.

## Flujo de trabajo con el Agente AI (Protocolo Estricto)
- **Modo Plan Obligatorio:** Antes de escribir o modificar código en el motor (`optimizer.py`) o en la base de datos (`create_db.py`), debes proponer un plan técnico detallado y esperar la aprobación explícita del usuario.
- **Cero Suposiciones (100% de Certeza):** En la lógica matemática y de negocio, la tolerancia al error es cero. Si tienes la más mínima duda sobre la convexidad, el impacto de una variable o la estructura del CSV, DETENTE y haz preguntas aclaratorias. No inventes soluciones.
- Realiza una sola tarea a la vez. Al terminar, notifica los cambios exactos para su revisión.
- Cuando se te asigne una tarea, ve a la carpeta `features/` correspondiente, lee las instrucciones completas y ejecuta lo que se pide.