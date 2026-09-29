"""WACC (05 §5): rf a 10 años de la moneda del emisor (Tesoro de EE. UU. o BCE), beta por regresión frente al mercado de
su bolsa (SPY o el índice de BME del segmento) o bottom-up, Ke por CAPM, Kd del analista o por rating sintético, pesos a
valor de mercado."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple

__all__ = ["Beta", "Wacc", "beta_regresion", "beta_bottom_up", "calcular"]


@dataclass
class Beta:
    bruta: float
    ajustada: float           # Blume: 0,67·β + 0,33
    r2: float
    error: float
    n: int
    desde: date
    hasta: date
    frecuencia: str


def _muestreo(cierres: Dict[date, float], frecuencia: str) -> Dict[Tuple[int, int], Tuple[date, float]]:
    """El último cierre de cada semana ISO (o de cada mes)."""
    salida: Dict[Tuple[int, int], Tuple[date, float]] = {}
    for d in sorted(cierres):
        clave = (d.isocalendar()[0], d.isocalendar()[1]) if frecuencia == "semanal" else (d.year, d.month)
        salida[clave] = (d, cierres[d])
    return salida


def beta_regresion(valor: Dict[date, float], mercado: Dict[date, float], hasta: date, anios: int = 2,
                   frecuencia: str = "semanal", solo_dias_comunes: bool = False) -> Optional[Beta]:
    """`solo_dias_comunes`: el mercado se toma solo en los días en que hay cierre del valor. Para un valor que no cotiza
    todos los días (BME, solo sesiones con negociación), su último cierre de la semana puede ser el martes y el del índice
    el viernes: dos rentabilidades de ventanas distintas, y la beta se atenúa. Así las dos series comparten fechas."""
    desde = date(hasta.year - anios, hasta.month, min(hasta.day, 28))
    v = {d: c for d, c in valor.items() if desde <= d <= hasta}
    m = {d: c for d, c in mercado.items() if desde <= d <= hasta and (not solo_dias_comunes or d in v)}
    mv, mm = _muestreo(v, frecuencia), _muestreo(m, frecuencia)
    claves = sorted(set(mv) & set(mm))
    ry, rx = [], []
    for a, b in zip(claves, claves[1:]):
        ry.append(mv[b][1] / mv[a][1] - 1)
        rx.append(mm[b][1] / mm[a][1] - 1)
    n = len(rx)
    if n < 20:
        return None
    mx, my = sum(rx) / n, sum(ry) / n
    sxx = sum((x - mx) ** 2 for x in rx)
    syy = sum((y - my) ** 2 for y in ry)
    sxy = sum((x - mx) * (y - my) for x, y in zip(rx, ry))
    beta = sxy / sxx
    r2 = sxy * sxy / (sxx * syy) if syy else 0.0
    residuos = sum((y - my - beta * (x - mx)) ** 2 for x, y in zip(rx, ry))
    error = math.sqrt(residuos / (n - 2) / sxx) if n > 2 else float("nan")
    return Beta(beta, 0.67 * beta + 0.33, r2, error, n, mv[claves[0]][0], mv[claves[-1]][0], frecuencia)


def beta_bottom_up(beta_u: float, t: float, deuda: float, fondos_propios: float) -> float:
    return beta_u * (1 + (1 - t) * deuda / fondos_propios)


@dataclass
class Wacc:
    rf: float
    rf_fecha: date
    beta: float
    beta_origen: str
    erp: float
    prima: float
    ke: float
    kd: float
    kd_origen: str
    t: float
    kd_neto: float
    e: float
    d: float
    peso_e: float
    peso_d: float
    wacc: float
    beta_regresion: Optional[Beta] = None
    beta_mensual: Optional[Beta] = None
    avisos: List[str] = field(default_factory=list)
    bloqueos: List[str] = field(default_factory=list)
    # de dónde sale el rf («Tesoro de EE. UU., curva par a 10 años», «BCE, curva al contado AAA…»): el rótulo viaja con la
    # cifra (regla 13), del mismo sitio que la pidió (`emisores.rf`)
    rf_fuente: str = ""


def calcular(rf: float, rf_fecha: date, beta: float, beta_origen: str, erp: float, prima: float, kd: Optional[float],
             kd_origen: str, t: float, e: float, d: float, beta_reg: Optional[Beta] = None,
             beta_mensual: Optional[Beta] = None, r2_min: float = 0.10) -> Wacc:
    bloqueos, avisos = [], []
    ke = rf + beta * erp + prima
    if kd is None:
        bloqueos.append("Kd: sin rendimiento de la deuda del analista ni tabla de rating sintético (la tabla de rating sintético de la configuración)")
        kd = 0.0
    kd_neto = kd * (1 - t)
    peso_e = e / (e + d) if e + d else 1.0
    peso_d = 1 - peso_e
    w = peso_e * ke + peso_d * kd_neto
    if beta_reg is not None and beta_reg.r2 < r2_min:
        avisos.append(f"R² de la regresión {beta_reg.r2:.2f} < {r2_min:.2f}: conviene la beta bottom-up")
    if w <= 0:
        bloqueos.append("WACC ≤ 0")
    return Wacc(rf, rf_fecha, beta, beta_origen, erp, prima, ke, kd, kd_origen, t, kd_neto, e, d, peso_e, peso_d, w,
                beta_reg, beta_mensual, avisos, bloqueos)
