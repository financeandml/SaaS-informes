"""Puerta de calidad (06 §3) y medidas del render (06 §4).

`revisar(informe, html)` devuelve los bloqueos (impiden emitir) y los avisos (página interna de QA, nunca en el cuerpo).
Lo que es de un apartado se decide punto a punto (`plantillas/puntos.py`, sistema por puntos): entradas y fuentes que
faltan, apartados vacíos, con contenido pendiente o con «N/A» donde no puede haberlo, cuadros que no salen y fechas
«próximas» anteriores al informe; cada bloqueo dice su apartado y su punto. Lo que no es de un apartado conserva su texto:
discrepancias abiertas, bloqueos del motor, índice, texto técnico en el cuerpo y valores únicos (precio, PO, recomendación,
horizonte). `relleno(pdf)` mide lo ocupado de cada página para el aviso de páginas casi vacías.
"""

from __future__ import annotations

import html as html_mod
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from ..plantillas import indice

__all__ = ["Puerta", "revisar", "texto_tecnico", "apartados", "trozos", "visible", "pendiente", "valores_unicos", "relleno",
           "paginas_de", "posicion", "extension"]

# rutas, comandos, etiquetas XBRL (con prefijo o como nombre de concepto: «SellingGeneralAndAdministrativeExpense»),
# nombres de las API, excepciones y mensajes de parser o de red (06 §3.6); las URL se admiten en 37 y 39
_TECNICO = re.compile(r"(?:\b[A-Za-z]:\\|/home/|/tmp/|/Users/|\b\w+\.py\b|python -m|\bus-gaap\b|\bdei:|\bifrs-full:|companyfacts|"
                      r"\bno trae\b|\bpatrón\b|Traceback|\bNone\b|\bnan\b|https?://|\bXBRL\b|\bconfig/|\.yaml\b|\.json\b|"
                      r"\b(?:[A-Z][a-z]+){4,}\b|\b[A-Z]\w*Member\b|\b[A-Z]\w*Error\b|\burlopen\b|\bErrno\b)")
_SIN_NA = frozenset(str(n) for n in indice.sin_na())          # 06 §3.10, de `01_indice.yaml › sin_na`
# Lo que marca contenido pendiente: «Pendiente del analista…», «PENDIENTE», «Texto pendiente de redacción…», «N/A —
# pendiente de la API», un bloque de clase «pendiente» o un elemento que dice solo «pendiente». En minúscula y suelta la
# palabra es también adjetivo de contenido («sin adquisición transformadora pendiente», criterio de la lista del 28;
# «obligaciones de desempeño pendientes»): esa no bloquea.
_PENDIENTE = re.compile(r"\b(?:Pendiente|PENDIENTE)\b|\bpendiente de (?:redacción|la API)\b")
_MARCA_PENDIENTE = re.compile(r'class="[^"]*\bpendiente\b|>\s*pendiente\b', re.I)


@dataclass
class Puerta:
    bloqueos: List[str] = field(default_factory=list)
    avisos: List[str] = field(default_factory=list)
    puntos: Dict[int, list] = field(default_factory=dict)          # apartado → [puntos.Punto] (0: lo que no es de ninguno)

    @property
    def emitible(self) -> bool:
        return not self.bloqueos


def _visible(fragmento: str) -> str:
    """El texto que se lee: sin etiquetas ni atributos (los title del HTML no son cuerpo) y sin gráficos."""
    fragmento = re.sub(r"<(svg|style|script)\b.*?</\1>", " ", fragmento, flags=re.S | re.I)
    return " ".join(html_mod.unescape(re.sub(r"<[^>]+>", " ", fragmento)).split())


visible = _visible                     # para el sistema por puntos, que mira el mismo texto que la puerta


def trozos(html: str) -> Dict[str, str]:
    """Número impreso del apartado → su HTML, de su título al siguiente título de apartado o de parte; «parte-<letra>», lo
    que va del título de una parte a su primer apartado; «portada», la portada. Se corta también en cada <h2: el arranque
    de una parte (la fuente de la parte H, los gráficos de la C) no es del último apartado de la parte anterior."""
    salida: Dict[str, str] = {}
    marcas: List[Tuple[int, str]] = []
    for m in re.finditer(r"<h([23])\b([^>]*)>", html):
        ident = re.search(r'\bid="([^"]+)"', m.group(2))
        ident = ident.group(1) if ident else ""
        if m.group(1) == "3":
            if re.fullmatch(r"ap-\d+", ident):
                marcas.append((m.start(), ident[3:]))
        else:                          # un <h2> sin ancla de parte (hoja 0, índice) corta, pero no es de nadie
            marcas.append((m.start(), ident if ident.startswith("parte-") else ""))
    for k, (inicio, clave) in enumerate(marcas):
        if clave:
            fin = marcas[k + 1][0] if k + 1 < len(marcas) else len(html)
            salida[clave] = salida.get(clave, "") + html[inicio:fin]
    i, j = html.find("PORTADA"), html.find("ÍNDICE")
    if i >= 0 and j > i:
        salida["portada"] = html[i:j]
    return salida


def apartados(html: str) -> Dict[str, str]:
    """Número impreso del apartado → su texto visible; «parte-<letra>», el arranque de cada parte; «portada», la portada."""
    return {clave: _visible(trozo) for clave, trozo in trozos(html).items()}


def pendiente(trozo: str) -> bool:
    """Queda contenido pendiente en este trozo de HTML (ver `_PENDIENTE`)."""
    return bool(_PENDIENTE.search(_visible(trozo)) or _MARCA_PENDIENTE.search(trozo))


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
    from ..fuentes import emisores
    from ..plantillas import puntos
    p = Puerta()
    hoy = hoy or inf.fecha_emision
    # 1, 9 y 10 · punto a punto: lo que el mercado del emisor no publica es «no aplica» y sus faltas no bloquean; el resto
    # bloquea por apartado y punto; lo que no es de ningún apartado, con su texto
    p.puntos = puntos.evaluar(inf, html, emisores.perfil(getattr(inf, "emisor", None)), hoy)
    p.bloqueos += puntos.bloqueos(p.puntos)
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
    portada = trozos(html).get("portada")                                                  # 10 · la portada no es un apartado
    if portada is not None and pendiente(portada):
        p.bloqueos.append("Apartado portada: queda contenido pendiente")
    if portada is not None and re.search(r"\bN/A\b", _visible(portada)):
        p.bloqueos.append("Apartado portada: «N/A» donde no puede haberlo")
    p.bloqueos = list(dict.fromkeys(p.bloqueos))                   # la misma línea dos veces en la hoja 0 es ruido, no dos bloqueos
    p.avisos += list(inf.avisos) + ([f"Rótulo de la bolsa sin traducir: {x}" for x in sorted(_sin_traducir())])
    p.avisos += puntos.cubiertas(p.puntos)
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
