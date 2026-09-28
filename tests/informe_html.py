"""Lector del HTML emitido para las pruebas: cuadros por título, filas por rótulo y el texto corrido.

Los cuadros se buscan por su título, no por su número: la numeración cambia en cuanto un apartado gana o pierde un
cuadro, y una prueba atada al «Cuadro 14» pasaría a mirar otro sin avisar.
"""

from __future__ import annotations

from html.parser import HTMLParser
from typing import Dict, List, Optional


class _Lector(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.cuadros: Dict[str, List[List[str]]] = {}
        self.titulos: Dict[str, List[List[str]]] = {}      # title="" de cada celda, en paralelo a las filas
        self.texto: List[str] = []
        self._pila: List[str] = []
        self._rotulo: Optional[str] = None
        self._en_rotulo = False
        self._fila: Optional[List[str]] = None
        self._fila_t: Optional[List[str]] = None
        self._celda: Optional[List[str]] = None
        self._saltar = 0

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ("script", "style"):
            self._saltar += 1
        if tag == "div" and "rotulo" in (a.get("class") or "").split():
            self._en_rotulo, self._rotulo = True, ""
        if tag == "tr" and self._rotulo is not None:
            self._fila, self._fila_t = [], []
        if tag in ("td", "th") and self._fila is not None:
            self._celda = []
            self._fila_t.append(a.get("title") or "")

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self._saltar -= 1
        if tag == "div" and self._en_rotulo:
            self._en_rotulo = False
            self.cuadros.setdefault(self._rotulo.strip(), [])
            self.titulos.setdefault(self._rotulo.strip(), [])
        if tag in ("td", "th") and self._celda is not None and self._fila is not None:
            self._fila.append(" ".join("".join(self._celda).split()))
            self._celda = None
        if tag == "tr" and self._fila is not None:
            self.cuadros[self._rotulo.strip()].append(self._fila)
            self.titulos[self._rotulo.strip()].append(self._fila_t)
            self._fila = None
        if tag == "table":
            self._rotulo = None

    def handle_data(self, data):
        if self._saltar:
            return
        if self._en_rotulo:
            self._rotulo += data
        if self._celda is not None:
            self._celda.append(data)
        if data.strip():
            self.texto.append(" ".join(data.split()))


class Informe:
    def __init__(self, html: str):
        lector = _Lector()
        lector.feed(html)
        self.html = html
        self.cuadros = lector.cuadros
        self._titulos = lector.titulos
        self.texto = "\n".join(lector.texto)

    def cuadro(self, titulo: str) -> List[List[str]]:
        """Las filas (cabecera incluida) del primer cuadro cuyo título contiene `titulo`."""
        for rotulo, filas in self.cuadros.items():
            if titulo.lower() in rotulo.lower():
                return filas
        raise KeyError(f"sin cuadro «{titulo}»")

    def fila(self, titulo: str, rotulo: str) -> List[str]:
        """Las celdas de la fila cuyo rótulo (primera celda) empieza por `rotulo`, sin el rótulo."""
        for f in self.cuadro(titulo):
            if f and f[0].lower().startswith(rotulo.lower()):
                return f[1:]
        raise KeyError(f"sin fila «{rotulo}» en «{titulo}»")

    def cabecera(self, titulo: str) -> List[str]:
        return self.cuadro(titulo)[0]

    def celda(self, titulo: str, rotulo: str, columna: str) -> str:
        cab = self.cabecera(titulo)
        return self.fila(titulo, rotulo)[cab.index(columna) - 1]
