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

__all__ = ["Ficha", "construir", "describir_cierre", "nombre_presentacion", "proponer_empleados", "proponer_fundacion"]

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
    nombre_presentacion: str = ""     # propuesta: la portada del 10-K, sin sufijo de estado ni mayúsculas de registro
    cierre_descrito: str = ""         # «último domingo de septiembre (ejercicio de 52/53 semanas)»
    constitucion: str = ""            # «Delaware (EE. UU.)»
    sede: str = ""                    # «5775 Morehouse Dr, San Diego, CA 92121 (EE. UU.)»


_MESES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre")
_DIAS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")
_ESTADOS = {"AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California", "CO": "Colorado", "CT": "Connecticut",
            "DE": "Delaware", "DC": "Distrito de Columbia", "FL": "Florida", "GA": "Georgia", "HI": "Hawái", "ID": "Idaho", "IL": "Illinois",
            "IN": "Indiana", "IA": "Iowa", "KS": "Kansas", "KY": "Kentucky", "LA": "Luisiana", "ME": "Maine", "MD": "Maryland",
            "MA": "Massachusetts", "MI": "Míchigan", "MN": "Minnesota", "MS": "Misisipi", "MO": "Misuri", "MT": "Montana", "NE": "Nebraska",
            "NV": "Nevada", "NH": "Nuevo Hampshire", "NJ": "Nueva Jersey", "NM": "Nuevo México", "NY": "Nueva York", "NC": "Carolina del Norte",
            "ND": "Dakota del Norte", "OH": "Ohio", "OK": "Oklahoma", "OR": "Oregón", "PA": "Pensilvania", "RI": "Rhode Island",
            "SC": "Carolina del Sur", "SD": "Dakota del Sur", "TN": "Tennessee", "TX": "Texas", "UT": "Utah", "VT": "Vermont",
            "VA": "Virginia", "WA": "Washington", "WV": "Virginia Occidental", "WI": "Wisconsin", "WY": "Wyoming"}


_FORMAS = {"INC": "Inc.", "CORP": "Corp.", "LTD": "Ltd.", "CO": "Co."}


def nombre_presentacion(portada: str, registral: str) -> str:
    """El nombre con que se titula el informe: el de la portada del 10-K («QUALCOMM Incorporated»), sin el sufijo de
    estado del nombre registral de EDGAR («/DE») y sin las mayúsculas de registro en palabras largas. Es una propuesta:
    el analista la confirma en el asistente."""
    base = (portada or registral or "").strip()
    base = re.sub(r"\s*/[A-Z]{2}\s*$", "", base)
    palabras = []
    for w in base.split():
        letras = re.sub(r"[^A-Za-z]", "", w)
        if len(letras) > 4 and letras.isupper() and "&" not in w:
            w = w[0] + w[1:].lower()
        palabras.append(w)
    # la forma jurídica en mayúsculas de registro («TEXAS INSTRUMENTS INC»): como se escribe
    if len(palabras) > 1 and palabras[-1].rstrip(".") in _FORMAS:
        palabras[-1] = _FORMAS[palabras[-1].rstrip(".")]
    return " ".join(palabras)


def describir_cierre(cierres: List[date]) -> str:
    """Cómo cierra la compañía su ejercicio, dicho con sus propias fechas de cierre (las de la SEC)."""
    from datetime import timedelta
    if not cierres:
        return ""
    if len({(d.month, d.day) for d in cierres}) == 1:
        d = cierres[-1]
        return f"{d.day} de {_MESES[d.month - 1]}"
    dias = {d.weekday() for d in cierres}
    if len(dias) == 1:
        dia = _DIAS[dias.pop()]
        ultimos = all((d + timedelta(days=7)).month != d.month for d in cierres)
        mes = _MESES[(cierres[-1] - timedelta(days=7)).month - 1]
        forma = f"último {dia} de {mes}" if ultimos else f"el {dia} más cercano a fin de {mes}"
        return forma + " (ejercicio de 52/53 semanas)"
    return f"{cierres[-1].day} de {_MESES[cierres[-1].month - 1]} (variable)"


# Empleados y fundación: patrones de lengua, no de un emisor. La cifra de plantilla se dice de muchas formas («we had
# approximately 16,000 full-time employees», «we had approximately 52,000 full-time, part-time and temporary workers»);
# lo que no cambia es el verbo, la cifra y un sustantivo de personas a pocas palabras.
_EMPLEADOS = re.compile(
    r"(?:(?:As of|At)\s+(?P<fecha>[A-Z][a-z]+ \d{1,2}, \d{4}),?\s+)?(?:we|the Company)\s+(?:had|employed|employ|have)\s+"
    r"(?:approximately|about|over|more than|roughly|nearly)?\s*(?P<valor>\d[\d,]{2,})\s+(?:[A-Za-z-]+,?\s+){0,6}?"
    r"(?:employees|workers|people|team members|associates)\b[^.]{0,200}\.", re.I)
_FUNDACION = re.compile(r"[^.]{0,160}?\b(?:incorporated|founded|organized|formed|established)\s+(?:in|on|under)\b[^.]{0,60}?"
                        r"\b(?P<anio>(?:18|19|20)\d\d)\b[^.]{0,120}\.", re.I)


def proponer_empleados(texto: str):
    """(valor, fecha, frase) de la primera declaración de plantilla del texto, o None."""
    m = _EMPLEADOS.search(texto)
    if not m:
        return None
    return _numero(m.group("valor")), (_fecha_larga(m.group("fecha")) if m.group("fecha") else None), " ".join(m.group(0).split())


def proponer_fundacion(texto: str):
    """(año, frase) de la primera frase que fecha la constitución o la fundación, o None."""
    m = _FUNDACION.search(texto)
    if not m:
        return None
    return int(m.group("anio")), " ".join(m.group(0).split())


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


def construir(emisor: Emisor, exp: Expediente, portada=None, facts: Optional[dict] = None) -> Ficha:
    """`portada` es el 10-K de EDGAR (`sec.portada_10k`): de ahí salen el auditor (dei:AuditorName), el nombre y, si
    no hay adjunto con páginas, las propuestas de plantilla y fundación. `facts` da el free float y los cierres."""
    from . import sec as sec_mod
    f = Ficha(emisor=emisor)
    dei = portada.dei if portada is not None else {}
    f.nombre_presentacion = nombre_presentacion(portada.nombre_portada if portada is not None else "", dei.get("EntityRegistrantName") or emisor.nombre)
    estado = dei.get("EntityIncorporationStateCountryCode") or _ESTADOS.get(emisor.estado_constitucion, emisor.estado_constitucion)
    f.constitucion = f"{_ESTADOS.get(estado, estado)} (EE. UU.)" if estado else ""
    partes = [x.strip() for x in emisor.direccion.split(",")]
    if len(partes) >= 3 and partes[-2].upper() in _ESTADOS:
        f.sede = ", ".join(x.title() for x in partes[:-2]) + f", {partes[-2].upper()} {partes[-1]} (EE. UU.)"
    else:
        f.sede = emisor.direccion.title()
    if facts is not None:
        f.cierre_descrito = describir_cierre([p.fin for p in sec_mod.calendario(facts, 12)][-5:])
    if portada is not None and dei.get("AuditorName"):
        d = portada.deposito
        f.citas["auditor"] = Cita(campo="auditor", texto=dei["AuditorName"], nota=dei.get("AuditorLocation", ""),
                                  origen=Origen(documento=f"10-K {d.periodo:%Y}" if d.periodo else "10-K", formulario="10-K",
                                                presentado=d.presentado, concepto="dei:AuditorName", referencia=d.accession))
    if facts is not None:
        acc = sec_mod.acciones_portada(facts)
        if acc is not None:
            valor, fecha, origen = acc
            f.citas["acciones_portada"] = Cita(campo="acciones_portada", texto="dei:EntityCommonStockSharesOutstanding", valor=valor,
                                               fecha=fecha, origen=origen)
        fl = sec_mod.float_publico(facts)
        if fl is not None:
            valor, fecha, origen = fl
            f.citas["float_portada"] = Cita(campo="float_portada", texto="dei:EntityPublicFloat", valor=valor, fecha=fecha, origen=origen,
                                            nota="valor de mercado de las acciones en manos de no afiliados a esa fecha; no es la capitalización actual")
    k10 = max(exp.de_tipo(Tipo.K10), key=lambda a: a.periodo_fin or date.min, default=None)
    if k10 is None:
        if portada is not None:
            _propuestas_de_texto(f, portada)
        else:
            f.faltan["portada"] = "sin 10-K en el expediente"
        return f
    p1 = k10.paginas[0]
    # Acciones en circulación, con su fecha, de la portada más reciente: un 10-Q posterior al 10-K gana,
    # porque la cifra del 10-K queda vieja en cuanto hay recompras y la capitalización se calcula con ella.
    for a in ([] if "acciones_portada" in f.citas else sorted(exp.de_tipo(Tipo.K10) + exp.de_tipo(Tipo.Q10), key=lambda a: a.periodo_fin or date.min, reverse=True)):
        cita = _acciones_portada(a)
        if cita is not None:
            f.citas["acciones_portada"] = cita
            break
    else:
        if "acciones_portada" not in f.citas:
            f.faltan["acciones_portada"] = "ninguna portada de 10-K o 10-Q declara las acciones en circulación con el patrón esperado"
    # Valor de mercado en manos de no afiliados (public float): se rotula así, nunca «capitalización»
    m = None if "float_portada" in f.citas else re.search(r"As of\s+(\w+ \d{1,2}, \d{4}),?\s+the aggregate market value[^$]{0,400}?\$\s?([\d,]+)", p1, re.I | re.S)
    if "float_portada" in f.citas:
        pass
    elif m:
        f.citas["float_portada"] = _cita(k10, 1, "float_portada", " ".join(m.group(0).split()), _numero(m.group(2)), _fecha_larga(m.group(1)),
                                         nota="valor de mercado de las acciones en manos de no afiliados a esa fecha; no es la capitalización actual")
    else:
        f.faltan["float_portada"] = "la portada del 10-K no declara el valor en manos de no afiliados con el patrón esperado"
    # Empleados
    for pag, texto in enumerate(k10.paginas, 1):
        emp = proponer_empleados(" ".join(texto.split()))
        if emp:
            f.citas["empleados"] = _cita(k10, pag, "empleados", emp[2], emp[0], emp[1], nota="propuesta: la confirma el analista")
            break
    else:
        f.faltan["empleados"] = "el 10-K no declara una cifra de plantilla reconocible: la aporta el analista con su cita"
    # Auditor: dei:AuditorName del 10-K de EDGAR. Sin él, la firma «/s/» del informe de auditoría, solo si es una firma
    # (LLP, LLC…): la primera «/s/» del documento es a menudo la del consejero delegado.
    pag, m, texto = (None, None, None) if "auditor" in f.citas else _buscar(k10, r"^/s/\s*(.+?\b(?:LLP|LLC|L\.L\.P\.|Ltd\.?))\s*$", None, re.M)
    if "auditor" in f.citas:
        pass
    elif m and "Report of Independent Registered Public Accounting Firm" in " ".join(k10.paginas[max(0, pag - 2):pag + 1]):
        ciudad = re.search(r"^([A-Z][A-Za-z .]+, [A-Z][a-z]+)\s*$", texto[m.end():m.end() + 200], re.M)
        f.citas["auditor"] = _cita(k10, pag, "auditor", m.group(1), nota=(ciudad.group(1) if ciudad else ""))
    else:
        f.faltan["auditor"] = "no se halló la firma «/s/» del informe de auditoría en el 10-K"
    # Fundación: solo si el 10-K lo dice con un año. Suele estar en la nota 1 de las cuentas («was incorporated
    # on August 29, 1997»), no en el Item 1, así que se busca en todo el documento; el verbo va pegado a la
    # fecha para no confundirlo con «incorporated by reference», que el 10-K repite decenas de veces.
    for pag, texto in enumerate(k10.paginas, 1):
        fun = proponer_fundacion(" ".join(texto.split()))
        if fun:
            f.citas["fundacion"] = _cita(k10, pag, "fundacion", fun[1], float(fun[0]), nota="propuesta: la confirma el analista")
            break
    else:
        f.faltan["fundacion"] = "el 10-K no fecha la constitución ni la fundación: la aporta el analista con su cita"
    # Descripción del negocio: primer párrafo del Item 1
    # El índice del 10-K también dice «Item 1. Business» seguido de números de página:
    # se exige que lo que sigue sea prosa (sin «Item 1A» en los primeros 150 caracteres).
    pag, m, _ = _buscar(k10, r"Item 1\.\s+Business\s+(?!.{0,150}Item 1A)(.{200,900}?\.)\s", range(2, 9))
    if m:
        f.citas["descripcion"] = _cita(k10, pag, "descripcion", " ".join(m.group(1).split()))
    else:
        f.faltan["descripcion"] = "no se halló el arranque del Item 1 «Business»"
    return f


def _propuestas_de_texto(f: Ficha, portada) -> None:
    """Sin 10-K adjunto (sin páginas), las propuestas se hacen sobre el 10-K de EDGAR y se citan por su sección."""
    d = portada.deposito
    origen = Origen(documento=f"10-K {d.periodo:%Y} (EDGAR)" if d.periodo else "10-K (EDGAR)", formulario="10-K", presentado=d.presentado,
                    referencia=d.accession)
    emp = proponer_empleados(portada.texto)
    if emp:
        f.citas["empleados"] = Cita(campo="empleados", texto=emp[2], valor=emp[0], fecha=emp[1], origen=origen, nota="propuesta: la confirma el analista")
    else:
        f.faltan["empleados"] = "el 10-K no declara una cifra de plantilla reconocible: la aporta el analista con su cita"
    fun = proponer_fundacion(portada.texto)
    if fun:
        f.citas["fundacion"] = Cita(campo="fundacion", texto=fun[1], valor=float(fun[0]), origen=origen, nota="propuesta: la confirma el analista")
    else:
        f.faltan["fundacion"] = "el 10-K no fecha la constitución ni la fundación: la aporta el analista con su cita"
