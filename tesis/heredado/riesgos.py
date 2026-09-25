"""Riesgos principales (apartado 30): los epígrafes del Item 1A del 10-K, tal cual, con su página.

El 10-K escribe cada riesgo como un epígrafe en negrita seguido de su desarrollo, y
agrupa los epígrafes bajo cabeceras «Risks Related to …». Aquí no se resume ni se
parafrasea: se leen los epígrafes por la fuente con que están compuestos (negrita
frente a redonda, que pdfium expone carácter a carácter) y se imprimen literales
con su página. La única inferencia es la clasificación en las cuatro familias que
pide el índice —regulatorio, financiero, competitivo, ejecución— y va con su motivo
(la cabecera del 10-K o la palabra del epígrafe que la decidió) y su certeza.
"""

from __future__ import annotations

import ctypes
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from ..datos.expediente import Adjunto, Expediente, Tipo
from ..datos.hechos import Certeza, Origen

__all__ = ["Riesgo", "Riesgos", "construir"]

FAMILIAS = ("regulatorio", "financiero", "competitivo", "ejecución")

# cabecera del 10-K → familia, cuando la cabecera basta
_POR_CABECERA = {
    "liquidity": "financiero",
    "stock ownership": "financiero",
    "privacy": "regulatorio",
    "international operations": "regulatorio",
    "intellectual property": "ejecución",
    "information technology": "ejecución",
    "human resources": "ejecución",
}
# palabras del epígrafe → familia, cuando la cabecera es genérica («Our Business»); en orden de prioridad
_POR_PALABRA = (
    (re.compile(r"regulat|law|legal proceeding|government|tax|privacy|net neutrality", re.I), "regulatorio"),
    (re.compile(r"indebtedness|capital|liquidity|stock price|dilution|interest rate|foreign exchange|financial results|fixed cost", re.I), "financiero"),
    (re.compile(r"compet|attract and retain members|pricing|reputation|value to our members|consumer", re.I), "competitivo"),
)


@dataclass
class Riesgo:
    epigrafe: str            # literal del 10-K
    cabecera: str            # «Risks Related to …» bajo la que está
    familia: str             # regulatorio · financiero · competitivo · ejecución
    motivo: str              # qué decidió la familia
    certeza: Certeza
    pagina: int
    origen: Origen
    nota: str = ""           # p. ej. «superado»: un 10-Q posterior dice que la operación a la que se refiere terminó


@dataclass
class Riesgos:
    riesgos: List[Riesgo] = field(default_factory=list)
    documento: Optional[str] = None
    paginas: Tuple[int, int] = (0, 0)      # primera y última página del Item 1A
    faltan: Dict[str, str] = field(default_factory=dict)

    def por_familia(self) -> Dict[str, List[Riesgo]]:
        salida: Dict[str, List[Riesgo]] = {f: [] for f in FAMILIAS}
        for r in self.riesgos:
            salida[r.familia].append(r)
        return salida


# El epígrafe va solo en su línea; en el índice le sigue el número de página («Item 1A. Risk Factors 14»).
_ITEM_1A = re.compile(r"^Item 1A\.\s*Risk Factors\s*$", re.M)


def _lineas_negrita(page) -> List[Tuple[str, bool]]:
    """Las líneas de la página (por altura) con su texto y si están compuestas en negrita.

    Se agrupa por la caja de cada carácter y no por el texto plano, por la misma razón que
    en `extractor`: el texto linealizado no comparte índice con las fuentes ni con las cajas.
    """
    import pypdfium2.raw as pdfium_c
    from ..datos.extractor import _lineas_de
    lineas = _lineas_de(page)     # el texto de cada línea, con los espacios bien puestos
    tp = page.get_textpage()
    n = tp.count_chars()
    buf = ctypes.create_string_buffer(256)
    flags = ctypes.c_int()
    total = [0] * len(lineas)
    negritas = [0] * len(lineas)
    for i in range(n):
        c = chr(pdfium_c.FPDFText_GetUnicode(tp, i))
        if not c.strip():
            continue
        _, y0, _, y1 = tp.get_charbox(i, loose=True)
        yc = (y0 + y1) / 2
        k = next((j for j, l in enumerate(lineas) if l.y0 - 1 <= yc <= l.y1 + 1), None)
        if k is None:
            continue
        pdfium_c.FPDFText_GetFontInfo(tp, i, buf, 256, ctypes.byref(flags))
        total[k] += 1
        negritas[k] += "bold" in buf.value.decode("utf-8", "replace").lower()
    return [(l.texto.strip(), total[k] > 0 and negritas[k] >= 0.8 * total[k]) for k, l in enumerate(lineas)]


def _es_cabecera(texto: str) -> bool:
    """Una cabecera de familia es una línea corta en negrita, sin punto final, que nombra riesgos: «Risks Related to…»
    (Netflix) o «Business and Operational Risks» (Oracle). Sin reconocerla se pega al epígrafe siguiente y el Item 1A
    entero sale como un solo riesgo."""
    if re.match(r"^Risks? (?:Factors )?Related to", texto, re.I):
        return True
    return len(texto.split()) <= 8 and not texto.rstrip().endswith(".") and bool(re.search(r"\bRisks?\b", texto, re.I))


def _epigrafes(page) -> List[Tuple[str, bool]]:
    """Los bloques en negrita de la página: cada uno, o es una cabecera «Risks Related to…» o un epígrafe.

    Un epígrafe puede ocupar varias líneas: se unen las líneas en negrita consecutivas hasta
    la que termina en punto; una cabecera no lleva punto y se cierra sola.
    """
    bloques: List[Tuple[str, bool]] = []
    actual: List[str] = []
    for texto, negrita in _lineas_negrita(page):
        if not negrita:
            if actual:
                bloques.append((" ".join(actual), False))
                actual = []
            continue
        if texto == "Table of Contents":
            continue
        if _es_cabecera(texto):
            if actual:
                bloques.append((" ".join(actual), False))
                actual = []
            bloques.append((texto, True))
            continue
        actual.append(texto)
        if texto.endswith("."):
            bloques.append((" ".join(actual), False))
            actual = []
    if actual:
        bloques.append((" ".join(actual), False))
    return bloques


def _familia(cabecera: str, epigrafe: str) -> Tuple[str, str, Certeza]:
    cab = cabecera.lower()
    for clave, familia in _POR_CABECERA.items():
        if clave in cab:
            return familia, f"cabecera del 10-K «{cabecera}»", Certeza.ALTA
    for patron, familia in _POR_PALABRA:
        m = patron.search(epigrafe)
        if m:
            return familia, f"el epígrafe dice «{m.group(0)}»", Certeza.MEDIA
    return "ejecución", "sin palabra clave: el resto del riesgo de negocio es de ejecución", Certeza.BAJA


def _completar(tramo: str, pagina: str) -> Optional[str]:
    """La frase entera del epígrafe, tal cual la imprime la página: desde donde empieza hasta el primer punto."""
    normal = lambda s: re.sub(r"\s+", " ", s).strip()
    texto, buscado = normal(pagina), normal(tramo)
    i = texto.find(buscado[:60])
    if i < 0:
        return None
    j = texto.find(".", i + len(buscado[:60]))
    return texto[i:j + 1] if 0 < j - i < 600 else None


def construir(exp: Expediente) -> Riesgos:
    import pypdfium2 as pdfium
    r = Riesgos()
    k10 = max(exp.de_tipo(Tipo.K10), key=lambda a: a.periodo_fin or 0, default=None)
    if k10 is None:
        r.faltan["item_1a"] = "sin 10-K en el expediente: no hay Item 1A que leer"
        return r
    r.documento = k10.nombre
    # El epígrafe de verdad va solo en su línea; en el índice le sigue el número de página («Item 1A. Risk Factors 14»).
    # Antes se pedía además que la página empezase por «Table of Contents», que es la cabecera que imprime EDGAR en
    # su HTML y no el PDF que maqueta la compañía: el 10-K de Qualcomm se quedaba sin un solo riesgo.
    inicio = next((i for i, t in enumerate(k10.paginas, 1) if _ITEM_1A.search(t) and len(t) > 1500), None)
    if inicio is None:
        r.faltan["item_1a"] = "el 10-K adjunto no tiene un «Item 1A. Risk Factors» reconocible"
        return r
    fin = next((i for i, t in enumerate(k10.paginas, 1) if i > inicio and re.search(r"^Item 1B\.", t, re.M)), inicio + 15)
    r.paginas = (inicio, fin)
    doc = pdfium.PdfDocument(str(k10.ruta))
    cabecera = "Risks Related to Our Business"
    for numero in range(inicio, fin + 1):
        for tramo, es_cabecera in _epigrafes(doc[numero - 1]):
            if es_cabecera:
                cabecera = tramo
                continue
            if tramo.startswith("Item 1"):
                if numero == fin and tramo.startswith("Item 1B"):
                    break
                continue
            # un epígrafe es una frase completa de al menos cuatro palabras. Hay 10-K en los que la última línea del
            # epígrafe comparte renglón con el comienzo del cuerpo y deja de contar como negrita: la frase se completa
            # con el texto literal de la misma página, nunca con texto de otra parte.
            if len(tramo.split()) < 4:
                continue
            if not tramo.endswith("."):
                tramo = _completar(tramo, k10.paginas[numero - 1])
            if tramo is None or not tramo.endswith("."):
                continue
            familia, motivo, certeza = _familia(cabecera, tramo)
            r.riesgos.append(Riesgo(epigrafe=tramo, cabecera=cabecera, familia=familia, motivo=motivo, certeza=certeza, pagina=numero,
                                    origen=Origen(documento=k10.nombre, formulario="10-K", presentado=k10.fecha, pagina=numero)))
    if not r.riesgos:
        r.faltan["epigrafes"] = f"el Item 1A (págs. {inicio}–{fin}) no tiene epígrafes en negrita reconocibles"
    _superados(exp, r)
    return r


def _superados(exp: Expediente, r: Riesgos) -> None:
    """Un riesgo del 10-K sobre una operación que un 10-Q posterior da por terminada se imprime, pero rotulado como superado."""
    for q in sorted(exp.de_tipo(Tipo.Q10), key=lambda a: a.orden, reverse=True):
        for numero, texto in enumerate(q.paginas, 1):
            m = re.search(r"On (\w+ \d{1,2}, \d{4}), (\w+) provided notice to the Company that it had terminated", texto)
            if m:
                for x in r.riesgos:
                    if m.group(2) in x.epigrafe or m.group(2) in x.cabecera:
                        x.nota = f"superado: el {q.tipo.value} de {q.fecha:%d/%m/%Y} (pág. {numero}) dice que {m.group(2)} terminó el acuerdo el {m.group(1)}"
                return
