# 001 · Ingesta de Datos con MCP — Tareas

_Checklist accionable derivada del `plan.md`. Tareas pequeñas y concretas; marca `[x]` al completarlas._

- [x] Analizar el archivo `universo_fundmix.csv` y aislar la fila correspondiente al ISIN objetivo.
- [x] Ejecutar la herramienta MCP para extraer el JSON de datos de dicho fondo.
- [x] Limpiar el formato de los datos extraídos (eliminar símbolos de porcentaje o divisas, estandarizar decimales).
- [x] Escribir los datos extraídos (TER, SRRI, Volatilidad, Rentabilidades, AUM) en las columnas exactas del CSV.
- [x] Confirmar de manera explícita que los datos geográficos o características de renta fija no devueltas correctamente se han dejado vacíos (sin inferencias algorítmicas).
- [x] Ejecutar en terminal: `python skills/ingest_csv.py` para realizar la carga fresca a la base de datos.
- [x] Ejecutar en terminal: `python skills/db_inspector.py` para auditar la integridad del sistema y confirmar el Data Shielding.
- [x] Validar contra los criterios de aceptación de `spec.md`.
- [x] Mover la feature a "Fases Completadas" en `../../features/roadmap.md`.

## Mantenimiento (checklist recurrente)

_Opcional. Pasos a repetir cada vez que se toque esta feature en el futuro (revisar datos, regenerar algo, etc.). Borra esta sección si no aplica._

- [ ] Verificar que el servidor MCP local esté levantado y respondiendo en el puerto correcto antes de iniciar cualquier consulta de nuevos ISINs.