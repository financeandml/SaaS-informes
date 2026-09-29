"""El léxico del mercado del emisor: lo que el informe nombra y que cambia de un mercado a otro.

Moneda, bolsa del precio, de dónde salen las cuentas y de dónde el tipo sin riesgo y el mercado de la beta. Se fija una
sola vez por informe (`fijar`, desde `informe.construir`) con el emisor y el motor, y las plantillas lo piden aquí en vez
de escribir «USD», «Nasdaq» o «la SEC»: una cifra y su rótulo salen del mismo sitio (regla 13), y un informe de una
empresa española no puede decir que su precio es el cierre de Nasdaq.
"""

from __future__ import annotations

__all__ = ["fijar", "moneda", "bolsa", "cuentas", "de_las_cuentas", "rf", "mercado_beta", "es_bme", "negocio"]

_POR_DEFECTO = {"moneda": "USD", "bolsa": "Nasdaq", "cuentas": "SEC EDGAR", "de_las_cuentas": "de la SEC",
                "rf": "Tesoro de EE. UU., curva par a 10 años", "mercado_beta": "SPY", "bme": False,
                "negocio": "Item 1 del 10-K"}
_L = dict(_POR_DEFECTO)


def fijar(emisor=None, motor=None) -> None:
    _L.clear()
    _L.update(_POR_DEFECTO)
    if emisor is not None and getattr(emisor, "mercado", "sec") == "bme":
        _L.update(moneda=getattr(emisor, "moneda", "") or "EUR", bolsa="BME", bme=True,
                  cuentas="cuentas anuales y semestrales publicadas en BME", de_las_cuentas="de las cuentas publicadas",
                  rf="BCE, curva al contado AAA del área del euro a 10 años", mercado_beta="índice de BME del segmento",
                  negocio="cuentas anuales y documento de incorporación")
    if motor is not None:
        _L["moneda"] = getattr(motor, "moneda", "") or _L["moneda"]
        _L["rf"] = getattr(motor, "fuente_rf", "") or _L["rf"]
        _L["mercado_beta"] = getattr(motor, "fuente_beta", "") or _L["mercado_beta"]


def moneda() -> str:
    return _L["moneda"]


def bolsa() -> str:
    return _L["bolsa"]


def cuentas() -> str:
    return _L["cuentas"]


def de_las_cuentas() -> str:
    return _L["de_las_cuentas"]


def rf() -> str:
    return _L["rf"]


def mercado_beta() -> str:
    return _L["mercado_beta"]


def es_bme() -> bool:
    return bool(_L["bme"])


def negocio() -> str:
    return _L["negocio"]
