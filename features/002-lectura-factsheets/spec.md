# Feature 002: Enriquecimiento de Datos vía PDFs (Factsheets)

## Objetivo Principal
Construir un pipeline automatizado para extraer información financiera profunda de los folletos oficiales (factsheets en PDF) de los fondos y ETFs. Los datos extraídos rellenarán las columnas vacías del *Golden Record* (`universo_fundmix.csv`) sin destruir la información ya validada en la Feature 001.

## Arquitectura de Carpetas (Cadena de Montaje)
El sistema utilizará un flujo de trabajo físico para gestionar los archivos y evitar la saturación de memoria (batching):
1. `data/pdfs_pendientes/`: Directorio de entrada donde el usuario deposita los PDFs.
2. `data/pdfs_procesados/`: Directorio de salida donde el script mueve automáticamente los PDFs tras extraer y volcar su información con éxito.

## Reglas de Negocio Estrictas

1. **Lógica de Upsert (Actualizar o Insertar):**
   - El script leerá el ISIN del PDF (o se deducirá del nombre del archivo).
   - **Update (Fondos existentes):** Si el ISIN ya existe en el CSV, actualizará la fila correspondiente.
   - **Insert (Nuevos ETFs):** Si el ISIN no existe, creará una nueva fila al final del CSV, deduciendo su Clase de Activo.

2. **Data Shielding (Blindaje de Datos):**
   - Para las filas existentes, **NUNCA** se sobrescribirán las columnas base (`Nombre`, `ISIN`, `ClaseActivo`) ni ningún dato que ya tenga un valor real.
   - Solo se rellenarán los campos que estén en blanco, sean `NULL` o tengan el valor por defecto `0.0` (especialmente crítico para la "Cura de los Mixtos" en `Expo_RV`, `Expo_RF`, `Expo_Alt`).

3. **Alcance de la Extracción:**
   - **Costes:** TER (Total Expense Ratio).
   - **Exposición Geográfica:** % EE. UU., Europa, Emergentes, Japón, etc.
   - **Exposición Sectorial:** % Tecnología, Salud, Financiero, etc. (Para RV).
   - **Métricas RF:** Duración Media, Calidad Crediticia Media (Para RF).
   - **Asset Allocation:** Distribución real de activos (Para Mixtos).

4. **Procesamiento por Lotes (Batching):**
   - El script procesará un máximo de N archivos (por defecto 5) por ejecución para evitar el colapso de contexto del LLM y errores de API.

## 5. Esquema de Datos Exacto (JSON Schema)
El agente de extracción debe devolver un JSON que mapee **exactamente** contra estas columnas de nuestro CSV. Los nombres deben ser idénticos (Key del JSON = Nombre de Columna):

- **Básicos/Costes:** `Divisa`, `EsHedged`, `TER`, `EscalaRiesgo`, `ClaseActivo`
- **Exposiciones Core:** `Expo_RV`, `Expo_RF`, `Expo_Monet`, `Expo_Alt`
- **Exposición Geográfica RV:** `Geo_RV_USA`, `Geo_RV_Europa`, `Geo_RV_Japon`, `Geo_RV_Canada`, `Geo_RV_China`, `Geo_RV_India`, `Geo_RV_Taiwan`, `Geo_RV_Korea`, `Geo_RV_Brasil`, `Geo_RV_Emergentes_Otros`, `Geo_RV_Otros`
- **Exposición Geográfica RF:** `Geo_RF_USA`, `Geo_RF_Europa`, `Geo_RF_Emergentes`, `Geo_RF_Otros`
- **Exposición Sectorial RV:** `Sec_Tecnologia`, `Sec_Salud`, `Sec_Finanzas`, `Sec_Consumo`, `Sec_Industrial`, `Sec_Energia`, `Sec_Otros`
- **Métricas RF:** `RF_Duracion`, `RF_Calidad`, `RF_Gobierno`, `RF_Corporativo`, `RF_Yield`
- **Métricas de Rendimiento/Riesgo:** `Ret_1Y`, `Ret_3Y_Ann`, `Ret_5Y_Ann`, `Volatilidad_3Y`, `Sharpe_3Y`, `Alpha_3Y`, `Beta_3Y`

*(Nota de Negocio: Si el PDF no contiene un dato, o si el dato no aplica a la Clase de Activo del fondo, el sistema de extracción debe devolver `null`. La lógica de Data Shielding en el script de Python se encargará de gestionar esos nulos para no sobrescribir datos válidos previos).*