"""Entradas del paso 7 (04) ya validadas y en tanto por uno: parámetros generales y tres escenarios.

Las series se dan en los años 1, 2, 3, 5 y N; el resto se interpola linealmente (04: «el resto se interpola»). Un año
dado explícitamente manda sobre la interpolación. Los porcentajes llegan en % (5 = 5 %) y aquí se pasan a tanto por uno.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Mapping, Optional

__all__ = ["Escenario", "Parametros", "leer", "serie", "NOMBRES"]

NOMBRES = ("pesimista", "base", "optimista")


def serie(dada, n: int, pct: bool = True) -> List[float]:
    """{"1": 13.3, "2": 11.5, "5": 8.5, "N": 5.5} → lista de n valores (tanto por uno si `pct`). Una lista se toma tal
    cual (y se alarga con su último valor); un número, constante."""
    escala = 0.01 if pct else 1.0
    if dada is None:
        raise ValueError("serie vacía")
    if isinstance(dada, (int, float)):
        return [float(dada) * escala] * n
    if isinstance(dada, list):
        valores = [float(v) * escala for v in dada][:n]
        return valores + [valores[-1]] * (n - len(valores))
    puntos: Dict[int, float] = {}
    for k, v in dada.items():
        anio = n if str(k).upper() == "N" else int(k)
        if 1 <= anio <= n:
            puntos[anio] = float(v) * escala
    if not puntos:
        raise ValueError("serie sin años válidos")
    anios = sorted(puntos)
    salida = []
    for t in range(1, n + 1):
        if t in puntos:
            salida.append(puntos[t])
        elif t < anios[0]:
            salida.append(puntos[anios[0]])
        elif t > anios[-1]:
            salida.append(puntos[anios[-1]])
        else:
            a = max(x for x in anios if x < t)
            b = min(x for x in anios if x > t)
            salida.append(puntos[a] + (puntos[b] - puntos[a]) * (t - a) / (b - a))
    return salida


@dataclass
class Escenario:
    nombre: str
    probabilidad: float
    narrativa: str
    crecimiento: List[float]
    margen: List[float]
    impuesto: List[float]
    da: List[float]
    capex: List[float]
    fm: float                                  # ΔFM = Δingresos × fm (negativo: el fondo de maniobra libera caja)
    sbc: List[float]
    paquete: Dict[str, List[float]] = field(default_factory=dict)   # partidas del paquete que restan del FCFF
    wacc_ajuste: float = 0.0                   # en tanto por uno
    g: float = 0.025
    ronic: Optional[float] = None
    multiplo_salida: Optional[float] = None


@dataclass
class Parametros:
    fecha_valoracion: date
    anio_base: str = "ultimo_ejercicio"
    periodo: int = 10
    mitad_de_anio: bool = True
    horizonte_meses: int = 12
    sbc_politica: str = "coste_de_caja"
    arrendamientos: str = "fuera_de_deuda"
    paquete: str = "general"
    paquete_propuesto: str = "general"                  # el del SIC (05 §2); `paquete` es el que confirma el analista (paso 1)
    paquete_confirmado: bool = False
    erp: float = 0.05
    erp_fuente: str = ""
    beta_metodo: str = "regresion"
    beta_desapalancada: Optional[float] = None
    beta_fuente: str = ""
    prima: float = 0.0
    kd_metodo: str = "rendimiento_bonos"
    kd: Optional[float] = None
    kd_fuente: str = ""
    tipo_marginal: float = 0.21
    tv_metodo: str = "value_driver"
    bin_inicial: float = 0.0
    ajustes_puente: List[dict] = field(default_factory=list)
    escenarios: Dict[str, Escenario] = field(default_factory=dict)
    mult_objetivos: List[dict] = field(default_factory=list)
    sotp: dict = field(default_factory=dict)
    faltas: List[str] = field(default_factory=list)       # lo que falta o no valida: bloqueos del paso 7


def leer(datos: Mapping, fecha_informe: date, paquete_propuesto: str = "general") -> Parametros:
    """`datos`: el JSON de entradas completo. Lo que falta queda en `faltas`, nunca con un valor inventado."""
    val, wacc, tv = datos.get("val") or {}, datos.get("wacc") or {}, datos.get("tv") or {}
    meta = datos.get("meta") or {}                      # paso 1 (04): fecha de valoración y sector del analista
    faltas: List[str] = []
    fv = meta.get("fecha_valoracion")
    p = Parametros(fecha_valoracion=date.fromisoformat(fv) if fv else fecha_informe)
    p.anio_base = val.get("anio_base", p.anio_base)
    p.paquete, p.paquete_propuesto = meta.get("sector") or paquete_propuesto, paquete_propuesto
    p.paquete_confirmado = bool(meta.get("sector"))
    # los valores de partida salen de la misma fuente que la propuesta del asistente (config/propuestas.yaml, regla 13)
    from ..entradas.proponer import por_defecto
    from ..umbrales import umbral
    from .datos import periodo_propuesto
    p.periodo = int(val.get("periodo_explicito", periodo_propuesto(p.paquete)))
    if not 5 <= p.periodo <= 15:
        faltas.append(f"val.periodo_explicito: {p.periodo} (entre 5 y 15)")
    p.mitad_de_anio = bool(val.get("mitad_de_anio", por_defecto("val.mitad_de_anio")))
    p.horizonte_meses = int(val.get("horizonte_meses", umbral("horizonte_meses_defecto")))
    if not 6 <= p.horizonte_meses <= 36:
        faltas.append(f"val.horizonte_meses: {p.horizonte_meses} (entre 6 y 36)")
    p.sbc_politica = val.get("sbc", por_defecto("val.sbc"))
    p.arrendamientos = val.get("arrendamientos", por_defecto("val.arrendamientos"))
    p.bin_inicial = float(val.get("bin_inicial", 0.0)) * 1e6
    p.ajustes_puente = list(val.get("ajustes_puente") or [])
    if wacc.get("erp") is None or not wacc.get("erp_fuente"):
        faltas.append("wacc.erp: prima de riesgo de mercado con fuente y fecha")
    p.erp = float(wacc.get("erp", 5.0)) / 100
    p.erp_fuente = wacc.get("erp_fuente", "")
    p.beta_metodo = wacc.get("beta_metodo", por_defecto("wacc.beta_metodo"))
    if wacc.get("beta_desapalancada") is not None:
        p.beta_desapalancada = float(wacc["beta_desapalancada"])
    p.beta_fuente = wacc.get("beta_fuente", "")
    if p.beta_metodo == "bottom_up" and (p.beta_desapalancada is None or not p.beta_fuente):
        faltas.append("wacc.beta_desapalancada: obligatoria con fuente en el método bottom-up")
    p.prima = float(wacc.get("prima", por_defecto("wacc.prima"))) / 100
    if p.prima and not wacc.get("prima_justificacion"):
        faltas.append("wacc.prima: distinta de cero exige justificación")
    p.kd_metodo = wacc.get("kd_metodo", por_defecto("wacc.kd_metodo"))
    if wacc.get("kd") is not None:
        p.kd = float(wacc["kd"]) / 100
    p.kd_fuente = wacc.get("kd_fuente", "")
    marginal = float(por_defecto("wacc.tipo_marginal"))
    p.tipo_marginal = float(wacc.get("tipo_marginal", marginal)) / 100
    if abs(p.tipo_marginal - marginal / 100) > 1e-9 and not wacc.get("tipo_marginal_justificacion"):
        faltas.append(f"wacc.tipo_marginal: distinto del {marginal:g} % exige justificación")
    p.tv_metodo = tv.get("metodo", por_defecto("tv.metodo"))
    p.mult_objetivos = list((datos.get("mult") or {}).get("objetivos") or [])
    p.sotp = dict(datos.get("sotp") or {})
    esc = datos.get("esc") or {}
    for nombre in NOMBRES:
        e = esc.get(nombre)
        if not e:
            faltas.append(f"esc.{nombre}: falta el escenario")
            continue
        try:
            n = p.periodo
            p.escenarios[nombre] = Escenario(
                nombre=nombre, probabilidad=float(e["probabilidad"]) / 100, narrativa=e.get("narrativa", ""),
                crecimiento=serie(e["crecimiento_ingresos"], n), margen=serie(e["margen_ebit"], n),
                impuesto=serie(e["impuesto_caja"], n), da=serie(e["da_pct"], n), capex=serie(e["capex_pct"], n),
                fm=float(e["fm_pct_incremental"]) / 100, sbc=serie(e["sbc_pct"], n),
                paquete={k: serie(v, n) for k, v in (e.get("paquete") or {}).items()},
                wacc_ajuste=float(e.get("wacc_ajuste_pp", 0)) / 100, g=float(e.get("g", 2.5)) / 100,
                ronic=float(e["ronic"]) / 100 if e.get("ronic") is not None else None,
                multiplo_salida=float(e["multiplo_salida"]) if e.get("multiplo_salida") is not None else None)
        except (KeyError, ValueError) as ex:
            faltas.append(f"esc.{nombre}: {ex}")
            continue
        if not e.get("narrativa"):
            faltas.append(f"esc.{nombre}.narrativa: obligatoria (15–50 palabras)")
        if float(e.get("wacc_ajuste_pp", 0)) and not e.get("wacc_ajuste_justificacion"):
            faltas.append(f"esc.{nombre}.wacc_ajuste_pp: distinto de cero exige justificación")
    p.faltas = faltas
    return p
