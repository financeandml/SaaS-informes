"""El perfil del emisor: de qué mercado es, qué publica y de qué fuente oficial sale cada cosa.

Un solo punto decide si una clave es de la SEC (ticker de EE. UU.) o de BME (ticker de BME con sufijo «.MC», o su ISIN),
y el resto del programa pregunta aquí en vez de dar por hecho EDGAR y Nasdaq. Las capacidades del perfil son lo que el
mercado publica de verdad: un apartado cuyo punto exige algo que el perfil no tiene sale «No aplica» con este motivo, en
lugar de salir como fallo o, peor, rellenado (sistema por puntos, `tesis/apartados`).

La clave de un emisor de BME es su ticker de la bolsa con «.MC» («RDG.MC»): no choca con un ticker de EE. UU., es un nombre
de fichero válido en Windows (a diferencia de «BME:RDG») y es como lo escribe un analista.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache
from typing import TYPE_CHECKING, Dict, FrozenSet, List, Optional, Tuple

from .sec import Emisor

if TYPE_CHECKING:
    from .tesoro import Rf

__all__ = ["Perfil", "SUFIJO_BME", "es_bme", "clave_bme", "emisor", "buscar", "perfil", "mercados", "bolsa_precio",
           "fuente_cuentas", "antiguedad_max_cierre", "cierres", "indice_beta", "cierres_mercado", "rf", "clasificacion_bolsa"]

SUFIJO_BME = ".MC"
_ISIN_ES = re.compile(r"^ES[A-Z0-9]{9}\d$")
# segmentos de BME que no son empresas analizables (instituciones de inversión colectiva)
_NO_EMPRESAS = {"SICAV", "SIL", "ECR", "ETF"}


def es_bme(clave: str) -> bool:
    c = (clave or "").strip().upper()
    return c.endswith(SUFIJO_BME) or bool(_ISIN_ES.match(c))


def clave_bme(ticker_bolsa: str) -> str:
    return ticker_bolsa.strip().upper() + SUFIJO_BME


@lru_cache(maxsize=1)
def mercados() -> dict:
    import yaml
    from ..rutas import CONFIG
    return yaml.safe_load((CONFIG / "mercados.yaml").read_text(encoding="utf-8")) or {}


@dataclass(frozen=True)
class Perfil:
    """Lo que publica el mercado del emisor. `capacidades` son nombres cortos que los puntos del índice piden
    (`requiere:` en `docs/spec/01_indice.yaml`); `sin` dice por qué falta cada una que no está."""
    mercado: str                         # «sec» | «bme»
    bolsa: str
    moneda: str
    periodicidad: str                    # «trimestral» | «semestral»
    capacidades: FrozenSet[str]
    sin: Dict[str, str] = field(default_factory=dict)

    def tiene(self, capacidad: str) -> bool:
        return capacidad in self.capacidades

    def motivo(self, capacidad: str) -> str:
        return self.sin.get(capacidad, f"el mercado del emisor ({self.bolsa}) no publica «{capacidad}»")


# Lo que publica cada mercado. EE. UU.: todo lo que el SaaS ya lee de EDGAR y Nasdaq. BME: lo que la bolsa y el
# emisor publican (comprobado en la API oficial el 28/09/2026); lo demás, con su porqué.
_SEC = frozenset({"sec", "xbrl", "trimestral", "item1", "item1a", "proxy", "ex21", "ocho_k", "form4", "trece_f",
                  "trece_dg", "opciones", "corto", "consenso", "calendario_bolsa", "segmentos_xbrl", "notas_resultados"})
_BME = frozenset({"bme", "cuentas_pdf", "semestral", "oir", "participaciones", "operaciones_directivos",
                  "documento_incorporacion"})
_SIN_BME = {
    "sec": "el emisor no presenta ante la SEC: es un emisor español de BME",
    "xbrl": "las cuentas de BME Growth se publican en PDF, sin XBRL",
    "trimestral": "el emisor publica información semestral, no trimestral",
    "item1": "no hay 10-K: la descripción del negocio sale de las cuentas anuales y del documento de incorporación",
    "item1a": "no hay 10-K (Item 1A): los factores de riesgo salen del documento de incorporación del emisor",
    "proxy": "no hay DEF 14A: los accionistas significativos salen de las comunicaciones del emisor a BME",
    "ex21": "no hay Exhibit 21: las sociedades del grupo salen de la memoria de las cuentas consolidadas",
    "ocho_k": "no hay 8-K: los hechos relevantes salen de la información privilegiada y otra información relevante publicada en BME",
    "form4": "no hay Form 4: las operaciones de directivos salen de sus comunicaciones publicadas en BME",
    "trece_f": "el régimen 13F es de EE. UU.: no existe para un emisor español",
    "trece_dg": "el régimen 13D/13G es de EE. UU.: las participaciones significativas salen de las comunicaciones a BME",
    "opciones": "la acción no tiene opciones cotizadas",
    "corto": "BME no publica el interés en corto; la CNMV publica solo las posiciones cortas netas ≥ 0,5 % y no responde a consultas automáticas",
    "consenso": "BME no publica consenso de analistas",
    "calendario_bolsa": "BME no publica fechas de resultados: la próxima presentación es la que anuncie el emisor",
    "segmentos_xbrl": "sin XBRL: la cifra de negocios por actividad y mercado sale de la nota de la memoria",
    "notas_resultados": "no hay Exhibit 99.1: la guía sale de las presentaciones y comunicaciones del emisor en BME",
}


def perfil(e: Optional[Emisor]) -> Perfil:
    if e is not None and e.mercado == "bme":
        m = mercados().get("bme") or {}
        return Perfil("bme", e.bolsa or "BME", e.moneda or m.get("moneda", "EUR"), m.get("periodicidad", "semestral"),
                      _BME, dict(_SIN_BME))
    m = mercados().get("sec") or {}
    return Perfil("sec", (e.bolsa if e is not None else "") or "Nasdaq", (e.moneda if e is not None else "") or "USD",
                  m.get("periodicidad", "trimestral"), _SEC, {})


def _ticker_bme(clave: str) -> str:
    return clave.strip().upper()[:-len(SUFIJO_BME)] if clave.strip().upper().endswith(SUFIJO_BME) else clave.strip().upper()


def emisor_bme(clave: str) -> Optional[Emisor]:
    """El emisor de BME por su clave («RDG.MC») o su ISIN: la ficha del valor y los datos registrales de la bolsa."""
    from . import bme
    c = _ticker_bme(clave)
    candidatos = bme.buscar(c, solo_cotizadas=False)
    elegido = None
    for e in candidatos:
        if e.isin == c:
            elegido = e
            break
    if elegido is None:
        # por ticker: la búsqueda devuelve emisores cuyo nombre o código contiene el texto; manda el ticker exacto
        for e in candidatos:
            if e.segmento.upper() in _NO_EMPRESAS:
                continue
            v = bme.valor(e.isin)
            if v is not None and v.ticker.upper() == c:
                elegido = e
                break
    if elegido is None:
        return None
    v = bme.valor(elegido.isin)
    if v is None:
        return None
    reg = bme.empresa(elegido.clave) or {}
    segmento = v.segmento or elegido.segmento
    bolsa = {"BMEGrowth": "BME Growth", "BMEScaleup": "BME Scaleup"}.get(segmento, "Mercado Continuo" if v.sistema == "SIBE" else segmento or "BME")
    return Emisor(cik="", nombre=elegido.nombre, ticker=clave_bme(v.ticker), bolsa=bolsa, sic="", descripcion_sic="",
                  estado_constitucion="España", cierre_fiscal="", direccion=str(reg.get("address") or "").title(),
                  telefono="", web=str(reg.get("websiteURL") or ""), obtenido_en=date.today(), depositos=[],
                  mercado="bme", moneda=v.moneda or "EUR", isin=v.isin, clave_bolsa=elegido.clave, segmento=segmento)


def emisor(clave: str) -> Optional[Emisor]:
    """El emisor de cualquier mercado por su clave: ticker de EE. UU. → SEC; «XXX.MC» o ISIN español → BME."""
    if es_bme(clave):
        return emisor_bme(clave)
    from . import sec
    return sec.emisor(clave)


def buscar(consulta: str, maximo: int = 12) -> List[dict]:
    """Candidatos de los dos mercados para el desplegable: {clave, nombre, mercado, id} (CIK o ISIN). La SEC solo si hay
    contacto configurado (la SEC lo exige); BME no pide identificación."""
    from . import sec
    salida: List[dict] = []
    q = (consulta or "").strip()
    if not q:
        return []
    errores = []
    try:
        salida += [{"clave": t, "nombre": n, "mercado": "sec", "id": f"CIK {int(c)}", "cik": c} for t, n, c in sec.buscar_tickers(q, maximo)]
    except sec.SinContacto as e:
        errores.append(str(e))
    try:
        from . import bme
        for e in bme.buscar(q, solo_cotizadas=True):
            if e.segmento.upper() in _NO_EMPRESAS:
                continue
            v = bme.valor(e.isin)
            if v is None or not v.ticker:
                continue
            salida.append({"clave": clave_bme(v.ticker), "nombre": e.nombre, "mercado": "bme", "id": f"ISIN {e.isin}",
                           "bolsa": {"BMEGrowth": "BME Growth", "BMEScaleup": "BME Scaleup"}.get(e.segmento, "Mercado Continuo")})
            if len([x for x in salida if x["mercado"] == "bme"]) >= maximo:
                break
    except Exception as e:                                  # BME caída no deja sin la SEC
        errores.append(f"BME no respondió: {e}")
    if not salida and errores:
        raise RuntimeError("; ".join(errores))
    return salida[: 2 * maximo]


# ---------------------------------------------------------------------------
# B4 · El mercado del emisor para el motor y la cotización: por despacho según `emisor.mercado` y `config/mercados.yaml`.
# Para la SEC, las mismas peticiones de siempre (Nasdaq, SPY, Tesoro): ni una URL cambia.
# ---------------------------------------------------------------------------

def _config(e: Optional[Emisor]) -> dict:
    return mercados().get("bme" if e is not None and e.mercado == "bme" else "sec") or {}


def bolsa_precio(e: Optional[Emisor]) -> str:
    """La bolsa cuyo cierre oficial es el precio (regla 4), como se nombra en los motivos: «Nasdaq» o «BME»."""
    return {"nasdaq": "Nasdaq", "bme": "BME"}.get(_config(e).get("bolsa_precio", "nasdaq"), "Nasdaq")


def fuente_cuentas(e: Optional[Emisor]) -> str:
    """De dónde salen las cuentas del emisor, como se nombra en los rótulos: «SEC» o «cuentas publicadas en BME»."""
    return "cuentas publicadas en BME" if _config(e).get("bolsa_precio") == "bme" else "SEC"


def antiguedad_max_cierre(e: Optional[Emisor]) -> Optional[int]:
    """Días naturales que puede tener la última sesión con negociación para ser el cierre vigente (BME, valores que no
    cotizan todos los días); None en Nasdaq, que publica todas las sesiones."""
    if _config(e).get("bolsa_precio") != "bme":
        return None
    from . import bme
    return bme.ventana_cierre()


def cierres(e: Emisor, desde: date, hasta: date) -> Dict[date, float]:
    """Cierres oficiales del valor entre dos fechas. SEC: el histórico de Nasdaq, como hasta ahora. BME: el histórico
    oficial, solo las sesiones con negociación (`bme.con_negociacion`: un día sin volumen repite el cierre y hunde la beta)."""
    if _config(e).get("bolsa_precio") == "bme":
        from . import bme
        return {d: s.cierre for d, s in bme.con_negociacion(bme.sesiones(e.isin, desde, hasta)).items()}
    from . import precio
    return precio.cierres_nasdaq(e.ticker, desde, hasta, limite=2000)


def indice_beta(e: Emisor) -> dict:
    """El índice oficial de BME frente al que se mide la beta, según el segmento del valor (`config/mercados.yaml`;
    segmento vacío = Mercado Continuo). Un segmento sin índice configurado es un error de configuración, no un «SPY»."""
    tabla = (mercados().get("bme") or {}).get("mercado_beta") or {}
    segmento = e.segmento or "continuo"
    if segmento not in tabla:
        raise KeyError(f"sin índice de la beta para el segmento «{segmento}» de BME en config/mercados.yaml")
    return tabla[segmento]


def cierres_mercado(e: Emisor, desde: date, hasta: date) -> Tuple[Dict[date, float], str]:
    """(cierres del mercado de la beta, rótulo de la regresión): la serie y lo que dice el informe de ella salen de aquí
    (regla 13). SEC: SPY con cierres de Nasdaq. BME: el índice oficial del segmento, con los cierres de BME."""
    cfg = _config(e)
    if cfg.get("bolsa_precio") == "bme":
        from . import bme
        ind = indice_beta(e)
        return (bme.indice(ind["isin"], desde, hasta),
                f"de los cierres oficiales de BME (solo sesiones con negociación) frente al {ind['nombre']}")
    from . import precio
    mb = cfg["mercado_beta"]
    return (precio.cierres_nasdaq(mb["simbolo"], desde, hasta, limite=2000, clase=mb["clase"]),
            f"frente a {mb['simbolo']} (cierres de Nasdaq)")


def rf(e: Optional[Emisor], fecha: date) -> Tuple[Optional["Rf"], str]:
    """(tipo sin riesgo a 10 años de la moneda del emisor, rótulo de su fuente). None si la fuente no publicó en la fecha."""
    if _config(e).get("rf") == "bce":
        from . import bce
        return bce.rf_10a(fecha), "BCE, curva al contado AAA del área del euro a 10 años"
    from . import tesoro
    return tesoro.rf_10a(fecha), "Tesoro de EE. UU., curva par a 10 años"


def clasificacion_bolsa(e: Emisor) -> Tuple[str, str]:
    """(sector, subsector) de la clasificación de BME en la ficha del valor; vacíos si la bolsa no los publica."""
    from . import bme
    v = bme.valor(e.isin)
    return (v.sector, v.subsector) if v is not None else ("", "")
