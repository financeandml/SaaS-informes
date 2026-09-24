"""Curva par diaria del Tesoro de EE. UU. (03 §7): el bono a 10 años de `fecha_valoracion`, tipo libre de riesgo del WACC.

Una fuente oficial y pública; la respuesta se guarda entera en la misma caché por URL y día que la bolsa.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

__all__ = ["Rf", "rf_10a"]


@dataclass(frozen=True)
class Rf:
    valor: float            # en tanto por uno
    fecha: date             # la del dato (≤ fecha pedida: el último día publicado)
    url: str


def _url(anio: int) -> str:
    return ("https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/"
            f"{anio}/all?type=daily_treasury_yield_curve&field_tdr_date_value={anio}&page&_format=csv")


def rf_10a(fecha: date) -> Optional[Rf]:
    """El «10 Yr» de la curva par en `fecha` o, si ese día no hubo publicación, el último anterior del mismo año."""
    from . import precio
    url = _url(fecha.year)
    try:
        texto = precio.texto_con_cache(url)
    except Exception:
        return None
    mejor = None
    for fila in csv.DictReader(io.StringIO(texto)):
        try:
            dia = datetime.strptime(fila["Date"], "%m/%d/%Y").date()
            valor = float(fila["10 Yr"])
        except (KeyError, ValueError):
            continue
        if dia <= fecha and (mejor is None or dia > mejor[0]):
            mejor = (dia, valor)
    return Rf(mejor[1] / 100, mejor[0], url) if mejor else None
