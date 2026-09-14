import sqlite3

DB_FILE = 'FundMix.db'

def create_schema():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # 1. Borramos tabla anterior para empezar limpio
    c.execute("DROP TABLE IF EXISTS fondos")
    
    # 2. Creamos la tabla con TODAS las columnas
    # (El orden aquí ya no importa para la inserción, pero lo mantenemos ordenado)
    c.execute("""
        CREATE TABLE fondos (
            -- IDENTIFICACIÓN
            ISIN TEXT PRIMARY KEY,
            Nombre TEXT,
            Ticker TEXT,           
            Gestora TEXT,
            TipoProducto TEXT,     -- 'ETF' o 'Fondo'
            
            -- CARACTERÍSTICAS
            EstiloGestion TEXT,    -- 'Activa' o 'Pasiva'
            -- Dominio cerrado de 13 valores (fuente de verdad: DOMINIOS en
            -- skills/procesar_pdfs.py). 'Alternativo' es categoría padre de las 3 últimas:
            -- excluirlo o ponerle una banda de estilo las arrastra (ver
            -- FAMILIAS_ESTRATEGIA en optimizer.py).
            -- OJO: este es el eje de ESTILO/FACTOR, independiente de ClaseActivo, que es
            -- el eje de COMPOSICIÓN. Un fondo Mixto puede ser Value, Defensivo o
            -- Flexible; por eso no existe una Estrategia llamada 'Mixto'.
            -- 'Small Cap' captura el factor TAMAÑO (SMB), que tiene beta, volatilidad y
            -- ciclicidad propias: no debe confundirse con 'Core' (mercado amplio).
            Estrategia TEXT,       -- 'Core', 'Value', 'Growth', 'Dividendo', 'Flexible',
                                   -- 'Small Cap', 'Alternativo', 'Inmobiliario',
                                   -- 'Quality', 'Defensivo',
                                   -- 'Event Driven', 'Market Neutral', 'Multiestrategia'
            PoliticaDiv TEXT,      -- 'Acc' o 'Dist'
            Divisa TEXT,           -- 'EUR', 'USD', 'GBP'...
            EsHedged TEXT,         -- 'Si' o 'No' (Unificado)
            
            -- METADATOS
            TER REAL,
            EscalaRiesgo INTEGER,  -- Antes SRRI
            ClaseActivo TEXT,      -- 'RV', 'RF', 'Mixto', 'Monetario', 'Alternativo'
            
            -- EXPOSICIONES DE CLASE (Suman 1.0)
            Expo_RV REAL DEFAULT 0,
            Expo_RF REAL DEFAULT 0,
            Expo_Monet REAL DEFAULT 0,
            Expo_Alt REAL DEFAULT 0,   -- Alternativos (oro, retorno absoluto, market neutral...)
            
            -- GEO RENTA VARIABLE
            -- CONVENCIÓN: reparto DENTRO de la renta variable del fondo, no sobre el
            -- fondo entero. Por tanto Sum(Geo_RV_*) = 1.0 siempre que el fondo tenga algo
            -- de bolsa, INDEPENDIENTEMENTE de cuánta bolsa lleve.
            --   Fondo 100% bolsa USA        -> Expo_RV=1.00, Geo_RV_USA=1.00
            --   Mixto 10% bolsa (toda USA)  -> Expo_RV=0.10, Geo_RV_USA=1.00
            -- Es lo que publican las fichas ("Market allocation" del fondo de renta
            -- variable). El motor calcula la exposición absoluta multiplicando por la
            -- máscara Expo_RV: 0.10 * 1.00 = 10% del fondo en bolsa USA.
            Geo_RV_USA REAL DEFAULT 0,
            Geo_RV_Europa REAL DEFAULT 0,
            Geo_RV_China REAL DEFAULT 0,
            Geo_RV_India REAL DEFAULT 0,
            Geo_RV_Taiwan REAL DEFAULT 0,
            Geo_RV_Korea REAL DEFAULT 0,
            Geo_RV_Brasil REAL DEFAULT 0,
            -- === NUEVO V2.1: AÑADIDO JAPÓN Y CANADÁ ===
            Geo_RV_Japon REAL DEFAULT 0,
            Geo_RV_Canada REAL DEFAULT 0,
            -- ===========================================
            Geo_RV_Emergentes_Otros REAL DEFAULT 0,
            Geo_RV_Otros REAL DEFAULT 0,
            
            -- GEO RENTA FIJA
            -- Misma convención: reparto DENTRO de la parte sensible a tipos del fondo.
            -- Sum(Geo_RF_*) = 1.0 si el fondo tiene bonos o monetario. El motor usa la
            -- máscara Expo_Tipos (= Expo_RF + Expo_Monet) para pasarlo a absoluto.
            Geo_RF_USA REAL DEFAULT 0,
            Geo_RF_Europa REAL DEFAULT 0,
            Geo_RF_Emergentes REAL DEFAULT 0,
            Geo_RF_Otros REAL DEFAULT 0,
            
            -- SECTORES (Solo RV) - TUS SECTORES COMPLETOS
            Sec_Tecnologia REAL DEFAULT 0,
            Sec_Salud REAL DEFAULT 0,
            Sec_Finanzas REAL DEFAULT 0,
            Sec_Consumo REAL DEFAULT 0,
            Sec_Industrial REAL DEFAULT 0,
            Sec_Energia REAL DEFAULT 0,
            Sec_Otros REAL DEFAULT 0,
            
            -- DETALLES RENTA FIJA (NIVEL PRO)
            RF_Duracion REAL DEFAULT 0,
            RF_Calidad TEXT,
            RF_Gobierno REAL DEFAULT 0,    -- % Deuda Pública
            RF_Corporativo REAL DEFAULT 0, -- % Deuda Empresas
            RF_Yield REAL DEFAULT 0,       -- TIR / Rentabilidad esperada
            
            -- RENTABILIDAD
            Ret_1Y REAL,
            Ret_3Y_Ann REAL,
            Ret_5Y_Ann REAL,
            
            -- RATIOS INFORMATIVOS (NIVEL DASHBOARD)
            Volatilidad_3Y REAL,
            Sharpe_3Y REAL,
            Alpha_3Y REAL,
            Beta_3Y REAL
        )
    """)
    conn.commit()
    conn.close()
    print(" Esquema de BBDD v2.1 creado correctamente.")

def insert_initial_data():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # --- DATOS DEFINIDOS COMO DICCIONARIOS (Robustez Profesional) ---
    # Cada fondo es un objeto independiente. No importa el orden de las claves.
    # De esta manera, independientemente de las actualizaciones en la base de datos, 
    # no tendremos que hacer nada, si no que actuará de forma independiente, poniendo NULL en un valor si se ha eliminado su columna o ignorando datos si sobran.
    
    fondos_data = [
        {
            # 1. S&P 500 ETF (Acc, USD, Sin cubrir)
            'ISIN': 'IE00B5BMR087', 'Nombre': 'iShares Core S&P 500', 'Ticker': 'CSPX',
            'Gestora': 'iShares', 'TipoProducto': 'ETF', 
            'EstiloGestion': 'Pasiva', 'Estrategia': 'Core',
            'PoliticaDiv': 'Acc', 'Divisa': 'USD', 'EsHedged': 'No',
            'TER': 0.0007, 'EscalaRiesgo': 5, 'ClaseActivo': 'RV',
            'Expo_RV': 1.0, 
            'Geo_RV_USA': 1.0, 
            # Sectores (Tec, Sal, Fin, Con, Ind, Ene, Otr)
            'Sec_Tecnologia': 0.3848, 'Sec_Salud': 0.0829, 'Sec_Finanzas': 0.1127, 
            'Sec_Consumo': 0.1424, 'Sec_Industrial': 0.0828, 'Sec_Energia': 0.0313, 'Sec_Otros': 0.1631,
            # Detalles RF (Todo 0)
            'RF_Duracion': 0.0, 'RF_Calidad': None, 
            'RF_Gobierno': 0.0, 'RF_Corporativo': 0.0, 'RF_Yield': 0.0,
            # Rentabilidad
            'Ret_1Y': 0.2946, 'Ret_3Y_Ann': 0.2329, 'Ret_5Y_Ann': 0.1384
        },
        {
            # 2. Bonos Globales ETF (Acc, EUR, Cubierto) - AQUÍ SÍ HAY DATOS RF
            'ISIN': 'IE00BDBRDM35', 'Nombre': 'iShares Global Agg Bond Eur Hedged', 'Ticker': 'AGGH',
            'Gestora': 'iShares', 'TipoProducto': 'ETF',
            'EstiloGestion': 'Pasiva', 'Estrategia': 'Core',
            'PoliticaDiv': 'Acc', 'Divisa': 'EUR', 'EsHedged': 'Si',
            'TER': 0.0010, 'EscalaRiesgo': 3, 'ClaseActivo': 'RF',
            'Expo_RF': 1.0,
            # Geo RF
            'Geo_RF_USA': 0.40, 'Geo_RF_Europa': 0.30, 'Geo_RF_Emergentes': 0.10, 'Geo_RF_Otros': 0.20,
            # Detalles RF PRO
            'RF_Duracion': 7.5, 'RF_Calidad': 'A', 
            'RF_Gobierno': 0.60, 'RF_Corporativo': 0.40, 'RF_Yield': 0.035, # Yield 3.5%
            # Rentabilidad
            'Ret_1Y': 0.04, 'Ret_3Y_Ann': -0.02, 'Ret_5Y_Ann': 0.01
        },
        {
            # 3. EMERGENTES (Ejemplo del nuevo desglose)
            'ISIN': 'IE0031786696', 'Nombre': 'Vanguard Emerging Markets Stock Index', 'Ticker': None,
            'Gestora': 'Vanguard', 'TipoProducto': 'Fondo',
            'EstiloGestion': 'Pasiva', 'Estrategia': 'Core',
            'PoliticaDiv': 'Acc', 'Divisa': 'EUR', 'EsHedged': 'No',
            'TER': 0.0023, 'EscalaRiesgo': 6, 'ClaseActivo': 'RV',
            'Expo_RV': 1.0,
            # Geo (Desglosado)
            'Geo_RV_China': 0.202, 'Geo_RV_India': 0.107, 'Geo_RV_Taiwan': 0.266, 
            'Geo_RV_Korea': 0.232, 'Geo_RV_Brasil': 0.038, 'Geo_RV_Emergentes_Otros': 0.155,
            # Sectores
            'Sec_Tecnologia': 0.438, 'Sec_Salud': 0.023, 'Sec_Finanzas': 0.178, 
            'Sec_Consumo': 0.110, 'Sec_Industrial': 0.068, 'Sec_Energia': 0.033, 'Sec_Otros': 0.150,
            # Detalles RF (Todo 0)
            'RF_Duracion': 0.0, 'RF_Calidad': None,
            'RF_Gobierno': 0.0, 'RF_Corporativo': 0.0, 'RF_Yield': 0.0,
            # Rentabilidad
            'Ret_1Y': 0.5010, 'Ret_3Y_Ann': 0.2122, 'Ret_5Y_Ann': 0.0832
        }
    ]

    # --- LÓGICA DE INSERCIÓN INTELIGENTE (EL CAMBIO PROFESIONAL) ---
    try:
        # 1. Leemos los nombres reales de las columnas en la BBDD
        c.execute("PRAGMA table_info(fondos)")
        columns_info = c.fetchall()
        # Creamos una lista solo con los nombres ['ISIN', 'Nombre', 'Ticker'...]
        db_columns_names = [col[1] for col in columns_info]

        count = 0
        for fondo in fondos_data:
            # 2. Para cada fondo, preparamos qué vamos a insertar
            # Solo cogemos los datos cuya clave coincida con una columna existente
            keys = []
            values = []
            
            for col_name in db_columns_names:
                # Si el dato está en el diccionario, lo usamos
                if col_name in fondo:
                    keys.append(col_name)
                    values.append(fondo[col_name])
                # Si no está (ej. olvidamos poner 'Sec_Energia' en un fondo), 
                # SQL pondrá el DEFAULT (0) o NULL automáticamente.
            
            # 3. Construimos la Query dinámicamente
            # INSERT INTO fondos (Col1, Col2...) VALUES (?, ?...)
            columns_str = ', '.join(keys)
            placeholders = ', '.join(['?'] * len(keys))
            sql = f"INSERT INTO fondos ({columns_str}) VALUES ({placeholders})"
            
            c.execute(sql, values)
            count += 1

        conn.commit()
        print(f" Datos Insertados (Modo Robusto): {count} fondos procesados correctamente.")
        
    except Exception as e:
        print(f" Error insertando datos: {e}")
        
    conn.close()

if __name__ == "__main__":
    create_schema()
    insert_initial_data()