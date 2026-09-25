"""Parte G (apartados 27–30): tesis consolidada, lista de comprobación, gestión del riesgo y seguimiento.

Es juicio del analista (paso 8 del asistente, `pos.*`), impreso literal y rotulado como suyo; el sistema pone el horizonte
y el PO del motor, evalúa los criterios automáticos de `config/checklist.yaml` con su evidencia, calcula el tamaño que
sugiere el drawdown tolerado y la volatilidad realizada, el drawdown histórico y la beta. Sin entradas de posición, cada
apartado dice qué falta y el informe no se emite (R30); nunca «N/A» en lugar del analista.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from datetime import date, timedelta
from functools import lru_cache
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

from ..entradas import Entradas, palabras
from ..formato import Celda, fecha as f_fecha, numero, pct
from ..rutas import CONFIG

__all__ = ["ParteG", "construir", "checklist", "texto"]

_RUTA = CONFIG / "checklist.yaml"
_CUMPLE = {"si": "sí", "no": "no", "parcial": "parcial", "sin_dato": "sin dato"}


@lru_cache(maxsize=1)
def checklist() -> dict:
    import yaml
    return yaml.safe_load(_RUTA.read_text(encoding="utf-8")) or {}


def texto(e: Entradas, id_: str) -> str:
    """Un texto del analista: {"texto": …} o una cadena."""
    v = e.valor(id_)
    return (v.get("texto", "") if isinstance(v, dict) else (v or "")).strip() if v is not None else ""


@dataclass
class ParteG:
    cuadros: Dict[str, object] = field(default_factory=dict)          # asunciones, checklist, invalidacion, riesgo, kpis
    argumento: str = ""
    recomendacion: str = ""                                           # la del analista
    regla: str = ""                                                   # la que sugiere la regla (motor)
    justificacion: str = ""
    horizonte_meses: Optional[int] = None
    entrada: Dict[str, str] = field(default_factory=dict)             # para la portada: precio, fecha, tamaño, stop
    fechas_revision: List[str] = field(default_factory=list)
    salida: List[str] = field(default_factory=list)
    pendientes: Dict[str, str] = field(default_factory=dict)
    faltas: List[str] = field(default_factory=list)
    avisos: List[str] = field(default_factory=list)
    _limpios: Optional[Tuple[object, int]] = None                     # (fila del criterio «datos limpios», posición de la celda)

    def cerrar(self, bloqueos: int, discrepancias: int) -> List[str]:
        """Con la puerta de calidad ya calculada: el criterio «0 discrepancias y 0 bloqueos» y, si es un «no» eliminatorio
        con «Comprar» sin justificación, la falta que eso supone."""
        if self._limpios is None:
            return []
        fila, k = self._limpios
        ok = bloqueos == 0 and discrepancias == 0
        evidencia = f"{numero(discrepancias)} discrepancias de datos y {numero(bloqueos)} bloqueos de calidad"
        fila.celdas[k] = Celda("sí" if ok else "no", "", "D", "valor" if ok else "negativo", evidencia)
        fila.celdas[k + 1] = Celda(evidencia, "", "D", "valor", "")
        if not ok and self.recomendacion == "Comprar" and palabras(self.justificacion) < 20:
            return ["pos.recomendacion: «Comprar» con el criterio eliminatorio «0 discrepancias de datos y 0 bloqueos de calidad» "
                    "sin cumplir exige una justificación escrita de 20 palabras o más"]
        return []


def _c(t: str, nota: str = "", clase: str = "valor", capa: str = "S") -> Celda:
    return Celda(t, "", capa, clase, nota)


def _evidencia(ev) -> str:
    """Una evidencia del analista: texto libre o cita {doc, pag, texto, texto_es} (se imprime la versión en español)."""
    if isinstance(ev, list):
        return " · ".join(_evidencia(x) for x in ev)
    if isinstance(ev, dict):
        ref = ev.get("doc", "") + (f", pág. {ev['pag']}" if ev.get("pag") else "")
        return f"«{ev.get('texto_es') or ev.get('texto', '')}» [{ref}]" if ref else str(ev.get("texto_es") or ev.get("texto", ""))
    return str(ev or "")


def _volatilidad(cierres: Sequence[float]) -> Optional[float]:
    r = [math.log(b / a) for a, b in zip(cierres, cierres[1:]) if a and b]
    return statistics.pstdev(r) * math.sqrt(252) if len(r) > 20 else None


def _drawdown(cierres: Sequence[float]) -> Optional[float]:
    if len(cierres) < 2:
        return None
    pico, peor = cierres[0], 0.0
    for c in cierres:
        pico = max(pico, c)
        peor = min(peor, c / pico - 1)
    return peor


def _mercado(sesiones: Mapping, hasta: date) -> dict:
    """Volumen medio en dólares de 3 meses, volatilidad realizada de 1 año y drawdown máximo de 1 y 5 años (Nasdaq)."""
    fechas = sorted(f for f in sesiones if f <= hasta)
    cierres = [sesiones[f].cierre for f in fechas]
    un_anio = [sesiones[f].cierre for f in fechas if f > hasta - timedelta(days=365)]
    tres = [sesiones[f] for f in fechas[-63:]]
    dolares = [s.cierre * s.volumen for s in tres if s.volumen]
    return {"liquidez": statistics.mean(dolares) if dolares else None, "vol_1a": _volatilidad(un_anio),
            "dd_1a": _drawdown(un_anio), "dd_5a": _drawdown(cierres), "desde": fechas[0] if fechas else None}


def _automatico(cid: str, cfg: dict, ctx: dict) -> Tuple[str, str]:
    """(cumple: si · no · sin_dato, evidencia) de un criterio automático."""
    v = ctx.get("valoracion")
    if cid == "potencial" and v is not None:
        return ("si" if v.potencial >= cfg["umbral"] else "no"), f"potencial {pct(v.potencial)} (umbral {pct(cfg['umbral'], 0)})"
    if cid == "recorrido_riesgo" and v is not None:
        if v.recorrido_riesgo is None:
            return "si", "sin pérdida en el escenario pesimista"
        return ("si" if v.recorrido_riesgo >= cfg["umbral"] else "no"), f"{numero(v.recorrido_riesgo, 2)} (umbral {numero(cfg['umbral'], 1)})"
    if cid == "margen_seguridad" and v is not None:
        return ("si" if v.margen_seguridad >= cfg["umbral"] else "no"), f"{pct(v.margen_seguridad)} (umbral {pct(cfg['umbral'], 0)})"
    if cid == "datos_limpios":
        return "sin_dato", "se evalúa al cerrar la puerta de calidad"
    if cid == "roic_wacc":
        roic, wacc = ctx.get("roic_5a"), ctx.get("wacc")
        if roic is None or wacc is None:
            return "sin_dato", "sin ROIC de cinco ejercicios o sin WACC del motor"
        return ("si" if roic > wacc else "no"), f"ROIC mediano {pct(roic)} frente a WACC {pct(wacc)}"
    if cid == "apalancamiento":
        x = ctx.get("dn_ebitda")
        if x is None:
            return "sin_dato", "sin deuda neta / EBITDA del último ejercicio"
        return ("si" if x <= cfg["umbral"] else "no"), f"{numero(x, 1)}x (umbral {numero(cfg['umbral'], 1)}x)"
    if cid == "liquidez":
        x = ctx.get("mercado", {}).get("liquidez")
        if x is None:
            return "sin_dato", "sin volumen de la bolsa"
        return ("si" if x >= cfg["umbral"] else "no"), f"{numero(x / 1e6)} M USD diarios (3 meses, Nasdaq)"
    if cid == "evento":
        prox, hoy = ctx.get("proxima"), ctx["fecha_informe"]
        if prox is None:
            return "sin_dato", "sin fecha de próximos resultados"
        habiles = sum(1 for k in range(1, (prox - hoy).days + 1) if (hoy + timedelta(days=k)).weekday() < 5)
        return ("si" if habiles > cfg["dias"] else "no"), f"próximos resultados el {f_fecha(prox)} ({numero(habiles)} días hábiles)"
    if cid == "catalizador":
        limite = ctx["fecha_informe"] + timedelta(days=int(30.44 * (ctx.get("horizonte") or 12)))
        dentro = [c for c in ctx.get("catalizadores", []) if c <= limite]
        return ("si" if dentro else "no"), (f"{numero(len(dentro))} {'catalizador fechado' if len(dentro) == 1 else 'catalizadores fechados'} "
                                            f"antes del {f_fecha(limite)}")
    if cid == "cortos":
        x = ctx.get("cortos")
        if x is None:
            return "sin_dato", "sin interés en corto de la bolsa"
        return ("si" if x < cfg["umbral"] else "no"), f"{pct(x)} de las acciones (Nasdaq, liquidación del {f_fecha(ctx.get('cortos_fecha'))})"
    if cid == "tamano":
        t, dd, r = ctx.get("tamano"), ctx.get("drawdown_tolerado"), checklist()["riesgo_max_posicion"]
        if t is None or dd is None:
            return "sin_dato", "sin tamaño o sin drawdown tolerado del analista"
        return ("si" if t * dd <= r + 1e-12 else "no"), f"{pct(t)} × {pct(dd, 0)} = {pct(t * dd, 2)} (máximo {pct(r, 0)})"
    if cid == "invalidacion":
        n = ctx.get("invalidaciones", 0)
        return ("si" if n >= 3 else "no"), f"{numero(n)} invalidaciones con métrica, umbral y plazo"
    return "sin_dato", ""


def construir(n, e: Entradas, motor, hechos, anuales, etiqueta, sesiones: Mapping, proxima: Optional[date] = None,
              cortos: Optional[Tuple[date, float]] = None, acciones: Optional[float] = None, fecha_informe: Optional[date] = None,
              escala: Sequence[str] = ("Comprar", "Mantener", "Vender")) -> ParteG:
    from .informe import Cuadro, FilaCuadro
    g = ParteG()
    v = getattr(motor, "valoracion", None)
    hoy = fecha_informe or date.today()
    g.horizonte_meses = v.parametros.horizonte_meses if v is not None else None
    g.regla = v.recomendacion if v is not None else ""
    g.recomendacion = str(e.valor("pos.recomendacion") or "")
    g.justificacion = texto(e, "pos.recomendacion_justificacion")
    g.argumento = texto(e, "pos.argumento")
    # 27 · asunciones clave
    from .parte_f import rotulo_supuesto
    filas = [FilaCuadro(a.get("texto", ""), [_c(rotulo_supuesto(a.get("driver", "")), str(a.get("driver", ""))), _c(str(a.get("umbral_invalidacion", "")))], capa="S")
             for a in e.valor("pos.asunciones") or []]
    if filas:
        g.cuadros["asunciones"] = Cuadro(n.siguiente(), "Asunciones clave", ["Supuesto al que se ata", "Se invalida si"], filas,
                                         "Fuente: analista (paso 8).")
    if not g.argumento:
        g.pendientes["argumento"] = "Pendiente del analista: el argumento de la tesis (80–150 palabras) y de tres a siete asunciones clave (paso 8)."
    # 28 · lista de comprobación
    ultimos = sorted(anuales, key=lambda p: p.fin)[-5:]
    roics = [hechos[("roic", p)].valor for p in ultimos if ("roic", p) in hechos and hechos[("roic", p)].hay_dato]
    dn = hechos.get(("dfn_ebitda", ultimos[-1])) if ultimos else None
    fv = v.parametros.fecha_valoracion if v is not None else hoy
    mercado = _mercado(sesiones, fv) if sesiones else {}
    catalizadores = []
    for c in e.valor("catalizadores") or []:
        try:
            catalizadores.append(date.fromisoformat(str(c.get("fecha", ""))))
        except ValueError:
            pass
    tam, dd = e.valor("pos.tamano_pct"), e.valor("pos.drawdown_tolerado")
    invalidaciones = [x for x in e.valor("pos.invalidacion") or [] if x.get("metrica") and x.get("umbral") and x.get("plazo")]
    ctx = {"valoracion": v, "roic_5a": statistics.median(roics) if roics else None, "wacc": v.wacc.wacc if v is not None else None,
           "dn_ebitda": dn.valor if dn is not None and dn.hay_dato else None, "mercado": mercado, "proxima": proxima,
           "fecha_informe": hoy, "catalizadores": catalizadores, "horizonte": g.horizonte_meses,
           "cortos": (cortos[1] / acciones) if cortos and acciones else None, "cortos_fecha": cortos[0] if cortos else None,
           "tamano": float(tam) / 100 if isinstance(tam, (int, float)) else None,
           "drawdown_tolerado": float(dd) / 100 if isinstance(dd, (int, float)) else None, "invalidaciones": len(invalidaciones)}
    propios = {str(x.get("id") or x.get("criterio")): x for x in e.valor("pos.checklist") or []}
    filas, eliminatorios_no = [], []
    for cfg in checklist()["criterios"]:
        if cfg["tipo"] == "auto":
            cumple, evidencia = _automatico(cfg["id"], cfg, ctx)
            tipo = "automático"
        else:
            x = propios.pop(cfg["id"], None) or propios.pop(cfg["texto"], None) or {}
            cumple, evidencia, tipo = (x.get("cumplido") or "sin_dato"), _evidencia(x.get("evidencia")), "del analista"
            if not x:
                g.faltas.append(f"pos.checklist: falta el criterio del analista «{cfg['texto']}»")
        if cfg.get("eliminatorio") and cumple == "no":
            eliminatorios_no.append(cfg["texto"])
        fila = FilaCuadro(cfg["texto"], [_c(tipo, capa="D"), _c(_CUMPLE.get(cumple, cumple), evidencia, "negativo" if cumple == "no" else "valor", "D"),
                                         _c(evidencia or "—", capa="D"), _c("sí" if cfg.get("eliminatorio") else "no", capa="D")], capa="D")
        filas.append(fila)
        if cfg["id"] == "datos_limpios":
            g._limpios = (fila, 1)
    for x in propios.values():                                  # criterios propios del analista
        filas.append(FilaCuadro(str(x.get("criterio", "")), [_c("del analista"), _c(_CUMPLE.get(x.get("cumplido", ""), "sin dato")),
                                                            _c(_evidencia(x.get("evidencia")) or "—"), _c("sí" if x.get("eliminatorio") else "no")], capa="S"))
    g.cuadros["checklist"] = Cuadro(n.siguiente(), "Lista de comprobación de entrada", ["Tipo", "¿Cumple?", "Evidencia", "Eliminatorio"],
                                    filas, "Fuente: criterios automáticos evaluados por el sistema con los datos del informe; los manuales, del analista.")
    if g.recomendacion == "Comprar" and eliminatorios_no and palabras(g.justificacion) < 20:
        g.faltas.append("pos.recomendacion: «Comprar» con criterios eliminatorios sin cumplir (" + "; ".join(eliminatorios_no)
                        + ") exige una justificación escrita de 20 palabras o más")
    # 29 · gestión del riesgo
    filas = [FilaCuadro(x.get("metrica", ""), [_c(str(x.get("umbral", ""))), _c(str(x.get("plazo", "")))], capa="S")
             for x in e.valor("pos.invalidacion") or []]
    if filas:
        g.cuadros["invalidacion"] = Cuadro(n.siguiente(), "Qué invalidaría la tesis", ["Umbral", "Plazo"], filas, "Fuente: analista (paso 8).")
    else:
        g.pendientes["invalidacion"] = "Pendiente del analista: al menos tres invalidaciones medibles (métrica, umbral y plazo)."
    filas = []
    if ctx["tamano"] is not None:
        filas.append(FilaCuadro("Tamaño de la posición", [_c(pct(ctx["tamano"], 1)), _c(texto(e, "pos.tamano_porque"))], capa="S"))
    if ctx["drawdown_tolerado"]:
        r = checklist()["riesgo_max_posicion"]
        filas.append(FilaCuadro("Drawdown tolerado", [_c(pct(ctx["drawdown_tolerado"], 0)), _c("caída de la acción que el analista acepta antes de salir")], capa="S"))
        filas.append(FilaCuadro("Tamaño que sugiere el drawdown", [_c(pct(min(r / ctx["drawdown_tolerado"], checklist()["tamano_max"]), 1), capa="D"),
                                _c(f"riesgo máximo por posición ({pct(r, 0)}) / drawdown tolerado, con tope del {pct(checklist()['tamano_max'], 0)}", capa="D")], capa="D"))
    if texto(e, "pos.stop"):
        filas.append(FilaCuadro("Stop", [_c(texto(e, "pos.stop")), _c("del analista")], capa="S"))
    if mercado.get("vol_1a") is not None:
        filas.append(FilaCuadro("Volatilidad realizada (1 año)", [_c(pct(mercado["vol_1a"]), capa="H"), _c("desviación típica de los rendimientos diarios × √252 (Nasdaq)", capa="H")], capa="H"))
    for clave, rot in (("dd_1a", "Drawdown máximo (1 año)"), ("dd_5a", "Drawdown máximo (5 años)")):
        if mercado.get(clave) is not None:
            filas.append(FilaCuadro(rot, [_c(pct(mercado[clave]), capa="H"), _c("mayor caída desde un máximo previo, con cierres oficiales de Nasdaq", capa="H")], capa="H"))
    if v is not None:
        filas.append(FilaCuadro("Beta", [_c(numero(v.wacc.beta, 2), capa="D"), _c(v.wacc.beta_origen, capa="D")], capa="D"))
    if filas:
        g.cuadros["riesgo"] = Cuadro(n.siguiente(), "Tamaño, volatilidad y drawdown", ["Valor", "Detalle"], filas,
                                     "Fuente: analista (tamaño, drawdown tolerado y stop); Nasdaq y motor de valoración (el resto).")
    if ctx["tamano"] is None:
        g.pendientes["tamano"] = "Pendiente del analista: tamaño de la posición y drawdown tolerado (paso 8)."
    # 30 · seguimiento
    filas = [FilaCuadro(k.get("kpi", ""), [_c(str(k.get("actual") or "—")), _c(str(k.get("verde", ""))), _c(str(k.get("rojo", ""))),
                                           _c(str(k.get("fuente", ""))), _c(str(k.get("frecuencia", "")))], capa="S")
             for k in e.valor("pos.kpis") or []]
    if filas:
        g.cuadros["kpis"] = Cuadro(n.siguiente(), "Indicadores que se vigilan", ["Actual", "En verde si", "En rojo si", "Fuente", "Frecuencia"],
                                   filas, "Fuente: analista (paso 8).")
    else:
        g.pendientes["kpis"] = "Pendiente del analista: al menos tres indicadores con umbral verde y rojo, fuente y frecuencia (paso 8)."
    for x in e.valor("pos.fechas_revision") or []:
        try:
            g.fechas_revision.append(f_fecha(date.fromisoformat(str(x))))
        except ValueError:
            g.fechas_revision.append(str(x))
    g.salida = [str(x.get("texto", x)) if isinstance(x, dict) else str(x) for x in e.valor("pos.salida") or []]
    if len(g.salida) < 3:
        g.pendientes["salida"] = "Pendiente del analista: al menos tres criterios de salida (paso 8)."
    # portada
    pe, fe = e.valor("pos.precio_entrada"), e.valor("pos.fecha_entrada")
    if isinstance(pe, (int, float)) and fe:
        g.entrada["precio"] = f"{numero(float(pe), 2)} USD"
        g.entrada["fecha"] = f_fecha(date.fromisoformat(str(fe)))
    if ctx["tamano"] is not None:
        g.entrada["tamano"] = pct(ctx["tamano"], 1)
    if texto(e, "pos.stop"):
        g.entrada["stop"] = texto(e, "pos.stop")
    if not g.recomendacion:
        g.pendientes["recomendacion"] = "Pendiente del analista: la recomendación (paso 8)."
    elif g.recomendacion not in escala:
        g.faltas.append(f"pos.recomendacion: «{g.recomendacion}» no está en la escala ({', '.join(escala)})")
    return g
