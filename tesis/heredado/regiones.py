"""Ingresos por región (apartado 4): la nota del 10-K/10-Q y la hoja regional del emisor, contrastadas.

Netflix declara un solo segmento operativo y desglosa los ingresos por cuatro
regiones (UCAN, EMEA, LATAM, APAC). `companyfacts` no trae ejes, así que la SEC
no sirve este desglose como hecho XBRL sin dimensiones; la fuente estructurada
es la nota de ingresos por región del 10-K y del 10-Q (texto de un formulario
depositado, H con cita) y, para los trimestres, la hoja «Regional Information»
que el emisor publica en su web (Hd).

Las dos se contrastan entre sí donde se solapan, y hay una comprobación más
que es la regla 9 aplicada: la suma de las regiones de un periodo tiene que
ser el ingreso total contrastado de ese periodo. Si no cuadra, se dice.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from ..verificacion.contraste import Tablero
from ..datos.expediente import Adjunto, Expediente, Tipo
from ..datos.extractor import PaginaLeida
from ..formato import numero
from ..datos.hechos import Capa, Certeza, Contraste, Hecho, Origen, Periodo, de_valor

__all__ = ["Regiones", "construir"]

REGIONES = (
    ("UCAN", r"^United States and Canada", "Estados Unidos y Canadá"),
    ("EMEA", r"^Europe, Middle East,? and Africa", "Europa, Oriente Medio y África"),
    ("LATAM", r"^Latin America", "Latinoamérica"),
    ("APAC", r"^Asia-Pacific", "Asia-Pacífico"),
)


@dataclass
class Regiones:
    hechos: Dict[Tuple[str, Periodo], Hecho] = field(default_factory=dict)   # (región, periodo) → hecho
    periodos: List[Periodo] = field(default_factory=list)
    cuadres: List[str] = field(default_factory=list)          # comprobaciones suma = total, en texto
    origenes: Dict[str, Origen] = field(default_factory=dict)
    faltan: Dict[str, str] = field(default_factory=dict)


def _de_paginas(exp: Expediente, paginas: Dict[str, List[PaginaLeida]], r: Regiones) -> None:
    por_clave = {a.clave: a for a in exp.adjuntos}
    for clave, pags in paginas.items():
        a = por_clave[clave]
        if a.tipo not in (Tipo.K10, Tipo.Q10):
            continue
        for p in pags:
            filas_region = [(f, cod, nombre) for f in p.filas for cod, patron, nombre in REGIONES if re.search(patron, f.rotulo)]
            if len(filas_region) < 4:
                continue
            for f, cod, nombre in filas_region:
                for j, cand in f.celdas.items():
                    if cand.periodo is None or cand.porcentaje:
                        continue
                    clave_h = (cod, cand.periodo)
                    if clave_h in r.hechos:
                        continue
                    origen = Origen(documento=a.nombre, formulario=a.tipo.value, presentado=a.fecha, pagina=p.numero, rectangulo=cand.rect_fila)
                    r.hechos[clave_h] = de_valor(f"ingresos_{cod}", cand.periodo, cand.valor, Capa.SEC, origen,
                                                 nota=f"nota de ingresos por región, {a.nombre} pág. {p.numero}").con(contraste=Contraste.CONFIRMADO)
            r.origenes[clave] = Origen(documento=a.nombre, formulario=a.tipo.value, presentado=a.fecha, pagina=p.numero)


def _de_xlsx(exp: Expediente, r: Regiones) -> None:
    import openpyxl
    from datetime import datetime
    for a in exp.de_tipo(Tipo.XLSX):
        wb = openpyxl.load_workbook(str(a.ruta), data_only=True)
        hoja = next((ws for ws in wb.worksheets if "region" in ws.title.lower()), None)
        if hoja is None:
            continue
        filas = list(hoja.iter_rows(values_only=True))
        escala = 1_000 if any(isinstance(c, str) and "in thousands" in c for f in filas[:6] for c in f) else 1
        periodo: Optional[Periodo] = None
        tipo = ""
        for i, f in enumerate(filas, 1):
            celdas = [c for c in f if c is not None and c != ""]
            if any(isinstance(c, str) and "Months Ended" in c for c in celdas):
                tipo = next(c for c in celdas if isinstance(c, str) and "Months Ended" in c)
                continue
            if any(isinstance(c, datetime) for c in celdas):
                fin = next(c for c in celdas if isinstance(c, datetime)).date()
                meses = 3 if "Three" in tipo else 12 if "Twelve" in tipo else 6 if "Six" in tipo else 9
                periodo = Periodo.de_meses(fin, meses)
                continue
            if periodo is None or not isinstance(f[0], str):
                continue
            for cod, patron, nombre in REGIONES:
                if re.search(patron, f[0]):
                    valor = next((c for c in f[1:] if isinstance(c, (int, float))), None)
                    if valor is None:
                        continue
                    clave_h = (cod, periodo)
                    origen = Origen(documento=a.nombre, formulario=a.tipo.value, presentado=a.fecha, pagina=wb.worksheets.index(hoja) + 1,
                                    referencia=f"{hoja.title}!{i}")
                    h = de_valor(f"ingresos_{cod}", periodo, valor * escala, Capa.DOCUMENTO, origen, certeza=Certeza.MEDIA,
                                 motivo="la SEC no sirve el desglose regional sin dimensiones",
                                 nota=f"{a.nombre}, hoja {hoja.title}, fila {i}").con(contraste=Contraste.SOLO_DOCUMENTO)
                    if clave_h in r.hechos:
                        previo = r.hechos[clave_h]
                        if abs(previo.valor - h.valor) <= escala / 2:
                            r.hechos[clave_h] = previo.con(nota=previo.nota + f" · coincide con {a.nombre} ({origen.referencia})")
                        else:
                            r.cuadres.append(f"≠ {cod} {periodo.clave}: formulario {numero(previo.valor)} frente a hoja regional {numero(h.valor)}")
                    else:
                        r.hechos[clave_h] = h
        r.origenes[a.clave] = Origen(documento=a.nombre, formulario=a.tipo.value, pagina=wb.worksheets.index(hoja) + 1)


def construir(exp: Expediente, tablero: Tablero) -> Regiones:
    r = Regiones()
    _de_paginas(exp, tablero.paginas, r)
    _de_xlsx(exp, r)
    if not r.hechos:
        r.faltan["regiones"] = "ni el 10-K/10-Q ni la hoja regional traen ingresos por región con los rótulos esperados"
        return r
    r.periodos = sorted({p for _, p in r.hechos})
    # Regla 9: la suma de las regiones es el ingreso total contrastado del periodo
    for p in r.periodos:
        partes = [r.hechos.get((cod, p)) for cod, _, _ in REGIONES]
        if any(h is None for h in partes):
            continue
        total = tablero.de("ingresos", p)
        if total is None or not total.hecho.hay_dato:
            continue
        suma = sum(h.valor for h in partes)
        if abs(suma - total.hecho.valor) <= 1_000:
            r.cuadres.append(f"✓ {p.clave}: suma de regiones {numero(suma)} = ingresos {numero(total.hecho.valor)}")
        else:
            r.cuadres.append(f"≠ {p.clave}: suma de regiones {numero(suma)} ≠ ingresos {numero(total.hecho.valor)} (diferencia {numero(suma - total.hecho.valor)})")
    return r
