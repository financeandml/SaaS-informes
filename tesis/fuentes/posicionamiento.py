"""Sección F (opciones, derivados y posicionamiento institucional) con lo que la propia bolsa publica.

El analista adjuntará una API de derivados para completar la sección; mientras, la web de
Nasdaq —la bolsa de cotización, la misma fuente del precio— publica cuatro de los seis
apartados y se leen tal cual, con la respuesta literal guardada como prueba:

- **Cadena de opciones** (apartado 24 del índice): volumen e interés abierto de calls y puts
  por strike y vencimiento. Se agregan por vencimiento y el put/call ratio se imprime como
  derivado (∑) con su fórmula. No hay volatilidad implícita: eso queda para la API.
- **Interés abierto call frente a put** (parte del 25): sale de la misma cadena. Sweeps y dark
  pool no los publica la bolsa: pendientes de la API.
- **Posicionamiento institucional** (27): resumen de tenedores (13F) y mayores posiciones con la
  fecha de cada 13F, que no es la misma para todos y se imprime.
- **Operaciones de insiders** (28): recuento de compras y ventas a 3 y 12 meses y las últimas
  operaciones, a partir de los Form 4 depositados en la SEC tal como Nasdaq los recoge.
- **Short interest** (29): la serie bimensual de FINRA (interés corto, volumen medio diario, días
  para cubrir), desde el split 10:1 para no mezclar acciones de antes y de después.
- **Volatilidad implícita y sesgo** (25, unificado con el antiguo 26 por decisión del analista):
  la bolsa no publica IV, así que —única excepción autorizada— se lee de Yahoo Finance por
  vencimiento: IV en el dinero de call y put, IV de la put un 10 % fuera y de la call un 10 %
  fuera, y el sesgo como derivado (∑ = IV put − IV call). El interés abierto que Yahoo trae por
  vencimiento se cuadra con el de la bolsa: si no coinciden, el informe lo marca.

Todo es capa «Hd» (documento externo, no depositado en la SEC), certeza media: la bolsa lo
publica, pero el depósito original (13F, Form 4) está en EDGAR y no se ha cruzado aún. Lo que
ninguna de las dos fuentes publica es N/A con motivo, no se estima.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Dict, List, Optional, Tuple
from urllib.error import HTTPError, URLError

from . import precio as precio_mod
from ..datos.hechos import Contraste
from ..rotulos import fallo

__all__ = ["Cadena", "Insiders", "Institucional", "Posicionamiento", "ShortInterest", "Vencimiento", "VolatilidadImplicita", "construir"]

FUENTE = "Nasdaq (web del mercado)"
_QUE = {"cadena": "la cadena de opciones", "institucional": "las posiciones institucionales (13F)",
        "insiders": "las operaciones de directivos", "short": "el interés en corto"}


@dataclass
class Respuesta:
    """Una respuesta de la API guardada entera: URL, cuerpo literal y hora, para el volcado de evidencia."""
    url: str
    cuerpo: str
    obtenido: datetime


@dataclass
class Strike:
    """Una fila de la cadena: precio de ejercicio, interés abierto y la prima de cada lado (punto medio compra/venta si
    la bolsa da los dos; si no, la última negociada)."""
    precio: float
    oi_calls: Optional[float]
    oi_puts: Optional[float]
    call: Optional[float]
    put: Optional[float]


@dataclass
class Vencimiento:
    fecha: str                     # tal cual lo rotula la bolsa («September 18, 2026»)
    vol_calls: Optional[float]
    vol_puts: Optional[float]
    oi_calls: Optional[float]
    oi_puts: Optional[float]
    contratos: int                 # filas (strikes) del vencimiento
    strikes: List[Strike] = field(default_factory=list)


@dataclass
class Cadena:
    vencimientos: List[Vencimiento] = field(default_factory=list)
    ultimo: str = ""               # «LAST TRADE: $75.66 (AS OF SEP 17, 2026 1:46 PM ET)», literal
    total_filas: int = 0
    respuesta: Optional[Respuesta] = None

    def total(self, campo: str) -> Optional[float]:
        valores = [getattr(v, campo) for v in self.vencimientos if getattr(v, campo) is not None]
        return sum(valores) if valores else None


@dataclass
class Institucional:
    resumen: List[Tuple[str, str]] = field(default_factory=list)          # (rótulo, valor literal)
    posiciones: List[Tuple[str, Optional[float], Optional[float]]] = field(default_factory=list)   # (rótulo, tenedores, acciones)
    mayores: List[Tuple[str, Optional[date], Optional[float], Optional[float], Optional[float]]] = field(default_factory=list)
    respuesta: Optional[Respuesta] = None


@dataclass
class Insiders:
    operaciones: List[Tuple[str, Optional[float], Optional[float]]] = field(default_factory=list)   # (rótulo, 3 meses, 12 meses)
    acciones: List[Tuple[str, Optional[float], Optional[float]]] = field(default_factory=list)
    ultimas: List[Tuple[str, str, Optional[date], str, Optional[float], Optional[float]]] = field(default_factory=list)   # insider, relación, fecha, tipo, acciones, precio
    cruce: List = field(default_factory=list)       # form4.Cruce por operación de `ultimas`, en el mismo orden (vacío: sin cruzar)
    total_operaciones: Optional[int] = None
    respuesta: Optional[Respuesta] = None
    # «bme»: leídas de las notificaciones de directivos que el emisor publica en BME (no hay Form 4), y en qué documentos
    fuente: str = ""
    documentos: List[str] = field(default_factory=list)


@dataclass
class ShortInterest:
    filas: List[Tuple[date, Optional[float], Optional[float], Optional[float]]] = field(default_factory=list)   # liquidación, interés, vol. medio, días
    desde: Optional[date] = None   # primera liquidación impresa (tras el split)
    respuesta: Optional[Respuesta] = None


@dataclass
class IVVencimiento:
    fecha: date
    subyacente: float
    strike_atm: Optional[float]
    iv_call_atm: Optional[float]
    iv_put_atm: Optional[float]
    strike_put_otm: Optional[float]       # la put más cercana al 90 % del subyacente
    iv_put_otm: Optional[float]
    strike_call_otm: Optional[float]      # la call más cercana al 110 % del subyacente
    iv_call_otm: Optional[float]
    oi_calls: Optional[float]
    oi_puts: Optional[float]
    contraste_oi: Optional[Tuple[Contraste, str]] = None    # frente al interés abierto de la bolsa para el mismo vencimiento
    motivo: str = ""                                          # por qué no se imprime IV para este vencimiento, si no se imprime

    @property
    def hay_iv(self) -> bool:
        return any(x is not None for x in (self.iv_call_atm, self.iv_put_atm, self.iv_put_otm, self.iv_call_otm))

    @property
    def sesgo(self) -> Optional[float]:
        if self.iv_put_otm is None or self.iv_call_otm is None:
            return None
        return self.iv_put_otm - self.iv_call_otm


@dataclass
class VolatilidadImplicita:
    vencimientos: List[IVVencimiento] = field(default_factory=list)
    hora_precio: Optional[datetime] = None
    respuesta: Optional[Respuesta] = None
    fuente: str = ""


@dataclass
class Posicionamiento:
    cadena: Optional[Cadena] = None
    institucional: Optional[Institucional] = None
    insiders: Optional[Insiders] = None
    short: Optional[ShortInterest] = None
    iv: Optional[VolatilidadImplicita] = None
    obtenido: Optional[datetime] = None
    faltan: Dict[str, str] = field(default_factory=dict)


def _pedir(url: str) -> Tuple[dict, Respuesta]:
    datos, cuerpo, obtenido = precio_mod.pedir_crudo(url)
    return datos, Respuesta(url, cuerpo, obtenido)


def _num(v) -> Optional[float]:
    if v is None:
        return None
    s = str(v).strip()
    if s in ("", "--", "N/A"):
        return None
    neg = s.startswith("(") and s.endswith(")")
    s = s.strip("()").replace("$", "").replace(",", "").replace("%", "")
    try:
        x = float(s)
    except ValueError:
        return None
    return -x if neg else x


def _fecha_us(s: str) -> Optional[date]:
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", (s or "").strip())
    return date(int(m.group(3)), int(m.group(1)), int(m.group(2))) if m else None


def _prima(fila: dict, lado: str) -> Optional[float]:
    compra, venta = _num(fila.get(f"{lado}_Bid")), _num(fila.get(f"{lado}_Ask"))
    if compra is not None and venta is not None and 0 < compra <= venta:
        return (compra + venta) / 2
    ultima = _num(fila.get(f"{lado}_Last"))
    return ultima if ultima is not None and ultima > 0 else None


def _cadena(ticker: str) -> Cadena:
    url = (f"https://api.nasdaq.com/api/quote/{ticker}/option-chain?assetclass=stocks&limit=0&fromdate=all"
           f"&todate=undefined&excode=oprac&callput=callput&money=all&type=all")
    datos, resp = _pedir(url)
    d = (datos or {}).get("data") or {}
    filas = ((d.get("table") or {}).get("rows")) or []
    c = Cadena(ultimo=str(d.get("lastTrade") or ""), total_filas=len(filas), respuesta=resp)
    actual: Optional[Vencimiento] = None
    for f in filas:
        grupo = (f.get("expirygroup") or "").strip()
        if grupo:                                   # fila de cabecera de un vencimiento
            actual = Vencimiento(grupo, None, None, None, None, 0)
            c.vencimientos.append(actual)
            continue
        if actual is None:
            continue
        actual.contratos += 1
        k = _num(f.get("strike"))
        if k is not None:
            actual.strikes.append(Strike(k, _num(f.get("c_Openinterest")), _num(f.get("p_Openinterest")), _prima(f, "c"), _prima(f, "p")))
        for campo, clave in (("vol_calls", "c_Volume"), ("vol_puts", "p_Volume"), ("oi_calls", "c_Openinterest"), ("oi_puts", "p_Openinterest")):
            v = _num(f.get(clave))
            if v is not None:
                setattr(actual, campo, (getattr(actual, campo) or 0.0) + v)
    return c


def _institucional(ticker: str) -> Institucional:
    url = f"https://api.nasdaq.com/api/company/{ticker}/institutional-holdings?limit=15&type=TOTAL&sortColumn=marketValue"
    datos, resp = _pedir(url)
    d = (datos or {}).get("data") or {}
    i = Institucional(respuesta=resp)
    for clave, v in (d.get("ownershipSummary") or {}).items():
        if isinstance(v, dict) and v.get("value") not in (None, ""):
            i.resumen.append((str(v.get("label") or clave), str(v["value"])))
    for bloque in ("activePositions", "newSoldOutPositions"):
        for f in ((d.get(bloque) or {}).get("rows")) or []:
            i.posiciones.append((str(f.get("positions") or ""), _num(f.get("holders")), _num(f.get("shares"))))
    for f in ((((d.get("holdingsTransactions") or {}).get("table")) or {}).get("rows")) or []:
        i.mayores.append((str(f.get("ownerName") or ""), _fecha_us(f.get("date")), _num(f.get("sharesHeld")), _num(f.get("sharesChange")),
                          _num(f.get("sharesChangePCT"))))
    return i


def _insiders(ticker: str) -> Insiders:
    url = f"https://api.nasdaq.com/api/company/{ticker}/insider-trades?limit=15&type=ALL&sortColumn=lastDate&sortOrder=DESC"
    datos, resp = _pedir(url)
    d = (datos or {}).get("data") or {}
    s = Insiders(respuesta=resp)
    for f in ((d.get("numberOfTrades") or {}).get("rows")) or []:
        s.operaciones.append((str(f.get("insiderTrade") or ""), _num(f.get("months3")), _num(f.get("months12"))))
    for f in ((d.get("numberOfSharesTraded") or {}).get("rows")) or []:
        s.acciones.append((str(f.get("insiderTrade") or ""), _num(f.get("months3")), _num(f.get("months12"))))
    tabla = d.get("transactionTable") or {}
    s.total_operaciones = int(_num(tabla.get("totalRecords")) or 0) or None
    for f in (((tabla.get("table")) or {}).get("rows")) or []:
        s.ultimas.append((str(f.get("insider") or "").title(), str(f.get("relation") or ""), _fecha_us(f.get("lastDate")),
                          str(f.get("transactionType") or ""), _num(f.get("sharesTraded")), _num(f.get("lastPrice"))))
    return s


def _no_cubre(obj) -> str:
    """El motivo, en español, cuando la bolsa responde sin datos y dice por qué (fallo [67]): «Short interest is only
    supported for Nasdaq Listed stocks» no es un dato pendiente, es una fuente que no cubre el valor. El literal inglés
    queda en la respuesta guardada (39); el cuerpo del informe lo dice en español."""
    r = getattr(obj, "respuesta", None)
    try:
        j = json.loads(r.cuerpo) if r is not None and r.cuerpo else {}
    except (ValueError, TypeError):
        return ""
    if not isinstance(j, dict) or j.get("data") or not j.get("message"):
        return ""
    mensaje = str(j["message"])
    if re.search(r"(?i)only supported for nasdaq listed", mensaje):
        return ("Nasdaq solo publica este dato de los valores que cotizan en Nasdaq y este no cotiza allí"
                + ("; su fuente oficial fuera de Nasdaq es FINRA (decisión del 28/09/2026), aún sin conectar" if isinstance(obj, ShortInterest) else ""))
    return "Nasdaq responde sin datos para este valor (su mensaje literal, en la respuesta guardada del apartado 39)"


def _short(ticker: str, desde: Optional[date]) -> ShortInterest:
    url = f"https://api.nasdaq.com/api/quote/{ticker}/short-interest?assetclass=stocks"
    datos, resp = _pedir(url)
    d = (datos or {}).get("data") or {}
    s = ShortInterest(respuesta=resp, desde=desde)
    for f in ((d.get("shortInterestTable") or {}).get("rows")) or []:
        liq = _fecha_us(f.get("settlementDate"))
        if liq is None or (desde is not None and liq <= desde):   # la liquidación del propio día del split aún es de antes
            continue
        s.filas.append((liq, _num(f.get("interest")), _num(f.get("avgDailyShareVolume")), _num(f.get("daysToCover"))))
    s.filas.sort(key=lambda x: x[0], reverse=True)
    return s


def _fecha_vencimiento_bolsa(texto: str) -> Optional[date]:
    """«September 18, 2026» → fecha."""
    try:
        return datetime.strptime(texto.strip(), "%B %d, %Y").date()
    except ValueError:
        return None


def _mas_cercano(contratos: List[dict], objetivo: float) -> Optional[dict]:
    """El contrato con strike más cercano al objetivo entre los que tienen IV con sentido y mercado de verdad.

    Fuera de sesión el agregador devuelve la cadena a medio cargar: bid y ask a cero, interés abierto a cero
    y una IV de relleno (0,0625, 0,125, 0,25, 0,5… o 1e-5). Un contrato así no tiene IV: se exige cotización
    (bid o ask), interés abierto y una IV entre el 2 % y el 300 %.
    """
    validos = [c for c in contratos if isinstance(c.get("impliedVolatility"), (int, float)) and 0.02 < c["impliedVolatility"] < 3.0
               and ((c.get("bid") or 0) > 0 or (c.get("ask") or 0) > 0) and (c.get("openInterest") or 0) > 0]
    return min(validos, key=lambda c: abs(float(c["strike"]) - objetivo), default=None)


def _iv_yahoo(ticker: str, cadena: Optional[Cadena], maximo: int = 4) -> VolatilidadImplicita:
    from . import yahoo
    cli = yahoo.cliente()
    base = f"https://query2.finance.yahoo.com/v7/finance/options/{ticker}"
    primero = cli.json(base)
    r = (primero.get("optionChain") or {}).get("result") or []
    if not r:
        raise ValueError("Yahoo no devolvió cadena de opciones")
    r = r[0]
    cuerpo, obtenido = cli.crudos[base]
    v = VolatilidadImplicita(respuesta=Respuesta(base, cuerpo, obtenido), fuente=yahoo.FUENTE)
    quote = r.get("quote") or {}
    if quote.get("regularMarketTime"):
        v.hora_precio = datetime.fromtimestamp(int(quote["regularMarketTime"]))
    por_fecha_bolsa = {}
    if cadena is not None:
        for venc in cadena.vencimientos:
            f = _fecha_vencimiento_bolsa(venc.fecha)
            if f:
                por_fecha_bolsa[f] = venc
    for k, epoch in enumerate((r.get("expirationDates") or [])[:maximo]):
        bloque = r["options"][0] if k == 0 else ((cli.json(f"{base}?date={epoch}").get("optionChain") or {}).get("result") or [{}])[0].get("options", [{}])[0]
        S = float(quote.get("regularMarketPrice") or 0)
        if not S:
            break
        calls, puts = bloque.get("calls") or [], bloque.get("puts") or []
        c_atm, p_atm = _mas_cercano(calls, S), _mas_cercano(puts, S)
        p_otm, c_otm = _mas_cercano(puts, 0.9 * S), _mas_cercano(calls, 1.1 * S)
        oi_c = sum(float(c.get("openInterest") or 0) for c in calls) if calls else None
        oi_p = sum(float(c.get("openInterest") or 0) for c in puts) if puts else None
        f = datetime.fromtimestamp(int(epoch), timezone.utc).date()
        iv = IVVencimiento(f, S, c_atm and float(c_atm["strike"]), c_atm and float(c_atm["impliedVolatility"]), p_atm and float(p_atm["impliedVolatility"]),
                           p_otm and float(p_otm["strike"]), p_otm and float(p_otm["impliedVolatility"]),
                           c_otm and float(c_otm["strike"]), c_otm and float(c_otm["impliedVolatility"]), oi_c, oi_p)
        # el mismo hecho en dos fuentes: el interés abierto del vencimiento según la bolsa y según el agregador
        bolsa = por_fecha_bolsa.get(f)
        if bolsa is not None and bolsa.oi_calls is not None and bolsa.oi_puts is not None and oi_c is not None and oi_p is not None:
            total_b, total_y = bolsa.oi_calls + bolsa.oi_puts, oi_c + oi_p
            dif = abs(total_y - total_b) / total_b if total_b else 1.0
            if dif <= 0.02:
                iv.contraste_oi = (Contraste.CONFIRMADO, f"OI total {_entero(total_y)} en Yahoo frente a {_entero(total_b)} en la bolsa ({dif * 100:.1f} %)")
            else:
                iv.contraste_oi = (Contraste.DISCREPANTE, f"OI total {_entero(total_y)} en Yahoo frente a {_entero(total_b)} en la bolsa ({dif * 100:.1f} %)")
        elif bolsa is None:
            iv.contraste_oi = (Contraste.HUECO, "la bolsa no lista este vencimiento")
        # regla 9: la IV del agregador solo se imprime si su cadena cuadra con la bolsa en el interés abierto del vencimiento;
        # una cadena que no cuadra (a medio cargar, o de otro día) no es una fuente para nada de lo que trae
        if iv.contraste_oi is not None and iv.contraste_oi[0] is Contraste.DISCREPANTE:
            iv.iv_call_atm = iv.iv_put_atm = iv.iv_put_otm = iv.iv_call_otm = None
            iv.motivo = "la cadena del agregador no cuadra con el interés abierto de la bolsa a la hora de consulta: su volatilidad implícita no se imprime"
        elif not iv.hay_iv:
            iv.motivo = "el agregador no trae ningún contrato con cotización, interés abierto y volatilidad implícita con sentido (cadena a medio cargar fuera de sesión)"
        v.vencimientos.append(iv)
    return v


def _entero(v: float) -> str:
    return f"{v:,.0f}".replace(",", ".")


def construir(ticker: str, split_desde: Optional[date] = None, con_iv: bool = True) -> Posicionamiento:
    """Los apartados que la bolsa publica y, como excepción, la IV del agregador; cada fallo de red deja su
    apartado en N/A con motivo."""
    p = Posicionamiento(obtenido=datetime.now())
    from . import emisores
    if emisores.es_bme(ticker):
        # un emisor de BME: la bolsa no publica nada de esto; cada hueco dice por qué, con el motivo del perfil del
        # emisor, y el sistema por puntos lo declara «No aplica» en 31–35 (no es un fallo de red ni un dato que falte)
        perfil = emisores.perfil(emisores.Emisor(cik="", nombre="", ticker=ticker, bolsa="BME", sic="", descripcion_sic="",
                                                estado_constitucion="", cierre_fiscal="", direccion="", telefono="", web="",
                                                obtenido_en=datetime.now().date(), mercado="bme", moneda="EUR"))
        for clave, capacidad in (("cadena", "opciones"), ("institucional", "trece_f"), ("insiders", "form4"),
                                 ("short", "corto"), ("iv", "opciones")):
            p.faltan[clave] = f"no aplica: {perfil.motivo(capacidad)}"
        return p
    if precio_mod.variable("WC_PRECIO_FUENTE").lower() != "nasdaq":
        p.faltan["fuente"] = "la sección F interina lee la web de Nasdaq y WC_PRECIO_FUENTE no es «nasdaq»"
        return p
    for clave, fn in (("cadena", lambda: _cadena(ticker)), ("institucional", lambda: _institucional(ticker)),
                      ("insiders", lambda: _insiders(ticker)), ("short", lambda: _short(ticker, split_desde))):
        try:
            setattr(p, clave, fn())
        except (HTTPError, URLError, ValueError, TypeError, KeyError, json.JSONDecodeError) as e:
            p.faltan[clave] = f"Nasdaq no sirvió {_QUE[clave]}: {fallo(e)}"
            continue
        motivo = _no_cubre(getattr(p, clave))
        if motivo:
            p.faltan[clave] = motivo
    if con_iv:
        try:
            p.iv = _iv_yahoo(ticker, p.cadena)
            if p.iv is not None and not any(x.hay_iv for x in p.iv.vencimientos):
                motivos = sorted({x.motivo for x in p.iv.vencimientos if x.motivo})
                p.faltan["iv"] = "la bolsa no publica volatilidad implícita y la cadena de Yahoo Finance (excepción) no sirve a esta hora: " + ("; ".join(motivos) or "sin vencimientos")
        except (HTTPError, URLError, ValueError, TypeError, KeyError, IndexError, json.JSONDecodeError) as e:
            p.faltan["iv"] = f"la bolsa no publica volatilidad implícita y Yahoo Finance (excepción) no respondió: {fallo(e)}"
    else:
        p.faltan["iv"] = "la bolsa no publica volatilidad implícita y no se pidió la excepción de Yahoo Finance"
    return p
