"""Comparables del analista (05 §8, 04 paso 5): sus múltiplos LTM con el mismo código que la compañía (contraste,
derivados y `multiplos`), medianas con filtros de antigüedad y moneda y atípicos marcados. La misma lista sirve para 22.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
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
    # cifras del último ejercicio (apartado 22): capitalización, ingresos, crecimiento y margen EBIT
    capitalizacion: Optional[float] = None
    ejercicio: str = ""
    ingresos: Optional[float] = None
    crecimiento: Optional[float] = None
    margen_ebit: Optional[float] = None
    atipicos: List[str] = field(default_factory=list)
    mercado: str = "sec"
    fuente: str = ""                         # de dónde salen sus cuentas y su precio, para el cuadro del apartado 22


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
    from ..fuentes import emisores
    if emisores.es_bme(ticker):
        return _uno_bme(ticker, fecha, umbrales)
    from ..verificacion import contraste
    from ..datos import derivados
    from . import multiplos
    from ..fuentes import precio as precio_mod, sec
    from ..datos.expediente import Expediente
    from ..datos.hechos import Capa, Origen, Periodo, de_valor
    c = Comparable(ticker.upper(), fuente="SEC (companyfacts); cierre oficial de Nasdaq")
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
        c.excluido = c.excluido or "sin cuentas US GAAP en la SEC"
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
            c.motivos["acciones"] = "sin portada vigente en la SEC: diluidas medias del último trimestre"
    p = de_valor("precio", Periodo.instante(c.fecha_precio), c.precio, Capa.SEC, Origen(documento="Nasdaq"), unidad="USD/acción")
    m = multiplos.construir(hechos, per["trimestres"], per["anuales"], p, acciones, None, facts, obtenido, no_aplican=tab.no_aplican)
    if acciones:
        c.capitalizacion = c.precio * acciones
    anuales = sorted(per["anuales"], key=lambda a: a.fin)
    if anuales:
        u = anuales[-1]
        ing, eb = hechos.get(("ingresos", u)), hechos.get(("ebit", u))
        c.ejercicio = u.fin.strftime("%m/%Y")
        if ing is not None and ing.hay_dato:
            c.ingresos = ing.valor
            if eb is not None and eb.hay_dato and ing.valor:
                c.margen_ebit = eb.valor / ing.valor
            if len(anuales) > 1:
                prev = hechos.get(("ingresos", anuales[-2]))
                if prev is not None and prev.hay_dato and prev.valor:
                    c.crecimiento = ing.valor / prev.valor - 1
    for clave, rotulo in MULTIPLOS:
        linea = m.linea(rotulo)
        c.valores[clave] = linea.valor if linea is not None else None
        if linea is not None and linea.valor is None:
            c.motivos[clave] = linea.motivo
    return c


# las cuentas de los comparables de BME: fuera de la copia de trabajo, como la caché de la bolsa (no son adjuntos de
# ningún informe; `adjuntos/` es del emisor del informe)
CACHE_DOCUMENTOS: Optional[Path] = None


def _uno_bme(ticker: str, fecha: date, umbrales: dict) -> Comparable:
    """Un comparable de BME con el mismo código que el emisor del informe: sus cuentas oficiales de la bolsa (las anuales
    de los dos últimos ejercicios y el último semestral publicados hasta `fecha`), contrastadas documento contra documento,
    y el cierre oficial de BME. Precio y cuentas en la misma moneda: sus múltiplos entran en las medianas."""
    from .. import entorno
    from ..datos import derivados, expediente
    from ..fuentes import bme, emisores, precio as precio_mod
    from ..verificacion import contraste
    from . import multiplos
    c = Comparable(ticker.upper(), mercado="bme")
    try:
        e = emisores.emisor_bme(ticker)
    except Exception as ex:                          # la bolsa no respondió: el comparable se dice excluido, no se inventa
        c.excluido = f"BME no respondió: {ex.__class__.__name__}"
        return c
    if e is None:
        c.excluido = "BME no lo encuentra entre sus emisores"
        return c
    c.nombre, c.moneda = e.nombre, e.moneda or "EUR"
    c.fuente = f"cuentas oficiales publicadas en BME; cierre oficial de {e.bolsa}"
    carpeta = (CACHE_DOCUMENTOS or Path(entorno.RAIZ) / "cache_bolsa" / "comparables") / c.ticker
    try:
        bme.traer(e, carpeta, anuales=2, semestrales=1, hoy=fecha, comunicaciones=False)
    except Exception as ex:
        c.excluido = f"BME no sirvió sus cuentas: {ex.__class__.__name__}"
        return c
    rutas = sorted(carpeta.glob("*.pdf"))
    if not rutas:
        c.excluido = "sin cuentas publicadas en BME"
        return c
    exp = expediente.cargar(c.ticker, rutas, None)
    try:
        per = contraste.periodos_del_informe(exp, facts=None, hasta=fecha)
    except ValueError:
        per = {"trimestres": [], "anuales": [], "instantes": []}
    if not per["trimestres"] and not per["anuales"]:
        c.excluido = "sin estados financieros legibles en sus cuentas de BME"
        return c
    mer = precio_mod.mercado(c.ticker, fecha, emisor=e)
    if not mer.precio.hay_dato:
        c.excluido = c.excluido or f"sin cierre oficial de BME: {mer.precio.motivo}"
        return c
    c.precio, c.fecha_precio = mer.precio.valor, mer.precio.periodo.fin
    tab = contraste.contrastar(exp, None, None, per, None)
    hechos = derivados.calcular(tab.hechos(), per["anuales"] + per["trimestres"], per["instantes"])
    try:
        ficha = bme.valor(e.isin)
    except Exception:
        ficha = None
    acciones = ficha.acciones if ficha is not None else None
    if acciones:
        c.capitalizacion = c.precio * acciones
    else:
        c.motivos["acciones"] = "la ficha del valor de BME no publica las acciones admitidas"
    # lo que no se puede leer se dice, y el comparable no entra en las medianas con cifras a medias
    anuales_doc = [a for a in exp.adjuntos if a.tipo is expediente.Tipo.CCAA]
    leidas = {clave for clave, ps in tab.paginas.items() if any(p.estado and p.filas for p in ps)}
    escaneadas = [a for a in anuales_doc if a.clave not in leidas and a.paginas
                  and sum(1 for t in a.paginas if len(t.strip()) < 50) / len(a.paginas) > umbrales["comparables_paginas_sin_texto_max"]]
    if escaneadas:
        c.excluido = c.excluido or (f"{len(escaneadas)} de sus {len(anuales_doc)} cuentas anuales en BME son imágenes escaneadas, "
                                    "sin capa de texto: sin OCR no se leen sus cifras")
    _, individuales = contraste._ambito(exp, tab.paginas)
    if individuales:
        c.excluido = c.excluido or ("solo se leen las cuentas individuales de la sociedad, no las del grupo: sus cifras no "
                                    "son comparables con unas consolidadas")
    if escaneadas or individuales:
        # sin sus cuentas legibles, ninguna cifra suya se imprime: la capitalización es de la bolsa y sí vale
        return c
    # la antigüedad, la del último periodo con ingresos leídos: unas cuentas recientes que no se leen no hacen recientes
    # las cifras de las anteriores
    con_ingresos = [p for p in per["trimestres"] + per["anuales"]
                    if hechos.get(("ingresos", p)) is not None and hechos[("ingresos", p)].hay_dato]
    if not con_ingresos:
        c.excluido = c.excluido or "sin ingresos legibles en sus cuentas de BME"
        return c
    ultimo = max(con_ingresos, key=lambda p: p.fin)
    c.cierre_ltm = ultimo.fin
    meses = (fecha.year - ultimo.fin.year) * 12 + fecha.month - ultimo.fin.month
    if meses > umbrales["comparables_antiguedad_max_meses"]:
        mas_recientes = max(p.fin for p in per["trimestres"] + per["anuales"])
        c.excluido = c.excluido or (f"último periodo con cifras legibles: {ultimo.fin:%m/%Y} (más de {umbrales['comparables_antiguedad_max_meses']} "
                                    "meses)" + (f"; sus cuentas hasta {mas_recientes:%m/%Y} no traen estados que el lector reconozca"
                                                if mas_recientes > ultimo.fin else "") + ": fuera de medianas")
    m = multiplos.construir(hechos, per["trimestres"], per["anuales"], mer.precio, acciones, None, None, None, no_aplican=tab.no_aplican)
    _cifras_del_ejercicio(c, hechos, per["anuales"])
    for clave, rotulo in MULTIPLOS:
        linea = m.linea(rotulo)
        c.valores[clave] = linea.valor if linea is not None else None
        if linea is not None and linea.valor is None:
            c.motivos[clave] = linea.motivo
    return c


def _cifras_del_ejercicio(c: Comparable, hechos, anuales) -> None:
    """Ingresos, crecimiento y margen EBIT del último ejercicio (apartado 22)."""
    anuales = sorted(anuales, key=lambda a: a.fin)
    con_ingresos = [a for a in anuales if hechos.get(("ingresos", a)) is not None and hechos[("ingresos", a)].hay_dato]
    if not con_ingresos:
        return
    u = con_ingresos[-1]
    ing, eb = hechos[("ingresos", u)], hechos.get(("ebit", u))
    c.ejercicio = u.fin.strftime("%m/%Y")
    c.ingresos = ing.valor
    if eb is not None and eb.hay_dato and ing.valor:
        c.margen_ebit = eb.valor / ing.valor
    previos = [a for a in con_ingresos if a.fin < u.fin]
    if previos and hechos[("ingresos", previos[-1])].valor:
        c.crecimiento = ing.valor / hechos[("ingresos", previos[-1])].valor - 1


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
