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

__all__ = ["calcular", "ttm", "deuda_neta_ebitda_vigente", "incluye_papel_comercial"]

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

    Y se busca **el del periodo anterior**, no el último publicado: entre el cierre de un ejercicio y el del anterior
    están los balances de los tres trimestres, y quedarse con el más reciente medía el patrimonio del FY25 con el del
    3T FY25 (auditoría del 27/09, fallos [13] y [43]). Vale el cierre publicado más cercano al calculado, a una semana
    como mucho (52/53 semanas); si no hay ninguno, el calculado, que saldrá N/A con su motivo.
    """
    objetivo = _instante_anterior(p).fin
    anteriores = [q for (c, q) in hechos if c == clave and q.es_instante and abs((q.fin - objetivo).days) <= 7]
    return min(anteriores, key=lambda q: abs((q.fin - objetivo).days), default=_instante_anterior(p))


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
    tipo_instante = clave in ("caja", "inversiones_cp", "inversiones_lp", "deuda_cp", "papel_comercial", "deuda_lp", "deuda_bruta", "deuda_neta",
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
    "roic": lambda ebit, tipo_efectivo, patrimonio, deuda_neta: (ebit * (1 - tipo_efectivo)) / (patrimonio + deuda_neta)
    if (patrimonio + deuda_neta) else None,
    "cobertura_intereses": lambda ebit, intereses: ebit / intereses if intereses else None,
    "payout": lambda dividendos, beneficio_neto: dividendos / beneficio_neto if beneficio_neto else None,
}

SOLO_ANUALES = {"roe", "roa", "roic"}

# Ratios cuyo denominador tiene que ser positivo para significar algo: con un FCF negativo, «retribución / FCF» de
# −24,8 % no dice nada (fallo [22]). Sale N/A con el motivo; el cero y el hueco siguen siendo lo que eran.
BASE_POSITIVA = {"retribucion_sobre_fcf": ("fcf", "el FCF"), "payout": ("beneficio_neto", "el beneficio neto"),
                 "dfn_ebitda": ("ebitda", "el EBITDA"), "roe": ("patrimonio", "el patrimonio neto medio")}
SOBRE_INSTANTES = {"deuda_bruta", "deuda_neta", "fondo_maniobra"}

# `deuda_cp` con estos conceptos es solo el vencimiento corriente del largo plazo: el papel comercial va aparte
_SOLO_VENCIMIENTO_CORRIENTE = ("LongTermDebtCurrent",)


def incluye_papel_comercial(deuda_cp: Optional[Hecho], papel_comercial: Optional[Hecho]) -> bool:
    """Si la deuda bruta debe sumar el papel comercial (A4, fallo [7]).

    Solo cuando la compañía lo presenta en línea propia y su deuda a corto plazo es únicamente el vencimiento corriente
    del largo plazo (Apple). Si la deuda a corto es el total («DebtCurrent», «ShortTermBorrowings»: Qualcomm imprime
    2.489 = 1.991 de vencimientos + 498 de pagarés), el papel comercial ya está dentro y sumarlo lo contaría dos veces.
    """
    if deuda_cp is None or papel_comercial is None or not papel_comercial.hay_dato or not papel_comercial.valor:
        return False
    concepto = (deuda_cp.origen.concepto if deuda_cp.origen is not None else "") or ""
    return concepto.split(":")[-1] in _SOLO_VENCIMIENTO_CORRIENTE


def _otros_que_cuadran(salida: Hechos, flujos: List[Periodo]) -> None:
    """«Otros ingresos y gastos» de un emisor de la SEC: lo que lleva del EBIT al resultado antes de impuestos.

    Quien no etiqueta el total no operativo publica sus partes (Oracle: intereses cobrados, plusvalías de inversiones,
    otros), y el primer concepto de la lista era solo una de ellas: EBIT − gastos financieros + otros no daba el
    resultado antes de impuestos (fallo [20]). Si lo publicado cuadra (con los gastos financieros aparte o dentro), se
    queda; si no, la fila es el resto, derivado y con su fórmula, y la nota dice qué publica la SEC.
    Las cuentas españolas no pasan por aquí: su «resultado financiero» ya es el total.
    """
    if not any(h.capa is Capa.SEC for h in salida.values()):
        return
    for p in flujos:
        bai, ebit, gf = (salida.get((c, p)) for c in ("bai", "ebit", "intereses"))
        if not all(h is not None and h.hay_dato for h in (bai, ebit, gf)):
            continue
        otros = salida.get(("otros_financieros", p))
        resto = bai.valor - ebit.valor + gf.valor
        if otros is not None and otros.hay_dato and min(abs(otros.valor - resto), abs(otros.valor - (bai.valor - ebit.valor))) <= 1e6:
            continue
        h = derivar("otros_financieros", p, "Resultado antes de impuestos − EBIT + Gastos financieros",
                    {"bai": bai, "ebit": ebit, "intereses": gf}, lambda bai, ebit, intereses: bai - ebit + intereses, unidad=bai.unidad)
        publicado = (f"la SEC publica {otros.valor / 1e6:,.0f} M en «{(otros.origen.concepto if otros.origen else '') or 'otros'}», solo una parte"
                     .replace(",", ".") if otros is not None and otros.hay_dato else "la compañía no publica la partida total")
        salida[("otros_financieros", p)] = h.con(nota=f"{publicado}: la fila es el resto, para que el cuadro sume")


def calcular(hechos: Hechos, flujos: List[Periodo], instantes: List[Periodo]) -> Hechos:
    """Añade los derivados del catálogo a `hechos` (copia) y devuelve el conjunto."""
    salida: Hechos = dict(hechos)
    _otros_que_cuadran(salida, flujos)
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
            if d.clave == "deuda_bruta":
                pc = salida.get(("papel_comercial", _instante(p)))
                if incluye_papel_comercial(entradas["deuda_cp"], pc):
                    salida[(d.clave, p)] = derivar(d.clave, p, d.formula + " + Papel comercial", {**entradas, "papel_comercial": pc},
                                                   lambda deuda_cp, deuda_lp, papel_comercial: deuda_cp + deuda_lp + papel_comercial,
                                                   unidad=d.unidad)
                    continue
            h = derivar(d.clave, p, d.formula, entradas, FORMULAS[d.clave], unidad=d.unidad)
            base = BASE_POSITIVA.get(d.clave)
            if base is not None and h.hay_dato and entradas[base[0]].valor < 0:
                h = derivar(d.clave, p, d.formula, entradas, lambda **_: None, unidad=d.unidad).con(
                    motivo=f"no significativo: {base[1]} es negativo ({entradas[base[0]].valor / 1e6:,.0f} M)".replace(",", "."))
            salida[(d.clave, p)] = h
    return salida


def deuda_neta_ebitda_vigente(hechos: Hechos) -> Optional[Tuple[float, Hecho, float, Periodo]]:
    """(ratio, deuda neta del último balance, EBITDA de los cuatro trimestres que acaban en esa fecha o antes, último
    trimestre): numerador y denominador de la misma fecha (A4, fallos [22] y [54]). La checklist dividía la deuda del
    ejercicio entre el EBITDA del ejercicio aunque hubiera un balance posterior, y el párrafo factual, la deuda del 3T
    entre el EBITDA del ejercicio anterior. Sin cuatro trimestres seguidos con EBITDA, None: no se mezcla."""
    deudas = sorted((p for (c, p), h in hechos.items() if c == "deuda_neta" and p.es_instante and h.hay_dato), key=lambda p: p.fin)
    if not deudas:
        return None
    fecha = deudas[-1].fin
    trimestres = sorted((p for (c, p), h in hechos.items() if c == "ebitda" and p.meses == 3 and p.fin <= fecha and h.hay_dato),
                        key=lambda p: p.fin)[-4:]
    if len(trimestres) < 4 or (trimestres[-1].fin - trimestres[0].inicio).days > 380 or (fecha - trimestres[-1].fin).days > 10:
        return None
    ebitda = sum(hechos[("ebitda", q)].valor for q in trimestres)
    if not ebitda:
        return None
    dn = hechos[("deuda_neta", deudas[-1])]
    return dn.valor / ebitda, dn, ebitda, trimestres[-1]


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
