# librería que convierte código Python en una página web.
import streamlit as st 
# Para mostrar los dataframes en la web bonitos
import pandas as pd
# librería para gráficos (potente e interactivo)
import plotly.express as px
import numpy as np

# Importamos el cerebro 
import optimizer

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(
    # titulo que saldrá en la pestaña del navegador
    page_title="FundMix Pro",
    # icono de la pestaña que acompaña al titulo
    page_icon="🧬",
    # CRÍTICO. Por defecto, Streamlit centra todo en una columna estrecha (como un blog). 
    # Con "wide", usamos todo el ancho de la pantalla. Necesitamos esto para poner gráficos y tablas lado a lado.
    layout="wide",
    # Fuerza a que la barra lateral (donde estarán los sliders) aparezca abierta al cargar la página.
    initial_sidebar_state="expanded",
    # para poner en los 3 puntitos, muy útil, mas adelante se pueden poner mas cosas, ahora de ejemplo dejos estas
    menu_items={
        'Get Help': 'https://miweb.com/ayuda',
        'Report a bug': "https://miweb.com/bug",
        'About': "# FundMix v1.0\nEsta app fue creada por Jorge para dominar el mundo financiero."
    }
)

# --- CSS (Opcional, para pulir detalles) ---
# Streamlit no te deja tocar mucho el diseño por defecto, pero con st.markdown podemos inyectar código CSS (hojas de estilo).
# en este caso: Busca los elementos llamados .stMetric (que son esas tarjetas grandes con números que dicen "Riesgo: 4.0") y les aplica un estilo:
st.markdown("""
<style>
    .stMetric {
        background-color: #f0f2f6;
        padding: 10px;
        border-radius: 5px;
    }
</style>
""", unsafe_allow_html=True)
# unsafe_allow_html=True: Es un permiso de seguridad. Le dices a Streamlit: "Sé lo que hago, déjame meter código HTML/CSS a mano"

# --- TÍTULO ---
# escribe encabezado H1 (grande y negrita)
# ESTO ES HTML Y ESTO LO DIMOS EN INFORMATICA DE LA ESO.
st.title("🧬 FundMix: Optimizador de Carteras Inteligente")
# Escribe texto enriquecido. Los asteriscos dobles **...** ponen el texto en negrita.
st.markdown("Construcción de carteras mediante **Minimización de Tracking Error** y Programación Cuadrática.")

# ==============================================================================
# 1. BARRA LATERAL (INPUTS DEL USUARIO)
# ==============================================================================
with st.sidebar:
    st.header("🎯 Define tu Objetivo")
    
    # --- BLOQUE 1: GEOGRAFÍA (RENTA VARIABLE) ---
    # OJO: estos porcentajes son el reparto DENTRO de la Renta Variable, no sobre el
    # total de la cartera. Es el modelo top-down estándar: primero decides el 60/40
    # entre clases (slider "Peso Total Renta Fija") y aquí repartes tu bolsa.
    with st.expander("🌍 Geografía (Renta Variable)", expanded=True):
        st.caption("Reparto **dentro de tu Renta Variable**. Deberían sumar ≤ 100%; "
                   "lo que dejes sin asignar queda libre para el optimizador.")
        target_usa = st.slider("🇺🇸 EE.UU. (% de tu RV)", 0.0, 1.0, 0.60, step=0.05)
        target_europa = st.slider("🇪🇺 Europa (% de tu RV)", 0.0, 1.0, 0.20, step=0.05)
        # === NUEVO V2.1: SLIDERS PARA JAPÓN, CANADÁ Y EMERGENTES TOTALES ===
        target_emerg = st.slider("🌏 Emergentes, total (% de tu RV)", 0.0, 1.0, 0.10, step=0.05)
        target_japon = st.slider("🇯🇵 Japón (% de tu RV)", 0.0, 1.0, 0.0, step=0.05)
        target_canada = st.slider("🇨🇦 Canadá (% de tu RV)", 0.0, 1.0, 0.0, step=0.05)
        # =================================================================
        _suma_geo = target_usa + target_europa + target_emerg + target_japon + target_canada
        if _suma_geo > 1.0:
            st.warning(f"Has repartido un {_suma_geo:.0%} de tu Renta Variable. "
                       "Al pasar del 100% el motor no podrá cumplir todos los objetivos "
                       "y repartirá el error entre ellos.")
    
    # --- BLOQUE 2: RENTA FIJA PRO ---
    with st.expander("🛡️ Renta Fija Avanzada", expanded=True):
        target_rf = st.slider("Peso Total Renta Fija", 0.0, 1.0, 0.40, step=0.05)
        
        st.caption("Objetivos específicos para la parte de Bonos:")
        target_duracion = st.slider("⏳ Duración Objetivo (Años)", 0.0, 15.0, 4.0, step=0.5,
                                   help="El optimizador ajustará esto SIN que la bolsa lo diluya.")
        
        # Mapeo inverso visual para el usuario (Letra -> Número)
        # El usuario elige 'A', nosotros enviamos '3.0' al motor
        calidad_opciones = {
            "AAA (Excelente)": 1.0,
            "AA (Muy Buena)": 2.0,
            "A (Buena)": 3.0,
            "BBB (Inversión)": 4.0,
            "High Yield (Riesgo)": 6.0
        }
        calidad_seleccion = st.select_slider(
            "💎 Calidad Crediticia Objetivo",
            options=list(calidad_opciones.keys()),
            value="A (Buena)"
        )
        target_calidad_num = calidad_opciones[calidad_seleccion]

    # --- BLOQUE 3: RIESGO Y SECTORES ---
    with st.expander("⚠️ Perfil de Riesgo", expanded=False):
        target_riesgo = st.slider("Nivel SRRI (1-7)", 1.0, 7.0, 4.0, step=0.1)
        st.caption("Indicador informativo: el motor no optimiza sobre el SRRI, "
                   "porque el riesgo real ya viene determinado por el reparto "
                   "entre clases de activo, la geografía y la duración. "
                   "En el panel verás el SRRI resultante de tu cartera.")
    st.header("⚙️ Preferencias y Filtros")
    
    # === NIVEL 1 (HARD): EXCLUSIÓN DE ESTRATEGIAS ===
    # Fuente de verdad única para los dos widgets (antes eran dos listas de 6 que no
    # coincidían: 'Alternativo'/'Inmobiliario' no tenían banda y 'Quality'/'Defensivo'
    # no se podían excluir).
    ESTRATEGIAS_PRINCIPALES = ['Core', 'Value', 'Growth', 'Dividendo', 'Flexible',
                               'Small Cap', 'Alternativo', 'Inmobiliario',
                               'Quality', 'Defensivo']
    # 'Alternativo' es categoría padre; estas son sus hijas. Solo se muestran si el
    # usuario interactúa con el padre, para no saturar la interfaz.
    SUBESTRATEGIAS_ALT = ['Event Driven', 'Market Neutral', 'Multiestrategia']

    estrategias_a_excluir = st.multiselect(
        "🚫 Estrategias a Excluir (0%)",
        options=ESTRATEGIAS_PRINCIPALES,
        default=[]
    )

    # Submenú condicional: solo aparece si el usuario toca la categoría padre.
    rescatadas = []
    if 'Alternativo' in estrategias_a_excluir:
        st.caption("↳ Se excluyen también Event Driven, Market Neutral y Multiestrategia. "
                   "Marca las que quieras mantener disponibles:")
        rescatadas = st.multiselect(
            "Excepto estas subestrategias",
            options=SUBESTRATEGIAS_ALT,
            default=[],
            key="rescate_alt"
        )

    # Si el usuario ha afinado, resolvemos la selección a nivel de hoja aquí y le decimos
    # al motor que NO vuelva a expandir (si lo hiciera, desharía el rescate).
    if rescatadas:
        familia_alt = ['Alternativo'] + SUBESTRATEGIAS_ALT
        exclusion_final = [e for e in estrategias_a_excluir if e != 'Alternativo']
        exclusion_final += [s for s in familia_alt if s not in rescatadas]
        expandir_familias = False
    else:
        exclusion_final = estrategias_a_excluir
        expandir_familias = True

   # === NIVEL 3 (SOFT): BANDAS DE ESTILO (TILTING) ===
    st.markdown("---")
    st.subheader("🎯 Sesgo de Estilo (Opcional)")
    
    # Diccionario de traducción: Texto -> (Min, Max)
    bandas_dict = {
        "Sin preferencia (Ignorar)": (0.0, 1.0),
        "Táctica (0% - 25%)": (0.0, 0.25),
        "Convencional (25% - 50%)": (0.25, 0.50),
        "Estructural (50% - 75%)": (0.50, 0.75),
        "Agresiva (75% - 100%)": (0.75, 1.0)
    }
    
    estrategias_bandas = {}

    # Usamos st.columns para poner los selectores en 2 columnas y ahorrar espacio visual
    cols_est = st.columns(2)
    for i, strat in enumerate(ESTRATEGIAS_PRINCIPALES):
        with cols_est[i % 2]:
            seleccion = st.selectbox(strat, options=list(bandas_dict.keys()), key=f"banda_{strat}")
            estrategias_bandas[strat] = bandas_dict[seleccion]

    # Afinado opcional de la familia alternativa. La banda del padre y las de las hijas
    # NUNCA coexisten: se sustituyen, para no superponer dos penalizaciones sobre los
    # mismos fondos (contarían doble en la función objetivo).
    if estrategias_bandas.get('Alternativo', (0.0, 1.0)) != (0.0, 1.0):
        if st.checkbox("↳ Afinar la banda por subestrategia alternativa"):
            del estrategias_bandas['Alternativo']
            cols_sub = st.columns(2)
            for i, sub in enumerate(SUBESTRATEGIAS_ALT):
                with cols_sub[i % 2]:
                    sel = st.selectbox(sub, options=list(bandas_dict.keys()), key=f"banda_{sub}")
                    estrategias_bandas[sub] = bandas_dict[sel]
            
    st.markdown("---")

    # === PREFERENCIAS CLÁSICAS ===
    max_activa = st.slider("Límite Gestión Activa (Suave)", 0.0, 1.0, 0.20, help="El motor penalizará si supera este %")

    # === NUEVO V4: LÍMITE DURO DE FONDOS ALTERNATIVOS ===
    st.caption("Fondos Alternativos: Estrategias (ej. Retorno Absoluto, Long/Short) diseñadas para comportarse de forma descorrelacionada al mercado, aportando estabilidad cuando la bolsa y los bonos tradicionales caen.")
    max_alt_pct = st.slider("Exposición máxima a Alternativos", 0, 100, 15, format="%d%%")
    st.caption("(Recomendado: máx. 20% por coste de oportunidad y altas comisiones)")
    max_alt_weight = max_alt_pct / 100.0

    pref_etf = st.select_slider(
        "Vehículo", 
        options=[-1.0, -0.5, 0.0, 0.5, 1.0], 
        value=-0.5,
        format_func=lambda x: "Prefiero Fondos" if x < 0 else ("Prefiero ETFs" if x > 0 else "Indiferente")
    )
    
    col_p1, col_p2 = st.columns(2)
    with col_p1:
        pref_hedged_rv = st.slider("Divisa RV", -1.0, 1.0, -1.0, help="Negativo = Sin Cubrir")
    with col_p2:
        pref_hedged_rf = st.slider("Divisa RF", -1.0, 1.0, 1.0, help="Positivo = Cubierta (Hedged)")

    # Sesgo de gestión por clase de activo (modelo Core-Satellite).
    # Un fondo mixto reparte su etiqueta entre ambas patas según su exposición real, así
    # que pedir "bolsa pasiva + bonos activos" no genera un choque de restricciones.
    st.caption("Estilo de gestión por clase (Core-Satellite):")
    col_g1, col_g2 = st.columns(2)
    with col_g1:
        pref_activa_rv = st.slider("Gestión RV", -1.0, 1.0, 0.0,
                                   help="Negativo = Indexada/Pasiva · Positivo = Activa")
    with col_g2:
        pref_activa_rf = st.slider("Gestión RF", -1.0, 1.0, 0.0,
                                   help="Negativo = Indexada/Pasiva · Positivo = Activa")
    calcular = st.button("🚀 Optimizar Cartera", type="primary", use_container_width=True)

# ==============================================================================
# 2. LÓGICA DE EJECUCIÓN
# ==============================================================================
if calcular:
    # 1. Cargar Datos (Usando tu función blindada)
    df_fondos = optimizer.get_data_from_db()
    
    if df_fondos.empty:
        st.error("❌ Error: No se pudieron cargar datos de la base de datos.")
        st.stop()

    # 2. Empaquetar Objetivos (Mapeo UI -> Backend)
    objetivos_usuario = {
        'Geo_RV_USA': target_usa,
        'Geo_RV_Europa': target_europa,
        'Geo_RV_Emergentes_Total': target_emerg,
        'Geo_RV_Japon': target_japon,
        'Geo_RV_Canada': target_canada,
        'Expo_RF': target_rf,
        'RF_Duracion': target_duracion,
        'RF_Calidad_Num': target_calidad_num,
        'EscalaRiesgo': target_riesgo
    }

    with st.spinner('El motor matemático está resolviendo las ecuaciones cuadráticas...'):
        # 3. LLAMADA AL CEREBRO
        resultado = optimizer.optimize_portfolio(
            df_fondos,
            objetivos_usuario,
            preference_etf=pref_etf,
            preference_hedged_rv=pref_hedged_rv,
            preference_hedged_rf=pref_hedged_rf,
            max_activa=max_activa,
            exclude_strategies=exclusion_final,        # Nivel 1 variable (ya resuelta)
            estrategias_bandas=estrategias_bandas,    # Nivel 3 variable
            max_alt_weight=max_alt_weight,            # Nivel 1: límite duro de alternativos
            expandir_familias=expandir_familias,      # Jerarquía padre-hijo de estrategias
            preference_activa_rv=pref_activa_rv,      # Nivel 3: sesgo de gestión en bolsa
            preference_activa_rf=pref_activa_rf       # Nivel 3: sesgo de gestión en bonos
        )

    # ==============================================================================
    # 3. VISUALIZACIÓN DE RESULTADOS
    # ==============================================================================
    if resultado is not None:
        st.success("✅ ¡Solución Óptima Encontrada!")
        
        # --- A. CÁLCULO DE KPIs REALES (AUDITORÍA VISUAL) ---
        peso = resultado['Peso_Optimizado'].values
        peso_rf_total = (resultado['Peso_Optimizado'] * resultado['is_RF_Universe']).sum()

        # Exposición real a Fondos Alternativos (para verificar el límite duro)
        peso_alt_total = (resultado['Peso_Optimizado'] * resultado['is_Alt']).sum()
        
        # Cálculo Duración Real (Renormalizada)
        dur_bruta = (resultado['Peso_Optimizado'] * resultado['RF_Duracion']).sum()
        dur_real = dur_bruta / peso_rf_total if peso_rf_total > 0.01 else 0.0
        
        # Cálculo Calidad Real (Renormalizada)
        cal_bruta = (resultado['Peso_Optimizado'] * resultado['RF_Calidad_Num']).sum()
        cal_real = cal_bruta / peso_rf_total if peso_rf_total > 0.01 else 0.0
        
        # Traducción de Calidad (Número -> Texto)
        if cal_real <= 1.5: cal_txt = "AAA"
        elif cal_real <= 2.5: cal_txt = "AA"
        elif cal_real <= 3.5: cal_txt = "A"
        elif cal_real <= 4.5: cal_txt = "BBB"
        elif cal_real <= 10.0: cal_txt = "High Yield"
        else: cal_txt = "⚠️ Datos Insuf."

        # --- B. MOSTRAR KPIs ---
        kpi1, kpi2, kpi3, kpi4, kpi5 = st.columns(5)
        kpi1.metric("Fondos Seleccionados", len(resultado))
        kpi2.metric("Riesgo Cartera (SRRI)", f"{(resultado['EscalaRiesgo'] * resultado['Peso_Optimizado']).sum():.2f}")
        kpi3.metric("Duración RF (Años)", f"{dur_real:.1f}", f"Obj: {target_duracion}", delta_color="off")
        kpi4.metric("Calidad Crediticia", cal_txt, f"Score: {cal_real:.1f}", delta_color="off")
        kpi5.metric("Exposición Alternativos", f"{peso_alt_total:.1%}", f"Límite: {max_alt_weight:.0%}", delta_color="off")

        # --- C. GRÁFICOS Y TABLA ---
        col_graf, col_tabla = st.columns([1, 2])
        
        with col_graf:
            st.subheader("Allocación de Activos")
            # Gráfico de Donut por Clase de Activo
            fig = px.pie(resultado, values='Peso_Optimizado', names='ClaseActivo', hole=0.4)
            fig.update_layout(margin=dict(t=0, b=0, l=0, r=0), height=300)
            st.plotly_chart(fig, use_container_width=True)

        with col_tabla:
            st.subheader("📋 Tu Cartera Optimizada")
            # Preparamos tabla bonita
            tabla_visual = resultado[[
                'Nombre', 'ClaseActivo', 'Peso_Optimizado',
            ]].copy()
            
            # Formato Porcentaje
            tabla_visual['Peso'] = tabla_visual['Peso_Optimizado'].apply(lambda x: f"{x:.1%}")
            
            st.dataframe(
                tabla_visual.drop(columns=['Peso_Optimizado']),
                hide_index=True,
                use_container_width=True
            )

        # --- D. AUDITORÍA DETALLADA (EXPANDER) ---
        with st.expander("🔍 Ver Auditoría de Desviaciones "):
            st.write("Comparativa exacta entre lo que pediste y lo que la matemática ha conseguido:")
            
            audit_data = []
            for metrica, target in objetivos_usuario.items():
                if metrica in resultado.columns:
                    val_bruto = (resultado[metrica] * resultado['Peso_Optimizado']).sum()
                    
                    # Lógica Renormalización RF
                    if metrica.startswith('RF_') and peso_rf_total > 0.01:
                        val_final = val_bruto / peso_rf_total
                    else:
                        val_final = val_bruto
                        
                    audit_data.append({
                        "Métrica": metrica,
                        "Objetivo User": target,
                        "Resultado Math": val_final,
                        "Desviación": val_final - target
                    })
            
            st.dataframe(pd.DataFrame(audit_data))

    else:
        st.error("❌ No se encontró una solución matemática factible.")
        st.warning("Prueba a relajar las restricciones (ej. no pidas mucha rentabilidad con riesgo muy bajo).")