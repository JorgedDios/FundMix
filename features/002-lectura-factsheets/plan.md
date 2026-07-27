# Plan de Ejecución Técnico - Feature 002

## 1. Preparación del Entorno
- Crear o verificar que estén creados los directorios `data/pdfs_pendientes/` y `data/pdfs_procesados/`.
- Asegurar que las dependencias de extracción de texto estén instaladas (ej. `PyMuPDF`, `pdfplumber` o la herramienta MCP nativa del agente para lectura de archivos).

## 2. Desarrollo del Script Principal (`skills/procesar_pdfs.py`)
Crear un script en Python que realice las siguientes acciones secuenciales:
1. **Listar:** Leer los primeros 5 archivos `.pdf` de `data/pdfs_pendientes/`.
2. **Extraer:** Para cada PDF, extraer el texto en crudo.
3. **Estructurar (LLM):** Enviar el texto al LLM con un prompt del sistema (JSON Schema) que obligue a devolver un diccionario mapeado exactamente a las columnas de `universo_fundmix.csv`.
4. **Mapear:** Cruzar el JSON devuelto con las columnas esperadas.
5. **Upsert:** Cargar `universo_fundmix.csv` mediante Pandas.
   - Buscar coincidencia por ISIN.
   - Si existe: Aplicar *Data Shielding* (solo actualizar `NaN`, `NULL` o `0.0`).
   - Si no existe: Añadir la fila con todos los datos extraídos.
6. **Guardar:** Escribir los cambios de vuelta a `universo_fundmix.csv`.
7. **Mover:** Mover el archivo PDF físico a `data/pdfs_procesados/`.

## 3. Sincronización BBDD
- Al finalizar el lote, el script debe llamar automáticamente a `ingest_csv.py` para que la tabla `FundMix.db` refleje los nuevos datos.