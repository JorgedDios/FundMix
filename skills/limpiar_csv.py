"""
Reparación estructural del Golden Record, previa a la Feature 002.

Corrige defectos detectados en auditoría SIN alterar ningún dato financiero:
  1. Registros con doble entrecomillado (la fila de Cartesio X, Fi quedó envuelta
     como un único campo al no escaparse bien la coma interna del nombre).
  2. Espacios sobrantes en la columna ISIN (8 fondos), que rompen el match por ISIN.
  3. Líneas en blanco intermedias y filas sin el padding de 51 campos.
  4. ISINs duplicados: conserva la fila con más campos poblados y descarta el resto.
     Si dos duplicados tuvieran datos distintos y no vacíos, ABORTA en vez de elegir.

Es idempotente: una segunda ejecución no produce cambios. Crea backup antes de escribir.
"""
import csv
import os
import shutil
import sys
from datetime import datetime
from io import StringIO

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV_FILE = os.path.join(ROOT_DIR, "universo_fundmix.csv")


def parsear(linea):
    return next(csv.reader([linea]))


def serializar(campos):
    buffer = StringIO()
    csv.writer(buffer, lineterminator="").writerow(campos)
    return buffer.getvalue()


def poblados(campos):
    return sum(1 for c in campos if str(c).strip() != "")


def limpiar():
    if not os.path.exists(CSV_FILE):
        print(f"❌ No se encuentra {CSV_FILE}")
        sys.exit(1)

    with open(CSV_FILE, "r", encoding="utf-8") as fh:
        lineas = fh.read().splitlines()

    cabecera = parsear(lineas[0])
    n_cols = len(cabecera)
    idx_isin = cabecera.index("ISIN")

    registros = []  # (linea_original, campos, cambiada)
    reparadas, blancos, stripeadas, padded = [], 0, [], 0

    for n_linea, linea in enumerate(lineas[1:], start=2):
        if not linea.strip():
            blancos += 1
            continue

        campos = parsear(linea)
        cambiada = False

        # 1. Registro envuelto como un único campo (doble entrecomillado).
        if len(campos) == 1 and n_cols > 1:
            recuperado = parsear(campos[0])
            if len(recuperado) == n_cols:
                campos = recuperado
                cambiada = True
                reparadas.append((n_linea, campos[idx_isin]))

        # 2. Espacios sobrantes en el ISIN.
        if campos[idx_isin] != campos[idx_isin].strip():
            stripeadas.append((n_linea, campos[idx_isin]))
            campos[idx_isin] = campos[idx_isin].strip()
            cambiada = True

        # 3. Padding a 51 campos.
        if len(campos) < n_cols:
            campos = campos + [""] * (n_cols - len(campos))
            padded += 1
            cambiada = True
        elif len(campos) > n_cols:
            print(f"❌ Línea {n_linea}: {len(campos)} campos (esperados {n_cols}). Abortando.")
            sys.exit(1)

        registros.append((linea, campos, cambiada))

    # 4. Deduplicación por ISIN: gana la fila con más campos poblados.
    por_isin = {}
    for pos, (_, campos, _) in enumerate(registros):
        por_isin.setdefault(campos[idx_isin], []).append(pos)

    descartar, eliminados = set(), []
    for isin, posiciones in por_isin.items():
        if len(posiciones) < 2:
            continue
        # Si más de una fila tiene datos reales y no son idénticas, no decidimos por el usuario.
        con_datos = [p for p in posiciones if poblados(registros[p][1]) > 1]
        if len(con_datos) > 1:
            distintas = {tuple(registros[p][1]) for p in con_datos}
            if len(distintas) > 1:
                print(f"❌ ISIN {isin} duplicado con datos DISTINTOS en filas {con_datos}.")
                print("   Requiere decisión humana. Abortando sin escribir nada.")
                sys.exit(1)
        ganadora = max(posiciones, key=lambda p: (poblados(registros[p][1]), -p))
        for p in posiciones:
            if p != ganadora:
                descartar.add(p)
                eliminados.append((isin, poblados(registros[p][1])))

    salida = [lineas[0]]
    for pos, (original, campos, cambiada) in enumerate(registros):
        if pos in descartar:
            continue
        salida.append(serializar(campos) if cambiada else original)

    # Backup antes de escribir.
    marca = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = f"{CSV_FILE}.bak_{marca}"
    shutil.copy2(CSV_FILE, backup)

    with open(CSV_FILE, "w", encoding="utf-8", newline="") as fh:
        fh.write("\n".join(salida) + "\n")

    # Informe.
    print(f"🗂️  Backup: {os.path.basename(backup)}")
    print(f"🔧 Registros desenvueltos: {len(reparadas)} {reparadas}")
    print(f"✂️  ISINs con espacios corregidos: {len(stripeadas)} -> {[i.strip() for _, i in stripeadas]}")
    print(f"🧹 Líneas en blanco eliminadas: {blancos}")
    print(f"➕ Filas rellenadas a {n_cols} campos: {padded}")
    print(f"🗑️  Filas duplicadas eliminadas: {len(eliminados)} {eliminados}")

    # Validación posterior: el fichero resultante debe ser impecable.
    with open(CSV_FILE, "r", encoding="utf-8") as fh:
        finales = [l for l in fh.read().splitlines() if l.strip()]
    malas = [i for i, l in enumerate(finales[1:], start=2) if len(parsear(l)) != n_cols]
    if malas:
        print(f"❌ Quedan líneas mal formadas: {malas}")
        sys.exit(1)

    isins = [parsear(l)[idx_isin] for l in finales[1:]]
    duplicados = sorted({i for i in isins if isins.count(i) > 1})
    if duplicados:
        print(f"❌ Siguen existiendo ISINs duplicados: {duplicados}")
        sys.exit(1)
    con_espacios = [i for i in isins if i != i.strip()]
    if con_espacios:
        print(f"❌ Siguen existiendo ISINs con espacios: {con_espacios}")
        sys.exit(1)

    print(f"✅ {len(isins)} filas, todas con {n_cols} campos, ISINs únicos y sin espacios.")


if __name__ == "__main__":
    limpiar()
