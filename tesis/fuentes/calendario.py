"""La próxima presentación de resultados (apartados 2 y 7), de las fuentes que la publican.

Ningún adjunto ni la SEC anuncian la fecha de los próximos resultados (la compañía no
la deposita). La bolsa la publica en su ficha del valor —como fecha «esperada», según
su proveedor de estimaciones— y el agregador también, con la marca de si es estimada.
El informe imprime la fecha de la bolsa con su calificativo y la cuadra con la del
agregador (regla 9): coinciden o no, y se dice.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import List, Optional, Tuple

from ..datos.hechos import Contraste

__all__ = ["Proxima", "proxima", "Dividendo", "dividendos", "Sorpresa", "sorpresas", "cortos"]

_FECHA_US = re.compile(r"(\d{1,2})/(\d{1,2})/(20\d\d)")
_TRIMESTRE = re.compile(r"Quarter ending ([A-Z][a-z]{2}) (20\d\d)")
_MESES = {"Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6, "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12}


@dataclass
class Proxima:
    fecha: date
    momento: str                         # «tras el cierre» · «antes de la apertura» · ""
    esperada: bool                       # la bolsa la califica de esperada (no confirmada por la compañía)
    trimestre: str                       # «3T26» según la bolsa, o ""
    consenso_bpa: Optional[float]        # lo que la bolsa dice que espera el consenso para ese trimestre
    texto: str                           # la frase literal de la bolsa
    fuente: str
    respuesta: Tuple[str, str, datetime]
    contraste: Contraste = Contraste.SIN_CONTRASTAR
    nota_contraste: str = ""
    estimada: bool = False               # la calcula el algoritmo del proveedor de la bolsa: nadie la ha anunciado


def _leer_nasdaq(ticker: str) -> Optional[Proxima]:
    from .posicionamiento import FUENTE as FUENTE_NASDAQ
    from .precio import pedir_crudo
    url = f"https://api.nasdaq.com/api/analyst/{ticker}/earnings-date"
    try:
        datos, cuerpo, obtenido = pedir_crudo(url)
    except Exception:
        return None
    d = (datos or {}).get("data") or {}
    texto = " ".join(str(d.get("reportText") or "").split())
    m = _FECHA_US.search(texto)
    if not m:
        return None
    fecha = date(int(m.group(3)), int(m.group(1)), int(m.group(2)))
    momento = "tras el cierre" if "after market close" in texto else ("antes de la apertura" if "before market open" in texto else "")
    t = _TRIMESTRE.search(texto)
    trimestre = ""
    if t:
        mes, anio = _MESES[t.group(1)], t.group(2)
        trimestre = f"{(mes - 1) // 3 + 1}T{anio[2:]}"
    c = re.search(r"consensus EPS forecast for the quarter is \$(\d+(?:\.\d+)?)", texto)
    return Proxima(fecha=fecha, momento=momento, esperada="expected" in texto or "estimated" in texto,
                   estimada="estimated" in texto or "algorithm" in texto, trimestre=trimestre,
                   consenso_bpa=float(c.group(1)) if c else None, texto=texto, fuente=FUENTE_NASDAQ, respuesta=(url, cuerpo, obtenido))


def proxima(ticker: str, agregador=None, hoy: Optional[date] = None) -> Optional[Proxima]:
    """La fecha que publica la bolsa, cuadrada con la del agregador si se le pasa su resumen. Con `hoy`, una fecha
    anterior (la bolsa aún no ha pasado página tras la última presentación) no vale: None."""
    p = _leer_nasdaq(ticker)
    if p is None or (hoy is not None and p.fecha < hoy):
        return None
    if agregador is not None and agregador.fecha_resultados is not None:
        if agregador.fecha_resultados == p.fecha:
            p.contraste = Contraste.CONFIRMADO
            p.nota_contraste = (f"el agregador publica la misma fecha ({agregador.fecha_resultados:%d/%m/%Y}"
                                + (", que no marca como estimada)" if agregador.fecha_resultados_estimada is False else ")"))
        else:
            p.contraste = Contraste.DISCREPANTE
            p.nota_contraste = f"el agregador publica otra fecha: {agregador.fecha_resultados:%d/%m/%Y}"
    else:
        p.nota_contraste = "sin segunda fuente con que cuadrarla"
    return p


@dataclass
class Dividendo:
    ex: Optional[date]
    pago: Optional[date]
    declarado: Optional[date]
    importe: Optional[float]
    texto: str


def _fecha_us(texto) -> Optional[date]:
    m = _FECHA_US.search(str(texto or ""))
    return date(int(m.group(3)), int(m.group(1)), int(m.group(2))) if m else None


def dividendos(ticker: str) -> Tuple[List[Dividendo], str]:
    """El historial de dividendos que publica la bolsa (más reciente primero) y la URL consultada.
    Sin filas: la compañía no paga dividendo (no es un hueco)."""
    from .precio import pedir_crudo
    url = f"https://api.nasdaq.com/api/quote/{ticker}/dividends?assetclass=stocks"
    try:
        datos, _, _ = pedir_crudo(url)
    except Exception:
        return [], url
    filas = (((datos or {}).get("data") or {}).get("dividends") or {}).get("rows") or []
    salida = []
    for f in filas:
        importe = re.sub(r"[^\d.]", "", str(f.get("amount") or ""))
        salida.append(Dividendo(ex=_fecha_us(f.get("exOrEffDate")), pago=_fecha_us(f.get("paymentDate")),
                                declarado=_fecha_us(f.get("declarationDate")), importe=float(importe) if importe else None,
                                texto=" · ".join(f"{k}: {v}" for k, v in f.items())))
    return salida, url


_MESES_EN = {m: k for k, m in enumerate(("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"), 1)}


@dataclass
class Sorpresa:
    """Consenso frente a BPA publicado, tal como lo publica la bolsa (01 › 26): su definición de BPA es la suya."""
    mes: Optional[date]                  # primer día del mes en que cierra el trimestre («Jun 2026»)
    publicado: Optional[date]
    consenso: float
    real: float
    sorpresa: Optional[float]            # fracción con signo, la de la bolsa
    texto: str


def sorpresas(ticker: str) -> Tuple[List[Sorpresa], str]:
    """Los últimos trimestres de consenso frente a BPA publicado de la bolsa (más antiguo primero) y la URL consultada."""
    from .precio import pedir_crudo
    url = f"https://api.nasdaq.com/api/company/{ticker}/earnings-surprise"
    try:
        datos, _, _ = pedir_crudo(url)
    except Exception:
        return [], url
    filas = (((datos or {}).get("data") or {}).get("earningsSurpriseTable") or {}).get("rows") or []
    salida = []
    for f in filas:
        try:
            consenso, real = float(f.get("consensusForecast")), float(f.get("eps"))
        except (TypeError, ValueError):
            continue
        try:
            sorpresa = float(f.get("percentageSurprise")) / 100
        except (TypeError, ValueError):
            sorpresa = None
        m = re.match(r"([A-Z][a-z]{2}) (20\d\d)", str(f.get("fiscalQtrEnd") or ""))
        mes = date(int(m.group(2)), _MESES_EN[m.group(1)], 1) if m and m.group(1) in _MESES_EN else None
        salida.append(Sorpresa(mes, _fecha_us(f.get("dateReported")), consenso, real, sorpresa,
                               " · ".join(f"{k}: {v}" for k, v in f.items())))
    salida.sort(key=lambda s: s.mes or date.min)
    return salida, url


def cortos(ticker: str) -> Optional[Tuple[date, float]]:
    """El último interés en corto que publica la bolsa: (fecha de liquidación, acciones en corto); None sin respuesta."""
    from .precio import pedir_crudo
    try:
        datos, _, _ = pedir_crudo(f"https://api.nasdaq.com/api/quote/{ticker}/short-interest?assetclass=stocks")
    except Exception:
        return None
    filas = []
    for f in (((datos or {}).get("data") or {}).get("shortInterestTable") or {}).get("rows") or []:
        dia, interes = _fecha_us(f.get("settlementDate")), re.sub(r"[^\d.]", "", str(f.get("interest") or ""))
        if dia and interes:
            filas.append((dia, float(interes)))
    return max(filas) if filas else None
