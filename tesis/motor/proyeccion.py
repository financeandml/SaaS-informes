"""Drivers → FCFF año a año (05 §3), con periodo parcial obligatorio y bases imponibles negativas.

Año 0 = hechos verificados (último ejercicio o últimos doce meses). El año 1 es el ejercicio en curso en la fecha de
valoración d: su flujo cuenta × f (f = días de d al cierre del ejercicio 1 / días del ejercicio), porque lo generado
antes de d ya está en el balance del puente.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List

from .supuestos import Escenario

__all__ = ["Proyeccion", "proyectar", "fraccion"]


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


def proyectar(ingresos_base: float, e: Escenario, wacc: float, fecha_valoracion: date, cierre_base: date,
              mitad_de_anio: bool = True, bin_inicial: float = 0.0, sbc_como_coste: bool = True) -> Proyeccion:
    """`cierre_base`: cierre del último ejercicio completo antes de la fecha de valoración (el año 1 acaba un año
    después). Los ejercicios de 52/53 semanas se aproximan al mismo día del año siguiente."""
    n = len(e.crecimiento)
    cierres = [_mas_anios(cierre_base, k) for k in range(1, n + 1)]
    f = fraccion(fecha_valoracion, cierre_base, cierres[0])
    ingresos, ebit, impuestos, nopat, da, capex, dfm, sbc, fcff, ebitda = ([] for _ in range(10))
    paquete = {k: [] for k in e.paquete}
    anterior, bin_ = ingresos_base, bin_inicial
    for t in range(n):
        ing = anterior * (1 + e.crecimiento[t])
        eb = ing * e.margen[t]
        base_imponible = max(0.0, eb - bin_)
        imp = base_imponible * e.impuesto[t]
        bin_ = max(0.0, bin_ - max(eb, 0.0)) + max(-eb, 0.0)
        np_ = eb - imp
        d = ing * e.da[t]
        cx = ing * e.capex[t]
        fm = (ing - anterior) * e.fm
        s = ing * e.sbc[t] if sbc_como_coste else 0.0
        extra = 0.0
        for k, v in e.paquete.items():
            paquete[k].append(ing * v[t])
            extra += ing * v[t]
        flujo = np_ + d - cx - fm - s - extra
        ingresos.append(ing); ebit.append(eb); impuestos.append(imp); nopat.append(np_); da.append(d); capex.append(cx)
        dfm.append(fm); sbc.append(s); fcff.append(flujo); ebitda.append(eb + d)
        anterior = ing
    tiempos = [(f / 2 if mitad_de_anio else f)] + [f + k - (0.5 if mitad_de_anio else 0.0) for k in range(1, n)]
    factores = [(1 + wacc) ** -t for t in tiempos]
    valor_actual = [fcff[0] * f * factores[0]] + [fcff[k] * factores[k] for k in range(1, n)]
    formulas = {
        "ingresos": "Ingresos(t−1) × (1 + g(t))",
        "ebit": "Ingresos × margen EBIT",
        "impuestos": "max(0, EBIT − bases imponibles negativas) × tipo en caja",
        "nopat": "EBIT − impuestos",
        "fcff": "NOPAT + D&A − capex − ΔFM − SBC" + (" − partidas del paquete" if e.paquete else ""),
        "tiempos": ("mitad de año: t1 = f/2; tk = f + (k − 1) − 0,5" if mitad_de_anio else "fin de año: t1 = f; tk = f + k − 1"),
        "factores": "(1 + WACC)^−t",
        "valor_actual": "FCFF × factor (el año 1, además, × f)",
    }
    return Proyeccion(cierres, ingresos, ebit, impuestos, nopat, da, capex, dfm, sbc, paquete, fcff, ebitda, f, tiempos,
                      factores, valor_actual, bin_, formulas)
