"""Reúne lo que el motor necesita, siempre de las fuentes oficiales, y lo ejecuta (05 §1–§8).

Precio = cierre oficial de Nasdaq en la fecha de valoración (nunca el intradía); rf = 10 años del Tesoro; beta frente a
SPY con cierres de Nasdaq; puente con el último balance (los mismos importes del apartado 9); acciones diluidas por el
método de autocartera o, si falta alguna pieza, las diluidas medias del último trimestre (marcado).

B4 · Emisor de BME (despacho en `fuentes/emisores.py`): cierre oficial de BME de la última sesión con negociación; rf de la
curva AAA del BCE; beta frente al índice de BME del segmento, solo con sesiones con negociación y un mínimo de ellas
(`umbrales.beta_sesiones_min`; por debajo, bloqueo con motivo, nunca SPY); UDM semestral (ejercicio + 1S − 1S anterior);
acciones diluidas = las del último periodo publicado (sin opciones ni RSU en XBRL); DPA = pagos de los 12 meses anteriores
o N/A con motivo; sin SIC no se propone paquete (lo elige el analista), y la regla 7 sale de la clasificación de la bolsa.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Dict, List, Mapping, Optional, Tuple

from ..datos.hechos import Hecho, Periodo, etiqueta_fiscal, na
from ..rotulos import fallo
from . import comparables as comparables_mod, multiplos as multiplos_mod
from .escenarios import Valoracion, valorar
from .puente import acciones_diluidas, puente
from .sensibilidad import Inverso, Matriz, inverso, matriz
from .supuestos import Parametros, leer
from .wacc import Beta, Wacc, beta_bottom_up, beta_regresion, calcular
from ..rutas import CONFIG

__all__ = ["Motor", "ejecutar", "paquete_por_sic", "paquete_del_emisor", "sectores", "ingresos_anuales"]


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
    dpa_anual: Optional[float] = 0.0           # None = sin dato (N/A con `dpa_motivo`), nunca un cero de relleno
    bloqueos: List[str] = field(default_factory=list)
    avisos: List[str] = field(default_factory=list)
    # B4: el mercado y la moneda del emisor (rótulos «mln EUR») y el texto de origen de precio, beta y rf, del mismo sitio
    # que pidió cada serie (`fuentes/emisores.py`, regla 13)
    moneda: str = "USD"
    mercado: str = "sec"
    fuente_precio: str = ""
    fuente_beta: str = ""
    fuente_rf: str = ""
    dpa_motivo: str = ""
    # los ingresos del ejercicio de hace cinco años: el «histórico 5 años» del DCF inverso son cinco intervalos, seis
    # ejercicios; con los cinco del informe salía un CAGR de cuatro con el rótulo de cinco (fallos [15] y [44])
    ingresos_hace_5: Optional[Hecho] = None


def _ingresos_hace_5(hechos, anuales: List[Periodo], facts: Optional[dict], fecha: date) -> Optional[Hecho]:
    """De los hechos si están; si no, de la SEC con el mismo mapeo del cuadro de resultados. Sin cifra publicada, N/A
    con motivo: nunca un CAGR de otro número de años."""
    if not anuales:
        return None
    ult = anuales[-1].fin
    objetivo = date(ult.year - 5, ult.month, min(ult.day, 28))
    cerca = lambda q: q.meses == 12 and abs((q.fin - objetivo).days) <= 10          # noqa: E731  (52/53 semanas)
    for (c, q), h in hechos.items():
        if c == "ingresos" and cerca(q) and h.hay_dato:
            return h
    if facts:
        from ..datos.campos import campo
        from ..fuentes import sec
        for q, h in sorted(sec.hechos_xbrl(facts, campo("ingresos"), fecha).items(), key=lambda x: x[0].fin):
            if cerca(q) and h.hay_dato:
                return h
    return na("ingresos", Periodo.anual(objetivo), f"no hay ingresos publicados del ejercicio cerrado hacia el {objetivo:%d/%m/%Y} "
              f"(hacen falta seis ejercicios para un crecimiento de cinco años)")


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


def paquete_del_emisor(emisor, ingresos: Optional[float] = None, umbrales: Optional[Mapping] = None) -> Tuple[str, Optional[str]]:
    """(paquete propuesto, bloqueo v1 o None) de un emisor de cualquier mercado.

    SEC: por su SIC (`paquete_por_sic`), como siempre. BME: sin SIC no hay propuesta automática —el paquete vacío dice
    «lo elige el analista en el paso 1»—, pero la regla 7 sigue: financieras, inmobiliarias y SOCIMI, y farmacéuticas o
    biotecnológicas por debajo del mínimo de ingresos, quedan bloqueadas por la clasificación sectorial de la bolsa
    (`config/sectores.yaml › bloqueo_bme`). `ingresos`: los del último ejercicio en la moneda del emisor."""
    u = umbrales or {}
    if getattr(emisor, "mercado", "sec") != "bme":
        return paquete_por_sic(emisor.sic, ingresos, u.get("biotech_ingresos_min_musd"))
    from ..fuentes import emisores
    from ..formato import numero
    datos = sectores().get("bloqueo_bme") or {}
    try:
        sector, subsector = emisores.clasificacion_bolsa(emisor)
    except Exception as e:                                   # sin la ficha no se puede descartar un paquete bloqueado
        return "", f"la ficha del valor de BME no respondió ({fallo(e)}): no se puede comprobar la regla 7 (sectores bloqueados)"
    if not sector:
        return "", "la ficha del valor de BME no publica su sector: no se puede comprobar la regla 7 (sectores bloqueados)"
    if sector in (datos.get("sectores") or []):
        return "", datos["motivo"].format(sector=f"{sector}/{subsector}")
    if f"{sector}/{subsector}" in (datos.get("biotech") or []):
        from ..umbrales import umbral
        minimo = float(u.get("biotech_ingresos_min_meur") or umbral("biotech_ingresos_min_meur"))
        if ingresos is None or ingresos < minimo * 1e6:
            cuanto = ("sin ingresos publicados en sus cuentas" if ingresos is None
                      else f"con {numero(ingresos / 1e6)} mln {emisor.moneda or 'EUR'} de ingresos en el último ejercicio")
            return "", datos["motivo_biotech"].format(ingresos=cuanto, minimo=numero(minimo))
    return "", None


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


def _ultimo_facts(facts: Optional[dict], concepto: str, unidad: str, hasta: date) -> Optional[Tuple[float, date]]:
    # un emisor sin XBRL (BME) no trae companyfacts: sin la pieza, None, y la dilución sale de lo publicado
    filas = ((((facts or {}).get("facts") or {}).get("us-gaap") or {}).get(concepto) or {}).get("units", {}).get(unidad, [])
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


def _historico_per_semestral(hechos, anuales: List[Periodo], semestres: List[Periodo], cierres: Dict[date, float], hasta: date,
                             antiguedad: int) -> List[Tuple[date, float]]:
    """PER al cierre de cada ejercicio y de cada 1S de los últimos 5 años de un emisor sin XBRL: cierre oficial / BPA
    diluido de los doce meses (el del ejercicio, o ejercicio + 1S − 1S anterior: la misma construcción que
    `_historico_per` hace con los acumulados de la SEC). El cierre es el de la última sesión con negociación de los
    `antiguedad` días anteriores. Solo con BPA positivo; sin BPA publicado, ningún punto (nunca uno estimado)."""
    anuales = sorted(anuales, key=lambda a: a.fin)
    limite = date(hasta.year - 5, hasta.month, 1)
    puntos: Dict[date, float] = {}
    for i, fy in enumerate(anuales):
        hasta_fy = anuales[:i + 1]
        candidatos = [(fy.fin, multiplos_mod.udm(hechos, "bpa_diluido", hasta_fy, [])[0])]
        v_s, usados, _ = multiplos_mod.udm(hechos, "bpa_diluido", hasta_fy, semestres)
        if len(usados) == 3:
            candidatos.append((usados[1].fin, v_s))
        for fin, bpa in candidatos:
            if bpa is None or bpa <= 0 or not limite <= fin <= hasta:
                continue
            dias = [d for d in cierres if d <= fin and (fin - d).days <= antiguedad]
            if dias:
                puntos[fin] = cierres[max(dias)] / bpa
    return sorted(puntos.items())


def _dpa_12_meses(dividendos: Optional[list], fv: date) -> Tuple[Optional[float], str]:
    """DPA de un emisor de fuera de la SEC: los pagos con fecha ex en los 12 meses anteriores a la valoración.

    `dividendos` None = la fuente no da el histórico: DPA N/A con motivo (nunca un cero de relleno). Lista vacía = la
    fuente lo da y no hubo pagos: un cero de verdad. Un pago sin importe publicado deja el DPA N/A."""
    if dividendos is None:
        return None, "sin histórico de dividendos de la fuente oficial del emisor"
    try:
        desde = fv.replace(year=fv.year - 1)
    except ValueError:                                  # 29 de febrero
        desde = fv.replace(year=fv.year - 1, day=28)
    pagos = [d for d in dividendos if d.ex and desde < d.ex <= fv]
    tramo = f"con fecha ex entre el {desde + timedelta(days=1):%d/%m/%Y} y el {fv:%d/%m/%Y}"
    if any(d.importe is None for d in pagos):
        return None, f"un pago {tramo} sin importe publicado"
    return sum(d.importe for d in pagos), f"{len(pagos)} pagos {tramo}"


def _betas_por_sesiones(cierres: Dict[date, float], mercado: Dict[date, float], fv: date, minimo: int
                        ) -> Tuple[Optional[Beta], Optional[Beta], str]:
    """Las betas semanal (2 años) y mensual (5 años) de un valor que no cotiza todos los días: solo con sus sesiones con
    negociación, el mercado en esas mismas fechas, y al menos `minimo` sesiones en la ventana. Por debajo, None con el
    motivo (el de la semanal, que es la que usa el WACC): una beta de pocas sesiones no se sustituye por otro mercado."""
    salida: List[Optional[Beta]] = []
    motivo = ""
    for anios, frecuencia in ((2, "semanal"), (5, "mensual")):
        desde = date(fv.year - anios, fv.month, min(fv.day, 28))
        n = sum(1 for d in cierres if desde <= d <= fv)
        if n < minimo:
            salida.append(None)
            if anios == 2:
                motivo = (f"solo {n} sesiones con negociación en los 2 años anteriores a la valoración (mínimo {minimo}, "
                          "config/umbrales.yaml › beta_sesiones_min)")
            continue
        salida.append(beta_regresion(cierres, mercado, fv, anios, frecuencia, solo_dias_comunes=True))
        if anios == 2 and salida[-1] is None:
            motivo = f"{n} sesiones con negociación, pero menos de 20 semanas con cierre del valor y del índice"
    return salida[0], salida[1], motivo


def ejecutar(emisor, facts: dict, hechos, periodos: Dict[str, List[Periodo]], datos_entradas: dict, fecha_informe: date,
             acciones_portada: Optional[float], umbrales: dict, desfase_fiscal: int = 0, dividendos: Optional[list] = None) -> Motor:
    from ..fuentes import emisores as emisores_mod
    ingresos_fy, _ = _ultimo(hechos, "ingresos", periodos["anuales"])
    paquete, bloqueo_v1 = paquete_del_emisor(emisor, ingresos_fy, umbrales)
    p = leer(datos_entradas, fecha_informe, paquete, getattr(emisor, "mercado", "sec"))
    de_la_sec = getattr(emisor, "mercado", "sec") != "bme"
    m = Motor(parametros=p, precio=None, fecha_precio=None, moneda=getattr(emisor, "moneda", "") or "USD",
              mercado="sec" if de_la_sec else "bme")
    if bloqueo_v1:
        m.bloqueos.append(f"v1: {bloqueo_v1}")
        return m
    if not p.paquete:
        m.bloqueos.append("sector: el emisor no tiene SIC y el sistema no propone paquete sectorial; el analista lo elige en el paso 1")
        return m
    fv = p.fecha_valoracion
    desde = date(fv.year - 5, fv.month, min(fv.day, 28)) - timedelta(days=10)
    bolsa = emisores_mod.bolsa_precio(emisor)
    try:
        cierres = emisores_mod.cierres(emisor, desde, fv)
        mercado, rotulo_beta = emisores_mod.cierres_mercado(emisor, desde, fv)
    except Exception as e:                                                   # la bolsa no respondió
        m.bloqueos.append(f"precio: el histórico de {bolsa} no respondió ({fallo(e)})")
        return m
    dias = sorted(d for d in cierres if d <= fv)
    if not dias:
        m.bloqueos.append(f"precio: sin cierre oficial de {bolsa} en la fecha de valoración")
        return m
    antiguedad = emisores_mod.antiguedad_max_cierre(emisor)
    if antiguedad is not None and (fv - dias[-1]).days > antiguedad:
        m.bloqueos.append(f"precio: sin sesiones con negociación en {bolsa} en los {antiguedad} días anteriores a la valoración "
                          f"(la última, el {dias[-1]:%d/%m/%Y})")
        return m
    m.fecha_precio, m.precio = dias[-1], cierres[dias[-1]]
    m.fuente_precio = f"cierre oficial de {bolsa} del {m.fecha_precio:%d/%m/%Y}" + (
        "" if antiguedad is None or m.fecha_precio == fv else f", última sesión con negociación hasta el {fv:%d/%m/%Y}")
    rf, m.fuente_rf = emisores_mod.rf(emisor, fv)
    if rf is None:
        m.bloqueos.append(f"rf: {m.fuente_rf} sin dato publicado en la fecha de valoración")
        return m
    # balance del puente: el último instante con deuda publicada (el mismo del apartado 9)
    instantes = periodos["instantes"]
    deuda, p_deuda = _ultimo(hechos, "deuda_bruta", instantes)
    fecha_balance = p_deuda.fin if p_deuda else None
    val = lambda campo: (hechos.get((campo, p_deuda)).valor if p_deuda and hechos.get((campo, p_deuda)) is not None
                         and hechos.get((campo, p_deuda)).hay_dato else None)                                  # noqa: E731
    caja, inversiones, arrend = val("caja"), val("inversiones_cp"), val("arrendamientos")
    inversiones_lp = val("inversiones_lp")
    if inversiones_lp and p.inversiones_lp is None:
        from ..formato import numero
        m.avisos.append(f"val.inversiones_lp: la compañía tiene {numero(inversiones_lp / 1e6)} mln {m.moneda} de valores negociables a "
                        f"largo plazo a {fecha_balance:%d/%m/%Y}; confirme en el paso 7 si entran en el puente (hoy, fuera)")
    trimestres = sorted(periodos["trimestres"], key=lambda q: q.fin)
    anuales = sorted(periodos["anuales"], key=lambda a: a.fin)
    semestres = multiplos_mod.semestres_de(periodos)
    # las acciones del último periodo publicado: el trimestre en la SEC; el semestre o el ejercicio en un emisor semestral
    recientes = sorted(set(semestres) | set(anuales), key=lambda q: q.fin) if semestres else trimestres
    diluidas_medias, q_dil = _ultimo(hechos, "acciones_diluidas", recientes)
    basicas_medias = (hechos.get(("acciones_basicas", q_dil)).valor if q_dil and hechos.get(("acciones_basicas", q_dil)) is not None
                      and hechos.get(("acciones_basicas", q_dil)).hay_dato else None)
    # sin XBRL (BME) no hay opciones ni RSU publicadas como hecho: quedan None y no se inventa su dilución
    opciones = _ultimo_facts(facts, "ShareBasedCompensationArrangementByShareBasedPaymentAwardOptionsOutstandingNumber", "shares", fv)
    ejercicio = _ultimo_facts(facts, "ShareBasedCompensationArrangementByShareBasedPaymentAwardOptionsOutstandingWeightedAverageExercisePrice", "USD/shares", fv)
    rsu = _ultimo_facts(facts, "ShareBasedCompensationArrangementByShareBasedPaymentAwardEquityInstrumentsOtherThanOptionsNonvestedNumber", "shares", fv)
    cierre_fy = periodos["anuales"][-1].fin if periodos["anuales"] else None
    if semestres:
        etq = lambda q: multiplos_mod.etiqueta(q, anuales, desfase_fiscal)                                       # noqa: E731
    else:
        etq = (lambda q: etiqueta_fiscal(q, cierre_fy, desfase_fiscal)) if cierre_fy else (lambda q: q.clave)  # noqa: E731
    acciones, nota = acciones_diluidas(acciones_portada, opciones[0] if opciones else None, ejercicio[0] if ejercicio else None,
                                       rsu[0] if rsu else None, m.precio, diluidas_medias, etq(q_dil) if q_dil else "",
                                       basicas_medias, p.dilucion_adicional,
                                       sin_dilucion_publicada=getattr(emisor, "mercado", "sec") != "sec")
    if acciones is None:
        m.bloqueos.append(f"acciones: {nota}")
        return m
    if not de_la_sec:
        # `acciones_diluidas` redacta su motivo para la SEC; el informe dice de dónde salen de verdad
        nota = nota.replace("la SEC no publica", f"las {emisores_mod.fuente_cuentas(emisor)} no traen")
    fuente_balance = f"balance a {fecha_balance:%d/%m/%Y} ({emisores_mod.fuente_cuentas(emisor)})" if fecha_balance else "sin balance"
    lp = inversiones_lp if p.inversiones_lp == "incluir" else None
    pte = puente(deuda, arrend, caja, inversiones, None, p.ajustes_puente, p.arrendamientos == "deuda", acciones, nota,
                 fecha_balance, fuente_balance, lp)
    # pesos a valor de mercado: E con las mismas acciones que el valor por acción (A4, fallo [8]); la capitalización de
    # los múltiplos, con las de la portada, como la publica la bolsa
    e_mercado = m.precio * acciones
    d_mercado = (deuda or 0.0) + ((arrend or 0.0) if p.arrendamientos == "deuda" else 0.0)
    m.cap_mercado = m.precio * (acciones_portada or acciones)
    m.ev_mercado = m.cap_mercado + d_mercado - (caja or 0.0) - (inversiones or 0.0) - (lp or 0.0)
    motivo_beta = ""
    if de_la_sec:
        b_sem = beta_regresion(cierres, mercado, fv, 2, "semanal")
        b_men = beta_regresion(cierres, mercado, fv, 5, "mensual")
    else:
        from ..umbrales import umbral
        b_sem, b_men, motivo_beta = _betas_por_sesiones(cierres, mercado, fv, int(umbrales.get("beta_sesiones_min") or umbral("beta_sesiones_min")))
    if p.beta_metodo == "bottom_up" and p.beta_desapalancada is not None:
        beta = beta_bottom_up(p.beta_desapalancada, p.tipo_marginal, d_mercado, e_mercado)
        origen = f"bottom-up: β desapalancada {p.beta_desapalancada:.2f} ({p.beta_fuente}) reapalancada con D/E de mercado"
    elif b_sem is not None:
        beta, origen = b_sem.ajustada, f"regresión semanal de 2 años {rotulo_beta}, ajuste de Blume"
    else:
        m.bloqueos.append(f"beta: {motivo_beta}: sin regresión {rotulo_beta} y sin beta bottom-up (paso 7); no se sustituye por otro mercado"
                          if motivo_beta else "beta: sin cierres suficientes para la regresión y sin beta bottom-up")
        return m
    m.fuente_beta = origen
    kd, kd_origen = p.kd, p.kd_fuente or "analista"
    if p.kd_metodo == "rating_sintetico" and kd is None:
        kd_origen = "falta la tabla de rating sintético del analista (con fuente y fecha)"
    w = calcular(rf.valor, rf.fecha, beta, origen, p.erp, p.prima, kd, kd_origen, p.tipo_marginal, e_mercado, d_mercado,
                 b_sem, b_men, umbrales.get("beta_r2_min", 0.10))
    w.rf_fuente = m.fuente_rf
    # año base: UDM de cuatro trimestres (SEC) o de ejercicio + 1S − 1S anterior (semestral), si el analista lo pide
    if p.anio_base == "ultimos_12_meses" and semestres:
        v_udm, usados, motivo_udm = multiplos_mod.udm(hechos, "ingresos", anuales, semestres)
        if v_udm is not None and len(usados) == 3:
            m.ingresos_base, m.etiqueta_base = v_udm, f"UDM a {etq(usados[1])}"
        elif motivo_udm:
            m.avisos.append(f"año base: sin UDM ({motivo_udm}); se toma el último ejercicio")
    elif p.anio_base == "ultimos_12_meses" and len(trimestres) >= 4:
        ult = trimestres[-4:]
        valores = [hechos.get(("ingresos", q)) for q in ult]
        if all(v is not None and v.hay_dato for v in valores):
            m.ingresos_base = sum(v.valor for v in valores)
            m.etiqueta_base = f"UDM a {etq(ult[-1])}"
    if m.ingresos_base is None:
        v, a = _ultimo(hechos, "ingresos", anuales)
        m.ingresos_base, m.etiqueta_base = v, (etq(a) if a else "")
    m.cierre_base = max((a.fin for a in anuales if a.fin < fv), default=None)
    p.cierres_publicados = sorted(a.fin for a in anuales if a.fin < fv)
    m.ingresos_hace_5 = _ingresos_hace_5(hechos, anuales, facts, fv)
    if m.ingresos_base is None or m.cierre_base is None:
        m.bloqueos.append("año base: sin ingresos verificados o sin cierre de ejercicio anterior a la valoración")
        return m
    if de_la_sec:
        # dividendos: los últimos cuatro pagos de la bolsa, llevados al horizonte
        pagos = sorted((d for d in (dividendos or []) if d.ex and d.ex <= fv and d.importe), key=lambda d: d.ex)[-4:]
        m.dpa_anual = sum(d.importe for d in pagos)
    else:
        m.dpa_anual, m.dpa_motivo = _dpa_12_meses(dividendos, fv)
        if m.dpa_anual is None:
            m.avisos.append(f"DPA N/A: {m.dpa_motivo}; el valor a {p.horizonte_meses} meses no descuenta dividendos")
    dpa_h = (m.dpa_anual or 0.0) * p.horizonte_meses / 12
    v = valorar(p, w, pte, m.precio, m.ingresos_base, m.cierre_base, umbrales, dpa_h)
    m.valoracion = v
    m.bloqueos += v.bloqueos
    m.avisos += v.avisos
    if v.resultados.get("base") is not None:
        m.matriz = matriz(v, m.ingresos_base, m.cierre_base, umbrales)
        m.inverso = inverso(v, m.ingresos_base, m.cierre_base, umbrales)
        if semestres:
            intereses, _, motivo_i = multiplos_mod.udm(hechos, "intereses", anuales, semestres)
            if intereses is None:
                m.avisos.append(f"NTM: sin gastos financieros de los últimos doce meses ({motivo_i}): los múltiplos NTM quedan N/A")
            else:
                m.ntm = _ntm(v, m, hechos, trimestres, p, abs(intereses))
        else:
            m.ntm = _ntm(v, m, hechos, trimestres, p)
    m.historico_per = (_historico_per(facts, cierres, fv) if de_la_sec
                       else _historico_per_semestral(hechos, anuales, semestres, cierres, fv, antiguedad or 0))
    m.avisos += hechos_materiales_sin_citar(emisor, datos_entradas, fv)
    from .sector import comprobar                       # 05 §2: las comprobaciones del paquete (avisos, no bloqueos)
    m.avisos += comprobar(p, hechos, periodos, facts, m, w, arrend, umbrales.get("sector") or {}, sectores())
    if datos_entradas.get("comparables"):
        m.comparables = comparables_mod.construir(datos_entradas["comparables"], m.fecha_precio, umbrales)
    return m


_ITEMS_MATERIALES = {"1.01": "acuerdo material", "2.01": "adquisición o venta de activos", "3.02": "venta de valores no registrados"}


def hechos_materiales_sin_citar(emisor, datos_entradas: dict, fv: date) -> List[str]:
    """Avisos (tramo 5: no bloquean) por cada 8-K de los doce meses anteriores a la valoración con un hecho material
    (Items 1.01, 2.01 o 3.02) que la tesis no cita en ninguna evidencia (A4, fallos [58] y [69]). El warrant de Qualcomm
    a Amazon —hasta 25 M de acciones, Item 3.02— no aparecía ni en la tesis ni en las acciones del valor por acción."""
    import json
    citado = json.dumps(datos_entradas or {}, ensure_ascii=False)
    avisos = []
    for d in getattr(emisor, "depositos", None) or []:
        if d.formulario != "8-K" or not (fv - timedelta(days=365) <= d.presentado <= fv):
            continue
        items = [x.strip() for x in (d.epigrafes or "").split(",") if x.strip() in _ITEMS_MATERIALES]
        if not items or f"8-K {d.presentado.isoformat()}" in citado:
            continue
        que = ", ".join(f"Item {x} ({_ITEMS_MATERIALES[x]})" for x in items)
        cola = ("; si emite o puede emitir acciones, su dilución va en val.dilucion_adicional con su cita" if "3.02" in items else "")
        avisos.append(f"8-K del {d.presentado:%d/%m/%Y} con {que} sin citar en la tesis{cola}")
    return avisos


def _ntm(v: Valoracion, m: Motor, hechos, trimestres: List[Periodo], p: Parametros, intereses_udm: Optional[float] = None) -> Ntm:
    """`intereses_udm`: los gastos financieros de los doce meses ya calculados (emisor semestral); sin ellos, los de los
    cuatro últimos trimestres, como siempre."""
    b = v.base.proyeccion
    f = b.fraccion
    mezcla = lambda serie: f * serie[0] + (1 - f) * serie[1]                        # noqa: E731
    intereses, _ = 0.0, None
    ult = trimestres[-4:]
    valores = [hechos.get(("intereses", q)) for q in ult]
    if intereses_udm is not None:
        intereses = intereses_udm
    elif valores and all(x is not None and x.hay_dato for x in valores):
        intereses = abs(sum(x.valor for x in valores))
    acciones = v.base.acciones or v.puente.acciones          # con «dilución», también las que pagan la SBC
    bpa_serie = [(n - intereses * (1 - p.tipo_marginal)) / acciones for n in b.nopat]
    ingresos, ebitda, bpa = mezcla(b.ingresos), mezcla(b.ebitda), mezcla(bpa_serie)
    fcf = mezcla([x - intereses * (1 - p.tipo_marginal) for x in b.fcff])
    per = m.precio / bpa if bpa > 0 else None
    cagr = (bpa_serie[3] / bpa_serie[0]) ** (1 / 3) - 1 if len(bpa_serie) > 3 and bpa_serie[0] > 0 and bpa_serie[3] > 0 else None
    return Ntm(ingresos, ebitda, bpa, fcf, per, m.ev_mercado / ebitda if ebitda > 0 else None,
               m.ev_mercado / ingresos if ingresos > 0 else None, m.cap_mercado / fcf if fcf > 0 else None,
               per / (cagr * 100) if per and cagr and cagr > 0 else None, cagr)
