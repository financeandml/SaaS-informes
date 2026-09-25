"""Parte A (apartados 2–3): el resumen ejecutivo y los cinco pilares.

2: los textos del analista (resumen, por qué ahora, visión frente a lo que descuenta el precio) y un párrafo factual de
plantilla —último trimestre, ejercicio, guía vigente, balance y retribución— con una cita por frase, que el analista
acepta o edita en el paso 9 (06 §1, `propuestas.py`). 3: los cinco
pilares del paso 3 con su argumento, sus evidencias verificadas, su KPI y el riesgo del Item 1A que los amenaza (la
versión en español del analista, con su página; el literal, en el HTML).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from typing import Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from ..entradas import Entradas, comprobar_paso3, verificar_cita
from ..formato import numero, pct
from .frases import frase, posicion, verbo
from ..entradas.propuestas import Parrafo, aplicar

__all__ = ["ParteA", "Pilar", "construir"]


@dataclass
class Pilar:
    numero: int
    titulo: str
    argumento: str
    evidencias: List[Tuple[str, str]]          # (impreso: «texto_es» [documento, pág.], literal original)
    kpi: str
    riesgo_es: str
    riesgo_ref: str                            # «10-K 2025, Item 1A, pág. 18»
    riesgo_literal: str


@dataclass
class ParteA:
    resumen: str = ""
    por_que_ahora: str = ""
    vision: str = ""
    factual: List[Tuple[str, str]] = field(default_factory=list)      # (frase, cita)
    pilares: List[Pilar] = field(default_factory=list)
    parrafos: List[Parrafo] = field(default_factory=list)                # 06 §1: propuestas para el paso 9
    pendientes: Dict[str, str] = field(default_factory=dict)
    faltas: List[str] = field(default_factory=list)


def _texto(v) -> str:
    return (v.get("texto", "") if isinstance(v, dict) else (v or "")).strip() if v is not None else ""


def _cita(h) -> str:
    o = h.origen or next((x.origen for x in h.entradas if x.origen is not None), None)
    if o is None:
        return "SEC EDGAR"
    doc = o.formulario or o.documento
    return f"{doc} {o.presentado:%d/%m/%Y}" if o.presentado else doc


def _mln(v: float) -> str:
    return f"{numero(v / 1e6)} mln USD"


def _dato(hechos, clave: str, p):
    h = hechos.get((clave, p)) if p is not None else None
    return h if h is not None and h.hay_dato else None


def _factual(hechos, periodos: Mapping, etiqueta: Callable, vigentes: Sequence, comparaciones: Sequence = ()) -> List[Tuple[str, str]]:
    salida: List[Tuple[str, str]] = []
    # último trimestre frente a su guía (la misma comparación del apartado 26); si no hay guía, frente al año anterior
    x = next((c for c in reversed(comparaciones) if c.candidato.metrica == "ingresos" and c.real is not None), None)
    if x is not None and x.candidato.bajo != x.candidato.alto:
        c, r = x.candidato, x.real
        clave = "dentro" if c.bajo <= r.valor <= c.alto else ("encima" if r.valor > c.alto else "debajo")
        salida.append((frase("2", "trimestre_guia", {"trimestre": c.trimestre, "valor": _mln(r.valor), "posicion": posicion(clave),
                                                     "bajo": numero(c.bajo / 1e6), "alto": _mln(c.alto)}), f"8-K {r.presentado:%d/%m/%Y}, Ex. 99.1"))
    # los trimestres de los hechos (no solo los del cuadro): el mismo trimestre del año anterior también cuenta
    trimestres = sorted({p for (c, p) in hechos if c == "ingresos" and p.meses == 3 and not p.es_instante}, key=lambda p: p.fin)
    anuales = sorted(periodos.get("anuales", []), key=lambda p: p.fin)
    instantes = sorted(periodos.get("instantes", []), key=lambda p: p.fin)
    q = next((p for p in reversed(trimestres) if _dato(hechos, "ingresos", p)), None)
    if q is not None and not salida:
        antes = next((p for p in trimestres if abs((q.fin - timedelta(days=364) - p.fin).days) <= 10), None)
        h, h0 = _dato(hechos, "ingresos", q), _dato(hechos, "ingresos", antes)
        if h0 is not None and h0.valor:
            var = h.valor / h0.valor - 1
            v = verbo(var)
            clave = "trimestre_igual" if v == verbo(0.0) else "trimestre"
            salida.append((frase("2", clave, {"trimestre": etiqueta(q), "verbo": v, "variacion": pct(abs(var)), "valor": _mln(h.valor)}), _cita(h)))
    if len(anuales) >= 2:
        a, a0 = anuales[-1], anuales[-2]
        ing, m, m0 = _dato(hechos, "ingresos", a), _dato(hechos, "margen_ebit", a), _dato(hechos, "margen_ebit", a0)
        if ing is not None and m is not None and m0 is not None:
            cambio = (m.valor - m0.valor) * 100
            texto = f"{'+' if cambio > 0 else ''}{numero(round(cambio, 1) + 0.0, 1)} p. p."
            salida.append((frase("2", "ejercicio", {"ejercicio": etiqueta(a), "ingresos": _mln(ing.valor), "margen": pct(m.valor), "cambio": texto}), _cita(ing)))
    g = next((c for c in vigentes if c.metrica == "ingresos"), None)
    if g is not None:
        cita = f"8-K {g.presentado:%d/%m/%Y}, Ex. 99.1"
        if g.bajo != g.alto:
            salida.append((frase("2", "guia", {"trimestre": g.trimestre, "bajo": f"{numero(g.bajo / 1e6)}", "alto": _mln(g.alto)}), cita))
        else:
            salida.append((frase("2", "guia_punto", {"trimestre": g.trimestre, "valor": _mln(g.bajo)}), cita))
    i = next((p for p in reversed(instantes) if _dato(hechos, "deuda_neta", p)), None)
    if i is not None:
        dn = _dato(hechos, "deuda_neta", i)
        cierre = next((p for p in trimestres + anuales if p.fin == i.fin), None)          # «3T FY26», no la fecha cruda
        periodo = etiqueta(cierre) if cierre is not None else f"{i.fin:%d/%m/%Y}"
        ebitda = _dato(hechos, "ebitda", anuales[-1]) if anuales else None
        if dn.valor < 0:
            salida.append((frase("2", "caja_neta", {"periodo": periodo, "importe": _mln(-dn.valor)}), _cita(dn)))
        elif ebitda is not None and ebitda.valor > 0:
            salida.append((frase("2", "deuda_neta", {"periodo": periodo, "importe": _mln(dn.valor), "veces": numero(dn.valor / ebitda.valor, 1),
                                                     "ejercicio": etiqueta(anuales[-1])}), _cita(dn)))
    if anuales:
        r, rf = _dato(hechos, "retribucion", anuales[-1]), _dato(hechos, "retribucion_sobre_fcf", anuales[-1])
        if r is not None and rf is not None:
            salida.append((frase("2", "retribucion", {"ejercicio": etiqueta(anuales[-1]), "importe": _mln(r.valor), "pct_fcf": pct(rf.valor, 0)}), _cita(r)))
    return salida


def construir(e: Entradas, textos: Mapping[str, str], umbral: float, item, alias: Optional[Dict[str, str]], hechos, periodos: Mapping,
              etiqueta: Callable, vigentes: Sequence, comparaciones: Sequence = ()) -> ParteA:
    from ..datos.item1a import buscar
    from .parte_b import alias_doc
    d = ParteA(resumen=_texto(e.valor("tesis.resumen")), por_que_ahora=_texto(e.valor("tesis.por_que_ahora")),
               vision=_texto(e.valor("tesis.vision_vs_mercado")))
    d.factual, parrafo, sin_validar = aplicar("resumen_factual", "Párrafo factual del resumen ejecutivo",
                                              _factual(hechos, periodos, etiqueta, vigentes, comparaciones), e.valor("revision.parrafos"))
    d.parrafos.append(parrafo)
    if not d.resumen:
        d.pendientes["resumen"] = ("Pendiente del analista: el resumen de la tesis (60–120 palabras), por qué ahora y su visión frente a lo "
                                   "que descuenta el precio (paso 3).")
    for k, p in enumerate(e.valor("pilares") or [], 1):
        evs = []
        for ev in p.get("evidencias") or []:
            if ev.get("texto_es") and verificar_cita(ev, textos, umbral)[0]:
                ref = alias_doc(ev.get("doc", ""), alias) + (f", pág. {ev['pag']}" if ev.get("pag") else "")
                evs.append((f"«{ev['texto_es']}» [{ref}]", ev.get("texto", "")))
        ep = buscar(item, p.get("riesgo_1a", "")) if item is not None and p.get("riesgo_1a") else None
        d.pilares.append(Pilar(k, p.get("titulo", ""), _texto(p.get("argumento")), evs, str(p.get("kpi") or ""), p.get("riesgo_es", ""),
                               f"{alias_doc('10-K', alias)}, Item 1A, pág. {ep.pagina}" if ep is not None else "",
                               ep.texto if ep is not None else ""))
    if not d.pilares:
        d.pendientes["pilares"] = ("Pendiente del analista: los cinco pilares, cada uno con su argumento, dos evidencias verificadas, "
                                   "su KPI y el riesgo del Item 1A que lo amenaza (paso 3).")
    d.faltas = comprobar_paso3(e, textos, umbral, lambda t: item is not None and buscar(item, t) is not None)
    d.faltas += [sin_validar] if sin_validar else []
    return d
