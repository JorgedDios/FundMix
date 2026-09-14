"""
Poda del Universo de Inversión (2026-08-02).

Retira del Golden Record los fondos redundantes, no comprables o subóptimos, para que el
optimizador trabaje sobre un universo curado y el mantenimiento manual sea sostenible.

Criterios aplicados (ver el análisis completo en el plan de la sesión):
  A) No comprables o sin datos  -> ETFs no UCITS (ISIN US, sin KID PRIIPs), filas fantasma,
     duplicados de domicilio y fondos cuyo único folleto está obsoleto.
  B) Redundancia exacta         -> mismo índice Y misma forma (Tipo/Divisa/Hedge/PolíticaDiv):
     sobra el más caro o el menos líquido.
  C) Solapamiento temático      -> decisión de gestor sobre salud y alternativos.

NO se tocan las clases que son la única de su forma (EUR-Hedged, USD, distribución...), porque
el motor optimiza preferencias de divisa, cobertura y política de dividendos: eliminarlas
dejaría objetivos del usuario sin instrumento con el que satisfacerse.

Es idempotente: una segunda ejecución detecta que ya no están y no hace nada.
Los PDFs de los fondos retirados se mueven a datos/pdfs_retirados/ en vez de borrarse.
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
PROCESADOS_DIR = os.path.join(ROOT_DIR, "datos", "pdfs_procesados")
RETIRADOS_DIR = os.path.join(ROOT_DIR, "datos", "pdfs_retirados")

# ISIN -> (bloque, motivo). Lista cerrada: el script se niega a tocar cualquier otra fila.
A_ELIMINAR = {
    # --- Bloque A: no comprables o sin datos utilizables ---
    "US4642863926": ("A", "ETF no UCITS (ISIN US, sin KID PRIIPs). MSCI World ya cubierto en 5 formas"),
    "US4642878614": ("A", "ETF no UCITS + TER 0,60%, el más caro de Europa (equivalente a 0,10%)"),
    "US46434V7385": ("A", "ETF no UCITS. Hueco cubierto por Vanguard FTSE Developed Europe (0,10%)"),
    "IE00BGV5VN51": ("A", "Fila fantasma: sin nombre, sin TER, sin geografía, sin folleto"),
    "LU1333148903": ("A", "Duplicado de ES0112611001 (Azvalor) con +63 pb de TER y sin datos"),
    "ES0138922036": ("A", "Único folleto es de 2012; sin duración ni rating. Cubierto por IE00BL1GVT98"),
    # --- Bloque B: redundancia exacta (mismo índice y misma forma) ---
    "IE0032126645": ("B", "S&P500 Fondo/EUR/Acc duplicado: Fidelity IE00BYX5MX67 cuesta 0,06% vs 0,10%"),
    "IE00B03HD191": ("B", "MSCI World Fondo/EUR/Acc duplicado: Fidelity IE00BYX5NX33 a 0,12% vs 0,18%"),
    "IE00BFMXXD54": ("B", "S&P500 ETF/USD/Acc: empate a 0,07% con iShares IE00B5BMR087, más líquido"),
    # --- Bloque C2: solapamiento en salud (se conserva IE00BJ5JNZ06, 0,18%) ---
    "IE00BM67HK77": ("C2", "Mismo índice que IE00BJ5JNZ06 (World Health Care) a 0,25% vs 0,18%"),
    "IE00BYZK4776": ("C2", "Temático de salud a 0,40%; solapa con el sectorial amplio"),
    # --- Bloque C3: alternativos (se conservan Jupiter IE00BLP5S460 y Dunas ES0175414012) ---
    "LU1112771503": ("C3", "Retorno absoluto a TER 1,90%; cupo cubierto por Jupiter y Dunas"),
    "LU1508158430": ("C3", "Retorno absoluto a TER 1,91%; cupo cubierto por Jupiter y Dunas"),
}


def comprobar_escritura():
    try:
        with open(CSV_FILE, "a", encoding="utf-8"):
            pass
    except PermissionError:
        print(f"❌ {os.path.basename(CSV_FILE)} está bloqueado por otro programa.")
        print("   Ciérralo (¿Excel?) y vuelve a ejecutar. No se ha modificado nada.")
        sys.exit(1)


def podar():
    comprobar_escritura()
    df = pd.read_csv(CSV_FILE, dtype=str, keep_default_na=False)
    presentes = {str(v).strip().upper() for v in df["ISIN"]}

    objetivo = [i for i in A_ELIMINAR if i in presentes]
    ausentes = [i for i in A_ELIMINAR if i not in presentes]

    if not objetivo:
        print("✅ Nada que hacer: los 13 fondos ya fueron retirados.")
        return

    print("=" * 78)
    print(f"🌳 PODA DEL UNIVERSO — {len(objetivo)} fondos a retirar de {len(df)}")
    print("=" * 78)
    for isin in objetivo:
        bloque, motivo = A_ELIMINAR[isin]
        fila = df[df["ISIN"].str.strip().str.upper() == isin].iloc[0]
        nombre = fila["Nombre"] or "(sin nombre)"
        print(f"\n  [{bloque}] {isin}  {fila['ClaseActivo'] or '?'}")
        print(f"       {nombre[:64]}")
        print(f"       → {motivo}")
    if ausentes:
        print(f"\n  ℹ️  Ya no estaban en el CSV: {ausentes}")

    marca = datetime.now().strftime("%Y%m%d_%H%M%S")
    shutil.copy2(CSV_FILE, f"{CSV_FILE}.bak_{marca}")

    df_podado = df[~df["ISIN"].str.strip().str.upper().isin(objetivo)].copy()
    df_podado.to_csv(CSV_FILE, index=False)

    # Los folletos no se borran: se archivan por si hay que revertir la decisión.
    os.makedirs(RETIRADOS_DIR, exist_ok=True)
    movidos = 0
    for isin in objetivo:
        origen = os.path.join(PROCESADOS_DIR, f"{isin}.pdf")
        if os.path.exists(origen):
            shutil.move(origen, os.path.join(RETIRADOS_DIR, f"{isin}.pdf"))
            movidos += 1

    print(f"\n{'=' * 78}")
    print(f"🗂️  Backup: universo_fundmix.csv.bak_{marca}")
    print(f"📄 PDFs archivados en datos/pdfs_retirados/: {movidos}")
    print(f"✅ Universo: {len(df)} → {len(df_podado)} fondos")

    reparto = df_podado["ClaseActivo"].value_counts()
    print("\n   Reparto resultante:")
    for clase, n in reparto.items():
        print(f"     {clase or '(sin clase)':<14} {n}")

    # Verificación: ninguna categoría puede quedarse vacía.
    for clase in ("RV", "RF", "Monetario", "Mixto", "Alternativo"):
        if reparto.get(clase, 0) == 0:
            print(f"\n⚠️  ATENCIÓN: la clase '{clase}' se ha quedado sin fondos.")

    print("\n➡️  Siguiente: python skills/ingest_csv.py")


if __name__ == "__main__":
    podar()
