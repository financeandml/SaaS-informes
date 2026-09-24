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
    titulo_en: str
    exigencia: str
    aporta: str                 # en qué apartados del informe entra
    aporta_en: str
    sin_el: str                 # qué queda N/A si no se adjunta
    sin_el_en: str
    donde: str                  # dónde lo encuentra el analista
    formatos: Tuple[str, ...] = DOC
    varios: bool = True         # admite más de uno (varios ejercicios, varios trimestres)
    bloquea_emision: bool = False   # sin él la emisión no puede ni empezar (no es lo mismo que «imprescindible»)


CATALOGO: Tuple[Documento, ...] = (
    Documento(
        clave="10K", tipo=Tipo.K10, titulo="Informe anual (10-K)", titulo_en="Annual report (10-K)", exigencia=IMPRESCINDIBLE,
        aporta="C · cuentas anuales y gráficos (8–11) · 19 segmentos · 28–31 riesgos (Item 1A) · 4–6 gobierno si no hay proxy",
        aporta_en="C · annual financials and charts (8–11) · 19 segments · 28–31 risk factors (Item 1A) · 4–6 governance if there is no proxy",
        sin_el="Sin 10-K no hay ejercicio base: el contraste con la SEC no puede correr y el informe no se emite.",
        sin_el_en="Without the 10-K there is no base fiscal year: the reconciliation cannot run and the report is not emitted.",
        donde="EDGAR, formulario 10-K (el PDF de la SEC o el del emisor)", bloquea_emision=True),
    Documento(
        clave="10Q", tipo=Tipo.Q10, titulo="Informes trimestrales (10-Q)", titulo_en="Quarterly reports (10-Q)", exigencia=IMPRESCINDIBLE,
        aporta="C · cuentas trimestrales (8–11) · 25 tamaño de mercado · 32 guía frente a real",
        aporta_en="C · quarterly financials (8–11) · 25 market size · 32 guidance vs. actual",
        sin_el="Sin 10-Q el informe solo tiene ejercicios cerrados: los trimestres del año en curso salen N/A.",
        sin_el_en="Without 10-Qs the report only has closed fiscal years: the current year's quarters are N/A.",
        donde="EDGAR, formulario 10-Q (adjunta los del ejercicio en curso)"),
    Documento(
        clave="PROXY", tipo=Tipo.DEF14A, titulo="Proxy de la junta (DEF 14A)", titulo_en="Proxy statement (DEF 14A)", exigencia=RECOMENDADO,
        aporta="4–6 gobierno: consejo, ejecutivos y retribución, accionistas significativos; retratos del consejo",
        aporta_en="4–6 governance: board, executives and pay, significant shareholders; board portraits",
        sin_el="El gobierno se toma del 10-K, que no trae retribución ni accionistas significativos: 4–6 salen incompletos y los retratos, N/A.",
        sin_el_en="Governance falls back to the 10-K, which carries no pay or significant-holder tables: 4–6 come out partial and portraits N/A.",
        donde="EDGAR, formulario DEF 14A (o la web de relación con inversores)", varios=False),
    Documento(
        clave="NOTA", tipo=Tipo.NOTA, titulo="Nota de resultados (8-K, anexo 99.1)", titulo_en="Earnings release (8-K, Exhibit 99.1)", exigencia=RECOMENDADO,
        aporta="7 objetivos y guía · 25 tamaño de mercado · C · 32 previsión frente a real",
        aporta_en="7 targets and guidance · 25 market size · C · 32 guidance vs. actual",
        sin_el="La guía del trimestre sale solo de lo que declare el 10-Q o la call: 7 y 32 quedan más pobres.",
        sin_el_en="Guidance is limited to whatever the 10-Q or the call states: 7 and 32 come out thinner.",
        donde="EDGAR, 8-K de resultados, anexo 99.1 (o la web del emisor)"),
    Documento(
        clave="TABLAS", tipo=Tipo.TABLAS, titulo="Cuentas del anexo 99.1 (8-K)", titulo_en="Condensed statements (8-K, Exhibit 99.1)", exigencia=RECOMENDADO,
        aporta="C · contraste de las cuentas del trimestre · regiones",
        aporta_en="C · reconciliation of the quarter's financials · regions",
        sin_el="El trimestre recién publicado no tiene cuentas hasta que se deposite el 10-Q.",
        sin_el_en="The just-reported quarter has no financials until the 10-Q is filed.",
        donde="EDGAR, 8-K de resultados, anexo 99.1 (las tablas en versales)"),
    Documento(
        clave="CARTA", tipo=Tipo.CARTA, titulo="Carta a accionistas", titulo_en="Shareholder letter", exigencia=OPCIONAL,
        aporta="7 objetivos y guía · 25 tamaño de mercado · 32 previsión frente a real (con las cartas que se bajan de EDGAR)",
        aporta_en="7 targets and guidance · 25 market size · 32 guidance vs. actual (together with the letters fetched from EDGAR)",
        sin_el="El historial de previsiones se queda con las cartas que haya en EDGAR.",
        sin_el_en="The guidance track record is limited to the letters available in EDGAR.",
        donde="EDGAR, 8-K de resultados, anexo 99.1; solo algunos emisores la publican"),
    Documento(
        clave="CALL", tipo=Tipo.CALL, titulo="Transcripción de la earnings call", titulo_en="Earnings call transcript", exigencia=RECOMENDADO,
        aporta="33 consenso frente a real · frases de guía de la dirección · 25 tamaño de mercado",
        aporta_en="33 consensus vs. actual · management guidance quotes · 25 market size",
        sin_el="Lo que la dirección dijo de viva voz no entra: 33 se queda sin las frases de guía y sin su fecha.",
        sin_el_en="What management said on the call does not enter: 33 loses the guidance quotes and their date.",
        donde="No está en EDGAR: es de un tercero (S&P Global, Motley Fool, la propia web del emisor)"),
    Documento(
        clave="SLIDES", tipo=Tipo.PRESENTACION, titulo="Presentación de resultados", titulo_en="Earnings slides", exigencia=OPCIONAL,
        aporta="25 tamaño de mercado (apoyo); las cifras se siguen tomando de las cuentas",
        aporta_en="25 market size (supporting); figures are still taken from the financial statements",
        sin_el="Nada esencial: es material de apoyo.",
        sin_el_en="Nothing essential: it is supporting material.",
        donde="Web de relación con inversores del emisor"),
    Documento(
        clave="FINWEB", tipo=Tipo.FINWEB, titulo="Cuentas trimestrales de la web del emisor", titulo_en="Quarterly financials (issuer website)", exigencia=OPCIONAL,
        aporta="C · contraste de las cuentas trimestrales · regiones",
        aporta_en="C · reconciliation of the quarterly financials · regions",
        sin_el="Nada que no den el 10-Q y el anexo 99.1.",
        sin_el_en="Nothing the 10-Q and Exhibit 99.1 do not already give.",
        donde="Web de relación con inversores («Financial statements», PDF sin portada)"),
    Documento(
        clave="XLSX", tipo=Tipo.XLSX, titulo="Hoja de cálculo de cuentas", titulo_en="Financials spreadsheet", exigencia=OPCIONAL,
        aporta="C · contraste de las cuentas · regiones",
        aporta_en="C · reconciliation of the financials · regions",
        sin_el="Nada: es una comodidad para contrastar sin abrir los PDF.",
        sin_el_en="Nothing: it is a convenience for reconciling without opening the PDFs.",
        donde="Web de relación con inversores («Financial data», .xlsx)", formatos=LIBRO),
)

POR_CLAVE: Dict[str, Documento] = {d.clave: d for d in CATALOGO}
POR_TIPO: Dict[Tipo, Documento] = {d.tipo: d for d in CATALOGO}
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
    for d in CATALOGO:
        if d.tipo.value == tipo:
            return d.clave
    return ""


def estado(filas: Sequence[dict], idioma: str = "es") -> List[dict]:
    """El catálogo con lo que el analista lleva adjuntado: una entrada por documento, con sus ficheros y su estado.

    `filas` son las de `saas.clasificar` (fichero, tipo, periodo…). Un documento está «adjuntado» cuando hay al menos
    un fichero reconocido como su tipo; si no, «falta», y la entrada dice qué se pierde el informe por ello.
    """
    por_clave: Dict[str, List[dict]] = {}
    for f in filas:
        por_clave.setdefault(_clave_de_fila(f), []).append(f)
    salida = []
    for d in CATALOGO:
        suyos = por_clave.get(d.clave, [])
        salida.append({"clave": d.clave, "tipo": d.tipo.value, "titulo": d.titulo, "titulo_en": d.titulo_en,
                       "exigencia": d.exigencia, "aporta": d.aporta, "aporta_en": d.aporta_en,
                       "sin_el": d.sin_el, "sin_el_en": d.sin_el_en, "donde": d.donde,
                       "formatos": list(d.formatos), "varios": d.varios,
                       "estado": "adjuntado" if suyos else "falta", "ficheros": suyos})
    return salida


def faltan(filas: Sequence[dict], solo_bloqueantes: bool = False) -> List[Documento]:
    """Los documentos imprescindibles que todavía no están, en orden de catálogo.

    Con `solo_bloqueantes`, solo aquellos sin los cuales la emisión no puede ni empezar: sin 10-K no hay ejercicio
    base con el que contrastar. Que falte un 10-Q empobrece el informe, pero no impide emitirlo, y esa diferencia
    tiene que notarse: un aviso no es una puerta cerrada.
    """
    tipos = {f.get("tipo") for f in filas}
    return [d for d in CATALOGO if d.exigencia == IMPRESCINDIBLE and d.tipo.value not in tipos
            and (d.bloquea_emision or not solo_bloqueantes)]


def sueltos(filas: Sequence[dict]) -> List[dict]:
    """Lo adjuntado que no cae en ninguna casilla del catálogo (desconocidos, Word solo para ordenar)."""
    return [f for f in filas if not _clave_de_fila(f)]


# la clave del catálogo y la que `expediente.Adjunto.clave` antepone al periodo son la misma cosa: si un día dejan de
# serlo, la lista de documentos no casaría con los adjuntos y no se vería en pantalla
assert all(CLAVE_DE[d.tipo] == d.clave for d in CATALOGO), "el catálogo y expediente.CLAVE_DE no concuerdan"
