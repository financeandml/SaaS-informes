"""Drivers → FCFF año a año (05 §3), con periodo parcial obligatorio y bases imponibles negativas.

Año 0 = hechos verificados (último ejercicio o últimos doce meses). El año 1 es el ejercicio en curso en la fecha de
valoración d: su flujo cuenta × f (f = días de d al cierre del ejercicio 1 / días del ejercicio), porque lo generado
antes de d ya está en el balance del puente.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Dict, List, Optional, Sequence

from .supuestos import Escenario

__all__ = ["Proyeccion", "proyectar", "fraccion", "siguiente_cierre"]


@dataclass
class Proyeccion:
    cierres: List[date]
    ingresos: List[float]
    ebit: List[float]
    impuestos: List[float]
    nopat: List[float]
    da: List[float]
    capex: List[float]
    dfm: List[float]
    sbc: List[float]
    paquete: Dict[str, List[float]]
    fcff: List[float]
    ebitda: List[float]
    fraccion: float
    tiempos: List[float]
    factores: List[float]
    valor_actual: List[float]              # FCFF × (f en el año 1) × factor
    bin_final: float
    formulas: Dict[str, str] = field(default_factory=dict)
    # parte del FCFF del año 1 que entra en el valor: desde el último balance del puente (`desde`), no desde la
    # valoración; lo generado entre ese balance y la valoración no está en ningún balance todavía (fallo [16])
    fraccion_flujo: float = 1.0
    desde: Optional[date] = None
    sbc_en_acciones: float = 0.0            # dilución: SBC del periodo explícito (importe) que se paga con acciones nuevas

    @property
    def suma_valor_actual(self) -> float:
        return sum(self.valor_actual)


def fraccion(fecha_valoracion: date, cierre_anterior: date, cierre_1: date) -> float:
    """Parte del ejercicio 1 que queda por generar en la fecha de valoración."""
    total = (cierre_1 - cierre_anterior).days
    return max(0.0, min(1.0, (cierre_1 - fecha_valoracion).days / total)) if total > 0 else 0.0


def _mas_anios(d: date, n: int) -> date:
    try:
        return d.replace(year=d.year + n)
    except ValueError:                                   # 29 de febrero
        return d.replace(year=d.year + n, day=28)


def _fin_de_mes_de(d: date) -> date:
    """El fin de mes al que pertenece un cierre por semanas: el que cae en los primeros días de un mes cierra el
    anterior («el domingo más cercano al 31 de agosto» puede ser el 1 o el 3 de septiembre)."""
    if d.day <= 7:
        return d.replace(day=1) - timedelta(days=1)
    return d.replace(day=calendar.monthrange(d.year, d.month)[1])


def _por_semanas(fechas: Sequence[date]) -> bool:
    """Si la compañía cierra por semanas (52/53): entre sus cierres publicados hay 364 o 371 días, nunca 365 o 366.
    Con un solo cierre, lo dice la fecha: un cierre por semanas cae en la última semana del mes o en la primera del
    siguiente, y casi nunca el último día."""
    saltos = [(b - a).days for a, b in zip(fechas, fechas[1:])]
    if saltos:
        return all(s in (364, 371) for s in saltos)
    d = fechas[-1]
    return d.day != calendar.monthrange(d.year, d.month)[1] and (d.day >= 22 or d.day <= 7)


def siguiente_cierre(cierre: date, publicados: Sequence[date] = ()) -> date:
    """El cierre del ejercicio siguiente a `cierre`, con la regla de los cierres que la compañía ya publicó.

    «Mismo día + 1 año» vale para quien cierra en una fecha fija. Quien cierra por semanas —el último sábado de
    septiembre (Apple), el último domingo (Qualcomm), el domingo más cercano a fin de mes— acaba 52 o 53 semanas
    después: Apple cerró el 27/09/2025 y cierra el 26/09/2026, Qualcomm el 28/09/2025 y el 27/09/2026 (fallos [18] y
    [60]). La regla se lee de los cierres publicados: si alguno cayó en los primeros días de un mes, es «el más
    cercano a fin de mes»; si no, «el último del mes».
    """
    fechas = sorted({*publicados, cierre})
    fechas = [d for d in fechas if d <= cierre]
    if not _por_semanas(fechas):
        return _mas_anios(cierre, 1)
    mes = _fin_de_mes_de(cierre).month
    candidatos = [cierre + timedelta(days=364), cierre + timedelta(days=371)]
    distancia = lambda d: (d - _fin_de_mes_de(d)).days                                  # noqa: E731
    del_mes = [d for d in candidatos if _fin_de_mes_de(d).month == mes]
    if any(d.day <= 7 for d in fechas):                                                 # el más cercano a fin de mes
        return min(del_mes, key=lambda d: abs(distancia(d)), default=candidatos[0])
    ultimos = [d for d in del_mes if -6 <= distancia(d) <= 0]                           # el último del mes
    return ultimos[0] if ultimos else candidatos[0]


def proyectar(ingresos_base: float, e: Escenario, wacc: float, fecha_valoracion: date, cierre_base: date,
              mitad_de_anio: bool = True, bin_inicial: float = 0.0, sbc_como_coste: bool = True,
              cierres_publicados: Sequence[date] = (), fecha_balance: Optional[date] = None) -> Proyeccion:
    """`cierre_base`: cierre del último ejercicio completo antes de la fecha de valoración; los siguientes, con la
    regla de `cierres_publicados` (52/53 semanas incluidas). `fecha_balance`: la del balance del puente; el FCFF del
    año 1 cuenta desde ella (entre el cierre base y la valoración), y el descuento, desde la valoración."""
    n = len(e.crecimiento)
    cierres: List[date] = []
    for _ in range(n):
        cierres.append(siguiente_cierre(cierres[-1] if cierres else cierre_base, [*cierres_publicados, *cierres]))
    f = fraccion(fecha_valoracion, cierre_base, cierres[0])
    desde = fecha_balance if fecha_balance is not None and cierre_base <= fecha_balance <= fecha_valoracion else fecha_valoracion
    f_flujo = fraccion(desde, cierre_base, cierres[0])
    ingresos, ebit, impuestos, nopat, da, capex, dfm, sbc, fcff, ebitda = ([] for _ in range(10))
    paquete = {k: [] for k in e.paquete}
    anterior, bin_ = ingresos_base, bin_inicial
    for t in range(n):
        ing = anterior * (1 + e.crecimiento[t])
        # SBC (decisión 1 del analista, 28/09): con «coste de caja» ya está dentro del margen EBIT GAAP y restarla otra
        # vez del FCFF la contaba dos veces [17]: la fila queda informativa. Con «dilución» se suma al EBIT y la pagan
        # las acciones nuevas (`sbc_en_acciones`)
        s = ing * e.sbc[t]
        eb = ing * e.margen[t] + (0.0 if sbc_como_coste else s)
        base_imponible = max(0.0, eb - bin_)
        imp = base_imponible * e.impuesto[t]
        bin_ = max(0.0, bin_ - max(eb, 0.0)) + max(-eb, 0.0)
        np_ = eb - imp
        d = ing * e.da[t]
        cx = ing * e.capex[t]
        fm = (ing - anterior) * e.fm
        extra = 0.0
        for k, v in e.paquete.items():
            paquete[k].append(ing * v[t])
            extra += ing * v[t]
        flujo = np_ + d - cx - fm - extra
        ingresos.append(ing); ebit.append(eb); impuestos.append(imp); nopat.append(np_); da.append(d); capex.append(cx)
        dfm.append(fm); sbc.append(s); fcff.append(flujo); ebitda.append(eb + d)
        anterior = ing
    # mitad de año: el flujo del año 1 se sitúa en el punto medio de su tramo (del balance al cierre), medido desde la
    # valoración: f − f_flujo / 2 (= f / 2 cuando el balance es del día de la valoración)
    tiempos = [(f - f_flujo / 2 if mitad_de_anio else f)] + [f + k - (0.5 if mitad_de_anio else 0.0) for k in range(1, n)]
    factores = [(1 + wacc) ** -t for t in tiempos]
    valor_actual = [fcff[0] * f_flujo * factores[0]] + [fcff[k] * factores[k] for k in range(1, n)]
    # dilución: la SBC del periodo explícito se paga con acciones nuevas al precio de hoy (lo del año 1, desde el balance)
    sbc_en_acciones = 0.0 if sbc_como_coste else sbc[0] * f_flujo + sum(sbc[1:])
    formulas = {
        "ingresos": "Ingresos(t−1) × (1 + g(t))",
        "ebit": "Ingresos × margen EBIT" + ("" if sbc_como_coste else " + SBC (política: dilución)"),
        "impuestos": "max(0, EBIT − bases imponibles negativas) × tipo en caja",
        "nopat": "EBIT − impuestos",
        "fcff": "NOPAT + D&A − capex − ΔFM" + (" − partidas del paquete" if e.paquete else ""),
        "sbc": ("Ingresos × SBC %: informativa, ya dentro del margen EBIT GAAP (política: coste de caja)" if sbc_como_coste
                else "Ingresos × SBC %: sumada al EBIT; se paga con acciones nuevas (política: dilución)"),
        "tiempos": ("mitad de año: t1 = f − f_flujo/2; tk = f + (k − 1) − 0,5" if mitad_de_anio else "fin de año: t1 = f; tk = f + k − 1"),
        "factores": "(1 + WACC)^−t",
        "valor_actual": "FCFF × factor (el año 1, además, × f_flujo: del último balance al cierre)",
    }
    return Proyeccion(cierres, ingresos, ebit, impuestos, nopat, da, capex, dfm, sbc, paquete, fcff, ebitda, f, tiempos,
                      factores, valor_actual, bin_, formulas, f_flujo, desde, sbc_en_acciones)
