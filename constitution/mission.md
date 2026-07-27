# Misión: FundMix

_FundMix es un motor cuantitativo institucional para la construcción de carteras personalizadas, diseñado para resolver el problema de la sobre-restricción matemática en el Asset Allocation mediante priorización jerárquica._

## Qué construimos

Una herramienta de ingeniería financiera que opera como un sistema inverso de asignación de pesos: en lugar de predecir el mercado, el motor calcula la combinación matemática exacta de activos (Fondos y ETFs) que minimiza la desviación (Tracking Error) frente al perfil ideal definido por el usuario.

1. **Base de Datos ("Golden Record")** — Un repositorio local SQLite, estructurado y blindado, poblado únicamente con un universo curado de activos de alta calidad.
2. **Motor Cuantitativo (CVXPY)** — El cerebro algorítmico que resuelve el problema de Programación Cuadrática en milisegundos aplicando restricciones lineales y penalizaciones elásticas (Soft Constraints).
3. **Interfaz Interactiva (Streamlit)** — Un panel de control visual para configurar objetivos granulares (geografía, sectores, riesgo) y auditar de forma transparente el resultado matemático de la cartera.

## Para quién

- **Gestores de patrimonio y Asesores financieros:** Que buscan automatizar la creación de carteras orientadas a objetivos específicos (*Goal-Based Investing*) sin depender de modelos predictivos frágiles.
- **Inversores particulares avanzados:** Que exigen un control institucional sobre su Asset Allocation, diferenciando riesgos como la geografía de la renta fija vs. la renta variable, o coberturas de divisa específicas.

## Principios

- **Modelo "Boutique Quant" (Calidad sobre Cantidad):** Priorizamos la precisión absoluta de los datos. Trabajamos con un Universo de Inversión Aprobado (APL) cuidadosamente seleccionado. Preferimos carecer de un dato antes que inyectar un valor falso o raspar HTML inestable.
- **Data Shielding (Defensa Activa):** Ante la ausencia de información crítica (como el riesgo crediticio), el sistema jamás asume un valor neutro que pueda pasar desapercibido. Siempre imputa el peor escenario posible para obligar al algoritmo a penalizar y evitar ese activo, protegiendo así la cartera final.
- **Jerarquía de Objetivos (Tolerancia Matemática):** Para evitar la sobre-restricción, el optimizador clasifica las variables estrictamente en tres niveles:
  - *Nivel 1 (Hard Constraints):* Presupuesto = 100%, Prohibición de cortos (w >= 0), Exclusiones estáticas (0% estricto).
  - *Nivel 2 (Prioridad Máxima - Multiplicador x100):* Asset Allocation (Exposición RF/RV), Geografía y Duración.
  - *Nivel 3 (Prioridad Blanda - Multiplicador x1):* Preferencias de Vehículo (ETF/Fondo), Política de Dividendos, Cobertura de Divisa (Hedged), Max_Activa y Bandas de Estilo.

## Qué NO es

- **NO es un Robo-Advisor predictivo:** No intentamos predecir retornos futuros ni dependemos de la Teoría de Markowitz (matrices de covarianzas inestables). Maximizamos el cumplimiento del perfil del usuario, no el Alpha.
- **NO es un agregador masivo:** No operamos con miles de fondos rellenados mediante web scraping frágil. Operamos con precisión quirúrgica.
- **NO es una plataforma de Trading:** No ejecuta órdenes en brokers; es estrictamente una herramienta analítica.