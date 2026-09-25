"""SEC EDGAR: lo que el emisor tiene depositado, tal cual lo depositó.

Tres servicios públicos, sin clave, de dominio público:

    company_tickers.json   ticker → CIK y nombre registral
    submissions            identidad del emisor y todos sus depósitos, con fecha y acceso
    companyfacts           todos los hechos XBRL (10-K y 10-Q), sin dimensiones

La SEC exige identificarse con un `User-Agent` «Nombre correo» y limita a diez
peticiones por segundo. El contacto no se cablea: sería declarar ante la SEC en
nombre de alguien. Se lee de `WC_SEC_CONTACTO` (entorno o `.env`) y, si falta,
no se descarga nada y se dice por qué.

Toda respuesta se guarda íntegra en `cache_sec/`, con la fecha de descarga, para
que cualquier cifra del informe se pueda seguir hasta el fichero que la SEC
sirvió y para no volver a pedirlo.

Las reglas de lectura de XBRL que se fijan aquí y se prueban:

- **Solo 10-K y 10-Q valen para estados financieros.** Una DEF 14A o un 8-K
  también llevan hechos XBRL, redondeados a millones; con «último presentado
  gana» sin este filtro, el beneficio neto FY2025 de Netflix salía
  10.981.000.000 (proxy) en vez de 10.981.201.000 (10-K).
- **Reexpresiones**: por periodo, el último 10-K/10-Q presentado; si el valor
  difiere del primero, se anota «reexpresado en <formulario, fecha>».
- **Sinónimos por periodo**, no por campo: el primer concepto de la lista que
  tenga *ese* periodo gana. Con «primer concepto presente» a secas, un concepto
  antiguo que ya no se usa bloqueaba los periodos recientes del sinónimo vigente.
- **El cuarto trimestre no existe en XBRL**: se deriva FY − 9M y sale rotulado
  como derivado, con su fórmula.
"""

from __future__ import annotations

import gzip
import json
import os
import re
import time
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .campos import Campo
from .formato import numero
from .hechos import Capa, Contraste, Estado, Hecho, Origen, Periodo, de_valor, na

__all__ = [
    "Deposito", "Emisor", "FORMULARIOS_ESTADOS", "Portada10K", "SinContacto",
    "acciones_portada", "ajustar_por_split", "cik_de", "companyfacts", "contacto", "depositos", "desfase_fiscal", "emisor", "float_publico",
    "hechos_xbrl", "periodos_de", "portada_10k", "q4_derivado", "splits", "submissions",
]

RAIZ = Path(__file__).resolve().parent.parent
CACHE = RAIZ / "cache_sec"
FORMULARIOS_ESTADOS = {"10-K", "10-Q", "10-K/A", "10-Q/A"}

# El anexo 99 del 8-K —la nota de resultados y sus tablas— y los ficheros del depósito que no son documentos.
_EX99 = re.compile(r"ex(?:hibit)?[-_ ]?99", re.I)
_NO_DOCUMENTO = re.compile(r"\.(xml|xsd|json|zip|gif|jpg|png|css|js|txt)$", re.I)


def es_anexo_99(nombre: str) -> bool:
    """Si un fichero del índice de un depósito es el anexo 99. Único sitio donde se decide.

    EDGAR lo nombra «ex99-1.htm», «orcl-ex99_1.htm», «exhibit991.htm» o «qcom062826erex991.htm». Con dos detectores distintos —uno por
    prefijo, otro por búsqueda— el mismo 8-K de Qualcomm tenía anexo para traerlo al expediente y no lo tenía para
    leer la previsión de la carta: el mismo hecho contestado de dos maneras (regla 9).
    """
    return bool(_EX99.search(nombre)) and not _NO_DOCUMENTO.search(nombre)
_ULTIMA_PETICION = [0.0]


class SinContacto(RuntimeError):
    pass


def contacto() -> str:
    """Identificación que se envía a la SEC. Del entorno o de `.env`; nunca inventada."""
    from .entorno import variable
    valor = variable("WC_SEC_CONTACTO")
    if not valor or "@" not in valor:
        raise SinContacto("Falta WC_SEC_CONTACTO (entorno o .env) con «Nombre correo@dominio»: "
                          "la SEC rechaza peticiones sin identificar y este programa no inventa una.")
    return valor


def _ruta_cache(url: str) -> Path:
    nombre = re.sub(r"[^A-Za-z0-9]+", "_", url.split("://", 1)[-1]).strip("_")
    return CACHE / (nombre + ".json.gz")


CONSULTADOS: Dict[str, Tuple[date, str]] = {}      # URL → (obtenido, sha256 de lo guardado): fuentes (37) y documentación (39)


def _registrar(url: str, obtenido: date, cuerpo: str) -> None:
    import hashlib
    if url not in CONSULTADOS:
        CONSULTADOS[url] = (obtenido, hashlib.sha256(cuerpo.encode("utf-8")).hexdigest())


def _descargar(url: str, refrescar: bool = False) -> Tuple[dict, date]:
    """Devuelve (JSON, fecha de obtención). Con caché en disco salvo `refrescar`."""
    ruta = _ruta_cache(url)
    if ruta.exists() and not refrescar:
        with gzip.open(ruta, "rt", encoding="utf-8") as f:
            cuerpo = f.read()
        envoltorio = json.loads(cuerpo)
        obtenido = date.fromisoformat(envoltorio["obtenido_en"])
        _registrar(url, obtenido, cuerpo)
        return envoltorio["datos"], obtenido
    espera = 0.11 - (time.monotonic() - _ULTIMA_PETICION[0])
    if espera > 0:
        time.sleep(espera)
    peticion = Request(url, headers={"User-Agent": contacto(), "Accept-Encoding": "gzip, deflate",
                                     "Host": url.split("/")[2]})
    try:
        with urlopen(peticion, timeout=60) as r:
            crudo = r.read()
            if r.headers.get("Content-Encoding") == "gzip":
                crudo = gzip.decompress(crudo)
    except (HTTPError, URLError) as e:
        raise RuntimeError(f"La SEC no sirvió {url}: {e}") from e
    _ULTIMA_PETICION[0] = time.monotonic()
    datos = json.loads(crudo.decode("utf-8"))
    hoy = date.today()
    CACHE.mkdir(exist_ok=True)
    cuerpo = json.dumps({"url": url, "obtenido_en": hoy.isoformat(), "datos": datos}, ensure_ascii=False)
    with gzip.open(ruta, "wt", encoding="utf-8") as f:
        f.write(cuerpo)
    _registrar(url, hoy, cuerpo)
    return datos, hoy


# ---------------------------------------------------------------------------
# Identidad y depósitos
# ---------------------------------------------------------------------------

def descargar_texto(url: str, refrescar: bool = False) -> Tuple[str, date]:
    """Un documento de EDGAR tal cual (HTML de un exhibit, atom de una búsqueda), con la misma caché y el mismo
    User-Agent que los JSON. Devuelve (texto, fecha de obtención)."""
    ruta = _ruta_cache(url)
    if ruta.exists() and not refrescar:
        with gzip.open(ruta, "rt", encoding="utf-8") as f:
            cuerpo = f.read()
        envoltorio = json.loads(cuerpo)
        obtenido = date.fromisoformat(envoltorio["obtenido_en"])
        _registrar(url, obtenido, cuerpo)
        return envoltorio["datos"], obtenido
    espera = 0.11 - (time.monotonic() - _ULTIMA_PETICION[0])
    if espera > 0:
        time.sleep(espera)
    peticion = Request(url, headers={"User-Agent": contacto(), "Accept-Encoding": "gzip, deflate", "Host": url.split("/")[2]})
    try:
        with urlopen(peticion, timeout=60) as r:
            crudo = r.read()
            if r.headers.get("Content-Encoding") == "gzip":
                crudo = gzip.decompress(crudo)
            tipo = r.headers.get("Content-Type", "")
    except (HTTPError, URLError) as e:
        raise RuntimeError(f"La SEC no sirvió {url}: {e}") from e
    _ULTIMA_PETICION[0] = time.monotonic()
    m = re.search(r"charset=([A-Za-z0-9_-]+)", tipo)
    texto = crudo.decode(m.group(1) if m else "utf-8", errors="replace")
    hoy = date.today()
    CACHE.mkdir(exist_ok=True)
    cuerpo = json.dumps({"url": url, "obtenido_en": hoy.isoformat(), "datos": texto}, ensure_ascii=False)
    with gzip.open(ruta, "wt", encoding="utf-8") as f:
        f.write(cuerpo)
    _registrar(url, hoy, cuerpo)
    return texto, hoy


def cik_de(ticker: str) -> Optional[Tuple[str, str]]:
    """(CIK a 10 dígitos, nombre registral) o None si no presenta ante la SEC."""
    datos, _ = _descargar("https://www.sec.gov/files/company_tickers.json")
    for fila in datos.values():
        if fila["ticker"].upper() == ticker.upper():
            return f"{int(fila['cik_str']):010d}", fila["title"]
    return None


def buscar_tickers(consulta: str, maximo: int = 12) -> List[Tuple[str, str, str]]:
    """(ticker, nombre registral, CIK) de los emisores de `company_tickers.json` que empiezan por la consulta (ticker)
    o la contienen (nombre); primero los tickers exactos y por prefijo, luego por nombre. Sin consulta, nada."""
    q = consulta.strip().upper()
    if not q:
        return []
    datos, _ = _descargar("https://www.sec.gov/files/company_tickers.json")
    filas = list(datos.values())
    def orden(f):
        # ticker exacto · ticker por prefijo (alfabético: BRK-A antes que BRKH) · nombre que empieza así · nombre que lo contiene
        tk, nombre = f["ticker"].upper(), f["title"].upper()
        return (0, tk) if tk == q else (1, tk) if tk.startswith(q) else (2, nombre) if nombre.startswith(q) else (3, nombre)
    candidatos = [f for f in filas if f["ticker"].upper().startswith(q) or q in f["title"].upper()]
    return [(f["ticker"], f["title"], f"{int(f['cik_str']):010d}") for f in sorted(candidatos, key=orden)[:maximo]]


def submissions(cik: str, refrescar: bool = False) -> Tuple[dict, date]:
    return _descargar(f"https://data.sec.gov/submissions/CIK{cik}.json", refrescar)


def companyfacts(cik: str, refrescar: bool = False) -> Tuple[dict, date]:
    return _descargar(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json", refrescar)


@dataclass(frozen=True)
class Deposito:
    cik: str
    formulario: str
    presentado: date
    periodo: Optional[date]
    accession: str
    documento: str
    epigrafes: str            # items de un 8-K («2.02,9.01»), vacío en el resto
    descripcion: str = ""

    @property
    def url(self) -> str:
        return f"https://www.sec.gov/Archives/edgar/data/{int(self.cik)}/{self.accession.replace('-', '')}/{self.documento}"


@dataclass
class Emisor:
    cik: str
    nombre: str
    ticker: str
    bolsa: str
    sic: str
    descripcion_sic: str
    estado_constitucion: str
    cierre_fiscal: str          # «1231»
    direccion: str
    telefono: str
    web: str
    obtenido_en: date
    depositos: List[Deposito] = field(default_factory=list)

    def ultimo(self, formulario: str) -> Optional[Deposito]:
        for d in self.depositos:
            if d.formulario == formulario:
                return d
        return None


def emisor(ticker: str) -> Optional[Emisor]:
    identidad = cik_de(ticker)
    if identidad is None:
        return None
    cik, _ = identidad
    s, obtenido = submissions(cik)
    dir_ = s.get("addresses", {}).get("business", {})
    direccion = ", ".join(x for x in (dir_.get("street1"), dir_.get("city"), dir_.get("stateOrCountry"), dir_.get("zipCode")) if x)
    e = Emisor(cik=cik, nombre=s.get("name", ""), ticker=ticker.upper(),
               bolsa=(s.get("exchanges") or [""])[0], sic=str(s.get("sic", "")),
               descripcion_sic=s.get("sicDescription", ""), estado_constitucion=s.get("stateOfIncorporation", ""),
               cierre_fiscal=s.get("fiscalYearEnd", ""), direccion=direccion, telefono=s.get("phone", ""),
               web=s.get("website", "") or "", obtenido_en=obtenido)
    e.depositos = depositos(cik, s)
    return e


def depositos(cik: str, s: Optional[dict] = None) -> List[Deposito]:
    if s is None:
        s, _ = submissions(cik)
    r = s["filings"]["recent"]
    salida = []
    for i in range(len(r["form"])):
        salida.append(Deposito(
            formulario=r["form"][i], presentado=date.fromisoformat(r["filingDate"][i]),
            periodo=date.fromisoformat(r["reportDate"][i]) if r["reportDate"][i] else None,
            accession=r["accessionNumber"][i], documento=r["primaryDocument"][i],
            epigrafes=r["items"][i] if "items" in r else "", descripcion=r.get("primaryDocDescription", [""] * len(r["form"]))[i],
            cik=cik))
    return salida


# ---------------------------------------------------------------------------
# Hechos XBRL
# ---------------------------------------------------------------------------

def _periodo_de(fila: dict) -> Periodo:
    fin = date.fromisoformat(fila["end"])
    if "start" in fila and fila["start"]:
        return Periodo(fin=fin, inicio=date.fromisoformat(fila["start"]))
    return Periodo(fin=fin)


def _filas_concepto(facts: dict, concepto: str) -> Tuple[str, List[dict]]:
    """Las filas de un concepto en cualquier espacio de nombres («dei:X» o «X» en us-gaap)."""
    espacio, _, nombre = concepto.rpartition(":")
    espacio = espacio or "us-gaap"
    unidades = facts.get("facts", {}).get(espacio, {}).get(nombre, {}).get("units", {})
    for unidad, filas in unidades.items():
        return unidad, filas
    return "", []


def _por_suma_de_conceptos(facts: dict, campo: Campo, ya_estan: Dict[Periodo, Hecho]) -> Dict[Periodo, Hecho]:
    """Los periodos que la compañía no etiqueta con el concepto agregado y sí con sus partes.

    Oracle no declara «Liabilities», declara «LiabilitiesCurrent» y «LiabilitiesNoncurrent»; no declara la
    amortización conjunta, declara la del inmovilizado y la de los intangibles; no declara el resultado antes de
    impuestos, declara el nacional y el extranjero. Cada grupo entra entero o no entra, y lo que sale es un derivado
    con su fórmula y sus entradas, nunca un hecho publicado por la SEC.
    """
    from .hechos import derivar
    salida: Dict[Periodo, Hecho] = {}
    for grupo in campo.conceptos_suma:
        partes: Dict[str, Dict[Periodo, Hecho]] = {}
        for concepto in grupo:
            unidad, filas = _filas_concepto(facts, concepto)
            por_periodo: Dict[Periodo, dict] = {}
            for fila in filas:
                if fila["form"] not in FORMULARIOS_ESTADOS:
                    continue
                p = _periodo_de(fila)
                if p.es_instante != (campo.tipo == "instante"):
                    continue
                if p not in por_periodo or fila["filed"] > por_periodo[p]["filed"]:
                    por_periodo[p] = fila
            partes[concepto] = {
                p: de_valor(concepto, p, f["val"], Capa.SEC, unidad=campo.unidad,
                            origen=Origen(documento="SEC EDGAR", formulario=f["form"],
                                          presentado=date.fromisoformat(f["filed"]), concepto=f"us-gaap:{concepto}",
                                          referencia=f["accn"]))
                for p, f in por_periodo.items()}
        comunes = set.intersection(*(set(v) for v in partes.values())) if partes else set()
        for p in comunes - set(ya_estan) - set(salida):
            entradas = {c: partes[c][p] for c in grupo}
            salida[p] = derivar(campo.clave, p, " + ".join(f"us-gaap:{c}" for c in grupo), entradas,
                                lambda **kw: sum(kw.values()), unidad=campo.unidad)
    return salida


def hechos_xbrl(facts: dict, campo: Campo, obtenido_en: date,
                periodos: Optional[Iterable[Periodo]] = None) -> Dict[Periodo, Hecho]:
    """Los hechos SEC de un campo, por periodo, con las reglas del módulo.

    Sin `periodos` devuelve todos los que la SEC trae. Con `periodos`, los
    pedidos: los que la SEC no tiene salen N/A con motivo, para que la ausencia
    se vea y no se confunda con «no se pidió».
    """
    por_periodo: Dict[Periodo, Tuple[dict, str, dict]] = {}   # periodo → (fila elegida, concepto, primera fila)
    for concepto in campo.conceptos:
        unidad, filas = _filas_concepto(facts, concepto)
        for fila in filas:
            if fila["form"] not in FORMULARIOS_ESTADOS:
                continue
            p = _periodo_de(fila)
            if (p.es_instante) != (campo.tipo == "instante"):
                continue
            actual = por_periodo.get(p)
            if actual is None:
                por_periodo[p] = (fila, concepto, fila)
            elif actual[1] == concepto:
                elegida, _, primera = actual
                if fila["filed"] > elegida["filed"]:
                    elegida = fila
                if fila["filed"] < primera["filed"]:
                    primera = fila
                por_periodo[p] = (elegida, concepto, primera)
            # un concepto posterior de la lista no sustituye al primero que tenga el periodo
    salida: Dict[Periodo, Hecho] = {}
    for p, (fila, concepto, primera) in por_periodo.items():
        nota = ""
        if primera is not fila and primera["val"] != fila["val"]:
            nota = f"reexpresado en {fila['form']} presentado el {fila['filed']} (antes {primera['val']:,} en {primera['form']} de {primera['filed']})"
        origen = Origen(documento="SEC EDGAR", formulario=fila["form"],
                        presentado=date.fromisoformat(fila["filed"]), concepto=f"us-gaap:{concepto}" if ":" not in concepto else concepto,
                        referencia=fila["accn"])
        salida[p] = de_valor(campo.clave, p, fila["val"], Capa.SEC, origen, unidad=campo.unidad, nota=nota)
    for p, h in _por_suma_de_conceptos(facts, campo, salida).items():
        salida[p] = h
    if periodos is not None:
        pedidos = {}
        cierres_fiscales = None
        for p in periodos:
            if p in salida:
                pedidos[p] = salida[p]
            else:
                if cierres_fiscales is None and p.meses == 3:
                    cierres_fiscales = {a.fin for a in calendario(facts, 12)}
                # el 4T es el trimestre que acaba con el ejercicio fiscal, no el de octubre a diciembre
                motivo = ("la SEC no presenta el cuarto trimestre fiscal como tal"
                          if (p.meses == 3 and p.fin in (cierres_fiscales or ())) else
                          f"la SEC no publica «{campo.rotulo}» para {f'{p.fin:%d/%m/%Y}' if p.es_instante else p.clave} en ningún 10-K ni 10-Q"
                          + ("" if campo.conceptos else " (la SEC no tiene una partida normalizada para esto)"))
                pedidos[p] = na(campo.clave, p, motivo, unidad=campo.unidad)
        return pedidos
    return salida


def splits(facts: dict) -> List[Tuple[date, float, Origen]]:
    """Los desdoblamientos de acciones que la SEC registra, con fecha y razón.

    Un 10-Q presentado antes del split trae BPA y acciones sin reexpresar; el
    10-K posterior, reexpresados. La serie solo es homogénea si se ajusta lo
    anterior, y el ajuste es un derivado con fórmula, nunca un cambio silencioso.
    """
    unidad, filas = _filas_concepto(facts, "StockholdersEquityNoteStockSplitConversionRatio1")
    vistos: Dict[date, Tuple[float, Origen]] = {}
    for f in filas:
        if f["form"] not in FORMULARIOS_ESTADOS:
            continue
        fecha = date.fromisoformat(f["end"])
        if fecha not in vistos:
            vistos[fecha] = (float(f["val"]), Origen(documento="SEC EDGAR", formulario=f["form"], presentado=date.fromisoformat(f["filed"]),
                                                     concepto="us-gaap:StockholdersEquityNoteStockSplitConversionRatio1", referencia=f["accn"]))
    # la misma operación llega declarada en varias fechas (anuncio, efectividad, cierre del trimestre): un split de la
    # misma razón a menos de 90 días del anterior es el mismo split, no otro; contarlo dos veces multiplicaría el ajuste
    salida: List[Tuple[date, float, Origen]] = []
    for fecha, (razon, origen) in sorted(vistos.items()):
        if salida and salida[-1][1] == razon and (fecha - salida[-1][0]).days <= 90:
            continue
        salida.append((fecha, razon, origen))
    return salida


def ajustar_por_split(h: Hecho, ajustes: Sequence[Tuple[date, float, Origen]], por_accion: bool) -> Hecho:
    """Reexpresa un hecho presentado antes de un split: BPA ÷ razón, acciones × razón. Derivado, con fórmula."""
    if not h.hay_dato or h.origen is None or h.origen.presentado is None:
        return h
    aplicables = [(fecha, razon) for fecha, razon, _ in ajustes if fecha > h.origen.presentado]
    if not aplicables:
        return h
    from .hechos import derivar
    factor = 1.0
    for _, razon in aplicables:
        factor *= razon
    descripcion = " y ".join(f"split {razon:g}:1 del {fecha:%d/%m/%Y}" for fecha, razon in aplicables)
    formula = (f"valor presentado ÷ {factor:g}" if por_accion else f"valor presentado × {factor:g}") + f" ({descripcion}; us-gaap:StockholdersEquityNoteStockSplitConversionRatio1)"
    ajustado = derivar(h.campo, h.periodo, formula, {"presentado": h},
                       (lambda presentado: presentado / factor) if por_accion else (lambda presentado: presentado * factor), unidad=h.unidad)
    return ajustado.con(origen=h.origen, nota=f"reexpresado por {descripcion}; el {h.origen.formulario} de {h.origen.presentado:%d/%m/%Y} publicó {numero(h.valor, 2)}")


def calendario(facts: dict, meses: int) -> List[Periodo]:
    """Los periodos de `meses` meses que la compañía declara de verdad en sus 10-K/10-Q, en orden cronológico.

    El calendario no se puede calcular. Quien cierra por semanas —Qualcomm, Apple, Cisco: el domingo más cercano a
    fin de mes— no cierra el mismo día cada año: 26/09/2021, 25/09/2022, 24/09/2023, 29/09/2024, 28/09/2025. Un
    ejercicio construido a mano («el mismo día del año pasado») no coincide con ningún hecho de la SEC, que van
    fechados con el cierre real, y la empresa entera sale N/A: 405 huecos y cero cifras confirmadas en Qualcomm.
    Aquí el calendario lo dicta el emisor.

    De cada cierre se queda el intervalo más repetido: el mismo cierre puede venir con dos comienzos —el ejercicio y
    el acumulado de una filial— y manda el que usan casi todos los conceptos.
    """
    cuenta: Dict[Tuple[date, date], int] = {}
    for espacio, conceptos in (facts.get("facts") or {}).items():
        for datos in conceptos.values():
            for filas in (datos.get("units") or {}).values():
                for fila in filas:
                    if fila.get("form") not in FORMULARIOS_ESTADOS or not fila.get("start"):
                        continue
                    par = (date.fromisoformat(fila["start"]), date.fromisoformat(fila["end"]))
                    cuenta[par] = cuenta.get(par, 0) + 1
    por_cierre: Dict[date, Tuple[int, date]] = {}
    for (inicio, fin), veces in cuenta.items():
        if Periodo(fin=fin, inicio=inicio).meses != meses:
            continue
        if fin not in por_cierre or veces > por_cierre[fin][0]:
            por_cierre[fin] = (veces, inicio)
    return [Periodo(fin=fin, inicio=inicio) for fin, (_, inicio) in sorted(por_cierre.items())]


def periodos_de(hechos: Dict[Periodo, Hecho], meses: Optional[int]) -> List[Periodo]:
    """Los periodos de `meses` meses (None = instantes) que hay, en orden cronológico."""
    return sorted(p for p in hechos if p.meses == meses)


def trimestre_por_acumulados(facts: dict, campo: Campo, hechos: Dict[Periodo, Hecho], p: Periodo) -> Optional[Hecho]:
    """El trimestre que la compañía no publica suelto: acumulado hasta su cierre − acumulado hasta el anterior.

    El estado de flujos de un 10-Q va acumulado desde el comienzo del ejercicio: Oracle publica el flujo de caja de
    seis y de nueve meses, no el del segundo ni el del tercer trimestre. Los dos sumandos son cifras publicadas y la
    resta es la definición del trimestre, así que sale como derivado con su fórmula; sin ella, catorce celdas de la
    sección C se quedaban vacías por una convención de presentación.
    """
    from datetime import timedelta
    from .hechos import derivar
    if p.es_instante or p.meses != 3 or campo.unidad != "USD":
        return None
    anuales = calendario(facts, 12)
    fy = next((a for a in anuales if a.inicio <= p.inicio and p.fin <= a.fin), None)
    if fy is not None:
        inicio_fy = fy.inicio
    else:
        # el ejercicio en curso aún no tiene 10-K: empieza el día siguiente al último cierre anual. Sin esto, el 2T y
        # el 3T del ejercicio abierto —los que más pesan en el TTM— se quedaban sin amortización ni flujo de caja.
        previos = [a for a in anuales if a.fin < p.inicio]
        if not previos:
            return None
        inicio_fy = previos[-1].fin + timedelta(days=1)
    if inicio_fy == p.inicio:      # el primer trimestre ya es el acumulado: no hay nada que restar
        return None
    hasta = hechos.get(Periodo(fin=p.fin, inicio=inicio_fy))
    hasta_antes = hechos.get(Periodo(fin=p.inicio - timedelta(days=1), inicio=inicio_fy))
    if hasta is None or hasta_antes is None or not hasta.hay_dato or not hasta_antes.hay_dato:
        return None
    return derivar(campo.clave, p, f"{hasta.periodo.clave} − {hasta_antes.periodo.clave} (la compañía publica el flujo "
                                   f"acumulado del ejercicio, no el del trimestre)",
                   {"acumulado": hasta, "acumulado_anterior": hasta_antes},
                   lambda acumulado, acumulado_anterior: acumulado - acumulado_anterior, unidad=campo.unidad)


def desfase_fiscal(facts: dict) -> int:
    """Cuánto se aparta la numeración del ejercicio de la compañía del año en que acaba (0 casi siempre).

    La SEC guarda en cada hecho el `fy` del formulario que lo presenta. En el último 10-K, el ejercicio que cierra
    es el suyo: si la compañía lo numera por el año en que empieza (un minorista que cierra el 1 de febrero de 2025 y
    lo llama 2024), `fy` − año de cierre da −1 y los rótulos lo respetan.
    """
    from datetime import timedelta
    mejor: Optional[Tuple[str, int]] = None
    for conceptos in (facts.get("facts") or {}).values():
        for datos in conceptos.values():
            for filas in (datos.get("units") or {}).values():
                for f in filas:
                    if f.get("form") != "10-K" or f.get("fp") != "FY" or not f.get("start") or not f.get("fy"):
                        continue
                    p = Periodo(fin=date.fromisoformat(f["end"]), inicio=date.fromisoformat(f["start"]))
                    if p.meses != 12:
                        continue
                    clave = (f["filed"], p.fin.isoformat())
                    if mejor is None or clave > mejor[0]:
                        mejor = (clave, int(f["fy"]) - (p.fin - timedelta(days=7)).year)
    return mejor[1] if mejor and mejor[1] in (-1, 0, 1) else 0


def float_publico(facts: dict) -> Optional[Tuple[float, date, Origen]]:
    """Valor en manos de no afiliados de la portada del último 10-K (dei:EntityPublicFloat), con su fecha."""
    filas = [f for f in (((facts.get("facts") or {}).get("dei") or {}).get("EntityPublicFloat") or {}).get("units", {}).get("USD", [])
             if f.get("form") in ("10-K", "10-K/A")]
    if not filas:
        return None
    f = max(filas, key=lambda f: (f["filed"], f["end"]))
    return (float(f["val"]), date.fromisoformat(f["end"]),
            Origen(documento="SEC EDGAR", formulario=f["form"], presentado=date.fromisoformat(f["filed"]),
                   concepto="dei:EntityPublicFloat", referencia=f["accn"]))


def acciones_portada(facts: dict) -> Optional[Tuple[float, date, Origen]]:
    """Acciones en circulación de la portada del último 10-K o 10-Q (dei:EntityCommonStockSharesOutstanding)."""
    filas = [f for f in (((facts.get("facts") or {}).get("dei") or {}).get("EntityCommonStockSharesOutstanding") or {}).get("units", {}).get("shares", [])
             if f.get("form") in ("10-K", "10-Q", "10-K/A", "10-Q/A")]
    if not filas:
        return None
    ultimo = max(f["filed"] for f in filas)
    # companyfacts omite la cifra cuando la compañía la etiqueta por clases: la última sin clases puede ser de hace años
    # (Comcast: 2009). Una portada anterior en más de 400 días al último depósito con cuentas no es la vigente.
    gaap = (facts.get("facts") or {}).get("us-gaap") or {}
    presentados = [f["filed"] for c in ("NetIncomeLoss", "Assets") for u in ((gaap.get(c) or {}).get("units") or {}).values() for f in u
                   if f.get("form") in ("10-K", "10-Q", "10-K/A", "10-Q/A")]
    if presentados and (date.fromisoformat(max(presentados)) - date.fromisoformat(ultimo)).days > 400:
        return None
    # una compañía con varias clases declara una fila por clase en el mismo formulario: se suman
    del_ultimo = [f for f in filas if f["filed"] == ultimo]
    f = del_ultimo[0]
    return (float(sum(x["val"] for x in del_ultimo)), date.fromisoformat(f["end"]),
            Origen(documento="SEC EDGAR", formulario=f["form"], presentado=date.fromisoformat(f["filed"]),
                   concepto="dei:EntityCommonStockSharesOutstanding", referencia=f["accn"]))


@dataclass
class Portada10K:
    """Lo que el 10-K declara en texto y la SEC no sirve en companyfacts: DEI no numéricas y el texto del documento."""
    deposito: Deposito
    obtenido_en: date
    dei: Dict[str, str]
    nombre_portada: str       # la línea encima de «(Exact name of registrant as specified in its charter)»
    texto: str                # el documento en texto plano, para proponer citas (empleados, fundación…)


def portada_10k(e: Emisor) -> Optional[Portada10K]:
    """El documento principal del último 10-K, de EDGAR: sus hechos DEI en XBRL inline y su texto plano.

    El auditor sale de `dei:AuditorName`, que la SEC exige desde 2021; leerlo de la firma «/s/» del PDF confundía al
    consejero delegado con la firma de auditoría.
    """
    import html as html_mod
    d = e.ultimo("10-K")
    if d is None:
        return None
    crudo, obtenido = descargar_texto(d.url)
    dei: Dict[str, str] = {}
    for m in re.finditer(r'<ix:nonNumeric[^>]*\bname="dei:([A-Za-z]+)"[^>]*>(.*?)</ix:nonNumeric>', crudo, re.S):
        valor = " ".join(html_mod.unescape(re.sub(r"<[^>]+>", " ", m.group(2))).split())
        dei.setdefault(m.group(1), valor)
    texto = " ".join(html_mod.unescape(re.sub(r"<[^>]+>", " ", crudo)).split())
    m = re.search(r"([A-Z0-9][A-Za-z0-9&.,'’\- ]{1,80}?)\s*\(\s*Exact name of registrant as specified in its charter\s*\)", texto)
    nombre = m.group(1).strip() if m else ""
    nombre = re.sub(r"^.*Commission [Ff]ile [Nn]umber\s*[\d-]+\s*", "", nombre).strip()
    return Portada10K(deposito=d, obtenido_en=obtenido, dei=dei, nombre_portada=nombre, texto=texto)


def q4_derivado(fy: Hecho, nueve_meses: Hecho) -> Hecho:
    """4T = ejercicio − nueve meses acumulados. Derivado, con fórmula, nunca «hecho SEC»."""
    from .hechos import derivar
    p = Periodo.de_meses(fy.periodo.fin, 3)
    return derivar(fy.campo, p, f"{fy.periodo.clave} − 9M{fy.periodo.fin.year % 100:02d}",
                   {"fy": fy, "nueve_meses": nueve_meses}, lambda fy, nueve_meses: fy - nueve_meses,
                   unidad=fy.unidad)
