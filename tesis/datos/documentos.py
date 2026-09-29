"""El listado de documentos que hace falta adjuntar, qué aporta cada uno y qué sale N/A si falta.

Es la lista que ve el analista en el paso 1 —una fila por documento, cada una con su propio botón de adjuntar— y
es también la única fuente de «dónde va esto en el informe»: el tablero, el aviso de lo que falta y el destino que
se imprime en la tabla de adjuntos salen todos de aquí (regla 9).

Adjuntar por casilla no cambia lo que el documento es: el tipo lo sigue diciendo el propio documento en su portada
(regla 3, `expediente.clasificar`). La casilla es una declaración del analista, y sirve para dos cosas: cuando el
documento no trae ninguna pista reconocible, se usa la declaración —diciéndolo— en vez de dejarlo en «desconocido»;
y cuando el documento dice ser otra cosa, manda el documento y se avisa del desacuerdo.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from .expediente import CLAVE_DE, Tipo

__all__ = ["Documento", "CATALOGO", "POR_CLAVE", "POR_TIPO", "destino", "tipo_declarado", "estado", "faltan"]

IMPRESCINDIBLE, RECOMENDADO, OPCIONAL = "imprescindible", "recomendado", "opcional"
# el PDF es el que sirve para todo: de un Word se lee el texto para ordenar el expediente, pero sin coordenadas no hay
# ni cifra con evidencia ni recorte, y el adjunto lo dice en su motivo
DOC = (".pdf", ".docx")
LIBRO = (".xlsx", ".xlsm")


@dataclass(frozen=True)
class Documento:
    clave: str                  # la misma que `expediente.Adjunto.clave` antepone al periodo: 10K, 10Q, PROXY…
    tipo: Tipo
    titulo: str
    exigencia: str
    aporta: str                 # en qué apartados del informe entra
    sin_el: str                 # qué queda N/A si no se adjunta
    donde: str                  # dónde lo encuentra el analista
    formatos: Tuple[str, ...] = DOC
    varios: bool = True         # admite más de uno (varios ejercicios, varios trimestres)
    bloquea_emision: bool = False   # sin él la emisión no puede ni empezar (no es lo mismo que «imprescindible»)


CATALOGO: Tuple[Documento, ...] = (
    Documento(
        clave="10K", tipo=Tipo.K10, titulo="Informe anual (10-K)", exigencia=IMPRESCINDIBLE,
        aporta="C · cuentas anuales y gráficos (8–11) · 4 segmentos · 24 riesgos (Item 1A) · 5–6 gobierno si no hay proxy",
        sin_el="Sin 10-K no hay ejercicio base: el contraste con la SEC no puede correr y el informe no se emite.",
        donde="EDGAR, formulario 10-K (el PDF de la SEC o el del emisor)", bloquea_emision=True),
    Documento(
        clave="10Q", tipo=Tipo.Q10, titulo="Informes trimestrales (10-Q)", exigencia=IMPRESCINDIBLE,
        aporta="C · cuentas trimestrales (8–11) · 21 tamaño de mercado · 26 guía frente a real",
        sin_el="Sin 10-Q el informe solo tiene ejercicios cerrados: los trimestres del año en curso salen N/A.",
        donde="EDGAR, formulario 10-Q (adjunta los del ejercicio en curso)"),
    Documento(
        clave="PROXY", tipo=Tipo.DEF14A, titulo="Proxy de la junta (DEF 14A)", exigencia=RECOMENDADO,
        aporta="5–6 gobierno: consejo, ejecutivos y retribución, accionistas significativos; retratos del consejo",
        sin_el="El gobierno se toma del 10-K, que no trae retribución ni accionistas significativos: 5–6 salen incompletos y los retratos, N/A.",
        donde="EDGAR, formulario DEF 14A (o la web de relación con inversores)", varios=False),
    Documento(
        clave="NOTA", tipo=Tipo.NOTA, titulo="Nota de resultados (8-K, anexo 99.1)", exigencia=RECOMENDADO,
        aporta="2 objetivos vigentes · 21 tamaño de mercado · C · 26 previsión frente a real",
        sin_el="La guía del trimestre sale solo de lo que declare el 10-Q o la call: 2 y 26 quedan más pobres.",
        donde="EDGAR, 8-K de resultados, anexo 99.1 (o la web del emisor)"),
    Documento(
        clave="TABLAS", tipo=Tipo.TABLAS, titulo="Cuentas del anexo 99.1 (8-K)", exigencia=RECOMENDADO,
        aporta="C · contraste de las cuentas del trimestre · 4 geografía",
        sin_el="El trimestre recién publicado no tiene cuentas hasta que se deposite el 10-Q.",
        donde="EDGAR, 8-K de resultados, anexo 99.1 (las tablas en versales)"),
    Documento(
        clave="CARTA", tipo=Tipo.CARTA, titulo="Carta a accionistas", exigencia=OPCIONAL,
        aporta="2 objetivos vigentes · 21 tamaño de mercado · 26 previsión frente a real (con las cartas que se bajan de EDGAR)",
        sin_el="El historial de previsiones se queda con las cartas que haya en EDGAR.",
        donde="EDGAR, 8-K de resultados, anexo 99.1; solo algunos emisores la publican"),
    Documento(
        clave="CALL", tipo=Tipo.CALL, titulo="Transcripción de la earnings call", exigencia=RECOMENDADO,
        aporta="26 consenso frente a real · frases de guía de la dirección · 21 tamaño de mercado",
        sin_el="Lo que la dirección dijo de viva voz no entra: 26 se queda sin las frases de guía y sin su fecha.",
        donde="No está en EDGAR: es de un tercero (S&P Global, Motley Fool, la propia web del emisor)"),
    Documento(
        clave="SLIDES", tipo=Tipo.PRESENTACION, titulo="Presentación de resultados", exigencia=OPCIONAL,
        aporta="21 tamaño de mercado (apoyo); las cifras se siguen tomando de las cuentas",
        sin_el="Nada esencial: es material de apoyo.",
        donde="Web de relación con inversores del emisor"),
    Documento(
        clave="FINWEB", tipo=Tipo.FINWEB, titulo="Cuentas trimestrales de la web del emisor", exigencia=OPCIONAL,
        aporta="C · contraste de las cuentas trimestrales · 4 geografía",
        sin_el="Nada que no den el 10-Q y el anexo 99.1.",
        donde="Web de relación con inversores («Financial statements», PDF sin portada)"),
    Documento(
        clave="XLSX", tipo=Tipo.XLSX, titulo="Hoja de cálculo de cuentas", exigencia=OPCIONAL,
        aporta="C · contraste de las cuentas · 4 geografía",
        sin_el="Nada: es una comodidad para contrastar sin abrir los PDF.",
        donde="Web de relación con inversores («Financial data», .xlsx)", formatos=LIBRO),
)

# Emisores de BME (España): lo que publica la bolsa y trae `fuentes.bme.traer` de una vez
CATALOGO_BME: Tuple[Documento, ...] = (
    Documento(
        clave="CCAA", tipo=Tipo.CCAA, titulo="Cuentas anuales auditadas", exigencia=IMPRESCINDIBLE,
        aporta="C · cuentas anuales, balance y flujos (8–11) · 1 ficha (auditor, constitución) · 2 cuadro de cifras",
        sin_el="Sin cuentas anuales no hay ejercicio base: el contraste no puede correr y el informe no se emite.",
        donde="BME, información financiera del emisor (se trae con «Traer de BME»)", bloquea_emision=True),
    Documento(
        clave="SEMESTRAL", tipo=Tipo.SEMESTRAL, titulo="Informe financiero semestral", exigencia=IMPRESCINDIBLE,
        aporta="C · primer semestre y segundo semestre derivado (8–11) · últimos doce meses del motor",
        sin_el="Sin el semestral el informe solo tiene ejercicios cerrados: los semestres salen N/A.",
        donde="BME, información financiera del emisor (se trae con «Traer de BME»)"),
    Documento(
        clave="SLIDES", tipo=Tipo.PRESENTACION, titulo="Presentación a inversores", exigencia=OPCIONAL,
        aporta="7 lo que dijo la dirección · 21 tamaño de mercado (apoyo); las cifras se siguen tomando de las cuentas",
        sin_el="Nada esencial: es material de apoyo.",
        donde="BME, otra información relevante del emisor (se trae con «Traer de BME»)"),
    Documento(
        clave="PARTICIPACIONES", tipo=Tipo.PARTICIPACIONES, titulo="Participaciones significativas", exigencia=RECOMENDADO,
        aporta="5 accionariado (participaciones ≥ 5 %, con su fecha de corte)",
        sin_el="El accionariado del apartado 5 lo aporta el analista con su cita.",
        donde="BME, otra información relevante del emisor (se trae con «Traer de BME»)"),
    Documento(
        clave="INCORPORACION", tipo=Tipo.INCORPORACION, titulo="Documento de incorporación al mercado", exigencia=OPCIONAL,
        aporta="4 y 6 apoyo para las citas del analista (negocio, consejo y dirección); no se toman cifras de él",
        sin_el="Nada automático: el analista cita la web del emisor o la memoria de las cuentas.",
        donde="BME, documentos de incorporación del emisor (se trae con «Traer de BME»)"),
)

POR_CLAVE: Dict[str, Documento] = {d.clave: d for d in CATALOGO}
POR_CLAVE.update({d.clave: d for d in CATALOGO_BME if d.clave not in POR_CLAVE})
POR_TIPO: Dict[Tipo, Documento] = {d.tipo: d for d in CATALOGO}
POR_TIPO.update({d.tipo: d for d in CATALOGO_BME if d.tipo not in POR_TIPO})
# «dónde va en el informe» de un tipo que no está en el catálogo (el desconocido) — no se inventa un destino
SIN_DESTINO = "no se usa en el informe (ver motivo)"


def destino(tipo) -> str:
    """En qué apartados entra un documento de este tipo. Única fuente: la tabla de adjuntos y la lista de documentos
    necesarios enseñan esta misma frase."""
    d = POR_TIPO.get(Tipo(tipo) if not isinstance(tipo, Tipo) else tipo)
    return d.aporta if d else SIN_DESTINO


def tipo_declarado(clave: str) -> Optional[Tipo]:
    d = POR_CLAVE.get((clave or "").upper())
    return d.tipo if d else None


def _clave_de_fila(fila: dict) -> str:
    """La casilla del catálogo a la que pertenece un adjunto ya clasificado: la de su tipo reconocido."""
    tipo = fila.get("tipo")
    for d in CATALOGO + CATALOGO_BME:
        if d.tipo.value == tipo:
            return d.clave
    return ""


def catalogo(mercado: str = "sec") -> Tuple[Documento, ...]:
    return CATALOGO_BME if mercado == "bme" else CATALOGO


def estado(filas: Sequence[dict], mercado: str = "sec") -> List[dict]:
    """El catálogo con lo que el analista lleva adjuntado: una entrada por documento, con sus ficheros y su estado.

    `filas` son las de `saas.clasificar` (fichero, tipo, periodo…). Un documento está «adjuntado» cuando hay al menos
    un fichero reconocido como su tipo; si no, «falta», y la entrada dice qué se pierde el informe por ello.
    """
    por_clave: Dict[str, List[dict]] = {}
    for f in filas:
        por_clave.setdefault(_clave_de_fila(f), []).append(f)
        # lo que trae dentro (la nota con los estados condensados) llena también esa casilla: es el mismo fichero
        for t in f.get("tambien") or ():
            d = next((d for d in catalogo(mercado) if d.tipo.value == t), None)
            if d is not None and f not in por_clave.setdefault(d.clave, []):
                por_clave[d.clave].append(f)
    salida = []
    for d in catalogo(mercado):
        suyos = por_clave.get(d.clave, [])
        salida.append({"clave": d.clave, "tipo": d.tipo.value, "titulo": d.titulo,
                       "exigencia": d.exigencia, "aporta": d.aporta,
                       "sin_el": d.sin_el, "donde": d.donde,
                       "formatos": list(d.formatos), "varios": d.varios,
                       "estado": "adjuntado" if suyos else "falta", "ficheros": suyos})
    return salida


def faltan(filas: Sequence[dict], solo_bloqueantes: bool = False, mercado: str = "sec") -> List[Documento]:
    """Los documentos imprescindibles que todavía no están, en orden de catálogo.

    Con `solo_bloqueantes`, solo aquellos sin los cuales la emisión no puede ni empezar: sin 10-K no hay ejercicio
    base con el que contrastar. Que falte un 10-Q empobrece el informe, pero no impide emitirlo, y esa diferencia
    tiene que notarse: un aviso no es una puerta cerrada.
    """
    tipos = {f.get("tipo") for f in filas}
    return [d for d in catalogo(mercado) if d.exigencia == IMPRESCINDIBLE and d.tipo.value not in tipos
            and (d.bloquea_emision or not solo_bloqueantes)]


def sueltos(filas: Sequence[dict]) -> List[dict]:
    """Lo adjuntado que no cae en ninguna casilla del catálogo (desconocidos, Word solo para ordenar)."""
    return [f for f in filas if not _clave_de_fila(f)]


# la clave del catálogo y la que `expediente.Adjunto.clave` antepone al periodo son la misma cosa: si un día dejan de
# serlo, la lista de documentos no casaría con los adjuntos y no se vería en pantalla
assert all(CLAVE_DE[d.tipo] == d.clave for d in CATALOGO), "el catálogo y expediente.CLAVE_DE no concuerdan"
