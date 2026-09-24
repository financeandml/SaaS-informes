"""La ficha de empresa (apartado 1): identidad y cifras de portada, cada una con su fuente.

Lo estructural —nombre registral, CIK, bolsa, SIC, estado de constitución,
cierre fiscal, sede— viene de `submissions` de la SEC. Lo que la SEC solo
publica como texto —empleados, auditor, acciones en circulación y valor en
manos de no afiliados de la portada— se lee del 10-K adjunto con una expresión
por dato, y sale como `Cita` con su página; las acciones en circulación, de la
portada más reciente (10-K o 10-Q), porque con recompras la del 10-K envejece. El año de fundación no está en
ninguna parte estructurada: si el 10-K no lo dice con un año, es N/A.

Lo que la SEC no publica —precio, capitalización, rango de 52 semanas, volumen—
no se estima ni se toma de un agregador: lo sirve `precio.py` si hay un
adaptador oficial configurado, y si no, es N/A con motivo.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional

from .expediente import Adjunto, Expediente, Tipo, _fecha_larga
from .hechos import Capa, Certeza, Cita, Origen
from .sec import Emisor

__all__ = ["Ficha", "construir"]

SIC_ES = {
    "7841": "Alquiler y distribución de vídeo (SIC 7841)",
    "7370": "Servicios informáticos (SIC 7370)",
    "7372": "Software preempaquetado (SIC 7372)",
}


@dataclass
class Ficha:
    emisor: Emisor
    citas: Dict[str, Cita] = field(default_factory=dict)      # clave → cita
    faltan: Dict[str, str] = field(default_factory=dict)      # clave → motivo del N/A


def _cita(adjunto: Adjunto, pagina: int, campo: str, texto: str, valor: Optional[float] = None,
          fecha: Optional[date] = None, nota: str = "") -> Cita:
    return Cita(campo=campo, texto=texto.strip(), valor=valor, fecha=fecha, nota=nota,
                origen=Origen(documento=adjunto.nombre, formulario=adjunto.tipo.value, presentado=adjunto.fecha, pagina=pagina))


def _buscar(adjunto: Adjunto, patron: str, paginas: Optional[range] = None, flags=re.I | re.S):
    for i, texto in enumerate(adjunto.paginas, 1):
        if paginas is not None and i not in paginas:
            continue
        m = re.search(patron, texto, flags)
        if m:
            return i, m, texto
    return None, None, None


def _numero(s: str) -> float:
    return float(s.replace(",", ""))


# Las acciones en circulación de la portada, en las dos formas en que los emisores las declaran. La carátula del
# formulario ocupa dos páginas cuando lleva la lista de valores registrados, así que se buscan en ambas.
_ACCIONES = (
    re.compile(r"As of\s+(?P<fecha>\w+ \d{1,2}, \d{4}),?\s+there were\s+(?P<valor>[\d,]+)\s+shares of the registrant", re.I | re.S),
    re.compile(r"number of shares outstanding of the registrant[’']s common stock was\s+(?P<valor>[\d,.]+)\s*"
               r"(?P<escala>million|billion)?\s*(?:at|as of)\s+(?P<fecha>\w+ \d{1,2}, \d{4})", re.I | re.S),
    # Oracle lo dice al revés y en las dos formas: «Number of shares of common stock outstanding as of June 12,
    # 2026: 2.880.471.000» y «The number of shares of registrant's common stock outstanding as of … was: …»
    re.compile(r"number of shares of[^.]{0,60}?outstanding as of\s+(?P<fecha>\w+ \d{1,2}, \d{4})\s*(?:was)?\s*:?\s*"
               r"(?P<valor>[\d,.]+)\s*(?P<escala>million|billion)?", re.I | re.S),
)
_ESCALAS = {"million": 1e6, "billion": 1e9}


def _acciones_portada(a: Adjunto) -> Optional[Cita]:
    for pagina, texto in enumerate(a.paginas[:2], 1):
        for patron in _ACCIONES:
            m = patron.search(texto)
            if m is None:
                continue
            escala = _ESCALAS.get((m.groupdict().get("escala") or "").lower(), 1.0)
            return _cita(a, pagina, "acciones_portada", m.group(0).replace("\n", " "),
                         _numero(m.group("valor")) * escala, _fecha_larga(m.group("fecha")),
                         nota="declaradas en millones en la portada" if escala != 1.0 else "")
    return None


def construir(emisor: Emisor, exp: Expediente) -> Ficha:
    f = Ficha(emisor=emisor)
    k10 = max(exp.de_tipo(Tipo.K10), key=lambda a: a.periodo_fin or date.min, default=None)
    if k10 is None:
        f.faltan["portada"] = "sin 10-K en el expediente"
        return f
    p1 = k10.paginas[0]
    # Acciones en circulación, con su fecha, de la portada más reciente: un 10-Q posterior al 10-K gana,
    # porque la cifra del 10-K queda vieja en cuanto hay recompras y la capitalización se calcula con ella.
    for a in sorted(exp.de_tipo(Tipo.K10) + exp.de_tipo(Tipo.Q10), key=lambda a: a.periodo_fin or date.min, reverse=True):
        cita = _acciones_portada(a)
        if cita is not None:
            f.citas["acciones_portada"] = cita
            break
    else:
        f.faltan["acciones_portada"] = "ninguna portada de 10-K o 10-Q declara las acciones en circulación con el patrón esperado"
    # Valor de mercado en manos de no afiliados (public float): se rotula así, nunca «capitalización»
    m = re.search(r"As of\s+(\w+ \d{1,2}, \d{4}),?\s+the aggregate market value[^$]{0,400}?\$\s?([\d,]+)", p1, re.I | re.S)
    if m:
        f.citas["float_portada"] = _cita(k10, 1, "float_portada", " ".join(m.group(0).split()), _numero(m.group(2)), _fecha_larga(m.group(1)),
                                         nota="valor de mercado de las acciones en manos de no afiliados a esa fecha; no es la capitalización actual")
    else:
        f.faltan["float_portada"] = "la portada del 10-K no declara el valor en manos de no afiliados con el patrón esperado"
    # Empleados
    pag, m, _ = _buscar(k10, r"As of\s+(\w+ \d{1,2}, \d{4}),?\s+we had approximately\s+([\d,]+)\s+full-time employees", range(2, 12))
    if m:
        f.citas["empleados"] = _cita(k10, pag, "empleados", " ".join(m.group(0).split()), _numero(m.group(2)), _fecha_larga(m.group(1)))
    else:
        f.faltan["empleados"] = "el 10-K no declara el número de empleados con el patrón «we had approximately N full-time employees»"
    # Auditor: la firma bajo el informe de auditoría
    pag, m, texto = _buscar(k10, r"^/s/\s*(.+?)\s*$", None, re.M)
    if m and "Report of Independent Registered Public Accounting Firm" in " ".join(k10.paginas[max(0, pag - 2):pag + 1]):
        ciudad = re.search(r"^([A-Z][A-Za-z .]+, [A-Z][a-z]+)\s*$", texto[m.end():m.end() + 200], re.M)
        f.citas["auditor"] = _cita(k10, pag, "auditor", m.group(1), nota=(ciudad.group(1) if ciudad else ""))
    else:
        f.faltan["auditor"] = "no se halló la firma «/s/» del informe de auditoría en el 10-K"
    # Fundación: solo si el 10-K lo dice con un año. Suele estar en la nota 1 de las cuentas («was incorporated
    # on August 29, 1997»), no en el Item 1, así que se busca en todo el documento; el verbo va pegado a la
    # fecha para no confundirlo con «incorporated by reference», que el 10-K repite decenas de veces.
    pag, m, _ = _buscar(k10, r"([^.]{0,160}\b(?:was|were)\s+(?:founded|incorporated|formed|organized)\s+(?:in|on|under)\b[^.]{0,40}?\b((?:19|20)\d\d)\b[^.]{0,120}\.)")
    if m:
        f.citas["fundacion"] = _cita(k10, pag, "fundacion", " ".join(m.group(1).split()), float(m.group(2)))
    else:
        f.faltan["fundacion"] = "el 10-K adjunto no menciona el año de fundación o constitución"
    # Descripción del negocio: primer párrafo del Item 1
    # El índice del 10-K también dice «Item 1. Business» seguido de números de página:
    # se exige que lo que sigue sea prosa (sin «Item 1A» en los primeros 150 caracteres).
    pag, m, _ = _buscar(k10, r"Item 1\.\s+Business\s+(?!.{0,150}Item 1A)(.{200,900}?\.)\s", range(2, 9))
    if m:
        f.citas["descripcion"] = _cita(k10, pag, "descripcion", " ".join(m.group(1).split()))
    else:
        f.faltan["descripcion"] = "no se halló el arranque del Item 1 «Business»"
    return f
