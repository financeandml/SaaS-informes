"""BME (Bolsas y Mercados Españoles): la bolsa oficial de los emisores españoles, por su propia API pública.

Es la fuente oficial (CLAUDE.md, reglas 4 y 6) de todo lo que en EE. UU. dan Nasdaq y EDGAR para una empresa española
de BME Growth, BME Scaleup o el Mercado Continuo: el buscador de emisores, la ficha del valor (acciones admitidas,
capitalización, último cierre), el histórico de cierres oficiales y la información que el emisor publica en la bolsa
(cuentas anuales auditadas, informes semestrales, información privilegiada y «otra información relevante»).

Cada respuesta se guarda entera con URL, hora y sha256 en la misma caché por URL y día que la bolsa de EE. UU.
(`precio._json`), así que las pruebas corren sin red con `precio.SOLO_CACHE`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urlencode

__all__ = ["API", "Empresa", "Valor", "Sesion", "Documento", "buscar", "empresa", "valor", "sesiones", "con_negociacion", "indice",
           "cierre_oficial", "ventana_cierre", "documentos", "informacion_financiera", "url_documento", "descargar"]

API = "https://apiweb.bolsasymercados.es/Market/v1/EQ/"
WEB = "https://www.bolsasymercados.es"
# la API responde a lo que pide su propia web: sin Referer devuelve vacío en algunos recursos
CABECERAS = {"User-Agent": "Mozilla/5.0", "Accept": "application/json", "Referer": WEB + "/"}


@dataclass(frozen=True)
class Empresa:
    """Un emisor del buscador de BME: `clave` es el código de emisor de la bolsa, el que piden sus documentos."""
    clave: str
    isin: str
    nombre: str
    nombre_valor: str
    cotiza: bool
    sistema: str            # «SIBE» (Mercado Continuo) o «MTF» (BME Growth, BME Scaleup)
    segmento: str           # «BMEGrowth», «BMEScaleup»… vacío en el Mercado Continuo


@dataclass(frozen=True)
class Valor:
    """La ficha del valor tal como la publica la bolsa."""
    isin: str
    ticker: str
    nombre: str
    clave: str
    acciones: Optional[float]
    capitalizacion: Optional[float]
    ultimo_cierre: Optional[float]
    fecha_ultimo: Optional[date]
    moneda: str
    nominal: Optional[float]
    sistema: str
    segmento: str
    url: str
    # la clasificación sectorial de la bolsa («05»/«01» = servicios financieros/banca): sin SIC, es lo único oficial que
    # dice si el emisor cae en un paquete bloqueado (regla 7; `config/sectores.yaml › bloqueo_bme`)
    sector: str = ""
    subsector: str = ""


@dataclass(frozen=True)
class Sesion:
    """Una sesión del histórico oficial. `fac_mult`/`fac_divi` son el ajuste que la bolsa aplica por operaciones
    societarias (un contrasplit 1×10 viene como 1/10); 0/0 es «sin ajuste»."""
    fecha: date
    cierre: float
    volumen: Optional[float]
    efectivo: Optional[float]
    maximo: Optional[float]
    minimo: Optional[float]
    anterior: Optional[float]
    fac_mult: float
    fac_divi: float


@dataclass(frozen=True)
class Documento:
    """Un documento publicado por el emisor en la bolsa."""
    id: str
    tipo: str               # el de la bolsa, en español («Otra información relevante», «Informes financieros anuales…»)
    clase: str              # «OtherRelevantInformation», «InsideInformation»… o «anual»/«semestral» en la financiera
    titulo: str
    fecha: date
    hora: str
    ruta: str               # relativa, tal como la da la API («/MTFDocuments/…pdf»)
    ejercicio: Optional[int] = None
    periodo: str = ""       # «AN» (anual), «1S» (primer semestre)…
    tamano: str = ""

    @property
    def url(self) -> str:
        return url_documento(self.ruta)


def _pedir(recurso: str, parametros: Dict[str, object]) -> dict:
    from . import precio
    url = API + recurso + "?" + urlencode(parametros)
    return precio._json(url, CABECERAS)


def _fecha(texto) -> Optional[date]:
    s = str(texto or "").strip()
    try:
        return datetime.strptime(s[:8], "%Y%m%d").date() if len(s) >= 8 and s[:8].isdigit() else None
    except ValueError:
        return None


def _num(v) -> Optional[float]:
    """La API da números o null; nunca se convierte un null en cero (regla 9)."""
    try:
        return None if v is None or v == "" else float(v)
    except (TypeError, ValueError):
        return None


def buscar(texto: str, solo_cotizadas: bool = False) -> List[Empresa]:
    """Emisores de BME (Mercado Continuo y BME Growth) cuyo nombre, ISIN o código contiene `texto`."""
    d = _pedir("CompanySearch", {"search": texto, "complete": "true", "tradingSystem": "SIBE,MTF",
                                 "page": 0, "pageSize": 0, "mtfSegment": ""})
    salida = [Empresa(str(x.get("companyKey") or ""), str(x.get("mainShareISIN") or ""), str(x.get("name") or "").strip(),
                      str(x.get("shareName") or "").strip(), bool(x.get("listed")), str(x.get("tradingSystem") or ""),
                      str(x.get("mtfSegment") or "")) for x in (d or {}).get("data") or []]
    return [e for e in salida if e.cotiza] if solo_cotizadas else salida


def empresa(clave: str) -> dict:
    """Datos registrales que publica la bolsa: NIF, domicilio, web, capital admitido."""
    return _pedir("CompanyData/AllData", {"companyKey": clave, "language": "es"}) or {}


def valor(isin: str) -> Optional[Valor]:
    from . import precio
    parametros = {"isin": isin, "language": "es"}
    d = _pedir("ShareDetailsInfo", parametros)
    if not d or not d.get("isin"):
        return None
    return Valor(isin=d["isin"], ticker=str(d.get("ticker") or ""), nombre=str(d.get("name") or "").strip(),
                 clave=str(d.get("issuerCode") or ""), acciones=_num(d.get("shares")), capitalizacion=_num(d.get("capitalisation")),
                 ultimo_cierre=_num(d.get("lastClosePrice")), fecha_ultimo=_fecha(d.get("lastClosePriceDate")),
                 moneda=str(d.get("currency") or ""), nominal=_num(d.get("nominal")), sistema=str(d.get("tradingSystem") or ""),
                 segmento=str(d.get("mtfSegment") or ""), url=API + "ShareDetailsInfo?" + urlencode(parametros),
                 sector=str(d.get("sector") or ""), subsector=str(d.get("subsector") or ""))


def url_sesiones(isin: str, desde: date, hasta: date, pagina: int = 0) -> str:
    return API + "HistoricalSharesPrices?" + urlencode({"isin": isin, "from": desde.strftime("%Y%m%d"), "to": hasta.strftime("%Y%m%d"),
                                                        "page": pagina, "pageSize": 100})   # la API rechaza más de 100


def sesiones(isin: str, desde: date, hasta: date) -> Dict[date, Sesion]:
    """Histórico oficial de cierres entre dos fechas (ambas incluidas), por páginas."""
    from . import precio
    salida: Dict[date, Sesion] = {}
    for pagina in range(0, 60):
        d = precio._json(url_sesiones(isin, desde, hasta, pagina), CABECERAS) or {}
        for x in d.get("data") or []:
            dia, cierre = _fecha(x.get("date")), _num(x.get("close"))
            if dia is None or cierre is None:
                continue
            salida[dia] = Sesion(dia, cierre, _num(x.get("volume")), _num(x.get("turnover")), _num(x.get("high")), _num(x.get("low")),
                                 _num(x.get("previous")), _num(x.get("facMult")) or 0.0, _num(x.get("facDivi")) or 0.0)
        if not d.get("hasMoreResults"):
            break
    return dict(sorted(salida.items()))


def url_indice(isin: str, desde: date, hasta: date, pagina: int = 0) -> str:
    return API + "HistoricalIndicesPrices?" + urlencode({"isin": isin, "from": desde.strftime("%Y%m%d"), "to": hasta.strftime("%Y%m%d"),
                                                         "page": pagina, "pageSize": 100})


def indice(isin: str, desde: date, hasta: date) -> Dict[date, float]:
    """Cierres oficiales de un índice de BME (el mercado de la beta: `config/mercados.yaml`).

    El recurso de índices ignora el número de página (comprobado el 28/09/2026: la página 1 repite la 0), así que se
    pide por ventanas de 120 días naturales, que caben en una página de 100 sesiones."""
    from . import precio
    salida: Dict[date, float] = {}
    inicio = desde
    while inicio <= hasta:
        fin = min(hasta, inicio + timedelta(days=119))
        d = precio._json(url_indice(isin, inicio, fin), CABECERAS) or {}
        for x in d.get("data") or []:
            dia, cierre = _fecha(x.get("date")), _num(x.get("close"))
            if dia is not None and cierre is not None and desde <= dia <= hasta:
                salida[dia] = cierre
        inicio = fin + timedelta(days=1)
    return dict(sorted(salida.items()))


def con_negociacion(historico: Dict[date, Sesion]) -> Dict[date, Sesion]:
    """Solo las sesiones en que el valor se negoció (volumen > 0).

    En un valor poco líquido, un día sin negociación repite el cierre anterior: como precio es el mismo, pero en una
    regresión cuenta como rentabilidad cero del valor frente a un índice que sí se movió y hunde la beta hacia 0. Un
    volumen nulo (la bolsa no lo da) tampoco prueba negociación: fuera también."""
    return {d: s for d, s in historico.items() if s.volumen is not None and s.volumen > 0}


def ventana_cierre() -> int:
    """Días naturales hacia atrás en que se busca la última sesión con negociación (`config/umbrales.yaml`)."""
    from ..umbrales import umbral
    return int(umbral("bme_cierre_ventana_dias"))


def cierre_oficial(isin: str, fecha: date, ventana_dias: Optional[int] = None) -> Optional[Sesion]:
    """La última sesión con negociación ≤ `fecha` (regla 4: nunca intradía, nunca posterior a la valoración). En BME un
    día sin negociación repite ese mismo cierre, así que es el cierre oficial vigente en `fecha`."""
    dias = ventana_cierre() if ventana_dias is None else ventana_dias
    previas = [s for d, s in con_negociacion(sesiones(isin, fecha - timedelta(days=dias), fecha)).items() if d <= fecha]
    return previas[-1] if previas else None


def _documento(x: dict, clase: str = "") -> Optional[Documento]:
    dia = _fecha(x.get("date"))
    if dia is None or not x.get("url"):
        return None
    tipos = x.get("types") or []
    return Documento(id=str(x.get("id") or ""), tipo=str((tipos[0] or {}).get("value") if tipos else "") or "",
                     clase=clase or str(x.get("documentType") or ""), titulo=" ".join(str(x.get("title") or "").split()),
                     fecha=dia, hora=str(x.get("hour") or ""), ruta=str(x["url"]),
                     ejercicio=int(x["financialInfoYear"]) if x.get("financialInfoYear") else None,
                     periodo=str(x.get("financialInfoPeriod") or ""), tamano=str(x.get("size") or ""))


def documentos(clave: str, desde: Optional[date] = None, hasta: Optional[date] = None, maximo: int = 400) -> List[Documento]:
    """Información privilegiada y otra información relevante del emisor, de la más reciente a la más antigua."""
    salida: List[Documento] = []
    parametros = {"companyKey": clave, "language": "es", "pageSize": 50}
    if desde is not None:
        parametros["from"] = desde.strftime("%Y%m%d")
    if hasta is not None:
        parametros["to"] = hasta.strftime("%Y%m%d")
    for pagina in range(0, max(1, maximo // 50)):
        d = _pedir("MtfEquity/Documents", {**parametros, "page": pagina}) or {}
        salida += [doc for doc in (_documento(x) for x in d.get("data") or []) if doc is not None]
        if not d.get("hasMoreResults"):
            break
    return salida


def informacion_financiera(clave: str) -> List[Documento]:
    """Cuentas anuales auditadas e informes semestrales, del periodo más reciente al más antiguo. Cuando la bolsa marca
    que un documento sustituye a otro («replaces»), manda el vigente: es el que publica la API en primer nivel."""
    d = _pedir("MtfEquity/FinancialInformation", {"companyKey": clave, "language": "es"}) or {}
    salida = []
    for x in d.get("data") or []:
        periodo = str(x.get("financialInfoPeriod") or "")
        doc = _documento(x, "anual" if periodo == "AN" else "semestral" if periodo.endswith("S") else "financiera")
        if doc is None and isinstance(x.get("replaces"), dict):
            # la entrada vigente a veces solo trae el enlace dentro de «replaces»: el periodo es el de la entrada
            y = dict(x["replaces"], financialInfoYear=x.get("financialInfoYear"), financialInfoPeriod=periodo, types=x.get("types"))
            doc = _documento(y, "anual" if periodo == "AN" else "semestral")
        if doc is not None and all(d.ruta != doc.ruta for d in salida):      # la bolsa repite a veces la misma entrada
            salida.append(doc)
    return salida


# La base de descarga de los PDF de la bolsa. La API da la ruta relativa («/MTFDocuments/…»); su propia web la sirve
# desde el mismo servidor de la API (`fileUrlPath` de la página «Información publicada»). Se fija aquí, en un solo sitio,
# para que el día que cambie se toque una línea.
BASE_DOCUMENTOS = "https://apiweb.bolsasymercados.es/Market"


def url_documento(ruta: str) -> str:
    return ruta if ruta.startswith("http") else BASE_DOCUMENTOS + ("" if ruta.startswith("/") else "/") + ruta


def descargar(doc: Documento, carpeta: Path) -> Path:
    """El PDF del documento en `carpeta`, con un nombre que dice qué es («bme_2025_AN_<id>.pdf»); si ya está, no se
    vuelve a pedir. Devuelve la ruta."""
    from urllib.request import Request, urlopen
    carpeta.mkdir(parents=True, exist_ok=True)
    sufijo = doc.id or doc.fecha.strftime("%Y%m%d")
    nombre = f"bme_{doc.ejercicio or doc.fecha.year}_{doc.periodo or doc.clase}_{sufijo}.pdf".replace("/", "-")
    destino = carpeta / nombre
    if destino.exists() and destino.stat().st_size > 0:
        return destino
    with urlopen(Request(doc.url, headers={"User-Agent": "Mozilla/5.0", "Referer": WEB + "/"}), timeout=120) as r:
        cuerpo = r.read()
    if not cuerpo.startswith(b"%PDF"):
        raise ValueError(f"la bolsa no devolvió un PDF para «{doc.titulo}»")
    destino.write_bytes(cuerpo)
    return destino


# Qué se trae de la bolsa para el expediente de un emisor de BME, con el mismo contrato que `edgar.traer`: cada documento
# con su resultado («traído», «ya estaba», «error»), nunca un «ok» resumido. Las cuentas anuales de tres ejercicios (la
# comparativa de cada una contrasta la anterior), los dos últimos semestrales, y de la información publicada en los
# últimos 18 meses lo que alimenta el informe: participaciones significativas (5), documento de incorporación (4, 6, 24),
# presentaciones (7, 21) y operaciones de directivos (34). Lo demás (avisos de la bolsa, convocatorias) no se trae.
_OIR_UTILES = (
    ("participaciones", r"(?i)participaciones? significativas?", 1),
    ("incorporacion", r"(?i)documento informativo|doc\. informativo", 1),
    ("presentacion", r"(?i)presentaci[óo]n", 2),
    ("directivos", r"(?i)(?:operaci[óo]n(?:es)?|compras?|ventas?) (?:realizadas?|de|con) (?:por )?(?:directivos|personas con responsabilidades)", 6),
    # lo que un analista cita de la vida corporativa: avances, juntas, ampliaciones y cambios en el consejo
    ("comunicacion", r"(?i)avance de resultados|acuerdos de la junta|ampliaci[óo]n de capital|nombramiento|dimisi[óo]n", 8),
)


def traer(emisor, carpeta: Path, anuales: int = 4, semestrales: int = 2, hoy: Optional[date] = None,
          comunicaciones: bool = True) -> list:
    """Trae a `carpeta` los documentos oficiales del emisor de BME publicados hasta `hoy` y deja su procedencia en
    `origen.json`. `anuales` y `semestrales` cuentan ejercicios y semestres distintos: la bolsa registra a veces dos
    documentos del mismo ejercicio (las cuentas individuales y las consolidadas, o el mismo PDF dos veces), y los dos
    entran sin quitarle el sitio al ejercicio anterior. Sin `comunicaciones`, solo las cuentas (un comparable)."""
    import json
    import re as _re
    from .edgar import Traido
    carpeta = Path(carpeta)
    carpeta.mkdir(parents=True, exist_ok=True)
    hoy = hoy or date.today()
    elegidos = []
    financiera = [d for d in informacion_financiera(emisor.clave_bolsa) if d.fecha is None or d.fecha <= hoy]

    def primeros(docs, cuantos):
        periodos = []
        for d in docs:
            if (d.ejercicio, d.periodo) not in periodos:
                periodos.append((d.ejercicio, d.periodo))
        return [d for d in docs if (d.ejercicio, d.periodo) in periodos[:cuantos]]
    elegidos += [("cuentas anuales", d) for d in primeros([d for d in financiera if d.periodo == "AN"], anuales)]
    elegidos += [("semestral", d) for d in primeros([d for d in financiera if d.periodo != "AN"], semestrales)]
    publicados = documentos(emisor.clave_bolsa, hoy - timedelta(days=548), hoy) if comunicaciones else []
    for clave, patron, cuantos in _OIR_UTILES:
        # la categoría de BME («Operaciones realizadas por directivos») dice más que un título como «Compras realizadas…»
        elegidos += [(clave, d) for d in [d for d in publicados if _re.search(patron, f"{d.tipo} {d.titulo}")][:cuantos]]
    ruta_origen = carpeta / "origen.json"
    try:
        origen = json.loads(ruta_origen.read_text(encoding="utf-8")) if ruta_origen.is_file() else {}
    except (OSError, ValueError):
        origen = {}
    salida = []
    for clave, d in elegidos:
        sufijo = d.id or d.fecha.strftime("%Y%m%d")
        previo = carpeta / f"bme_{d.ejercicio or d.fecha.year}_{d.periodo or d.clase}_{sufijo}.pdf".replace("/", "-")
        estado = "ya estaba" if previo.exists() and previo.stat().st_size > 0 else "traído"
        try:
            ruta = descargar(d, carpeta)
        except Exception as ex:           # un documento que no baja no tumba el resto: se dice cuál y por qué
            salida.append(Traido(clave=clave, estado="error", url=d.url, formulario=d.tipo, presentado=d.fecha,
                                 motivo=f"{d.titulo}: {ex.__class__.__name__}: {ex}"))
            continue
        origen[ruta.name] = {"fuente": "bme", "clave": clave, "url": d.url, "titulo": d.titulo, "publicado": d.fecha.isoformat(),
                             "tipo_bme": d.tipo, "ejercicio": d.ejercicio, "periodo": d.periodo, "id": d.id}
        salida.append(Traido(clave=clave, estado=estado, fichero=ruta.name, url=d.url, formulario=d.tipo, presentado=d.fecha,
                             motivo=d.titulo))
    ruta_origen.write_text(json.dumps(origen, ensure_ascii=False, indent=1), encoding="utf-8")
    return salida
