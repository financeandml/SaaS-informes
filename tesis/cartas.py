"""Las cartas a accionistas de trimestres anteriores, tal como están depositadas en la SEC.

La compañía deposita cada carta como Exhibit 99.1 de un 8-K (Item 2.02, resultados).
Cada carta trae una tabla con los cinco últimos trimestres publicados y una columna
«Forecast» con la previsión de la propia compañía para el trimestre siguiente. Leyendo
las cartas en orden se obtiene, trimestre a trimestre, lo que la compañía previó y lo
que después publicó: la respuesta documental a «¿ha fallado antes?» (apartado 32).

Todo sale de EDGAR con el mismo contacto y la misma caché que el resto (`sec.py`); el
«real» se cuadra con el hecho contrastado del informe cuando el trimestre está en él.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from html.parser import HTMLParser
from typing import Dict, List, Optional, Sequence, Tuple

from . import sec
from .hechos import Contraste, Hecho, Periodo

__all__ = ["Carta", "Guia", "cartas_edgar", "guias_frente_a_real"]

# métrica de la carta → (clave del hecho del informe, escala de la carta a la unidad del hecho, unidad impresa)
METRICAS = {
    "Revenue": ("ingresos", 1e6, "M USD"),
    "Operating Income": ("ebit", 1e6, "M USD"),
    "Operating Margin": ("margen_ebit", 0.01, "%"),
    "Net Income": ("beneficio_neto", 1e6, "M USD"),
    "Diluted EPS": ("bpa_diluido", 1.0, "USD"),
}
_TRIMESTRE = re.compile(r"^Q([1-4])'(\d\d)(\s+Forecast)?$")


@dataclass
class Carta:
    presentado: date
    accession: str
    url: str
    trimestre: str                           # el trimestre que publica («2T26»)
    reales: Dict[Tuple[str, str], float]     # (trimestre, métrica) → valor tal cual en la carta
    prevision: Dict[Tuple[str, str], float]  # (trimestre previsto, métrica) → valor de la columna Forecast
    avisos: List[str] = field(default_factory=list)   # filas de METRICAS que no se han podido leer, con el motivo


@dataclass
class Guia:
    trimestre: str
    metrica: str
    unidad: str
    prevista: float
    real: float
    desvio: Optional[float]                  # fracción (o puntos porcentuales / 100 si la métrica es un margen); None si la previsión es 0
    carta_prevision: Carta
    carta_real: Carta
    contraste: Contraste = Contraste.SIN_CONTRASTAR
    nota: str = ""


class _Tablas(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tablas: List[List[List[str]]] = []
        self._tabla: Optional[list] = None
        self._fila: Optional[list] = None
        self._celda: Optional[list] = None

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self._tabla = []
        elif tag == "tr" and self._tabla is not None:
            self._fila = []
        elif tag in ("td", "th") and self._fila is not None:
            self._celda = []

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._celda is not None:
            texto = " ".join("".join(self._celda).replace("\xa0", " ").split())
            if texto:
                self._fila.append(texto)
            self._celda = None
        elif tag == "tr" and self._fila is not None:
            if self._fila:
                self._tabla.append(self._fila)
            self._fila = None
        elif tag == "table" and self._tabla is not None:
            self.tablas.append(self._tabla)
            self._tabla = None

    def handle_data(self, d):
        if self._celda is not None:
            self._celda.append(d)


def _numero(celda: str) -> Optional[float]:
    """La cifra de una celda («$12,250», «(12)», «$(12)», «7.5%»), o None si no es un número («—», «n/a»)."""
    limpio = celda.replace(",", "").replace("$", "").replace(" ", "")
    m = re.fullmatch(r"(\()?-?(\d+(?:\.\d+)?)\)?%?", limpio)
    if not m:
        return None
    v = float(m.group(2))
    return -v if m.group(1) or limpio.startswith("-") else v


def _numeros(celdas: List[str]) -> List[float]:
    """Las cifras de una fila, saltando lo que no es número."""
    return [v for v in (_numero(c) for c in celdas) if v is not None]


def _splits_unicos(splits: Sequence[Tuple[date, float]]) -> List[Tuple[date, float]]:
    """La SEC registra un mismo split con varias fechas de contexto (el 7:1 de 2015 aparece tres veces): la misma razón a
    menos de 90 días es un solo split, con la primera fecha."""
    salida: List[Tuple[date, float]] = []
    for fecha, factor in sorted(splits, key=lambda s: s[0]):
        if salida and salida[-1][1] == factor and (fecha - salida[-1][0]).days < 90:
            continue
        salida.append((fecha, factor))
    return salida


def _tabla_resumen(html: str) -> Optional[List[List[str]]]:
    p = _Tablas()
    p.feed(html)
    for t in p.tablas:
        if t and any(_TRIMESTRE.match(c) and "Forecast" in c for c in t[0]):
            return t
    return None


def _clave(q: str, anio: str) -> str:
    return f"{q}T{anio}"


def _leer(html: str, presentado: date, accession: str, url: str) -> Optional[Carta]:
    tabla = _tabla_resumen(html)
    if tabla is None:
        return None
    cabecera = tabla[0]
    columnas: List[Tuple[str, bool]] = []
    for c in cabecera:
        m = _TRIMESTRE.match(c)
        if m:
            columnas.append((_clave(m.group(1), m.group(2)), bool(m.group(3))))
    if not columnas:
        return None
    reales: Dict[Tuple[str, str], float] = {}
    prevision: Dict[Tuple[str, str], float] = {}
    avisos: List[str] = []
    for fila in tabla[1:]:
        metrica = fila[0]
        if metrica not in METRICAS:
            continue
        # cada celda va con su columna de cabecera: un «$» o «%» suelto se salta, y una celda no numérica («—», «n/a») deja su
        # hueco en vez de desplazar las siguientes, que haría pasar una previsión por cifra publicada de otro trimestre.
        # La fila puede quedarse sin las últimas columnas solo si son de previsión (caja, acciones no se prevén).
        celdas = [c for c in fila[1:] if c.replace(",", "").strip() not in ("$", "%", "")]
        if len(celdas) > len(columnas) or any(not es_prevision for _, es_prevision in columnas[len(celdas):]):
            avisos.append(f"fila «{metrica}»: {len(celdas)} celdas para {len(columnas)} columnas; no se lee")
            continue
        for (trimestre, es_prevision), c in zip(columnas, celdas):
            v = _numero(c)
            if v is not None:
                (prevision if es_prevision else reales)[(trimestre, metrica)] = v
    publicados = [t for t, p in columnas if not p]
    return Carta(presentado=presentado, accession=accession, url=url, trimestre=publicados[-1] if publicados else "", reales=reales, prevision=prevision, avisos=avisos)


def cartas_edgar(cik: str, maximo: int = 9) -> Tuple[List[Carta], Dict[str, str]]:
    """Las últimas cartas (Ex. 99.1 de los 8-K de resultados) leídas de EDGAR, de la más reciente a la más antigua."""
    faltan: Dict[str, str] = {}
    try:
        s, _ = sec.submissions(cik)
    except Exception as e:
        return [], {"cartas": f"no se pudo leer la lista de depósitos de EDGAR: {e}"}
    r = s["filings"]["recent"]
    ochok = [(date.fromisoformat(r["filingDate"][i]), r["accessionNumber"][i]) for i in range(len(r["form"]))
             if r["form"][i] == "8-K" and "2.02" in (r.get("items", [""] * len(r["form"]))[i] or "")]
    cartas: List[Carta] = []
    for presentado, accession in ochok[:maximo]:
        carpeta = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession.replace('-', '')}"
        try:
            indice, _ = sec._descargar(f"{carpeta}/index.json")
            nombre = next((it["name"] for it in indice["directory"]["item"] if sec.es_anexo_99(it["name"])), None)
            if nombre is None:
                faltan[accession] = "el 8-K no lleva Exhibit 99"
                continue
            html, _ = sec.descargar_texto(f"{carpeta}/{nombre}")
        except Exception as e:
            faltan[accession] = f"EDGAR no sirvió el exhibit: {e}"
            continue
        carta = _leer(html, presentado, accession, f"{carpeta}/{nombre}")
        if carta is None:
            faltan[accession] = "el Exhibit 99 no trae la tabla de resumen con columna «Forecast»"
            continue
        cartas.append(carta)
        if carta.avisos:
            faltan[f"{accession} (filas)"] = "; ".join(carta.avisos)
    return cartas, faltan


def guias_frente_a_real(cartas: List[Carta], hechos: Dict[Tuple[str, Periodo], Hecho],
                        splits: Sequence[Tuple[date, float]] = ()) -> List[Guia]:
    """Cada previsión de una carta frente a lo que la compañía publicó después, en la carta siguiente;
    el «real» se cuadra con el hecho del informe si el trimestre está en él.

    `splits`: (fecha, factor) de cada desdoblamiento registrado en la SEC. Una previsión por acción escrita
    antes de un split y un real publicado después no son comparables sin dividir la previsión por el factor
    (la carta posterior reexpresa los trimestres anteriores; la anterior no podía).
    """
    indice = {(campo, p.clave): h for (campo, p), h in hechos.items() if h.hay_dato}
    por_trimestre_real: Dict[Tuple[str, str], Tuple[float, Carta]] = {}
    for carta in sorted(cartas, key=lambda c: c.presentado):          # la carta más reciente manda si repite un trimestre
        for clave, v in carta.reales.items():
            por_trimestre_real[clave] = (v, carta)
    salida: List[Guia] = []
    for carta in sorted(cartas, key=lambda c: c.presentado):
        for (trimestre, metrica), prevista in carta.prevision.items():
            if (trimestre, metrica) not in por_trimestre_real:
                continue
            real, carta_real = por_trimestre_real[(trimestre, metrica)]
            campo, escala, unidad = METRICAS[metrica]
            nota_split = ""
            if unidad == "USD":
                # las cifras por acción se llevan a la base actual, la de la sección C: cada split posterior a una carta divide su cifra
                for fecha_split, factor in _splits_unicos(splits):
                    if not factor or carta.presentado >= fecha_split:
                        continue
                    prevista = prevista / factor
                    if carta_real.presentado < fecha_split:
                        real = real / factor
                        nota_split = f"previsión y real divididos por el split {factor:g}:1 del {fecha_split:%d/%m/%Y}, posterior a las dos cartas"
                    else:
                        nota_split = f"previsión dividida por el split {factor:g}:1 del {fecha_split:%d/%m/%Y} (la carta que la escribió es anterior)"
            desvio = (real - prevista) / 100 if unidad == "%" else ((real - prevista) / prevista if prevista else None)
            g = Guia(trimestre, metrica, unidad, prevista, real, desvio, carta, carta_real, nota=nota_split)
            h = indice.get((campo, trimestre))
            if h is not None:
                en_carta = h.valor / escala
                tol = 0.005 if unidad == "USD" else (0.05 if unidad == "%" else 0.5)
                if abs(en_carta - real) <= tol:
                    g.contraste, g.nota = Contraste.CONFIRMADO, "; ".join(x for x in (g.nota, "el real de la carta coincide con el hecho contrastado (sección C)") if x)
                else:
                    g.contraste, g.nota = Contraste.DISCREPANTE, "; ".join(x for x in (g.nota, f"la carta dice {real:g} y el hecho contrastado es {en_carta:.2f}") if x)
            else:
                g.nota = "; ".join(x for x in (g.nota, "trimestre fuera del alcance de la sección C: real según la carta siguiente (8-K)") if x)
            salida.append(g)
    salida.sort(key=lambda g: (g.trimestre[2:], g.trimestre[0], list(METRICAS).index(g.metrica)))
    return salida
