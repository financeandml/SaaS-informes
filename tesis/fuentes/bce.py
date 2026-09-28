"""Curva de tipos del BCE (regla 6: banco central): el tipo libre de riesgo del WACC para emisores en euros.

La curva al contado a 10 años de los bonos soberanos AAA del área del euro (serie YC.B.U2.EUR.4F.G_N_A.SV_C_YM.SR_10Y),
el equivalente en euros del bono a 10 años del Tesoro de EE. UU. (`tesoro.rf_10a`). La respuesta se guarda entera en la
misma caché por URL y día que la bolsa.
"""

from __future__ import annotations

import csv
import io
from datetime import date, datetime, timedelta
from typing import Optional

from .tesoro import Rf

__all__ = ["SERIE", "rf_10a"]

SERIE = "YC/B.U2.EUR.4F.G_N_A.SV_C_YM.SR_10Y"


def _url(desde: date, hasta: date) -> str:
    return (f"https://data-api.ecb.europa.eu/service/data/{SERIE}?startPeriod={desde.isoformat()}"
            f"&endPeriod={hasta.isoformat()}&format=csvdata")


def rf_10a(fecha: date) -> Optional[Rf]:
    """El 10 años de la curva AAA en `fecha` o, si ese día no hubo publicación, el último anterior (hasta 15 días)."""
    from . import precio
    url = _url(fecha - timedelta(days=15), fecha)
    try:
        texto = precio.texto_con_cache(url)
    except Exception:
        return None
    mejor = None
    for fila in csv.DictReader(io.StringIO(texto)):
        try:
            dia = datetime.strptime(fila["TIME_PERIOD"], "%Y-%m-%d").date()
            valor = float(fila["OBS_VALUE"])
        except (KeyError, ValueError, TypeError):
            continue
        if dia <= fecha and (mejor is None or dia > mejor[0]):
            mejor = (dia, valor)
    return Rf(mejor[1] / 100, mejor[0], url) if mejor else None
