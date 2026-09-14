"""
Feature 002 — Enriquecimiento del Golden Record desde factsheets PDF.

Pipeline en dos fases (agente en el bucle, sin API externa):

  1) python skills/procesar_pdfs.py extract
     Toma los primeros 5 PDFs de datos/pdfs_pendientes/, extrae texto y tablas
     con pdfplumber y los deja en datos/_lote_actual/<ISIN>.txt junto a un
     manifiesto lote.json. NO toca el CSV ni mueve ningún PDF.

  2) El agente lee los .txt y escribe datos/_lote_actual/extraido.json
     con la forma {"<ISIN>": {"<Columna>": valor|null, ...}, ...}

  3) python skills/procesar_pdfs.py apply
     Valida el JSON, aplica Data Shielding sobre universo_fundmix.csv, mueve los
     PDFs aplicados a datos/pdfs_procesados/ y archiva el lote en
     datos/logs_extraccion/ para auditoría.

  python skills/procesar_pdfs.py estado
     Informe de cobertura: pendientes, procesados e ISINs del CSV sin PDF.

Reglas duras (ver constitution/mission.md, "Data Shielding"):
  - ISIN nunca se sobrescribe.
  - Columnas de texto/identidad: solo si la celda está vacía.
  - Columnas numéricas: si la celda está vacía o vale 0.0 (imprescindible para la
    "Cura de los Mixtos" en Expo_RV / Expo_RF / Expo_Monet / Expo_Alt).
  - null = dato ausente en el PDF -> no se escribe nada.
  - PDF sin fila en el CSV -> INSERT. Fila del CSV sin PDF -> skip silencioso.
"""
import argparse
import json
import os
import re
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
DATOS_DIR = os.path.join(ROOT_DIR, "datos")
PENDIENTES_DIR = os.path.join(DATOS_DIR, "pdfs_pendientes")
PROCESADOS_DIR = os.path.join(DATOS_DIR, "pdfs_procesados")
LOTE_DIR = os.path.join(DATOS_DIR, "_lote_actual")
LOGS_DIR = os.path.join(DATOS_DIR, "logs_extraccion")
MANIFIESTO = os.path.join(LOTE_DIR, "lote.json")
EXTRAIDO = os.path.join(LOTE_DIR, "extraido.json")

BATCH_SIZE = 5
# 25.000 se quedaba corto: en los informes semestrales de la CNMV el desglose
# RF/RV de la sección 3.1 cae más allá de ese punto y quedaba truncado.
MAX_CHARS = 45000
MIN_CHARS_UTIL = 200

# --- Whitelist de columnas escribibles y su régimen de blindaje -------------

COLS_TEXTO = [
    "Nombre", "Ticker", "Gestora", "TipoProducto", "EstiloGestion", "Estrategia",
    "PoliticaDiv", "Divisa", "EsHedged", "ClaseActivo", "RF_Calidad",
]
COLS_NUM = [
    "TER", "EscalaRiesgo",
    "Expo_RV", "Expo_RF", "Expo_Monet", "Expo_Alt",
    "Geo_RV_USA", "Geo_RV_Europa", "Geo_RV_Japon", "Geo_RV_Canada", "Geo_RV_China",
    "Geo_RV_India", "Geo_RV_Taiwan", "Geo_RV_Korea", "Geo_RV_Brasil",
    "Geo_RV_Emergentes_Otros", "Geo_RV_Otros",
    "Geo_RF_USA", "Geo_RF_Europa", "Geo_RF_Emergentes", "Geo_RF_Otros",
    "Sec_Tecnologia", "Sec_Salud", "Sec_Finanzas", "Sec_Consumo", "Sec_Industrial",
    "Sec_Energia", "Sec_Otros",
    "RF_Duracion", "RF_Gobierno", "RF_Corporativo", "RF_Yield",
    "Ret_1Y", "Ret_3Y_Ann", "Ret_5Y_Ann", "Volatilidad_3Y", "Sharpe_3Y",
    "Alpha_3Y", "Beta_3Y",
]
COLS_ESCRIBIBLES = COLS_TEXTO + COLS_NUM
COLS_PROTEGIDAS = {"ISIN"}

# Dominios cerrados: cualquier otro valor rechaza el fondo.
DOMINIOS = {
    "TipoProducto": {"Fondo", "ETF"},
    "PoliticaDiv": {"Acc", "Dist"},
    "EsHedged": {"Si", "No"},
    "ClaseActivo": {"RV", "RF", "Mixto", "Monetario", "Alternativo"},
    "EstiloGestion": {"Pasiva", "Activa"},
    # Las 10 primeras son las que ofrece la interfaz (ESTRATEGIAS_PRINCIPALES en app.py).
    # Las 3 últimas son subestrategias de 'Alternativo': no aparecen en la UI salvo que
    # el usuario despliegue el submenú, pero sí están en el CSV desde la Feature 001.
    #
    # 'Flexible' = gestión activa mixta sin restricciones fijas de clase, geografía,
    # sector ni duración. Es un EJE DISTINTO de ClaseActivo='Mixto': aquel describe qué
    # contiene el fondo, este cómo lo gestiona. No se usa 'Core' para estos fondos
    # porque en este universo 'Core' significa indexado puro de mercado amplio.
    #
    # 'Small Cap' = sesgo de TAMAÑO (el factor SMB de Fama-French), no de estilo. No es
    # un matiz de 'Core': sobre los datos del propio universo, un global small cap frente
    # a su hermano de gran capitalización lleva -14 pp de Tecnología, +9 pp de Industrial
    # y +6 pp de Japón. Marcarlo 'Core' metería un sesgo de tamaño no solicitado en quien
    # pida un núcleo indexado de mercado amplio.
    "Estrategia": {
        "Core", "Value", "Growth", "Dividendo", "Flexible", "Small Cap",
        "Alternativo", "Inmobiliario", "Quality", "Defensivo",
        "Event Driven", "Market Neutral", "Multiestrategia",
    },
}

# OJO — deuda conocida sobre 'Estrategia' (auditoría del 2026-07-30):
# Los 4 fondos con 'Event Driven' / 'Market Neutral' / 'Multiestrategia' tienen
# ClaseActivo='Alternativo', pero el filtro de exclusión de la UI compara contra
# la columna Estrategia (optimizer.py:148), no contra ClaseActivo. Resultado: marcar
# "Alternativo" en la app NO los excluye, y tampoco casan con ninguna banda de estilo
# (optimizer.py:331). Se resuelve de una de estas dos formas, que es decisión de negocio:
#   (a) añadir esos 3 valores a las listas de app.py, o
#   (b) remapear los 4 fondos a Estrategia='Alternativo' y reducir este dominio a 8.

# Rangos numéricos admisibles (min, max).
RANGOS = {c: (0.0, 1.0) for c in COLS_NUM if c.startswith(("Expo_", "Geo_", "Sec_"))}
RANGOS.update({
    "TER": (0.0, 0.05),
    "EscalaRiesgo": (1, 7),
    "RF_Duracion": (0.0, 40.0),
    "RF_Gobierno": (0.0, 1.0),
    "RF_Corporativo": (0.0, 1.0),
    "RF_Yield": (-0.05, 0.30),
    "Ret_1Y": (-1.0, 3.0),
    "Ret_3Y_Ann": (-1.0, 3.0),
    "Ret_5Y_Ann": (-1.0, 3.0),
    "Alpha_3Y": (-1.0, 1.0),
    "Volatilidad_3Y": (0.0, 2.0),
    "Sharpe_3Y": (-5.0, 5.0),
    "Beta_3Y": (-3.0, 3.0),
})

GRUPOS_SUMA_1 = {
    "core": ["Expo_RV", "Expo_RF", "Expo_Monet", "Expo_Alt"],
    "geo_rv": [c for c in COLS_NUM if c.startswith("Geo_RV_")],
    "geo_rf": [c for c in COLS_NUM if c.startswith("Geo_RF_")],
    "sectores": [c for c in COLS_NUM if c.startswith("Sec_")],
}

# --- Utilidades -------------------------------------------------------------


def asegurar_directorios():
    for d in (PENDIENTES_DIR, PROCESADOS_DIR, LOTE_DIR, LOGS_DIR):
        os.makedirs(d, exist_ok=True)


def cargar_csv():
    """Carga el CSV como texto puro: pandas no debe reinterpretar ni un número."""
    return pd.read_csv(CSV_FILE, dtype=str, keep_default_na=False)


def norm_isin(valor):
    return str(valor).strip().upper()


def celda_vacia(valor):
    return valor is None or str(valor).strip() == ""


def hueco_numerico(valor):
    """Hueco = vacío o exactamente 0.0 (regla de la 'Cura de los Mixtos')."""
    if celda_vacia(valor):
        return True
    try:
        return float(str(valor).strip()) == 0.0
    except ValueError:
        return False


def es_hueco(columna, valor):
    return celda_vacia(valor) if columna in COLS_TEXTO else hueco_numerico(valor)


def fmt_valor(columna, valor):
    """Serializa el valor tal y como debe quedar escrito en el CSV."""
    if columna in COLS_TEXTO:
        return str(valor).strip()
    f = float(valor)
    if f == int(f):
        return str(int(f))
    texto = f"{f:.8f}".rstrip("0")
    return texto + "0" if texto.endswith(".") else texto


def columnas_huecas(fila):
    return [c for c in COLS_ESCRIBIBLES if es_hueco(c, fila.get(c, ""))]


# Un informe semestral de la CNMV son ~45.000 caracteres de los que el 80% es
# aviso legal, régimen fiscal y política de remuneración. El condensado conserva
# solo las líneas con señal financiera; el .txt íntegro se guarda igualmente en
# el staging para poder consultarlo cuando el condensado no baste.
# Texto jurídico y de contacto: nunca aporta un dato financiero.
RE_BOILERPLATE = re.compile(
    r"aviso legal|no constituye|rentabilidades? pasadas?|no garantiza|garantizado?s? "
    r"resultados|folleto|datos fundamentales|kiid|priip|"
    r"autorizada y regulada|supervisi[óo]n de la comisi[óo]n|domicilio social|"
    r"registro mercantil|inscrita en|derechos de los inversores|reclamaci|"
    r"oficina de atenci[óo]n|atenci[óo]n al (cliente|inversor)|"
    r"pol[íi]tica de remuneraci[óo]n|r[ée]gimen fiscal|auditor|depositario:|"
    r"material (de marketing|promocional)|fines meramente informativos|"
    r"marcas comerciales|derechos reservados|llamadas telef[óo]nicas|"
    r"asesoramiento|recomendaci[óo]n de inversi[óo]n|capital en riesgo|"
    r"www\.|https?:|@|tel[:.]|tel[ée]fono|correo electr|direcci[óo]n$",
    re.IGNORECASE,
)

# Etiquetas de alta precisión: se conservan aunque la línea no traiga números.
RE_ETIQUETAS = re.compile(
    r"isin|ticker|bloomberg|gestora|management company|empresa de gesti[óo]n|"
    r"divisa|currency|hedge|cubiert|"
    r"gastos|ongoing charge|expense ratio|\bter\b|comisi[óo]n de|"
    r"perfil de riesgo|indicador de riesgo|\bsri\b|\bsrri\b|escala del? 1|"
    r"vocaci[óo]n|categor[íi]a|clase de activos?|asset class|tipo de fondo|"
    r"uso de los ingresos|acumulaci[óo]n|reparto|"
    r"rentabilidad|return|performance|anualizad|annualis|annualiz|"
    r"volatilidad|volatility|sharpe|\bbeta\b|\balpha\b|tracking error|"
    r"duraci[óo]n|duration|maturity|yield|\btir\b|cup[óo]n|"
    r"rating|calidad crediticia|credit quality|"
    r"geogr[áa]fic|geographic|desglose|exposici[óo]n|exposure|"
    # Los desgloses geográficos vienen como gráfico de barras: cada país es una
    # línea con un solo porcentaje, sin etiqueta de sección que la acompañe.
    r"estados unidos|united states|\busa\b|norteam|am[ée]rica|"
    r"europa|europe|reino unido|united kingdom|alemania|germany|francia|france|"
    r"suiza|switzerland|pa[íi]ses bajos|netherlands|holanda|italia|italy|"
    r"espa[ñn]a|spain|suecia|sweden|dinamarca|denmark|noruega|norway|"
    r"finlandia|finland|b[ée]lgica|belgium|irlanda|ireland|austria|portugal|"
    r"jap[óo]n|japan|china|hong kong|india|taiw[áa]n|taiwan|corea|korea|"
    r"brasil|brazil|m[ée]xico|mexico|canad[áa]|canada|australia|"
    r"emergent|emerging|desarrollad|developed|"
    r"sector|tecnolog|technology|salud|health|financier|finanzas|financials|"
    r"consumo|consumer|industrial|energ[íi]a|energy|utilities|servicios p[úu]blicos|"
    r"materiales|materials|materias primas|inmobiliari|real estate|telecom|"
    r"distribuci[óo]n (del|de la)|allocation|"
    r"renta fija|renta variable|fixed income|liquidez|tesorer|dep[óo]sito|"
    r"total (patrimonio|inversiones|renta|iic|dep)|inversiones financieras|"
    r"metodolog[íi]a|[íi]ndice de referencia|benchmark|r[ée]plica|gesti[óo]n pasiva|"
    r"===== P[ÁA]GINA|--- TABLA",
    re.IGNORECASE,
)

RE_NUMERO = re.compile(r"-?\d+(?:[.,]\d+)?")
LINEAS_CABECERA = 25  # identidad del fondo: nombre, ISIN, gestora, fecha

# Los informes periódicos de la CNMV tienen formato rígido y obligatorio, así que
# se pueden podar sin heurística frágil: (a) cada tabla aparece dos veces, en
# texto plano y como bloque "--- TABLA ---"; (b) la sección 3.1 lista la cartera
# valor a valor, cientos de líneas de las que solo importan los subtotales.
RE_CNMV = re.compile(r"N[ºo°]?\s*Registro CNMV", re.IGNORECASE)
RE_TABLA = re.compile(r"^--- TABLA ")
RE_PAGINA = re.compile(r"^===== P[ÁA]GINA ")
RE_SEC_CARTERA = re.compile(r"^\s*3\.\d\s|Inversiones financieras a valor", re.IGNORECASE)
RE_SEC_FIN_CARTERA = re.compile(r"^\s*4\.\s|Hechos relevantes", re.IGNORECASE)
RE_SUBTOTAL = re.compile(r"TOTAL\s+(RENTA|IIC|DEP[ÓO]SITOS|INVERSIONES|DERIVADOS|"
                         r"ADQUISICI|INTERESES|PATRIMONIO)", re.IGNORECASE)
# Desde "4. Hechos relevantes" hasta el final solo hay hechos relevantes, operaciones
# vinculadas y el comentario de gestión: narrativa, ningún campo del schema.
RE_CNMV_FIN = re.compile(r"^\s*4\.\s*Hechos relevantes", re.IGNORECASE)
# Bloques intermedios sin ningún campo: (inicio, hasta dónde se salta).
BLOQUES_CNMV_INUTILES = [
    (re.compile(r"^\s*B\)\s*Comparativa", re.I), re.compile(r"^\s*2\.3\s", re.I)),
    (re.compile(r"^\s*2\.4\s*Estado de variaci", re.I),
     re.compile(r"Inversiones financieras a valor|^\s*3\.1", re.I)),
    (re.compile(r"^\s*3\.[23]\s|^\s*3\.[23]\(cid", re.I), RE_CNMV_FIN),
]


def podar_cnmv(texto):
    """Elimina la duplicación tabla/texto y el detalle valor a valor de la cartera."""
    salida, en_tabla, en_cartera, saltar_hasta = [], False, False, None
    for linea in texto.split("\n"):
        # El bloque TABLA dura hasta la siguiente tabla o el siguiente salto de página.
        if RE_TABLA.match(linea):
            en_tabla = True
            continue
        if RE_PAGINA.match(linea):
            en_tabla = False
        if en_tabla:
            continue

        # Bloques completos sin ningún campo del schema.
        if saltar_hasta is not None:
            if saltar_hasta.search(linea):
                saltar_hasta = None
            else:
                continue
        if RE_CNMV_FIN.search(linea):
            break
        salto = next((fin for ini, fin in BLOQUES_CNMV_INUTILES if ini.search(linea)), None)
        if salto is not None:
            saltar_hasta = salto
            continue

        if RE_SEC_CARTERA.search(linea):
            en_cartera = True
        elif RE_SEC_FIN_CARTERA.search(linea):
            en_cartera = False
        if en_cartera and not RE_SUBTOTAL.search(linea) and not RE_SEC_CARTERA.search(linea):
            if not RE_PAGINA.match(linea):
                continue
        salida.append(linea)
    return "\n".join(salida)


def condensar(texto, contexto=1):
    """Deja solo las líneas con señal financiera.

    Dos criterios de retención: etiquetas de alta precisión y densidad numérica
    (>=3 números). El segundo es imprescindible: en los factsheets de proveedor
    las rentabilidades viven en filas de tabla sin etiqueta propia, del estilo
    "Clase del fondo | 7.56 25.95 14.66 52.20 46.81 32.51".
    """
    if RE_CNMV.search(texto[:4000]):
        texto = podar_cnmv(texto)
    lineas = texto.split("\n")
    conservar = set()
    for i, linea in enumerate(lineas):
        if i < LINEAS_CABECERA:
            conservar.add(i)
            continue
        if RE_BOILERPLATE.search(linea):
            continue
        if RE_ETIQUETAS.search(linea) or len(RE_NUMERO.findall(linea)) >= 3:
            conservar.update(range(max(0, i - contexto), min(len(lineas), i + contexto + 1)))

    salida, vistas, ultimo = [], set(), -2
    for i in sorted(conservar):
        linea = lineas[i]
        if RE_BOILERPLATE.search(linea):
            continue
        clave = " ".join(linea.split())
        if not clave or clave in vistas:
            continue
        vistas.add(clave)
        if i > ultimo + 1:
            salida.append("[...]")
        salida.append(linea)
        ultimo = i
    return "\n".join(salida)


def extraer_texto(ruta_pdf):
    """Texto + tablas. Las tablas importan: los desgloses geo/sectorial van en tabla."""
    import pdfplumber

    partes = []
    with pdfplumber.open(ruta_pdf) as pdf:
        for n, pagina in enumerate(pdf.pages, start=1):
            partes.append(f"\n===== PÁGINA {n} =====")
            texto = pagina.extract_text() or ""
            if texto.strip():
                partes.append(texto)
            for t, tabla in enumerate(pagina.extract_tables() or [], start=1):
                filas = [
                    " | ".join((celda or "").strip() for celda in fila)
                    for fila in tabla
                ]
                filas = [f for f in filas if f.strip(" |")]
                if filas:
                    partes.append(f"--- TABLA {n}.{t} ---")
                    partes.extend(filas)
    completo = "\n".join(partes)
    if len(completo) > MAX_CHARS:
        completo = completo[:MAX_CHARS] + "\n\n[...TRUNCADO POR LÍMITE DE CARACTERES...]"
    return completo


# --- Fase 1: extract --------------------------------------------------------


def cmd_extract(batch_size):
    asegurar_directorios()

    residuo = [f for f in os.listdir(LOTE_DIR) if not f.startswith(".")]
    if residuo:
        print("❌ Hay un lote sin aplicar en datos/_lote_actual/:")
        print(f"   {residuo}")
        print("   Ejecuta 'apply' o vacía la carpeta antes de extraer otro lote.")
        sys.exit(1)

    df = cargar_csv()
    filas_por_isin = {norm_isin(f["ISIN"]): f for _, f in df.iterrows()}

    pdfs = sorted(f for f in os.listdir(PENDIENTES_DIR) if f.lower().endswith(".pdf"))
    if not pdfs:
        print("✅ No quedan PDFs pendientes.")
        return

    lote, items = pdfs[:batch_size], []
    for nombre in lote:
        isin = norm_isin(os.path.splitext(nombre)[0])
        try:
            texto = extraer_texto(os.path.join(PENDIENTES_DIR, nombre))
        except Exception as exc:
            print(f"⚠️  {nombre}: no se pudo extraer texto ({exc}). Se deja pendiente.")
            continue

        # El condensado es lo que lee el agente; el crudo queda al lado como
        # respaldo para cuando el condensado se quede corto en algún fondo.
        resumen = condensar(texto)
        with open(os.path.join(LOTE_DIR, f"{isin}.txt"), "w", encoding="utf-8") as fh:
            fh.write(resumen)
        with open(os.path.join(LOTE_DIR, f"{isin}.completo.txt"), "w", encoding="utf-8") as fh:
            fh.write(texto)

        fila = filas_por_isin.get(isin)
        items.append({
            "isin": isin,
            "pdf": nombre,
            "txt": f"{isin}.txt",
            "txt_completo": f"{isin}.completo.txt",
            "chars_crudo": len(texto),
            "accion": "update" if fila is not None else "insert",
            "nombre_actual": fila["Nombre"] if fila is not None else None,
            "clase_activo_actual": fila["ClaseActivo"] if fila is not None else None,
            "columnas_huecas": columnas_huecas(fila) if fila is not None else COLS_ESCRIBIBLES,
            "chars": len(resumen),
            "necesita_vision": len(texto) < MIN_CHARS_UTIL,
        })

    with open(MANIFIESTO, "w", encoding="utf-8") as fh:
        json.dump({
            "generado": datetime.now().isoformat(timespec="seconds"),
            "pendientes_restantes": len(pdfs) - len(items),
            "items": items,
        }, fh, indent=2, ensure_ascii=False)

    print(f"📄 Lote preparado: {len(items)} PDFs -> datos/_lote_actual/")
    for it in items:
        aviso = "  ⚠️ SIN TEXTO (usar visión)" if it["necesita_vision"] else ""
        print(f"   • {it['isin']}  [{it['accion']}]  {it['chars']} chars  "
              f"{len(it['columnas_huecas'])} huecos{aviso}")
    print(f"📊 PDFs aún pendientes tras este lote: {len(pdfs) - len(items)}")
    print("\n➡️  Siguiente: el agente lee los .txt y escribe "
          "datos/_lote_actual/extraido.json")
    print('    Forma: {"<ISIN>": {"<Columna>": valor|null, ...}, ...}')
    print("    Porcentajes SIEMPRE como fracción decimal (72.3% -> 0.723).")
    print("    Dato ausente en el PDF -> null. Nunca inventar.")


# --- Fase 2: apply ----------------------------------------------------------


def validar(datos):
    """Devuelve (errores, avisos). Con errores, el fondo no se aplica."""
    errores, avisos = [], []

    for col in datos:
        if col in COLS_PROTEGIDAS:
            errores.append(f"'{col}' es columna protegida, no se puede escribir")
        elif col not in COLS_ESCRIBIBLES:
            errores.append(f"'{col}' no existe en el schema permitido")

    for col, valor in datos.items():
        if valor is None or col not in COLS_ESCRIBIBLES:
            continue
        if col in DOMINIOS and str(valor).strip() not in DOMINIOS[col]:
            errores.append(f"{col}='{valor}' fuera del dominio {sorted(DOMINIOS[col])}")
            continue
        if col in COLS_TEXTO:
            continue
        try:
            num = float(valor)
        except (TypeError, ValueError):
            errores.append(f"{col}='{valor}' no es numérico")
            continue
        if col in RANGOS:
            lo, hi = RANGOS[col]
            if not lo <= num <= hi:
                errores.append(f"{col}={num} fuera de rango [{lo}, {hi}]")

    # Coherencia de los grupos que deben sumar 1.
    for nombre, cols in GRUPOS_SUMA_1.items():
        presentes = {c: datos[c] for c in cols if datos.get(c) is not None}
        if not presentes:
            continue
        try:
            total = sum(float(v) for v in presentes.values())
        except (TypeError, ValueError):
            continue
        if nombre == "core" and len(presentes) == len(cols) and abs(total - 1.0) > 0.05:
            errores.append(f"grupo 'core' suma {total:.3f}, debe ser 1.0 (±0.05)")
        elif nombre != "core" and total > 0 and abs(total - 1.0) > 0.05:
            avisos.append(f"grupo '{nombre}' suma {total:.3f} "
                          f"({len(presentes)}/{len(cols)} columnas presentes)")

    return errores, avisos


def validar_fila_resultante(fila):
    """Valida la fila DESPUÉS de aplicar el blindaje.

    Escribir solo parte del grupo core es peligroso: si Expo_RV ya valía 1 y el
    folleto aporta un 5% de RF, la fila acabaría sumando 1.05 y rompería la
    restricción de presupuesto del optimizador (sum(w) == 1). Por eso la
    coherencia se comprueba sobre el resultado final, no sobre el JSON de entrada.
    """
    errores, avisos = [], []

    core = {c: fila.get(c, "") for c in GRUPOS_SUMA_1["core"]}
    if all(not celda_vacia(v) for v in core.values()):
        try:
            total = sum(float(v) for v in core.values())
        except ValueError:
            return ["grupo 'core' contiene valores no numéricos"], avisos
        if abs(total - 1.0) > 0.02:
            errores.append(
                f"la fila resultante deja Expo_RV+RF+Monet+Alt = {total:.4f} "
                f"(debe ser 1.0 ±0.02): {', '.join(f'{k}={v}' for k, v in core.items())}"
            )

    # Las geografías y los sectores son el reparto DENTRO de su clase de activo, así que
    # suman 1.0 con independencia de cuánto pese esa clase en el fondo:
    #   un mixto con 10% de bolsa toda en USA lleva Geo_RV_USA = 1.00, no 0.10.
    # El motor lo pasa a absoluto multiplicando por la máscara (Expo_RV / Expo_Tipos).
    # Solo se comprueba el grupo si el fondo tiene exposición real a esa clase.
    def _num(clave):
        valor = fila.get(clave, "")
        try:
            return float(valor) if not celda_vacia(valor) else 0.0
        except ValueError:
            return 0.0

    aplica = {
        "geo_rv": _num("Expo_RV") > 0.01,
        "geo_rf": (_num("Expo_RF") + _num("Expo_Monet")) > 0.01,
        "sectores": _num("Expo_RV") > 0.01,
    }
    for nombre, procede in aplica.items():
        valores = [fila.get(c, "") for c in GRUPOS_SUMA_1[nombre]]
        presentes = [float(v) for v in valores if not celda_vacia(v)]
        if not procede or not presentes or sum(presentes) <= 0:
            continue
        if abs(sum(presentes) - 1.0) > 0.05:
            avisos.append(f"la fila resultante deja '{nombre}' sumando {sum(presentes):.3f}; "
                          f"debería sumar 1.0 (es el reparto dentro de su clase de activo)")

    return errores, avisos


def cmd_apply(sync):
    asegurar_directorios()
    if not os.path.exists(MANIFIESTO):
        print("❌ No hay lote.json. Ejecuta primero 'extract'.")
        sys.exit(1)
    if not os.path.exists(EXTRAIDO):
        print("❌ Falta datos/_lote_actual/extraido.json (lo escribe el agente).")
        sys.exit(1)

    with open(MANIFIESTO, encoding="utf-8") as fh:
        manifiesto = json.load(fh)
    with open(EXTRAIDO, encoding="utf-8") as fh:
        extraido = json.load(fh)

    items = {it["isin"]: it for it in manifiesto["items"]}
    df = cargar_csv()
    indice = {norm_isin(v): i for i, v in df["ISIN"].items()}

    aceptados, rechazados, resumen = [], {}, []

    for isin_raw, datos in extraido.items():
        isin = norm_isin(isin_raw)
        if isin not in items:
            rechazados[isin] = ["no forma parte del lote actual"]
            continue

        errores, avisos = validar(datos)
        if errores:
            rechazados[isin] = errores
            continue

        # Se trabaja sobre una copia: la fila solo se escribe si el resultado
        # final sigue siendo financieramente coherente.
        escritas, blindadas = [], []
        existe = isin in indice
        fila = dict(df.loc[indice[isin]]) if existe else {c: "" for c in df.columns}
        if not existe:
            fila["ISIN"] = isin

        for col, valor in datos.items():
            if valor is None:
                continue
            if es_hueco(col, fila.get(col, "")):
                fila[col] = fmt_valor(col, valor)
                escritas.append(col)
            else:
                blindadas.append(col)

        errores_fila, avisos_fila = validar_fila_resultante(fila)
        if errores_fila:
            rechazados[isin] = errores_fila
            continue
        avisos = avisos + avisos_fila

        if existe:
            for col in escritas:
                df.at[indice[isin], col] = fila[col]
            accion = "UPDATE"
        else:
            df.loc[len(df)] = fila
            indice[isin] = len(df) - 1
            accion = "INSERT"

        aceptados.append(isin)
        resumen.append((isin, accion, escritas, blindadas, avisos))

    if aceptados:
        df.to_csv(CSV_FILE, index=False)

    # Informe.
    print("=" * 70)
    print("📝 RESULTADO DEL LOTE")
    print("=" * 70)
    for isin, accion, escritas, blindadas, avisos in resumen:
        print(f"\n✅ {isin} [{accion}] — {len(escritas)} columnas escritas")
        print(f"   escritas: {', '.join(escritas) if escritas else '(ninguna)'}")
        if blindadas:
            print(f"   🛡️  blindadas (ya tenían dato): {', '.join(blindadas)}")
        for aviso in avisos:
            print(f"   ⚠️  {aviso}")
    for isin, errores in rechazados.items():
        print(f"\n❌ {isin} RECHAZADO (su PDF sigue pendiente):")
        for err in errores:
            print(f"   - {err}")

    # Mover solo los PDFs aplicados con éxito.
    for isin in aceptados:
        nombre = items[isin]["pdf"]
        origen = os.path.join(PENDIENTES_DIR, nombre)
        if os.path.exists(origen):
            destino = os.path.join(PROCESADOS_DIR, nombre)
            if os.path.exists(destino):
                base, ext = os.path.splitext(nombre)
                destino = os.path.join(PROCESADOS_DIR,
                                       f"{base}__{datetime.now():%H%M%S}{ext}")
            shutil.move(origen, destino)
        for clave in ("txt", "txt_completo"):
            txt = os.path.join(LOTE_DIR, items[isin].get(clave, ""))
            if items[isin].get(clave) and os.path.exists(txt):
                os.remove(txt)

    # Archivar el lote para auditoría.
    marca = datetime.now().strftime("%Y%m%d_%H%M%S")
    with open(os.path.join(LOGS_DIR, f"lote_{marca}.json"), "w", encoding="utf-8") as fh:
        json.dump({"manifiesto": manifiesto, "extraido": extraido,
                   "aceptados": aceptados, "rechazados": rechazados},
                  fh, indent=2, ensure_ascii=False)

    # Dejar en el staging solo lo que sigue pendiente.
    os.remove(EXTRAIDO)
    restantes = [it for it in manifiesto["items"] if it["isin"] not in aceptados]
    if restantes:
        manifiesto["items"] = restantes
        with open(MANIFIESTO, "w", encoding="utf-8") as fh:
            json.dump(manifiesto, fh, indent=2, ensure_ascii=False)
        print(f"\n⚠️  {len(restantes)} fondos siguen en el lote sin aplicar.")
    else:
        os.remove(MANIFIESTO)
        print(f"\n🎉 Lote cerrado. {len(aceptados)} PDFs movidos a pdfs_procesados/.")

    if sync:
        print("\n🔄 Sincronizando SQLite...")
        os.system(f'python "{os.path.join(ROOT_DIR, "skills", "ingest_csv.py")}"')
    else:
        print("\n➡️  Cuando valides el CSV: python skills/ingest_csv.py")


# --- Informe ----------------------------------------------------------------


def cmd_estado():
    asegurar_directorios()
    df = cargar_csv()
    isins = [norm_isin(v) for v in df["ISIN"]]
    pendientes = {norm_isin(os.path.splitext(f)[0])
                  for f in os.listdir(PENDIENTES_DIR) if f.lower().endswith(".pdf")}
    procesados = {norm_isin(os.path.splitext(f)[0].split("__")[0])
                  for f in os.listdir(PROCESADOS_DIR) if f.lower().endswith(".pdf")}

    sin_pdf = [i for i in isins if i not in pendientes and i not in procesados]
    sin_fila = sorted((pendientes | procesados) - set(isins))
    huecos = sum(len(columnas_huecas(f)) for _, f in df.iterrows())
    total = len(df) * len(COLS_ESCRIBIBLES)

    print(f"📊 Filas en el CSV: {len(df)} | PDFs pendientes: {len(pendientes)} | "
          f"procesados: {len(procesados)}")
    print(f"🕳️  Celdas huecas escribibles: {huecos} de {total} "
          f"({100 * huecos / total:.1f}%)")
    print(f"\n✋ ISINs SIN PDF ({len(sin_pdf)}) — a rellenar a mano:")
    for i in sin_pdf:
        print(f"   • {i}")
    if sin_fila:
        print(f"\n➕ PDFs sin fila en el CSV ({len(sin_fila)}) — generarán INSERT:")
        for i in sin_fila:
            print(f"   • {i}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Pipeline PDF -> Golden Record (Feature 002)")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_ext = sub.add_parser("extract", help="Prepara un lote de PDFs en staging")
    p_ext.add_argument("--batch-size", type=int, default=BATCH_SIZE)
    p_app = sub.add_parser("apply", help="Aplica extraido.json al CSV")
    p_app.add_argument("--sync", action="store_true",
                       help="Ejecuta ingest_csv.py al terminar")
    sub.add_parser("estado", help="Informe de cobertura")

    args = parser.parse_args()
    if args.cmd == "extract":
        cmd_extract(args.batch_size)
    elif args.cmd == "apply":
        cmd_apply(args.sync)
    else:
        cmd_estado()
