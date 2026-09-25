"""Objetivos de la compañía e hitos (apartados 2 y 7): lo que la compañía dijo, con fecha.

Un objetivo de la compañía es un hecho de documento —lo que la dirección
anunció, el día que lo anunció—, nunca una estimación del sistema ni del
analista, y se rotula «objetivo de la compañía». Se lee de la carta a
accionistas (anexo 99.1 del 8-K de resultados) y de la transcripción de la
conferencia, siempre como cita literal con página.

Los hitos son los 8-K que el emisor depositó en los últimos doce meses, con la
fecha y los epígrafes que la SEC registra. Solo lo que la compañía comunicó:
ninguna fecha «esperada» por patrón. La próxima presentación de resultados es
N/A salvo que un documento la anuncie.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple

from .expediente import Adjunto, Expediente, Tipo
from .hechos import Capa, Certeza, Cita, Origen
from ..fuentes.sec import Deposito

__all__ = ["Guidance", "Hito", "Objetivo", "construir"]

EPIGRAFES_8K = {
    "1.01": "Acuerdo material", "1.02": "Terminación de acuerdo material", "2.01": "Adquisición o venta de activos",
    "2.02": "Resultados del periodo", "2.03": "Obligación financiera directa", "2.05": "Costes de reestructuración",
    "3.02": "Venta de valores no registrados", "5.02": "Cambios en consejeros o directivos",
    "5.03": "Modificación de estatutos", "5.07": "Resultado de la junta", "7.01": "Divulgación Reg FD",
    "8.01": "Otros hechos", "9.01": "Estados financieros y anexos",
}


@dataclass
class Objetivo:
    metrica: str
    periodo: str            # «3T26», «FY2026»
    texto: str              # literal
    valor: Optional[float]
    valor_hasta: Optional[float]
    unidad: str             # «USD», «%», «USD/acción»
    origen: Origen
    fecha: Optional[date]   # cuándo se dijo


@dataclass
class Hito:
    fecha: date
    formulario: str
    epigrafes: str
    descripcion: str
    url: str


@dataclass
class Guidance:
    objetivos: List[Objetivo] = field(default_factory=list)
    tabla_prevision: List[Tuple[str, List[str]]] = field(default_factory=list)   # filas de la tabla de la carta, literales
    cabecera_prevision: List[str] = field(default_factory=list)
    origen_tabla: Optional[Origen] = None
    citas_call: List[Cita] = field(default_factory=list)
    hitos: List[Hito] = field(default_factory=list)
    proxima_presentacion: Optional[Cita] = None
    faltan: Dict[str, str] = field(default_factory=dict)


def _origen(a: Adjunto, pagina: int) -> Origen:
    return Origen(documento=a.nombre, formulario=a.tipo.value, presentado=a.fecha, pagina=pagina)


def _tabla_prevision(carta: Adjunto, g: Guidance) -> None:
    """La tabla «Q2'25 … Q3'26 Forecast» de la primera página: filas literales y el objetivo por métrica."""
    for i, texto in enumerate(carta.paginas[:3], 1):
        m = re.search(r"((?:Q[1-4]'\d\d\s+){3,})\s*(Q[1-4]'\d\d)\s*\n?\s*Forecast", texto)
        if not m:
            continue
        cab = m.group(1).split() + [m.group(2) + " Forecast"]
        g.cabecera_prevision = cab
        g.origen_tabla = _origen(carta, i)
        resto = texto[m.end():]
        pendiente = ""      # un rótulo partido en dos líneas («Net cash provided by operating» / «activities $…»)
        for l in resto.splitlines():
            l = l.strip()
            mm = re.match(r"^([A-Za-z][A-Za-z /%()]+?)\s+((?:\$?-?[\d,.]+%?\s*){2,})$", l)
            if not mm:
                if l.startswith("1 ") or l.lower().startswith("excluding"):
                    break
                pendiente = l if re.fullmatch(r"[A-Za-z][A-Za-z /%()]+", l) else ""
                continue
            valores = mm.group(2).split()
            rotulo = mm.group(1).strip()
            if pendiente and rotulo[0].islower():
                rotulo = pendiente + " " + rotulo
            pendiente = ""
            g.tabla_prevision.append((rotulo, valores))
            if len(valores) == len(cab):
                ultimo = valores[-1]
                trimestre = cab[-1].split()[0]           # «Q3'26»
                periodo = f"{trimestre[1]}T{trimestre[-2:]}"
                unidad = "%" if ultimo.endswith("%") else ("USD/acción" if "EPS" in rotulo else "USD")
                v = float(ultimo.strip("$%").replace(",", ""))
                if unidad == "USD":
                    v *= 1_000_000   # «in millions»
                g.objetivos.append(Objetivo(metrica=rotulo, periodo=periodo, texto=l, valor=v, valor_hasta=None,
                                            unidad=unidad, origen=_origen(carta, i), fecha=carta.fecha))
        return
    g.faltan["tabla_prevision"] = "la carta no trae la tabla de resultados y previsión con el patrón «Qn'yy … Forecast»"


def _frases_prevision(carta: Adjunto, g: Guidance) -> None:
    """Frases del ejercicio completo: rango de ingresos y margen operativo."""
    for i, texto in enumerate(carta.paginas[:4], 1):
        plano = " ".join(texto.split())
        m = re.search(r"For (20\d\d), ([^.]*?revenue[^.]*?\$([\d.]+)-\$([\d.]+)B[^.]*?operating margin of ([\d.]+)%[^.]*\.)", plano, re.I)
        if m:
            anio = m.group(1)
            g.objetivos.append(Objetivo("Revenue", f"FY{anio}", m.group(2), float(m.group(3)) * 1e9, float(m.group(4)) * 1e9, "USD", _origen(carta, i), carta.fecha))
            g.objetivos.append(Objetivo("Operating Margin", f"FY{anio}", m.group(2), float(m.group(5)), None, "%", _origen(carta, i), carta.fecha))
            return
        m = re.search(r"(narrowing|maintaining|raising|updating) our revenue forecast to \$([\d.]+)-\$([\d.]+)B[^.]*\.", plano, re.I)
        if m:
            g.objetivos.append(Objetivo("Revenue", "FY" + str(carta.fecha.year if carta.fecha else ""), m.group(0), float(m.group(2)) * 1e9, float(m.group(3)) * 1e9, "USD", _origen(carta, i), carta.fecha))
    if not any(o.periodo.startswith("FY") for o in g.objetivos):
        g.faltan["prevision_anual"] = "la carta no formula un objetivo anual de ingresos y margen con el patrón esperado"


_ROL = re.compile(r"\b(Chief|Officer|President|Director|Vice|Head|Treasurer|Secretary|Investor Relations|Analyst|Research|Founder|Chairman|Controller|Counsel|Managing|Partner)\b")
_INTERROGATIVO = re.compile(r"^(What|How|Why|When|Where|Which|Who|Can|Could|Would|Should|Do|Does|Did|Is|Are|Will|Any|Maybe)\b", re.I)


def _participantes(call: Adjunto) -> Tuple[Dict[str, str], Dict[str, str]]:
    """La página «Call Participants»: {nombre: cargo} de los ejecutivos y de los analistas.
    Un nombre es una línea sin palabras de cargo; el cargo, las líneas que le siguen hasta el siguiente nombre."""
    ejecutivos: Dict[str, str] = {}
    analistas: Dict[str, str] = {}
    for texto in call.paginas[:5]:
        # el índice de la transcripción también dice «Call Participants»; la página buena trae la cabecera EXECUTIVES
        if "Call Participants" not in texto or not re.search(r"^\s*EXECUTIVES\s*$", texto, re.M):
            continue
        grupo: Optional[Dict[str, str]] = None
        nombre = None
        for l in texto.splitlines():
            l = l.strip()
            if not l or l.startswith("Copyright") or l.startswith("spglobal") or l.startswith("NETFLIX"):
                continue
            if l.upper() == "EXECUTIVES":
                grupo, nombre = ejecutivos, None
                continue
            if l.upper() == "ANALYSTS":
                grupo, nombre = analistas, None
                continue
            if grupo is None:
                continue
            es_nombre = re.fullmatch(r"[A-Z][\w.'’\-]+(?: [A-Z][\w.'’\-]+){1,4}", l) and not _ROL.search(l)
            if es_nombre:
                nombre = l
                grupo[nombre] = ""
            elif nombre:
                grupo[nombre] = (grupo[nombre] + " " + l).strip()
        break
    return ejecutivos, analistas


def _intervenciones(call: Adjunto, oradores: Dict[str, str]) -> List[Tuple[int, str, str]]:
    """(página, orador, texto) por intervención. Una línea igual a un nombre conocido abre intervención;
    las líneas de cargo que la siguen se descartan. Sin página de participantes, todo va sin orador."""
    salida: List[Tuple[int, str, str]] = []
    orador = ""
    for i, texto in enumerate(call.paginas, 1):
        if i <= 2 or "S&P Global Market Intelligence Estimates" in texto or "Call Participants" in texto:
            continue
        acumulado: List[str] = []
        en_cargo = False
        for l in texto.splitlines():
            l = l.strip()
            if not l or l.startswith("Copyright") or l.startswith("spglobal") or (l.startswith("NETFLIX") and "EARNINGS CALL" in l):
                continue
            if l in oradores:
                if acumulado:
                    salida.append((i, orador, " ".join(acumulado)))
                orador, acumulado, en_cargo = l, [], True
                continue
            if en_cargo and _ROL.search(l) and not re.search(r"[.?!]\s*$", l) and len(l) < 120:
                continue    # la línea del cargo bajo el nombre («Chief Financial Officer»)
            en_cargo = False
            acumulado.append(l)
        if acumulado:
            salida.append((i, orador, " ".join(acumulado)))
    return salida


def _call(call: Adjunto, g: Guidance) -> None:
    """Lo que la dirección dijo de sus previsiones. Solo frases de ejecutivos —la transcripción dice quién habla—
    y nunca preguntas: quien lee la pregunta de un analista no está anunciando nada."""
    # La frase puede empezar por el propio verbo («We're guiding…», «We expect…»): sin mínimo antes de él
    patron = re.compile(r"(?:^|(?<=[.?!]\s))(?=[A-Z])[^.?!]{0,300}?\b(we expect|we anticipate|our forecast|guidance|we project|we continue to expect|we[’']re forecasting|we[’']re guiding|our outlook)\b[^.?!]{0,220}[.?!]", re.I)
    ejecutivos, analistas = _participantes(call)
    if not ejecutivos:
        g.faltan["oradores_call"] = "la transcripción no trae la página «Call Participants»: no se puede saber quién habla y no se citan previsiones de la call"
        return
    for pagina, orador, texto in _intervenciones(call, {**ejecutivos, **analistas}):
        if orador not in ejecutivos:
            continue
        for m in patron.finditer(" ".join(texto.split())):
            frase = m.group(0).strip()
            if "S&P Global" in frase or "COPYRIGHT" in frase or frase.endswith("?") or _INTERROGATIVO.match(frase):
                continue
            if re.search(r"\b(question|questions)\b", frase, re.I):
                continue    # el moderador presentando la pregunta de un analista
            if len(g.citas_call) >= 12:
                return
            quien = f"{orador} ({ejecutivos[orador]})" if ejecutivos[orador] else orador
            g.citas_call.append(Cita(campo="guidance_call", texto=frase, origen=_origen(call, pagina), capa=Capa.DOCUMENTO, certeza=Certeza.MEDIA,
                                     nota=f"{quien}; transcripción de un tercero, no depositada en la SEC"))


def _hitos(depositos: List[Deposito], desde: date, g: Guidance) -> None:
    for d in depositos:
        if d.formulario == "8-K" and d.presentado >= desde:
            descripcion = "; ".join(EPIGRAFES_8K.get(e.strip(), e.strip()) for e in d.epigrafes.split(",") if e.strip())
            g.hitos.append(Hito(fecha=d.presentado, formulario=d.formulario, epigrafes=d.epigrafes, descripcion=descripcion or d.descripcion, url=d.url))
    g.hitos.sort(key=lambda h: h.fecha, reverse=True)


def _proxima_presentacion(exp: Expediente, g: Guidance) -> None:
    for a in exp.de_tipo(Tipo.CARTA) + exp.de_tipo(Tipo.NOTA) + exp.de_tipo(Tipo.CALL):
        for i, texto in enumerate(a.paginas, 1):
            m = re.search(r"[^.]{0,80}\b(next|third|fourth|Q[1-4])\b[^.]{0,40}\b(earnings|results)\b[^.]{0,60}\b(on|scheduled for)\s+(\w+ \d{1,2}(?:, \d{4})?)[^.]{0,40}\.", texto, re.I)
            if m:
                g.proxima_presentacion = Cita(campo="proxima_presentacion", texto=" ".join(m.group(0).split()), origen=_origen(a, i), capa=Capa.DOCUMENTO, certeza=Certeza.MEDIA)
                return
    g.faltan["proxima_presentacion"] = "ningún adjunto anuncia la fecha de la próxima presentación de resultados"


def construir(exp: Expediente, depositos: List[Deposito], hoy: date) -> Guidance:
    g = Guidance()
    carta = max(exp.de_tipo(Tipo.CARTA) + exp.de_tipo(Tipo.NOTA), key=lambda a: a.fecha or date.min, default=None)
    call = max(exp.de_tipo(Tipo.CALL), key=lambda a: a.fecha or date.min, default=None)
    if carta is not None:
        _tabla_prevision(carta, g)
        _frases_prevision(carta, g)
    else:
        g.faltan["carta"] = "sin carta a accionistas en el expediente: no hay objetivos de la compañía"
    if call is not None:
        _call(call, g)
    _hitos(depositos, hoy - timedelta(days=365), g)
    _proxima_presentacion(exp, g)
    return g
