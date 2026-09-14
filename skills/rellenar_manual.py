"""
Relleno manual asistido del Golden Record, fila a fila.

Pensado para los datos que el pipeline de factsheets no puede cubrir: los 3 ISINs
sin PDF, la geografía de los 4 fondos que hubo que resetear y cualquier hueco que
quieras completar a mano sin abrir el CSV y arriesgarte a romper el formato.

    python skills/rellenar_manual.py                 # pide el ISIN por consola
    python skills/rellenar_manual.py IE00BYX5N771    # ISIN directo
    python skills/rellenar_manual.py <ISIN> --grupo "Geo RV"   # solo un bloque
    python skills/rellenar_manual.py <ISIN> --forzar  # permite CORREGIR datos ya existentes

Por defecto solo ofrece las celdas vacías o a 0.0: el Data Shielding se respeta
igual que en el pipeline automático. `--forzar` es la excepción explícita para
corregir un dato erróneo, y avisa en rojo antes de sobrescribir nada.

Durante la sesión:
    <valor>  asigna            (acepta "72,3%", "72.3%" o "0.723" indistintamente)
    Enter    deja la celda como está
    ?        explica qué espera esa columna
    s        salta el resto del bloque actual
    q        termina de editar y pasa al resumen
    x        aborta sin escribir nada
"""
import argparse
import os
import shutil
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import procesar_pdfs as pipe  # noqa: E402  (reutiliza blindaje y validación)

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT_DIR = pipe.ROOT_DIR
CSV_FILE = pipe.CSV_FILE

# Orden de presentación: bloques temáticos, no el orden físico de columnas.
BLOQUES = [
    ("Identidad", ["Nombre", "Ticker", "Gestora", "TipoProducto", "EstiloGestion",
                   "Estrategia", "PoliticaDiv", "Divisa", "EsHedged", "ClaseActivo"]),
    ("Costes y riesgo", ["TER", "EscalaRiesgo"]),
    ("Exposición core", ["Expo_RV", "Expo_RF", "Expo_Monet", "Expo_Alt"]),
    ("Geo RV", [c for c in pipe.COLS_NUM if c.startswith("Geo_RV_")]),
    ("Geo RF", [c for c in pipe.COLS_NUM if c.startswith("Geo_RF_")]),
    ("Sectores", [c for c in pipe.COLS_NUM if c.startswith("Sec_")]),
    ("Métricas RF", ["RF_Duracion", "RF_Calidad", "RF_Gobierno", "RF_Corporativo", "RF_Yield"]),
    ("Rentabilidad", ["Ret_1Y", "Ret_3Y_Ann", "Ret_5Y_Ann"]),
    ("Riesgo 3 años", ["Volatilidad_3Y", "Sharpe_3Y", "Alpha_3Y", "Beta_3Y"]),
]

# Columnas que el optimizador interpreta como fracción (0-1), no como porcentaje.
COLS_FRACCION = {c for c in pipe.COLS_NUM
                 if c.startswith(("Expo_", "Geo_", "Sec_"))
                 or c in {"TER", "RF_Gobierno", "RF_Corporativo", "RF_Yield",
                          "Ret_1Y", "Ret_3Y_Ann", "Ret_5Y_Ann",
                          "Volatilidad_3Y", "Alpha_3Y"}}


def comprobar_escritura():
    try:
        with open(CSV_FILE, "a", encoding="utf-8"):
            pass
    except PermissionError:
        print(f"❌ {os.path.basename(CSV_FILE)} está bloqueado por otro programa.")
        print("   Ciérralo (¿Excel?) y vuelve a ejecutar. No se ha modificado nada.")
        sys.exit(1)


def ayuda_columna(col):
    if col in pipe.DOMINIOS:
        return f"uno de: {', '.join(sorted(pipe.DOMINIOS[col]))}"
    if col in pipe.COLS_TEXTO:
        return "texto libre (ej. para RF_Calidad: AAA, AA+, A-, BBB, BB, 'Ninguna')"
    partes = []
    if col in COLS_FRACCION:
        partes.append("fracción decimal — puedes escribir 72,3% y se guarda como 0.723")
    if col in pipe.RANGOS:
        lo, hi = pipe.RANGOS[col]
        partes.append(f"rango admitido [{lo}, {hi}]")
    return "; ".join(partes) or "numérico"


def parsear(col, texto):
    """Convierte lo que teclea el usuario al valor que espera el CSV."""
    texto = texto.strip()
    if col in pipe.DOMINIOS:
        # Normaliza a la forma canónica del dominio: "value" -> "Value", "etf" -> "ETF",
        # "market neutral" -> "Market Neutral". Si no casa con ninguna, se devuelve tal
        # cual para que validar() lo rechace con el mensaje que lista las opciones.
        canonico = next((v for v in pipe.DOMINIOS[col] if v.lower() == texto.lower()), None)
        return canonico if canonico else texto
    if col in pipe.COLS_TEXTO:
        return texto
    porcentaje = texto.endswith("%")
    numero = texto.rstrip("%").strip().replace(",", ".")
    valor = float(numero)
    if porcentaje:
        valor /= 100.0
    return valor


def elegir_fila(df, isin_arg):
    indice = {pipe.norm_isin(v): i for i, v in df["ISIN"].items()}
    isin = pipe.norm_isin(isin_arg) if isin_arg else ""
    while isin not in indice:
        if isin:
            print(f"⚠️  '{isin}' no está en el CSV.")
            candidatos = [k for k in indice if isin in k]
            if candidatos:
                print(f"   ¿Quisiste decir? {', '.join(candidatos[:5])}")
        try:
            isin = pipe.norm_isin(input("\nISIN a rellenar (Enter para salir): "))
        except EOFError:
            isin = ""
        if not isin:
            print("Nada que hacer.")
            sys.exit(0)
    return indice[isin], isin


def editar(fila, bloques, forzar):
    """Recorre los bloques pidiendo valores. Devuelve {columna: valor_formateado}."""
    cambios = {}
    for nombre, cols in bloques:
        candidatas = [c for c in cols
                      if c in pipe.COLS_ESCRIBIBLES
                      and (forzar or pipe.es_hueco(c, fila.get(c, "")))]
        if not candidatas:
            continue

        print(f"\n{'─' * 72}\n  {nombre}  ({len(candidatas)} campos editables)\n{'─' * 72}")
        saltar_bloque = False
        for col in candidatas:
            if saltar_bloque:
                break
            actual = str(fila.get(col, "")).strip()
            pista = f"[actual: {actual}]" if actual else "[vacío]"
            while True:
                try:
                    resp = input(f"  {col:<26} {pista} > ").strip()
                except EOFError:
                    return cambios
                if resp == "":
                    break
                if resp == "?":
                    print(f"{'':<28} └─ {ayuda_columna(col)}")
                    continue
                if resp.lower() == "s":
                    print(f"{'':<28} └─ salto el resto del bloque '{nombre}'")
                    saltar_bloque = True
                    break
                if resp.lower() == "q":
                    return cambios
                if resp.lower() == "x":
                    print("\n🚫 Abortado. No se ha escrito nada.")
                    sys.exit(0)
                try:
                    valor = parsear(col, resp)
                except ValueError:
                    print(f"{'':<28} └─ ❌ no es un número válido. {ayuda_columna(col)}")
                    continue
                errores, _ = pipe.validar({col: valor})
                if errores:
                    for e in errores:
                        print(f"{'':<28} └─ ❌ {e}")
                    continue
                if actual and forzar:
                    conf = input(f"{'':<28} └─ ⚠️  sobrescribir '{actual}' por "
                                 f"'{valor}'? [s/N] ").strip().lower()
                    if conf != "s":
                        break
                cambios[col] = pipe.fmt_valor(col, valor)
                print(f"{'':<28} └─ ✔️  {col} = {cambios[col]}")
                break
    return cambios


def main():
    parser = argparse.ArgumentParser(description="Relleno manual asistido del Golden Record")
    parser.add_argument("isin", nargs="?", help="ISIN a editar")
    parser.add_argument("--grupo", help="Editar solo un bloque (ej. \"Geo RV\")")
    parser.add_argument("--forzar", action="store_true",
                        help="Permite CORREGIR celdas que ya tienen valor")
    parser.add_argument("--no-sync", action="store_true",
                        help="No ejecutar ingest_csv.py al terminar")
    args = parser.parse_args()

    comprobar_escritura()
    df = pipe.cargar_csv()
    idx, isin = elegir_fila(df, args.isin)
    fila = {c: df.at[idx, c] for c in df.columns}

    print(f"\n{'=' * 72}")
    print(f"  {isin} — {fila['Nombre'] or '(sin nombre)'}")
    print(f"  Clase de activo: {fila['ClaseActivo'] or '(sin clasificar)'}"
          f"   |   Gestora: {fila['Gestora'] or '—'}")
    huecas = pipe.columnas_huecas(fila)
    print(f"  Celdas vacías o a 0.0: {len(huecas)} de {len(pipe.COLS_ESCRIBIBLES)}")
    if args.forzar:
        print("  ⚠️  MODO FORZAR: también se ofrecerán celdas que ya tienen datos.")
    print(f"{'=' * 72}")
    print("  Enter=saltar   ?=ayuda   s=saltar bloque   q=terminar   x=abortar")

    bloques = BLOQUES
    if args.grupo:
        bloques = [(n, c) for n, c in BLOQUES if n.lower() == args.grupo.lower()]
        if not bloques:
            print(f"❌ Bloque '{args.grupo}' no existe. Disponibles: "
                  f"{', '.join(n for n, _ in BLOQUES)}")
            sys.exit(1)

    cambios = editar(fila, bloques, args.forzar)

    if not cambios:
        print("\n✅ No has introducido ningún valor. El CSV queda intacto.")
        return

    # Validar la fila RESULTANTE, no solo los valores sueltos.
    resultante = dict(fila)
    resultante.update(cambios)
    errores, avisos = pipe.validar_fila_resultante(resultante)

    print(f"\n{'=' * 72}\n  RESUMEN — {len(cambios)} celdas a escribir\n{'=' * 72}")
    for col, valor in cambios.items():
        antes = str(fila.get(col, "")).strip() or "(vacío)"
        print(f"  {col:<26} {antes:>12}  ->  {valor}")
    for aviso in avisos:
        print(f"\n  ⚠️  {aviso}")
    if errores:
        print("\n  ❌ La fila resultante NO es coherente:")
        for e in errores:
            print(f"     - {e}")
        print("\n  No se escribe nada. Revisa los valores y vuelve a ejecutar.")
        sys.exit(1)

    try:
        if input("\n¿Guardar? [s/N] ").strip().lower() != "s":
            print("🚫 Descartado. El CSV queda intacto.")
            return
    except EOFError:
        print("🚫 Sin confirmación. El CSV queda intacto.")
        return

    marca = datetime.now().strftime("%Y%m%d_%H%M%S")
    shutil.copy2(CSV_FILE, f"{CSV_FILE}.bak_{marca}")
    for col, valor in cambios.items():
        df.at[idx, col] = valor
    df.to_csv(CSV_FILE, index=False)
    print(f"✅ Guardado. Backup: universo_fundmix.csv.bak_{marca}")

    if args.no_sync:
        print("➡️  Recuerda sincronizar: python skills/ingest_csv.py")
    else:
        print("\n🔄 Sincronizando SQLite...")
        os.system(f'python "{os.path.join(ROOT_DIR, "skills", "ingest_csv.py")}"')


if __name__ == "__main__":
    main()
