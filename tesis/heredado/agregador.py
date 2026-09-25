"""Lo que el agregador (Yahoo Finance) publica del valor y que ni la SEC ni la bolsa publican.

Decisión del analista (18/09/2026): las fuentes son la SEC, Nasdaq y, para completar o
contrastar, Yahoo Finance. De aquí salen solo cifras que ninguna de las dos primeras
da como tales: rentabilidad sobre fondos propios y sobre activos (TTM), deuda total y
caja según el agregador, EV/EBITDA y PEG publicados, y la fecha de resultados que
anuncia. Todo con capa Hd, certeza media, y donde el informe puede calcular lo mismo
con cifras de la SEC lo hace y lo contrasta (regla 9). La respuesta literal se
guarda entera y se pinta como evidencia.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Optional, Tuple

from ..fuentes import yahoo

__all__ = ["Resumen", "resumen", "URL"]

URL = "https://query2.finance.yahoo.com/v10/finance/quoteSummary/{ticker}?modules=financialData,defaultKeyStatistics,calendarEvents"


@dataclass
class Resumen:
    ticker: str
    roe: Optional[float]                  # fracción, TTM
    roa: Optional[float]
    deuda_total: Optional[float]          # USD, «Total Debt» del agregador (incluye arrendamientos: no lo desglosa)
    caja_total: Optional[float]
    ebitda_ttm: Optional[float]
    valor_empresa: Optional[float]
    ev_ebitda: Optional[float]
    peg: Optional[float]                  # PEG del agregador: PER sobre crecimiento esperado a cinco años
    bpa_ttm: Optional[float]
    acciones_circulacion: Optional[float]
    ultimo_trimestre: Optional[date]
    fecha_resultados: Optional[date]
    fecha_resultados_estimada: Optional[bool]
    consenso_bpa_siguiente: Optional[float]
    consenso_ingresos_siguiente: Optional[float]
    moneda: str
    respuesta: Tuple[str, str, datetime]  # (url, cuerpo, obtenido)
    fuente: str = yahoo.FUENTE


def _crudo(d: Optional[dict]) -> Optional[float]:
    if not isinstance(d, dict):
        return None
    v = d.get("raw")
    return float(v) if isinstance(v, (int, float)) else None


def _fecha(d: Optional[dict]) -> Optional[date]:
    v = _crudo(d)
    return datetime.fromtimestamp(v, timezone.utc).date() if v else None


def resumen(ticker: str) -> Optional[Resumen]:
    """Los módulos financialData, defaultKeyStatistics y calendarEvents del agregador, o None si no responde."""
    c = yahoo.cliente()
    url = URL.format(ticker=ticker.upper())
    try:
        datos = c.json(url)
    except Exception:
        return None
    resultados = ((datos.get("quoteSummary") or {}).get("result") or [])
    if not resultados:
        return None
    r = resultados[0]
    fd, ks, ce = r.get("financialData") or {}, r.get("defaultKeyStatistics") or {}, r.get("calendarEvents") or {}
    ganancias = ce.get("earnings") or {}
    fechas = [_fecha(x) for x in (ganancias.get("earningsDate") or [])]
    cuerpo, obtenido = c.crudos[url]
    return Resumen(
        ticker=ticker.upper(), roe=_crudo(fd.get("returnOnEquity")), roa=_crudo(fd.get("returnOnAssets")),
        deuda_total=_crudo(fd.get("totalDebt")), caja_total=_crudo(fd.get("totalCash")), ebitda_ttm=_crudo(fd.get("ebitda")),
        valor_empresa=_crudo(ks.get("enterpriseValue")), ev_ebitda=_crudo(ks.get("enterpriseToEbitda")), peg=_crudo(ks.get("pegRatio")),
        bpa_ttm=_crudo(ks.get("trailingEps")), acciones_circulacion=_crudo(ks.get("sharesOutstanding")),
        ultimo_trimestre=_fecha(ks.get("mostRecentQuarter")),
        fecha_resultados=min([f for f in fechas if f], default=None),
        fecha_resultados_estimada=ganancias.get("isEarningsDateEstimate") if isinstance(ganancias.get("isEarningsDateEstimate"), bool) else None,
        consenso_bpa_siguiente=_crudo(ganancias.get("earningsAverage")), consenso_ingresos_siguiente=_crudo(ganancias.get("revenueAverage")),
        moneda=str(fd.get("financialCurrency") or ""), respuesta=(url, cuerpo, obtenido))
