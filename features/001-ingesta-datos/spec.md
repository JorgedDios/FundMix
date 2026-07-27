# 001 · Ingesta de Datos con MCP

**Estado:** ✅ COMPLETADA (cierre: 2026-07-25 · 64 fondos en `FundMix.db`, 62 con datos + 2 filas fantasma en blanco pendientes de ISIN/ficha)

## Qué hace

Automatiza la extracción de datos financieros públicos (TER, SRRI, Volatilidad, AUM y Rentabilidades históricas) de un fondo específico utilizando la herramienta del servidor MCP conectada a MyInvestor. Los datos extraídos se inyectarán directamente en el archivo maestro local (`universo_fundmix.csv`), listos para ser procesados por la base de datos sin alterar la estructura del documento.

## Por qué

La introducción manual de parámetros numéricos en el CSV es lenta y propensa a errores humanos ("Fat-finger errors"). Esta automatización acelera la creación del "Golden Record" manteniendo la calidad institucional, liberando al gestor para que se enfoque exclusivamente en curar los datos complejos que el bróker no provee o clasifica mal (como la duración modificada de los bonos, la calidad crediticia real o la exposición geográfica pura).

## Criterios de aceptación

_Condiciones verificables que deben cumplirse para dar la feature por terminada. Redacta cada una de forma que se pueda comprobar con un sí/no. Marca `[x]` al cumplirse._

- [x] El agente extrae correctamente los valores numéricos de TER, SRRI, Volatilidad y Rentabilidades del servidor MCP.
- [x] Los campos que el servidor devuelve como vacíos, erróneos o genéricos (ej. clasificar Renta Fija como "Otros" o no desglosar "Top Regiones") se dejan en blanco de forma explícita en el CSV para su posterior curación manual, respetando el Data Shielding.
- [x] El archivo `universo_fundmix.csv` se actualiza correctamente manteniendo su formato original y sin corromper las filas de los demás activos.
- [x] La ejecución posterior de `skills/ingest_csv.py` y `skills/db_inspector.py` finaliza con éxito sin arrojar errores de integridad ni violaciones de tipo en la base de datos SQLite.

## Fuera de alcance

_Lo que esta feature NO incluye, para evitar que crezca. Si algo se difiere, enlaza a dónde (roadmap/backlog)._

- Conexión directa mediante Web Scraping a Morningstar o Yahoo Finance (Delegado a Fase 4 del `roadmap.md`).
- Descarga masiva o en bucle de múltiples fondos simultáneos. El diseño actual exige la consulta secuencial para garantizar la supervisión y validación humana de la calidad del dato.