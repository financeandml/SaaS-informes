"""Valoración por suma de partes (05 §8, apartado 19; decisión 5 del analista, 28/09/2026).

VE de cada segmento = su métrica del último periodo publicado (ingresos, EBIT o EBITDA) × el múltiplo que justifica el
analista; menos los costes corporativos capitalizados (los que no reparte entre segmentos, por su propio múltiplo); más
el puente del DCF (deuda, caja, inversiones y ajustes) → fondos propios → por acción, frente al valor del DCF.

La métrica sale de los segmentos que el informe ya imprime en el apartado 4 (XBRL del emisor o cifras del analista con
cita); si el analista elige una métrica que el informe no tiene por segmento (el EBIT de un emisor que solo desglosa
ingresos), la aporta él con su cita verificable (regla 12) o el segmento queda fuera, con su motivo. Nada se reparte
ni se estima.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Mapping, Optional, Sequence

__all__ = ["Parte", "Sotp", "calcular", "METRICAS"]

METRICAS = {"ingresos": "ingresos", "ebit": "EBIT", "ebitda": "EBITDA"}


@dataclass
class Parte:
    segmento: str
    metrica: str
    periodo: str = ""
    valor_metrica: Optional[float] = None
    multiplo: Optional[float] = None
    justificacion: str = ""
    origen: str = ""                     # de dónde sale la métrica: «segmentos del apartado 4» o la cita del analista
    motivo: str = ""                     # por qué no se valora

    @property
    def ve(self) -> Optional[float]:
        if self.valor_metrica is None or self.multiplo is None:
            return None
        return self.valor_metrica * self.multiplo


@dataclass
class Sotp:
    partes: List[Parte] = field(default_factory=list)
    costes_corporativos: Optional[float] = None       # anuales, en positivo
    multiplo_costes: Optional[float] = None
    costes_origen: str = ""
    ajuste_puente: float = 0.0
    acciones: float = 0.0
    dcf_v0: Optional[float] = None
    faltan: List[str] = field(default_factory=list)

    @property
    def costes_capitalizados(self) -> float:
        if self.costes_corporativos is None or self.multiplo_costes is None:
            return 0.0
        return self.costes_corporativos * self.multiplo_costes

    @property
    def ve(self) -> Optional[float]:
        if not self.partes or any(p.ve is None for p in self.partes):
            return None
        return sum(p.ve for p in self.partes) - self.costes_capitalizados

    @property
    def fondos_propios(self) -> Optional[float]:
        return None if self.ve is None else self.ve + self.ajuste_puente

    @property
    def por_accion(self) -> Optional[float]:
        fp = self.fondos_propios
        return None if fp is None or not self.acciones else fp / self.acciones

    @property
    def frente_al_dcf(self) -> Optional[float]:
        pa = self.por_accion
        return None if pa is None or not self.dcf_v0 else pa / self.dcf_v0 - 1


def _num(x) -> Optional[float]:
    return float(x) if isinstance(x, (int, float)) and not isinstance(x, bool) else None


def calcular(entradas: Mapping, segmentos, puente, dcf_v0: Optional[float], verificar: Callable[[dict], bool],
             etiqueta: Callable = lambda p: p.clave) -> Sotp:
    """`entradas`: el bloque `sotp` del analista. `segmentos`: los del apartado 4 (`datos.segmentos.Segmentos`) o None.
    `verificar(cita)`: si la cita del analista se encuentra en su documento y página (la misma comprobación que la QA)."""
    s = Sotp(ajuste_puente=puente.ajuste, acciones=puente.acciones, dcf_v0=dcf_v0)
    lineas = {}
    ultimo = None
    if segmentos is not None and getattr(segmentos, "periodos", None):
        ultimo = segmentos.periodos[-1]
        for l in segmentos.de_tipo("segmento"):
            lineas[l.rotulo.lower()] = l
            lineas[l.miembro.lower()] = l
    for x in entradas.get("segmentos") or []:
        nombre = str(x.get("segmento", "")).strip()
        metrica = str(x.get("metrica", "")).strip().lower()
        p = Parte(nombre, metrica, multiplo=_num(x.get("multiplo")), justificacion=str(x.get("justificacion", "")).strip())
        s.partes.append(p)
        if metrica not in METRICAS:
            p.motivo = f"métrica «{metrica}» desconocida (ingresos, ebit o ebitda)"
            continue
        if p.multiplo is None or p.multiplo <= 0:
            p.motivo = "sin múltiplo positivo del analista"
            continue
        valor_analista, evidencias = _num(x.get("valor")), x.get("evidencia") or []
        if valor_analista is not None:
            # la métrica que el informe no tiene por segmento la da el analista, y solo vale con su cita encontrada
            verificadas = [ev for ev in evidencias if verificar(ev)]
            if not verificadas:
                p.motivo = "la cifra del analista no lleva una cita que se encuentre en su documento y página"
                continue
            ev = verificadas[0]
            p.valor_metrica, p.periodo = valor_analista, str(x.get("periodo", "")).strip()
            p.origen = f"analista, {ev.get('doc', '')} pág. {ev.get('pag', '')}"
            continue
        if metrica != "ingresos":
            p.motivo = f"el informe no tiene el {METRICAS[metrica]} por segmento: lo aporta el analista con su cita"
            continue
        linea = lineas.get(nombre.lower())
        if linea is None or ultimo is None:
            p.motivo = "no es un segmento del apartado 4"
            continue
        h = linea.valores.get(ultimo)
        if h is None or not h.hay_dato:
            p.motivo = f"sin ingresos del segmento en {etiqueta(ultimo)}"
            continue
        p.valor_metrica, p.periodo, p.origen = h.valor, etiqueta(ultimo), "segmentos del apartado 4"
    costes = entradas.get("costes_corporativos") or {}
    if costes:
        valor, evidencias = _num(costes.get("valor")), costes.get("evidencia") or []
        verificadas = [ev for ev in evidencias if verificar(ev)]
        if valor is None or not verificadas:
            s.faltan.append("costes corporativos sin cifra o sin cita que se encuentre en su documento y página")
        else:
            s.costes_corporativos, s.multiplo_costes = abs(valor), _num(costes.get("multiplo"))
            s.costes_origen = f"analista, {verificadas[0].get('doc', '')} pág. {verificadas[0].get('pag', '')}"
            if s.multiplo_costes is None:
                s.faltan.append("costes corporativos sin múltiplo con que capitalizarlos")
    if len([p for p in s.partes if p.ve is not None]) < 2:
        s.faltan.append("menos de dos segmentos valorados: no hay suma de partes")
    for p in s.partes:
        if p.motivo:
            s.faltan.append(f"{p.segmento}: {p.motivo}")
    return s
