# Roadmap y Evolución del Proyecto: FundMix

Este documento define la trayectoria de desarrollo de FundMix. Sirve como contexto histórico y mapa de ruta para alinear cualquier nueva implementación con la visión a largo plazo del producto.

---

## 🟢 Fases Completadas (Core del Sistema)

Estas fases están desarrolladas, auditadas y en producción. El código relacionado con estas áreas es estable y cualquier modificación debe tratarse como un refactor crítico.

### Fase 1: Capa de Persistencia y Data Shielding
- **Hito:** Implementación de la base de datos SQLite (`FundMix.db`) y el archivo maestro de curación (`universo_fundmix.csv`).
- **Logros Técnicos:** 
  - Diseño de ingesta semántica por diccionarios para hacer la BBDD resistente a cambios de esquema.
  - Implementación del protocolo de *Data Shielding*: protección algorítmica ante datos nulos o asimétricos (penalizaciones defensivas en Renta Fija y neutralidad en Renta Variable).

### Fase 2: Motor Cuantitativo (El Cerebro)
- **Hito:** Desarrollo de `optimizer.py` utilizando CVXPY y ECOS.
- **Logros Técnicos:**
  - Sustitución de la aproximación de Markowitz por un sistema inverso de minimización de *Tracking Error*.
  - Formulación de restricciones lineales continuas (Long-Only, presupuesto 100%).
  - Linealización de ratios condicionales (Duración y Calidad Crediticia exclusivas de la sub-cartera de Renta Fija) manteniendo estrictamente la convexidad del problema matemático.
  - Implementación de la jerarquía de objetivos (Hard vs. Soft Constraints).

### Fase 3: Interfaz de Usuario e Interactividad
- **Hito:** Despliegue del dashboard analítico interactivo con Streamlit y Plotly (`app.py`).
- **Logros Técnicos:**
  - Panel de control dinámico sin recargas de estado pesadas.
  - Visualización en tiempo real de desviaciones y métricas de la cartera óptima.
  - Gestión paramétrica de coberturas de divisa (Hedging) selectivas.

---

## 🟡 Fase Actual (En Desarrollo)

Esta es la zona de trabajo activa. Las *features* actuales deben enfocarse exclusivamente en resolver este bloque.

### Fase 4: Ingesta Automática y Enriquecimiento de Datos (Modelo Híbrido)
- **Objetivo:** Reducir la fricción del mantenimiento del "Golden Record" conectando el sistema a fuentes de datos sin perder el enfoque "Boutique Quant".
- **Iniciativas:**
  - **(Feature 001 - ✅ Completada · 2026-07-25):** Integración del protocolo MCP para consultar métricas públicas fiables (TER, AUM, Volatilidad, SRRI) directamente desde el servidor del bróker y volcarlas al CSV local. Universo inicial cargado: **64 fondos** en `FundMix.db` (RV/RF/Monetario/Alternativo enrutados por la Convención Dinámica; 2 filas fantasma en blanco pendientes de ISIN). Hotfix arquitectónico incluido: columna `Expo_Alt` + restricción dura `max_alt_weight` en el motor y KPI en la UI.
  - **(Feature 002 - ✅ Completada · 2026-07-30):** Extracción automatizada de datos complejos (Geografía Pura, Duración de bonos, Calidad Crediticia real) mediante análisis de Factsheets oficiales en PDF. Pipeline en dos fases sin API de pago (`skills/procesar_pdfs.py`: `extract` → el agente lee los `.txt` condensados → `apply`), con condensación de documentos al 20% y validación de coherencia sobre la fila resultante. **86 factsheets procesados, 1.467 celdas escritas, 0 violaciones de Data Shielding.** Universo: **89 fondos**. Herramientas auxiliares: `limpiar_csv.py` (reparación estructural), `fix_geografia.py` (bypass acotado y auditado del blindaje) y `rellenar_manual.py` (relleno asistido por consola).
  - **(Feature 003 - 📋 Planificada):** **Enriquecimiento Web.** Ver detalle abajo.

#### Feature 003: Enriquecimiento Web (scraping de geografía y sectores)

- **Problema que resuelve:** los informes semestrales de la CNMV —única fuente disponible para los ~50 fondos españoles del universo— **no publican desglose geográfico, sectorial ni duración efectiva**. Solo aportan vocación inversora, perfil de riesgo, ratio de gastos y el reparto RF/RV/liquidez. Esto deja la cobertura de `Sec_*` en el 50,6% y la de `Geo_RV_*` en el 73,0%, justo las dimensiones que el optimizador usa como restricciones de Nivel 2 (prioridad máxima).
- **Alcance:** completar `Geo_RV_*`, `Geo_RF_*` y `Sec_*` de los fondos cuyo folleto no los publica, más las métricas a 3 años (`Sharpe_3Y`, `Alpha_3Y`, `Beta_3Y`, `Volatilidad_3Y`), hoy al 26,1%.
- **Fuentes candidatas:** Morningstar (ficha del fondo por ISIN), Yahoo Finance (`yfinance`, ya en `requirements.txt`) o el propio MCP del bróker si expone estos desgloses.
- **Restricciones heredadas de la Constitución:** el principio *Boutique Quant* dice explícitamente que preferimos carecer de un dato antes que "raspar HTML inestable". Por tanto la feature debe: (a) fijar la fuente por ISIN y registrarla en el CSV o en un log de procedencia, (b) validar cada extracción contra los rangos y sumas del pipeline actual, y (c) **reutilizar el Data Shielding y el guard de coherencia de fila ya implementados** en `skills/procesar_pdfs.py` en lugar de reescribirlos.
- **Riesgo principal:** el scraping se rompe en silencio cuando cambia el HTML. Necesita una prueba canario que falle ruidosamente si la estructura cambia, antes de escribir nada en el Golden Record.

---

## ⚪ Fases Futuras (Backlog Estratégico)

Iniciativas planificadas para escalar el producto una vez que la ingesta de datos sea robusta e independiente.

### Fase 5: Refinamiento de Usuario y Ponderación (Weighted Optimization)
- **Objetivo:** Otorgar mayor control al usuario en escenarios de "Infeasible Problem" o conflicto de restricciones.
- **Iniciativas:** Incorporación de multiplicadores dinámicos que permitan al usuario priorizar explícitamente qué objetivo ceder primero (ej. sacrificar precisión geográfica a cambio de mantener el TER bajo).

### Fase 6: Internacionalización (i18n)
- **Objetivo:** Expansión del público objetivo.
- **Iniciativas:** Arquitectura bilingüe (Español/Inglés) controlada por diccionarios de variables en la interfaz web, manteniendo el código matemático agnóstico al idioma.

### Fase 7: Modelos Avanzados de IA
- **Objetivo:** Análisis no supervisado del universo de inversión.
- **Iniciativas:** Integración de algoritmos de *Clustering* para descubrir similitudes ocultas entre fondos y crear sistemas de recomendación que sugieran alternativas eficientes a los activos elegidos por el usuario.

### Fase 8: Orquestación y Automatización
- **Objetivo:** Eliminar la dependencia de la ejecución manual una vez que la ingesta de datos sea infalible.
- **Iniciativas:** Configuración de un orquestador (como Apache Airflow o GitHub Actions) para ejecutar de forma autónoma el pipeline de ingesta (MCP + Factsheets PDF) con una periodicidad mensual, coincidiendo con la actualización de carteras de las gestoras.