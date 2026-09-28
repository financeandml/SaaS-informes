"""Las series del DCF por su histórico (F12): lo que el asistente propone para el paso 7 y lo que el informe imprime como
«histórico» junto a cada supuesto. Una sola función para los dos (regla 13): si el asistente propusiera una mediana y el
informe imprimiera otra, el analista confirmaría un número que no ve.

Lee los conceptos normalizados del catálogo (`datos/campos.py`), no etiquetas US GAAP sueltas: cuando llegue la capa NIIF
(F16) se cambia el catálogo, no esto. La única excepción son los impuestos pagados, que el informe no imprime y solo sirven
aquí; van en un campo propio de este módulo, sin entrar en el contraste general.

Tres estados, siempre con motivo:
- `valor`: la mediana (o el cociente del periodo, en el fondo de maniobra), en % con un decimal, como se teclea;
- `sin_propuesta`: la SEC no publica ejercicios suficientes, o no en todos;
- `no_aplica`: la compañía no declara la partida en ningún 10-K ni 10-Q. No es un cero: el analista decide.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple

from ..datos.campos import CAMPOS, Campo
from ..datos.hechos import Capa, Periodo

__all__ = ["Serie", "series", "crecimiento_udm", "margen_ciclo", "margen_ultimo", "ejercicios_historico", "SERIES"]

# la clave es la del escenario en 04 (esc.<escenario>.<clave>)
SERIES = ("da_pct", "capex_pct", "sbc_pct", "fm_pct_incremental", "impuesto_caja")

_IMPUESTOS_PAGADOS = Campo("impuestos_pagados", "Impuestos pagados", "Income taxes paid", 10,
                           conceptos=("IncomeTaxesPaidNet", "IncomeTaxesPaid"))


@dataclass(frozen=True)
class Serie:
    clave: str
    rotulo: str
    formula: str
    estado: str                                  # valor | sin_propuesta | no_aplica
    valor: Optional[float]                       # en % (4.1 = 4,1 %), con un decimal
    motivo: str
    anios: Tuple[Tuple[date, float], ...] = ()   # (cierre del ejercicio, cociente en tanto por uno)
    certeza: str = "alta"                        # media si algún ejercicio es un derivado (suma de conceptos)

    @property
    def hay_valor(self) -> bool:
        return self.estado == "valor"


def ejercicios_historico() -> int:
    from ..umbrales import umbral
    return int(umbral("historico_ejercicios"))


def _campo(clave: str) -> Campo:
    return next(c for c in CAMPOS if c.clave == clave)


def _declara(facts: dict, campo: Campo) -> bool:
    """Si la compañía ha etiquetado la partida alguna vez (con su concepto o con sus partes)."""
    gaap = (facts.get("facts") or {}).get("us-gaap") or {}
    return any(c in gaap for c in campo.conceptos) or any(all(c in gaap for c in g) for g in campo.conceptos_suma)


def _anuales(facts: dict, campo: Campo, hasta: date) -> Dict[date, object]:
    from ..fuentes import sec
    return {p.fin: h for p, h in sec.hechos_xbrl(facts, campo, hasta).items()
            if not p.es_instante and p.meses == 12 and p.fin <= hasta and h.hay_dato}


def _instantes(facts: dict, campo: Campo, hasta: date) -> Dict[date, object]:
    from ..fuentes import sec
    return {p.fin: h for p, h in sec.hechos_xbrl(facts, campo, hasta).items() if p.es_instante and p.fin <= hasta and h.hay_dato}


def _pct(x: float) -> float:
    return round(x * 100, 1)


def _lista(anios) -> str:
    from ..formato import numero
    return ", ".join(f"{f.year}: {numero(v * 100, 1)} %" for f, v in anios)


def _mediana_sobre(facts: dict, clave: str, rotulo: str, num: Campo, den: Campo, hasta: date, n: int,
                   solo_positivos: bool = False) -> Serie:
    formula = f"mediana de «{num.rotulo}» / «{den.rotulo}» de los últimos {n} ejercicios"
    if not _declara(facts, num):
        return Serie(clave, rotulo, formula, "no_aplica", None,
                     f"la compañía no declara «{num.rotulo}» en ningún 10-K ni 10-Q: no es un cero, lo decide el analista")
    a, b = _anuales(facts, num, hasta), _anuales(facts, den, hasta)
    cierres = sorted(set(b))[-n:]
    if len(cierres) < n:
        return Serie(clave, rotulo, formula, "sin_propuesta", None,
                     f"la SEC publica {len(cierres)} ejercicios de «{den.rotulo}» y la mediana pide {n}")
    faltan = [f for f in cierres if f not in a]
    if faltan:
        return Serie(clave, rotulo, formula, "sin_propuesta", None,
                     f"la SEC no publica «{num.rotulo}» del ejercicio cerrado el {faltan[0]:%d/%m/%Y}")
    anios, derivado = [], False
    for f in cierres:
        d = b[f].valor
        if not d or (solo_positivos and d <= 0):
            continue
        anios.append((f, abs(a[f].valor) / d))
        derivado |= a[f].capa is Capa.DERIVADO or b[f].capa is Capa.DERIVADO
    if len(anios) < n:
        return Serie(clave, rotulo, formula, "sin_propuesta", None,
                     f"{n - len(anios)} de los {n} ejercicios con «{den.rotulo}» nulo o negativo: la mediana no se calcula")
    mediana = statistics.median(v for _, v in anios)
    return Serie(clave, rotulo, formula, "valor", _pct(mediana), f"mediana de {_lista(anios)}", tuple(anios),
                 "media" if derivado else "alta")


def _fondo_maniobra(facts: dict, hasta: date, n: int) -> Serie:
    """(FM operativo al cierre del último ejercicio − al cierre del primero) / (ingresos del último − del primero).

    Un cociente del periodo y no una mediana de cocientes anuales: un año con los ingresos casi planos divide entre casi
    cero y da cifras de ±500 % que la mediana no siempre aparta. FM operativo = (activo corriente − caja − inversiones a
    corto plazo) − (pasivo corriente − deuda a corto plazo).
    """
    clave, rotulo = "fm_pct_incremental", "Fondo de maniobra incremental"
    formula = f"Δ fondo de maniobra operativo / Δ ingresos entre el primer y el último de los {n} ejercicios"
    ingresos = _anuales(facts, _campo("ingresos"), hasta)
    cierres = sorted(ingresos)[-n:]
    if len(cierres) < n:
        return Serie(clave, rotulo, formula, "sin_propuesta", None, f"la SEC publica {len(cierres)} ejercicios de ingresos y el cálculo pide {n}")
    partes = {"activo_corriente": 1, "caja": -1, "inversiones_cp": -1, "pasivo_corriente": -1, "deuda_cp": 1}
    fm: Dict[date, float] = {}
    for f in (cierres[0], cierres[-1]):
        total = 0.0
        for c, signo in partes.items():
            campo = _campo(c)
            if not _declara(facts, campo):
                continue                                  # la compañía no tiene esa partida: no suma, no es un cero inventado
            h = _instantes(facts, campo, hasta).get(f)
            if h is None:
                return Serie(clave, rotulo, formula, "sin_propuesta", None,
                             f"la SEC no publica «{campo.rotulo}» a {f:%d/%m/%Y}")
            total += signo * h.valor
        fm[f] = total
    d_ing = ingresos[cierres[-1]].valor - ingresos[cierres[0]].valor
    if d_ing <= 0:
        return Serie(clave, rotulo, formula, "sin_propuesta", None,
                     f"los ingresos no crecen entre {cierres[0].year} y {cierres[-1].year}: el cociente no tiene sentido")
    ratio = (fm[cierres[-1]] - fm[cierres[0]]) / d_ing
    from ..formato import numero
    return Serie(clave, rotulo, formula, "valor", _pct(ratio),
                 f"fondo de maniobra operativo {numero(fm[cierres[0]] / 1e6)} → {numero(fm[cierres[-1]] / 1e6)} mln USD e ingresos "
                 f"{numero(ingresos[cierres[0]].valor / 1e6)} → {numero(ingresos[cierres[-1]].valor / 1e6)} mln USD "
                 f"({cierres[0].year}–{cierres[-1].year})", ((cierres[-1], ratio),))


def series(facts: dict, hasta: date, n: Optional[int] = None) -> Dict[str, Serie]:
    """Las cinco series del paso 7 con su histórico, a la fecha `hasta` (la de valoración)."""
    n = n or ejercicios_historico()
    ing = _campo("ingresos")
    return {
        "da_pct": _mediana_sobre(facts, "da_pct", "D&A sobre ingresos", _campo("amortizacion"), ing, hasta, n),
        "capex_pct": _mediana_sobre(facts, "capex_pct", "Capex sobre ingresos", _campo("capex"), ing, hasta, n),
        "sbc_pct": _mediana_sobre(facts, "sbc_pct", "SBC sobre ingresos", _campo("sbc"), ing, hasta, n),
        "fm_pct_incremental": _fondo_maniobra(facts, hasta, n),
        "impuesto_caja": _mediana_sobre(facts, "impuesto_caja", "Impuesto en caja sobre EBIT", _IMPUESTOS_PAGADOS,
                                        _campo("ebit"), hasta, n, solo_positivos=True),
    }


def _anterior(periodos: Dict[Periodo, object], p: Periodo) -> Optional[Periodo]:
    """El periodo de la misma duración que acaba un año antes (± 10 días: ejercicios de 52/53 semanas)."""
    return next((q for q in periodos if q.meses == p.meses and abs((p.fin - q.fin).days - 364) <= 10 and q.fin < p.fin), None)


def crecimiento_udm(facts: dict, hasta: date) -> Serie:
    """Crecimiento de los ingresos de los últimos doce meses frente a los doce anteriores.

    UDM = último ejercicio + acumulado del ejercicio en curso − el mismo acumulado un año antes. Sin trimestres tras el
    último ejercicio, el crecimiento de ese ejercicio.
    """
    from ..fuentes import sec
    clave, rotulo = "crecimiento_ingresos", "Crecimiento de ingresos (últimos doce meses)"
    formula = "ingresos de los últimos doce meses / los de los doce anteriores − 1"
    hechos = {p: h for p, h in sec.hechos_xbrl(facts, _campo("ingresos"), hasta).items()
              if not p.es_instante and p.fin <= hasta and h.hay_dato}
    anuales = sorted((p for p in hechos if p.meses == 12), key=lambda p: p.fin)
    if len(anuales) < 2:
        return Serie(clave, rotulo, formula, "sin_propuesta", None, "la SEC publica menos de dos ejercicios de ingresos")
    fy, fy_prev = anuales[-1], _anterior(hechos, anuales[-1])
    if fy_prev is None:
        return Serie(clave, rotulo, formula, "sin_propuesta", None, f"sin el ejercicio anterior al cerrado el {fy.fin:%d/%m/%Y}")
    inicio = fy.fin + timedelta(days=1)
    acumulados = sorted((p for p in hechos if p.inicio == inicio and p.meses in (3, 6, 9)), key=lambda p: p.fin)
    from ..formato import numero
    if not acumulados:
        g = hechos[fy].valor / hechos[fy_prev].valor - 1
        return Serie(clave, rotulo, "ingresos del último ejercicio / los del anterior − 1", "valor", _pct(g),
                     f"{numero(hechos[fy_prev].valor / 1e6)} → {numero(hechos[fy].valor / 1e6)} mln USD ({fy.fin.year})",
                     ((fy.fin, g),))
    acc = acumulados[-1]
    acc_1 = _anterior(hechos, acc)
    acc_2 = _anterior(hechos, acc_1) if acc_1 else None
    if acc_1 is None or acc_2 is None:
        return Serie(clave, rotulo, formula, "sin_propuesta", None,
                     f"la SEC no publica los ingresos acumulados comparables a los de {acc.clave}")
    udm = hechos[fy].valor + hechos[acc].valor - hechos[acc_1].valor
    udm_1 = hechos[fy_prev].valor + hechos[acc_1].valor - hechos[acc_2].valor
    g = udm / udm_1 - 1
    return Serie(clave, rotulo, formula, "valor", _pct(g),
                 f"{numero(udm_1 / 1e6)} → {numero(udm / 1e6)} mln USD (doce meses a {acc.fin:%d/%m/%Y})", ((acc.fin, g),))


def margen_ciclo(facts: dict, hasta: date, minimo: int, maximo: int) -> Serie:
    """Mediana del margen operativo de los últimos `maximo` ejercicios (al menos `minimo`). La misma que usa la comprobación
    de ciclo de los semiconductores (`sector._ciclo`) y la que propone el asistente como margen terminal del base."""
    clave, rotulo = "margen_ebit", "Margen EBIT de ciclo"
    formula = f"mediana del EBIT / ingresos de hasta {maximo} ejercicios"
    ingresos, ebit = _anuales(facts, _campo("ingresos"), hasta), _anuales(facts, _campo("ebit"), hasta)
    margenes = sorted((f, ebit[f].valor / h.valor) for f, h in ingresos.items() if f in ebit and h.valor)[-maximo:]
    if len(margenes) < minimo:
        return Serie(clave, rotulo, formula, "sin_propuesta", None,
                     f"la SEC publica {len(margenes)} ejercicios de margen operativo y la mediana de ciclo pide al menos {minimo}")
    return Serie(clave, rotulo, formula, "valor", _pct(statistics.median(v for _, v in margenes)),
                 f"mediana de {len(margenes)} ejercicios ({margenes[0][0].year}–{margenes[-1][0].year})", tuple(margenes))


def margen_ultimo(facts: dict, hasta: date) -> Serie:
    """Margen EBIT del último ejercicio (el año 1 del base parte de él si no hay guía)."""
    ingresos, ebit = _anuales(facts, _campo("ingresos"), hasta), _anuales(facts, _campo("ebit"), hasta)
    comunes = sorted(f for f in ingresos if f in ebit and ingresos[f].valor)
    if not comunes:
        return Serie("margen_ebit", "Margen EBIT del último ejercicio", "EBIT / ingresos", "sin_propuesta", None,
                     "la SEC no publica ingresos y EBIT de un mismo ejercicio")
    f = comunes[-1]
    m = ebit[f].valor / ingresos[f].valor
    return Serie("margen_ebit", "Margen EBIT del último ejercicio", "EBIT / ingresos", "valor", _pct(m),
                 f"ejercicio cerrado el {f:%d/%m/%Y}", ((f, m),))
