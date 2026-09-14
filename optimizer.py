import sqlite3
import pandas as pd
import cvxpy as cp
import numpy as np

# Configuración
DB_FILE = 'FundMix.db'

# === JERARQUÍA DE ESTRATEGIAS (categoría padre -> familia) ===
# 'Alternativo' actúa como categoría padre: excluirlo o ponerle una banda de estilo
# afecta también a sus subestrategias. La familia se incluye a sí misma porque
# 'Alternativo' es además un valor válido de la columna Estrategia.
# Sin esto, excluir "Alternativo" desde la interfaz NO eliminaba los fondos cuya
# Estrategia es 'Market Neutral' / 'Event Driven' / 'Multiestrategia' (tienen
# 'Alternativo' en ClaseActivo, que es otra columna).
FAMILIAS_ESTRATEGIA = {
    'Alternativo': ['Alternativo', 'Event Driven', 'Market Neutral', 'Multiestrategia'],
}


def expandir_familias_estrategia(seleccion):
    """Convierte categorías padre en su familia completa, conservando el orden y sin duplicar."""
    expandida = []
    for estrategia in seleccion or []:
        expandida.extend(FAMILIAS_ESTRATEGIA.get(estrategia, [estrategia]))
    return list(dict.fromkeys(expandida))

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
    # Escala ordinal inversa 1 (AAA, mejor) -> 10 (D, peor). El optimizador MINIMIZA
    # este número, así que minimizar = buscar mejor calidad.
    # Los sufijos +/- son imprescindibles: las agencias los usan y las fichas técnicas
    # los publican tal cual ('A-', 'BBB+'). Sin ellos quedaban sin mapear (NaN) y el
    # Data Shielding los castigaba con un 12 como si fueran bonos sin rating, haciendo
    # que el motor huyera de fondos excelentes. Se interpolan a un tercio de escalón,
    # que es la convención estándar al numerizar ratings.
    quality_map = {
        'AAA': 1.0,
        'AA+': 1.7, 'AA': 2.0, 'AA-': 2.3,
        'A+': 2.7,  'A': 3.0,  'A-': 3.3,
        'BBB+': 3.7, 'BBB': 4.0, 'BBB-': 4.3,
        'BB+': 4.7,  'BB': 5.0,  'BB-': 5.3,
        'B+': 5.7,   'B': 6.0,   'B-': 6.3,
        'CCC+': 6.7, 'CCC': 7.0, 'CCC-': 7.3,
        'CC': 8.0, 'C': 9.0, 'D': 10.0
    }
    
    # Aplicamos el mapa. 
    # Los que no sean bonos (ej. Acciones) tendrán nulos, los rellenamos con 0 o un valor neutro, previamente en el .filna(0)

    def _map_calidad(valor):
        """Acepta rating textual ('BBB+') o el valor YA numérico en la escala 1-12.

        Cuando la ficha de un fondo no publica un rating medio único —típico en mixtos y
        en fondos flexibles— el gestor puede calcular a mano la media ponderada de su
        cartera de bonos y anotarla directamente codificada (contando los 'sin rating'
        como 12, igual que hace el Data Shielding). En ese caso se usa tal cual: pasarla
        por quality_map devolvería NaN y el blindaje la castigaría con un 12 como si no
        hubiera dato, destruyendo un cálculo que sí es real.
        """
        texto = str(valor).strip()
        if not texto:
            return np.nan
        try:
            return float(texto)                    # ya viene en la escala 1-12
        except ValueError:
            return quality_map.get(texto, np.nan)  # rating textual: 'AAA', 'BBB+'...

    df['RF_Calidad_Num'] = df['RF_Calidad'].map(_map_calidad)

    
    # Convertimos TipoProducto a binario (para usarlo luego en penalizaciones)
    # 1 si es ETF, 0 si es Fondo
    df['is_ETF'] = (df['TipoProducto'] == 'ETF').astype(int)

    # Distribución (1) vs Acumulación (0)
    # Si el usuario odia los dividendos, penalizaremos los que tengan is_Dist = 1
    df['is_Dist'] = (df['PoliticaDiv'] == 'Dist').astype(int)

    # === Gestion Activa (1) vs Pasiva (2)
    df['is_Activa'] = (df['EstiloGestion'] == 'Activa').astype(int)
    # =========================================================================

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

    # === NUEVO V5: MÁSCARA CONTINUA DEL UNIVERSO SENSIBLE A TIPOS ===
    # is_RF_Universe es BINARIA y se deriva de ClaseActivo, así que un fondo Mixto con
    # un 80% de bonos vale 0 en ella. En el término de duración eso hace que el mixto
    # aporte al numerador pero NO al denominador, inflando la duración media.
    # Expo_Tipos es la versión continua: ese mixto pesa 0.8, que es lo correcto.
    # Se incluye Expo_Monet porque un monetario tiene duración ~0 pero SÍ pertenece al
    # universo de tipos; excluirlo distorsionaría la duración media al alza (medido:
    # 4.348 con is_RF_Universe, 4.258 solo con Expo_RF, 3.760 con la suma correcta).
    df['Expo_Tipos'] = df['Expo_RF'].fillna(0) + df['Expo_Monet'].fillna(0)
    # ================================================================

    # === BANDERA DE FONDOS ALTERNATIVOS (solo informativa) ===
    # Igualdad estricta: marca los fondos PURAMENTE alternativos. Se conserva únicamente
    # para la auditoría; el techo de alternativos ya NO la usa, porque un mixto con un 20%
    # de alternativos valía 0 aquí y escapaba a una restricción dura de Nivel 1.
    df['is_Alt'] = (df['Expo_Alt'].fillna(0) == 1).astype(int)
    # ==============================================

    # BLINDAJE DE DATOS (Lógica Defensiva)
    #  Tratamiento de Calidad Crediticia:
    # - Con bonos reales y sin dato: 12 (Peor que D=10) -> PENALIZACIÓN MÁXIMA.
    # - Sin bonos relevantes: 0 (No aplica, no afecta al promedio).
    #
    # La decisión NO puede depender de la etiqueta ClaseActivo: un fondo 'Mixto' con un
    # 90% de bonos no entraba en is_rv NI en is_rf, así que caía al fillna(0.0) global de
    # más abajo y acababa valiendo 0 = MEJOR QUE AAA. Es justo el bug que este blindaje
    # existe para evitar. Por eso se decide por EXPOSICIÓN REAL.
    #
    # El criterio es Expo_Tipos (bonos + monetario), la MISMA máscara que usa el motor
    # como denominador. Tiene que ser la misma: si un fondo pesa en el denominador de la
    # calidad media, su valor debe estar blindado. Los monetarios invierten en papel
    # comercial y depósitos, así que sí tienen riesgo de crédito y sí deben blindarse.
    # El umbral del 5% evita castigar a un fondo de bolsa por una tesorería residual.
    tiene_bonos = df['Expo_Tipos'] > 0.05
    sin_dato = df['RF_Calidad_Num'].isna()

    df.loc[tiene_bonos & sin_dato, 'RF_Calidad_Num'] = 12.0
    df.loc[~tiene_bonos & sin_dato, 'RF_Calidad_Num'] = 0.0

    # COLUMNAS FRANCOTIRADOR (Para penalizar con precisión)
    #
    # 'EsHedged' y 'EstiloGestion' son propiedades BINARIAS a nivel de ISIN: un fondo está
    # cubierto o no lo está, es activo o es pasivo. Lo que hay que hacer continuo no es la
    # bandera, sino CUÁNTA exposición de cada clase aporta ese fondo:
    #
    #     aportación = bandera_binaria (0/1)  ×  exposición_continua (0..1)
    #
    # Antes se hacía 'is_rv & is_hedged', y como is_rv se derivaba de ClaseActivo, un
    # fondo Mixto cubierto NO disparaba ninguna de las cuatro banderas: las preferencias
    # de divisa lo ignoraban por completo. Ahora un mixto cubierto 20/80 aporta 0.20 a
    # "bolsa cubierta" y 0.80 a "bonos cubiertos", que es lo correcto.
    es_hedged = is_hedged_global.astype(int)
    expo_rv = df['Expo_RV'].fillna(0)

    # Caso A: Renta Variable
    df['expo_RV_Hedged'] = es_hedged * expo_rv
    df['expo_RV_Unhedged'] = (1 - es_hedged) * expo_rv

    # Caso B: Renta Fija (usa Expo_Tipos: bonos + monetario, igual que el resto del motor)
    df['expo_RF_Hedged'] = es_hedged * df['Expo_Tipos']
    df['expo_RF_Unhedged'] = (1 - es_hedged) * df['Expo_Tipos']

    # Caso C: Estilo de gestión descompuesto por clase de activo.
    # Un fondo de autor gestiona activamente AMBAS patas, así que su etiqueta 'Activa' se
    # reparte proporcionalmente: el 6.7% de bolsa de un mixto es bolsa gestionada
    # activamente, y su 92% de bonos también. Esto permite pedir "bolsa pasiva + bonos
    # activos" sin que un mixto genere un choque de restricciones.
    df['expo_RV_Activa'] = df['is_Activa'] * expo_rv
    df['expo_RV_Pasiva'] = (1 - df['is_Activa']) * expo_rv
    df['expo_RF_Activa'] = df['is_Activa'] * df['Expo_Tipos']
    df['expo_RF_Pasiva'] = (1 - df['is_Activa']) * df['Expo_Tipos']

    # === NUEVO V2: AGRUPACIÓN DE EMERGENTES PARA FACILITAR LOS OBJETIVOS DEL USUARIO ===
    cols_emergentes = ['Geo_RV_China', 'Geo_RV_India', 'Geo_RV_Taiwan', 'Geo_RV_Korea', 'Geo_RV_Brasil', 'Geo_RV_Emergentes_Otros']
    # Sumamos las subcolumnas pero tratando los posibles Nulos como 0 para no romper cálculos
    df['Geo_RV_Emergentes_Total'] = df[cols_emergentes].fillna(0).sum(axis=1)
    # ====================================================================================

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
                       preference_hedged_rf=0.0,
                       # === NUEVO V2: PARÁMETROS PARA ESTRATEGIAS Y LÍMITE DE ACTIVA ===
                       exclude_strategies=None,
                       max_activa=None,
                       # === NUEVO V3: BANDAS DE ESTILO ===
                       estrategias_bandas=None,
                       # === NUEVO V4: LÍMITE DURO DE FONDOS ALTERNATIVOS ===
                       max_alt_weight=0.15,
                       # === NUEVO V5: JERARQUÍA PADRE-HIJO EN ESTRATEGIAS ===
                       expandir_familias=True,
                       # === NUEVO V5: SESGO DE GESTIÓN POR CLASE DE ACTIVO ===
                       preference_activa_rv=0.0,
                       preference_activa_rf=0.0):
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
        expandir_familias: Si es True (por defecto), las categorías padre de
                        FAMILIAS_ESTRATEGIA se expanden a toda su familia, tanto al excluir
                        como al aplicar bandas de estilo. Ponerlo a False hace que las listas
                        se tomen literalmente; lo usa la interfaz cuando el usuario ha afinado
                        a mano qué subestrategias concretas quiere excluir y ya ha resuelto la
                        selección a nivel de hoja (si no, la expansión desharía ese afinado).
    """
    
    # === NUEVO V2: PRE-PROCESSING (FILTRO POR ESTRATEGIAS ANTES DE OPTIMIZAR) ===
    if exclude_strategies:
        # 'Alternativo' es categoría padre: al excluirlo caen también sus subestrategias.
        prohibidas = (expandir_familias_estrategia(exclude_strategies)
                      if expandir_familias else list(exclude_strategies))
        # Borramos los fondos que pertenezcan a las estrategias prohibidas
        df = df[~df['Estrategia'].isin(prohibidas)].copy()
        df.reset_index(drop=True, inplace=True) # Reset de índice vital para CVXPY
    # ============================================================================

    # --- A. VARIABLES ---
    n_funds = len(df) # numero de fondos (numero de filas (records))

    # === NUEVO V2: CONTROL DE SEGURIDAD POR SI EL FILTRO ELIMINA TODOS LOS FONDOS ===
    if n_funds == 0:
        print("Tras aplicar los filtros, no quedan fondos en el universo.")
        return None
    # ==============================================================================

    # 'w' es el vector de PESOS que buscamos. El ordenador debe rellenar esto.
    w = cp.Variable(n_funds) 
    # tenemos tantos pesos como número de fondos (me reserva memoria para n_funds)
    # el peso que nuestro optimizador va a devolverle con cada fondo, resultando en la cartera final
    
    # --- B. RESTRICCIONES (CONSTRAINTS) ---
    constraints = [
        cp.sum(w) == 1.0,  # 1. La suma de pesos debe ser 100%
        w >= 0             # 2. No permitimos posiciones cortas (pesos negativos) Posiciones positivas = compra
    ]
    
    # =========================================================================
    # NIVEL 1: RESTRICCIONES DURAS (HARD CONSTRAINTS) - INNEGOCIABLES
    # =========================================================================
    # LÓGICA DE TOLERANCIA CERO: Si pide 0%, prohibimos matemáticamente tener exposición.
    for col, target_val in user_targets.items():
        # Excluimos la Renta Fija de esta restricción dura directa por cómo calculamos su media después
        if target_val == 0.0 and col in df.columns and not col.startswith('RF_'):
            constraints.append(w @ df[col].values == 0)

    # === NUEVO V4: LÍMITE DURO DE EXPOSICIÓN A ALTERNATIVOS ===
    # La suma de pesos de los fondos con Expo_Alt=1 no puede superar max_alt_weight.
    # 'w @ is_Alt' es una expresión AFÍN (var * constantes 0/1); 'afín <= constante'
    # es una restricción convexa válida en DCP. No se divide por 'w'.
    if max_alt_weight is not None:
        # Se usa Expo_Alt (continua) y NO is_Alt (binaria, igualdad estricta a 1): un fondo
        # mixto con un 20% de alternativos valía 0 en la bandera y escapaba a este techo,
        # que es una restricción DURA. Ahora consume exactamente su 20%.
        constraints.append(w @ df['Expo_Alt'].fillna(0).values <= max_alt_weight)
    # ==========================================================

    # --- C. FUNCIÓN OBJETIVO (EL ERROR A MINIMIZAR) ---
    error_total = 0
    
    # =========================================================================
    # NIVEL 2: PRIORIDAD MÁXIMA (Multiplicador x100) - Geografía y Asset Allocation
    # =========================================================================
    factor_nivel_2 = 100.0

    # Recorremos cada deseo del usuario (Ej: 'Geo_RV_USA': 0.60)
    # col es el attribute (clave) y target_val es el valor dentro del diccionario de los objetivos del usuario
    # diccionario.items() returns clave, valor.
    for col, target_val in user_targets.items():
        if col not in df.columns:
            print(f"Aviso: La columna '{col}' no existe en la BBDD. Se ignora.")
            continue
            # continue ignora y sigue.

        # Saltamos los 0% de RV porque ya están blindados como Hard Constraint en el Nivel 1
        if target_val == 0.0 and not col.startswith('RF_'):
            continue

        # Pasamos la Escala de Riesgo a modo "Solo Informativo" (El motor no la optimiza)
        if col == 'EscalaRiesgo':
            continue

        # Para cada columna y valores (clave: valor)    
        # Extraemos los datos de esa columna del DataFrame (ej. la columna USA de todos los fondos)
        col_data = df[col].values
        
        # === MÉTRICAS RELATIVAS A UNA CLASE DE ACTIVO (no al total de la cartera) ===
        # Las tres ramas siguientes comparten la misma linealización: como no se puede
        # dividir por una expresión que contiene 'w' sin romper la convexidad (DCP),
        # se quita el denominador multiplicando en cruz:
        #     Sum(w * valor) - (Target * Sum(w * mascara)) = 0
        # 'term' es una resta de dos expresiones afines en w, luego afín; su cuadrado es
        # convexo. Si la clase no está presente, la máscara vale 0 y el error se anula.
        mascara = None

        if col.startswith('RF_'):
            # Métricas exclusivas de la sub-cartera de tipos: duración, calidad, yield...
            # Máscara CONTINUA (ver Expo_Tipos): antes era is_RF_Universe, binaria,
            # que dejaba fuera a los mixtos y falseaba la media.
            mascara = df['Expo_Tipos'].values

        elif col.startswith('Geo_RV_') or col.startswith('Sec_'):
            # Geografía Y SECTORES son fracción de la parte de RENTA VARIABLE.
            # ("60% USA" = el 60% de mi bolsa está en EE.UU.; "30% Tecnología" = el 30%
            # de mi bolsa es tecnológica). Un mixto 10/90 con toda su bolsa en tech
            # aporta 0.10 de tecnología a la cartera, no 1.00.
            mascara = df['Expo_RV'].fillna(0).values

        elif col.startswith('Geo_RF_'):
            # Idem para la renta fija: el % SOBRE la parte de tipos.
            mascara = df['Expo_Tipos'].values

        if mascara is not None:
            # El dato del CSV es RELATIVO a su clase (Geo_RV_USA=1.0 significa "toda mi
            # bolsa en USA", no "todo el fondo en USA"). Para sumarlo entre fondos hay que
            # llevarlo antes a contribución ABSOLUTA multiplicando por la máscara:
            #   mixto 10% bolsa toda en USA -> 0.10 * 1.0 = 0.10 del fondo
            # Sin esta ponderación el cociente daría 10.0 en vez de 1.0.
            # 'mascara * col_data' es producto de dos vectores CONSTANTES: la expresión
            # sigue siendo afín en w y la convexidad queda intacta.
            contribution_sum = w @ (mascara * col_data)
            denominador = w @ mascara
            term = contribution_sum - (target_val * denominador)
            error_total += factor_nivel_2 * cp.power(term, 2)

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
            error_total += factor_nivel_2 * cp.power(actual_exposure - target_val, 2)

    # =========================================================================
    # NIVEL 3: PRIORIDAD BLANDA (Multiplicador x1) - Preferencias y Bandas
    # =========================================================================
    factor_nivel_3 = 1.0

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
        # expo_RV_Unhedged es un vector CONTINUO (0..1): cuánta bolsa sin cubrir aporta
        # cada fondo. Al hacer el producto escalar penalizamos el peso de esos fondos
        # en proporción exacta a la bolsa sin cubrir que realmente llevan dentro.
        penalty_hedged_rv = preference_hedged_rv * (w @ df['expo_RV_Unhedged'].values)
        # no quiero hedged
    elif preference_hedged_rv < 0:
        # ODIO cubrir RV -> Penalizo RV SÍ Cubierta
        penalty_hedged_rv = abs(preference_hedged_rv) * (w @ df['expo_RV_Hedged'].values)

    # --- RENTA FIJA ---
    penalty_hedged_rf = 0
    if preference_hedged_rf > 0:
        # QUIERO cubrir RF -> Penalizo RF NO Cubierta
        penalty_hedged_rf = preference_hedged_rf * (w @ df['expo_RF_Unhedged'].values)
    elif preference_hedged_rf < 0:
        # ODIO cubrir RF -> Penalizo RF SÍ Cubierta
        penalty_hedged_rf = abs(preference_hedged_rf) * (w @ df['expo_RF_Hedged'].values)

    # === NUEVO V5: SESGO DE GESTIÓN POR CLASE DE ACTIVO (Nivel 3) ===
    # Mismo patrón bidireccional que el hedging: positivo = "lo quiero" (penalizo lo
    # contrario), negativo = "lo evito" (penalizo tenerlo), cero = indiferente.
    # Permite el modelo Core-Satellite real: indexados en bolsa (mercado eficiente) y
    # gestión activa en bonos (mercado OTC ineficiente), sin que un fondo mixto genere
    # un choque: sus dos patas se contabilizan por separado y en su justa proporción.
    penalty_activa_rv = 0
    if preference_activa_rv > 0:      # QUIERO bolsa activa -> penalizo la bolsa pasiva
        penalty_activa_rv = preference_activa_rv * (w @ df['expo_RV_Pasiva'].values)
    elif preference_activa_rv < 0:    # QUIERO bolsa pasiva -> penalizo la bolsa activa
        penalty_activa_rv = abs(preference_activa_rv) * (w @ df['expo_RV_Activa'].values)

    penalty_activa_rf = 0
    if preference_activa_rf > 0:      # QUIERO bonos activos -> penalizo los bonos pasivos
        penalty_activa_rf = preference_activa_rf * (w @ df['expo_RF_Pasiva'].values)
    elif preference_activa_rf < 0:    # QUIERO bonos pasivos -> penalizo los bonos activos
        penalty_activa_rf = abs(preference_activa_rf) * (w @ df['expo_RF_Activa'].values)

    # === NUEVO V2: RESTRICCIÓN SUAVE (SOFT CONSTRAINT) PARA LÍMITE DE GESTIÓN ACTIVA ===
    penalty_activa = 0
    if max_activa is not None:
        # Exposición EFECTIVA a gestión activa, no peso de fondos etiquetados 'Activa'.
        # Antes, meter un 15% de un mixto activo con solo un 6.7% de bolsa consumía los 15
        # puntos enteros del límite. Ahora consume lo que realmente gestiona activamente.
        expo_activa_total = df['expo_RV_Activa'].values + df['expo_RF_Activa'].values
        # cp.pos() devuelve 0 si no nos pasamos de max_activa, y el exceso si nos pasamos.
        exceso_activa = cp.pos((w @ expo_activa_total) - max_activa)
        # Multiplicamos por 10.0 (un factor de penalización) y lo elevamos al cuadrado.
        # Es lo suficientemente alto para frenarlo, pero permite pasarse un poco si mejora enormemente la cartera.
        penalty_activa = 10.0 * cp.power(exceso_activa, 2)
    # ===================================================================================

    # === NUEVO V3: LÓGICA DE BANDAS DE ESTILO (HINGE LOSS) ===
    penalty_bandas = 0
    if estrategias_bandas:
        for strat, (min_val, max_val) in estrategias_bandas.items():
            if min_val == 0.0 and max_val == 1.0:
                continue # Si no hay preferencia, ignoramos para ahorrar cálculo
                
            # Identificamos qué fondos tienen esta estrategia.
            # Si es una categoría padre ('Alternativo'), la banda cubre toda su familia.
            familia = (FAMILIAS_ESTRATEGIA.get(strat, [strat])
                       if expandir_familias else [strat])
            is_strat = df['Estrategia'].isin(familia).astype(int).values
            peso_strat = w @ is_strat
            
            # Penalización "Suelo y Techo": Solo hay castigo si sale del rango [min, max]
            penal_suelo = cp.pos(min_val - peso_strat)
            penal_techo = cp.pos(peso_strat - max_val)
            penalty_bandas += (cp.power(penal_suelo, 2) + cp.power(penal_techo, 2))
    # ===================================================================================

    # --- E. RESOLVER ---
    # Agrupamos todas las penalizaciones suaves multiplicadas por el factor Nivel 3
    penalizaciones_suaves = factor_nivel_3 * (penalty_etf + penalty_dist + penalty_hedged_rf + penalty_hedged_rv
                                              + penalty_activa + penalty_bandas
                                              + penalty_activa_rv + penalty_activa_rf)
    
    # Queremos minimizar (Error de Tracking Nivel 2 + Penalizaciones de Preferencia Nivel 3)
    objective = cp.Minimize(error_total + penalizaciones_suaves)
    prob = cp.Problem(objective, constraints)
    
    # El solver intenta encontrar los valores de 'w'
    # se hace control de error, por si el solver diera cualquier tipo de error, saber que ha sido por el solver.
    try:
        # Usamos ECOS en lugar de default porque es mucho más estable matemáticamente para las funciones Hinge Loss (cp.pos)
        prob.solve() 
    except Exception as e:
        print(f"Error resolviendo: {e}")
        return None

    # --- F. RESULTADOS ---
    # Guardamos los pesos calculados en el DataFrame para verlos
    df['Peso_Optimizado'] = w.value
    
    # Limpiamos ruido matemático (ej: 0.000000001% lo ponemos a 0)
    df['Peso_Optimizado'] = df['Peso_Optimizado'].apply(lambda x: 0 if x < 0.001 else x)
    
    # Filtramos para devolver solo los fondos que ha comprado (peso > 0)
    # y devolvemos una copia de ese dataframe para no modificar el original
    cartera_final = df[df['Peso_Optimizado'] > 0].copy()
    
    # Ordenamos de mayor a menor peso, para que nos salgan los fondos con mayor peso al principio
    return cartera_final.sort_values(by='Peso_Optimizado', ascending=False)


# --- BLOQUE DE EJECUCIÓN (AUDITORIA) (PARA PROBARLO) ---
if __name__ == "__main__":
    print("Iniciando Motor FundMix v2...")
    
    # 1. Cargar Datos
    df_fondos = get_data_from_db()
    print(f"Datos cargados: {len(df_fondos)} fondos disponibles.")
    
    # 2. Definir un Objetivo de Prueba (EL USUARIO)
    # Vamos a pedir una cartera "60/40 Clásica"
    # 60% Bolsa USA, 40% Bonos Globales (con duración 7.5 aprox)
    objetivos_usuario = {
        'Geo_RV_USA': 0.60,      # Quiero 60% en acciones USA
        
        # === NUEVO V2: PODEMOS USAR LA MACRO-VARIABLE QUE HEMOS CREADO ===
        'Geo_RV_Emergentes_Total': 0.10, # Usando la suma de China, India, etc.
        # =================================================================
        'Geo_RV_Japon':0.1,
        'Expo_RF': 0.20,         # Quiero 30% en Renta Fija total
        'RF_Duracion': 3.0,     # Quiero una duración media de cartera de 3 años (mezcla corto/largo)
        'EscalaRiesgo' : 4.0,
    }
    
    # Preferencias
    pref_etf = -1.0     # Prefiero Fondo a ETF
    pref_dist = 0.0     # indiferente
    preference_hedged_rv= -1 # No quiero hedged en RV
    preference_hedged_rf = 1 # quiero hedged en RF

    # === NUEVO V2: DEFINIMOS LOS LÍMITES DE ACTIVA Y ESTRATEGIAS EXCLUIDAS ===
    estrategias_prohibidas = ['Alternativo', 'Inmobiliario'] # Ej: No quiero estas estrategias
    limite_activa_suave = 0.20 # Máximo 20% en fondos de EstiloGestion='Activa'
    # =========================================================================

    print(f"\n Objetivos del usuario: {objetivos_usuario}")
    print(f" Estrategias excluidas: {estrategias_prohibidas}")
    print(f" Límite Gestión Activa (Suave): {limite_activa_suave * 100}%")
    
    # 3. Optimizar
    # === NUEVO V2: PASAMOS LAS VARIABLES EXTRA AL OPTIMIZADOR ===
    resultado = optimize_portfolio(df_fondos, 
                                   objetivos_usuario, 
                                   preference_dist=pref_dist, 
                                   preference_etf=pref_etf, 
                                   preference_hedged_rv=preference_hedged_rv,
                                   preference_hedged_rf=preference_hedged_rf,
                                   exclude_strategies=estrategias_prohibidas,
                                   max_activa=limite_activa_suave,
                                   estrategias_bandas=None) # Añadido
    # ============================================================
    
    # 4. Mostrar Resultado de forma Dinámica

    # verifica si el optimizador tuvo éxito. A veces cuando pides algo imposible
    # el optimizador falla y devuelve None, evitamos que el programa explote por imprimir resultados de un None
    if resultado is not None:
        print("\n CARTERA RECOMENDADA ")
        
        # A. CONSTRUCCIÓN DINÁMICA DE COLUMNAS
        # Columnas fijas (Identidad)
        # === NUEVO V2: AÑADIMOS LAS COLUMNAS DE ESTRATEGIA A LA VISTA ===
        cols_basicas = ['Nombre', 'Ticker', 'TipoProducto', 'EstiloGestion', 'Estrategia', 'Peso_Optimizado']
        # ================================================================

        # Columnas dinámicas (Lo que pidió el usuario) + Variables de preferencia usadas
        # Solo intentamos mostrar las columnas que REALMENTE existen en el resultado
        cols_objetivos = [col for col in objetivos_usuario.keys() if col in resultado.columns]

        cols_preferencias = ['EscalaRiesgo','PoliticaDiv','EsHedged'] # Añadimos esta porque usamos pref_hedged
        
        # === NUEVO V2: CREAMOS LA LISTA DE RATIOS FINANCIEROS INFORMATIVOS ===
        cols_informativas = ['Ret_3Y_Ann', 'Sharpe_3Y', 'Volatilidad_3Y']
        # =====================================================================

        # Juntamos todo
        # Filtro estético para no duplicar columnas (si EscalaRiesgo está en objetivos y preferencias, solo sale una vez)
        cols_to_show = cols_basicas + \
                       [c for c in cols_preferencias if c not in cols_basicas] + \
                       [c for c in cols_objetivos if c not in cols_basicas and c not in cols_preferencias] + \
                       [c for c in cols_informativas if c in resultado.columns] # Añadimos ratios al final
        
        # Imprimimos tabla filtada (solo con las columnas que queremos y no las de todo el data frame)
        # .to_string(index=false): esto es un truco estético: si haces print(df) normal, 
        # Pandas imprime los numeros de fila (0,1,2...) a la izquierda de cada fila de la tabla (queda feo)
        # si lo pasamos a string así, imprime la tabla limpia como un reporte profesional
        print(resultado[cols_to_show].to_string(index=False))
        
        # B. AUDITORÍA DINÁMICA (Bucle)
        print(f"\n Auditoría de Objetivos:")

        # sacamos el vector columna de pesos para tenerlos en un vector y poder hacer operaciones matermaticas con ellos
        peso = resultado['Peso_Optimizado'].values

        # Calculamos cuánto pesa cada clase para poder "des-diluir" sus métricas.
        # Usamos las máscaras CONTINUAS (Expo_Tipos / Expo_RV), las mismas que el motor,
        # para que la auditoría informe exactamente sobre la base en la que se optimizó.
        peso_total_rf = np.dot(peso, resultado['Expo_Tipos'].values)
        peso_total_rv = np.dot(peso, resultado['Expo_RV'].fillna(0).values)
        print(f"    Peso total Renta Fija (incl. monetarios): {peso_total_rf:.2%}")
        print(f"    Peso total Renta Variable: {peso_total_rv:.2%}")

        # === NUEVO V2: IMPRIMIMOS EL PESO TOTAL DE LA GESTIÓN ACTIVA PARA AUDITORÍA ===
        peso_total_activa = np.dot(peso, resultado['is_Activa'].values)
        print(f"    Peso total Gestión Activa: {peso_total_activa:.2%} (Límite solicitado: {limite_activa_suave:.2%})")
        # ==============================================================================
        
        for metrica, valor_objetivo in objetivos_usuario.items():
            # Verificamos que la métrica exista en el resultado para no fallar
            if metrica in resultado.columns:
                # Producto escalar: Pesos * Valores de esa columna
                # calculamos la media ponderada. Se calcula una media por cada métrica a comprobar.
                # ejemplo: para la metrica RV_USA coge y hace sumatorio de todos los fondos (los pesos de cada fondo * RV_USA de cada fondo)
                # y así para cada métrica
                # Renormalizamos con la MISMA base y la MISMA ponderación que usó el motor.
                # Si no, el informe contradiría lo que se optimizó.
                # La guarda >0.01 evita dividir por 0 cuando la clase no está en la cartera.
                if metrica.startswith('RF_') or metrica.startswith('Geo_RF_'):
                    # Métricas y geografía de la parte sensible a tipos
                    raw_contribution = np.dot(peso, resultado['Expo_Tipos'].values * resultado[metrica].values)
                    valor_real = raw_contribution / peso_total_rf if peso_total_rf > 0.01 else 0.0
                elif metrica.startswith('Geo_RV_') or metrica.startswith('Sec_'):
                    # Geografía y sectores de la parte de renta variable
                    raw_contribution = np.dot(peso, resultado['Expo_RV'].fillna(0).values * resultado[metrica].values)
                    valor_real = raw_contribution / peso_total_rv if peso_total_rv > 0.01 else 0.0
                else:
                    raw_contribution = np.dot(peso, resultado[metrica].values)
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
                    else: cal_txt = " DATOS INSUFICIENTES (Penalizado) Por favor, contacte con soporte para poder rellenar el dato faltante o eliminar dicho fondo"
                    
                    mensaje_extra = f"   Equivale a: {cal_txt}"


                # calcula lo que nos equivocamos
                diff = valor_real - valor_objetivo
                
                # Mostramos resultado (todo trasparente para que el usuario juzgue la calidad de la solución)
                print(f"   - {metrica}: {valor_real:.2f} (Meta: {valor_objetivo}) | Desv: {diff:.2f}{mensaje_extra}")
            else:
                print(f"    No se pudo auditar {metrica} (Columna no encontrada)")
        
    else:
        print(" No se encontró solución óptima.")