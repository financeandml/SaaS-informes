"""Reúne lo que el motor necesita, siempre de las fuentes oficiales, y lo ejecuta (05 §1–§8).

Precio = cierre oficial de Nasdaq en la fecha de valoración (nunca el intradía); rf = 10 años del Tesoro; beta frente a
SPY con cierres de Nasdaq; puente con el último balance (los mismos importes del apartado 9); acciones diluidas por el
método de autocartera o, si falta alguna pieza, las diluidas medias del último trimestre (marcado).
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple

from ..datos.hechos import Periodo, etiqueta_fiscal
from ..rotulos import fallo
from . import comparables as comparables_mod
from .escenarios import Valoracion, valorar
from .puente import acciones_diluidas, puente
from .sensibilidad import Inverso, Matriz, inverso, matriz
from .supuestos import Parametros, leer
from .wacc import Beta, Wacc, beta_bottom_up, beta_regresion, calcular
from ..rutas import CONFIG

__all__ = ["Motor", "ejecutar", "paquete_por_sic", "sectores", "ingresos_anuales"]


@dataclass
class Ntm:
    ingresos: float
    ebitda: float
    bpa: float
    fcf: float
    per: Optional[float]
    ev_ebitda: Optional[float]
    ev_ventas: Optional[float]
    p_fcf: Optional[float]
    peg: Optional[float]
    cagr_bpa: Optional[float]


@dataclass
class Motor:
    parametros: Parametros
    precio: Optional[float]
    fecha_precio: Optional[date]
    valoracion: Optional[Valoracion] = None
    matriz: Optional[Matriz] = None
    inverso: Optional[Inverso] = None
    ntm: Optional[Ntm] = None
    historico_per: List[Tuple[date, float]] = field(default_factory=list)
    comparables: Optional[comparables_mod.Comparables] = None
    ingresos_base: Optional[float] = None
    etiqueta_base: str = ""
    cierre_base: Optional[date] = None
    ev_mercado: Optional[float] = None
    cap_mercado: Optional[float] = None
    dpa_anual: float = 0.0
    bloqueos: List[str] = field(default_factory=list)
    avisos: List[str] = field(default_factory=list)


def sectores() -> dict:
    from ..rutas import leer_yaml
    return leer_yaml(CONFIG / "sectores.yaml")


def paquete_por_sic(sic: str, ingresos: Optional[float] = None, minimo_biotech: Optional[float] = None) -> Tuple[str, Optional[str]]:
    """(paquete propuesto, bloqueo v1 o None) según `config/sectores.yaml`. Los códigos concretos antes que los rangos.
    `ingresos`: los del último ejercicio en USD (None si la SEC no los publica): una biotecnológica por debajo de
    `umbrales.biotech_ingresos_min_musd` queda fuera de la v1 (05 §2)."""
    from ..formato import numero
    datos = sectores()
    try:
        n = int(sic)
    except (TypeError, ValueError):
        return "general", None
    for a, b in datos["bloqueo_v1"]["sic"]:
        if a <= n <= b:
            return "general", datos["bloqueo_v1"]["motivo"]
    bio = datos.get("bloqueo_biotech") or {}
    if any(a <= n <= b for a, b in bio.get("sic", [])):
        if minimo_biotech is None:
            from ..umbrales import umbral
            minimo_biotech = float(umbral("biotech_ingresos_min_musd"))
        if ingresos is None or ingresos < minimo_biotech * 1e6:
            cuanto = "sin ingresos publicados en la SEC" if ingresos is None else f"con {numero(ingresos / 1e6)} mln USD de ingresos en el último ejercicio"
            return "salud_madura", bio["motivo"].format(ingresos=cuanto, minimo=numero(minimo_biotech))
    candidatos = []
    for nombre, pq in datos["paquetes"].items():
        for a, b in pq.get("sic", []):
            if a <= n <= b:
                candidatos.append((b - a, nombre))
    return (min(candidatos)[1] if candidatos else "general"), None


def periodo_propuesto(paquete: str) -> int:
    """El periodo explícito del paquete sectorial (el extremo alto de su horquilla en config/sectores.yaml): el que propone
    el asistente y el que usa el motor si el analista no lo da."""
    pq = (sectores().get("paquetes") or {}).get(paquete) or (sectores().get("paquetes") or {}).get("general") or {}
    horquilla = pq.get("periodo") or [10, 10]
    return int(horquilla[-1])


def ingresos_anuales(facts: dict, obtenido: Optional[date] = None) -> Optional[float]:
    """Los ingresos del último ejercicio publicado en la SEC (sin el informe construido: el paso 1 del asistente)."""
    from ..fuentes import sec
    from ..datos.campos import CAMPOS
    campo = next(c for c in CAMPOS if c.clave == "ingresos")
    hechos = sec.hechos_xbrl(facts, campo, obtenido or date.today())
    anuales = [(p.fin, h.valor) for p, h in hechos.items() if p.meses == 12 and not p.es_instante and h.hay_dato]
    return max(anuales)[1] if anuales else None


def _ultimo(hechos, campo: str, periodos: List[Periodo]) -> Tuple[Optional[float], Optional[Periodo]]:
    for p in sorted(periodos, key=lambda p: p.fin, reverse=True):
        h = hechos.get((campo, p))
        if h is not None and h.hay_dato:
            return h.valor, p
    return None, None


def _ultimo_facts(facts: dict, concepto: str, unidad: str, hasta: date) -> Optional[Tuple[float, date]]:
    filas = (((facts.get("facts") or {}).get("us-gaap") or {}).get(concepto) or {}).get("units", {}).get(unidad, [])
    filas = [f for f in filas if date.fromisoformat(f["end"]) <= hasta and (hasta - date.fromisoformat(f["end"])).days <= 400]
    if not filas:
        return None
    f = max(filas, key=lambda f: (f["end"], f["filed"]))
    return float(f["val"]), date.fromisoformat(f["end"])


def _historico_per(facts: dict, cierres: Dict[date, float], hasta: date) -> List[Tuple[date, float]]:
    """PER de cada cierre de trimestre de los últimos 5 años: cierre oficial / BPA diluido de los 12 meses anteriores
    (ejercicio, o ejercicio + acumulado − acumulado del año anterior). Solo con BPA positivo."""
    from ..fuentes import sec
    filas = (((facts.get("facts") or {}).get("us-gaap") or {}).get("EarningsPerShareDiluted") or {}).get("units", {}).get("USD/shares", [])
    # los cierres de Nasdaq vienen ajustados por splits; el BPA de un depósito anterior a un split, no: se divide por la razón
    splits = [(f, r) for f, r, _ in sec.splits(facts)]
    por_largo: Dict[Tuple[int, date], float] = {}
    presentado: Dict[Tuple[int, date], str] = {}
    for f in filas:
        if "start" not in f:
            continue
        ini, fin = date.fromisoformat(f["start"]), date.fromisoformat(f["end"])
        meses = round((fin - ini).days / 30.44)
        clave = (meses, fin)
        if clave in presentado and presentado[clave] >= f["filed"]:
            continue                                          # la cifra del depósito más reciente manda (reexpresiones)
        valor = float(f["val"])
        for fecha_split, razon in splits:
            if razon and date.fromisoformat(f["filed"]) < fecha_split:
                valor /= razon
        por_largo[clave], presentado[clave] = valor, f["filed"]
    anuales = sorted(fin for (m, fin) in por_largo if m == 12)
    salida = []
    for (m, fin), v in sorted(por_largo.items(), key=lambda kv: kv[0][1]):
        if fin < date(hasta.year - 5, hasta.month, 1) or fin > hasta:
            continue
        if m == 12:
            ttm = v
        elif m in (3, 6, 9):
            previos = [a for a in anuales if a < fin]
            anterior = next((por_largo[(m, d)] for (mm, d) in por_largo if mm == m and abs((fin - d).days - 364) <= 10), None)
            if not previos or anterior is None:
                continue
            ttm = por_largo[(12, previos[-1])] + v - anterior
        else:
            continue
        dias = [d for d in cierres if d <= fin and (fin - d).days <= 7]
        if ttm > 0 and dias:
            salida.append((fin, cierres[max(dias)] / ttm))
    vistos, unicos = set(), []
    for fin, per in salida:
        if fin not in vistos:
            vistos.add(fin)
            unicos.append((fin, per))
    return unicos


def ejecutar(emisor, facts: dict, hechos, periodos: Dict[str, List[Periodo]], datos_entradas: dict, fecha_informe: date,
             acciones_portada: Optional[float], umbrales: dict, desfase_fiscal: int = 0, dividendos: Optional[list] = None) -> Motor:
    from ..fuentes import precio as precio_mod, sec, tesoro
    ingresos_fy, _ = _ultimo(hechos, "ingresos", periodos["anuales"])
    paquete, bloqueo_v1 = paquete_por_sic(emisor.sic, ingresos_fy, umbrales.get("biotech_ingresos_min_musd"))
    p = leer(datos_entradas, fecha_informe, paquete)
    m = Motor(parametros=p, precio=None, fecha_precio=None)
    if bloqueo_v1:
        m.bloqueos.append(f"v1: {bloqueo_v1}")
        return m
    fv = p.fecha_valoracion
    desde = date(fv.year - 5, fv.month, min(fv.day, 28)) - timedelta(days=10)
    try:
        cierres = precio_mod.cierres_nasdaq(emisor.ticker, desde, fv, limite=2000)
        mercado = precio_mod.cierres_nasdaq("SPY", desde, fv, limite=2000, clase="etf")
    except Exception as e:                                                   # la bolsa no respondió
        m.bloqueos.append(f"precio: el histórico de Nasdaq no respondió ({fallo(e)})")
        return m
    dias = sorted(d for d in cierres if d <= fv)
    if not dias:
        m.bloqueos.append("precio: sin cierre oficial de Nasdaq en la fecha de valoración")
        return m
    m.fecha_precio, m.precio = dias[-1], cierres[dias[-1]]
    rf = tesoro.rf_10a(fv)
    if rf is None:
        m.bloqueos.append("rf: el Tesoro no publicó la curva par en la fecha de valoración")
        return m
    # balance del puente: el último instante con deuda publicada (el mismo del apartado 9)
    instantes = periodos["instantes"]
    deuda, p_deuda = _ultimo(hechos, "deuda_bruta", instantes)
    fecha_balance = p_deuda.fin if p_deuda else None
    val = lambda campo: (hechos.get((campo, p_deuda)).valor if p_deuda and hechos.get((campo, p_deuda)) is not None
                         and hechos.get((campo, p_deuda)).hay_dato else None)                                  # noqa: E731
    caja, inversiones, arrend = val("caja"), val("inversiones_cp"), val("arrendamientos")
    trimestres = sorted(periodos["trimestres"], key=lambda q: q.fin)
    diluidas_medias, q_dil = _ultimo(hechos, "acciones_diluidas", trimestres)
    opciones = _ultimo_facts(facts, "ShareBasedCompensationArrangementByShareBasedPaymentAwardOptionsOutstandingNumber", "shares", fv)
    ejercicio = _ultimo_facts(facts, "ShareBasedCompensationArrangementByShareBasedPaymentAwardOptionsOutstandingWeightedAverageExercisePrice", "USD/shares", fv)
    rsu = _ultimo_facts(facts, "ShareBasedCompensationArrangementByShareBasedPaymentAwardEquityInstrumentsOtherThanOptionsNonvestedNumber", "shares", fv)
    cierre_fy = periodos["anuales"][-1].fin if periodos["anuales"] else None
    etq = (lambda q: etiqueta_fiscal(q, cierre_fy, desfase_fiscal)) if cierre_fy else (lambda q: q.clave)
    acciones, nota = acciones_diluidas(acciones_portada, opciones[0] if opciones else None, ejercicio[0] if ejercicio else None,
                                       rsu[0] if rsu else None, m.precio, diluidas_medias, etq(q_dil) if q_dil else "")
    if acciones is None:
        m.bloqueos.append(f"acciones: {nota}")
        return m
    fuente_balance = f"balance a {fecha_balance:%d/%m/%Y} (SEC)" if fecha_balance else "sin balance"
    pte = puente(deuda, arrend, caja, inversiones, None, p.ajustes_puente, p.arrendamientos == "deuda", acciones, nota,
                 fecha_balance, fuente_balance)
    # pesos a valor de mercado
    e_mercado = m.precio * (acciones_portada or acciones)
    d_mercado = (deuda or 0.0) + ((arrend or 0.0) if p.arrendamientos == "deuda" else 0.0)
    m.cap_mercado = e_mercado
    m.ev_mercado = e_mercado + d_mercado - (caja or 0.0) - (inversiones or 0.0)
    b_sem = beta_regresion(cierres, mercado, fv, 2, "semanal")
    b_men = beta_regresion(cierres, mercado, fv, 5, "mensual")
    if p.beta_metodo == "bottom_up" and p.beta_desapalancada is not None:
        beta = beta_bottom_up(p.beta_desapalancada, p.tipo_marginal, d_mercado, e_mercado)
        origen = f"bottom-up: β desapalancada {p.beta_desapalancada:.2f} ({p.beta_fuente}) reapalancada con D/E de mercado"
    elif b_sem is not None:
        beta, origen = b_sem.ajustada, "regresión semanal de 2 años frente a SPY (cierres de Nasdaq), ajuste de Blume"
    else:
        m.bloqueos.append("beta: sin cierres suficientes para la regresión y sin beta bottom-up")
        return m
    kd, kd_origen = p.kd, p.kd_fuente or "analista"
    if p.kd_metodo == "rating_sintetico" and kd is None:
        kd_origen = "falta la tabla de rating sintético del analista (con fuente y fecha)"
    w = calcular(rf.valor, rf.fecha, beta, origen, p.erp, p.prima, kd, kd_origen, p.tipo_marginal, e_mercado, d_mercado,
                 b_sem, b_men, umbrales.get("beta_r2_min", 0.10))
    # año base
    anuales = sorted(periodos["anuales"], key=lambda a: a.fin)
    if p.anio_base == "ultimos_12_meses" and len(trimestres) >= 4:
        ult = trimestres[-4:]
        valores = [hechos.get(("ingresos", q)) for q in ult]
        if all(v is not None and v.hay_dato for v in valores):
            m.ingresos_base = sum(v.valor for v in valores)
            m.etiqueta_base = f"UDM a {etq(ult[-1])}"
    if m.ingresos_base is None:
        v, a = _ultimo(hechos, "ingresos", anuales)
        m.ingresos_base, m.etiqueta_base = v, (etq(a) if a else "")
    m.cierre_base = max((a.fin for a in anuales if a.fin < fv), default=None)
    if m.ingresos_base is None or m.cierre_base is None:
        m.bloqueos.append("año base: sin ingresos verificados o sin cierre de ejercicio anterior a la valoración")
        return m
    # dividendos: los últimos cuatro pagos de la bolsa, llevados al horizonte
    pagos = sorted((d for d in (dividendos or []) if d.ex and d.ex <= fv and d.importe), key=lambda d: d.ex)[-4:]
    m.dpa_anual = sum(d.importe for d in pagos)
    dpa_h = m.dpa_anual * p.horizonte_meses / 12
    v = valorar(p, w, pte, m.precio, m.ingresos_base, m.cierre_base, umbrales, dpa_h)
    m.valoracion = v
    m.bloqueos += v.bloqueos
    m.avisos += v.avisos
    if v.resultados.get("base") is not None:
        m.matriz = matriz(v, m.ingresos_base, m.cierre_base, umbrales)
        m.inverso = inverso(v, m.ingresos_base, m.cierre_base, umbrales)
        m.ntm = _ntm(v, m, hechos, trimestres, p)
    m.historico_per = _historico_per(facts, cierres, fv)
    from .sector import comprobar                       # 05 §2: las comprobaciones del paquete (avisos, no bloqueos)
    m.avisos += comprobar(p, hechos, periodos, facts, m, w, arrend, umbrales.get("sector") or {}, sectores())
    if datos_entradas.get("comparables"):
        m.comparables = comparables_mod.construir(datos_entradas["comparables"], m.fecha_precio, umbrales)
    return m


def _ntm(v: Valoracion, m: Motor, hechos, trimestres: List[Periodo], p: Parametros) -> Ntm:
    b = v.base.proyeccion
    f = b.fraccion
    mezcla = lambda serie: f * serie[0] + (1 - f) * serie[1]                        # noqa: E731
    intereses, _ = 0.0, None
    ult = trimestres[-4:]
    valores = [hechos.get(("intereses", q)) for q in ult]
    if valores and all(x is not None and x.hay_dato for x in valores):
        intereses = abs(sum(x.valor for x in valores))
    acciones = v.puente.acciones
    bpa_serie = [(n - intereses * (1 - p.tipo_marginal)) / acciones for n in b.nopat]
    ingresos, ebitda, bpa = mezcla(b.ingresos), mezcla(b.ebitda), mezcla(bpa_serie)
    fcf = mezcla([x - intereses * (1 - p.tipo_marginal) for x in b.fcff])
    per = m.precio / bpa if bpa > 0 else None
    cagr = (bpa_serie[3] / bpa_serie[0]) ** (1 / 3) - 1 if len(bpa_serie) > 3 and bpa_serie[0] > 0 and bpa_serie[3] > 0 else None
    return Ntm(ingresos, ebitda, bpa, fcf, per, m.ev_mercado / ebitda if ebitda > 0 else None,
               m.ev_mercado / ingresos if ingresos > 0 else None, m.cap_mercado / fcf if fcf > 0 else None,
               per / (cagr * 100) if per and cagr and cagr > 0 else None, cagr)
