"""Hechos del XBRL inline de un 10-K o 10-Q, con sus dimensiones (03 §5).

`companyfacts` solo sirve hechos sin dimensiones: los ingresos por segmento, producto o país viven únicamente en el
documento depositado, etiquetados con ejes (`StatementBusinessSegmentsAxis`, `ProductOrServiceAxis`,
`StatementGeographicalAxis`, `ConsolidationItemsAxis`). Se leen con la librería estándar: contextos, unidades y
`ix:nonFraction` con su escala y su signo.
"""

from __future__ import annotations

import html as html_mod
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional, Tuple

__all__ = ["Contexto", "HechoIX", "Documento", "leer"]

_CONTEXTO = re.compile(r"<(?:\w+:)?context\b[^>]*\bid=\"([^\"]+)\"[^>]*>(.*?)</(?:\w+:)?context>", re.S)
_MIEMBRO = re.compile(r"<(?:\w+:)?explicitMember\b[^>]*\bdimension=\"([^\"]+)\"[^>]*>\s*([^<\s]+)\s*</(?:\w+:)?explicitMember>", re.S)
_TIPADO = re.compile(r"<(?:\w+:)?typedMember\b[^>]*\bdimension=\"([^\"]+)\"[^>]*>(.*?)</(?:\w+:)?typedMember>", re.S)
_FECHA = {k: re.compile(rf"<(?:\w+:)?{k}>\s*(\d{{4}}-\d\d-\d\d)\s*</(?:\w+:)?{k}>") for k in ("startDate", "endDate", "instant")}
_NUMERO = re.compile(r"<ix:nonFraction\b([^>]*)>(.*?)</ix:nonFraction>", re.S | re.I)
_ATRIBUTO = re.compile(r"([\w:.-]+)=\"([^\"]*)\"")


@dataclass(frozen=True)
class Contexto:
    id: str
    inicio: Optional[date]
    fin: date                              # fin del periodo o el instante
    instante: bool
    dims: Tuple[Tuple[str, str], ...]      # ((eje, miembro), …) ordenado; vacío = consolidado

    @property
    def meses(self) -> int:
        if self.instante or self.inicio is None:
            return 0
        return round((self.fin - self.inicio).days / 30.44)

    def miembro(self, eje_local: str) -> Optional[str]:
        for eje, m in self.dims:
            if eje.split(":")[-1] == eje_local:
                return m
        return None


@dataclass(frozen=True)
class HechoIX:
    concepto: str            # «us-gaap:Revenues»
    contexto: Contexto
    valor: float             # ya escalado y con signo
    unidad: str
    decimales: str
    id: str


@dataclass
class Documento:
    url: str
    contextos: Dict[str, Contexto] = field(default_factory=dict)
    hechos: List[HechoIX] = field(default_factory=list)

    def de(self, conceptos, meses: Optional[int] = None) -> List[HechoIX]:
        """Hechos de uno o varios conceptos (nombre local o con prefijo), sin duplicados (un mismo hecho se etiqueta
        a veces en dos tablas del documento)."""
        nombres = {conceptos} if isinstance(conceptos, str) else set(conceptos)
        vistos, salida = set(), []
        for h in self.hechos:
            if h.concepto not in nombres and h.concepto.split(":")[-1] not in nombres:
                continue
            if meses is not None and h.contexto.meses != meses:
                continue
            clave = (h.concepto, h.contexto.inicio, h.contexto.fin, h.contexto.dims, h.unidad)
            if clave in vistos:
                continue
            vistos.add(clave)
            salida.append(h)
        return salida


def _valor(atributos: Dict[str, str], interior: str) -> Optional[float]:
    texto = " ".join(html_mod.unescape(re.sub(r"<[^>]+>", " ", interior)).split())
    formato = atributos.get("format", "")
    if "zero" in formato or texto in ("—", "–", "-", ""):
        v = 0.0
    else:
        if "comma-decimal" in formato or "numcommadecimal" in formato:
            texto = texto.replace(".", "").replace(" ", "").replace(",", ".")
        else:
            texto = texto.replace(",", "").replace(" ", "")
        try:
            v = float(texto)
        except ValueError:
            return None
    v *= 10 ** int(atributos.get("scale", "0") or 0)
    return -v if atributos.get("sign") == "-" else v


def etiquetas(lab_xml: str) -> Dict[str, str]:
    """Rótulo corto (en inglés) de cada elemento del linkbase de etiquetas del depósito: «qcom:QctMember» → «QCT».
    Preferencia: terseLabel, label sin « [Member]», documentation."""
    locs = {m.group(1): m.group(2) for m in re.finditer(
        r"<(?:\w+:)?loc\b[^>]*xlink:label=\"([^\"]+)\"[^>]*xlink:href=\"[^\"#]*#([^\"]+)\"", lab_xml)}
    locs.update({m.group(2): m.group(1) for m in re.finditer(
        r"<(?:\w+:)?loc\b[^>]*xlink:href=\"[^\"#]*#([^\"]+)\"[^>]*xlink:label=\"([^\"]+)\"", lab_xml)})
    arcos: Dict[str, List[str]] = {}
    for m in re.finditer(r"<(?:\w+:)?labelArc\b([^>]*)/?>", lab_xml):
        a = dict(_ATRIBUTO.findall(m.group(1)))
        arcos.setdefault(a.get("xlink:from", ""), []).append(a.get("xlink:to", ""))
    textos: Dict[str, Dict[str, str]] = {}
    for m in re.finditer(r"<(?:\w+:)?label\b([^>]*)>(.*?)</(?:\w+:)?label>", lab_xml, re.S):
        a = dict(_ATRIBUTO.findall(m.group(1)))
        rol = a.get("xlink:role", "").rsplit("/", 1)[-1]
        textos.setdefault(a.get("xlink:label", ""), {})[rol] = " ".join(html_mod.unescape(m.group(2)).split())
    salida: Dict[str, str] = {}
    for loc, fragmento in locs.items():
        roles: Dict[str, str] = {}
        for destino in arcos.get(loc, []):
            roles.update(textos.get(destino, {}))
        texto = roles.get("terseLabel") or re.sub(r"\s*\[(Member|Axis|Domain)\]$", "", roles.get("label", "")) or roles.get("documentation", "")
        if texto:
            salida[fragmento.replace("_", ":", 1)] = texto
    return salida


def leer(crudo: str, url: str = "") -> Documento:
    doc = Documento(url=url)
    for m in _CONTEXTO.finditer(crudo):
        cuerpo = m.group(2)
        fechas = {k: p.search(cuerpo) for k, p in _FECHA.items()}
        dims = [(e, v) for e, v in _MIEMBRO.findall(cuerpo)]
        dims += [(e, " ".join(re.sub(r"<[^>]+>", " ", v).split())) for e, v in _TIPADO.findall(cuerpo)]
        if fechas["instant"]:
            ctx = Contexto(m.group(1), None, date.fromisoformat(fechas["instant"].group(1)), True, tuple(sorted(dims)))
        elif fechas["endDate"]:
            ctx = Contexto(m.group(1), date.fromisoformat(fechas["startDate"].group(1)) if fechas["startDate"] else None,
                           date.fromisoformat(fechas["endDate"].group(1)), False, tuple(sorted(dims)))
        else:
            continue
        doc.contextos[ctx.id] = ctx
    for m in _NUMERO.finditer(crudo):
        atributos = dict(_ATRIBUTO.findall(m.group(1)))
        ctx = doc.contextos.get(atributos.get("contextRef", ""))
        v = _valor(atributos, m.group(2))
        if ctx is None or v is None or "name" not in atributos:
            continue
        doc.hechos.append(HechoIX(atributos["name"], ctx, v, atributos.get("unitRef", ""), atributos.get("decimals", ""),
                                  atributos.get("id", "")))
    return doc
