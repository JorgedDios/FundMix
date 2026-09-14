"""
Auditoría de integridad del Golden Record y lista de tareas de data entry.

    python skills/db_inspector.py              # informe completo (audita el CSV)
    python skills/db_inspector.py --db         # audita SQLite en vez del CSV
    python skills/db_inspector.py --isin XXX   # solo un fondo
    python skills/db_inspector.py --resumen    # sin la tabla de tareas
    python skills/db_inspector.py --sin-color

Todo se calcula dinámicamente desde la fuente: no hay ISINs ni contadores fijados en el
código, así que el informe siempre refleja el universo actual, crezca o se pode.

Qué campo es obligatorio depende de la EXPOSICIÓN REAL del fondo, no de su etiqueta
ClaseActivo. Un mixto con un 80% de bonos necesita duración y rating igual que un fondo
de renta fija puro; un fondo de bolsa, no. Es el mismo criterio que usa el motor
(máscaras Expo_RV / Expo_Tipos), para que la auditoría no discrepe del optimizador.
"""
import argparse
import os
import sqlite3
import sys

import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_FILE = os.path.join(ROOT_DIR, "FundMix.db")
CSV_FILE = os.path.join(ROOT_DIR, "universo_fundmix.csv")

UMBRAL_CLASE = 0.01   # exposición mínima para exigir los campos de esa clase

# Campos obligatorios SIEMPRE, sea cual sea el fondo.
OBLIGATORIOS_BASE = ["Nombre", "Gestora", "TipoProducto", "EstiloGestion",
                     "PoliticaDiv", "Divisa", "EsHedged", "ClaseActivo", "TER"]
# Obligatorios solo si el fondo tiene exposición a tipos (bonos o monetario).
OBLIGATORIOS_TIPOS = ["RF_Duracion", "RF_Calidad", "RF_Yield"]
# Obligatorios solo si el fondo tiene renta variable.
OBLIGATORIOS_RV = ["Geo_RV_USA", "Sec_Tecnologia"]   # centinelas de sus grupos

GRUPOS = {
    "Geo RV": lambda cols: [c for c in cols if c.startswith("Geo_RV_")],
    "Geo RF": lambda cols: [c for c in cols if c.startswith("Geo_RF_")],
    "Sectores": lambda cols: [c for c in cols if c.startswith("Sec_")],
}


class Color:
    def __init__(self, on):
        self.on = on

    def _c(self, code, t):
        return f"\033[{code}m{t}\033[0m" if self.on else t

    def verde(self, t): return self._c("32", t)
    def rojo(self, t): return self._c("31", t)
    def ambar(self, t): return self._c("33", t)
    def gris(self, t): return self._c("90", t)
    def bold(self, t): return self._c("1", t)


def num(fila, col):
    """Valor numérico de una celda, tolerando vacíos, NaN y texto."""
    if col not in fila:
        return 0.0
    v = fila[col]
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return 0.0
    try:
        return float(str(v).strip()) if str(v).strip() else 0.0
    except ValueError:
        return 0.0


def vacia(fila, col):
    if col not in fila:
        return True
    v = fila[col]
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return True
    return str(v).strip() in ("", "nan", "None")


def cargar(usar_db):
    """El CSV es la fuente por defecto y no es un capricho: al insertar en SQLite, las
    celdas vacías se convierten en el DEFAULT 0 de la columna, así que un hueco real
    (duración sin rellenar) queda indistinguible de un 0 legítimo (un monetario).
    Solo el CSV conserva la diferencia, y es además el fichero que se edita a mano."""
    if not usar_db:
        return pd.read_csv(CSV_FILE, dtype=str, keep_default_na=False), "universo_fundmix.csv"
    if not os.path.exists(DB_FILE):
        print(f"❌ No existe {DB_FILE}. Ejecuta primero: python skills/ingest_csv.py")
        sys.exit(1)
    with sqlite3.connect(DB_FILE) as conn:
        return pd.read_sql("SELECT * FROM fondos", conn), "FundMix.db"


def campos_pendientes(fila, columnas):
    """Devuelve {bloque: [campos]} exigibles a ESTE fondo y que están vacíos."""
    expo_rv = num(fila, "Expo_RV")
    expo_tipos = num(fila, "Expo_RF") + num(fila, "Expo_Monet")
    pendientes = {}

    base = [c for c in OBLIGATORIOS_BASE if c in columnas and vacia(fila, c)]
    if base:
        pendientes["Identidad/Coste"] = base

    if expo_tipos > UMBRAL_CLASE:
        faltan = [c for c in OBLIGATORIOS_TIPOS if c in columnas and vacia(fila, c)]
        # 'Desconocido' es lo que deja la limpieza cuando no hubo dato: cuenta como hueco.
        if "RF_Calidad" in columnas and str(fila.get("RF_Calidad", "")).strip() == "Desconocido":
            if "RF_Calidad" not in faltan:
                faltan.append("RF_Calidad")
        if faltan:
            pendientes[f"Renta Fija ({expo_tipos:.0%} del fondo)"] = faltan

    for nombre, selector in GRUPOS.items():
        cols = selector(columnas)
        if not cols:
            continue
        procede = expo_rv > UMBRAL_CLASE if nombre in ("Geo RV", "Sectores") else expo_tipos > UMBRAL_CLASE
        if not procede:
            continue
        valores = [num(fila, c) for c in cols if not vacia(fila, c)]
        if not valores or sum(valores) == 0:
            pendientes[f"{nombre} (bloque entero)"] = ["sin datos"]
        elif abs(sum(valores) - 1.0) > 0.05:
            pendientes[f"{nombre} (suma {sum(valores):.3f})"] = ["debería sumar 1.0"]
    return pendientes


def main():
    p = argparse.ArgumentParser(description="Auditoría del Golden Record y lista de tareas")
    p.add_argument("--db", action="store_true",
                   help="Auditar SQLite en vez del CSV (ojo: allí los huecos ya valen 0.0)")
    p.add_argument("--isin", help="Auditar un solo fondo")
    p.add_argument("--resumen", action="store_true", help="Omitir la tabla de tareas")
    p.add_argument("--sin-color", action="store_true")
    args = p.parse_args()

    if os.name == "nt":
        os.system("")
    c = Color(not args.sin_color and sys.stdout.isatty())

    df, fuente = cargar(args.db)
    columnas = list(df.columns)
    if args.isin:
        df = df[df["ISIN"].astype(str).str.strip().str.upper() == args.isin.strip().upper()]
        if df.empty:
            print(f"❌ '{args.isin}' no está en {fuente}.")
            sys.exit(1)

    total = len(df)
    print(f"\n{c.bold('=' * 84)}")
    print(c.bold(f"  AUDITORÍA DEL GOLDEN RECORD — {total} fondos  ·  fuente: {fuente}"))
    print(c.gris("  Los campos exigidos dependen de la exposición REAL del fondo, no de su etiqueta."))
    if args.db:
        print(c.ambar("  ⚠️  En SQLite los huecos numéricos ya valen 0.0: no se distinguen de un cero"))
        print(c.ambar("      real. Para la lista de tareas usa la fuente CSV (por defecto)."))
    print(c.bold("=" * 84))

    # --- Reparto por clase (dinámico) ---
    print(f"\n{c.bold('REPARTO POR CLASE DE ACTIVO')}")
    for clase, n in df["ClaseActivo"].fillna("(sin clase)").replace("", "(sin clase)").value_counts().items():
        print(f"   {clase:<16} {n:>3}")

    # --- Coherencia estructural ---
    print(f"\n{c.bold('COHERENCIA ESTRUCTURAL')}")
    core = ["Expo_RV", "Expo_RF", "Expo_Monet", "Expo_Alt"]
    malos_core, malos_geo = [], []
    for _, fila in df.iterrows():
        if all(c_ in columnas and not vacia(fila, c_) for c_ in core):
            s = sum(num(fila, c_) for c_ in core)
            if abs(s - 1.0) > 0.02:
                malos_core.append((fila["ISIN"], round(s, 4)))
        for nombre, selector in GRUPOS.items():
            cols = selector(columnas)
            vals = [num(fila, c_) for c_ in cols if not vacia(fila, c_)]
            if vals and sum(vals) > 0 and abs(sum(vals) - 1.0) > 0.05:
                malos_geo.append((fila["ISIN"], nombre, round(sum(vals), 3)))
    print(f"   {'Suma Expo_RV+RF+Monet+Alt = 1':<46} "
          + (c.verde("OK") if not malos_core else c.rojo(f"{len(malos_core)} fallos: {malos_core}")))
    print(f"   {'Grupos Geo/Sec suman 1 dentro de su clase':<46} "
          + (c.verde("OK") if not malos_geo else c.ambar(f"{len(malos_geo)} avisos")))
    for isin, grupo, s in malos_geo[:8]:
        print(f"      {c.gris('·')} {isin} · {grupo} suma {s}")
    dup = df[df["ISIN"].duplicated(keep=False)]["ISIN"].tolist()
    print(f"   {'ISIN únicos':<46} " + (c.verde("OK") if not dup else c.rojo(f"duplicados: {dup}")))

    # --- Lista de tareas ---
    tareas = []
    for _, fila in df.iterrows():
        pend = campos_pendientes(fila, columnas)
        if pend:
            tareas.append((fila["ISIN"], str(fila.get("Nombre") or "(sin nombre)"),
                           str(fila.get("ClaseActivo") or "?"), pend))

    completos = total - len(tareas)
    print(f"\n{c.bold('ESTADO GENERAL')}")
    print(f"   {c.verde('Completos')}: {completos}/{total}   "
          f"{c.ambar('Con campos pendientes')}: {len(tareas)}/{total}")

    if args.resumen or not tareas:
        if not tareas:
            print(f"\n   {c.verde('No hay campos obligatorios pendientes.')}")
        print()
        return

    print(f"\n{c.bold('─' * 84)}")
    print(c.bold("  📋 LISTA DE TAREAS — campos obligatorios en blanco"))
    print(c.bold("─" * 84))
    tareas.sort(key=lambda t: -sum(len(v) for v in t[3].values()))
    for isin, nombre, clase, pend in tareas:
        n = sum(len(v) for v in pend.values())
        marca = c.rojo(f"{n:>2} campos") if n >= 4 else c.ambar(f"{n:>2} campos")
        print(f"\n   {c.bold(isin)}  {marca}  {c.gris('[' + clase + ']')}  {nombre[:46]}")
        for bloque, campos in pend.items():
            print(f"      {c.gris('·')} {bloque:<30} {', '.join(campos)}")

    # --- Resumen por campo, para saber por dónde empezar ---
    print(f"\n{c.bold('─' * 84)}")
    print(c.bold("  CAMPOS MÁS REPETIDOS"))
    print(c.bold("─" * 84))
    cuenta = {}
    for *_, pend in tareas:
        for campos in pend.values():
            for campo in campos:
                if campo not in ("sin datos", "debería sumar 1.0"):
                    cuenta[campo] = cuenta.get(campo, 0) + 1
    for campo, n in sorted(cuenta.items(), key=lambda x: -x[1]):
        print(f"   {campo:<24} {n:>3} fondos")

    peor = tareas[0][0]
    print(f"\n{c.gris('➡️  Para rellenar el más incompleto:')}")
    print(f"   .\\.venv\\Scripts\\python.exe skills\\rellenar_manual.py {peor}\n")


if __name__ == "__main__":
    main()
