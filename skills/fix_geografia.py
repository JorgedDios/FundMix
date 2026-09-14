"""
Bypass puntual del Data Shielding para 4 filas con geografía RV envenenada.

La Feature 001 dejó cuatro fondos cuyas columnas Geo_RV_* suman más de 1, lo que
rompe la restricción de presupuesto del optimizador (una cartera del 109% o, en el
peor caso, del 200%). El blindaje impide sobrescribir esos valores desde el
pipeline de factsheets, así que se limpian aquí de forma explícita y acotada.

Este script es la ÚNICA excepción autorizada al Data Shielding del proyecto:
  - La lista de ISINs está fijada en el código; se niega a tocar cualquier otra fila.
  - Solo vacía columnas Geo_RV_* y Geo_RF_*; jamás toca identidad, costes,
    exposiciones core, sectores, métricas de RF ni rentabilidades.
  - Deja las celdas VACÍAS (no a 0.0) para que 'procesar_pdfs.py estado' las
    siga contando como huecos pendientes y no se confunda "no lo sabemos" con
    "la exposición es cero".
  - Crea backup con timestamp e imprime los valores anteriores para poder
    reconstruirlos con skills/rellenar_manual.py.

Es idempotente: una segunda ejecución no cambia nada.
"""
import os
import shutil
import sys
from datetime import datetime

import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV_FILE = os.path.join(ROOT_DIR, "universo_fundmix.csv")

# Auditoría del 2026-07-30: suma de Geo_RV_* fuera de rango.
ISINS_A_LIMPIAR = {
    "IE00BYX5N771": "Fidelity MSCI Japan Index Fund — Geo_RV sumaba 2.000",
    "IE00BYX5NX33": "Fidelity MSCI World Index Fund — Geo_RV sumaba 1.090",
    "IE00B03HD316": "Vanguard Global Stock Index EUR Hedged — Geo_RV sumaba 1.091",
    # 'US4642863926' (iShares MSCI World ETF) también estaba aquí, pero salió del universo
    # en la poda del 2026-08-02 por ser un ETF no UCITS. Se retira de la lista porque este
    # script aborta si algún ISIN no existe en el CSV.
}


def comprobar_escritura():
    """En Windows, tener el CSV abierto en Excel lo bloquea. Mejor detectarlo antes
    de haber hecho backup y modificado nada."""
    try:
        with open(CSV_FILE, "a", encoding="utf-8"):
            pass
    except PermissionError:
        print(f"❌ {os.path.basename(CSV_FILE)} está bloqueado por otro programa.")
        print("   Ciérralo (¿Excel?) y vuelve a ejecutar. No se ha modificado nada.")
        sys.exit(1)


def limpiar():
    comprobar_escritura()
    df = pd.read_csv(CSV_FILE, dtype=str, keep_default_na=False)
    cols_geo = [c for c in df.columns if c.startswith(("Geo_RV_", "Geo_RF_"))]

    indice = {str(v).strip().upper(): i for i, v in df["ISIN"].items()}
    faltan = [i for i in ISINS_A_LIMPIAR if i not in indice]
    if faltan:
        print(f"❌ Estos ISINs no existen en el CSV: {faltan}. Abortando.")
        sys.exit(1)

    cambios = []
    for isin, motivo in ISINS_A_LIMPIAR.items():
        idx = indice[isin]
        previos = {c: df.at[idx, c] for c in cols_geo if str(df.at[idx, c]).strip() != ""}
        if not previos:
            print(f"✔️  {isin} ya estaba limpio.")
            continue
        suma = sum(float(v) for c, v in previos.items()
                   if c.startswith("Geo_RV_") and c_num(v))
        for c in cols_geo:
            df.at[idx, c] = ""
        cambios.append((isin, motivo, previos, suma))

    if not cambios:
        print("✅ Nada que hacer: las 4 filas ya estaban limpias.")
        return

    marca = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = f"{CSV_FILE}.bak_{marca}"
    shutil.copy2(CSV_FILE, backup)
    df.to_csv(CSV_FILE, index=False)

    print(f"🗂️  Backup: {os.path.basename(backup)}\n")
    print("=" * 72)
    print("🧹 GEOGRAFÍA RESETEADA (valores anteriores, para poder reconstruirlos)")
    print("=" * 72)
    for isin, motivo, previos, suma in cambios:
        print(f"\n• {isin} — {motivo}")
        print(f"  suma previa de Geo_RV_*: {suma:.4f}")
        for c, v in previos.items():
            print(f"    {c:<26} = {v}")

    # Verificación posterior sobre el fichero ya escrito.
    df2 = pd.read_csv(CSV_FILE, dtype=str, keep_default_na=False)
    cols_rv = [c for c in df2.columns if c.startswith("Geo_RV_")]
    malas = []
    for _, r in df2.iterrows():
        v = [float(r[c]) for c in cols_rv if str(r[c]).strip() != ""]
        if v and sum(v) > 0 and abs(sum(v) - 1) > 0.05:
            malas.append((r["ISIN"], round(sum(v), 3)))
    print(f"\n{'=' * 72}")
    if malas:
        print(f"⚠️  Siguen existiendo filas con Geo_RV incoherente: {malas}")
    else:
        print("✅ Ninguna fila del universo tiene ya Geo_RV fuera de rango.")
    print("➡️  Reconstruye estas 4 con: python skills/rellenar_manual.py <ISIN>")
    print("➡️  Después sincroniza: python skills/ingest_csv.py")


def c_num(valor):
    try:
        float(valor)
        return True
    except ValueError:
        return False


if __name__ == "__main__":
    limpiar()
