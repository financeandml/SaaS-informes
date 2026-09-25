"""Item 1A del 10-K de EDGAR (03 §6): los epígrafes de riesgo, literales, con su cabecera («Risks Related to …») y la
página que ve el lector (el folio impreso, como en las citas).

El 10-K compone cada riesgo como un epígrafe con una tipografía propia (negrita, cursiva o ambas) seguido de su
desarrollo en redonda. El estilo de los epígrafes se deduce del propio documento: entre los párrafos del Item 1A que son
frases enteras con un único estilo distinto de la redonda, el más frecuente, prefiriendo la negrita (el resumen de
riesgos que algunos emisores anteponen repite los epígrafes en cursiva). La única inferencia es la familia —regulatorio,
financiero, competitivo, ejecución—, por reglas de `config/riesgos.yaml` y con su motivo y su certeza; el analista la
corrige en `riesgos.familias`.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from functools import lru_cache
from html.parser import HTMLParser
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

from . import tablas_html
from ..entradas import normalizar
from ..rutas import CONFIG

__all__ = ["Epigrafe", "Item1A", "leer", "FAMILIAS", "buscar"]

FAMILIAS = ("regulatorio", "financiero", "competitivo", "ejecucion")
_RUTA = CONFIG / "riesgos.yaml"
_BLOQUES = {"div", "p", "li", "tr", "table", "h1", "h2", "h3", "h4", "h5", "h6"}
_VACIOS = {"br", "hr", "img", "meta", "link", "input", "col", "area", "base", "wbr"}
_INICIO = re.compile(r"^item\s*1a\.?\s*[-–—:]?\s*risk\s*factors\.?$", re.I)
_FIN = re.compile(r"^item\s*(?:1b|1c|2)\b", re.I)


@dataclass
class Bloque:
    texto: str
    estilo: str          # «b», «i», «bi» (uniforme), «» (redonda) o «mixto»
    fisica: int          # página física (índice desde 1, como `tablas_html.paginas`)


@dataclass
class Epigrafe:
    texto: str           # literal del 10-K
    cabecera: str        # «Risks Related to …» bajo la que está («» si el 10-K no agrupa)
    pagina: str          # folio impreso (o índice físico si el documento no numera sus páginas)
    familia: str
    motivo: str
    certeza: str         # alta · media · baja


@dataclass
class Item1A:
    epigrafes: List[Epigrafe] = field(default_factory=list)
    estilo: str = ""
    faltan: Dict[str, str] = field(default_factory=dict)

    def por_familia(self) -> Dict[str, List[Epigrafe]]:
        salida: Dict[str, List[Epigrafe]] = {f: [] for f in FAMILIAS}
        for e in self.epigrafes:
            salida[e.familia].append(e)
        return salida


class _Lector(HTMLParser):
    """Párrafos con el estilo de sus trozos de texto y su página física (mismos saltos que `tablas_html`)."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.bloques: List[Bloque] = []
        self._pila: List[Tuple[str, bool, bool]] = []       # (etiqueta, negrita, cursiva)
        self._trozos: List[Tuple[str, bool, bool]] = []
        self._pagina = 1
        self._div = 0
        self._cortes_div: List[int] = []

    def _cerrar(self) -> None:
        texto = tablas_html.limpiar("".join(t for t, _, _ in self._trozos))
        if texto:
            con_letra = [(n, c) for t, n, c in self._trozos if t.strip()]
            estilos = {("b" if n else "") + ("i" if c else "") for n, c in con_letra}
            self.bloques.append(Bloque(texto, estilos.pop() if len(estilos) == 1 else "mixto", self._pagina))
        self._trozos = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        estilo = "".join((a.get("style") or "").lower().split())
        if tablas_html._SALTO_ANTES.search(estilo):
            self._cerrar()
            self._pagina += 1
        despues = bool(tablas_html._SALTO_DESPUES.search(estilo))
        if tag in _BLOQUES:
            self._cerrar()
        if tag == "div":
            self._div += 1
            if despues:
                self._cortes_div.append(self._div)
                despues = False
        if despues:
            self._cerrar()
            self._pagina += 1
        if tag in _VACIOS:
            return
        negrita, cursiva = self._pila[-1][1:] if self._pila else (False, False)
        negrita = negrita or tag in ("b", "strong") or bool(re.search(r"font-weight:(?:bold|[6-9]00)", estilo))
        if "font-weight:normal" in estilo or "font-weight:400" in estilo:
            negrita = False
        cursiva = cursiva or tag in ("i", "em") or "font-style:italic" in estilo
        if "font-style:normal" in estilo:
            cursiva = False
        self._pila.append((tag, negrita, cursiva))

    def handle_endtag(self, tag):
        if tag in _BLOQUES:
            self._cerrar()
        if tag == "div":
            if self._cortes_div and self._cortes_div[-1] == self._div:
                self._cortes_div.pop()
                self._cerrar()
                self._pagina += 1
            self._div = max(0, self._div - 1)
        for k in range(len(self._pila) - 1, -1, -1):
            if self._pila[k][0] == tag:
                del self._pila[k:]
                break

    def handle_data(self, d):
        negrita, cursiva = self._pila[-1][1:] if self._pila else (False, False)
        self._trozos.append((d, negrita, cursiva))

    def close(self):
        super().close()
        self._cerrar()


@lru_cache(maxsize=1)
def _reglas() -> dict:
    import yaml
    return yaml.safe_load(_RUTA.read_text(encoding="utf-8")) or {}


def _familia(cabecera: str, texto: str) -> Tuple[str, str, str]:
    reglas = _reglas()
    for palabra, familia in (reglas.get("por_cabecera") or {}).items():
        if re.search(r"\b" + re.escape(palabra), cabecera, re.I):
            return familia, f"cabecera del 10-K «{cabecera}»", "alta"
    for familia, palabras in (reglas.get("por_palabra") or {}).items():
        for p in palabras:
            m = re.search(r"\b" + re.escape(p), texto, re.I)
            if m:
                return familia, f"el epígrafe dice «{m.group(0)}»", "media"
    return reglas.get("defecto", "ejecucion"), "sin palabra clave: riesgo de negocio, de ejecución por defecto", "baja"


def _es_cabecera(b: Bloque) -> bool:
    """«RISKS RELATED TO …», «Risks Related to Our Business», «Legal and Regulatory Risks»: corta, en negrita y sin punto."""
    t = b.texto
    if "b" not in b.estilo or len(t) > 150 or t.endswith("."):
        return False
    letras = re.sub(r"[^A-Za-z]", "", t)
    return bool(re.search(r"\brisks?\b", t, re.I)) or (len(letras) > 8 and letras.isupper())


def leer(html: str, correcciones: Sequence[Mapping] = ()) -> Item1A:
    """Los epígrafes del Item 1A de un 10-K. `correcciones`: [{epigrafe: comienzo literal, familia}] del analista."""
    lector = _Lector()
    lector.feed(html)
    lector.close()
    bloques = lector.bloques
    salida = Item1A()
    # la cabecera del Item 1A en el cuerpo (en el índice va con su número de página y no casa)
    inicios = [k for k, b in enumerate(bloques) if _INICIO.match(b.texto) and "b" in b.estilo]
    if not inicios:
        salida.faltan["item_1a"] = "el 10-K no tiene un epígrafe «Item 1A. Risk Factors» reconocible"
        return salida
    ini = inicios[-1] if len(inicios) > 1 and not any(_FIN.match(b.texto) for b in bloques[inicios[0]:inicios[-1]]) else inicios[0]
    fin = next((k for k in range(ini + 1, len(bloques)) if _FIN.match(bloques[k].texto) and "b" in bloques[k].estilo), len(bloques))
    tramo = bloques[ini + 1:fin]
    candidatos = [b for b in tramo if b.estilo in ("b", "i", "bi") and len(b.texto) >= 40 and b.texto.rstrip().endswith((".", ";"))
                  and not _es_cabecera(b)]
    cuenta = Counter(b.estilo for b in candidatos)
    negritas = [e for e, n in cuenta.most_common() if "b" in e and n >= 3]
    salida.estilo = negritas[0] if negritas else (cuenta.most_common(1)[0][0] if cuenta else "")
    if not salida.estilo:
        salida.faltan["epigrafes"] = "el Item 1A no tiene epígrafes con una tipografía propia reconocible"
        return salida
    fol = tablas_html.folios_por_pagina(tablas_html.paginas(html))
    corr = [(normalizar(c.get("epigrafe", ""))[:80], c.get("familia")) for c in correcciones if c.get("epigrafe") and c.get("familia") in FAMILIAS]
    cabecera = ""
    for b in tramo:
        if _es_cabecera(b):
            cabecera = b.texto
            continue
        if b.estilo != salida.estilo or len(b.texto) < 40 or not b.texto.rstrip().endswith((".", ";")):
            continue
        familia, motivo, certeza = _familia(cabecera, b.texto)
        n = normalizar(b.texto)
        for prefijo, fam in corr:
            if n.startswith(prefijo):
                familia, motivo, certeza = fam, "corregida por el analista", "alta"
        pagina = fol[b.fisica - 1] if 0 < b.fisica <= len(fol) else None
        salida.epigrafes.append(Epigrafe(b.texto, cabecera, pagina or "", familia, motivo, certeza))
    if not salida.epigrafes:
        salida.faltan["epigrafes"] = "el Item 1A no tiene epígrafes reconocibles"
    return salida


def buscar(item: Item1A, comienzo: str) -> Optional[Epigrafe]:
    """El epígrafe que empieza por `comienzo` (normalizado): así cita el analista un riesgo del Item 1A."""
    n = normalizar(comienzo)
    return next((e for e in item.epigrafes if n and normalizar(e.texto).startswith(n)), None)
