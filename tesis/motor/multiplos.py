"""Múltiplos y rentabilidades sobre cifras de la SEC y la cotización oficial (apartados 11 y 17).

Decisión del analista (18/09/2026): los múltiplos que el libro no trae (EV/EBITDA, PEG) se
calculan con fórmula **siempre que las cifras sean las últimas de la SEC, contrastadas**, y la
cotización sea la oficial de la bolsa. Aquí se hace eso, y nada más:

- Cifras de flujo en TTM: la suma de los cuatro últimos trimestres contrastados de la
  sección C (ingresos, EBIT, amortización → EBITDA, beneficio, BPA diluido, CFO, capex → FCF).
- Cifras de balance al último cierre contrastado (deuda bruta, tesorería e inversiones).
- Capitalización = cotización oficial × acciones de la portada del último formulario.
- EV = capitalización + deuda bruta − tesorería − inversiones a corto plazo.
- PER, EV/EBITDA, EV/Ventas, P/FCF sobre TTM; PEG = PER / crecimiento del BPA diluido del
  último ejercicio frente al anterior (la única tasa de crecimiento que la SEC da).
- ROE y ROA en TTM con la definición que la propia compañía escribe en su 10-K (beneficio
  después de impuestos / patrimonio medio), sobre el patrimonio y el activo medios de las
  dos últimas fechas de junio.

Donde el agregador publica el mismo múltiplo (EV/EBITDA, ROE, ROA) se cuadra con él; donde
publica otra definición (PEG sobre crecimiento esperado a cinco años) se imprime al lado
rotulado como definición distinta, sin cuadrar.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional, Tuple

from ..datos import campos as campos_mod
from ..fuentes import sec
from ..datos.hechos import Contraste, Hecho, Periodo

__all__ = ["Multiplos", "Linea", "construir"]

TOLERANCIA = 0.02   # diferencia relativa admitida frente al agregador (redondeos y fecha de la cotización)


@dataclass
class Linea:
    rotulo: str
    valor: Optional[float]
    unidad: str                         # «x» · «%» · «musd» · «usd»
    formula: str
    componentes: str                    # las cifras que entran, impresas
    motivo: str = ""                    # si N/A, por qué
    agregador: Optional[float] = None   # lo que publica el agregador para el mismo hecho
    contraste: Contraste = Contraste.SIN_CONTRASTAR
    nota_contraste: str = ""


@dataclass
class Multiplos:
    fin: str                            # clave del último trimestre («2T26»)
    trimestres: List[str]
    cierre: Optional[date]
    precio: Optional[float]
    acciones: Optional[float]           # acciones de la portada (unidades)
    lineas: List[Linea] = field(default_factory=list)
    faltan: Dict[str, str] = field(default_factory=dict)
    por_acumulados: Dict[str, str] = field(default_factory=dict)   # magnitudes cuyo TTM sale de los acumulados, y por qué

    def linea(self, rotulo: str) -> Optional[Linea]:
        return next((l for l in self.lineas if l.rotulo == rotulo), None)


def _suma(hechos: Dict[Tuple[str, Periodo], Hecho], campo: str, trimestres: List[Periodo]) -> Tuple[Optional[float], str]:
    valores = []
    for p in trimestres:
        h = hechos.get((campo, p))
        if h is None or not h.hay_dato:
            return None, f"{campo} {p.clave} sin dato contrastado"
        valores.append(h.valor)
    return sum(valores), ""


def _por_acumulados(facts: Optional[dict], obtenido: Optional[date], campo: str, fin: Periodo,
                    anuales: List[Periodo]) -> Tuple[Optional[float], str]:
    """Los doce meses cuando el trimestre suelto no se publica: ejercicio + acumulado del año − el del año anterior.

    El estado de flujos de un 10-Q viene acumulado desde el comienzo del ejercicio, no por trimestre: sumando cuatro
    trimestres, el flujo de caja operativo y la amortización de Qualcomm salían N/A, y con ellos el EBITDA TTM, el
    EV/EBITDA y el P/FCF. Los tres sumandos son cifras que publica la SEC; la resta es la definición de TTM.
    """
    if not facts or not anuales:
        return None, "sin hechos XBRL para el acumulado"
    from datetime import timedelta
    fy = next((p for p in reversed(anuales) if p.fin <= fin.fin), None)
    if fy is None:
        return None, "sin ejercicio cerrado anterior al trimestre"
    valor_fy = _xbrl(facts, obtenido, campo, fy)
    if valor_fy is None:
        return None, f"companyfacts no trae {campo} del ejercicio {fy.clave}"
    if fy.fin == fin.fin:
        return valor_fy, ""
    ytd = Periodo(fin=fin.fin, inicio=fy.fin + timedelta(days=1))
    previo = next((p for p in sec.calendario(facts, ytd.meses) if p.inicio == fy.inicio), None)
    if previo is None:
        return None, f"companyfacts no trae el acumulado de {ytd.meses} meses del ejercicio anterior"
    a, b = _xbrl(facts, obtenido, campo, ytd), _xbrl(facts, obtenido, campo, previo)
    if a is None or b is None:
        return None, f"companyfacts no trae {campo} de los acumulados {ytd.clave} y {previo.clave}"
    return valor_fy + a - b, ""


def _instante(hechos: Dict[Tuple[str, Periodo], Hecho], campo: str, p: Periodo) -> Optional[float]:
    h = hechos.get((campo, p))
    return h.valor if h is not None and h.hay_dato else None


def _xbrl(facts: dict, obtenido: date, campo: str, p: Periodo) -> Optional[float]:
    """Un saldo que no está en los periodos del informe, directamente de companyfacts (sin ese saldo, N/A)."""
    if facts is None:
        return None
    try:
        h = sec.hechos_xbrl(facts, campos_mod.campo(campo), obtenido, [p]).get(p)
    except (KeyError, ValueError):
        return None
    return h.valor if h is not None and h.hay_dato else None


def _cuadrar(l: Linea, publicado: Optional[float], que: str) -> None:
    from ..formato import numero as _numero
    if publicado is None:
        l.nota_contraste = f"el agregador no publica {que}"
        return
    l.agregador = publicado
    if l.valor is None:
        return
    impreso = (_numero(publicado * 100, 1) + " %") if l.unidad == "%" else (_numero(publicado, 1) + "x" if l.unidad == "x" else _numero(publicado / 1e6))
    if abs(l.valor - publicado) <= TOLERANCIA * abs(publicado):
        l.contraste, l.nota_contraste = Contraste.CONFIRMADO, f"coincide con {que} del agregador ({impreso}, ±{TOLERANCIA:.0%})"
    else:
        l.contraste, l.nota_contraste = Contraste.DISCREPANTE, f"el agregador publica {impreso} para {que}; su definición no está publicada"


def _un_anio_antes(d: date) -> date:
    try:
        return d.replace(year=d.year - 1)
    except ValueError:                 # 29 de febrero
        return d.replace(year=d.year - 1, day=28)


def _cierre_de_hace_un_anio(facts: Optional[dict], fin: Periodo) -> date:
    """El cierre del mismo trimestre del año anterior, tal como lo fechó el emisor.

    Restar un año del calendario da el 28/06/2025 cuando Qualcomm cerró el 29: en la SEC no hay balance a esa fecha
    y el patrimonio medio —y con él el ROE y el ROA— salían N/A. Se busca el cierre real más cercano (±10 días).
    """
    objetivo = _un_anio_antes(fin.fin)
    if not facts:
        return objetivo
    cierres = {p.fin for p in sec.calendario(facts, 3)} | {p.fin for p in sec.calendario(facts, 12)}
    cercano = min(cierres, key=lambda d: abs((d - objetivo).days), default=None)
    return cercano if cercano is not None and abs((cercano - objetivo).days) <= 10 else objetivo


def construir(hechos: Dict[Tuple[str, Periodo], Hecho], trimestres: List[Periodo], anuales: List[Periodo], precio: Optional[Hecho],
              acciones: Optional[float], agregador=None, facts: Optional[dict] = None, obtenido: Optional[date] = None,
              no_aplican: Optional[Dict[str, str]] = None) -> Multiplos:
    """Los múltiplos y rentabilidades TTM; cada línea con su fórmula, sus componentes y su contraste."""
    ultimos = sorted(trimestres, key=lambda p: p.fin)[-4:]
    fin = ultimos[-1] if ultimos else None
    m = Multiplos(fin=fin.clave if fin else "", trimestres=[p.clave for p in ultimos], cierre=fin.fin if fin else None,
                  precio=precio.valor if precio is not None and precio.hay_dato else None, acciones=acciones)
    if len(ultimos) < 4:
        m.faltan["ttm"] = f"solo {len(ultimos)} trimestres contrastados: no hay TTM"
        return m
    if m.precio is None:
        m.faltan["precio"] = "sin cotización oficial (apartado 1): los múltiplos sobre precio quedan N/A"
    if acciones is None:
        m.faltan["acciones"] = "sin acciones en circulación de la portada: capitalización N/A"
    sumas: Dict[str, Tuple[Optional[float], str]] = {c: _suma(hechos, c, ultimos) for c in ("ingresos", "ebit", "amortizacion", "beneficio_neto", "bpa_diluido", "cfo", "capex")}
    # lo que no se publica por trimestres se saca de los acumulados; el BPA no se suma ni se resta así (el número de
    # acciones cambia dentro del año), y se queda N/A con su motivo antes que salir aproximado
    for c, (valor, motivo) in list(sumas.items()):
        if valor is None and c != "bpa_diluido":
            por_acumulado, motivo_ac = _por_acumulados(facts, obtenido, c, fin, anuales)
            if por_acumulado is not None:
                sumas[c] = (por_acumulado, "")
                m.por_acumulados[c] = f"ejercicio + acumulado del año − el del año anterior ({motivo or 'el trimestre suelto no se publica'})"
            else:
                sumas[c] = (None, f"{motivo}; {motivo_ac}")
    v = {c: s[0] for c, s in sumas.items()}
    cierre = Periodo.instante(fin.fin)
    deuda = _instante(hechos, "deuda_bruta", cierre)
    caja, inv = _instante(hechos, "caja", cierre), _instante(hechos, "inversiones_cp", cierre)
    # «no es una partida de esta empresa» no es un hueco (regla 10): quien nunca publica inversiones a corto no las tiene
    if inv is None and no_aplican and "inversiones_cp" in no_aplican:
        inv = 0.0
        m.faltan["inversiones_cp"] = f"inversiones a corto plazo = 0: {no_aplican['inversiones_cp']}"
    ebitda = v["ebit"] + v["amortizacion"] if v["ebit"] is not None and v["amortizacion"] is not None else None
    fcf = v["cfo"] - v["capex"] if v["cfo"] is not None and v["capex"] is not None else None
    cap = m.precio * acciones if m.precio is not None and acciones else None
    ev = cap + deuda - caja - inv if None not in (cap, deuda, caja, inv) else None   # sin inversiones contrastadas no hay EV: un None no es un cero
    from ..formato import numero as _numero
    mln = lambda x: _numero(x / 1e6)
    dos = lambda x: _numero(x, 2)
    unod = lambda x: _numero(x, 1)
    rango = f"{ultimos[0].clave}–{fin.clave}"

    def linea(rotulo, valor, unidad, formula, componentes, motivo=""):
        m.lineas.append(Linea(rotulo, valor, unidad, formula, componentes, motivo if valor is None else ""))
        return m.lineas[-1]

    linea("Capitalización (M USD)", cap, "musd", "cotización oficial × acciones de la portada",
          f"{dos(m.precio)} × {mln(acciones)} M" if cap is not None else "", m.faltan.get("precio") or m.faltan.get("acciones") or "")
    linea("Valor de empresa, EV (M USD)", ev, "musd", "capitalización + deuda bruta − tesorería − inversiones a corto plazo",
          f"{mln(cap)} + {mln(deuda)} − {mln(caja)} − {mln(inv)}" if ev is not None else "", "sin capitalización o sin saldos contrastados de deuda, tesorería e inversiones a corto plazo al cierre")
    l = linea("EBITDA TTM (M USD)", ebitda, "musd", f"EBIT + amortización del inmovilizado, {rango}", f"{mln(v['ebit'])} + {mln(v['amortizacion'])}" if ebitda is not None else "",
              sumas["ebit"][1] or sumas["amortizacion"][1])
    _cuadrar(l, agregador.ebitda_ttm if agregador is not None else None, "el EBITDA TTM")
    bpa, formula_per = v["bpa_diluido"], "cotización oficial / BPA diluido TTM"
    if bpa is None and v["beneficio_neto"] is not None:
        # el BPA del trimestre que nadie publica (el 4T fiscal) no se resta; el TTM se saca del beneficio TTM entre las
        # acciones medias diluidas del último trimestre, y la fórmula lo dice
        acc_diluidas = hechos.get(("acciones_diluidas", fin))
        if acc_diluidas is not None and acc_diluidas.hay_dato and acc_diluidas.valor:
            bpa = v["beneficio_neto"] / acc_diluidas.valor
            formula_per = f"cotización oficial / (beneficio neto TTM / acciones medias diluidas del {fin.clave})"
    per = m.precio / bpa if m.precio is not None and bpa and bpa > 0 else None   # con BPA negativo no hay PER, como en comparables
    linea("PER (TTM)", per, "x", formula_per, f"{dos(m.precio)} / {dos(bpa)}" if per is not None else "",
          m.faltan.get("precio") or ("" if bpa is not None else sumas["bpa_diluido"][1]) or ("BPA TTM negativo: PER no definido" if bpa else "BPA TTM nulo"))
    l = linea("EV / EBITDA (TTM)", ev / ebitda if ev is not None and ebitda else None, "x", "EV / EBITDA TTM", f"{mln(ev)} / {mln(ebitda)}" if ev is not None and ebitda else "",
              "sin EV o sin EBITDA")
    _cuadrar(l, agregador.ev_ebitda if agregador is not None else None, "EV/EBITDA")
    linea("EV / Ventas (TTM)", ev / v["ingresos"] if ev is not None and v["ingresos"] else None, "x", "EV / ingresos TTM", f"{mln(ev)} / {mln(v['ingresos'])}" if ev is not None and v["ingresos"] else "",
          "sin EV o sin ingresos TTM")
    linea("P / FCF (TTM)", cap / fcf if cap is not None and fcf else None, "x", "capitalización / (CFO − capex) TTM", f"{mln(cap)} / ({mln(v['cfo'])} − {mln(v['capex'])})" if cap is not None and fcf else "",
          "sin capitalización o sin FCF TTM")
    # PEG con la única tasa de crecimiento que la SEC da: el BPA diluido del último ejercicio frente al anterior
    ejercicios = sorted(anuales, key=lambda p: p.fin)[-2:]
    crecimiento, detalle = None, "sin dos ejercicios con BPA diluido"
    if len(ejercicios) == 2:
        a0, a1 = (hechos.get(("bpa_diluido", p)) for p in ejercicios)
        if a0 is not None and a1 is not None and a0.hay_dato and a1.hay_dato and a0.valor > 0:
            crecimiento = a1.valor / a0.valor - 1
            detalle = f"{dos(a1.valor)} / {dos(a0.valor)} − 1 = {unod(crecimiento * 100)} % ({ejercicios[1].clave} frente a {ejercicios[0].clave})"
    linea("Crecimiento del BPA diluido, último ejercicio", crecimiento, "%", f"BPA {ejercicios[1].clave if len(ejercicios) == 2 else ''} / BPA {ejercicios[0].clave if len(ejercicios) == 2 else ''} − 1", detalle if crecimiento is not None else "", detalle)
    peg = per / (crecimiento * 100) if per is not None and crecimiento and crecimiento > 0 else None
    l = linea("PEG (PER TTM / crecimiento anual del BPA, en puntos)", peg, "x", "PER TTM / (crecimiento del BPA diluido del último ejercicio × 100)",
              f"{unod(per)} / {unod(crecimiento * 100)}" if peg is not None else "", "sin PER o sin crecimiento positivo del BPA")
    if agregador is not None and agregador.peg is not None:
        l.agregador = agregador.peg
        l.nota_contraste = "el agregador publica su PEG sobre el crecimiento esperado a cinco años: otra definición, no se cuadra"
    # ROE y ROA TTM, con la definición del 10-K (beneficio después de impuestos / patrimonio medio)
    hace_un_anio = Periodo.instante(_cierre_de_hace_un_anio(facts, fin))
    for rotulo, campo, que in (("ROE (TTM)", "patrimonio", "ROE"), ("ROA (TTM)", "total_activo", "ROA")):
        ahora = _instante(hechos, campo, cierre)
        antes = _instante(hechos, campo, hace_un_anio) or _xbrl(facts, obtenido or date.today(), campo, hace_un_anio)
        valor = v["beneficio_neto"] / ((ahora + antes) / 2) if v["beneficio_neto"] is not None and ahora and antes else None
        l = linea(rotulo, valor, "%", f"beneficio neto TTM / {campos_mod.campo(campo).rotulo.lower()} medio ({hace_un_anio.fin:%d/%m/%Y} y {cierre.fin:%d/%m/%Y})",
                  f"{mln(v['beneficio_neto'])} / (({mln(antes)} + {mln(ahora)}) / 2)" if valor is not None else "",
                  sumas["beneficio_neto"][1] or f"sin {campos_mod.campo(campo).rotulo.lower()} a {hace_un_anio.fin:%d/%m/%Y} en la SEC")
        _cuadrar(l, getattr(agregador, "roe" if que == "ROE" else "roa", None) if agregador is not None else None, f"el {que} TTM")
    return m
