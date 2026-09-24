"""Tablas de un HTML de EDGAR (proxy, Exhibit 21, comunicados) con la librería estándar (03 §6).

Cada tabla sale con sus filas de celdas no vacías y el texto que la precede (el epígrafe y la frase «as of …»), que
es lo que la identifica y lo que se cita. Las celdas de relleno de los maquetadores de EDGAR (espacios de ancho cero,
«$» y «%» sueltos) se funden con su cifra. La tabla que se busca se elige por puntuación de cabeceras, nunca por su
posición en el documento.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Dict, List, Optional

__all__ = ["Tabla", "tablas", "texto_plano", "paginas", "folios", "buscar", "numero", "limpiar"]

# saltos de página del HTML de EDGAR: marcan las páginas físicas del documento (las de su PDF)
_SALTO_ANTES = re.compile(r"(?:page-)?break-before:(?:always|page)")
_SALTO_DESPUES = re.compile(r"(?:page-)?break-after:(?:always|page)")
_FOLIO = re.compile(r"(?:[A-Z]{1,2}-)?(?:\d{1,3}|[ivx]{1,5})")

_INVISIBLES = dict.fromkeys(map(ord, "​‌‍﻿"), None)


def limpiar(texto: str) -> str:
    return " ".join(texto.translate(_INVISIBLES).replace("\xa0", " ").split())


@dataclass
class Tabla:
    indice: int
    filas: List[List[str]]
    antes: str                 # hasta 1.500 caracteres de texto justo antes de la tabla

    @property
    def cabecera(self) -> str:
        return " ".join(" ".join(f) for f in self.filas[:3])


class _Lector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tablas: List[Tabla] = []
        self._pila: List[list] = []            # tablas anidadas: se aplanan en la de fuera
        self._fila: Optional[list] = None
        self._celda: Optional[list] = None
        self._fuera: List[str] = []
        self.texto: List[str] = []
        self._div = 0
        self._cortes_div: List[int] = []        # profundidad de los div con salto de página detrás

    def handle_starttag(self, tag, attrs):
        estilo = "".join((dict(attrs).get("style") or "").lower().split())
        if _SALTO_ANTES.search(estilo):
            self.texto.append("\f")
        despues = bool(_SALTO_DESPUES.search(estilo))
        if tag == "div":
            self._div += 1
            if despues:
                self._cortes_div.append(self._div)
                despues = False
        if despues:
            self.texto.append("\f")
        if tag == "table":
            self._pila.append([])
        elif tag == "tr" and self._pila:
            self._fila = []
        elif tag in ("td", "th") and self._fila is not None:
            self._celda = []
        elif tag in ("br", "p", "div") and self._celda is not None:
            self._celda.append(" ")

    def handle_endtag(self, tag):
        if tag == "div":
            if self._cortes_div and self._cortes_div[-1] == self._div:
                self._cortes_div.pop()
                self.texto.append("\f")
            self._div = max(0, self._div - 1)
        if tag in ("td", "th"):
            self.texto.append(" ")          # en el texto plano, las celdas de una fila no se pegan
        if tag in ("td", "th") and self._celda is not None and self._fila is not None:
            self._fila.append(limpiar("".join(self._celda)))
            self._celda = None
        elif tag == "tr" and self._fila is not None and self._pila:
            fila = _fundir(self._fila)
            if fila:
                self._pila[-1].append(fila)
            self._fila = None
        elif tag == "table" and self._pila:
            filas = self._pila.pop()
            if self._pila:
                self._pila[-1].extend(filas)
            elif filas:
                antes = limpiar(" ".join(self._fuera))[-1500:]
                self.tablas.append(Tabla(len(self.tablas), filas, antes))
                self._fuera = []
        if tag in ("p", "div", "tr", "li", "h1", "h2", "h3", "h4", "table"):
            self.texto.append("\n")

    def handle_data(self, d):
        self.texto.append(d)
        if self._celda is not None:
            self._celda.append(d)
        elif not self._pila:
            self._fuera.append(d)
            if len(self._fuera) > 1200:
                self._fuera = self._fuera[-600:]


def _fundir(celdas: List[str]) -> List[str]:
    """«$» + «1,350,000» → «$1,350,000»; «10.53» + «%» → «10.53%»; «(» «12» «)» → «(12)». Fuera las vacías."""
    salida: List[str] = []
    pendiente = ""
    for c in celdas:
        if not c:
            continue
        if c in ("$", "(", "$(", "US$"):
            pendiente += c
            continue
        if c in ("%", ")", ")%", "%)") and salida:
            salida[-1] += c
            continue
        salida.append(pendiente + c)
        pendiente = ""
    return salida


def tablas(html: str) -> List[Tabla]:
    lector = _Lector()
    lector.feed(html)
    return lector.tablas


def texto_plano(html: str) -> str:
    """El documento en texto, con saltos de párrafo (para buscar epígrafes y proponer citas)."""
    lector = _Lector()
    lector.feed(html)
    lineas = (limpiar(l) for l in "".join(lector.texto).split("\n"))
    return "\n".join(l for l in lineas if l)


def paginas(html: str) -> List[str]:
    """El documento en texto, página a página (índice físico desde 1 = posición en la lista + 1), según los saltos de
    página del HTML. Sin saltos, una sola página."""
    lector = _Lector()
    lector.feed(html)
    trozos = "".join(lector.texto).split("\f")
    salida = ["\n".join(l for l in (limpiar(x) for x in t.split("\n")) if l) for t in trozos]
    while len(salida) > 1 and not salida[-1]:
        salida.pop()
    return salida


def folios(lista: List[str]) -> Dict[str, str]:
    """Página → texto, con la página que ve el lector: el folio impreso al pie (una de las tres últimas líneas: «28»,
    «F-12», «ii»). Si lo lleva menos de la mitad de las páginas o los folios no crecen, el índice físico («1», «2»…).
    Las páginas sin folio (portada, índice) solo están en el texto completo del documento."""
    hallados = []
    for t in lista:
        hallados.append(next((l for l in reversed(t.split("\n")[-3:]) if _FOLIO.fullmatch(l)), None))
    numeros = [int(f) for f in hallados if f and f.isdigit()]
    if sum(1 for f in hallados if f) * 2 < len(lista) or numeros != sorted(numeros):
        return {str(k): t for k, t in enumerate(lista, 1)}
    salida: Dict[str, str] = {}
    for f, t in zip(hallados, lista):
        if f:
            salida[f] = f"{salida[f]}\n{t}" if f in salida else t
    return salida


def buscar(lista: List[Tabla], pesos: Dict[str, float], minimo: float, en_antes: Optional[Dict[str, float]] = None) -> Optional[Tabla]:
    """La tabla con más puntuación: suma del peso de cada patrón que aparece en su cabecera (y en el texto de antes)."""
    mejor, puntos_mejor = None, 0.0
    for t in lista:
        puntos = sum(p for patron, p in pesos.items() if re.search(patron, t.cabecera, re.I))
        puntos += sum(p for patron, p in (en_antes or {}).items() if re.search(patron, t.antes, re.I))
        if puntos > puntos_mejor:
            mejor, puntos_mejor = t, puntos
    return mejor if puntos_mejor >= minimo else None


def numero(celda: str) -> Optional[float]:
    """«$1,350,000», «(12)», «10.53%», «—» → cifra; «—» es cero declarado (convención de las tablas de la SEC).
    Lo que no es cifra (un «*», un nombre) → None."""
    t = celda.replace("$", "").replace(",", "").replace(" ", "").replace("US", "")
    if t in ("—", "–", "-", "— %", "—%"):
        return 0.0
    m = re.fullmatch(r"(\()?(-?\d+(?:\.\d+)?)\)?%?(?:\(\d+\))?", t)
    if not m:
        return None
    v = float(m.group(2))
    return -abs(v) if m.group(1) else v
