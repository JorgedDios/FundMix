import sqlite3
import pandas as pd
import cvxpy as cp
import numpy as np

# Configuración
DB_FILE = 'FundMix.db'

def get_data_from_db():
    """
    Paso 1: Cargar los datos de SQLite a un DataFrame de Pandas.
    """
    # lo hacemos con with y no con conn.close para:
    # con conn.close(): 
    # Esto está bien ahora. Pero si mañana tu app tiene 100 usuarios a la vez, abrir y cerrar conexiones SQLite por cada cálculo es lento.
    # Solución Profesional (Best Practice): Usar un Context Manager (with) para asegurar que la conexión se cierra incluso si hay un error de lectura, 
    # y para gestionar mejor los recursos.
    with sqlite3.connect(DB_FILE) as conn:
        df = pd.read_sql("SELECT * FROM fondos", conn)
    # No hace falta conn.close(), el 'with' lo hace solo.
    
    
    # ORDINAL ENCODING 
    # Definimos el mapa de traducción (diccionario)
    quality_map = {
        'AAA': 1, 'AA': 2, 'A': 3, 
        'BBB': 4, 'BB': 5, 'B': 6, 
        'CCC': 7, 'CC': 8, 'C': 9, 'D': 10
    }
    
    # Aplicamos el mapa. 
    # Los que no sean bonos (ej. Acciones) tendrán nulos, los rellenamos con 0 o un valor neutro, previamente en el .filna(0)

    # Aquí usamos un truco: Si es RV, le ponemos un 0 para que no afecte al promedio de riesgo de crédito
    df['RF_Calidad_Num'] = df['RF_Calidad'].map(quality_map)

    
    # Convertimos TipoProducto a binario (para usarlo luego en penalizaciones)
    # 1 si es ETF, 0 si es Fondo
    df['is_ETF'] = (df['TipoProducto'] == 'ETF').astype(int)

    # Distribución (1) vs Acumulación (0)
    # Si el usuario odia los dividendos, penalizaremos los que tengan is_Dist = 1
    df['is_Dist'] = (df['PoliticaDiv'] == 'Dist').astype(int)

    # ---  BANDERAS AVANZADAS (HEDGING POR CLASE) ---
    
    # Detectamos si es Hedged (General)
    is_hedged_global = df['EsHedged'].isin(['Si', 'Yes', 'Cubierto', 'Hedged', 'True'])
    
    # Detectamos Clase de Activo
    # is_rv e is_rf son booleanos, devuelven true or false en función de la clase de activo de cada fondo
    is_rv = df['ClaseActivo'] == 'RV'
    # Tratamos RF y Monetario como el mismo grupo para divisa (a la hora de cubrirla en RF)
    is_rf = df['ClaseActivo'].isin(['RF', 'Monetario']) 
    
    # Guardamos una nueva columna (attribute) para el optimizador, que es una flag binaria 
    # que nos indica si es RF o no para el momento de calcular la duración tenerlo en cuenta o no 
    # (no quiero tener en cuenta la RV)
    df['is_RF_Universe'] = is_rf.astype(int)

    # BLINDAJE DE DATOS (Lógica Defensiva)
    #  Tratamiento de Calidad Crediticia:
    # - Si es RV: Ponemos 0 (No aplica, no afecta al promedio).
    # - Si es RF y es Nulo: Ponemos 12 (Peor que D). 
    #   PENALIZACIÓN MÁXIMA a la incertidumbre.
    
    # Rellenamos RV con 0
    df.loc[is_rv, 'RF_Calidad_Num'] = df.loc[is_rv, 'RF_Calidad_Num'].fillna(0.0)
    
    # Rellenamos RF con 12 (Castigo)
    df.loc[is_rf, 'RF_Calidad_Num'] = df.loc[is_rf, 'RF_Calidad_Num'].fillna(12.0)

    # COLUMNAS FRANCOTIRADOR (Para penalizar con precisión)
    
    # Caso A: Renta Variable
    # 1. Es RV y está Cubierto (Para penalizar si ODIO el hedging en bolsa)
    df['is_RV_Hedged'] = (is_rv & is_hedged_global).astype(int)
    # 2. Es RV y NO está Cubierto (Para penalizar si QUIERO hedging en bolsa)
    df['is_RV_Unhedged'] = (is_rv & ~is_hedged_global).astype(int)
    
    # Caso B: Renta Fija
    # 3. Es RF y está Cubierto
    df['is_RF_Hedged'] = (is_rf & is_hedged_global).astype(int)
    # 4. Es RF y NO está Cubierto
    df['is_RF_Unhedged'] = (is_rf & ~is_hedged_global).astype(int)

    
    # LIMPIEZA DE DATOS (CRÍTICO)
    # Los valores NULL en el optimizador no interesan. 
    # Los convertimos a 0.0
    # (Si no tiene dato de Tecnología, asumimos que es 0% Tecnología)
    # Al final del todo haciendo barrido general.
    # En lugar de df.fillna(0.0) global:
    # pero solo queremos poner a 0's las variables numéricas, las que no lo sean no para no llevar a confusiones
    numeric_cols = df.select_dtypes(include=[np.number]).columns
    df[numeric_cols] = df[numeric_cols].fillna(0.0)

    # Para las de texto, rellena con "" o "Desconocido"
    text_cols = df.select_dtypes(include=['object']).columns
    df[text_cols] = df[text_cols].fillna("Desconocido")

    return df

def optimize_portfolio(df, user_targets, 
                       preference_etf=0.0,
                       preference_dist=0.0,
                       preference_hedged_rv=0.0,
                       preference_hedged_rf=0.0):
    """
    Paso 2: El Motor Matemático (CVXPY).
    
    Args:
        df: DataFrame con los fondos.
        user_targets: Diccionario con los objetivos (del usuario) {Columna: ValorDecimal}.
                      Ej: {'Geo_RV_USA': 0.60, 'RF_Duracion': 5.0}
        preference_value: Penalización suave. 
                        0.0 = Indiferente.
                        > 0 Positivo (ej. 0.1) =   Usuario QUIERE esa caraterística, penaliza lo contrario
                        < 0 Negativo (ej. -0.1) = Usuario ODIA esta característica, penaliza el tenerla
    """
    
    # --- A. VARIABLES ---
    n_funds = len(df) # numero de fondos (numero de filas (records))
    # 'w' es el vector de PESOS que buscamos. El ordenador debe rellenar esto.
    w = cp.Variable(n_funds) 
    # tenemos tantos pesos como número de fondos (me reserva memoria para n_funds)
    # el peso que nuestro optimizador va a devolverle con cada fondo, resultando en la cartera final
    
    # --- B. RESTRICCIONES (CONSTRAINTS) ---
    constraints = [
        cp.sum(w) == 1.0,  # 1. La suma de pesos debe ser 100%
        w >= 0             # 2. No permitimos posiciones cortas (pesos negativos) Posiciones positivas = compra
    ]
    
    # --- C. FUNCIÓN OBJETIVO (EL ERROR A MINIMIZAR) ---
    error_total = 0
    
    # Recorremos cada deseo del usuario (Ej: 'Geo_RV_USA': 0.60)
    # col es el attribute (clave) y target_val es el valor dentro del diccionario de los objetivos del usuario
    # diccionario.items() returns clave, valor.
    for col, target_val in user_targets.items():
        if col not in df.columns:
            print(f"⚠️ Aviso: La columna '{col}' no existe en la BBDD. Se ignora.")
            continue
            # continue ignora y sigue.

        # Para cada columna y valores (clave: valor)    
        # Extraemos los datos de esa columna del DataFrame (ej. la columna USA de todos los fondos)
        col_data = df[col].values
        
        # Métricas exclusivas para la RF (Todas empiezan por RF ( RF_Duracion, RF_Calidad_num...))
        if col.startswith('RF_'):
            # Usamos el truco descrito en el word para que el optimizador me deje 
            # aplicar la duracion solo a la RF y no a la RV, manteniendo la convexidad de las funciones
            # en todo momento, garantizando la convexidad del problema
            # recordamos que estas operaciones son unicamente para los elementos de col_data y target_val que estan relacionados con RF
            contribution_sum = w @ col_data  # Numerador (Aportación de duración, duracion total (sin hacer la media))
            weight_sum_rf = w @ df['is_RF_Universe'].values # Denominador (Cuánto pesa la RF)
            # de tal forma que dividiendo esto me da la duracion media de mi cartera (atentiendo solo a la RF)

            # El error es la diferencia entre la Contribución Real y la Contribución Teórica Ideal
            # Si tengo 0% de RF, weight_sum_rf es 0 y el error se anula (correcto).
            term = contribution_sum - (target_val * weight_sum_rf)
            error_total += cp.power(term, 2)

        else:
            # AHORA EL CASO NORMAL (global), aquí si que contamos toda la cartera y no solo la RF

            # CÁLCULO DE LA EXPOSICIÓN REAL DE LA CARTERA
            # Multiplicamos los pesos (w) por los datos de la columna.
            # Ej: (Peso_Fondo1 * USA_Fondo1) + (Peso_Fondo2 * USA_Fondo2)...
            actual_exposure = w @ col_data 
            # en esta linea, lo que esta haciendo no es calcular el resultado, si no escribir una formula gigante en su memoria
            # simplemente creamos la formula, que es lo que vamos a querer comparar con el valor del usuario para minimizar esa diferencia
        
            # SUMAMOS EL ERROR AL CUADRADO
            # (Lo que tenemos - Lo que queremos)^2
            # Usamos cuadrados para penalizar mucho los errores grandes.
            error_total += cp.power(actual_exposure - target_val, 2)

    def get_penalty_term(weights, binary_col_values, preference_val):
        """
        Calcula la penalización matemática basada en el deseo del usuario.
        
        Args:
            weights: Variables de peso (cvxpy).
            binary_col_values: Array de 1s y 0s del DataFrame (ej. is_ETF).
                LO QUE TENEMOS
            preference_val: 
                > 0: Usuario QUIERE esta característica (Penaliza lo contrario).
                < 0: Usuario ODIA esta característica (Penaliza tenerla).
                0: Indiferente.
                LO QUE QUIERE EL USUARIO
        """
        # Preference val puede ser un número cualquiera x < |1| (entre -1 y 1)
        # de tal forma que cuanto mayor sea el valor en valor absoluto, mayor penalización aplicará
        if preference_val > 0:
            # Usuario QUIERE X. El enemigo son los que NO son X (los 0s).
            # Convertimos 0s a 1s haciendo (1 - columna)
            return preference_val * (weights @ (1 - binary_col_values))
            
        elif preference_val < 0:
            # Usuario ODIA X. El enemigo son los que SÍ son X (los 1s).
            # Usamos abs() para que el coste sea positivo matemáticamente.
            return abs(preference_val) * (weights @ binary_col_values)
            
        else:
            return 0

    # Aplicamos la lógica unificada a las 3 variables
    # columna.values retorna un vector con todos los valores de la base de datos binaria
    # preference_etf es un vector del mismo tamaño con todos los valores iguales (si prefiere una cosa negativo, si prefiere otra, positivo)
    penalty_etf = get_penalty_term(w, df['is_ETF'].values, preference_etf)
    penalty_dist = get_penalty_term(w, df['is_Dist'].values, preference_dist)

    # 3. PENALIZACIONES DE DIVISA (Lógica Específica por Clase)
    
    # --- RENTA VARIABLE ---
    penalty_hedged_rv = 0
    # quiero hedged
    if preference_hedged_rv > 0:
        # QUIERO cubrir RV -> Penalizo RV NO Cubierta
        # is_RV_Unhedged es un vector booleano 0's o 1's en un fucnion de si cada fondo es sin cubrir (true) o no
        # en este caso al coger en la penalizacion los fondos que son ungedged, los penalizo 
        # (estoy penalizando los pesos en la fila que se encuentran estos fondos, al hacer el producto escalar)
        penalty_hedged_rv = preference_hedged_rv * (w @ df['is_RV_Unhedged'].values)
        # no quiero hedged
    elif preference_hedged_rv < 0:
        # ODIO cubrir RV -> Penalizo RV SÍ Cubierta
        penalty_hedged_rv = abs(preference_hedged_rv) * (w @ df['is_RV_Hedged'].values)

    # --- RENTA FIJA ---
    penalty_hedged_rf = 0
    if preference_hedged_rf > 0:
        # QUIERO cubrir RF -> Penalizo RF NO Cubierta
        penalty_hedged_rf = preference_hedged_rf * (w @ df['is_RF_Unhedged'].values)
    elif preference_hedged_rf < 0:
        # ODIO cubrir RF -> Penalizo RF SÍ Cubierta
        penalty_hedged_rf = abs(preference_hedged_rf) * (w @ df['is_RF_Hedged'].values)

    # --- E. RESOLVER ---
    # Queremos minimizar (Error de Tracking + Penalización de Preferencia)
    objective = cp.Minimize(error_total + penalty_etf + penalty_dist + penalty_hedged_rf + penalty_hedged_rv)
    prob = cp.Problem(objective, constraints)
    
    # El solver intenta encontrar los valores de 'w'
    # se hace control de error, por si el solver diera cualquier tipo de error, saber que ha sido por el solver.
    try:
        prob.solve()
    except Exception as e:
        print(f"Error resolviendo: {e}")
        return None

    # --- F. RESULTADOS ---
    # Guardamos los pesos calculados en el DataFrame para verlos
    df['Peso_Optimizado'] = w.value
    
    # Filtramos para devolver solo los fondos que ha comprado (peso > 0.001)
    # y devolvemos una copia de ese dataframe para no modificar el original
    cartera_final = df[df['Peso_Optimizado'] > 0.001].copy()
    
    # Ordenamos de mayor a menor peso, para que nos salgan los fondos con mayor peso al principio
    return cartera_final.sort_values(by='Peso_Optimizado', ascending=False)


# --- BLOQUE DE EJECUCIÓN (AUDITORIA) (PARA PROBARLO) ---
if __name__ == "__main__":
    print("🚀 Iniciando Motor FundMix...")
    
    # 1. Cargar Datos
    df_fondos = get_data_from_db()
    print(f"✅ Datos cargados: {len(df_fondos)} fondos disponibles.")
    
    # 2. Definir un Objetivo de Prueba (EL USUARIO)
    # Vamos a pedir una cartera "60/40 Clásica"
    # 60% Bolsa USA, 40% Bonos Globales (con duración 7.5 aprox)
    objetivos_usuario = {
        'Geo_RV_USA': 0.60,      # Quiero 60% en acciones USA
        'Expo_RF': 0.40,         # Quiero 40% en Renta Fija total
        'RF_Duracion': 3.0,     # Quiero una duración media de cartera de 3 años (mezcla corto/largo)
        'EscalaRiesgo' : 4.0,
    }
    
    # Preferencias
    pref_etf = -1.0     # Prefiero Fondo a ETF
    pref_dist = 0.0     # indiferente
    preference_hedged_rv= -1 # No quiero hedged en RV
    preference_hedged_rf = 1 # quiero hedged en RF

    print(f"\n🎯 Objetivos del usuario: {objetivos_usuario}")
    
    # 3. Optimizar
    resultado = optimize_portfolio(df_fondos, 
                                   objetivos_usuario, 
                                   preference_dist=pref_dist, 
                                   preference_etf=pref_etf, 
                                   preference_hedged_rv=preference_hedged_rv,
                                   preference_hedged_rf=preference_hedged_rf)
    
    # 4. Mostrar Resultado de forma Dinámica

    # verifica si el optimizador tuvo éxito. A veces cuando pides algo imposible
    # el optimizador falla y devuelve None, evitamos que el programa explote por imprimir resultados de un None
    if resultado is not None:
        print("\n✨ CARTERA RECOMENDADA ✨")
        
        # A. CONSTRUCCIÓN DINÁMICA DE COLUMNAS
        # Columnas fijas (Identidad)
        cols_basicas = ['Nombre', 'Ticker', 'TipoProducto', 'Peso_Optimizado']
        # Columnas dinámicas (Lo que pidió el usuario) + Variables de preferencia usadas
        # Solo intentamos mostrar las columnas que REALMENTE existen en el resultado
        cols_objetivos = [col for col in objetivos_usuario.keys() if col in resultado.columns]

        cols_preferencias = ['EscalaRiesgo','PoliticaDiv','EsHedged'] # Añadimos esta porque usamos pref_hedged
        
        # Juntamos todo
        # Filtro estético para no duplicar columnas (si EscalaRiesgo está en objetivos y preferencias, solo sale una vez)
        cols_to_show = cols_basicas + \
                       [c for c in cols_preferencias if c not in cols_basicas] + \
                       [c for c in cols_objetivos if c not in cols_basicas and c not in cols_preferencias]
        
        # Imprimimos tabla filtada (solo con las columnas que queremos y no las de todo el data frame)
        # .to_string(index=false): esto es un truco estético: si haces print(df) normal, 
        # Pandas imprime los numeros de fila (0,1,2...) a la izquierda de cada fila de la tabla (queda feo)
        # si lo pasamos a string así, imprime la tabla limpia como un reporte profesional
        print(resultado[cols_to_show].to_string(index=False))
        
        # B. AUDITORÍA DINÁMICA (Bucle)
        print(f"\n📊 Auditoría de Objetivos:")

        # sacamos el vector columna de pesos para tenerlos en un vector y poder hacer operaciones matermaticas con ellos
        peso = resultado['Peso_Optimizado'].values

        # Calculamos cuánto pesa la Renta Fija en total para poder "des-diluir" sus métricas
        peso_total_rf = np.dot(peso, resultado['is_RF_Universe'].values)
        print(f"   ℹ️ Peso total Renta Fija: {peso_total_rf:.2%}")
        
        for metrica, valor_objetivo in objetivos_usuario.items():
            # Verificamos que la métrica exista en el resultado para no fallar
            if metrica in resultado.columns:
                # Producto escalar: Pesos * Valores de esa columna
                # calculamos la media ponderada. Se calcula una media por cada métrica a comprobar.
                # ejemplo: para la metrica RV_USA coge y hace sumatorio de todos los fondos (los pesos de cada fondo * RV_USA de cada fondo)
                # y así para cada métrica
                raw_contribution = np.dot(peso, resultado[metrica].values)

                # Volvemos a diferenciar para la hora de mostrar resultados la RF del resto (RV) para la hora de la duración
                if metrica.startswith('RF_'):
                    # Si es métrica de RF, dividimos por el peso de la RF (Renormalizar)
                    # vamos a hacer este if para evitarnos problemas por si la persona quiere 100% RV (i.e 0% RF),
                    # NO SE DIVIDA POR 0, Entonces si la cantidad de RF<0.5%, entonces no intentes calcular su duracion, es 0 directamente (else)
                    if peso_total_rf > 0.01: 
                        valor_real = raw_contribution / peso_total_rf
                    else:
                        # la parte de renta fija es 0
                        valor_real = 0.0
                else:
                    # si es global, el valor es directo
                    # para las demas variables ( que no empiezan por RF_), entonces directamente es ese valor
                    valor_real = raw_contribution

                # --- VOLVEMOS A TRADUCIR LA CALIDAD CREDITICIA AL LENGUAJE ORIGINAL (Número -> Letra) ---
                # PARA EXPONERSELO AL USUARIO. DESHACEMOS EL ENCODING TRAS OPTIMIZAR
                mensaje_extra = ""
                
                if metrica == 'RF_Calidad_Num':
                    # Lógica inversa: Convertimos el 3.5 de vuelta a "A/BBB"
                    if valor_real <= 1.5: cal_txt = "AAA (Excelente)"
                    elif valor_real <= 2.5: cal_txt = "AA (Muy Buena)"
                    elif valor_real <= 3.5: cal_txt = "A (Buena)"
                    elif valor_real <= 4.5: cal_txt = "BBB (Inversión)"
                    elif valor_real <= 5.5: cal_txt = "BB (High Yield)"
                    elif valor_real <= 6.5: cal_txt = "B (Speculative)"
                    elif valor_real <= 10.0: cal_txt = "C/D (Riesgo Alto)"
                    else: cal_txt = "⚠️ DATOS INSUFICIENTES (Penalizado) Por favor, contacte con soporte para poder rellenar el dato faltante o eliminar dicho fondo"
                    
                    mensaje_extra = f"  👉 Equivale a: {cal_txt}"


                # calcula lo que nos equivocamos
                diff = valor_real - valor_objetivo
                
                # Mostramos resultado (todo trasparente para que el usuario juzgue la calidad de la solución)
                print(f"   - {metrica}: {valor_real:.2f} (Meta: {valor_objetivo}) | Desv: {diff:.2f}{mensaje_extra}")
            else:
                print(f"   ⚠️ No se pudo auditar {metrica} (Columna no encontrada)")
        
    else:
        print("❌ No se encontró solución óptima.")