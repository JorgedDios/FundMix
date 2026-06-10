# 🧬 FundMix: Asistente Inteligente para la Composición de Carteras

FundMix es una herramienta avanzada de ingeniería financiera desarrollada en Python. Su objetivo es ayudar a inversores y asesores a construir carteras de inversión personalizadas (Fondos y ETFs) totalmente adaptadas a sus preferencias específicas.

A diferencia de los optimizadores tradicionales basados en la Teoría de Markowitz (que requieren predecir rentabilidades futuras), FundMix opera como un **sistema inverso de asignación de pesos**. El usuario define su perfil ideal (exposición geográfica, sectorial, nivel de riesgo, costes máximos y política de divisa) y el motor calcula la combinación matemática exacta de activos que minimiza la desviación (*Tracking Error*) frente a ese objetivo.

---

## 🔧 ¿Qué hace FundMix? (Características Actuales)

* **Ingesta y Gestión de Datos Eficiente:** Capa de persistencia local optimizada para la lectura rápida del universo de inversión.
* **Segmentación Geográfica Dual:** Separa los riesgos de mercado y de tipo de interés distinguiendo entre geografía de Renta Variable (`Geo_RV`) y Renta Fija (`Geo_RF`).
* **Motor de Optimización Convexa:** Resuelve asignaciones complejas en milisegundos garantizando el óptimo global mediante programación cuadrática.
* **Lógica de Negocio Defensiva (*Data Shielding*):** Penaliza automáticamente activos con información incompleta para proteger la cartera de la incertidumbre.
* **Gestión Granular de Divisas:** Permite aplicar coberturas de tipo de cambio (*Hedging*) de forma selectiva por clase de activo.
* **Interfaz de Usuario Interactiva:** Panel visual dinámico con gráficos en tiempo real y reportes de auditoría de desviaciones.

---

## 🛠️ Arquitectura Técnica y Stack Tecnológico

El proyecto está diseñado bajo un enfoque modular, separando estrictamente la persistencia, la lógica matemática y la capa de presentación:

* **Base de Datos (Fase 1):** `SQLite3` (archivo local `FundMix.db`). Implementa un sistema de inyección semántica por diccionarios que la hace inmune a cambios futuros en el esquema de la tabla.
* **Motor Matemático (Fase 2):** `CVXPY` + `Pandas` + `NumPy`. Formulación de restricciones lineales (*Long-Only*, presupuesto del 100%) y linealización de ratios condicionales para optimizar métricas exclusivas de Renta Fija (como la *Duración*) sin romper la convexidad del problema.
* **Interfaz Gráfica (Fase 3):** `Streamlit` + `Plotly`. Dashboard interactivo web *serverless* que actúa como panel de control del optimizador.

---

## 💬 Ejemplo Práctico de Uso

**Entrada del Usuario (Deseos):**
* 60% de exposición a Renta Variable de EE.UU.
* 40% de exposición a Renta Fija Global.
* Duración media de la Renta Fija de 3.0 años.
* Nivel de riesgo global de la cartera ajustado a un SRRI de 4.0.
* Preferencias: Evitar vehículos estructurados como ETFs (priorizar Fondos) y exigir cobertura de divisa (*Hedged*) exclusivamente en la parte de bonos.

**Resultado del Motor:**
El sistema procesa el universo disponible en la base de datos y devuelve la lista de activos óptima con sus pesos exactos (ej. *45% Amundi Index MSCI World, 35% iShares Core S&P 500, 20% iShares Global Agg Bond*), junto con un reporte de auditoría que demuestra el cumplimiento de los objetivos.

---

## 🔄 Roadmap (Evolución del Proyecto)

* [🚀 **En Desarrollo**] **Fase 4: Ingesta Automática de Datos Reales.** Desarrollo de un Web Scraper (Morningstar/Yahoo Finance) o integración de APIs financieras para poblar la base de datos con miles de activos reales en tiempo real.
* [🔮 **Próximamente**] **Fase 5: Refinamiento de Usuario y Ponderación.** Incorporación de un sistema de pesos (*Weighted Optimization*) para permitir al usuario priorizar unos objetivos sobre otros en caso de conflicto matemático.
* [🔮 **Próximamente**] **Internacionalización (i18n):** Soporte bilingüe completo (Español / Inglés) configurable desde la interfaz.
* [🤖 **Futuro**] **Modelos Avanzados de IA:** Integración de algoritmos de Clustering para clasificación de estilo y sistemas de recomendación basados en el comportamiento histórico del usuario.

---

## 📚 Aplicaciones

* **Educativa:** Herramienta interactiva para estudiantes y analistas que deseen comprender la construcción de carteras diversificadas y las matemáticas de la optimización convexa.
* **Profesional:** Soporte cuantitativo para asesores financieros y gestores de patrimonio que busquen automatizar la asignación de activos orientada a objetivos específicos (*Goal-Based Investing*).
