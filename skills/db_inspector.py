import sqlite3
import pandas as pd
import sys

# Resiliencia en consolas Windows (cp1252): fuerza UTF-8 para poder imprimir emojis/acentos.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

DB_FILE = 'FundMix.db'

def inspect_db():
    print("🔍 INICIANDO AUDITORÍA DE BASE DE DATOS FUNDMIX...")
    try:
        with sqlite3.connect(DB_FILE) as conn:
            df = pd.read_sql("SELECT * FROM fondos", conn)
            
        print(f"✅ Fondos registrados: {len(df)}")
        
        # Validar Data Shielding
        nulos_ter = df['TER'].isnull().sum()
        print(f"⚠️ Fondos sin TER: {nulos_ter}")
        
        # Validar la Renta Fija
        rf_df = df[df['ClaseActivo'].isin(['RF', 'Monetario'])]
        print(f"✅ Fondos de Renta Fija/Monetarios: {len(rf_df)}")
        if not rf_df.empty:
            sin_duracion = (rf_df['RF_Duracion'] == 0.0).sum()
            print(f"⚠️ Fondos RF sin Duración asignada: {sin_duracion}")
            
    except Exception as e:
        print(f"❌ Error al conectar con la base de datos: {e}")

if __name__ == "__main__":
    inspect_db()