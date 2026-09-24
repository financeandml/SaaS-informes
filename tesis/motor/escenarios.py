"""Tres escenarios, precio objetivo y métricas con definiciones únicas (05 §7).

V_h = V₀ × (1 + Ke)^(h/12) − DPA esperados en h. Valor razonable hoy = Σ p·V₀. PO = Σ p·V_h.
Potencial = PO / P − 1 · margen de seguridad = 1 − P / valor razonable · downside = V_h,pes / P − 1 ·
recorrido/riesgo = (PO − P) / (P − V_h,pes).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .proyeccion import Proyeccion, proyectar
from .puente import Puente
from .supuestos import NOMBRES, Escenario, Parametros
from .terminal import Terminal, terminal
from .wacc import Wacc

__all__ = ["Resultado", "Valoracion", "valorar", "valorar_escenario", "recomendacion"]


@dataclass
class Resultado:
    escenario: Escenario
    wacc: float
    proyeccion: Proyeccion
    terminal: Terminal
    ev: float
    fondos_propios: float
    v0: float
    vh: float
    peso_vt: float
    avisos: List[str] = field(default_factory=list)
    bloqueos: List[str] = field(default_factory=list)


@dataclass
class Valoracion:
    parametros: Parametros
    wacc: Wacc
    puente: Puente
    precio: float
    resultados: Dict[str, Resultado]
    valor_razonable: float
    po: float
    potencial: float
    margen_seguridad: float
    downside: float
    recorrido_riesgo: Optional[float]           # None: sin pérdida en el escenario pesimista
    recomendacion: str
    dpa_horizonte: float
    bloqueos: List[str] = field(default_factory=list)
    avisos: List[str] = field(default_factory=list)

    @property
    def base(self) -> Resultado:
        return self.resultados["base"]


def valorar_escenario(e: Escenario, p: Parametros, wacc_base: float, ke: float, ingresos_base: float, cierre_base,
                      pte: Puente, rf: Optional[float], umbrales: dict, dpa_horizonte: float = 0.0) -> Resultado:
    w = wacc_base + e.wacc_ajuste
    pr = proyectar(ingresos_base, e, w, p.fecha_valoracion, cierre_base, p.mitad_de_anio, p.bin_inicial,
                   p.sbc_politica == "coste_de_caja")
    ronic = e.ronic if e.ronic is not None else w + umbrales["ronic_defecto_pp"] / 100
    tv = terminal(pr.nopat[-1], pr.fcff[-1], pr.ebitda[-1], w, e.g, ronic, e.multiplo_salida, pr.fraccion, len(pr.fcff),
                  p.tv_metodo, rf, umbrales["g_max"], umbrales["wacc_menos_g_min_pp"] / 100, umbrales["ronic_max_x_wacc"],
                  umbrales["vt_contraste_aviso"])
    ev = pr.suma_valor_actual + tv.valor_actual
    fp = pte.fondos_propios(ev)
    v0 = fp / pte.acciones
    vh = v0 * (1 + ke) ** (p.horizonte_meses / 12) - dpa_horizonte
    peso = tv.valor_actual / ev if ev else 0.0
    avisos = list(tv.avisos)
    if peso > umbrales["peso_vt_aviso"]:
        avisos.append(f"el valor terminal pesa un {peso:.0%} del valor de empresa (aviso desde {umbrales['peso_vt_aviso']:.0%})")
    return Resultado(e, w, pr, tv, ev, fp, v0, vh, peso, avisos, list(tv.bloqueos))


def recomendacion(potencial: float, recorrido_riesgo: Optional[float], regla: dict) -> str:
    comprar, vender = regla["comprar"], regla["vender"]
    if potencial >= comprar["potencial_min"] and (recorrido_riesgo is None or recorrido_riesgo >= comprar["recorrido_riesgo_min"]):
        return "Comprar"
    if potencial <= vender["potencial_max"]:
        return "Vender"
    return "Mantener"


def valorar(p: Parametros, w: Wacc, pte: Puente, precio: float, ingresos_base: float, cierre_base, umbrales: dict,
            dpa_horizonte: float = 0.0) -> Valoracion:
    bloqueos = list(p.faltas) + list(w.bloqueos) + list(pte.faltas)
    avisos = list(w.avisos)
    resultados: Dict[str, Resultado] = {}
    for nombre in NOMBRES:
        e = p.escenarios.get(nombre)
        if e is None:
            continue
        r = valorar_escenario(e, p, w.wacc, w.ke, ingresos_base, cierre_base, pte, w.rf, umbrales, dpa_horizonte)
        resultados[nombre] = r
        bloqueos += [f"{nombre}: {b}" for b in r.bloqueos]
        avisos += [f"{nombre}: {a}" for a in r.avisos]
    if len(resultados) == 3:
        v = [resultados[n].v0 for n in NOMBRES]
        if not v[0] <= v[1] <= v[2]:
            bloqueos.append("escenarios desordenados: el valor pesimista, el base y el optimista deben ir de menor a mayor")
        suma = sum(resultados[n].escenario.probabilidad for n in NOMBRES)
        if abs(suma - 1) > 1e-6:
            bloqueos.append(f"las probabilidades suman {suma:.0%}, no 100 %")
        if resultados["base"].escenario.probabilidad < umbrales["prob_base_min"]:
            bloqueos.append(f"probabilidad del escenario base < {umbrales['prob_base_min']:.0%}")
    razonable = sum(r.escenario.probabilidad * r.v0 for r in resultados.values())
    po = sum(r.escenario.probabilidad * r.vh for r in resultados.values())
    pes = resultados.get("pesimista")
    potencial = po / precio - 1
    margen = 1 - precio / razonable if razonable else float("nan")
    downside = pes.vh / precio - 1 if pes else float("nan")
    rr = None if (pes is None or pes.vh >= precio) else (po - precio) / (precio - pes.vh)
    rec = recomendacion(potencial, rr, umbrales["recomendacion"])
    return Valoracion(p, w, pte, precio, resultados, razonable, po, potencial, margen, downside, rr, rec, dpa_horizonte,
                      bloqueos, avisos)
