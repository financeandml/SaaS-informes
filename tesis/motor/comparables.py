"""Comparables del analista (05 §8, 04 paso 5): sus múltiplos LTM con el mismo código que la compañía (contraste,
derivados y `multiplos`), medianas con filtros de antigüedad y moneda y atípicos marcados. La misma lista sirve para 22.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Dict, List, Optional

__all__ = ["Comparable", "Comparables", "construir", "MULTIPLOS"]

MULTIPLOS = (("per", "PER (TTM)"), ("ev_ebitda", "EV / EBITDA (TTM)"), ("ev_ventas", "EV / Ventas (TTM)"), ("p_fcf", "P / FCF (TTM)"))


@dataclass
class Comparable:
    ticker: str
    nombre: str = ""
    justificacion: str = ""
    usar: bool = True
    precio: Optional[float] = None
    fecha_precio: Optional[date] = None
    cierre_ltm: Optional[date] = None
    moneda: str = ""
    valores: Dict[str, Optional[float]] = field(default_factory=dict)
    excluido: str = ""                       # motivo por el que no entra en las medianas
    motivos: Dict[str, str] = field(default_factory=dict)
    atipicos: List[str] = field(default_factory=list)


@dataclass
class Comparables:
    filas: List[Comparable]
    medianas: Dict[str, Optional[float]]
    faltan: Dict[str, str] = field(default_factory=dict)


def _monedas(facts: dict) -> set:
    salida = set()
    for tax in ("us-gaap", "ifrs-full"):
        for c in ("Revenues", "Revenue", "RevenueFromContractWithCustomerExcludingAssessedTax", "NetIncomeLoss", "ProfitLoss"):
            salida |= set(((facts.get("facts", {}).get(tax, {}).get(c) or {}).get("units") or {}).keys())
    return salida


def _uno(ticker: str, fecha: date, umbrales: dict) -> Comparable:
    from .. import contraste, derivados, multiplos, precio as precio_mod, sec
    from ..expediente import Expediente
    from ..hechos import Capa, Origen, Periodo, de_valor
    c = Comparable(ticker.upper())
    try:
        e = sec.emisor(ticker)
    except (RuntimeError, sec.SinContacto) as ex:
        c.excluido = f"EDGAR no respondió: {ex}"
        return c
    if e is None:
        c.excluido = "no presenta ante la SEC"
        return c
    c.nombre = e.nombre
    try:
        facts, obtenido = sec.companyfacts(e.cik)
    except (RuntimeError, sec.SinContacto) as ex:
        c.excluido = f"EDGAR no sirvió sus cuentas: {ex}"
        return c
    monedas = _monedas(facts)
    c.moneda = ", ".join(sorted(monedas)) or "?"
    if "USD" not in monedas:
        c.excluido = f"cuentas en {c.moneda}: fuera de medianas (v1 solo en USD)"
    cierres = precio_mod.cierres_nasdaq(ticker, fecha - timedelta(days=10), fecha, limite=30)
    dias = sorted(d for d in cierres if d <= fecha)
    if dias:
        c.fecha_precio, c.precio = dias[-1], cierres[dias[-1]]
    try:
        per = contraste.periodos_del_informe(Expediente(ticker, []), facts=facts, hasta=fecha)
    except ValueError:
        per = {"trimestres": [], "anuales": [], "instantes": []}
    if not per["trimestres"] and not per["anuales"]:
        c.excluido = c.excluido or "sin cuentas US GAAP en companyfacts"
        return c
    ultimo = max(per["trimestres"] + per["anuales"], key=lambda p: p.fin)
    c.cierre_ltm = ultimo.fin
    meses = (fecha.year - ultimo.fin.year) * 12 + fecha.month - ultimo.fin.month
    if meses > umbrales["comparables_antiguedad_max_meses"]:
        c.excluido = c.excluido or f"cuentas de {ultimo.fin.year} (más de {umbrales['comparables_antiguedad_max_meses']} meses): fuera de medianas"
    if c.precio is None:
        c.excluido = c.excluido or "sin cierre oficial de Nasdaq en la fecha de valoración"
        return c
    tab = contraste.contrastar(Expediente(ticker, []), facts, obtenido, per)
    hechos = derivados.calcular(tab.hechos(), per["anuales"] + per["trimestres"], per["instantes"])
    portada = sec.acciones_portada(facts)
    acciones = portada[0] if portada else None
    if acciones is None and per["trimestres"]:
        h = hechos.get(("acciones_diluidas", max(per["trimestres"], key=lambda q: q.fin)))
        if h is not None and h.hay_dato:
            acciones = h.valor
            c.motivos["acciones"] = "sin portada vigente en companyfacts: diluidas medias del último trimestre"
    p = de_valor("precio", Periodo.instante(c.fecha_precio), c.precio, Capa.SEC, Origen(documento="Nasdaq"), unidad="USD/acción")
    m = multiplos.construir(hechos, per["trimestres"], per["anuales"], p, acciones, None, facts, obtenido, no_aplican=tab.no_aplican)
    for clave, rotulo in MULTIPLOS:
        linea = m.linea(rotulo)
        c.valores[clave] = linea.valor if linea is not None else None
        if linea is not None and linea.valor is None:
            c.motivos[clave] = linea.motivo
    return c


def construir(lista: List[dict], fecha: date, umbrales: dict) -> Comparables:
    filas = []
    for x in lista:
        c = _uno(x["ticker"], fecha, umbrales)
        c.justificacion, c.usar = x.get("justificacion", ""), bool(x.get("usar_en_multiplos", True))
        if not c.usar and not c.excluido:
            c.excluido = "el analista no lo usa en los múltiplos"
        filas.append(c)
    medianas: Dict[str, Optional[float]] = {}
    k = umbrales["atipicos_iqr"]
    for clave, _ in MULTIPLOS:
        valores = [(c, c.valores.get(clave)) for c in filas if not c.excluido and c.valores.get(clave) is not None]
        if clave in ("per", "p_fcf"):
            valores = [(c, v) for c, v in valores if v > 0]             # PER solo con beneficios positivos
        if len(valores) >= 4:
            q1, _, q3 = statistics.quantiles([v for _, v in valores], n=4)
            iqr = q3 - q1
            for c, v in valores:
                if v < q1 - k * iqr or v > q3 + k * iqr:
                    c.atipicos.append(clave)
            valores = [(c, v) for c, v in valores if clave not in c.atipicos]
        medianas[clave] = statistics.median([v for _, v in valores]) if valores else None
    return Comparables(filas, medianas)
