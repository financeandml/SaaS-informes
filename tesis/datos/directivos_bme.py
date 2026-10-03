"""Operaciones de directivos de un emisor de BME (apartado 34), de sus propias comunicaciones al mercado.

En España no hay Form 4: cada consejero o directivo, o la sociedad que controla, notifica sus operaciones con el modelo
del Reglamento (UE) 596/2014 sobre abuso de mercado, y el emisor lo publica en BME como «Operaciones realizadas por
directivos». El modelo es el mismo para cualquier emisor: el titular va tras «Nombre y apellidos - Razón social», su
cargo tras «Cargo - posición», y cada operación en una línea con el ISIN, el instrumento, la naturaleza, la fecha, el
centro de negociación, el volumen y el precio. Solo se lee lo que dice el documento; lo que no case con ese modelo no
se cuenta.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import List, Optional, Tuple

from ..fuentes.posicionamiento import Insiders

__all__ = ["leer", "insiders"]

_OPERACION = re.compile(r"(?P<isin>[A-Z]{2}[A-Z0-9]{9}\d)\s+(?P<instrumento>Acci[óo]n(?:es)?|[A-Z][a-zá-ú]+)\s+"
                        r"(?P<tipo>Compra|Venta|Suscripci[óo]n|Otros?|Donaci[óo]n|Herencia|Pr[ée]stamo)\s+"
                        r"(?P<fecha>\d{2}/\d{2}/\d{4})\s+(?P<lugar>\S+)\s+(?P<volumen>[\d.]+(?:,\d+)?)\s+(?P<precio>[\d.]+(?:,\d+)?)\s+(?P<moneda>[A-Z]{3})")
_TITULAR = re.compile(r"(?i)Raz[óo]n social\s*\|\s*Name and surname[^\n]*\n\s*([^\n]+)")
_CARGO = re.compile(r"(?i)Cargo\s*-\s*posici[óo]n\s*\|\s*Job title[^\n]*\n\s*([^\n]+)")


def _num(texto: str) -> float:
    return float(texto.replace(".", "").replace(",", "."))


def leer(textos: List[Tuple[str, str]]) -> List[Tuple[str, str, date, str, float, float, str]]:
    """(titular, cargo, fecha, naturaleza, acciones, precio, documento) de cada operación de las notificaciones;
    `textos`: (nombre del documento, texto completo)."""
    salida = []
    for documento, texto in textos:
        if not re.search(r"(?i)responsabilidades? de direcci[óo]n|managerial responsabilit", texto):
            continue
        titular = _TITULAR.search(texto)
        cargo = _CARGO.search(texto)
        for m in _OPERACION.finditer(texto):
            salida.append((" ".join(titular.group(1).split()) if titular else "titular no legible",
                           " ".join(cargo.group(1).split()) if cargo else "",
                           datetime.strptime(m.group("fecha"), "%d/%m/%Y").date(), m.group("tipo"),
                           _num(m.group("volumen")), _num(m.group("precio")), documento))
    return sorted(salida, key=lambda x: x[2], reverse=True)


def insiders(textos: List[Tuple[str, str]], hoy: date) -> Optional[Insiders]:
    """El bloque del apartado 34 con las operaciones leídas: recuento y acciones a 3 y 12 meses y las últimas."""
    ops = [o for o in leer(textos) if o[2] <= hoy]
    if not ops:
        return None
    def suma(desde: date, tipo: str, campo: int) -> Optional[float]:
        dentro = [o for o in ops if o[2] >= desde and o[3] == tipo]
        return (len(dentro) if campo < 0 else sum(o[campo] for o in dentro)) if dentro else 0
    hace3, hace12 = hoy - timedelta(days=91), hoy - timedelta(days=365)
    ins = Insiders()
    ins.operaciones = [("Compras", suma(hace3, "Compra", -1), suma(hace12, "Compra", -1)),
                       ("Ventas", suma(hace3, "Venta", -1), suma(hace12, "Venta", -1))]
    ins.acciones = [("Acciones compradas", suma(hace3, "Compra", 4), suma(hace12, "Compra", 4)),
                    ("Acciones vendidas", suma(hace3, "Venta", 4), suma(hace12, "Venta", 4))]
    ins.ultimas = [(titular, cargo, fecha, tipo, acciones, precio) for titular, cargo, fecha, tipo, acciones, precio, _ in ops]
    ins.total_operaciones = len(ops)
    ins.documentos = sorted({o[6] for o in ops})
    ins.fuente = "bme"
    return ins
