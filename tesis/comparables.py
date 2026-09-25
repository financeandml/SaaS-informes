"""Comparables (apartado 22): los que la bolsa asigna a la compañía, con sus cuentas de la SEC.

Decisión del analista (17/09/2026): el apartado 22 se resuelve con la API de Nasdaq «viendo qué
competidores directos tiene asignados». La bolsa no publica una lista de competidores: lo que
publica es la **clasificación sectorial** de cada valor (sector · industria) en su screener, y
los comparables son los demás valores de la misma industria. Eso es lo que se imprime, con el
rótulo literal de la industria y la advertencia de que la clasificación es de la bolsa, no del
sistema ni del analista (Netflix cae en «Consumer Electronics/Video Chains», con Best Buy e
iQIYI; el 10-K no nombra competidores concretos).

De cada comparable: capitalización y última cotización (screener de Nasdaq, capa Hd) y, si
presenta ante la SEC, ingresos y beneficio neto del último ejercicio anual (companyfacts, capa
H, con formulario y cierre) → P/Ventas y PER como derivados ∑ con fórmula. Quien no presenta
ante la SEC (o cuyo ejercicio no está en companyfacts) sale N/A con motivo.

Segunda clasificación oficial (18/09/2026, pedido del analista: solo fuentes oficiales): el
código SIC que la SEC asigna al emisor y los demás emisores con ticker que comparten ese SIC
(búsqueda de EDGAR por SIC), con las mismas cuentas y los mismos múltiplos. Ninguna de las dos
fuentes publica «competidores»: publican clasificaciones, y el informe lo dice.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Dict, List, Optional, Tuple
from urllib.error import HTTPError, URLError

from . import precio as precio_mod
from . import sec
from .rotulos import fallo

__all__ = ["Comparable", "Comparables", "construir"]

_INGRESOS = ("us-gaap:Revenues", "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax", "ifrs-full:Revenue")
_BENEFICIO = ("us-gaap:NetIncomeLoss", "us-gaap:ProfitLoss", "ifrs-full:ProfitLoss")
_FORMULARIOS_ANUALES = {"10-K", "10-K/A", "20-F", "20-F/A", "40-F"}


@dataclass
class Comparable:
    ticker: str
    nombre: str
    pais: str
    capitalizacion: Optional[float]           # USD, del screener de la bolsa
    ultimo: Optional[float]                   # última cotización del screener
    cik: Optional[str] = None
    ingresos: Optional[float] = None          # último ejercicio anual, USD
    beneficio: Optional[float] = None
    cierre: Optional[date] = None
    formulario: str = ""
    moneda: str = ""                          # la unidad de companyfacts; si no es USD, no se divide con la capitalización
    nota_sec: str = ""                        # por qué faltan las cuentas, si faltan

    @property
    def p_ventas(self) -> Optional[float]:
        return self.capitalizacion / self.ingresos if self.capitalizacion and self.ingresos and self.moneda == "USD" else None

    @property
    def per(self) -> Optional[float]:
        return self.capitalizacion / self.beneficio if self.capitalizacion and self.beneficio and self.beneficio > 0 and self.moneda == "USD" else None


@dataclass
class Comparables:
    ticker: str
    industria: str = ""
    sector: str = ""
    filas: List[Comparable] = field(default_factory=list)      # la propia compañía primero, luego por capitalización
    obtenido: Optional[datetime] = None
    respuesta: Optional[Tuple[str, str, datetime]] = None       # url, cuerpo literal, hora (screener)
    sic: str = ""                                               # código SIC que la SEC asigna al emisor
    sic_descripcion: str = ""
    filas_sic: List[Comparable] = field(default_factory=list)   # los emisores con ticker del mismo SIC, por capitalización
    respuesta_sic: Optional[Tuple[str, str, datetime]] = None   # url de la búsqueda de EDGAR, atom literal, hora
    faltan: Dict[str, str] = field(default_factory=dict)


def _num(v) -> Optional[float]:
    if v in (None, "", "N/A", "NA"):
        return None
    try:
        return float(str(v).replace("$", "").replace(",", ""))
    except ValueError:
        return None


def _ultimo_anual(facts: dict, conceptos: Tuple[str, ...]) -> Optional[Tuple[float, date, str, str]]:
    """(valor, cierre, formulario, unidad) del último ejercicio anual completo que la SEC trae para el primer concepto con datos."""
    mejor = None
    for concepto in conceptos:
        unidad, filas = sec._filas_concepto(facts, concepto)
        for f in filas:
            if f.get("form") not in _FORMULARIOS_ANUALES or f.get("fp") != "FY" or "start" not in f:
                continue
            inicio, fin = date.fromisoformat(f["start"]), date.fromisoformat(f["end"])
            if not 340 <= (fin - inicio).days <= 380:
                continue
            candidato = (float(f["val"]), fin, f["form"], unidad)
            if mejor is None or candidato[1] > mejor[1]:
                mejor = candidato
    return mejor          # el cierre más reciente entre todos los conceptos: muchos emisores conservan «Revenues» antiguos junto al de ASC 606


def _cuentas(c: Comparable) -> None:
    identidad = sec.cik_de(c.ticker)
    if identidad is None:
        c.nota_sec = "no presenta ante la SEC (sin CIK en company_tickers)"
        return
    c.cik = identidad[0]
    facts, _ = sec.companyfacts(c.cik)
    ingresos, beneficio = _ultimo_anual(facts, _INGRESOS), _ultimo_anual(facts, _BENEFICIO)
    if ingresos is None or beneficio is None:
        c.nota_sec = "companyfacts no trae un ejercicio anual completo de ingresos y beneficio"
        return
    c.ingresos, c.cierre, c.formulario, c.moneda = ingresos
    c.beneficio = beneficio[0]
    if beneficio[1] != ingresos[1]:
        c.beneficio = None            # un PER con ingresos y beneficio de ejercicios distintos no es un múltiplo: N/A con este motivo
        c.nota_sec = f"ingresos al {ingresos[1]:%d/%m/%Y} y beneficio al {beneficio[1]:%d/%m/%Y}: cierres distintos, el PER no se calcula"
    elif c.moneda != "USD":
        c.nota_sec = f"cuentas en {c.moneda} y capitalización en USD: los múltiplos no se calculan sin tipo de cambio oficial"


def construir(ticker: str, con_sec: bool = True, maximo: int = 12) -> Comparables:
    """Los valores de la misma industria que la bolsa asigna al ticker, con sus cuentas anuales de la SEC."""
    c = Comparables(ticker=ticker.upper(), obtenido=datetime.now())
    if precio_mod.variable("WC_PRECIO_FUENTE").lower() != "nasdaq":
        c.faltan["fuente"] = "los comparables se leen del screener de Nasdaq y WC_PRECIO_FUENTE no es «nasdaq»"
        return c
    url = "https://api.nasdaq.com/api/screener/stocks?tableonly=false&limit=25&offset=0&download=true"
    try:
        datos, cuerpo, obtenido = precio_mod.pedir_crudo(url)
    except (HTTPError, URLError, ValueError, json.JSONDecodeError) as e:
        c.faltan["screener"] = f"el screener de Nasdaq no respondió: {fallo(e)}"
        return c
    filas = ((datos or {}).get("data") or {}).get("rows") or []
    propia = next((f for f in filas if (f.get("symbol") or "").upper() == c.ticker), None)
    if propia is None:
        c.faltan["screener"] = f"{c.ticker} no está en el screener de Nasdaq"
        return c
    c.industria, c.sector = str(propia.get("industry") or ""), str(propia.get("sector") or "")
    # el cuerpo entero pesa más de un megabyte: la evidencia guarda solo las filas de la industria, literales
    misma = [f for f in filas if f.get("industry") == c.industria]
    c.respuesta = (url, json.dumps({"industria": c.industria, "filas_de_la_industria": misma, "filas_totales_del_screener": len(filas)}, indent=1, ensure_ascii=False), obtenido)
    orden = sorted(misma, key=lambda f: -(_num(f.get("marketCap")) or 0))
    orden = [propia] + [f for f in orden if f is not propia]
    for f in orden[:maximo]:
        c.filas.append(Comparable(ticker=str(f.get("symbol") or ""), nombre=str(f.get("name") or ""), pais=str(f.get("country") or ""),
                                  capitalizacion=_num(f.get("marketCap")), ultimo=_num(f.get("lastsale"))))
    if not con_sec:
        c.faltan["sec"] = "no se pidieron las cuentas de los comparables a la SEC"
        return c
    for x in c.filas:
        try:
            _cuentas(x)
        except sec.SinContacto as e:
            c.faltan["sec"] = str(e)
            break
        except (HTTPError, URLError, RuntimeError, ValueError, KeyError) as e:
            x.nota_sec = f"EDGAR no sirvió las cuentas: {fallo(e)}"
    if len(c.filas) <= 1:
        c.faltan["comparables"] = f"la bolsa no asigna a ningún otro valor la industria «{c.industria}»"
    _mismo_sic(c, filas, maximo)
    return c


def _mismo_sic(c: Comparables, filas_screener: list, maximo: int) -> None:
    """Los emisores con ticker que la SEC clasifica en el mismo SIC que la compañía, con capitalización del screener."""
    import re
    try:
        identidad = sec.cik_de(c.ticker)
        if identidad is None:
            c.faltan["sic"] = "la compañía no presenta ante la SEC: sin SIC"
            return
        s, _ = sec.submissions(identidad[0])
        c.sic, c.sic_descripcion = str(s.get("sic") or ""), str(s.get("sicDescription") or "")
        if not c.sic:
            c.faltan["sic"] = "la SEC no publica SIC para este emisor"
            return
        url = f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&SIC={c.sic}&type=10-K&owner=include&count=100&output=atom"
        atom, obtenido = sec.descargar_texto(url)
        tickers, _ = sec._descargar("https://www.sec.gov/files/company_tickers.json")
    except sec.SinContacto as e:
        c.faltan["sic"] = str(e)
        return
    except (HTTPError, URLError, RuntimeError, ValueError, KeyError) as e:
        c.faltan["sic"] = f"EDGAR no sirvió la búsqueda por SIC: {fallo(e)}"
        return
    por_cik = {f"{int(f['cik_str']):010d}": (str(f["ticker"]), str(f["title"])) for f in tickers.values()}
    ciks = re.findall(r"<cik>(\d+)</cik>", atom)
    c.respuesta_sic = (url, atom, datetime.combine(obtenido, datetime.min.time()))
    por_simbolo = {(f.get("symbol") or "").upper(): f for f in filas_screener}
    candidatos = []
    for cik in ciks:
        if cik not in por_cik or cik == identidad[0]:
            continue
        simbolo, nombre = por_cik[cik]
        f = por_simbolo.get(simbolo.upper(), {})
        candidatos.append(Comparable(ticker=simbolo, nombre=str(f.get("name") or nombre), pais=str(f.get("country") or ""),
                                     capitalizacion=_num(f.get("marketCap")), ultimo=_num(f.get("lastsale")), cik=cik))
    candidatos.sort(key=lambda x: -(x.capitalizacion or 0))
    c.filas_sic = candidatos[:maximo]
    if not c.filas_sic:
        c.faltan["sic_comparables"] = f"ningún otro emisor con ticker comparte el SIC {c.sic} ({c.sic_descripcion})"
        return
    for x in c.filas_sic:
        try:
            _cuentas(x)
        except (sec.SinContacto, HTTPError, URLError, RuntimeError, ValueError, KeyError) as e:
            x.nota_sec = f"EDGAR no sirvió las cuentas: {fallo(e)}"
