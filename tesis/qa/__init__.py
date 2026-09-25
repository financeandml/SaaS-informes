"""Puerta de calidad (06 §3) y medidas del render (06 §4).

`revisar(informe, html)` devuelve los bloqueos (impiden emitir) y los avisos (página interna de QA, nunca en el cuerpo):
entradas y fuentes que faltan, discrepancias abiertas, bloqueos del motor, índice, texto técnico en el cuerpo, apartados
obligatorios vacíos o con «N/A» donde no puede haberlo, valores únicos (precio, PO, recomendación, horizonte) y fechas
«próximas» anteriores al informe. `relleno(pdf)` mide lo ocupado de cada página para el aviso de páginas casi vacías.
"""

from __future__ import annotations

import html as html_mod
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Tuple

__all__ = ["Puerta", "revisar", "texto_tecnico", "apartados", "valores_unicos", "relleno", "paginas_de", "posicion", "extension"]

# rutas, comandos, etiquetas XBRL (con prefijo o como nombre de concepto: «SellingGeneralAndAdministrativeExpense»),
# nombres de las API, excepciones y mensajes de parser o de red (06 §3.6); las URL se admiten en 37 y 39
_TECNICO = re.compile(r"(?:\b[A-Za-z]:\\|/home/|/tmp/|/Users/|\b\w+\.py\b|python -m|\bus-gaap\b|\bdei:|\bifrs-full:|companyfacts|"
                      r"\bno trae\b|\bpatrón\b|Traceback|\bNone\b|\bnan\b|https?://|\bXBRL\b|\bconfig/|\.yaml\b|\.json\b|"
                      r"\b(?:[A-Z][a-z]+){4,}\b|\b[A-Z]\w*Member\b|\b[A-Z]\w*Error\b|\burlopen\b|\bErrno\b)")
_SIN_NA = {"2", "3"} | {str(k) for k in range(12, 21)} | {str(k) for k in range(27, 31)}      # 06 §3.10


@dataclass
class Puerta:
    bloqueos: List[str] = field(default_factory=list)
    avisos: List[str] = field(default_factory=list)

    @property
    def emitible(self) -> bool:
        return not self.bloqueos


def _visible(fragmento: str) -> str:
    """El texto que se lee: sin etiquetas ni atributos (los title del HTML no son cuerpo) y sin gráficos."""
    fragmento = re.sub(r"<(svg|style|script)\b.*?</\1>", " ", fragmento, flags=re.S | re.I)
    return " ".join(html_mod.unescape(re.sub(r"<[^>]+>", " ", fragmento)).split())


def apartados(html: str) -> Dict[str, str]:
    """Número impreso del apartado → su texto visible; «portada», la portada."""
    salida: Dict[str, str] = {}
    marcas = list(re.finditer(r'<h3 id="ap-(\d+)"', html))
    for k, m in enumerate(marcas):
        fin = marcas[k + 1].start() if k + 1 < len(marcas) else len(html)
        salida[m.group(1)] = _visible(html[m.start():fin])
    i, j = html.find("PORTADA"), html.find("ÍNDICE")
    if i >= 0 and j > i:
        salida["portada"] = _visible(html[i:j])
    return salida


def texto_tecnico(html: str) -> List[str]:
    """Los apartados (y la portada) con texto técnico en el cuerpo: «apartado: fragmento»."""
    salida = []
    for clave, texto in apartados(html).items():
        if clave in ("37", "39"):
            continue
        m = _TECNICO.search(texto)
        if m:
            salida.append(f"{clave}: «{texto[max(0, m.start() - 40):m.end() + 40]}»")
    return salida


_DATA_HECHO = re.compile(r'<(td|span|b)\b[^>]*\bdata-hecho="([^"]+)"[^>]*>(.*?)</\1>', re.S)
_NUM_ES = re.compile(r"[−-]?\d{1,3}(?:\.\d{3})+(?:,\d+)?|[−-]?\d+(?:,\d+)?")


def _valor(texto: str):
    """(número, decimales impresos) de la primera cifra es-ES del texto; sin cifra, (texto normalizado, None)."""
    m = _NUM_ES.search(texto)
    if not m:
        return " ".join(re.sub(r"[^\w]+", " ", texto.lower()).split()), None
    entero, _, dec = m.group(0).replace("−", "-").partition(",")
    return float(entero.replace(".", "") + ("." + dec if dec else "")), len(dec)


def valores_unicos(html: str) -> List[str]:
    """06 §3.3: cada concepto marcado con `data-hecho` (precio, po, recomendación, horizonte, deuda neta de una fecha,
    acciones diluidas, capitalización) sale con un solo valor en todo el informe; dos, con el redondeo impreso, lo bloquean."""
    marcas = [(m.start(), m.group(1)) for m in re.finditer(r'<h3 id="ap-(\d+)"', html)]

    def apartado(pos: int) -> str:
        previas = [n for s, n in marcas if s < pos]
        return previas[-1] if previas else "portada"
    grupos: Dict[str, List[Tuple[str, str]]] = {}
    for m in _DATA_HECHO.finditer(html):
        texto = _visible(m.group(3))
        if texto and not texto.startswith("N/A"):
            grupos.setdefault(m.group(2), []).append((texto, apartado(m.start())))
    salida = []
    for clave, lista in grupos.items():
        base, d0 = _valor(lista[0][0])
        for texto, ap in lista[1:]:
            v, d = _valor(texto)
            distinto = v != base if d0 is None or d is None else abs(v - base) > 0.5 * 10 ** -min(d0, d) + 1e-9
            if distinto:
                salida.append(f"«{clave}» sale como «{lista[0][0]}» (apartado {lista[0][1]}) y como «{texto}» (apartado {ap})")
                break
    return salida


def revisar(inf, html: str, hoy: Optional[date] = None) -> Puerta:
    p = Puerta()
    hoy = hoy or inf.fecha_emision
    p.bloqueos += list(inf.faltan)                                                         # 1 · entradas y fuentes
    p.bloqueos += [f"Discrepancia abierta: {d}" for d in inf.discrepancias]                # 2
    pd = getattr(inf, "parte_d", None)
    if pd is not None:
        p.bloqueos += [f"Motor: {b}" for b in pd.bloqueos if f"Motor: {b}" not in p.bloqueos]   # 4
        p.avisos += [f"Motor: {a}" for a in pd.avisos]
        if pd.po is not None and inf.objetivo_portada is not None and abs(inf.objetivo_portada[1] - pd.po) > 0.005:
            p.bloqueos.append("Valor único: el precio objetivo de la portada no es el del motor")       # 3
    pg = getattr(inf, "parte_g", None)
    if pg is not None and pg.recomendacion and inf.recomendacion and pg.recomendacion != inf.recomendacion:
        p.bloqueos.append("Valor único: la recomendación de la portada no es la del analista")
    numeros = sorted(int(x) for x in set(inf.numeros.values()) if str(x).isdigit())
    letras = [x.letra for x in inf.indice]
    if numeros != list(range(1, 40)) or letras != list("ABCDEFGHI"):
        p.bloqueos.append(f"Índice: {len(numeros)} apartados y partes {''.join(letras)} (se piden 39 y A–I)")   # 5
    p.bloqueos += [f"Texto técnico en el cuerpo, apartado {x}" for x in texto_tecnico(html)]              # 6
    p.bloqueos += [f"Valor único: {x}" for x in valores_unicos(html)]                                      # 3
    textos = apartados(html)
    for clave, texto in textos.items():                                                    # 10
        if "Pendiente" in texto:
            p.bloqueos.append(f"Apartado {clave}: queda contenido pendiente")
        if (clave in _SIN_NA or clave == "portada") and re.search(r"\bN/A\b", texto):
            p.bloqueos.append(f"Apartado {clave}: «N/A» donde no puede haberlo")
    for d in re.findall(r"[Pp]róxim\w+[^.]{0,80}?(\d{2}/\d{2}/\d{4})", textos.get("7", "")):             # 9
        dia = date(int(d[6:]), int(d[3:5]), int(d[:2]))
        if dia < hoy:
            p.bloqueos.append(f"Fecha «próxima» anterior al informe: {d}")
    p.avisos += list(inf.avisos) + ([f"Rótulo de la bolsa sin traducir: {x}" for x in sorted(_sin_traducir())])
    if pg is not None:
        p.avisos += list(pg.avisos)
    return p


def _sin_traducir() -> set:
    from ..rotulos import SIN_TRADUCIR_BOLSA
    return set(SIN_TRADUCIR_BOLSA)


def paginas_de(pdf: Path) -> List[str]:
    import pypdfium2 as pdfium
    doc = pdfium.PdfDocument(str(pdf))
    try:
        return [doc[k].get_textpage().get_text_range() for k in range(len(doc))]
    finally:
        doc.close()


def posicion(pdf: Path, texto: str, arriba_mm: float = 20.0, abajo_mm: float = 18.0) -> Optional[Tuple[int, float]]:
    """(página desde 1, fracción del área de contenido desde arriba) de la ÚLTIMA aparición de `texto`: el título de
    un apartado aparece antes en el índice."""
    import pypdfium2 as pdfium
    doc = pdfium.PdfDocument(str(pdf))
    hallado = None
    try:
        for k in range(len(doc)):
            pagina = doc[k]
            tp = pagina.get_textpage()
            buscador = tp.search(texto, match_case=True)
            r = buscador.get_next()
            while r is not None:
                arriba, abajo = pagina.get_height() - arriba_mm / 25.4 * 72, abajo_mm / 25.4 * 72
                hallado = (k + 1, round((arriba - tp.get_charbox(r[0])[3]) / (arriba - abajo), 3))
                r = buscador.get_next()
    finally:
        doc.close()
    return hallado


def extension(pdf: Path, desde: str, hasta: str) -> Optional[float]:
    """Lo que ocupa, en páginas de área de contenido, lo que va de `desde` a `hasta` (06 §4: 38 en una página como máximo)."""
    a, b = posicion(pdf, desde), posicion(pdf, hasta)
    return None if a is None or b is None else round((b[0] - a[0]) + (b[1] - a[1]), 3)


def relleno(pdf: Path, arriba_mm: float = 20.0, abajo_mm: float = 18.0) -> List[Tuple[int, float, bool]]:
    """(página desde 1, fracción ocupada del área de contenido, es fin de parte o de documento). La fracción es la
    distancia de la línea más baja de texto al borde superior del área de contenido, sobre su alto (cabecera y pie
    fuera). Fin de parte: la página siguiente abre una parte («B. …») o no hay siguiente."""
    import pypdfium2 as pdfium
    doc = pdfium.PdfDocument(str(pdf))
    salida = []
    try:
        n = len(doc)
        textos = [doc[k].get_textpage().get_text_range() for k in range(n)]
        for k in range(n):                                   # los márgenes de @page (tesis.css): ahí van cabecera y pie
            pagina = doc[k]
            alto = pagina.get_height()
            tp = pagina.get_textpage()
            arriba, abajo = alto - arriba_mm / 25.4 * 72, abajo_mm / 25.4 * 72
            mas_baja = None
            for r in range(tp.count_rects()):
                x0, y0, x1, y1 = tp.get_rect(r)
                if y0 > arriba - 1 or y1 < abajo + 1:              # cabecera y pie de Chromium
                    continue
                mas_baja = y0 if mas_baja is None else min(mas_baja, y0)
            fraccion = 0.0 if mas_baja is None else (arriba - mas_baja) / (arriba - abajo)
            siguiente = textos[k + 1] if k + 1 < n else ""
            # fin de parte: la siguiente abre una parte, el índice o la portada (la hoja 0 del borrador va sola)
            fin = (k + 1 == n or bool(re.search(r"^\s*[A-I]\. \S", siguiente, re.M)) or "Índice" in siguiente[:200]
                   or "RECOMENDACIÓN" in siguiente[:1500])
            salida.append((k + 1, round(fraccion, 3), fin))
    finally:
        doc.close()
    return salida
