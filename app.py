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
    with st.expander("🌍 Geografía (Renta Variable)", expanded=True):
        target_usa = st.slider("🇺🇸 Exposición EE.UU.", 0.0, 1.0, 0.60, step=0.05)
        target_europa = st.slider("🇪🇺 Exposición Europa", 0.0, 1.0, 0.20, step=0.05)
        target_emerg = st.slider("🌏 Exposición Emergentes", 0.0, 1.0, 0.10, step=0.05)
    
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
        st.info("El sistema buscará fondos que promedien este riesgo exacto.")

    st.header("⚙️ Preferencias")
    
    # Preferencias (-1 a 1)
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
    # Solo enviamos lo que el usuario ha tocado para no meter ruido
    objetivos_usuario = {
        'Geo_RV_USA': target_usa,
        'Geo_RV_Europa': target_europa,
        'Geo_RV_Emergentes': target_emerg,
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
            preference_hedged_rf=pref_hedged_rf
        )

    # ==============================================================================
    # 3. VISUALIZACIÓN DE RESULTADOS
    # ==============================================================================
    if resultado is not None:
        st.success("✅ ¡Solución Óptima Encontrada!")
        
        # --- A. CÁLCULO DE KPIs REALES (AUDITORÍA VISUAL) ---
        peso = resultado['Peso_Optimizado'].values
        peso_rf_total = (resultado['Peso_Optimizado'] * resultado['is_RF_Universe']).sum()
        
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
        kpi1, kpi2, kpi3, kpi4 = st.columns(4)
        kpi1.metric("Fondos Seleccionados", len(resultado))
        kpi2.metric("Riesgo Cartera (SRRI)", f"{(resultado['EscalaRiesgo'] * resultado['Peso_Optimizado']).sum():.2f}", f"Obj: {target_riesgo}")
        kpi3.metric("Duración RF (Años)", f"{dur_real:.1f}", f"Obj: {target_duracion}")
        kpi4.metric("Calidad Crediticia", cal_txt, f"Score: {cal_real:.1f}")

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
                'Nombre', 'Ticker', 'ClaseActivo', 'RF_Duracion', 'EscalaRiesgo', 'Peso_Optimizado'
            ]].copy()
            
            # Formato Porcentaje
            tabla_visual['Peso'] = tabla_visual['Peso_Optimizado'].apply(lambda x: f"{x:.1%}")
            
            st.dataframe(
                tabla_visual.drop(columns=['Peso_Optimizado']),
                hide_index=True,
                use_container_width=True
            )

        # --- D. AUDITORÍA DETALLADA (EXPANDER) ---
        with st.expander("🔍 Ver Auditoría de Desviaciones (Debug)"):
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