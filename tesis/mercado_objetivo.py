"""Tamaño de mercado (apartado 21): TAM · SAM · SOM con lo que la compañía declara en sus documentos oficiales.

Decisión del analista (17/09/2026): el apartado 21 se obtiene «de la SEC o de los documentos
oficiales de la empresa». Ninguna de las dos fuentes usa las etiquetas TAM/SAM/SOM; lo que hay
son frases de la dirección con cifras (hogares direccionables, ingresos direccionables, cuota,
penetración, audiencia, suscripciones) y hechos contrastados (ingresos del ejercicio). Este
módulo las lee literalmente, con documento y página, y las **clasifica** en TAM, SAM o SOM: la
clasificación es una inferencia del sistema y lleva su motivo; la cifra y la frase son de la
compañía. Lo que la compañía no declara sale N/A con motivo, no se estima.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional, Tuple

from .expediente import Adjunto, Expediente, Tipo
from .hechos import Capa, Certeza, Cita, Hecho, Origen, Periodo

__all__ = ["Declaracion", "MercadoObjetivo", "construir"]

_ESCALA = {"million": 1e6, "billion": 1e9, "trillion": 1e12}


@dataclass
class Declaracion:
    concepto: str                 # rótulo del informe
    valor: Optional[float]
    unidad: str                   # «hogares», «USD», «%», «personas», «suscripciones»
    clase: str                    # TAM · SAM · SOM · penetración
    motivo: str                   # por qué se clasifica así (inferencia del sistema)
    cita: Optional[Cita]          # la frase literal con documento y página
    capa: str = "Hd"              # Hd (dicho por la compañía) o H (hecho contrastado de la sección C)


@dataclass
class MercadoObjetivo:
    declaraciones: List[Declaracion] = field(default_factory=list)
    faltan: Dict[str, str] = field(default_factory=dict)
    no_aplican: Dict[str, str] = field(default_factory=dict)   # conceptos de otro sector: no son huecos de esta compañía

    def por_clase(self) -> Dict[str, List[Declaracion]]:
        salida: Dict[str, List[Declaracion]] = {"TAM": [], "SAM": [], "SOM": [], "penetración": []}
        for d in self.declaraciones:
            salida.setdefault(d.clase, []).append(d)
        return salida


# (concepto, patrón con grupos (número, escala opcional), unidad, clase, motivo, término). Las frases son de la
# dirección; los patrones solo reconocen la forma en que la dicen («roughly 800 million addressable households»).
# El término es la expresión literal de ese concepto: si no aparece en ningún documento, la compañía no habla de eso
# —una empresa de bases de datos no mide «hogares direccionables»— y no se lista como algo que le falte. Si aparece
# sin cifra reconocible, entonces sí falta, y el motivo lo distingue.
_PATRONES: Tuple[Tuple[str, str, str, str, str], ...] = (
    ("Hogares direccionables", r"[^.]*?\b(?:roughly|about|approximately|around|over|some)?\s*([\d.,]+)\s*(million|billion)\s+addressable households[^.]*\.", "hogares", "TAM",
     "la dirección llama «addressable households» al total de hogares a los que podría llegar: mercado total", "addressable households"),
    ("Ingresos direccionables", r"[^.]*?\$\s?([\d.,]+)\s*(billion|trillion)\s+of addressable revenue[^.]*\.", "USD", "SAM",
     "la dirección lo acota a «the countries and categories in which we operate today»: mercado al que sirve, no el total", "addressable revenue"),
    ("Penetración de hogares direccionables", r"[^.]*?\b(?:under|below|about|roughly|approximately)?\s*([\d.,]+)%\s+penetrated into addressable households[^.]*\.", "%", "penetración",
     "cuota de hogares que la dirección declara sobre sus propios hogares direccionables", "penetrated into addressable households"),
    ("Cuota del mercado de ingresos direccionable", r"[^.]*?\b(?:just|only|about|roughly|approximately)?\s*([\d.,]+)%\s+of addressable revenue[^.]*\.", "%", "penetración",
     "cuota que la dirección declara sobre sus propios ingresos direccionables: SOM / SAM", "of addressable revenue"),
    ("Cuota de visionado de televisión", r"[^.]*?\b(?:only|about|roughly|approximately)?\s*([\d.,]+)%\s+of TV view share[^.]*\.", "%", "penetración",
     "cuota de tiempo de visionado que la dirección declara; no es cuota de ingresos", "TV view share"),
    ("Audiencia", r"[^.]*?audience (?:approaching|of|over|of more than)\s+([\d.,]+)\s*(million|billion)\s+people[^.]*\.", "personas", "SOM",
     "personas a las que la compañía dice llegar hoy: mercado obtenido, en personas", "audience"),
    ("Suscripciones de pago", r"[^.]*?\b(?:over|more than|surpassed|exceeded)\s+([\d.,]+)\s*(million|billion)\s+paid memberships[^.]*\.", "suscripciones", "SOM",
     "suscripciones de pago que la compañía declara: mercado obtenido, en clientes", "paid memberships"),
)


def _se_habla_de(exp: Expediente, termino: str) -> bool:
    """Si el término aparece en algún adjunto, aunque sea sin cifra."""
    rx = re.compile(re.escape(termino), re.I)
    return any(rx.search(" ".join(p.split())) for a in exp.adjuntos for p in a.paginas)


def _numero(texto: str, escala: Optional[str]) -> float:
    return float(texto.replace(",", "")) * _ESCALA.get(escala or "", 1.0)


def _origen(a: Adjunto, pagina: int) -> Origen:
    return Origen(documento=a.nombre, formulario=a.tipo.value, presentado=a.fecha, pagina=pagina)


def _buscar(exp: Expediente, patron: str) -> Optional[Tuple[Adjunto, int, "re.Match"]]:
    """La primera frase que casa, priorizando el documento más reciente de cada tipo (carta, call, proxy, 10-K, 10-Q)."""
    rx = re.compile(patron, re.I)
    orden = [Tipo.CALL, Tipo.CARTA, Tipo.NOTA, Tipo.PRESENTACION, Tipo.DEF14A, Tipo.K10, Tipo.Q10]
    # por tipo y, dentro de cada tipo, el más reciente primero (a.orden es cronológico ascendente)
    adjuntos = sorted((a for a in exp.adjuntos if a.tipo in orden),
                      key=lambda a: (orden.index(a.tipo),) + tuple(-x.toordinal() if isinstance(x, date) else -x for x in a.orden))
    for a in adjuntos:
        for i, texto in enumerate(a.paginas, 1):
            m = rx.search(" ".join(texto.split()))
            if m:
                return a, i, m
    return None


def construir(exp: Expediente, hechos: Optional[Dict[Tuple[str, Periodo], Hecho]] = None) -> MercadoObjetivo:
    salida = MercadoObjetivo()
    for concepto, patron, unidad, clase, motivo, termino in _PATRONES:
        hallado = _buscar(exp, patron)
        if hallado is None:
            if _se_habla_de(exp, termino):
                salida.faltan[concepto] = f"la dirección habla de «{termino}» en los adjuntos, pero sin una cifra reconocible al lado"
            else:
                # la compañía no usa ese lenguaje: no es un hueco suyo, es un concepto de otro sector
                salida.no_aplican[concepto] = f"ningún documento adjunto menciona «{termino}»: la compañía no mide su mercado así"
            continue
        a, pagina, m = hallado
        escala = m.group(2) if m.lastindex and m.lastindex >= 2 else None
        cita = Cita(campo="mercado_" + clase.lower(), texto=m.group(0).strip(), origen=_origen(a, pagina), capa=Capa.DOCUMENTO, certeza=Certeza.MEDIA)
        salida.declaraciones.append(Declaracion(concepto, _numero(m.group(1), escala), unidad, clase, motivo, cita))
    # el mercado obtenido en dinero es un hecho contrastado de la sección C, no una declaración
    if hechos:
        anuales = sorted((p for (c, p) in hechos if c == "ingresos" and not p.es_instante and p.meses == 12), key=lambda p: p.fin)
        if anuales:
            h = hechos[("ingresos", anuales[-1])]
            if h.hay_dato:
                salida.declaraciones.append(Declaracion(f"Ingresos {anuales[-1].fin.year} (mercado obtenido)", h.valor, "USD", "SOM",
                                                        "lo que la compañía factura: mercado obtenido, contrastado con la SEC (sección C)", None, capa="H"))
    if not any(d.clase == "TAM" for d in salida.declaraciones):
        salida.faltan["TAM"] = "la compañía no declara un mercado total con cifra en los adjuntos"
    return salida
