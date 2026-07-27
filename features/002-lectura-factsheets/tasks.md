# Lista de Tareas - Feature 002

- [ ] Crear o verificar que estén creadas las carpetas `data/pdfs_pendientes/` y `data/pdfs_procesados/`.
- [ ] Instalar dependencias necesarias para lectura de PDF en Python (si no están ya disponibles en el entorno).
- [ ] Crear el script `skills/procesar_pdfs.py`.
- [ ] Programar la lógica de lectura y el límite de lote (máx. 5 archivos por ejecución).
- [ ] Diseñar el prompt / JSON Schema para extraer los datos del PDF respetando las columnas del CSV.
- [ ] Implementar la lógica de *Upsert* (Match por ISIN, Insert de nuevos ETFs).
- [ ] Implementar la regla de *Data Shielding* (No sobrescribir valores existentes, solo rellenar vacíos/0.0).
- [ ] Implementar el movimiento de archivos físicos tras un procesamiento exitoso.
- [ ] **PRUEBA UNITARIA:** Ejecutar el script con **1 solo PDF** de prueba en la carpeta de pendientes.
- [ ] Verificar que el CSV se actualiza correctamente y aplicar correcciones al script si el LLM falla en el formato.
- [ ] Integrar / Ejecutar `ingest_csv.py` para sincronizar base de datos.
- [ ] Validar con `db_inspector.py` que los tipos de datos en la BBDD son correctos.