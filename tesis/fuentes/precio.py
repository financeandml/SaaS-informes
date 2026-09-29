"""La cotización: de la bolsa o de un proveedor licenciado de datos de bolsa; Yahoo, solo en último extremo.

La SEC no publica cotizaciones. «Fuente oficial» aquí es el mercado de
cotización del valor —la propia web de Nasdaq sirve la última cotización de sus
listados— o un proveedor con licencia del SIP (Polygon/Massive). Yahoo Finance es
un agregador sin licencia declarada y se usa solo si se configura expresamente
como último recurso; cuando se usa, el informe lo rotula «fuente no oficial».

Regla del día de emisión: un precio que no sea del día en que se emite el
informe (o del último día de mercado anterior) no se imprime; sale N/A con el
motivo. Un informe con un precio de hace una semana afirma algo que no es.

La fuente es `WC_PRECIO_FUENTE=nasdaq` (en el entorno o en `.env`), la única admitida (CLAUDE.md, regla 6); sin
configurar, vale «nasdaq» (`entorno._POR_DEFECTO`: no es una elección, es la única). Cualquier otro valor deja el precio
N/A con su motivo; nunca se toma un precio de otra fuente.

De Nasdaq se toma además lo que la propia bolsa publica en la ficha del valor
—volumen, rango de 52 semanas, cierre anterior, capitalización, «1 Year Target»—
y su histórico de cierres, que sirve para dos contrastes: el «cierre anterior» de
la ficha contra el histórico (la misma fuente no puede decir dos cosas) y el
precio que el analista tecleó en su libro contra el cierre oficial de esa fecha.
Con la sesión abierta, el precio es el último cruce y el informe lo rotula así,
con su hora, en lugar de llamarlo cierre.

Un emisor de BME (clave «XXX.MC», `emisores.py`) no pasa por Nasdaq ni por `WC_PRECIO_FUENTE`: su precio es el cierre
oficial de BME de la última sesión con negociación (`_mercado_bme`), en euros, y del mismo histórico oficial salen el
volumen, el rango de 52 semanas y el volumen medio.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from ..entorno import variable
from ..formato import numero
from ..datos.hechos import Capa, Certeza, Contraste, Hecho, Origen, Periodo, de_valor, na
from ..rotulos import fallo

__all__ = ["Consenso", "Cotizacion", "Mercado", "mercado", "obtener", "pedir_crudo"]

_CABECERAS_NASDAQ = {"User-Agent": "Mozilla/5.0", "Accept": "application/json", "Accept-Language": "en-US,en;q=0.9"}


@dataclass(frozen=True)
class Cotizacion:
    precio: float
    fecha: date
    fuente: str
    oficial: bool
    url: str
    moneda: str = "USD"
    hora: str = ""                                   # «12:57 PM ET» del último cruce; vacía si la fuente no la da
    sesion: str = ""                                 # estado del mercado tal cual lo publica la fuente («Open», «Closed»…)
    volumen: Optional[float] = None                  # de la sesión a la que pertenece el precio
    volumen_medio: Optional[float] = None
    cierre_anterior: Optional[float] = None          # lo que la fuente llama «Previous Close»
    rango_52s: Optional[Tuple[float, float]] = None  # (mínimo, máximo)
    cap_mercado_fuente: Optional[float] = None       # la capitalización que publica la fuente, solo para contrastar la nuestra
    objetivo_consenso: Optional[float] = None        # «1 Year Target» que publica Nasdaq en la ficha del valor
    fuera_de_sesion: Optional[Tuple[float, str]] = None   # (precio, hora) del último cruce fuera de sesión, si lo hay; nunca es «el precio»

    @property
    def es_cierre(self) -> bool:
        return self.sesion.lower() not in ("open", "pre-market", "pre market")


@dataclass
@dataclass(frozen=True)
class Consenso:
    """El consenso de analistas que publica la bolsa: precio objetivo medio, rango y recuento de recomendaciones."""
    objetivo: float
    bajo: Optional[float]
    alto: Optional[float]
    compra: Optional[int]
    mantener: Optional[int]
    venta: Optional[int]
    mes: Optional[date]                # fecha del último punto de la serie mensual que publica la bolsa
    url: str

    @property
    def analistas(self) -> Optional[int]:
        partes = [x for x in (self.compra, self.mantener, self.venta) if x is not None]
        return sum(partes) if partes else None


@dataclass
class Mercado:
    """Todo lo que del mercado entra en el informe, con el precio como `Hecho` y los cierres oficiales pedidos."""
    precio: Hecho
    cotizacion: Optional[Cotizacion] = None
    cierres: Dict[date, float] = field(default_factory=dict)      # fecha → cierre oficial (histórico de la bolsa)
    contraste_cierre: Optional[Tuple[Contraste, str]] = None     # «Previous Close» de la ficha frente al histórico: un hecho, una fuente
    consenso: Optional[Consenso] = None
    contraste_consenso: Optional[Tuple[Contraste, str]] = None   # el «1 Year Target» de la ficha frente al consenso de analistas: misma bolsa, dos cifras
    crudos: Dict[str, Tuple[str, str, datetime]] = field(default_factory=dict)   # nombre → (url, cuerpo literal, hora): la evidencia
    faltan: Dict[str, str] = field(default_factory=dict)
    # campo de la cotización → cómo se calculó o por qué no está, cuando la bolsa no lo publica hecho (BME: rango y volumen
    # medio salen del histórico oficial; la capitalización de la ficha es de otra fecha). Vacío en Nasdaq.
    notas: Dict[str, str] = field(default_factory=dict)


_CRUDOS: Dict[str, Tuple[str, datetime]] = {}      # url → (cuerpo literal, hora): lo que se pinta como evidencia


CACHE_BOLSA: Optional[Path] = None   # por defecto <raíz>/cache_bolsa; las pruebas la apuntan a sus fixtures
SOLO_CACHE = False                     # pruebas: nunca a la red, la última respuesta guardada de esa URL


def _ruta_bolsa(url: str, dia: date):
    from .. import entorno
    carpeta = CACHE_BOLSA or Path(entorno.RAIZ) / "cache_bolsa"
    nombre = re.sub(r"[^A-Za-z0-9]+", "_", url.split("://", 1)[-1]).strip("_")
    return carpeta, carpeta / f"{nombre}__{dia.isoformat()}.json.gz"


def texto_con_cache(url: str, cabeceras: Optional[dict] = None) -> str:
    """Un CSV o un texto de una fuente pública (el Tesoro), con la misma caché por URL y día que la bolsa."""
    import gzip
    import hashlib
    carpeta, ruta = _ruta_bolsa(url, date.today())
    if not ruta.exists() and SOLO_CACHE:
        previas = sorted(carpeta.glob(ruta.name.rsplit("__", 1)[0] + "__*.json.gz"))
        if not previas:
            raise URLError(f"sin respuesta guardada de {url}")
        ruta = previas[-1]
    if ruta.exists():
        with gzip.open(ruta, "rt", encoding="utf-8") as f:
            return json.load(f)["cuerpo"]
    with urlopen(Request(url, headers=cabeceras or {"User-Agent": "Mozilla/5.0"}), timeout=60) as r:
        cuerpo = r.read().decode("utf-8", errors="replace")
    carpeta.mkdir(parents=True, exist_ok=True)
    with gzip.open(ruta, "wt", encoding="utf-8") as f:
        json.dump({"url": url, "obtenido": datetime.now().isoformat(timespec="seconds"),
                   "sha256": hashlib.sha256(cuerpo.encode("utf-8")).hexdigest(), "cuerpo": cuerpo}, f, ensure_ascii=False)
    return cuerpo


def _json(url: str, cabeceras: dict) -> dict:
    """Respuesta de la bolsa, guardada entera con URL, hora y sha256 (03 §7); caché por URL y día."""
    import gzip
    import hashlib
    carpeta, ruta = _ruta_bolsa(url, date.today())
    if not ruta.exists() and SOLO_CACHE:
        previas = sorted(carpeta.glob(ruta.name.rsplit("__", 1)[0] + "__*.json.gz"))
        if not previas:
            raise URLError(f"sin respuesta guardada de {url}")
        ruta = previas[-1]
    if ruta.exists():
        with gzip.open(ruta, "rt", encoding="utf-8") as f:
            envoltorio = json.load(f)
        _CRUDOS[url] = (envoltorio["cuerpo"], datetime.fromisoformat(envoltorio["obtenido"]))
        return json.loads(envoltorio["cuerpo"])
    peticion = Request(url, headers=cabeceras)
    with urlopen(peticion, timeout=30) as r:
        cuerpo = r.read().decode("utf-8")
    ahora = datetime.now()
    _CRUDOS[url] = (cuerpo, ahora)
    try:
        carpeta.mkdir(parents=True, exist_ok=True)
        with gzip.open(ruta, "wt", encoding="utf-8") as f:
            json.dump({"url": url, "obtenido": ahora.isoformat(timespec="seconds"),
                       "sha256": hashlib.sha256(cuerpo.encode("utf-8")).hexdigest(), "cuerpo": cuerpo}, f, ensure_ascii=False)
    except OSError:
        pass
    return json.loads(cuerpo)


def pedir_crudo(url: str) -> Tuple[dict, str, datetime]:
    """Una petición a la bolsa devolviendo también el cuerpo literal y la hora (para `recortes.volcado_api`)."""
    datos = _json(url, _CABECERAS_NASDAQ)
    cuerpo, obtenido = _CRUDOS.get(url, (json.dumps(datos), datetime.now()))
    return datos, cuerpo, obtenido


def consenso_nasdaq(ticker: str) -> Optional[Consenso]:
    """El consenso de precio objetivo de la bolsa, con recuento de recomendaciones y el mes del último punto."""
    url = f"https://api.nasdaq.com/api/analyst/{ticker}/targetprice"
    datos = _json(url, _CABECERAS_NASDAQ)
    d = (datos or {}).get("data") or {}
    c = d.get("consensusOverview") or {}
    objetivo = _num(c.get("priceTarget"))
    if objetivo is None:
        return None
    mes = None
    serie = d.get("historicalConsensus") or []
    if serie:
        m = re.match(r"(\d{2})/(\d{2})/(\d{4})", str(((serie[-1] or {}).get("z") or {}).get("date") or ""))
        if m:
            mes = date(int(m.group(3)), int(m.group(1)), int(m.group(2)))
    entero = lambda v: int(v) if _num(v) is not None else None  # noqa: E731
    return Consenso(objetivo=objetivo, bajo=_num(c.get("lowPriceTarget")), alto=_num(c.get("highPriceTarget")),
                    compra=entero(c.get("buy")), mantener=entero(c.get("hold")), venta=entero(c.get("sell")), mes=mes, url=url)


def _num(texto) -> Optional[float]:
    """«$75.71», «12,316,261.94», «N/A» → número o None. Nunca cero por defecto."""
    if texto is None:
        return None
    s = str(texto).replace("$", "").replace(",", "").strip()
    if not s or s.upper() == "N/A":
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _nasdaq(ticker: str) -> Optional[Cotizacion]:
    """La web de Nasdaq: la bolsa de cotización, sin clave. `info` da el último cruce con su fecha y hora;
    `summary` añade cierre anterior, capitalización publicada, volumen medio y el «1 Year Target»."""
    url = f"https://api.nasdaq.com/api/quote/{ticker}/info?assetclass=stocks"
    datos = _json(url, _CABECERAS_NASDAQ)
    d = (datos or {}).get("data") or {}
    primario = d.get("primaryData") or {}
    secundario = d.get("secondaryData") or {}
    sesion = str(d.get("marketStatus") or "")
    fuera = None
    # Fuera de sesión (After-Hours, Pre-Market) la bolsa pone en primaryData el último cruce extrabursátil y en
    # secondaryData el cierre oficial («Closed at Sep 17, 2026 4:00 PM ET»): el precio del informe es el cierre.
    if "Closed at" in str(secundario.get("lastTradeTimestamp") or "") and _num(secundario.get("lastSalePrice")) is not None:
        m_fuera = re.search(r"(\d{1,2}:\d{2} [AP]M ET)", str(primario.get("lastTradeTimestamp") or ""))
        if _num(primario.get("lastSalePrice")) is not None:
            fuera = (_num(primario.get("lastSalePrice")), m_fuera.group(1) if m_fuera else "")
        volumen_sesion = _num(primario.get("volume"))      # el volumen acumulado del día sigue en primaryData
        primario = {**secundario, "volume": volumen_sesion}
        sesion = "Closed"
    precio = _num(primario.get("lastSalePrice"))
    if precio is None:
        return None
    # «Sep 17, 2026 12:57 PM ET» en lastTradeTimestamp: fecha para la regla del día de emisión, hora para rotularlo
    m = re.search(r"([A-Z][a-z]{2} \d{1,2}, \d{4})\s*(\d{1,2}:\d{2} [AP]M ET)?", str(primario.get("lastTradeTimestamp") or ""))
    if not m:
        return None
    fecha = datetime.strptime(m.group(1), "%b %d, %Y").date()
    rango = None
    m52 = re.search(r"([\d.,]+)\s*-\s*([\d.,]+)", (((d.get("keyStats") or {}).get("fiftyTwoWeekHighLow") or {}).get("value") or ""))
    if m52:
        a, b = _num(m52.group(1)), _num(m52.group(2))
        if a is not None and b is not None:
            rango = (min(a, b), max(a, b))
    extra: dict = {}
    try:
        resumen = _json(f"https://api.nasdaq.com/api/quote/{ticker}/summary?assetclass=stocks", _CABECERAS_NASDAQ)
        s = ((resumen or {}).get("data") or {}).get("summaryData") or {}
        valor = lambda clave: _num((s.get(clave) or {}).get("value"))  # noqa: E731
        extra = {"cierre_anterior": valor("PreviousClose"), "cap_mercado_fuente": valor("MarketCap"),
                 "volumen_medio": valor("AverageVolume"), "objetivo_consenso": valor("OneYrTarget")}
    except (HTTPError, URLError, ValueError, TypeError, KeyError):
        pass    # la ficha resumida es un complemento: sin ella, esos campos quedan N/A
    return Cotizacion(precio=precio, fecha=fecha, fuente="Nasdaq (web del mercado)", oficial=True, url=url,
                      hora=m.group(2) or "", sesion=sesion, volumen=_num(primario.get("volume")) if not isinstance(primario.get("volume"), float) else primario["volume"],
                      rango_52s=rango, fuera_de_sesion=fuera, **extra)


@dataclass(frozen=True)
class Sesion:
    apertura: Optional[float]
    maximo: Optional[float]
    minimo: Optional[float]
    cierre: float
    volumen: Optional[float]


def _url_historico(ticker: str, desde: date, hasta: date, limite: int = 400, clase: str = "stocks") -> str:
    return (f"https://api.nasdaq.com/api/quote/{ticker}/historical?assetclass={clase}"
            f"&fromdate={desde:%Y-%m-%d}&todate={hasta:%Y-%m-%d}&limit={limite}")


def sesiones_nasdaq(ticker: str, desde: date, hasta: date, limite: int = 400, clase: str = "stocks") -> Dict[date, Sesion]:
    """Las sesiones oficiales del histórico de Nasdaq (apertura, máximo, mínimo, cierre y volumen) por fecha."""
    url = _url_historico(ticker, desde, hasta, limite, clase)
    datos = _json(url, _CABECERAS_NASDAQ)
    filas = (((datos or {}).get("data") or {}).get("tradesTable") or {}).get("rows") or []
    salida: Dict[date, Sesion] = {}
    for fila in filas:
        c = _num(fila.get("close"))
        try:
            f = datetime.strptime(fila.get("date", ""), "%m/%d/%Y").date()
        except ValueError:
            continue
        if c is not None:
            salida[f] = Sesion(_num(fila.get("open")), _num(fila.get("high")), _num(fila.get("low")), c, _num(fila.get("volume")))
    return salida


def desde_5a(hasta: date) -> date:
    """El inicio del histórico de 5 años que piden el motor (beta), el asistente y la parte G: una sola petición en caché."""
    return date(hasta.year - 5, hasta.month, min(hasta.day, 28)) - timedelta(days=10)


def cierres_nasdaq(ticker: str, desde: date, hasta: date, limite: int = 400, clase: str = "stocks") -> Dict[date, float]:
    """Cierres oficiales por fecha del histórico de Nasdaq; vacío si la bolsa no responde. `clase`: «stocks» o «etf»
    (SPY, el mercado de la beta)."""
    return {f: s.cierre for f, s in sesiones_nasdaq(ticker, desde, hasta, limite, clase).items()}


def _dia_de_mercado_valido(fecha: date, hoy: date) -> bool:
    """Hoy, o el último día laborable anterior (fin de semana o antes de la apertura)."""
    if fecha == hoy:
        return True
    d = hoy
    for _ in range(4):
        d -= timedelta(days=1)
        if d.weekday() < 5:
            return fecha == d
    return False


def _ventana(hoy: date, fechas: Tuple[date, ...] = ()) -> Tuple[date, date]:
    """El tramo del histórico que acompaña a la cotización: las dos últimas semanas hasta el día de emisión (y las fechas
    que se pidan). Una sola petición para la sesión, el cierre anterior, el volumen y la evidencia del apartado 1."""
    return min([hoy - timedelta(days=14), *fechas]) - timedelta(days=7), hoy


def _con_sesion(c: Cotizacion, sesiones: Dict[date, "Sesion"]) -> Cotizacion:
    """La sesión, el volumen y el cierre anterior salen del histórico oficial, no de la ficha (A1, fallos [1] y [66]).

    La ficha de Nasdaq fecha el cierre del viernes con el día anterior («Sep 24» para el cierre del 25/09): su fecha no
    manda. Con el mercado cerrado, el precio de la ficha es el cierre de la última sesión del histórico que lo iguale; esa
    es su fecha, y el volumen es el de esa sesión en el histórico.
    """
    from dataclasses import replace
    if not c.es_cierre or not sesiones:
        return c
    candidatas = sorted((f for f in sesiones if f >= c.fecha and abs(sesiones[f].cierre - c.precio) <= 0.0005 * c.precio), reverse=True)
    if not candidatas:
        return c
    f = candidatas[0]
    return replace(c, fecha=f, volumen=sesiones[f].volumen if sesiones[f].volumen is not None else c.volumen,
                   hora="" if f != c.fecha else c.hora)


def _cotizacion(ticker: str, hoy: date) -> Tuple[Optional[Cotizacion], Hecho]:
    """La cotización de la fuente configurada y el `Hecho` del precio (N/A con motivo si no procede)."""
    p = Periodo.instante(hoy)
    fuente = variable("WC_PRECIO_FUENTE").lower()
    if not fuente:
        return None, na("precio", p, "sin fuente de cotización configurada (WC_PRECIO_FUENTE): la SEC no publica precios", unidad="USD/acción")
    if fuente != "nasdaq":                 # regla 6: el precio es el cierre oficial de Nasdaq y ninguna otra fuente
        return None, na("precio", p, f"fuente de cotización no admitida ({fuente}): el precio es el cierre oficial de Nasdaq", unidad="USD/acción")
    try:
        c = _nasdaq(ticker)
    except (HTTPError, URLError, KeyError, ValueError, TypeError) as e:
        return None, na("precio", p, f"la fuente {fuente} no respondió: {fallo(e)}", unidad="USD/acción")
    if c is None:
        return None, na("precio", p, f"la fuente {fuente} no devolvió cotización para {ticker}", unidad="USD/acción")
    try:
        c = _con_sesion(c, sesiones_nasdaq(ticker, *_ventana(hoy)))
    except (HTTPError, URLError, KeyError, ValueError, TypeError):
        pass                                    # sin histórico, la fecha de la ficha; la regla del día de emisión decide
    if not _dia_de_mercado_valido(c.fecha, hoy):
        return c, na("precio", p, f"la cotización de {c.fuente} es del {c.fecha:%d/%m/%Y}, no del día de emisión", unidad="USD/acción")
    origen = Origen(documento=c.fuente, presentado=c.fecha, referencia=c.url)
    # Con la sesión abierta el precio es el último cruce, no un cierre, y el informe lo dice tal cual
    que = f"cierre del {c.fecha:%d/%m/%Y}" if c.es_cierre else f"último precio del {c.fecha:%d/%m/%Y}, sesión abierta" + (f" ({c.hora})" if c.hora else "")
    if c.fuera_de_sesion is not None:
        que += f"; fuera de sesión se cruzó a {numero(c.fuera_de_sesion[0], 2)}" + (f" ({c.fuera_de_sesion[1]})" if c.fuera_de_sesion[1] else "") + ", que no es el precio del informe"
    hecho = de_valor("precio", Periodo.instante(c.fecha), c.precio, Capa.DOCUMENTO, origen, unidad="USD/acción",
                     certeza=Certeza.ALTA if c.oficial else Certeza.MEDIA,
                     motivo="cotización del mercado" if c.oficial else "fuente no oficial: agregador",
                     nota=f"{c.fuente}, {que}" + ("" if c.oficial else " · FUENTE NO OFICIAL"))
    return c, hecho


def obtener(ticker: str, hoy: date) -> Hecho:
    """El precio del día de emisión como `Hecho`, o N/A con el motivo exacto."""
    from .emisores import es_bme
    if es_bme(ticker):
        return mercado(ticker, hoy).precio
    return _cotizacion(ticker, hoy)[1]


_FUENTE_BME = "BME (histórico oficial de cierres)"
_SEMANAS_RANGO = timedelta(weeks=52)       # el «rango de 52 semanas» es la definición, no un umbral


def _pagina_con(isin: str, desde: date, hasta: date, dia: date) -> Optional[str]:
    """La URL de la página del histórico de BME que trae la sesión `dia`: la evidencia del precio (03 §7)."""
    from . import bme
    marca = f'"date":"{dia:%Y%m%d}"'
    for pagina in range(0, 60):
        url = bme.url_sesiones(isin, desde, hasta, pagina)
        if url not in _CRUDOS:
            return None
        if marca in _CRUDOS[url][0]:
            return url
    return None


def _mercado_bme(e, hoy: date, fechas: Tuple[date, ...] = ()) -> Mercado:
    """Un emisor de BME. Precio = cierre oficial de la última sesión con negociación ≤ `hoy` (regla 4: en BME un día sin
    negociación repite ese cierre), dentro de `umbrales.bme_cierre_ventana_dias`. Del mismo histórico oficial salen el
    volumen de la sesión, el cierre anterior que publica la propia sesión (contrastado con la sesión previa), el rango y
    el volumen medio de 52 semanas y los cierres pedidos. La capitalización de la ficha del valor solo sirve para
    contrastar, y solo si es de la misma sesión. BME no publica consenso: `consenso` queda None y no es un fallo."""
    from . import bme
    moneda = e.moneda or "EUR"
    unidad = f"{moneda}/acción"
    p = Periodo.instante(hoy)
    inicio_rango = hoy - _SEMANAS_RANGO
    desde = min([inicio_rango, _ventana(hoy, tuple(fechas))[0]])
    try:
        historico = bme.sesiones(e.isin, desde, hoy)
    except (HTTPError, URLError, KeyError, ValueError, TypeError) as ex:
        return Mercado(precio=na("precio", p, f"el histórico oficial de BME no respondió: {fallo(ex)}", unidad=unidad))
    negociadas = bme.con_negociacion(historico)
    previas = sorted(d for d in negociadas if d <= hoy)
    ventana = bme.ventana_cierre()
    if not previas or (hoy - previas[-1]).days > ventana:
        return Mercado(precio=na("precio", p, f"sin sesiones con negociación en BME en los {ventana} días anteriores al {hoy:%d/%m/%Y}: "
                                 "no hay cierre oficial vigente", unidad=unidad))
    dia = previas[-1]
    s = negociadas[dia]
    anio = [d for d in previas if d >= inicio_rango]
    cierres_anio = [negociadas[d].cierre for d in anio]
    volumenes = [negociadas[d].volumen for d in anio]
    url = _pagina_con(e.isin, desde, hoy, dia) or bme.url_sesiones(e.isin, desde, hoy)
    que = f"cierre del {dia:%d/%m/%Y}" + ("" if dia == hoy else f", última sesión con negociación hasta el {hoy:%d/%m/%Y}")
    m = Mercado(precio=de_valor("precio", Periodo.instante(dia), s.cierre, Capa.DOCUMENTO, Origen(documento=_FUENTE_BME, presentado=dia, referencia=url),
                                unidad=unidad, certeza=Certeza.ALTA, motivo="cotización del mercado", nota=f"{_FUENTE_BME}, {que}"))
    m.notas["rango_52s"] = (f"mínimo y máximo de los cierres oficiales de BME de las 52 semanas hasta el {hoy:%d/%m/%Y} "
                            f"({len(anio)} sesiones con negociación)")
    m.notas["volumen_medio"] = f"media del volumen (acciones) de esas {len(anio)} sesiones con negociación del histórico oficial de BME"
    m.notas["consenso"] = "BME no publica consenso de analistas"
    cap, ficha = None, None
    try:
        ficha = bme.valor(e.isin)
    except (HTTPError, URLError, KeyError, ValueError, TypeError) as ex:
        m.notas["cap_mercado_fuente"] = f"la ficha del valor de BME no respondió: {fallo(ex)}"
    if ficha is not None:
        if ficha.fecha_ultimo == dia and ficha.capitalizacion is not None:
            cap = ficha.capitalizacion
        else:
            # la ficha da la capitalización de su último cierre: con otra fecha no es un contraste del precio del informe
            de_cuando = f"del {ficha.fecha_ultimo:%d/%m/%Y}" if ficha.fecha_ultimo else "sin fecha"
            m.notas["cap_mercado_fuente"] = f"la ficha de BME publica la capitalización {de_cuando}, no la de la sesión del precio ({dia:%d/%m/%Y})"
        if ficha.url in _CRUDOS:
            m.crudos["cotizacion"] = (ficha.url, *_CRUDOS[ficha.url])
    c = Cotizacion(precio=s.cierre, fecha=dia, fuente=_FUENTE_BME, oficial=True, url=url, moneda=moneda, volumen=s.volumen,
                   volumen_medio=sum(volumenes) / len(volumenes) if volumenes else None, cierre_anterior=s.anterior,
                   rango_52s=(min(cierres_anio), max(cierres_anio)) if cierres_anio else None, cap_mercado_fuente=cap)
    m.cotizacion = c
    ventana_desde = _ventana(hoy, tuple(fechas))[0]
    m.cierres = {d: negociadas[d].cierre for d in previas if d >= ventana_desde}
    if url in _CRUDOS:
        m.crudos["historico"] = (url, *_CRUDOS[url])
    # el cierre anterior que publica la sesión frente a la sesión previa del mismo histórico: un hecho, una fuente
    anteriores = [d for d in previas if d < dia]
    if s.anterior is not None and anteriores:
        f_ant, v_ant = anteriores[-1], negociadas[anteriores[-1]].cierre
        if abs(v_ant - s.anterior) <= 0.005 * abs(v_ant):
            m.contraste_cierre = (Contraste.CONFIRMADO, f"el cierre anterior de la sesión ({numero(s.anterior, 2)}) coincide con el histórico del {f_ant:%d/%m/%Y}")
        else:
            m.contraste_cierre = (Contraste.DISCREPANTE, f"la sesión del {dia:%d/%m/%Y} publica cierre anterior {numero(s.anterior, 2)} y el histórico del {f_ant:%d/%m/%Y} dice {numero(v_ant, 2)}")
    elif s.anterior is None:
        m.faltan["cierre_anterior"] = "el histórico oficial de BME no trae el cierre anterior de la sesión"
    return m


def mercado(ticker: str, hoy: date, fechas: Tuple[date, ...] = (), emisor=None) -> Mercado:
    """Precio del día de emisión, cierres oficiales de las `fechas` pedidas (las que el analista tecleó en su
    libro) y el contraste interno de la fuente: su «cierre anterior» frente a su propio histórico.

    Un emisor de BME (clave «XXX.MC» o ISIN español, o `emisor` ya resuelto con `mercado == "bme"`) va a `_mercado_bme`;
    cualquier otro, a Nasdaq, como siempre."""
    from . import emisores
    if emisor is None and emisores.es_bme(ticker):
        unidad = f"{(emisores.mercados().get('bme') or {}).get('moneda', 'EUR')}/acción"
        try:
            emisor = emisores.emisor(ticker)
        except (HTTPError, URLError, KeyError, ValueError, TypeError) as ex:
            return Mercado(precio=na("precio", Periodo.instante(hoy), f"BME no respondió al buscar {ticker}: {fallo(ex)}", unidad=unidad))
        if emisor is None:
            return Mercado(precio=na("precio", Periodo.instante(hoy), f"BME no tiene un valor cotizado con la clave {ticker}", unidad=unidad))
    if emisor is not None and getattr(emisor, "mercado", "sec") == "bme":
        return _mercado_bme(emisor, hoy, tuple(fechas))
    c, hecho = _cotizacion(ticker, hoy)
    m = Mercado(precio=hecho, cotizacion=c)
    if c is None or variable("WC_PRECIO_FUENTE").lower() != "nasdaq":
        if c is not None:
            m.faltan["cierres"] = f"la fuente {c.fuente} no sirve histórico de cierres en este adaptador"
        return m
    desde, hasta = _ventana(hoy, tuple(fechas))
    try:
        m.cierres = cierres_nasdaq(ticker, desde, hasta)
    except (HTTPError, URLError, KeyError, ValueError, TypeError) as e:
        m.faltan["cierres"] = f"el histórico de Nasdaq no respondió: {fallo(e)}"
        return m
    try:
        m.consenso = consenso_nasdaq(ticker)
    except (HTTPError, URLError, KeyError, ValueError, TypeError) as e:
        m.faltan["consenso"] = f"el consenso de analistas de Nasdaq no respondió: {fallo(e)}"
    if m.consenso is not None and c.objetivo_consenso is not None:
        # dos cifras de la misma bolsa para el mismo hecho: si no coinciden, el informe lo marca
        dif = abs(m.consenso.objetivo - c.objetivo_consenso)
        if dif <= 0.005 * m.consenso.objetivo:
            m.contraste_consenso = (Contraste.CONFIRMADO, f"el «1 Year Target» de la ficha ({numero(c.objetivo_consenso, 2)}) coincide con el consenso de analistas ({numero(m.consenso.objetivo, 2)})")
        else:
            m.contraste_consenso = (Contraste.DISCREPANTE, f"la ficha de Nasdaq dice «1 Year Target» {numero(c.objetivo_consenso, 2)} y su página de analistas {numero(m.consenso.objetivo, 2)}: dos cifras de la misma bolsa para el mismo hecho")
    for nombre, patron in (("cotizacion", "/info?"), ("resumen", "/summary?"), ("consenso", "/targetprice")):
        for url, (cuerpo, obtenido) in _CRUDOS.items():
            if f"/{ticker}/" in url and patron in url:
                m.crudos[nombre] = (url, cuerpo, obtenido)
    # la evidencia del histórico es la ventana que fecha el precio, no la serie de cinco años del motor (A1, fallo [2])
    url_h = _url_historico(ticker, desde, hasta)
    if url_h in _CRUDOS:
        m.crudos["historico"] = (url_h, *_CRUDOS[url_h])
    anteriores = sorted(f for f in m.cierres if f < c.fecha)
    if c.cierre_anterior is not None and anteriores:
        f_ant, v_ant = anteriores[-1], m.cierres[anteriores[-1]]
        if abs(v_ant - c.cierre_anterior) <= 0.005 * abs(v_ant):
            m.contraste_cierre = (Contraste.CONFIRMADO, f"el «cierre anterior» de la ficha ({numero(c.cierre_anterior, 2)}) coincide con el histórico del {f_ant:%d/%m/%Y}")
        else:
            m.contraste_cierre = (Contraste.DISCREPANTE, f"la ficha dice cierre anterior {numero(c.cierre_anterior, 2)} y el histórico del {f_ant:%d/%m/%Y} dice {numero(v_ant, 2)}")
    elif c.cierre_anterior is None:
        m.faltan["cierre_anterior"] = "la ficha de Nasdaq no trae «Previous Close»"
    return m


def sesiones(ticker: str, desde: date, hasta: date, limite: int = 2000) -> Dict[date, "Sesion"]:
    """Las sesiones oficiales de la bolsa del emisor (Nasdaq en EE. UU., BME en España) con apertura, máximo, mínimo,
    cierre y volumen: una sola entrada para liquidez, volatilidad y drawdown, sea cual sea el mercado."""
    from . import emisores
    if not emisores.es_bme(ticker):
        return sesiones_nasdaq(ticker, desde, hasta, limite=limite)
    from . import bme
    e = emisores.emisor(ticker)
    if e is None or not e.isin:
        return {}
    return {d: Sesion(apertura=None, maximo=s.maximo, minimo=s.minimo, cierre=s.cierre, volumen=s.volumen)
            for d, s in bme.sesiones(e.isin, desde, hasta).items()}
