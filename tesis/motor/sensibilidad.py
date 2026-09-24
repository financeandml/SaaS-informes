"""Sensibilidad WACC × g del escenario base y DCF inverso (05 §8)."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Callable, List, Optional, Tuple

from .escenarios import Valoracion, valorar_escenario

__all__ = ["Matriz", "matriz", "Inverso", "inverso", "biseccion"]


@dataclass
class Matriz:
    waccs: List[float]
    gs: List[float]
    valores: List[List[Optional[float]]]      # [wacc][g]; None donde WACC − g no deja valorar
    base: Tuple[int, int]


def matriz(v: Valoracion, ingresos_base: float, cierre_base, umbrales: dict) -> Matriz:
    b = v.base
    pasos_w = umbrales["sensibilidad"]["wacc_pp"]
    pasos_g = umbrales["sensibilidad"]["g_pp"]
    waccs = [b.wacc + x / 100 for x in pasos_w]
    gs = [b.escenario.g + x / 100 for x in pasos_g]
    valores: List[List[Optional[float]]] = []
    for w in waccs:
        fila = []
        for g in gs:
            e = replace(b.escenario, g=g, wacc_ajuste=w - v.wacc.wacc)
            r = valorar_escenario(e, v.parametros, v.wacc.wacc, v.wacc.ke, ingresos_base, cierre_base, v.puente, None,
                                  dict(umbrales, g_max=1.0), v.dpa_horizonte)
            fila.append(None if w - g <= 0 else r.v0)
        valores.append(fila)
    return Matriz(waccs, gs, valores, (pasos_w.index(0.0), pasos_g.index(0.0)))


def biseccion(f: Callable[[float], float], a: float, b: float, tol: float = 1e-7, iteraciones: int = 200) -> Optional[float]:
    """Raíz de f en [a, b] si cambia de signo; si no, None (se dice que no hay solución en el rango)."""
    fa, fb = f(a), f(b)
    if fa == 0:
        return a
    if fb == 0:
        return b
    if fa * fb > 0:
        return None
    for _ in range(iteraciones):
        m = (a + b) / 2
        fm = f(m)
        if abs(fm) < tol or (b - a) / 2 < tol:
            return m
        if fa * fm < 0:
            b, fb = m, fm
        else:
            a, fa = m, fm
    return (a + b) / 2


@dataclass
class Inverso:
    cagr_ingresos: Optional[float]
    margen_terminal: Optional[float]
    crecimiento_fcff: Optional[float]
    base_cagr: float
    base_margen: float
    rangos: dict


def inverso(v: Valoracion, ingresos_base: float, cierre_base, umbrales: dict) -> Inverso:
    """Qué hay que creer para que el valor por acción del base sea el precio: (a) CAGR de ingresos constante con los
    márgenes del base; (b) margen EBIT del último año con el crecimiento del base; (c) crecimiento constante del FCFF
    desde el FCFF del año 1."""
    b, p, precio = v.base, v.parametros, v.precio
    n = len(b.escenario.crecimiento)
    rangos = umbrales["reverse_rangos"]

    def valor(e) -> float:
        return valorar_escenario(e, p, v.wacc.wacc, v.wacc.ke, ingresos_base, cierre_base, v.puente, None,
                                 dict(umbrales, g_max=1.0), v.dpa_horizonte).v0 - precio

    cagr = biseccion(lambda x: valor(replace(b.escenario, crecimiento=[x] * n)), *rangos["cagr"])
    inicio = b.escenario.margen[0]
    margen = biseccion(lambda x: valor(replace(b.escenario, margen=[inicio + (x - inicio) * (t + 1) / n for t in range(n)])),
                       *rangos["margen"])
    pr = b.proyeccion
    fcff1 = pr.fcff[0]
    w, g = b.wacc, b.escenario.g

    def por_fcff(x: float) -> float:
        flujos = [fcff1 * (1 + x) ** t for t in range(n)]
        va = flujos[0] * pr.fraccion * pr.factores[0] + sum(fl * fa for fl, fa in zip(flujos[1:], pr.factores[1:]))
        vt = flujos[-1] * (1 + g) / (w - g) * (1 + w) ** -(pr.fraccion + n - 1)
        return v.puente.por_accion(va + vt) - precio

    crec = biseccion(por_fcff, *rangos["fcff"])
    base_cagr = (b.proyeccion.ingresos[-1] / ingresos_base) ** (1 / n) - 1
    return Inverso(cagr, margen, crec, base_cagr, b.escenario.margen[-1], rangos)
