"""Accionistas, ejecutivos, retribución, filiales y 13D/13G desde los HTML y XML de EDGAR (apartados 5 y 6; 03 §6).

- DEF 14A: la tabla de propiedad («Beneficial Ownership») y la Summary Compensation Table, elegidas por puntuación
  de cabeceras; la fecha «as of» del texto que las precede viaja con ellas.
- 10-K: ejecutivos (nombre, edad y cargo) de «Information about our Executive Officers».
- Exhibit 21 del índice del 10-K: filiales y jurisdicción.
- Schedule 13G/13D presentados sobre la compañía: el último de cada declarante; vigente si declara ≥ 5 %.

Sin patrones de redacción de un emisor: cabeceras estándar de la SEC y puntuación.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Dict, List, Optional, Sequence, Tuple

from .. import rotulos
from . import tablas_html
from .hechos import Origen

__all__ = ["Declaracion", "Propiedad", "Retribuido", "Directivo", "Filial13", "leer_propiedad", "leer_retribucion",
           "leer_ejecutivos", "leer_filiales", "leer_13g", "vigentes", "fecha_as_of", "clave_nombre"]

_MESES_EN = {m: i for i, m in enumerate(("january", "february", "march", "april", "may", "june", "july", "august",
                                          "september", "october", "november", "december"), 1)}


def fecha_as_of(texto: str) -> Optional[date]:
    """La última fecha «as of <Month> <d>, <yyyy>» de un texto."""
    hallazgos = re.findall(r"(?:as of|within 60 days (?:of|after))\s+([A-Z][a-z]+)\s+(\d{1,2}),\s+(\d{4})", texto)
    for mes, dia, anio in reversed(hallazgos):
        if mes.lower() in _MESES_EN:
            return date(int(anio), _MESES_EN[mes.lower()], int(dia))
    return None


def _sin_notas(texto: str) -> str:
    """Fuera las llamadas a nota («Vanguard Group Inc. (2)», «Salary ($) (3)»)."""
    return " ".join(re.sub(r"\(\s*\d{1,2}\s*\)|\(\s*\$\s*\)|\*+$", " ", texto).split()).strip(" ,")


def clave_nombre(nombre: str) -> str:
    """Nombre normalizado para cruzar la proxy con los 13G («The Vanguard Group» = «VANGUARD GROUP INC»)."""
    t = re.sub(r"[^a-z0-9 ]", " ", nombre.lower())
    fuera = {"the", "inc", "incorporated", "corp", "corporation", "co", "company", "llc", "lp", "ltd", "plc", "group",
             "holdings", "and", "n", "a", "sa", "ag"}
    return " ".join(w for w in t.split() if w not in fuera)


# ---------------------------------------------------------------------------
# Propiedad (DEF 14A)
# ---------------------------------------------------------------------------

@dataclass
class Propiedad:
    nombre: str
    acciones: Optional[float]
    porcentaje: Optional[float]        # None con «*» (menos del 1 %) o sin dato
    menos_de_uno: bool
    es_grupo: bool                     # «All current executive officers and directors as a group»
    fila: str                          # la fila literal (para la cita)


def _nombre_de_titular(celda: str) -> str:
    nombre = _sin_notas(celda)
    # una dirección pegada al nombre empieza por un número de calle: fuera
    m = re.match(r"^(.*?[A-Za-z.,)])\s+\d{1,6}\s+[A-Z]", nombre)
    return (m.group(1) if m else nombre).strip(" ,")


def leer_propiedad(html: str) -> Tuple[List[Propiedad], Optional[date], str]:
    """(filas, fecha «as of», epígrafe) de la tabla de propiedad de la proxy."""
    lista = tablas_html.tablas(html)
    t = tablas_html.buscar(lista, {r"beneficial(ly)? own": 3, r"percent(age)? of (class|outstanding)": 3,
                                  r"number of shares|amount and nature": 2}, 6)
    if t is None:
        return [], None, ""
    filas: List[Propiedad] = []
    for f in t.filas:
        if len(f) < 2 or re.search(r"beneficial owner|number of shares|percent", " ".join(f), re.I):
            continue
        nombre = _nombre_de_titular(f[0])
        if not re.search(r"[A-Za-z]{2}", nombre):
            continue
        cifras = [tablas_html.numero(c) for c in f[1:]]
        acciones = next((v for v, c in zip(cifras, f[1:]) if v is not None and "%" not in c), None)
        pct_celda = next((c for c in reversed(f[1:]) if "%" in c or c.strip() == "*"), None)
        porcentaje = tablas_html.numero(pct_celda) if pct_celda and pct_celda.strip() != "*" else None
        filas.append(Propiedad(nombre=nombre, acciones=acciones, porcentaje=porcentaje,
                               menos_de_uno=bool(pct_celda and pct_celda.strip() == "*"),
                               es_grupo=bool(re.search(r"as a group", nombre, re.I)), fila=" | ".join(f)))
    fecha = fecha_as_of(t.antes)
    return filas, fecha, "Security Ownership of Certain Beneficial Owners and Management"


# ---------------------------------------------------------------------------
# Summary Compensation Table (DEF 14A)
# ---------------------------------------------------------------------------

_COLUMNAS = ((r"salary", "Salario"), (r"bonus", "Bonus"), (r"stock award", "Acciones"), (r"option award", "Opciones"),
             (r"non-?equity incentive", "Incentivo en efectivo"), (r"pension|deferred comp", "Pensiones y diferida"),
             (r"all other", "Otras"), (r"^total", "Total"))
_CARGO = re.compile(r"(?:\b[Cc]o-)?\b(President|Chief|Executive|Senior|Vice|EVP|SVP|General Counsel|Former|Chair|Chairman|Chairwoman|"
                    r"Co-Founder|Founder|Treasurer|Secretary|Controller|Group|Head)\b")


@dataclass
class Retribuido:
    nombre: str
    cargo: str
    anio: int
    cifras: List[Optional[float]]      # en el orden de `columnas`
    total: Optional[float]


def _partir_nombre(celda: str, conocidos: Sequence[str]) -> Tuple[str, str]:
    """«Cristiano R. Amon President and Chief Executive Officer» → (nombre, cargo). Con los nombres de la tabla de
    propiedad si los hay (grafía correcta); si no, por la primera palabra de cargo. Un nombre en mayúsculas se pasa a
    mayúscula inicial."""
    celda = _sin_notas(celda)
    for n in sorted(conocidos, key=len, reverse=True):
        if n and celda.lower().startswith(n.lower()):
            return n, celda[len(n):].strip(" ,")
    m = _CARGO.search(celda)
    nombre, cargo = (celda[:m.start()].strip(" ,"), celda[m.start():].strip()) if m and m.start() > 0 else (celda, "")
    if nombre.isupper():
        nombre = nombre.title()
    return nombre, cargo


def leer_retribucion(html: str, conocidos: Sequence[str] = ()) -> Tuple[List[Retribuido], List[str]]:
    """(filas, columnas en español) de la Summary Compensation Table."""
    lista = tablas_html.tablas(html)
    t = tablas_html.buscar(lista, {r"name and principal position": 4, r"\bsalary\b": 2, r"\btotal\b": 1,
                                  r"stock awards": 1, r"\byear\b": 1}, 7, {r"summary compensation table": 2})
    if t is None:
        return [], []
    cab_i = next((i for i, f in enumerate(t.filas) if re.search(r"salary", " ".join(f), re.I)), None)
    if cab_i is None:
        return [], []
    cabecera = [_sin_notas(c) for c in t.filas[cab_i]]
    numericas = [c for c in cabecera if not re.search(r"name|position|^year$", c, re.I)]
    columnas = []
    for c in numericas:
        columnas.append(next((es for patron, es in _COLUMNAS if re.search(patron, c, re.I)), c))
    salida: List[Retribuido] = []
    actual = ("", "")
    for f in t.filas[cab_i + 1:]:
        if re.fullmatch(r"20\d\d", f[0]):
            anio_i = 0
        elif len(f) > 1 and re.fullmatch(r"20\d\d", f[1]):
            actual = _partir_nombre(f[0], conocidos)
            anio_i = 1
        else:
            continue
        # «(5)» suelto en una columna de cifras es una llamada a nota, no un −5
        cifras = [tablas_html.numero(c) for c in f[anio_i + 1:] if not re.fullmatch(r"\(\d{1,2}\)", c)]
        if len(cifras) != len(columnas) or not actual[0]:
            continue            # fila sin datos de ese año (no era ejecutivo nombrado) o desalineada
        total = cifras[-1] if columnas and columnas[-1] == "Total" else None
        salida.append(Retribuido(nombre=actual[0], cargo=actual[1], anio=int(f[anio_i]), cifras=cifras, total=total))
    return salida, columnas


# ---------------------------------------------------------------------------
# Ejecutivos (10-K)
# ---------------------------------------------------------------------------

@dataclass
class Directivo:
    nombre: str
    edad: Optional[int]
    cargo: str
    femenino: bool = False             # «Ms.»/«Mrs.» en su biografía: el cargo se escribe en femenino


def leer_ejecutivos(html: str) -> Tuple[List[Directivo], Optional[date]]:
    """Tabla «Name | Age | Position» del 10-K (Information about our Executive Officers)."""
    lista = tablas_html.tablas(html)
    t = tablas_html.buscar(lista, {r"\bname\b": 2, r"\bage\b": 3, r"position|title": 2}, 7,
                           {r"executive officers": 2})
    salida: List[Directivo] = []
    if t is not None:
        for f in t.filas:
            if len(f) >= 3 and re.fullmatch(r"\d{2}", f[1]) and not re.search(r"^name$", f[0], re.I):
                salida.append(Directivo(nombre=_sin_notas(f[0]), edad=int(f[1]), cargo=_sin_notas(" ".join(f[2:]))))
        if salida:
            return salida, fecha_as_of(t.antes)
    # sin tabla: párrafos «Nombre, age NN, has served as <cargo> since <fecha>.» tras el epígrafe
    texto = tablas_html.texto_plano(html)
    fecha = None
    for m in re.finditer(r"executive officers[^\n]{0,80}\bages?\b[^\n]*|Information about our Executive Officers[^\n]*", texto, re.I):
        fecha = fecha_as_of(texto[m.start():m.end() + 300])
        for linea in texto[m.end():m.end() + 20000].split("\n"):
            e = re.match(r"^([A-Z][A-Za-z.'’\- ]{3,50}?),\s*(?:age\s*)?(\d{2}),\s*(?:has served|has been|serves|is)\s+(?:as\s+)?(?:our\s+)?(.{3,200}?)"
                         r"(?:\s+(?:and as a member of|since|effective)\b|[.;])", linea.strip())
            if e:
                apellido = e.group(1).split()[-1]
                trato = re.search(rf"\b(Mr|Ms|Mrs|Dr)\.\s+{re.escape(apellido)}\b", linea)
                salida.append(Directivo(nombre=e.group(1).strip(), edad=int(e.group(2)), cargo=e.group(3).strip(" ,."),
                                        femenino=bool(trato and trato.group(1) in ("Ms", "Mrs"))))
        if salida:
            break
    return salida, fecha


# ---------------------------------------------------------------------------
# Exhibit 21
# ---------------------------------------------------------------------------

@dataclass
class Filial13:
    nombre: str
    jurisdiccion: str
    traducida: bool


def leer_filiales(html: str) -> List[Filial13]:
    salida: List[Filial13] = []
    for t in tablas_html.tablas(html):
        col = None                                  # la columna de la jurisdicción, por su cabecera
        for f in t.filas:
            cab = [i for i, c in enumerate(f) if re.search(r"jurisdiction|state or (other )?(country|jurisdiction)|country of", c, re.I)]
            if cab and len(f) > 1:
                col = cab[-1]
                continue
            if len(f) < 2 or re.search(r"^(legal )?name|^subsidiar", f[0], re.I):
                continue
            nombre = _sin_notas(f[0])
            jur = _sin_notas(f[col] if col is not None and col < len(f) else f[-1])
            if not re.search(r"[A-Za-z]{3}", jur) or re.search(r"\d{2,}", jur):
                continue
            texto, ok = rotulos.jurisdiccion(jur)
            salida.append(Filial13(nombre, texto, ok))
    if salida:
        return salida
    for linea in tablas_html.texto_plano(html).split("\n"):
        m = re.match(r"^(.{3,120}?)\s*\(([A-Z][A-Za-z .,&]+)\)\s*$", linea.strip()) or \
            re.match(r"^(.{3,120}?)\s+[—–-]\s+([A-Z][A-Za-z .,&]+)$", linea.strip())
        if m:
            texto, ok = rotulos.jurisdiccion(m.group(2))
            salida.append(Filial13(_sin_notas(m.group(1)), texto, ok))
    return salida


# ---------------------------------------------------------------------------
# Schedule 13G / 13D
# ---------------------------------------------------------------------------

@dataclass
class Declaracion:
    declarante: str
    porcentaje: Optional[float]
    acciones: Optional[float]
    fecha_evento: Optional[date]
    presentado: date
    formulario: str
    url: str


def _xml(etiqueta: str, texto: str) -> Optional[str]:
    m = re.search(rf"<(?:\w+:)?{etiqueta}>\s*([^<]+?)\s*</(?:\w+:)?{etiqueta}>", texto, re.I)
    return m.group(1) if m else None


def _fecha_libre(texto: Optional[str]) -> Optional[date]:
    if not texto:
        return None
    for formato in ("%m/%d/%Y", "%Y-%m-%d", "%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(texto.strip(), formato).date()
        except ValueError:
            continue
    return None


def leer_13g(texto: str, presentado: date, formulario: str, url: str, emisor: str = "") -> Optional[Declaracion]:
    """Un Schedule 13G/13D en XML estructurado (obligatorio desde diciembre de 2024; los anteriores ya los recoge la
    proxy). EDGAR lista también los que presenta la compañía sobre otras: con `emisor`, solo los que son sobre ella."""
    if "<edgarSubmission" in texto or "reportingPersonName" in texto:
        sobre = _xml("issuerName", texto) or ""
        if emisor and clave_nombre(sobre).split()[:1] != clave_nombre(emisor).split()[:1]:
            return None
        nombre = _xml("reportingPersonName", texto)
        pct = _xml("classPercent", texto) or _xml("percentOfClass", texto)
        acciones = _xml("reportingPersonBeneficiallyOwnedAggregateNumberOfShares", texto) or _xml("aggregateAmountOwned", texto)
        evento = _fecha_libre(_xml("eventDateRequiresFilingThisStatement", texto) or _xml("dateOfEvent", texto))
        if nombre is None:
            return None
        return Declaracion(" ".join(nombre.split()), float(pct) if pct else None, float(acciones) if acciones else None,
                           evento, presentado, formulario, url)
    return None


def vigentes(declaraciones: List[Declaracion], umbral: float = 5.0) -> Tuple[List[Declaracion], List[Declaracion]]:
    """(vigentes ≥ umbral, salidas): la última declaración de cada declarante manda."""
    ultima: Dict[str, Declaracion] = {}
    for d in sorted(declaraciones, key=lambda d: d.presentado):
        ultima[clave_nombre(d.declarante)] = d
    dentro = [d for d in ultima.values() if d.porcentaje is not None and d.porcentaje >= umbral]
    fuera = [d for d in ultima.values() if d.porcentaje is not None and d.porcentaje < umbral]
    return sorted(dentro, key=lambda d: -(d.porcentaje or 0)), fuera


def origen(documento: str, formulario: str, presentado: Optional[date], url: str, seccion: str = "") -> Origen:
    return Origen(documento=documento, formulario=formulario, presentado=presentado, referencia=url,
                  concepto=seccion)
