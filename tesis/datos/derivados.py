"""Los derivados: márgenes, deuda neta, FCF, rentabilidades. Cada uno con su fórmula y sus entradas.

Un derivado se calcula sobre los hechos ya contrastados y guarda de cuáles
salió: eso es lo que permite afirmar por máquina que el margen impreso es el
cociente de las dos cifras de su fila, y que la caja de cifras del resumen y la
tabla de la sección C son el mismo objeto. Si falta una entrada, el derivado es
N/A y dice cuál falta; nunca se calcula con un cero que tape el hueco.

Las rentabilidades sobre saldos medios (ROE, ROA, ROIC) se calculan solo para
ejercicios completos: un ROE trimestral anualizado es una convención más, y las
convenciones que el informe no imprime no se aplican.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple

from .campos import DERIVADOS, Derivado
from .hechos import Capa, Contraste, Hecho, Periodo, derivar, na

__all__ = ["calcular", "ttm"]

Hechos = Dict[Tuple[str, Periodo], Hecho]


def _instante(p: Periodo) -> Periodo:
    return Periodo.instante(p.fin)


def _instante_anterior(p: Periodo) -> Periodo:
    """El cierre anterior *calculado*, y solo cuando no hay ninguno publicado con el que quedarse."""
    if p.meses == 12:
        return Periodo.instante(date(p.fin.year - 1, p.fin.month, p.fin.day))
    return Periodo.instante(p.inicio - timedelta(days=1))


def _cierre_anterior(clave: str, p: Periodo, hechos: Hechos) -> Periodo:
    """El último cierre que la compañía publicó antes de este, leído de los hechos y no calculado del calendario.

    Con un ejercicio de 52/53 semanas el cierre de hace un año no cae el mismo día del mes: Qualcomm cerró el
    26/09/2021 y el 25/09/2022, y Apple o Cisco igual. Restarle un año a la fecha de cierre pedía un saldo de un día
    que no existe, así que el patrimonio medio salía N/A **en todos los ejercicios** y con él el ROE, el ROA y el
    ROIC del informe entero. El saldo anterior no se deduce: se busca entre los que hay.
    """
    fin = _instante(p).fin
    anteriores = [q for (c, q) in hechos if c == clave and q.es_instante and q.fin < fin]
    return max(anteriores, key=lambda q: q.fin, default=_instante_anterior(p))


def _media(clave: str, p: Periodo, hechos: Hechos) -> Hecho:
    a, b = hechos.get((clave, _instante(p))), hechos.get((clave, _cierre_anterior(clave, p, hechos)))
    if a is None:
        a = na(clave, _instante(p), "sin saldo al cierre")
    if b is None:
        b = na(clave, _instante_anterior(p), "sin saldo al cierre anterior")
    return derivar(f"{clave}_medio", p, f"({clave} cierre + {clave} cierre anterior) / 2", {"cierre": a, "anterior": b},
                   lambda cierre, anterior: (cierre + anterior) / 2, unidad=a.unidad)


def _entrada(clave: str, p: Periodo, hechos: Hechos, d: Derivado) -> Hecho:
    if clave in d.medios:
        return _media(clave, p, hechos)
    tipo_instante = clave in ("caja", "inversiones_cp", "deuda_cp", "deuda_lp", "deuda_bruta", "deuda_neta",
                              "patrimonio", "total_activo", "activo_corriente", "pasivo_corriente", "fondo_maniobra")
    clave_p = _instante(p) if (tipo_instante and not p.es_instante) else p
    h = hechos.get((clave, clave_p))
    if h is None:
        return na(clave, clave_p, "no hay hecho para este periodo")
    return h


FORMULAS = {
    "margen_bruto": lambda ingresos, coste_ingresos: (ingresos - coste_ingresos) / ingresos if ingresos else None,
    "ebitda": lambda ebit, amortizacion: ebit + amortizacion,
    "margen_ebitda": lambda ebitda, ingresos: ebitda / ingresos if ingresos else None,
    "margen_ebit": lambda ebit, ingresos: ebit / ingresos if ingresos else None,
    "margen_neto": lambda beneficio_neto, ingresos: beneficio_neto / ingresos if ingresos else None,
    "tipo_efectivo": lambda impuestos, bai: impuestos / bai if bai else None,
    "deuda_bruta": lambda deuda_cp, deuda_lp: deuda_cp + deuda_lp,
    "deuda_neta": lambda deuda_bruta, caja, inversiones_cp: deuda_bruta - caja - inversiones_cp,
    "dfn_ebitda": lambda deuda_neta, ebitda: deuda_neta / ebitda if ebitda else None,
    "fondo_maniobra": lambda activo_corriente, pasivo_corriente: activo_corriente - pasivo_corriente,
    "fcf": lambda cfo, capex: cfo - capex,
    "retribucion": lambda dividendos, recompras: dividendos + recompras,
    "retribucion_sobre_fcf": lambda retribucion, fcf: retribucion / fcf if fcf else None,
    "capex_ventas": lambda capex, ingresos: capex / ingresos if ingresos else None,
    "roe": lambda beneficio_neto, patrimonio: beneficio_neto / patrimonio if patrimonio else None,
    "roa": lambda beneficio_neto, total_activo: beneficio_neto / total_activo if total_activo else None,
    "roic": lambda ebit, tipo_efectivo, patrimonio, deuda_bruta, caja: (ebit * (1 - tipo_efectivo)) / (patrimonio + deuda_bruta - caja)
    if (patrimonio + deuda_bruta - caja) else None,
    "cobertura_intereses": lambda ebit, intereses: ebit / intereses if intereses else None,
    "payout": lambda dividendos, beneficio_neto: dividendos / beneficio_neto if beneficio_neto else None,
}

SOLO_ANUALES = {"roe", "roa", "roic"}
SOBRE_INSTANTES = {"deuda_bruta", "deuda_neta", "fondo_maniobra"}


def calcular(hechos: Hechos, flujos: List[Periodo], instantes: List[Periodo]) -> Hechos:
    """Añade los derivados del catálogo a `hechos` (copia) y devuelve el conjunto."""
    salida: Hechos = dict(hechos)
    for d in DERIVADOS:
        periodos = instantes if d.clave in SOBRE_INSTANTES else flujos
        for p in periodos:
            if d.clave in SOLO_ANUALES and p.meses != 12:
                continue
            if d.clave == "dfn_ebitda" and p.meses != 12:
                continue   # deuda neta / EBITDA anual: un trimestre no es comparable
            entradas = {clave: _entrada(clave, p, salida, d) for clave in d.entradas}
            if d.clave == "dfn_ebitda":
                entradas = {"deuda_neta": _entrada("deuda_neta", p, salida, d), "ebitda": _entrada("ebitda", p, salida, d)}
            salida[(d.clave, p)] = derivar(d.clave, p, d.formula, entradas, FORMULAS[d.clave], unidad=d.unidad)
    return salida


def ttm(hechos: Hechos, trimestres: List[Periodo], claves: List[str]) -> Hechos:
    """Últimos doce meses = suma de los cuatro últimos trimestres, para magnitudes aditivas."""
    salida: Hechos = {}
    if len(trimestres) < 4:
        return salida
    ultimos = trimestres[-4:]
    p = Periodo(fin=ultimos[-1].fin, inicio=ultimos[0].inicio)
    for clave in claves:
        entradas = {f"t{i+1}": hechos.get((clave, t)) or na(clave, t, "sin trimestre") for i, t in enumerate(ultimos)}
        salida[(clave, p)] = derivar(clave, p, " + ".join(t.clave for t in ultimos), entradas,
                                     lambda t1, t2, t3, t4: t1 + t2 + t3 + t4, unidad=entradas["t1"].unidad)
    return salida
