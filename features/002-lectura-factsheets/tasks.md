# Lista de Tareas - Feature 002

- [x] Crear o verificar que estén creadas las carpetas `datos/pdfs_pendientes/` y `datos/pdfs_procesados/`.
- [x] Instalar dependencias necesarias para lectura de PDF en Python (`pdfplumber`, añadido a `requirements.txt`).
- [x] **PREVIO (no planificado):** `skills/limpiar_csv.py` — reparación estructural del Golden Record antes de ingerir nada.
- [x] Crear el script `skills/procesar_pdfs.py`.
- [x] Programar la lógica de lectura y el límite de lote (máx. 5 archivos por ejecución).
- [x] Diseñar el prompt / JSON Schema para extraer los datos del PDF respetando las columnas del CSV.
- [x] Implementar la lógica de *Upsert* (Match por ISIN, Insert de nuevos ETFs).
- [x] Implementar la regla de *Data Shielding* (No sobrescribir valores existentes, solo rellenar vacíos/0.0).
- [x] Implementar el movimiento de archivos físicos tras un procesamiento exitoso.
- [x] **PRUEBA UNITARIA:** primer lote ejecutado y verificado (0 violaciones de blindaje sobre 57 celdas escritas).
- [x] Verificar que el CSV se actualiza correctamente y aplicar correcciones al script.
- [x] Procesar los 86 PDFs en 18 lotes. Carpeta de pendientes vacía, 1.467 celdas escritas, 0 violaciones de blindaje.
- [x] Integrar / Ejecutar `ingest_csv.py` para sincronizar base de datos (89 fondos en SQLite).
- [x] Validar con `db_inspector.py` que los tipos de datos en la BBDD son correctos.

- [x] `skills/auditar_huecos.py` — informe de completitud por fondo y por bloque, para saber qué rellenar sin abrir el CSV.

**FEATURE 002 CERRADA.** 86 factsheets procesados, 1.512 celdas escritas, 0 violaciones de Data Shielding, 89 fondos en SQLite, ninguna incoherencia de suma en el universo.

## Pendiente para el usuario (requiere fuente externa o decisión)

- [ ] Rellenar a mano los 3 ISINs sin PDF: `US46434V7385`, `LU1333148903`, `IE00BGV5VN51`.
- [ ] Conseguir un factsheet actual de `ES0138922036` (Gesconsult): el disponible es de marzo de 2012 y se descartaron todos sus datos temporales.
- [x] **Corregir 4 filas con geografía RV incoherente heredada de la Feature 001.** Reseteadas con `skills/fix_geografia.py` (bypass acotado del blindaje) y reconstruidas 3 de 4 con el dato real de su propio folleto, devolviendo sus PDFs a la cola:
  - `IE00BYX5N771` (Fidelity MSCI Japan): sumaba **2,000** → `Japon=1`. Suma 1,0000.
  - `IE00BYX5NX33` (Fidelity MSCI World): sumaba 1,090 → USA 0,7266 / Europa 0,1276 / Japón 0,0563 / Canadá 0,0332 / Otros 0,0563. Suma 1,0000.
  - `IE00B03HD316` (Vanguard Global Hedged): sumaba 1,091 → USA 0,725 / Europa 0,128 / Japón 0,057 / Canadá 0,033 / Otros 0,057. Suma 1,0000.
- [ ] `US4642863926` (iShares MSCI World ETF): geografía reseteada y **vacía**. Su folleto no publica desglose geográfico, así que hay que rellenarla a mano:
      `.\.venv\Scripts\python.exe skills\rellenar_manual.py US4642863926 --grupo "Geo RV"`
- [ ] Completar geografía/sectores de los ~50 fondos españoles: los informes semestrales de la CNMV no publican esos desgloses (hará falta MCP o Morningstar).
- [ ] Métricas de riesgo a 3 años (Sharpe/Alpha/Beta/Volatilidad): solo 26% de cobertura, la mayoría de folletos no las publican.