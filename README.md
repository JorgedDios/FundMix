# FundMix
Sistema inverso de asignación de pesos para carteras de fondos de inversión
# 🧠 FundMix – Asistente Inteligente para Composición de Carteras

**FundMix** es una herramienta desarrollada en Python cuyo objetivo es ayudar a los usuarios a construir carteras de inversión personalizadas, ajustadas a sus preferencias específicas. El usuario define condiciones como exposición geográfica, sectorial o temática, límites de comisiones, tipo de gestión (activa/pasiva), y el sistema le indica en qué fondos debe invertir y en qué proporción.  

Es, esencialmente, un **sistema inverso de asignación de pesos**.  

---

## 🔧 ¿Qué puede hacer FundMix?

- Recibe criterios de inversión del usuario: país, sector, temática, comisiones máximas, tipo de gestión, etc.
- Busca fondos que cumplan con las condiciones.
- Calcula los pesos exactos que cada fondo debe tener en la cartera final.
- Utiliza métodos de optimización lineal (`scipy.optimize.linprog`, `cvxpy`) para resolver el sistema.
- Parte de una **base de datos local de fondos**, introducida manualmente en una primera versión.
- Permite escalar a cientos de fondos con múltiples dimensiones.

---

## 💬 Ejemplo de uso

El usuario indica que quiere:

- 50% de exposición a EE.UU. (equiponderado)
- 20% de exposición a China
- 50% del total invertido en el sector tecnológico
- Comisiones inferiores al 0.5%

**Resultado posible:**

- 35% en MSCI World  
- 45% en fondo MYIN (S&P500 equiponderado)  
- 20% en fondo tecnológico chino

---

## 🔄 Evolución prevista

- Añadir función que actualice la base de datos automáticamente desde APIs o páginas web.
- Detectar diferencias entre la base de datos local y externa y sugerir actualizaciones.
- Crear interfaz gráfica (Tkinter, PyQt) o aplicación web (Flask, Django).
- Soporte para criterios adicionales: rating ESG, volatilidad, riesgo, drawdown, exposición a divisa, etc.

---

## 🤖 IA y aprendizaje automático

Se planea introducir técnicas de inteligencia artificial para:

- Aprender de carteras anteriores y mejorar la asignación.
- Recomendar fondos en función del perfil de usuario.
- Predecir exposiciones óptimas en base a datos económicos, correlaciones y tendencias.
- Utilizar clustering, aprendizaje por refuerzo o sistemas de recomendación.
- Incorporar noticias o eventos de mercado en las sugerencias.

---

## 📚 Aplicaciones

- Herramienta educativa para comprender cómo se construyen carteras diversificadas.
- Soporte profesional para asesores financieros o analistas cuantitativos.
- Proyectos académicos o investigación aplicada sobre optimización de carteras.

---

Este repositorio está construido con las buenas prácticas de versionado usando Git y GitHub, incluyendo configuración de `.gitignore`, documentación modular, uso de ramas para nuevas funcionalidades y posibilidad de automatización futura.

¡Bienvenido a FundMix! ✨


VER SI LA DESCRIPCIÓN DE ARRIBA TIENE LO MISMO QUE LA DE ABAJO

# FundMix - Asistente Inteligente para Composición de Carteras

# FundMix será un programa donde el usuario podrá introducir cómo desea invertir su dinero: 
# especificando porcentajes por país, sector, exposición temática, tipo de fondos, comisiones máximas, 
# gestión activa o pasiva, y otras restricciones relevantes.

# El programa devolverá en qué fondos invertir y en qué proporción, respetando todas las condiciones 
# introducidas por el usuario. Es, esencialmente, un sistema inverso de asignación de pesos.

# Para ello se creará una base de datos de fondos, inicialmente introducida manualmente, incluyendo los 
# datos relevantes de cada uno (geografía, sector, comisiones, tipo de gestión, etc.).

# Más adelante se añadirá una función que actualice automáticamente la base de datos a partir de fuentes reales 
# (webs, APIs) y que avise si encuentra diferencias con la base de datos local.

# El proyecto es altamente escalable: se podrán cargar cientos de fondos, y es aplicable al mundo real. 
# Además, es flexible: soporta múltiples dimensiones de exposición (geográfica, sectorial, temática, ESG...).

# --- Ejemplo inicial simple de uso:
# Quiero una cartera con:
# - 50% en EE.UU. (equiponderado),
# - 20% en China,
# - 50% del total en tecnología,
# - Fondos con comisiones menores a 0.5%

# Resultado esperado (ejemplo):
# - 35% en MSCI World,
# - 45% en fondo MYIN (S&P500 equiponderado),
# - 20% en fondo tecnológico chino

# En su versión más sencilla, esto se resuelve como un sistema de ecuaciones lineales, 
# donde las incógnitas son los pesos de cada fondo. Herramientas en Python que he dado en optimizacion y sirven:
# - scipy.optimize.linprog
# - cvxpy

# --- Mejoras futuras:
# - Interfaz gráfica o aplicación web
# - Soporte para más dimensiones: volatilidad, rating ESG, riesgo, drawdown...
# - Importación automática de datos reales
# - Optimización basada en Machine Learning

# --- Aplicaciones de Inteligencia Artificial:
# - Modelos que aprendan a asignar pesos óptimos a partir de casos anteriores
# - Sistemas que aprendan del comportamiento de usuarios para recomendar carteras
# - Modelos predictivos de exposiciones óptimas en base a previsiones de riesgo, correlaciones, tendencias, datos macroeconómicos, noticias, etc.
# - Técnicas de aprendizaje por refuerzo, clustering, predicción o sistemas de recomendación

# FundMix será una herramienta educativa y profesional para la planificación de carteras personalizadas basada en objetivos concretos.
