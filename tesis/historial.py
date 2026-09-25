"""Historial de resultados (apartado 32): ¿ha fallado antes? Lo que dicen los adjuntos, no una opinión.

Dos fuentes, las dos en el expediente:
- La portada de la transcripción (S&P Global Market Intelligence) trae consenso, real y
  sorpresa de los últimos cuatro trimestres y del trimestre publicado, más el consenso
  y la guía del siguiente. Se lee la tabla tal cual, con su página, y el «real» se
  contrasta con el hecho del informe (BPA diluido, ingresos) cuando existe.
- La carta a accionistas dice, con sus palabras, si el trimestre quedó en línea, por
  encima o por debajo de la previsión de la propia compañía. Se citan esas frases.

Y dos más, fuera del expediente pero oficiales o autorizadas (18/09/2026):
- Las cartas de trimestres anteriores depositadas en la SEC (Ex. 99.1 de cada 8-K de
  resultados, `cartas.py`): la previsión de la compañía para cada trimestre frente a lo
  que publicó después. Es la respuesta documental a «¿ha fallado antes?».
- La serie de consenso frente a real que publica la bolsa (Nasdaq, con la fecha de cada
  publicación), cuadrada con el BPA diluido de la sección C.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from datetime import date, datetime

from .expediente import Adjunto, Expediente, Tipo
from .formato import numero
from .hechos import Capa, Certeza, Cita, Contraste, Hecho, Origen, Periodo
from .rotulos import fallo

__all__ = ["Historial", "Sorpresa", "SorpresaBolsa", "construir"]

_FILA_TRIMESTRE = re.compile(r"^FQ([1-4]) (20\d\d)\s+(\(?[\d.]+\)?)\s+(\(?[\d.]+\)?)\s+(\(?)([\d.]+)\s*%\)?\s*$", re.M)


def _con_parentesis(s: str) -> float:
    """El proveedor escribe los negativos entre paréntesis."""
    return -float(s.strip("()")) if s.startswith("(") else float(s)
_FILA_EPS = re.compile(r"^EPS Normalized\s+([\d.]+)\s+([\d.]+)\s+(\(?)([\d.]+)\s+([\d.]+|NA)\s+([\d.]+|NA)\s+([\d.]+|NA)\s+(?:NA\s+)*([\d.]+|NA)", re.M)
_FILA_INGRESOS = re.compile(r"^Revenue \(mm\)\s+([\d.]+)\s+([\d.]+)\s+(\(?)([\d.]+)\s*%\)?\s+([\d.]+|NA)\s+([\d.]+|NA)\s+([\d.]+|NA)\s+(?:NA\s+)*([\d.]+|NA)", re.M)
_PALABRAS_GUIA = re.compile(r"\b(?:in-line with|in line with|ahead of (?:our )?forecast|above our forecast|below our forecast|slightly (?:above|below)|versus our (?:guidance|forecast))", re.I)
_FIN_FRASE = re.compile(r"(?<=[.!?])\s+(?=[A-Z“\"(])")   # un punto seguido de mayúscula; «$12.6B» no parte la frase


@dataclass
class Sorpresa:
    periodo: str                 # «3T25»
    metrica: str                 # «BPA normalizado» · «Ingresos (M USD)»
    consenso: float
    real: float
    sorpresa: float              # fracción con signo
    pagina: int
    contraste: Contraste = Contraste.SIN_CONTRASTAR
    nota: str = ""


@dataclass
class SorpresaBolsa:
    periodo: str                 # «2T26»
    publicado: Optional[date]    # fecha en que la compañía publicó
    consenso: float
    real: float
    sorpresa: Optional[float]    # fracción con signo, tal cual la publica la bolsa
    contraste: Contraste = Contraste.SIN_CONTRASTAR
    nota: str = ""


@dataclass
class Historial:
    sorpresas: List[Sorpresa] = field(default_factory=list)
    bolsa: List[SorpresaBolsa] = field(default_factory=list)                 # consenso frente a real según la bolsa
    bolsa_respuesta: Optional[Tuple[str, str, datetime]] = None              # (url, cuerpo, obtenido)
    guias: list = field(default_factory=list)                                # cartas.Guia: previsión de la compañía frente a real
    cartas: list = field(default_factory=list)                               # cartas.Carta leídas de EDGAR
    consenso_siguiente: List[Tuple[str, str, Optional[float], Optional[float]]] = field(default_factory=list)  # (periodo, métrica, consenso, guía)
    consenso_anual: List[Tuple[str, str, Optional[float]]] = field(default_factory=list)                        # (FY, métrica, consenso)
    frases_guia: List[Cita] = field(default_factory=list)
    fuente: Optional[Origen] = None
    proveedor: str = ""
    faltan: Dict[str, str] = field(default_factory=dict)


def _num(t: str) -> Optional[float]:
    return None if t == "NA" else float(t)


def _sorpresa(parentesis: str, valor: str) -> float:
    return (-1 if parentesis else 1) * float(valor) / 100


def _trimestre(q: str, anio: str) -> str:
    return f"{q}T{anio[2:]}"


def _leer_call(call: Adjunto, h: Historial, hechos: Dict[Tuple[str, Periodo], Hecho]) -> None:
    for numero, texto in enumerate(call.paginas, 1):
        if "Estimates" not in texto or "CONSENSUS" not in texto:
            continue
        h.fuente = Origen(documento=call.nombre, formulario=call.tipo.value, presentado=call.fecha, pagina=numero)
        m = re.search(r"^(.*?)\s+Estimates\s*$", texto, re.M)
        h.proveedor = m.group(1).strip() if m else "tabla de estimaciones de la portada"
        cabecera = re.search(r"-FQ([1-4]) (20\d\d)-\s+-FQ([1-4]) (20\d\d)-\s+-FY (20\d\d)-\s+-FY (20\d\d)-", texto)
        for mm in _FILA_TRIMESTRE.finditer(texto):
            h.sorpresas.append(Sorpresa(periodo=_trimestre(mm.group(1), mm.group(2)), metrica="BPA normalizado (USD)", consenso=_con_parentesis(mm.group(3)),
                                        real=_con_parentesis(mm.group(4)), sorpresa=_sorpresa(mm.group(5), mm.group(6)), pagina=numero))
        if cabecera:
            publicado, siguiente = _trimestre(cabecera.group(1), cabecera.group(2)), _trimestre(cabecera.group(3), cabecera.group(4))
            fy1, fy2 = f"FY{cabecera.group(5)}", f"FY{cabecera.group(6)}"
            me, mi = _FILA_EPS.search(texto), _FILA_INGRESOS.search(texto)
            if mi:
                h.sorpresas.append(Sorpresa(periodo=publicado, metrica="Ingresos (M USD)", consenso=float(mi.group(1)), real=float(mi.group(2)),
                                            sorpresa=_sorpresa(mi.group(3), mi.group(4)), pagina=numero))
                h.consenso_siguiente.append((siguiente, "Ingresos (M USD)", _num(mi.group(5)), _num(mi.group(6))))
                h.consenso_anual += [(fy1, "Ingresos (M USD)", _num(mi.group(7))), (fy2, "Ingresos (M USD)", _num(mi.group(8)))]
            if me:
                h.consenso_siguiente.append((siguiente, "BPA normalizado (USD)", _num(me.group(5)), _num(me.group(6))))
                h.consenso_anual += [(fy1, "BPA normalizado (USD)", _num(me.group(7))), (fy2, "BPA normalizado (USD)", _num(me.group(8)))]
        break
    if h.fuente is None:
        h.faltan["consenso"] = "la transcripción adjunta no trae la tabla de consenso/real/sorpresa de la portada"
        return
    # el «real» del proveedor frente al hecho contrastado del informe: es el mismo hecho y debe coincidir
    indice = {(campo, p.clave): x for (campo, p), x in hechos.items()}
    for s in h.sorpresas:
        clave = ("bpa_diluido" if s.metrica.startswith("BPA") else "ingresos", s.periodo)
        x = indice.get(clave)
        if x is None or not x.hay_dato:
            s.nota = "sin hecho contrastado en el informe para este periodo"
            continue
        valor = x.valor if clave[0] == "bpa_diluido" else x.valor / 1e6
        tol = 0.005 if clave[0] == "bpa_diluido" else 0.5
        if abs(valor - s.real) <= tol:
            s.contraste = Contraste.CONFIRMADO
            s.nota = "el real del proveedor coincide con el hecho contrastado (sección C)"
        else:
            s.contraste = Contraste.DISCREPANTE
            s.nota = f"el proveedor publica {numero(s.real, 2)} y el hecho contrastado es {numero(valor, 2)}: BPA normalizado ≠ BPA GAAP diluido" if clave[0] == "bpa_diluido" \
                else f"el proveedor publica {numero(s.real, 2)} y el hecho contrastado es {numero(valor, 2)}"


def _leer_carta(carta: Adjunto, h: Historial) -> None:
    for numero, texto in enumerate(carta.paginas[:3], 1):
        for frase in _FIN_FRASE.split(" ".join(texto.split())):
            frase = frase.strip()
            if _PALABRAS_GUIA.search(frase) and 30 < len(frase) < 400:
                h.frases_guia.append(Cita(campo="guia_vs_real", texto=frase, capa=Capa.DOCUMENTO, certeza=Certeza.ALTA,
                                          origen=Origen(documento=carta.nombre, formulario=carta.tipo.value, presentado=carta.fecha, pagina=numero)))
    if not h.frases_guia:
        h.faltan["guia_vs_real"] = "la carta adjunta no compara el trimestre con la previsión de la compañía con palabras reconocibles"


_MES = {"Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6, "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12}


def _periodo_bolsa(texto: str) -> str:
    """«Jun 2026» → «2T26»."""
    m = re.match(r"([A-Z][a-z]{2}) (20\d\d)", texto or "")
    return f"{(_MES[m.group(1)] - 1) // 3 + 1}T{m.group(2)[2:]}" if m and m.group(1) in _MES else texto


def _leer_bolsa(ticker: str, h: Historial, hechos: Dict[Tuple[str, Periodo], Hecho]) -> None:
    from .precio import pedir_crudo
    url = f"https://api.nasdaq.com/api/company/{ticker}/earnings-surprise"
    try:
        datos, cuerpo, obtenido = pedir_crudo(url)
    except Exception as e:
        h.faltan["consenso_bolsa"] = f"la bolsa no sirvió la serie de sorpresas: {fallo(e)}"
        return
    filas = (((datos or {}).get("data") or {}).get("earningsSurpriseTable") or {}).get("rows") or []
    if not filas:
        h.faltan["consenso_bolsa"] = "la bolsa no publica la serie de consenso frente a real para este valor"
        return
    h.bolsa_respuesta = (url, cuerpo, obtenido)
    indice = {(campo, p.clave): x for (campo, p), x in hechos.items()}
    for f in filas:
        try:
            consenso, real = float(f.get("consensusForecast")), float(f.get("eps"))
        except (TypeError, ValueError):
            continue
        try:
            sorpresa = float(f.get("percentageSurprise")) / 100
        except (TypeError, ValueError):
            sorpresa = None
        m = re.match(r"(\d{1,2})/(\d{1,2})/(20\d\d)", f.get("dateReported") or "")
        publicado = date(int(m.group(3)), int(m.group(1)), int(m.group(2))) if m else None
        s = SorpresaBolsa(_periodo_bolsa(f.get("fiscalQtrEnd", "")), publicado, consenso, real, sorpresa)
        x = indice.get(("bpa_diluido", s.periodo))
        if x is not None and x.hay_dato:
            if abs(x.valor - real) <= 0.005:
                s.contraste, s.nota = Contraste.CONFIRMADO, "coincide con el BPA diluido de la sección C"
            else:
                s.contraste, s.nota = Contraste.DISCREPANTE, f"la bolsa publica {real:g} y el BPA diluido contrastado es {x.valor:.2f}"
        else:
            s.nota = "trimestre fuera del alcance de la sección C"
        h.bolsa.append(s)
    h.bolsa.sort(key=lambda s: s.publicado or date.min)


def construir(exp: Expediente, hechos: Dict[Tuple[str, Periodo], Hecho], cik: Optional[str] = None, ticker: Optional[str] = None,
              splits: Sequence[Tuple[date, float]] = (), maximo_cartas: int = 9) -> Historial:
    h = Historial()
    call = max(exp.de_tipo(Tipo.CALL), key=lambda a: a.orden, default=None)
    carta = max(exp.de_tipo(Tipo.CARTA) + exp.de_tipo(Tipo.NOTA), key=lambda a: a.orden, default=None)
    if call is None:
        h.faltan["consenso"] = "sin transcripción en el expediente: no hay tabla de consenso frente a real"
    else:
        _leer_call(call, h, hechos)
    if carta is None:
        h.faltan["guia_vs_real"] = "sin carta a accionistas en el expediente"
    else:
        _leer_carta(carta, h)
    if cik:
        from . import cartas as cartas_mod
        h.cartas, faltan_cartas = cartas_mod.cartas_edgar(cik, maximo_cartas)
        h.guias = cartas_mod.guias_frente_a_real(h.cartas, hechos, splits)
        if not h.guias:
            h.faltan["guias_anteriores"] = "EDGAR no devolvió cartas con tabla de previsión: " + ("; ".join(f"{k}: {v}" for k, v in faltan_cartas.items()) or "sin 8-K de resultados")
        for k, v in faltan_cartas.items():
            h.faltan[f"carta {k}"] = v
    else:
        h.faltan["guias_anteriores"] = "sin CIK: las cartas anteriores no se han pedido a EDGAR"
    if ticker:
        _leer_bolsa(ticker, h, hechos)
    return h
