# Tech stack y convenciones

_Cómo está construido FundMix y las reglas que todo el código debe respetar. Es la referencia técnica que ningún plan de feature debe contradecir._

## Tecnologías

- **Lenguaje:** Python 3 (Tipado dinámico pero con control estricto en limpieza de datos).
- **Framework / runtime:** Streamlit (Renderizado *serverless*, re-ejecución completa en cada interacción).
- **Base de datos:** SQLite3 (Archivo local `FundMix.db`).
- **Motor Cuantitativo:** CVXPY (Solver ECOS), Pandas y NumPy.

## Archivos / módulos clave

- `app.py` — Interfaz visual y captura de parámetros del usuario.
- `optimizer.py` — Cerebro matemático. Transforma datos y resuelve la Programación Cuadrática.
- `create_db.py` — Esquema SQL y lógica de inserción inicial.
- `skills/` — Scripts autónomos de auditoría e ingesta para automatización.
- `universo_fundmix.csv` — El "Golden Record". Archivo maestro de datos.

## Comandos

- `python app.py` — Arranca la interfaz web en local.
- `python skills/check_dcp.py` — Ejecuta la auditoría matemática (obligatorio antes de confirmar cambios en el motor).
- `python skills/db_inspector.py` — Revisa la integridad tras ingestas de datos.
- `python skills/ingest_csv.py` — Vuelca los datos del CSV a SQLite.

## Modelo de datos / dominio

- `RF_Calidad_Num` — Mapeo inverso de *Rating*. Escala de 1 (AAA) a 10 (D). **Regla de Inyección:** Si falta el dato en RF, se imputa estrictamente `12.0` (penalización extrema por encima de D).
- `is_RF_Universe` — Máscara booleana (`1`/`0`) utilizada para aislar la Renta Fija matemáticamente sin romper la convexidad global.
- `w` — Vector de variables de decisión (CVXPY). Representa los pesos asignados a cada activo.

## Convenciones

- **Conexiones a BBDD:** Uso obligatorio de bloques `with sqlite3.connect(...) as conn` para garantizar la liberación de recursos de la base de datos.
- **Ingesta Dinámica:** Las inserciones SQL en Python deben usar mapeo por diccionarios y consultar `PRAGMA table_info`.
- **Limpieza de Datos:** `.fillna(0.0)` solo se aplicará sobre columnas tipo numérico. Las nulas de tipo texto deben rellenarse con `"Desconocido"` o `""`.

## Estilo visual

- **Inyección de CSS:** Modificaciones visuales avanzadas se realizan inyectando etiquetas `<style>` mediante `st.markdown(..., unsafe_allow_html=True)`.
- **Layout:** Se utiliza `layout="wide"` para maximizar el ancho de tablas y gráficos.

## Límites duros

- **Matemática Convexa (DCP):** PROHIBIDO dividir por la variable de decisión `w` o por funciones que la contengan.
- **Linealización Obligatoria:** Las sub-medias (ej. Duración RF) deben reordenarse a formato lineal: `(w @ valor) - (Target * (w @ is_RF)) = 0`.
- **Seguridad SQL:** PROHIBIDO usar concatenación de *strings* directa. Uso obligatorio de `?` (placeholders) para prevenir inyecciones SQL.
- **Flujo UI:** PROHIBIDO colocar código de Streamlit antes de `st.set_page_config()`.