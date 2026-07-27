import sys
import os

# Resiliencia en consolas Windows (cp1252): fuerza UTF-8 para poder imprimir emojis/acentos.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import optimizer

def test_convexity():
    print("🧮 VALIDANDO CONVEXIDAD DEL MOTOR CVXPY...")
    try:
        # Cargamos datos
        df = optimizer.get_data_from_db()
        if df.empty:
            print("⚠️ No hay datos para testear la convexidad.")
            return

        # Objetivos simulados (Stress Test)
        objetivos = {
            'Geo_RV_USA': 0.60,
            'Expo_RF': 0.40,
            'RF_Duracion': 5.0
        }
        
        resultado = optimizer.optimize_portfolio(df, objetivos)
        
        if resultado is not None:
            print("✅ TEST PASADO: El problema es convexo y el solver (ECOS) ha encontrado solución óptima.")
        else:
            print("❌ TEST FALLIDO: El solver no convergió. Revisa las restricciones matemáticas.")
            sys.exit(1)
            
    except Exception as e:
        print(f"❌ ERROR CRÍTICO DCP: Has roto las reglas de Programación Convexa. Detalle: {e}")
        sys.exit(1)

if __name__ == "__main__":
    test_convexity()