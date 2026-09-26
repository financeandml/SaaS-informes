"""Las operaciones de directivos que publica la bolsa, cruzadas con su Form 4 depositado en EDGAR (apartado 28).

La bolsa resume cada operación (titular, fecha, acciones, precio) a partir de los Form 4, pero lo que imprime es suyo:
el depósito original está en EDGAR, entre los depósitos del propio emisor. Una operación se da por casada con su Form 4
cuando el Form 4 se presentó entre el día de la operación y `umbrales.form4_dias_presentacion_max` días después, su
titular es el mismo y trae, ese día, una línea o la suma de las líneas de un mismo código con las mismas acciones. Si no, se dice cuál de las
tres cosas falló; nunca se da por cruzada una operación que no se ha podido leer.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Callable, List, Optional, Sequence, Tuple

__all__ = ["Cruce", "Linea", "cruzar", "leer"]


@dataclass(frozen=True)
class Linea:
    fecha: date
    codigo: str
    acciones: float
    precio: Optional[float]


@dataclass(frozen=True)
class Cruce:
    casado: bool
    motivo: str = ""
    accession: str = ""
    presentado: Optional[date] = None
    url: str = ""


def _url_xml(d) -> str:
    """El XML en crudo: EDGAR sirve el Form 4 con una hoja de estilo delante (`xslF345X05/…`) que no es el documento."""
    documento = d.documento.split("/")[-1] if d.documento.lower().startswith("xsl") else d.documento
    return f"https://www.sec.gov/Archives/edgar/data/{int(d.cik)}/{d.accession.replace('-', '')}/{documento}"


def _texto(nodo, ruta: str) -> str:
    x = nodo.find(ruta)
    return (x.text or "").strip() if x is not None and x.text else ""


def leer(xml: str) -> Tuple[str, List[Linea]]:
    """(titular, líneas de acciones sin derivados) de un Form 4."""
    raiz = ET.fromstring(xml.encode("utf-8") if isinstance(xml, str) else xml)
    titular = _texto(raiz, "reportingOwner/reportingOwnerId/rptOwnerName")
    lineas = []
    for t in raiz.iter("nonDerivativeTransaction"):
        try:
            fecha = date.fromisoformat(_texto(t, "transactionDate/value")[:10])
            acciones = float(_texto(t, "transactionAmounts/transactionShares/value"))
        except ValueError:
            continue
        precio = _texto(t, "transactionAmounts/transactionPricePerShare/value")
        lineas.append(Linea(fecha, _texto(t, "transactionCoding/transactionCode"), acciones, float(precio) if re.fullmatch(r"[\d.]+", precio) else None))
    return titular, lineas


def _palabras(nombre: str) -> set:
    return {w for w in re.findall(r"[A-Z]+", nombre.upper()) if len(w) > 1}


def _mismo_titular(bolsa: str, form4: str) -> bool:
    """La bolsa y EDGAR escriben el nombre igual («Amon Cristiano R» / «AMON CRISTIANO R») o con otro orden: bastan dos
    palabras en común (apellido y nombre), o una si el nombre solo tiene una."""
    a, b = _palabras(bolsa), _palabras(form4)
    return len(a & b) >= min(2, len(a), len(b)) > 0


def cruzar(ultimas: Sequence[tuple], depositos: Sequence, descargar: Optional[Callable] = None,
           dias: Optional[int] = None) -> List[Cruce]:
    """Un `Cruce` por operación de `ultimas` (insider, relación, fecha, tipo, acciones, precio), en el mismo orden."""
    if descargar is None:
        from .sec import descargar_texto as descargar
    if dias is None:
        from ..umbrales import umbral
        dias = int(umbral("form4_dias_presentacion_max"))
    form4s = [d for d in depositos if d.formulario == "4"]
    leidos: dict = {}

    def leido(d):
        if d.accession not in leidos:
            try:
                leidos[d.accession] = leer(descargar(_url_xml(d))[0])
            except Exception as e:                                  # EDGAR caído o XML roto: se dice, no se cruza
                leidos[d.accession] = e
        return leidos[d.accession]

    salida = []
    for insider, _, fecha, _, acciones, _ in ultimas:
        if fecha is None or acciones is None:
            salida.append(Cruce(False, "la bolsa no da fecha o acciones de esta operación"))
            continue
        candidatos = [d for d in form4s if fecha <= d.presentado <= fecha + timedelta(days=dias)]
        if not candidatos:
            salida.append(Cruce(False, f"ningún Form 4 del emisor presentado entre el {fecha:%d/%m/%Y} y {dias} días después"))
            continue
        motivo, cruce = "", None
        for d in sorted(candidatos, key=lambda x: x.presentado):
            lectura = leido(d)
            if isinstance(lectura, Exception):
                motivo = motivo or f"EDGAR no sirvió el Form 4 {d.accession}"
                continue
            titular, lineas = lectura
            if not _mismo_titular(insider, titular):
                motivo = motivo or f"los Form 4 de esas fechas son de otro titular (p. ej. «{titular}»)"
                continue
            # una línea suelta, o la suma de las del mismo código ese día: el ejercicio de opciones («M») se declara en
            # varias líneas y la retención fiscal del mismo día («F») es otra operación, que no se suma
            del_dia = [x for x in lineas if x.fecha == fecha]
            sumas = {}
            for x in del_dia:
                sumas[x.codigo] = sumas.get(x.codigo, 0.0) + x.acciones
            if any(abs(x.acciones - acciones) <= 0.5 for x in del_dia) or any(abs(s - acciones) <= 0.5 for s in sumas.values()):
                cruce = Cruce(True, "", d.accession, d.presentado, _url_xml(d))
                break
            motivo = f"el Form 4 {d.accession} de {titular} no trae {acciones:,.0f} acciones ese día".replace(",", ".")
        salida.append(cruce or Cruce(False, motivo or "sin Form 4 que case"))
    return salida
