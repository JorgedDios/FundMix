# 001 · Ingesta de Datos con MCP — Plan

_Cómo se implementa lo descrito en `spec.md`. Debe respetar la `constitution/`._

## Enfoque

Utilizaremos el Model Context Protocol (MCP) como puente seguro para extraer el JSON de datos desde el servidor del bróker. Este enfoque evita la fragilidad inherente del *web scraping* tradicional (cambios en el DOM de la web) y se alinea perfectamente con nuestro principio "Boutique Quant", permitiendo una extracción automatizada de métricas de alto nivel fiables mientras delegamos los datos opacos a la revisión experta del Portfolio Manager.

## Implementación

_Pasos técnicos concretos, en orden. Indica los archivos/módulos que se tocan._

1. **Lectura Base:** El agente leerá `universo_fundmix.csv` para identificar el fondo objetivo y su ISIN.
2. **Llamada a la Herramienta:** El agente ejecutará una consulta a través del MCP solicitando los datos financieros públicos del ISIN especificado.
3. **Parseo y Volcado:** El agente mapeará la respuesta JSON e insertará estrictamente los valores numéricos de costes y rentabilidades en la fila correspondiente de `universo_fundmix.csv`.
4. **Sincronización:** Se ejecutará el script `skills/ingest_csv.py` para volcar el CSV actualizado a SQLite (`FundMix.db`).
5. **Validación de Integridad:** Se ejecutará `skills/db_inspector.py` para asegurar que las reglas defensivas (ej. inyección del valor `12.0` en calidades crediticias faltantes) se aplican correctamente en la base de datos tras la ingesta.

## Decisiones

_Elecciones de diseño relevantes y su justificación. Alternativas descartadas y por qué._

- **Modificación local del CSV frente a inyección directa SQL:** Decidimos que el agente modifique primero el CSV y luego use la skill de ingesta, en lugar de inyectar datos directamente a SQLite. ¿Por qué? Porque el CSV actúa como nuestro *Golden Record* auditable visualmente por el ser humano. Inyectar directamente en SQLite destruiría la trazabilidad del dato.
- **Tolerancia Cero a la Inferencia:** Decidimos dejar las celdas geográficas y de renta fija en blanco si el MCP no las proporciona o las cataloga mal, descartando la idea de que la IA deduzca la geografía por el nombre del fondo. Esto respeta la regla innegociable de no inventar datos financieros.

## Riesgos

_Qué puede salir mal o requerir cuidado, y cómo se mitiga._

- **Riesgo de Tipos de Datos (Type Mismatch):** Que el agente guarde un TER como "0,23%" (string con coma) en el CSV y rompa la limpieza en Pandas, que espera floats para el motor matemático. **Mitigación:** El agente debe asegurarse de limpiar los caracteres especiales y usar formato decimal estándar antes de escribir en el CSV.
- **Riesgo de Esquema del Servidor:** Que MyInvestor cambie la estructura de llaves del JSON que devuelve el MCP. **Mitigación:** El agente parseará la respuesta dinámicamente, no de forma rígida, y solicitará asistencia humana (Modo 100% Certeza) si no encuentra los campos críticos.