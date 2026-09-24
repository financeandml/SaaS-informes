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

__all__ = ["Tabla", "tablas", "texto_plano", "buscar", "numero", "limpiar"]

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

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self._pila.append([])
        elif tag == "tr" and self._pila:
            self._fila = []
        elif tag in ("td", "th") and self._fila is not None:
            self._celda = []
        elif tag in ("br", "p", "div") and self._celda is not None:
            self._celda.append(" ")

    def handle_endtag(self, tag):
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
