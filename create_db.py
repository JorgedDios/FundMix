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
            PoliticaDiv TEXT,      -- 'Acc' o 'Dist'
            Divisa TEXT,           -- 'EUR', 'USD', 'GBP'...
            EsHedged TEXT,         -- 'Si' o 'No' (Unificado)
            
            -- METADATOS
            TER REAL,
            EscalaRiesgo INTEGER,  -- Antes SRRI
            ClaseActivo TEXT,      -- 'RV', 'RF', 'Monetario'
            
            -- EXPOSICIONES DE CLASE (Suman 1.0)
            Expo_RV REAL DEFAULT 0,
            Expo_RF REAL DEFAULT 0,
            Expo_Monet REAL DEFAULT 0,
            
            -- GEO RENTA VARIABLE (Suman 1.0 dentro de la parte RV)
            Geo_RV_USA REAL DEFAULT 0,
            Geo_RV_Europa REAL DEFAULT 0,
            Geo_RV_Emergentes REAL DEFAULT 0,
            Geo_RV_Otros REAL DEFAULT 0,
            
            -- GEO RENTA FIJA (Suman 1.0 dentro de la parte RF)
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
            Ret_5Y_Ann REAL
        )
    """)
    conn.commit()
    conn.close()
    print(f"✅ Esquema de BBDD creado correctamente.")

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
            'PoliticaDiv': 'Acc', 'Divisa': 'USD', 'EsHedged': 'No',
            'TER': 0.0007, 'EscalaRiesgo': 6, 'ClaseActivo': 'RV',
            'Expo_RV': 1.0, 
            'Geo_RV_USA': 1.0, 
            # Sectores (Tec, Sal, Fin, Con, Ind, Ene, Otr)
            'Sec_Tecnologia': 0.30, 'Sec_Salud': 0.13, 'Sec_Finanzas': 0.12, 
            'Sec_Consumo': 0.10, 'Sec_Industrial': 0.08, 'Sec_Energia': 0.04, 'Sec_Otros': 0.23,
            # Detalles RF (Todo 0)
            'RF_Duracion': 0.0, 'RF_Calidad': None, 
            'RF_Gobierno': 0.0, 'RF_Corporativo': 0.0, 'RF_Yield': 0.0,
            # Rentabilidad
            'Ret_1Y': 0.25, 'Ret_3Y_Ann': 0.10, 'Ret_5Y_Ann': 0.12
        },
        {
            # 2. Bonos Globales ETF (Acc, EUR, Cubierto) - AQUÍ SÍ HAY DATOS RF
            'ISIN': 'IE00BDBRDM35', 'Nombre': 'iShares Global Agg Bond Eur Hedged', 'Ticker': 'AGGH',
            'Gestora': 'iShares', 'TipoProducto': 'ETF',
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
            # 3. Fondo Indexado Mundo (Fondo, Acc, EUR, Sin cubrir)
            'ISIN': 'LU0996182563', 'Nombre': 'Amundi Index MSCI World', 'Ticker': None,
            'Gestora': 'Amundi', 'TipoProducto': 'Fondo',
            'PoliticaDiv': 'Acc', 'Divisa': 'EUR', 'EsHedged': 'No',
            'TER': 0.0030, 'EscalaRiesgo': 6, 'ClaseActivo': 'RV',
            'Expo_RV': 1.0,
            # Geo
            'Geo_RV_USA': 0.68, 'Geo_RV_Europa': 0.20, 'Geo_RV_Otros': 0.12,
            # Sectores
            'Sec_Tecnologia': 0.22, 'Sec_Salud': 0.12, 'Sec_Finanzas': 0.14, 
            'Sec_Consumo': 0.10, 'Sec_Industrial': 0.10, 'Sec_Energia': 0.05, 'Sec_Otros': 0.27,
            # Detalles RF (Todo 0)
            'RF_Duracion': 0.0, 'RF_Calidad': None,
            'RF_Gobierno': 0.0, 'RF_Corporativo': 0.0, 'RF_Yield': 0.0,
            # Rentabilidad
            'Ret_1Y': 0.20, 'Ret_3Y_Ann': 0.08, 'Ret_5Y_Ann': 0.10
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
        print(f"✅ Datos Insertados (Modo Robusto): {count} fondos procesados correctamente.")
        
    except Exception as e:
        print(f"❌ Error insertando datos: {e}")
        
    conn.close()

if __name__ == "__main__":
    create_schema()
    insert_initial_data()