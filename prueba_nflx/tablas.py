"""Paso 3 de la prueba: las tablas de los adjuntos, leídas como propuestas.

Un estado financiero en un PDF es texto: una cabecera que dice qué periodo es
cada columna, una línea de escala («in thousands»), y filas con un rótulo y
tantas casillas como columnas. Este módulo reconstruye eso, página a página,
sin saber nada de la SEC: lo que sale de aquí son *candidatos* con su página y
su línea, que después `contraste.py` compara con los hechos XBRL.

Tres decisiones que se fijan aquí y por qué:

**La columna se lee de la cabecera, no del dato.** Sería más fácil averiguar el
periodo de una columna buscando qué hecho de la SEC coincide con su cifra, pero
entonces una columna mal rotulada en el documento pasaría por buena. Cuando la
cabecera no se entiende, la tabla sale con `columnas=None` y se declara.

**Un guion es una casilla vacía, no un cero.** «Acquisitions (17,194) — —»
tiene tres casillas; contar solo los números correría las columnas y le
atribuiría a 2024 la cifra de 2025. Cada casilla es un importe o un hueco.

**El separador se detecta por documento.** El fichero de la web del emisor
llegó con formato español (10.542.801 y 0,68) porque quien lo exportó tenía
esa configuración regional. Un lector que asuma coma de miles leería 10,54.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path
from typing import Optional

AQUI = Path(__file__).resolve().parent
DATOS = AQUI / "datos"
TEXTO = DATOS / "texto"

MESES = {m: i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July",
     "August", "September", "October", "November", "December"], 1)}
MES_RE = "(?:" + "|".join(MESES) + ")"

MARCADORES = [
    # (regex, duración en meses; 0 = instante)
    (r"Three\s+Months\s+Ended", 3),
    (r"Six\s+Months\s+Ended", 6),
    (r"Nine\s+Months\s+Ended", 9),
    (r"Twelve\s+Months(?:\s+Ended)?", 12),
    (r"Years?\s+[Ee]nded", 12),
    (r"As\s+of", 0),
]

TITULOS = [
    ("resultados", r"Statements?\s+of\s+Operations"),
    ("integral", r"Comprehensive\s+Income"),
    ("flujos", r"Statements?\s+of\s+Cash\s+Flows"),
    ("balance", r"Balance\s+Sheets?"),
    ("patrimonio", r"Stockholders.?\s+Equity"),
    ("no_gaap", r"Non-GAAP"),
    ("resumen", r"summary\s+results"),
]


@dataclass
class Columna:
    fin: str                     # fecha de cierre ISO
    meses: int                   # 3, 6, 9, 12 o 0 (instante)
    inicio: Optional[str]        # ISO; None para instantes
    etiqueta: str                # lo que decía la cabecera
    prevision: bool = False      # «Forecast»: objetivo de la compañía, no dato

    @property
    def clave(self) -> str:
        return f"{self.inicio or ''}..{self.fin}" if self.meses else f"@{self.fin}"


@dataclass
class Fila:
    linea: int
    etiqueta: str
    celdas: list                 # float | None (hueco declarado)
    literal: str


@dataclass
class Tabla:
    documento: str
    pagina: int
    tipo: str
    escala: int                  # 1, 1_000 o 1_000_000
    columnas: Optional[list]     # list[Columna] o None si la cabecera no se entendió
    filas: list = field(default_factory=list)
    certeza: str = "alta"
    motivo: str = ""


# ---------------------------------------------------------------------------
# Números
# ---------------------------------------------------------------------------

_NUM_EN = r"\(?-?\$?\s?\d{1,3}(?:,\d{3})*(?:\.\d+)?\)?%?|\(?-?\$?\s?\d+(?:\.\d+)?\)?%?"
_NUM_ES = r"\(?-?\$?\s?\d{1,3}(?:\.\d{3})*(?:,\d+)?\)?%?|\(?-?\$?\s?\d+(?:,\d+)?\)?%?"
HUECO = r"—|–|-(?=\s|$)"


def detectar_locale(texto: str) -> str:
    """«es» si el documento separa miles con punto y decimales con coma."""
    es = len(re.findall(r"\d{1,3}(?:\.\d{3}){2,}", texto))
    en = len(re.findall(r"\d{1,3}(?:,\d{3}){2,}", texto))
    return "es" if es > en else "en"


def a_numero(token: str, loc: str) -> Optional[float]:
    t = token.strip().replace("$", "").replace(" ", "")
    if re.fullmatch(HUECO, t):
        return None
    negativo = t.startswith("(") and t.endswith(")")
    t = t.strip("()")
    pct = t.endswith("%")
    t = t.rstrip("%")
    if loc == "es":
        t = t.replace(".", "").replace(",", ".")
    else:
        t = t.replace(",", "")
    try:
        v = float(t)
    except ValueError:
        return None
    if pct:
        v /= 100
    return -v if negativo else v


def celdas_y_etiqueta(linea: str, loc: str) -> tuple[str, list[str]]:
    """Separa el rótulo de la cola de casillas. Las casillas son los últimos
    tokens numéricos o huecos contiguos; lo que va delante es rótulo."""
    num = _NUM_ES if loc == "es" else _NUM_EN
    tokens = re.findall(rf"{num}|{HUECO}|\S+", linea)
    cola: list[str] = []
    i = len(tokens)
    while i > 0:
        tk = tokens[i - 1]
        if tk == "$":
            i -= 1
            continue
        if re.fullmatch(num, tk) or re.fullmatch(HUECO, tk):
            cola.insert(0, tk)
            i -= 1
        else:
            break
    etiqueta = " ".join(t for t in tokens[:i] if t != "$").strip(" :")
    return etiqueta, cola


# ---------------------------------------------------------------------------
# Cabecera
# ---------------------------------------------------------------------------

def _iso(mes: str, dia: int, anyo: int) -> str:
    return f"{anyo:04d}-{MESES[mes]:02d}-{dia:02d}"


def _inicio(fin: str, meses: int) -> Optional[str]:
    if not meses:
        return None
    f = date.fromisoformat(fin)
    m = f.month - meses + 1
    a = f.year
    while m <= 0:
        m += 12
        a -= 1
    return date(a, m, 1).isoformat()


def _fin_trimestre(q: int, anyo: int) -> str:
    return {1: f"{anyo}-03-31", 2: f"{anyo}-06-30", 3: f"{anyo}-09-30", 4: f"{anyo}-12-31"}[q]


def leer_cabecera(lineas: list[str]) -> tuple[Optional[list], str, str]:
    """Las columnas que declara la cabecera de una página, o None y el motivo."""
    texto = "\n".join(lineas)

    # Caso A: columnas por trimestre rotulado («Q2'25 … Q3'26 Forecast»).
    qs = re.findall(r"Q([1-4])'(\d\d)(\s+Forecast)?", texto)
    if len(qs) >= 3:
        cols = []
        for q, aa, fc in qs:
            fin = _fin_trimestre(int(q), 2000 + int(aa))
            cols.append(Columna(fin, 3, _inicio(fin, 3), f"Q{q}'{aa}" + (" Forecast" if fc else ""), bool(fc)))
        return cols, "alta", "Trimestres rotulados en la cabecera."

    marcadores: list[int] = []
    fechas: list[tuple[str, int]] = []          # (Month, day) en orden
    anyos: list[int] = []
    mes_dia_marcador: Optional[tuple[str, int]] = None
    for l in lineas:
        # En orden de aparición en la línea, no en el orden del catálogo: la
        # cabecera «Twelve Months Ended Six Months Ended» nombra primero el año.
        encontrados = []
        for rx, meses in MARCADORES:
            for m in re.finditer(rx, l):
                encontrados.append((m.start(), meses))
        marcadores += [meses for _, meses in sorted(encontrados)]
        for m in re.finditer(rf"({MES_RE})\s+(\d{{1,2}}),", l):
            fechas.append((m.group(1), int(m.group(2))))
        if re.fullmatch(r"(?:\d{4}\s*)+", l.strip()):
            anyos += [int(a) for a in re.findall(r"\d{4}", l)]
    if not marcadores and not fechas:
        return None, "baja", "Sin marcadores de periodo en la cabecera."

    # Caso B (10-K): el marcador lleva el mes y el día, y los años van en una línea.
    if len(fechas) == 1 and len(anyos) >= 2 and len(marcadores) >= 1:
        mes, dia = fechas[0]
        meses = marcadores[0]
        cols = []
        for a in anyos:
            fin = _iso(mes, dia, a)
            cols.append(Columna(fin, meses, _inicio(fin, meses), f"{mes} {dia}, {a}"))
        return cols, "alta", "Un marcador, una fecha y una fila de años."

    # Caso C: pares (Month D, / año) o una fila de meses y otra de años.
    if len(fechas) >= 2 and len(anyos) == len(fechas):
        finales = [_iso(m, d, a) for (m, d), a in zip(fechas, anyos)]
        cols: list[Columna] = []
        if not marcadores or set(marcadores) == {0}:
            for f, (m, d), a in zip(finales, fechas, anyos):
                cols.append(Columna(f, 0, None, f"{m} {d}, {a}"))
            return cols, "alta", "Cabecera de instantes («As of»)."
        duraciones = [x for x in marcadores if x]
        ascendente = finales == sorted(finales)
        if ascendente:
            # Web del emisor: trimestres consecutivos; una fecha repetida es el
            # acumulado que anuncia el siguiente marcador de la cabecera.
            asignadas = []
            k = 0
            for i, f in enumerate(finales):
                if i > 0 and f == finales[i - 1] and k < len(duraciones):
                    asignadas.append(duraciones[k]); k += 1
                else:
                    asignadas.append(3)
            if k != len(duraciones):
                return None, "baja", "Marcadores acumulados sin fecha repetida a la que asignarlos."
            certeza, motivo = "media", "Columnas ascendentes: los trimestres sin marcador se toman por tres meses."
        else:
            # 10-Q y carta: cada grupo de un marcador va en orden decreciente;
            # cuando la fecha deja de bajar, empieza el grupo del marcador siguiente.
            asignadas = []
            k = 0
            for i, f in enumerate(finales):
                if i > 0 and f >= finales[i - 1]:
                    k += 1
                if k >= len(duraciones):
                    return None, "baja", "Más grupos de columnas que marcadores de periodo."
                asignadas.append(duraciones[k])
            if k != len(duraciones) - 1:
                return None, "baja", "Menos grupos de columnas que marcadores de periodo."
            certeza, motivo = "alta", "Grupos de columnas en orden decreciente, uno por marcador."
        for f, meses, (m, d), a in zip(finales, asignadas, fechas, anyos):
            cols.append(Columna(f, meses, _inicio(f, meses), f"{m} {d}, {a}"))
        return cols, certeza, motivo

    return None, "baja", f"Cabecera no reconocida: {len(marcadores)} marcadores, {len(fechas)} fechas, {len(anyos)} años."


# ---------------------------------------------------------------------------
# Página → tabla
# ---------------------------------------------------------------------------

def leer_pagina(documento: str, pagina: int, texto: str, loc: str) -> Optional[Tabla]:
    lineas = [re.sub(r"\s+", " ", l).strip() for l in texto.splitlines()]
    lineas = [l for l in lineas if l]
    cabeza = "\n".join(lineas[:8])
    tipo = next((t for t, rx in TITULOS if re.search(rx, cabeza, re.I)), None)
    m_escala = re.search(r"\(in\s+(thousands|millions)", texto, re.I)
    if tipo is None and not m_escala:
        return None
    escala = {"thousands": 1_000, "millions": 1_000_000}.get((m_escala.group(1).lower() if m_escala else ""), 1)

    # Cabecera: hasta la primera fila con rótulo y casillas.
    num_cols_min = 2
    fin_cabecera = None
    for i, l in enumerate(lineas):
        et, celdas = celdas_y_etiqueta(l, loc)
        if et and len(celdas) >= num_cols_min and not re.fullmatch(r"(?:\d{4}\s*)+", l) \
                and not re.search(rf"^{MES_RE}\s+\d{{1,2}},", l) and not re.search(r"Q[1-4]'\d\d", l):
            fin_cabecera = i
            break
    if fin_cabecera is None:
        return Tabla(documento, pagina, tipo or "?", escala, None, [], "baja", "Sin filas de datos.")
    columnas, certeza, motivo = leer_cabecera(lineas[:fin_cabecera])

    filas: list[Fila] = []
    pendiente = ""                     # rótulo partido en varias líneas
    n = len(columnas) if columnas else None
    for i, l in enumerate(lineas[fin_cabecera:], fin_cabecera):
        et, celdas = celdas_y_etiqueta(l, loc)
        if not celdas:
            pendiente = (pendiente + " " + l).strip() if pendiente else l
            if len(pendiente) > 400:
                pendiente = l
            continue
        if not et:
            et = pendiente
        elif pendiente and not pendiente.endswith(":") and not re.search(r"\d{4}$", pendiente):
            # Rótulo partido: «Net cash provided by operating» / «activities 2,423 …».
            # Un epígrafe de grupo acaba en dos puntos y no se pega.
            et = pendiente + " " + et
        pendiente = ""
        if n and len(celdas) > n:
            # Un rótulo que acaba en número («Note 9», «…of $33 million») cede
            # sus tokens al rótulo: las casillas son las últimas n.
            et = (et + " " + " ".join(celdas[:-n])).strip()
            celdas = celdas[-n:]
        if n and len(celdas) < n:
            # Fila incompleta: no se adivina en qué columna falta; se declara.
            filas.append(Fila(i + 1, et, [a_numero(c, loc) for c in celdas] + [None] * (n - len(celdas)),
                              l + "   [fila con menos casillas que columnas]"))
            continue
        filas.append(Fila(i + 1, et, [a_numero(c, loc) for c in celdas], l))
    return Tabla(documento, pagina, tipo or "?", escala, columnas, filas, certeza, motivo)


def leer_documento(clave: str) -> list[Tabla]:
    carpeta = TEXTO / clave
    paginas = sorted(carpeta.glob("p*.txt"))
    todo = "\n".join(p.read_text(encoding="utf-8") for p in paginas)
    loc = detectar_locale(todo)
    tablas = []
    for p in paginas:
        num = int(p.stem[1:])
        t = leer_pagina(clave, num, p.read_text(encoding="utf-8"), loc)
        if t and t.filas:
            tablas.append(t)
    return tablas


def main() -> None:
    inventario = json.loads((DATOS / "adjuntos.json").read_text(encoding="utf-8"))
    salida = {}
    for adj in inventario:
        tablas = leer_documento(adj["clave"])
        salida[adj["clave"]] = [asdict(t) for t in tablas]
        con_cols = [t for t in tablas if t.columnas]
        print(f"{adj['clave']:16} páginas con tabla={len(tablas):3}  con cabecera entendida={len(con_cols):3}")
        for t in con_cols:
            if t.tipo in ("resultados", "flujos", "balance", "no_gaap", "integral", "patrimonio"):
                print(f"   p{t.pagina:03d} {t.tipo:11} escala={t.escala:<8} filas={len(t.filas):3} "
                      f"cols={[c.etiqueta + ('/' + str(c.meses) + 'M' if c.meses else '') for c in t.columnas]} [{t.certeza}]")
    (DATOS / "tablas.json").write_text(json.dumps(salida, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
