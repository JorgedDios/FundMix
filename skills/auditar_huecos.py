"""
Auditoría de huecos del Golden Record: qué fondos están completos y qué le falta
exactamente a cada uno de los demás.

    python skills/auditar_huecos.py                    # informe completo
    python skills/auditar_huecos.py --bloque "Geo RV"  # solo un bloque
    python skills/auditar_huecos.py --completos        # solo la lista de completos
    python skills/auditar_huecos.py --sin-color        # para redirigir a fichero

Dos decisiones que conviene tener presentes al leer el informe:

1. Aquí "hueco" significa CELDA VACÍA, no `0.0`. El pipeline de factsheets trata
   el 0.0 como rellenable (para poder curar los Mixtos), pero para saber qué te
   falta por rellenar un 0.0 es un dato legítimo: que un fondo tenga 0% de China
   es información, no una ausencia.

2. Un fondo se considera completo cuando no le falta nada en los bloques que
   APLICAN a su ClaseActivo. No tiene sentido exigirle duración de bonos a un ETF
   de renta variable ni desglose sectorial a un fondo monetario.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import procesar_pdfs as pipe  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

BLOQUES = [
    ("Identidad", ["Nombre", "Gestora", "TipoProducto", "EstiloGestion",
                   "PoliticaDiv", "Divisa", "EsHedged", "ClaseActivo"]),
    ("Costes y riesgo", ["TER", "EscalaRiesgo"]),
    ("Exposición core", ["Expo_RV", "Expo_RF", "Expo_Monet", "Expo_Alt"]),
    ("Geo RV", [c for c in pipe.COLS_NUM if c.startswith("Geo_RV_")]),
    ("Geo RF", [c for c in pipe.COLS_NUM if c.startswith("Geo_RF_")]),
    ("Sectores", [c for c in pipe.COLS_NUM if c.startswith("Sec_")]),
    ("Métricas RF", ["RF_Duracion", "RF_Calidad", "RF_Gobierno", "RF_Corporativo", "RF_Yield"]),
    ("Rentabilidad", ["Ret_1Y", "Ret_3Y_Ann", "Ret_5Y_Ann"]),
    ("Riesgo 3 años", ["Volatilidad_3Y", "Sharpe_3Y", "Alpha_3Y", "Beta_3Y"]),
]

# Bloques que NO se le exigen a cada clase de activo.
NO_APLICA = {
    "RV": {"Geo RF", "Métricas RF"},
    "RF": {"Geo RV", "Sectores"},
    "Monetario": {"Geo RV", "Sectores"},
    "Alternativo": {"Geo RV", "Geo RF", "Sectores", "Métricas RF"},
    "Mixto": set(),
}

# `Ticker` y `Estrategia` quedan fuera del informe: solo los llevan los ETFs
# cotizados y los fondos alternativos respectivamente, y su ausencia no es un hueco.


class Color:
    def __init__(self, activo):
        self.on = activo

    def _c(self, codigo, texto):
        return f"\033[{codigo}m{texto}\033[0m" if self.on else texto

    def verde(self, t):
        return self._c("32", t)

    def amarillo(self, t):
        return self._c("33", t)

    def rojo(self, t):
        return self._c("31", t)

    def gris(self, t):
        return self._c("90", t)

    def bold(self, t):
        return self._c("1", t)


def bloques_aplicables(clase):
    excluidos = NO_APLICA.get(str(clase).strip(), set())
    return [(n, cols) for n, cols in BLOQUES if n not in excluidos]


def analizar(fila):
    """Devuelve {bloque: [columnas vacías]} solo de los bloques aplicables."""
    faltan = {}
    for nombre, cols in bloques_aplicables(fila.get("ClaseActivo", "")):
        vacias = [c for c in cols if str(fila.get(c, "")).strip() == ""]
        if vacias:
            faltan[nombre] = vacias
    return faltan


def main():
    parser = argparse.ArgumentParser(description="Auditoría de huecos del Golden Record")
    parser.add_argument("--bloque", help='Filtrar por bloque (ej. "Geo RV")')
    parser.add_argument("--completos", action="store_true", help="Solo la lista de completos")
    parser.add_argument("--sin-color", action="store_true")
    args = parser.parse_args()

    if os.name == "nt":
        os.system("")  # habilita las secuencias ANSI en la consola de Windows
    c = Color(not args.sin_color and sys.stdout.isatty())

    df = pipe.cargar_csv()
    completos, incompletos = [], []
    for _, fila in df.iterrows():
        faltan = analizar(fila)
        if args.bloque:
            faltan = {k: v for k, v in faltan.items() if k.lower() == args.bloque.lower()}
        registro = (fila["ISIN"], fila["Nombre"] or "(sin nombre)",
                    fila["ClaseActivo"] or "?", faltan)
        (completos if not faltan else incompletos).append(registro)

    total = len(df)
    print(f"\n{c.bold('═' * 78)}")
    print(c.bold(f"  AUDITORÍA DE HUECOS — {total} fondos en universo_fundmix.csv"))
    print(c.gris("  Hueco = celda vacía. Solo se exigen los bloques que aplican a cada ClaseActivo."))
    if args.bloque:
        print(c.gris(f"  Filtrado por bloque: {args.bloque}"))
    print(c.bold("═" * 78))

    # --- Completos ---
    print(f"\n{c.verde('✅ COMPLETOS')}  {len(completos)}/{total} "
          f"({100 * len(completos) / total:.0f}%)")
    if completos:
        for isin, nombre, clase, _ in sorted(completos, key=lambda r: r[0]):
            print(f"   {c.verde(isin):<24} {c.gris(f'[{clase:<11}]')} {nombre[:44]}")
    else:
        print(c.gris("   (ninguno)"))

    if args.completos:
        return

    # --- Incompletos, los más graves primero ---
    incompletos.sort(key=lambda r: -sum(len(v) for v in r[3].values()))
    print(f"\n{c.amarillo('⚠️  INCOMPLETOS')}  {len(incompletos)}/{total}"
          f"   {c.gris('(ordenados por nº de celdas vacías)')}")
    for isin, nombre, clase, faltan in incompletos:
        n = sum(len(v) for v in faltan.values())
        marca = c.rojo(f"{n:>3} vacías") if n >= 10 else c.amarillo(f"{n:>3} vacías")
        print(f"\n   {c.bold(isin)}  {marca}  {c.gris(f'[{clase}]')}  {nombre[:50]}")
        for bloque, cols in faltan.items():
            total_bloque = next(len(cs) for nb, cs in BLOQUES if nb == bloque)
            etiqueta = f"{bloque} ({len(cols)}/{total_bloque})"
            detalle = "bloque entero" if len(cols) == total_bloque else ", ".join(cols)
            print(f"      {c.gris('·')} {etiqueta:<22} {detalle}")

    # --- Resumen por bloque ---
    print(f"\n{c.bold('─' * 78)}\n{c.bold('  RESUMEN POR BLOQUE')}\n{c.bold('─' * 78)}")
    print(f"   {'Bloque':<20}{'fondos afectados':>18}{'celdas vacías':>16}"
          f"{'aplicable a':>12}")
    for nombre, cols in BLOQUES:
        afectados = sum(1 for *_, f in incompletos if nombre in f)
        celdas = sum(len(f[nombre]) for *_, f in incompletos if nombre in f)
        aplica = sum(1 for _, fl in df.iterrows()
                     if nombre in {n for n, _ in bloques_aplicables(fl["ClaseActivo"])})
        if not aplica:
            continue
        color = c.verde if afectados == 0 else (c.rojo if afectados > aplica / 2 else c.amarillo)
        print(f"   {nombre:<20}{color(f'{afectados:>18}')}{celdas:>16}{aplica:>12}")

    if incompletos:
        peor = incompletos[0][0]
        print(f"\n{c.gris('➡️  Para rellenar el más incompleto:')}")
        print(f"   .\\.venv\\Scripts\\python.exe skills\\rellenar_manual.py {peor}")


if __name__ == "__main__":
    main()
