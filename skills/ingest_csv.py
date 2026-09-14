import sqlite3
import pandas as pd
import os
import sys

# Resiliencia en consolas Windows (cp1252): fuerza UTF-8 para poder imprimir emojis/acentos.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# Asegurar que encuentra la base de datos y el CSV en la raíz
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_FILE = os.path.join(ROOT_DIR, 'FundMix.db')
CSV_FILE = os.path.join(ROOT_DIR, 'universo_fundmix.csv')

def ingest_data():
    print("📥 INICIANDO INGESTA DE DATOS DESDE CSV...")
    
    if not os.path.exists(CSV_FILE):
        print(f"❌ Error: No se encuentra el archivo {CSV_FILE}")
        sys.exit(1)

    try:
        # Leer el CSV asegurando que los nulos se manejan bien
        df_csv = pd.read_csv(CSV_FILE)
        fondos_data = df_csv.to_dict(orient='records')
        
        with sqlite3.connect(DB_FILE) as conn:
            c = conn.cursor()

            # El esquema es responsabilidad exclusiva de create_db.py. Aquí solo se
            # comprueba que la BBDD sea la esperada: si faltara una columna, el INSERT
            # dinámico de más abajo la omitiría SIN AVISAR y perderíamos el dato en
            # silencio, así que preferimos abortar de forma ruidosa.
            c.execute("PRAGMA table_info(fondos)")
            columnas_bbdd = {col[1] for col in c.fetchall()}
            if "Expo_Alt" not in columnas_bbdd:
                print("❌ La BBDD no tiene la columna 'Expo_Alt' (esquema anterior a Feature 001).")
                print("   Recrea el esquema con: python create_db.py   [OJO: borra la tabla]")
                sys.exit(1)

            # Limpiar la tabla antes de la carga masiva (carga destructiva/fresca)
            c.execute("DELETE FROM fondos")

            # Obtener nombres de columnas reales de la BBDD
            c.execute("PRAGMA table_info(fondos)")
            db_columns_names = [col[1] for col in c.fetchall()]
            
            count = 0
            for fondo in fondos_data:
                keys = []
                values = []
                
                for col_name in db_columns_names:
                    if col_name in fondo and not pd.isna(fondo[col_name]):
                        keys.append(col_name)
                        values.append(fondo[col_name])
                
                if not keys:
                    continue
                    
                columns_str = ', '.join(keys)
                placeholders = ', '.join(['?'] * len(keys))
                sql = f"INSERT INTO fondos ({columns_str}) VALUES ({placeholders})"
                
                c.execute(sql, values)
                count += 1
                
            conn.commit()
            print(f"✅ Ingesta completada: {count} fondos insertados/actualizados de forma segura en SQLite.")
            
    except Exception as e:
        print(f"❌ Error crítico en la ingesta: {e}")
        sys.exit(1)

if __name__ == "__main__":
    ingest_data()