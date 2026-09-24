"""El informe: las once secciones del índice como datos, listas para la maqueta.

Aquí no se calcula nada ni se lee ningún documento: se recogen los hechos que
producen `contraste`, `derivados`, `ficha`, `gobierno`, `guidance` y `regiones`
y se colocan en la estructura del índice (A.1–3, B.4–7, C.8–11). La regla 9 se
cumple por construcción: la caja de cifras del apartado 2 y las tablas de la
sección C se construyen con los mismos objetos `Hecho`, y `pruebas/` lo afirma.

Los cuadros se numeran al pedirlos, por orden de aparición: «Cuadro 7» no se
teclea en ningún sitio.

Los apartados de texto (2 y 3) los redacta el sistema a partir de los adjuntos
(`narrativa`). Aquí solo se verifican contra los mismos hechos que la sección C
y se preparan para imprimir: cada frase con su cita, cada frase retirada con su
motivo en el Anexo I. Sin narrativa, el informe imprime el hueco como tal
—«pendiente de redacción»— y las evidencias que la redacción debería usar.
Nunca un texto de relleno.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from . import derivados as derivados_mod
from .campos import CAMPOS, DERIVADOS, campo as campo_de, por_seccion
from .contraste import Tablero
from .expediente import Expediente, Tipo
from .ficha import Ficha
from .formato import Celda, celda, fecha as f_fecha, mln, numero, pct
from .gobierno import Gobierno
from .guidance import Guidance
from .hechos import Capa, Cita, Contraste, Estado, Hecho, Periodo
from .recortes import Recorte
from .regiones import Regiones
from .sec import Emisor

__all__ = ["Cuadro", "FilaCuadro", "Informe", "construir"]


class Cuadros:
    """Reparte el número de cada cuadro por orden de aparición."""
    def __init__(self) -> None:
        self.n = 0

    def siguiente(self) -> int:
        self.n += 1
        return self.n


@dataclass
class FilaCuadro:
    rotulo: str
    celdas: List[Celda]
    capa: str = "H"
    formula: str = ""
    destacada: bool = False
    sangria: bool = False
    # de dónde salió cada celda, para que la doble comprobación (`revision`) pueda releerla sin pasar por aquí
    origen: str = ""                       # «hecho:ingresos» cuando las celdas son hechos del diccionario
    periodos: Tuple[str, ...] = ()         # clave del periodo de cada celda, en el mismo orden
    unidad: str = ""                       # unidad con que se imprimió (vacía = la del hecho)


@dataclass
class Cuadro:
    numero: int
    titulo: str
    columnas: List[str]
    filas: List[FilaCuadro]
    fuente: str
    notas: List[str] = field(default_factory=list)
    recortes: List[Recorte] = field(default_factory=list)
    partible: bool = False             # un cuadro alto puede partirse entre páginas; los de cifras, no


@dataclass
class Dato:
    """Una línea de la ficha: rótulo, texto y de dónde sale."""
    rotulo: str
    texto: str
    fuente: str
    clase: str = "valor"


@dataclass
class FraseImpresa:
    """Una frase verificada, lista para la maqueta: el texto y su cita ya compuesta («Carta 2T26, pág. 2»)."""
    texto: str
    cita: str


@dataclass
class PilarImpreso:
    titulo: str
    frases: List[FraseImpresa]
    riesgo: Optional[FraseImpresa]


@dataclass
class NarrativaImpresa:
    """Lo que se imprime en los apartados 2 y 3, con la etiqueta de quién lo redactó y de qué."""
    resumen: List[List[FraseImpresa]]
    pilares: List[PilarImpreso]
    redactor: str
    documentos: List[str]
    certeza: str
    retiradas: int
    reparos: List[str]                 # para el Anexo I
    bloques: Dict[str, List[List[FraseImpresa]]] = field(default_factory=dict)   # apartados 21, 22, 23, 31
    evidencias: Dict[str, List[Recorte]] = field(default_factory=dict)          # por apartado: recortes de las páginas citadas


@dataclass
class Seccion:
    """Una entrada del índice: letra, título y sus apartados numerados en el orden en que se imprimen."""
    letra: str
    titulo: str
    apartados: List[Tuple[int, str]]
    estado: str = ""                   # «parcial» cuando la bolsa no da todo lo de la parte (sin IV cuadrada)
    subtitulo: str = ""                # el de `01_indice.yaml` (G y H)


@dataclass
class Informe:
    ticker: str
    nombre: str
    fecha_emision: date
    emisor: Emisor
    expediente: Expediente
    tablero: Tablero
    hechos: Dict[Tuple[str, Periodo], Hecho]
    ficha: List[Dato]
    precio: Hecho
    cifras_resumen: Cuadro
    objetivos: Cuadro
    hitos: List
    narrativa: Optional[NarrativaImpresa]
    descripcion: Optional[Cita]
    regiones: Cuadro
    grafico_regiones: str
    grafico_ingresos: str
    grafico_deuda: str
    accionistas: Cuadro
    filiales: Cuadro
    ejecutivos: Cuadro
    retribucion: Cuadro
    citas_call: List[Cita]
    proxima_presentacion: Optional[Cita]
    resultados: Cuadro
    balance: Cuadro
    flujo: Cuadro
    rentabilidad: Cuadro
    resumen_contraste: Dict[str, int]
    discrepancias: List[str]
    solo_sec: List[str]
    huecos: List[str]
    avisos: List[str]
    fuentes: List[str]
    faltan: List[str]
    periodos_anuales: List[Periodo]
    periodos_trimestres: List[Periodo]
    # secciones D–I y evidencia visual (17/09/2026)
    indice: List[Seccion] = field(default_factory=list)
    numeros: Dict[str, int] = field(default_factory=dict)          # clave del apartado («30») → número impreso
    titulos: Dict[str, str] = field(default_factory=dict)          # clave del apartado → título de `01_indice.yaml`
    evidencias: Dict[str, List[Recorte]] = field(default_factory=dict)   # por apartado (ficha, gobierno, guidance, regiones…)
    fotos_ejecutivos: List = field(default_factory=list)
    fotos_consejo: List = field(default_factory=list)
    dcf: Dict[str, object] = field(default_factory=dict)
    riesgos_cuadros: Dict[str, Cuadro] = field(default_factory=dict)
    riesgos_recortes: List[Recorte] = field(default_factory=list)
    riesgos_faltan: Dict[str, str] = field(default_factory=dict)
    historial_cuadros: Dict[str, Cuadro] = field(default_factory=dict)
    historial_frases: List[Cita] = field(default_factory=list)
    historial_faltan: Dict[str, str] = field(default_factory=dict)
    historial_recorte: Optional[Recorte] = None
    posicion: Optional[object] = None
    posicion_faltan: Dict[str, str] = field(default_factory=dict)
    segmento_unico: Optional[Cita] = None
    objetivo_portada: Optional[Tuple[str, float, str]] = None       # (rótulo, USD/acción, origen) del analista, para la portada
    f_cuadros: Dict[str, Cuadro] = field(default_factory=dict)      # sección F interina: lo que publica la bolsa
    f_faltan: Dict[str, str] = field(default_factory=dict)
    comparables_cuadro: Optional[Cuadro] = None                      # 22: la industria que la bolsa asigna, con cuentas de la SEC
    comparables_faltan: Dict[str, str] = field(default_factory=dict)
    mercado_cuadro: Optional[Cuadro] = None                          # 21: TAM · SAM · SOM según lo declarado por la compañía
    mercado_faltan: Dict[str, str] = field(default_factory=dict)
    # 18/09/2026: fuentes externas, números limpios y documentación complementaria
    comparables_sic_cuadro: Optional[Cuadro] = None                  # 22: los emisores del mismo SIC según la SEC
    rentabilidad_ttm: Optional[Cuadro] = None                        # 11: ROE y ROA TTM frente al agregador
    proxima_bolsa: Optional[object] = None                           # calendario.Proxima: la fecha de resultados que publica la bolsa
    potencial: Optional[float] = None                                # precio objetivo del analista / cotización oficial − 1
    recomendacion: str = ""                                          # del fichero de posición del analista
    documentacion: List[Tuple[int, str, List[Recorte]]] = field(default_factory=list)   # apartado final: (número, título, recortes) por apartado
    cuadres_apendice: List[str] = field(default_factory=list)        # las notas de cuadre que ya no se imprimen bajo cada cuadro
    # F2 · parte B rehecha (EDGAR, Nasdaq y entradas del analista)
    textos_b: Optional[object] = None                                # parte_b.Textos
    segmentos: Optional[Cuadro] = None
    geografia: Optional[Cuadro] = None
    grafico_mezcla: str = ""
    fechas_clave: Optional[Cuadro] = None
    catalizadores: Optional[Cuadro] = None
    salidas_13g: List[str] = field(default_factory=list)
    clases_acciones: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Cuadros de la sección C
# ---------------------------------------------------------------------------

_FISCAL = {"cierre": None, "desfase": 0}   # lo fija `construir` con el calendario de la compañía


def _etiqueta(p: Periodo, anuales=None, tab: Optional[Tablero] = None) -> str:
    """El trimestre por su número en el ejercicio fiscal de la compañía («4T FY25»), nunca por el natural. Con `anuales`
    y `tab` el cuadro se rotula solo; sin ellos, con el calendario que fijó `construir`."""
    from .hechos import etiqueta_fiscal
    if anuales:
        return etiqueta_fiscal(p, anuales[-1].fin, tab.desfase_fiscal if tab is not None else 0)
    return etiqueta_fiscal(p, _FISCAL["cierre"], _FISCAL["desfase"])


def _fila(hechos, clave: str, rotulo: str, periodos: Sequence[Periodo], instante: bool = False, unidad: Optional[str] = None,
          destacada: bool = False, sangria: bool = False, formula: str = "") -> FilaCuadro:
    celdas = []
    capa = "H"
    claves = []
    for p in periodos:
        k = (clave, Periodo.instante(p.fin) if instante else p)
        h = hechos.get(k)
        celdas.append(celda(h, unidad))
        claves.append(k[1].clave)
        if h is not None and h.capa is not Capa.SEC:
            capa = h.capa.value
    return FilaCuadro(rotulo=rotulo, celdas=celdas, capa=capa, formula=formula, destacada=destacada, sangria=sangria,
                      origen=f"hecho:{clave}", periodos=tuple(claves), unidad=unidad or "")


def _fuente_tablero(tab: Tablero, claves: Sequence[str], periodos: Sequence[Periodo], instante: bool = False) -> str:
    docs = set()
    for r in tab.resultados:
        if r.campo.clave in claves and r.evidencia is not None:
            docs.add(r.evidencia.documento)
    partes = ["SEC EDGAR (companyfacts, 10-K/10-Q)"] + sorted(docs)
    return "Fuente: " + "; ".join(partes) + "."


def _filas_de_la_compania(filas: List[FilaCuadro], tab: Tablero) -> List[FilaCuadro]:
    """Fuera las líneas que no son de las cuentas de esta compañía: ni un «Activos de contenido» en un fabricante de
    chips ni «Ventas y marketing» vacío en quien publica una sola línea de gastos generales. Una línea que la compañía
    sí tiene y falta se queda, con su N/A y su motivo: ese hueco hay que verlo."""
    from .campos import CAMPOS
    solo_documento = {c.clave for c in CAMPOS if c.solo_documento}
    salida = []
    for f in filas:
        clave = f.origen.split(":", 1)[1] if f.origen.startswith("hecho:") else ""
        vacia = all(c.clase == "na" for c in f.celdas)
        if clave in tab.no_aplican or (vacia and clave in solo_documento):
            continue
        salida.append(f)
    return salida


def _nota_splits(tab: Tablero, anuales) -> str:
    """La nota de reexpresión, de los splits que registra la SEC dentro de la ventana; sin split, nada que decir."""
    desde = anuales[0].inicio if anuales and anuales[0].inicio else None
    dentro = [(fecha, razon) for fecha, razon in tab.splits if desde is None or fecha >= desde]
    if not dentro:
        return ""
    return "; las presentadas antes de " + " y de ".join(f"el split {razon:g}:1 del {fecha:%d/%m/%Y}" for fecha, razon in dentro) \
        + " se reexpresan con su razón"


def _cuadro_resultados(n: Cuadros, hechos, tab: Tablero, anuales, trimestres) -> Cuadro:
    periodos = list(anuales) + list(trimestres)
    columnas = [_etiqueta(p, anuales, tab) for p in periodos]
    filas = [
        _fila(hechos, "ingresos", "Ingresos", periodos, destacada=True),
        _fila(hechos, "coste_ingresos", "Coste de los ingresos", periodos, sangria=True),
        _fila(hechos, "margen_bruto", "Margen bruto", periodos, unidad="%", sangria=True, formula="(Ingresos − Coste) / Ingresos"),
        _fila(hechos, "marketing", "Ventas y marketing", periodos, sangria=True),
        _fila(hechos, "tecnologia", "Investigación y desarrollo", periodos, sangria=True),
        _fila(hechos, "generales", "Generales y administrativos", periodos, sangria=True),
        _fila(hechos, "sga", "Ventas, generales y administrativos", periodos, sangria=True),
        _fila(hechos, "ebitda", "EBITDA", periodos, destacada=True, formula="EBIT + Amortización del inmovilizado"),
        _fila(hechos, "margen_ebitda", "Margen EBITDA", periodos, unidad="%", sangria=True),
        _fila(hechos, "amortizacion", "Amortización del inmovilizado", periodos, sangria=True),
        _fila(hechos, "ebit", "EBIT (resultado operativo)", periodos, destacada=True),
        _fila(hechos, "margen_ebit", "Margen operativo", periodos, unidad="%", sangria=True),
        _fila(hechos, "intereses", "Gastos financieros", periodos, sangria=True),
        _fila(hechos, "otros_financieros", "Otros ingresos y gastos", periodos, sangria=True),
        _fila(hechos, "bai", "Resultado antes de impuestos", periodos),
        _fila(hechos, "impuestos", "Impuesto sobre beneficios", periodos, sangria=True),
        _fila(hechos, "tipo_efectivo", "Tipo impositivo efectivo", periodos, unidad="%", sangria=True),
        _fila(hechos, "beneficio_neto", "Beneficio neto", periodos, destacada=True),
        _fila(hechos, "margen_neto", "Margen neto", periodos, unidad="%", sangria=True),
        _fila(hechos, "bpa_basico", "BPA básico (USD)", periodos, unidad="USD/acción"),
        _fila(hechos, "bpa_diluido", "BPA diluido (USD)", periodos, unidad="USD/acción"),
        _fila(hechos, "acciones_diluidas", "Acciones medias diluidas (mln)", periodos, unidad="acciones", sangria=True),
    ]
    filas = _filas_de_la_compania(filas, tab)
    notas = ["EBITDA = EBIT + amortización del inmovilizado material e intangible"
             + ("; la amortización de contenido es coste de los ingresos y no se devuelve." if "amortizacion_contenido" not in tab.no_aplican else "."),
             "Trimestres fiscales de la compañía; el 4T es el ejercicio menos los nueve meses acumulados (la SEC no presenta el cuarto trimestre). "
             "Las filas sin fuente directa (EBITDA, márgenes) se calculan de las anteriores; al pasar el ratón, la fórmula."]
    return Cuadro(n.siguiente(), "Estado de resultados (mln USD)", columnas, filas,
                  _fuente_tablero(tab, [c.clave for c in por_seccion(8)], periodos), notas)


def _cuadro_balance(n: Cuadros, hechos, tab: Tablero, anuales, trimestres) -> Cuadro:
    periodos = list(anuales) + [t for t in trimestres if t.fin != anuales[-1].fin]
    columnas = [_etiqueta(p, anuales, tab) for p in periodos]
    filas = [
        _fila(hechos, "caja", "Tesorería y equivalentes", periodos, instante=True),
        _fila(hechos, "inversiones_cp", "Inversiones a corto plazo", periodos, instante=True),
        _fila(hechos, "activo_corriente", "Activo corriente", periodos, instante=True, destacada=True),
        _fila(hechos, "contenido", "Activos de contenido, neto", periodos, instante=True),
        _fila(hechos, "inmovilizado", "Inmovilizado material, neto", periodos, instante=True),
        _fila(hechos, "total_activo", "Total activo", periodos, instante=True, destacada=True),
        _fila(hechos, "pasivo_corriente", "Pasivo corriente", periodos, instante=True),
        _fila(hechos, "deuda_cp", "Deuda a corto plazo", periodos, instante=True, sangria=True),
        _fila(hechos, "deuda_lp", "Deuda a largo plazo", periodos, instante=True),
        _fila(hechos, "arrendamientos", "Pasivos por arrendamiento (no corrientes)", periodos, instante=True),
        _fila(hechos, "pasivo_total", "Total pasivo", periodos, instante=True, destacada=True),
        _fila(hechos, "patrimonio", "Patrimonio neto", periodos, instante=True, destacada=True),
        _fila(hechos, "deuda_bruta", "Deuda bruta", periodos, instante=True, formula="Deuda a corto + Deuda a largo"),
        _fila(hechos, "deuda_neta", "Deuda neta", periodos, instante=True, destacada=True, formula="Deuda bruta − Tesorería − Inversiones a corto"),
        _fila(hechos, "fondo_maniobra", "Fondo de maniobra", periodos, instante=True, formula="Activo corriente − Pasivo corriente"),
        _fila(hechos, "acciones_circulacion", "Acciones en circulación (mln)", periodos, instante=True, unidad="acciones"),
    ]
    filas = _filas_de_la_compania(filas, tab)
    notas = ["Deuda neta sin pasivos por arrendamiento; se imprimen aparte.",
             "Acciones en circulación: las de la portada de cada formulario, a su fecha" + _nota_splits(tab, anuales) + "."]
    return Cuadro(n.siguiente(), "Balance de situación (mln USD)", columnas, filas,
                  _fuente_tablero(tab, [c.clave for c in por_seccion(9)], periodos, True), notas)


def _cuadro_flujo(n: Cuadros, hechos, tab: Tablero, anuales, trimestres) -> Cuadro:
    periodos = list(anuales) + list(trimestres)
    columnas = [_etiqueta(p, anuales, tab) for p in periodos]
    filas = [
        _fila(hechos, "cfo", "Flujo de caja operativo", periodos, destacada=True),
        _fila(hechos, "capex", "Capex", periodos, sangria=True),
        _fila(hechos, "fcf", "Flujo de caja libre (FCF)", periodos, destacada=True, formula="Flujo operativo − Capex"),
        _fila(hechos, "capex_ventas", "Capex / Ingresos", periodos, unidad="%", sangria=True),
        _fila(hechos, "fcf_compania", "Flujo de caja libre (definición de la compañía)", periodos, sangria=True),
        _fila(hechos, "cfi", "Flujo de caja de inversión", periodos),
        _fila(hechos, "adquisiciones", "Adquisiciones (caja)", periodos, sangria=True),
        _fila(hechos, "cff", "Flujo de caja de financiación", periodos),
        _fila(hechos, "dividendos", "Dividendos pagados", periodos, sangria=True),
        _fila(hechos, "recompras", "Recompra de acciones", periodos, sangria=True),
        _fila(hechos, "retribucion", "Retribución al accionista", periodos, destacada=True, formula="Dividendos + Recompras"),
        _fila(hechos, "retribucion_sobre_fcf", "Retribución / FCF", periodos, unidad="%", sangria=True),
        _fila(hechos, "emision_deuda", "Emisión de deuda", periodos, sangria=True),
        _fila(hechos, "amortizacion_deuda", "Amortización de deuda", periodos, sangria=True),
    ]
    filas = _filas_de_la_compania(filas, tab)
    notas = ["FCF del informe = flujo operativo − capex. El flujo de caja libre que publique la compañía es no-GAAP y se imprime aparte, tal como ella lo define."]
    if any(r.campo.clave == "dividendos" and r.hecho.hay_dato and r.hecho.valor == 0 and r.hecho.nota for r in tab.resultados):
        notas.append("Dividendos: cero declarado por la compañía en el 10-K (al pasar el ratón, su frase y página).")
    return Cuadro(n.siguiente(), "Flujo de caja (mln USD)", columnas, filas,
                  _fuente_tablero(tab, [c.clave for c in por_seccion(10)], periodos), notas)


def _cuadro_rentabilidad(n: Cuadros, hechos, tab: Tablero, anuales) -> Cuadro:
    periodos = list(anuales)
    columnas = [_etiqueta(p, anuales, tab) for p in periodos]
    filas = [
        _fila(hechos, "roe", "ROE", periodos, unidad="%", formula="Beneficio neto / Patrimonio neto medio"),
        _fila(hechos, "roa", "ROA", periodos, unidad="%", formula="Beneficio neto / Total activo medio"),
        _fila(hechos, "roic", "ROIC", periodos, unidad="%", formula="EBIT × (1 − tipo efectivo) / (Patrimonio + Deuda bruta − Tesorería), medios"),
        _fila(hechos, "margen_bruto", "Margen bruto", periodos, unidad="%"),
        _fila(hechos, "margen_ebitda", "Margen EBITDA", periodos, unidad="%"),
        _fila(hechos, "margen_ebit", "Margen operativo", periodos, unidad="%"),
        _fila(hechos, "margen_neto", "Margen neto", periodos, unidad="%"),
        _fila(hechos, "dfn_ebitda", "Deuda neta / EBITDA", periodos, unidad="x"),
        _fila(hechos, "cobertura_intereses", "Cobertura de intereses (EBIT / gastos financieros)", periodos, unidad="x"),
        _fila(hechos, "payout", "Pay-out", periodos, unidad="%"),
        _fila(hechos, "capex_ventas", "Capex / Ingresos", periodos, unidad="%"),
    ]
    notas = ["Rentabilidades sobre saldos medios (cierre y cierre anterior); requieren el balance del ejercicio anterior. Los formularios no publican ROE, ROA ni ROIC: "
             "se calculan con las cifras de los cuadros anteriores y, el ROE, con la definición que el 10-K da para su plan de incentivos."]
    return Cuadro(n.siguiente(), "Rentabilidad y eficiencia", columnas, filas,
                  "Fuente: cifras de la SEC contrastadas en los cuadros anteriores; al pasar el ratón, la fórmula de cada fila.", notas)


def _cuadro_cifras_resumen(n: Cuadros, hechos, anuales, trimestres) -> Cuadro:
    """La caja del apartado 2: los mismos objetos que la sección C (regla 9)."""
    periodos = list(anuales)
    columnas = [_etiqueta(p, anuales) for p in periodos]
    filas = [
        _fila(hechos, "ingresos", "Ingresos", periodos, destacada=True),
        _fila(hechos, "ebitda", "EBITDA", periodos),
        _fila(hechos, "margen_ebit", "Margen operativo", periodos, unidad="%"),
        _fila(hechos, "beneficio_neto", "Beneficio neto", periodos, destacada=True),
        _fila(hechos, "bpa_diluido", "BPA diluido (USD)", periodos, unidad="USD/acción"),
        _fila(hechos, "fcf", "FCF", periodos),
        _fila(hechos, "deuda_neta", "Deuda neta", periodos, instante=True),
        _fila(hechos, "dfn_ebitda", "Deuda neta / EBITDA", periodos, unidad="x"),
    ]
    return Cuadro(n.siguiente(), "Cifras que sostienen el resumen (mln USD)", columnas, filas,
                  "Fuente: SEC EDGAR y adjuntos, contrastados (sección C).")


# ---------------------------------------------------------------------------
# Secciones A y B
# ---------------------------------------------------------------------------

def _ficha(emisor: Emisor, f: Ficha, precio: Hecho, exp: Expediente, hechos, mercado=None) -> List[Dato]:
    datos: List[Dato] = [
        Dato("Nombre", f.nombre_presentacion or emisor.nombre, "portada del 10-K (propuesta; la confirma el analista)"),
        Dato("Nombre registral", emisor.nombre, "SEC EDGAR (submissions)"),
        Dato("Ticker · bolsa", f"{emisor.ticker} · {emisor.bolsa}", "SEC EDGAR"),
        Dato("CIK · SIC", f"{int(emisor.cik)} · {emisor.sic}", "SEC EDGAR"),
        Dato("Constitución", f.constitucion or emisor.estado_constitucion, "SEC EDGAR"),
        Dato("Sede", f.sede or emisor.direccion.title(), "SEC EDGAR"),
        Dato("Cierre fiscal", f.cierre_descrito or (f"{emisor.cierre_fiscal[2:]}/{emisor.cierre_fiscal[:2]}" if len(emisor.cierre_fiscal) == 4 else emisor.cierre_fiscal),
             "SEC EDGAR (cierres de los cinco últimos ejercicios)"),
    ]
    def cita(clave, rotulo, fmt):
        c = f.citas.get(clave)
        if c is None:
            datos.append(Dato(rotulo, "N/A", f.faltan.get(clave, ""), "na"))
        else:
            donde = f"pág. {c.origen.pagina}" if c.origen.pagina else (c.origen.concepto or c.origen.formulario)
            datos.append(Dato(rotulo, fmt(c), f"{c.origen.documento}, {donde}" + (f" · a {f_fecha(c.fecha)}" if c.fecha else "")
                              + (f" · {c.nota}" if c.nota.startswith("propuesta") else "")))
    cita("fundacion", "Fundación", lambda c: f"{int(c.valor)}")
    cita("empleados", "Empleados", lambda c: numero(c.valor))
    cita("auditor", "Auditor", lambda c: c.texto + (f" ({c.nota})" if c.nota else ""))
    cita("acciones_portada", "Acciones en circulación", lambda c: f"{mln(c.valor)} mln")
    cita("float_portada", "Valor en manos de no afiliados", lambda c: f"{mln(c.valor)} mln USD")
    if precio.hay_dato:
        datos.append(Dato("Precio", f"{numero(precio.valor, 2)} USD", precio.nota, "valor"))
        c = mercado.cotizacion if mercado is not None else None
        if c is not None and c.cierre_anterior is not None:
            # el cierre anterior solo se imprime si la ficha de la bolsa y su histórico dicen lo mismo (regla 9)
            contraste = mercado.contraste_cierre
            if contraste is None or contraste[0] is Contraste.CONFIRMADO:
                datos.append(Dato("Cierre anterior", f"{numero(c.cierre_anterior, 2)} USD",
                                  f"{c.fuente}" + (f" · {contraste[1]}" if contraste else " · histórico no contrastado"), "valor"))
            else:
                datos.append(Dato("Cierre anterior", "N/A", contraste[1], "na"))
        acc = f.citas.get("acciones_portada")
        if acc is not None:
            capitalizacion = precio.valor * acc.valor
            fuente = f"precio × {mln(acc.valor, 1)} mln acciones ({acc.origen.formulario}, portada, a {f_fecha(acc.fecha)})"
            if c is not None and c.cap_mercado_fuente is not None:
                dif = (capitalizacion - c.cap_mercado_fuente) / c.cap_mercado_fuente
                fuente += f" · {c.fuente} publica {mln(c.cap_mercado_fuente)} mln USD (diferencia {numero(dif * 100, 2)} %)"
            datos.append(Dato("Capitalización", f"{mln(capitalizacion)} mln USD", fuente, "valor"))
        else:
            datos.append(Dato("Capitalización", "N/A", "sin acciones en circulación de portada con que multiplicar el precio", "na"))
        if c is not None:
            if c.rango_52s is not None:
                datos.append(Dato("Rango 52 semanas", f"{numero(c.rango_52s[0], 2)} – {numero(c.rango_52s[1], 2)} USD", c.fuente, "valor"))
            else:
                datos.append(Dato("Rango 52 semanas", "N/A", f"{c.fuente} no lo publica en la ficha", "na"))
            if c.volumen is not None:
                sesion = "sesión en curso" if not c.es_cierre else f"sesión del {f_fecha(c.fecha)}"
                medio = f" · volumen medio {numero(c.volumen_medio)}" if c.volumen_medio is not None else ""
                datos.append(Dato("Volumen", f"{numero(c.volumen)} acciones ({sesion})", c.fuente + medio, "valor"))
            else:
                datos.append(Dato("Volumen", "N/A", f"{c.fuente} no lo publica en la ficha", "na"))
    else:
        datos.append(Dato("Precio", "N/A", precio.motivo, "na"))
        datos.append(Dato("Capitalización · rango 52 s · volumen", "N/A", "requieren cotización", "na"))
    ultimo_k = emisor.ultimo("10-K"); ultimo_q = emisor.ultimo("10-Q")
    datos.append(Dato("Última presentación", ", ".join(f"{d.formulario} {f_fecha(d.presentado)}" for d in (ultimo_k, ultimo_q) if d), "SEC EDGAR"))
    return datos


def _cuadro_objetivos(n: Cuadros, g: Guidance) -> Cuadro:
    filas = []
    for o in g.objetivos:
        if o.unidad == "%":
            texto = f"{numero(o.valor, 1)} %"
        elif o.unidad == "USD/acción":
            texto = numero(o.valor, 2)
        else:
            texto = mln(o.valor) + (f" – {mln(o.valor_hasta)}" if o.valor_hasta else "")
        filas.append(FilaCuadro(o.metrica, [Celda(o.periodo, "", "Hd", "valor", ""), Celda(texto, "◑", "Hd", "valor", o.texto),
                                             Celda(f_fecha(o.fecha), "", "Hd", "valor", ""), Celda(f"pág. {o.origen.pagina}", "", "", "valor", "")], capa="Hd"))
    fuente = f"Fuente: {g.origen_tabla.documento}" if g.origen_tabla else "Fuente: —"
    return Cuadro(n.siguiente(), "Objetivos de la compañía vigentes", ["Métrica", "Periodo", "Objetivo (mln USD, %, USD/acc.)", "Comunicado el", "Página"], filas,
                  fuente + ". Objetivo de la compañía, no estimación del analista.", [])


def _cuadro_regiones(n: Cuadros, r: Regiones, anuales, trimestres) -> Tuple[Cuadro, str]:
    from . import graficos
    from .regiones import REGIONES
    periodos = [p for p in r.periodos if p.meses in (12, 3)]
    periodos = [p for p in periodos if p in list(anuales) + list(trimestres)] or periodos[-6:]
    columnas = [_etiqueta(p) for p in periodos]
    filas = []
    for cod, _, nombre in REGIONES:
        celdas = [celda(r.hechos.get((cod, p))) for p in periodos]
        capa = "H" if all((r.hechos.get((cod, p)) is None or r.hechos[(cod, p)].capa is Capa.SEC) for p in periodos) else "Hd"
        filas.append(FilaCuadro(f"{nombre} ({cod})", celdas, capa=capa))
    fuente = "Fuente: " + "; ".join(f"{o.documento} pág. {o.pagina}" for o in r.origenes.values()) + ". companyfacts no sirve ejes regionales."
    ultimo = periodos[-1] if periodos else None
    svg = ""
    if ultimo is not None:
        svg, _ = graficos.tarta([(cod, r.hechos.get((cod, ultimo))) for cod, _, _ in REGIONES if r.hechos.get((cod, ultimo)) is not None])
    return Cuadro(n.siguiente(), f"Ingresos por región (mln USD){' · reparto ' + _etiqueta(ultimo) if ultimo else ''}", columnas, filas, fuente, r.cuadres), svg


def _cuadros_gobierno(n: Cuadros, g: Gobierno) -> Tuple[Cuadro, Cuadro, Cuadro, Cuadro]:
    # Las acciones van enteras: en millones sin decimales, 151.211 acciones se imprimían como «0», que es otro estado.
    def _pct_accionista(a) -> Celda:
        if a.porcentaje is not None:
            return Celda(f"{numero(a.porcentaje, 2)} %", "", "H", "valor", "")
        if a.nota.startswith("menos del 1"):
            return Celda("< 1 %", "", "H", "valor", "«*» en la proxy: menos del 1 %")
        return Celda("N/A", "", "H", "na", a.nota or "sin porcentaje en la proxy")
    def _fuente(o, seccion: str) -> str:
        if o is None:
            return ""
        if o.pagina:
            return f"Fuente: {o.documento}, pág. {o.pagina} ({seccion})."
        return f"Fuente: SEC EDGAR, {o.documento}{' del ' + f_fecha(o.presentado) if o.presentado else ''} ({seccion})."
    edgar = any(a.fuente for a in g.accionistas)
    filas = [FilaCuadro(a.nombre, [Celda(numero(a.acciones) if a.acciones is not None else "N/A", "", "H", "valor" if a.acciones is not None else "na", ""),
                                   _pct_accionista(a),
                                   Celda((a.fuente or a.direccion or "c/o la compañía").replace("SCHEDULE ", "").replace("SC ", ""), "", "", "valor", "")],
                        destacada=a.nombre.startswith("Consejeros y directivos")) for a in g.accionistas]
    o = g.origenes.get("accionistas")
    accionistas = Cuadro(n.siguiente(), "Accionistas con 5 % o más, y consejeros y directivos en conjunto" if edgar else
                         f"Principales accionistas, consejeros y directivos{' a ' + f_fecha(g.fecha_accionistas) if g.fecha_accionistas else ''}",
                         ["Acciones", "% del capital", "Fuente y fecha" if edgar else "Dirección"], filas,
                         (_fuente(o, "tabla de propiedad") + (" Participaciones posteriores: Schedule 13G/13D en XML de EDGAR; la última declaración de cada declarante manda." if edgar else ""))
                         if o else "Fuente: " + g.faltan.get("accionistas", "—"))
    con_pct = any(x.porcentaje is not None for x in g.filiales)
    filas = [FilaCuadro(x.nombre, [Celda(x.jurisdiccion, "", "H", "valor", "")] +
                        ([Celda(f"{numero(x.porcentaje)} %" if x.porcentaje is not None else "N/A", "", "H", "valor" if x.porcentaje is not None else "na", "")] if con_pct else []))
             for x in g.filiales]
    o = g.origenes.get("filiales")
    filiales = Cuadro(n.siguiente(), "Filiales significativas (Exhibit 21)", ["Jurisdicción"] + (["% participación"] if con_pct else []), filas,
                      (_fuente(o, "lista de filiales") if o else "Fuente: " + g.faltan.get("filiales", "—")), [g.nota_filiales] if g.nota_filiales else [])
    filas = [FilaCuadro(e.nombre, [Celda(str(e.edad) if e.edad else "N/A", "", "H", "valor" if e.edad else "na", ""), Celda(e.cargo, "", "H", "valor", "")]) for e in g.ejecutivos]
    o = g.origenes.get("ejecutivos")
    ejecutivos = Cuadro(n.siguiente(), f"Ejecutivos{' (edad a ' + f_fecha(g.fecha_ejecutivos) + ')' if g.fecha_ejecutivos else ''}", ["Edad", "Cargo"], filas,
                        _fuente(o, "ejecutivos") if o else "Fuente: " + g.faltan.get("ejecutivos", "—"))
    filas = []
    for r in g.retribucion:
        cifras = list(r.cifras) + ([r.total] if r.total is not None and len(g.cabecera_retribucion) > len(r.cifras) + 1 else [])
        celdas = [Celda(str(r.anio), "", "H", "valor", "")] + [Celda(numero(c) if c else "—", "", "H", "valor" if c else "cero", "") for c in cifras]
        filas.append(FilaCuadro(r.nombre + (f" · {r.cargo}" if getattr(r, "cargo", "") else ""), celdas))
    o = g.origenes.get("retribucion")
    ancho = max((len(f.celdas) for f in filas), default=8)
    cab = g.cabecera_retribucion[:ancho] if g.cabecera_retribucion else ["Año", "Salario", "Bonus", "Acciones", "Opciones", "Incentivo no accionarial", "Otros", "Total"][:ancho]
    retribucion = Cuadro(n.siguiente(), "Retribución de los ejecutivos nombrados (USD, último ejercicio de la Summary Compensation Table)", cab, filas,
                         (_fuente(o, "Summary Compensation Table") + " Columnas tal como las publica la proxy; «—» es cero en la tabla.") if o else "Fuente: " + g.faltan.get("retribucion", "—"))
    return accionistas, filiales, ejecutivos, retribucion


def _graficos_evolucion(hechos, anuales) -> Tuple[str, str, List[str]]:
    from . import graficos
    avisos: List[str] = []
    ingresos = [hechos.get(("ingresos", p)) for p in anuales]
    margen = [hechos.get(("margen_ebit", p)) for p in anuales]
    etiquetas = [_etiqueta(p) for p in anuales]
    from .hechos import na as _na
    ingresos = [h if h is not None else _na("ingresos", p, "sin hecho") for h, p in zip(ingresos, anuales)]
    svg1, av1 = graficos.barras_con_linea(ingresos, margen, "Ingresos", "Margen operativo", etiquetas)
    deuda = [hechos.get(("deuda_neta", Periodo.instante(p.fin))) or _na("deuda_neta", Periodo.instante(p.fin), "sin hecho") for p in anuales]
    ratio = [hechos.get(("dfn_ebitda", p)) for p in anuales]
    svg2, av2 = graficos.barras_con_linea(deuda, ratio, "Deuda neta", "Deuda neta / EBITDA", etiquetas, unidad_linea="x")
    return svg1, svg2, av1 + av2


# ---------------------------------------------------------------------------
# Narrativa (apartados 2 y 3): verificar contra los mismos hechos e imprimir solo lo que pasa
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Ensamblado
# ---------------------------------------------------------------------------

# El índice sale de `docs/spec/01_indice.yaml` (tesis/indice.py): letras, títulos, números y anclas.
_GLIFOS_CUADRE = ("✓", "≠", "◐", "◑", "—", "∑")


def _documentacion(indice: List[Seccion], numeros: Dict[str, int], por_clave: Dict[str, List[Recorte]]) -> List[Tuple[int, str, List[Recorte]]]:
    """El apartado final: los recortes de cada apartado en el orden del índice, una sola vez cada imagen (misma huella =
    misma imagen, aunque la citen varias frases o varios cuadros)."""
    salida: List[Tuple[int, str, List[Recorte]]] = []
    for s in indice:
        for numero_impreso, nombre in s.apartados:
            clave = next(k for k, v in numeros.items() if v == numero_impreso)
            vistos, lista = set(), []
            for r in por_clave.get(clave, []):
                if r.huella not in vistos:
                    vistos.add(r.huella)
                    lista.append(r)
            if lista:
                salida.append((numero_impreso, nombre, lista))
    return salida


def _mover_cuadres(cuadros) -> List[str]:
    """Las notas de cuadre (las que empiezan por un glifo de contraste) salen de los cuadros y van al apéndice:
    los números se imprimen limpios y el detalle del cuadre queda donde el analista lo busca."""
    salida: List[str] = []
    for c in cuadros:
        if c is None:
            continue
        quedan = []
        for nota in c.notas:
            if nota[:1] in _GLIFOS_CUADRE:
                salida.append(f"Cuadro {c.numero} ({c.titulo}): {nota}")
            else:
                quedan.append(nota)
        c.notas = quedan
    return salida


def _indice() -> Tuple[List[Seccion], Dict[str, int]]:
    from . import indice as indice_mod
    secciones, numeros = [], {}
    for parte in indice_mod.partes():
        for a in parte.apartados:
            numeros[a.clave] = a.numero
        secciones.append(Seccion(parte.letra, parte.titulo, [(a.numero, a.titulo) for a in parte.apartados], "", parte.subtitulo))
    return secciones, numeros


def _titulo(indice: List[Seccion], numero: int) -> str:
    return next(nombre for s in indice for n, nombre in s.apartados if n == numero)


def _segmento_unico(exp: Expediente) -> Optional[Cita]:
    """El 10-K dice cuántos segmentos operativos hay; con uno solo, la SOTP no aplica y se cita por qué."""
    import re
    from .hechos import Origen
    for a in sorted(exp.de_tipo(Tipo.K10), key=lambda a: a.orden, reverse=True):
        for numero, texto in enumerate(a.paginas, 1):
            m = re.search(r"We operate as (one|a single) operating segment\b[^.]*\.", texto)
            if m:
                return Cita(campo="segmentos", texto=m.group(0), origen=Origen(documento=a.nombre, formulario="10-K", presentado=a.fecha, pagina=numero), capa=Capa.DOCUMENTO)
    return None


def construir(ticker: str, hoy: date, emisor: Emisor, exp: Expediente, tab: Tablero, periodos: Dict[str, List[Periodo]],
              ficha: Ficha, gobierno: Gobierno, guidance: Guidance, regiones: Regiones, precio: Hecho,
              recortes: Dict[Tuple[str, int], Recorte], modelo_dcf=None, posicion=None, riesgos=None, historial=None,
              salida_recortes: Optional[Path] = None, mercado=None, posicionamiento=None, comparables=None, mercado_objetivo=None,
              agregador=None, multiplos=None, proxima=None, parte_b=None) -> Informe:
    from . import secciones as secciones_mod
    from . import parte_b as parte_b_mod
    anuales, trimestres, instantes = periodos["anuales"], periodos["trimestres"], periodos["instantes"]
    _FISCAL.update(cierre=anuales[-1].fin if anuales else None, desfase=tab.desfase_fiscal)
    hechos = derivados_mod.calcular(tab.hechos(), anuales + trimestres, instantes)
    narrativa_impresa = None    # sin IA: los textos los escribe el analista (docs/fases)
    n = Cuadros()
    cifras = _cuadro_cifras_resumen(n, hechos, anuales, trimestres)
    segmentos_c = geografia_c = fechas_c = catalizadores_c = None
    svg_mezcla = ""
    if parte_b is not None:
        from . import guia as guia_mod
        vigentes = guia_mod.vigentes(parte_b.notas, parte_b.confirmadas)
        objetivos = parte_b_mod.cuadro_objetivos(n, vigentes, bool(parte_b.notas and parte_b.notas[-1].candidatos))
    else:
        objetivos = _cuadro_objetivos(n, guidance)
    if parte_b is not None and parte_b.segmentos is not None and parte_b.segmentos.periodos:
        segmentos_c, geografia_c, svg_mezcla, sin_traducir = parte_b_mod.cuadro_segmentos(n, parte_b.segmentos, lambda p: _etiqueta(p, anuales, tab))
        regiones_c, svg_regiones = geografia_c, ""
        parte_b.faltas += [f"rótulo sin traducir en el cuadro de segmentos: {m}" for m in sin_traducir]
    else:
        regiones_c, svg_regiones = _cuadro_regiones(n, regiones, anuales, trimestres)
    svg_ingresos, svg_deuda, avisos_graficos = _graficos_evolucion(hechos, anuales)
    accionistas, filiales, ejecutivos, retribucion = _cuadros_gobierno(n, gobierno)
    if parte_b is not None:
        publicado = parte_b.notas[-1].publicado if parte_b.notas else None
        fechas_c = parte_b_mod.cuadro_fechas(n, hoy, proxima, parte_b.dividendos, getattr(gobierno, "junta", None),
                                             gobierno.origenes.get("junta"), parte_b_mod.siguiente_trimestre(publicado), parte_b.dividendos_url)
        catalizadores_c = parte_b_mod.cuadro_catalizadores(n, parte_b.entradas)
    resultados = _cuadro_resultados(n, hechos, tab, anuales, trimestres)
    balance = _cuadro_balance(n, hechos, tab, anuales, trimestres)
    flujo = _cuadro_flujo(n, hechos, tab, anuales, trimestres)
    rentabilidad = _cuadro_rentabilidad(n, hechos, tab, anuales)
    rentabilidad_ttm = secciones_mod.cuadro_rentabilidad_ttm(n, multiplos) if multiplos is not None else None
    # recortes bajo cada cuadro de la sección C, por el estado que contienen
    for cuadro, patron in ((resultados, "OPERATIONS"), (balance, "BALANCE"), (flujo, "CASH FLOWS")):
        for (clave, pagina), rec in sorted(recortes.items()):
            titulo = next((p.titulo for p in tab.paginas.get(clave, []) if p.numero == pagina), "")
            if patron in titulo.upper():
                cuadro.recortes.append(rec)
    discrepancias = [f"{r.campo.rotulo} {r.periodo.clave}: {r.nota}" for r in tab.resultados if r.hecho.contraste is Contraste.DISCREPANTE]
    solo_sec = [f"{r.campo.rotulo} {r.periodo.clave}" for r in tab.resultados if r.hecho.contraste is Contraste.SOLO_SEC]
    huecos = [f"{r.campo.rotulo} {r.periodo.clave}: {r.hecho.motivo}" for r in tab.resultados if r.hecho.contraste is Contraste.HUECO]
    faltan = [f"Ficha · {k}: {v}" for k, v in ficha.faltan.items()] + [f"Gobierno · {k}: {v}" for k, v in gobierno.faltan.items()] \
        + [f"Objetivos · {k}: {v}" for k, v in guidance.faltan.items()] + [f"Regiones · {k}: {v}" for k, v in regiones.faltan.items()]
    fuentes = [f"{a.nombre} — {a.tipo.value}" + (f", periodo {f_fecha(a.periodo_fin)}" if a.periodo_fin else "") + (f", fecha {f_fecha(a.fecha)}" if a.fecha else "")
               + (" · verificado en EDGAR" if a.verificado_en_edgar else "") + f" · sha256 {a.huella[:12]}" for a in exp.adjuntos]
    fuentes.append(f"SEC EDGAR companyfacts y submissions, CIK {int(emisor.cik)}, obtenidos el {f_fecha(emisor.obtenido_en)}")
    if mercado is not None and mercado.cotizacion is not None:
        c = mercado.cotizacion
        fuentes.append(f"{c.fuente} — ficha del valor e histórico de cierres, consultados el {f_fecha(hoy)}" + (f" ({c.hora})" if c.hora else "") + f" · {c.url}")
        faltan += [f"Mercado · {k}: {v}" for k, v in mercado.faltan.items()]
    elif mercado is not None and not mercado.precio.hay_dato:
        faltan.append(f"Mercado · precio: {mercado.precio.motivo}")
    # --- secciones D–I y evidencia visual de las tablas leídas de documentos ---
    indice, numeros = _indice()
    evidencias: Dict[str, List[Recorte]] = {}
    # Una página citada varias veces en un apartado da un solo recorte con todas sus anclas. El fichero del
    # recorte es uno por (adjunto, página, apartado): dos recortes distintos de la misma página se pisarían y
    # las huellas impresas dejarían de ser las de la imagen que se ve (regla 9).
    pedidos: Dict[Tuple[str, str, int], List[str]] = {}

    def evidencia(clave: str, documento: str, pagina: Optional[int], anclas: Sequence[str]) -> None:
        if pagina is None:
            return
        lista = pedidos.setdefault((clave, documento, pagina), [])
        lista.extend(a for a in anclas if a not in lista)

    def recortar_pedidos() -> None:
        for (clave, documento, pagina), anclas in pedidos.items():
            rec = secciones_mod.recorte_texto(exp, documento, pagina, anclas, salida_recortes, clave)
            if rec is not None:
                evidencias.setdefault(clave, []).append(rec)

    # la ficha: también la fundación (nota 1 de las cuentas) y las acciones de la portada más reciente
    for k in ("fundacion", "empleados", "auditor", "acciones_portada"):
        c = ficha.citas.get(k)
        if c is not None and c.origen.pagina:
            evidencia("1", c.origen.documento, c.origen.pagina, [c.texto[:80]])
    if gobierno.accionistas and "accionistas" in gobierno.origenes:
        evidencia("5", gobierno.origenes["accionistas"].documento, gobierno.origenes["accionistas"].pagina, [a.nombre for a in gobierno.accionistas[:8]])
    if gobierno.ejecutivos and "ejecutivos" in gobierno.origenes:
        evidencia("6", gobierno.origenes["ejecutivos"].documento, gobierno.origenes["ejecutivos"].pagina, [f"{e.nombre} {e.edad}" for e in gobierno.ejecutivos])
    if gobierno.retribucion and "retribucion" in gobierno.origenes:
        evidencia("6", gobierno.origenes["retribucion"].documento, gobierno.origenes["retribucion"].pagina, sorted({r.nombre for r in gobierno.retribucion}) + ["Summary Compensation Table"])
    if guidance.objetivos and guidance.origen_tabla is not None:
        evidencia("7", guidance.origen_tabla.documento, guidance.origen_tabla.pagina, [o.metrica for o in guidance.objetivos[:6]] + ["Forecast"])
    for c in guidance.citas_call[:4]:
        evidencia("7", c.origen.documento, c.origen.pagina, [c.texto[:70]])
    for origen in list(getattr(regiones, "origenes", {}).values())[:2]:
        if getattr(origen, "pagina", None):
            evidencia("4", origen.documento, origen.pagina, ["UCAN", "EMEA", "LATAM", "APAC"])
    recortar_pedidos()
    fotos_ejecutivos, fotos_consejo = secciones_mod.fotos(gobierno)

    # D · el modelo del analista
    from . import dcf as dcf_mod
    cierres = mercado.cierres if mercado is not None else {}
    cuadres = dcf_mod.cuadrar(modelo_dcf, hechos, cierres=cierres, agregador=agregador) if modelo_dcf is not None else []
    cuadros_dcf = secciones_mod.cuadros_dcf(n, modelo_dcf, cuadres, precio if precio.hay_dato else None, mercado, multiplos)
    cuadros_dcf["cuadres"] = cuadres
    # Los cuadros se numeran por orden de impresión, que es el del índice (A–I).
    # E · 21 y 22 con lo que declara la compañía y lo que asigna la bolsa
    mercado_cuadro = secciones_mod.cuadro_mercado_objetivo(n, mercado_objetivo) if mercado_objetivo is not None else None
    mercado_faltan = dict(mercado_objetivo.faltan) if mercado_objetivo is not None else {"fuente": "no se pidió la lectura del tamaño de mercado"}
    comparables_cuadro = secciones_mod.cuadros_comparables(n, comparables) if comparables is not None else None
    comparables_sic_cuadro = secciones_mod.cuadro_comparables_sic(n, comparables) if comparables is not None else None
    comparables_faltan = dict(comparables.faltan) if comparables is not None else {"fuente": "no se pidieron los comparables a la bolsa"}
    faltan += [f"Comparables · {k}: {v}" for k, v in comparables_faltan.items()] + [f"Mercado objetivo · {k}: {v}" for k, v in mercado_faltan.items()]
    # G · riesgos e historial
    riesgos_cuadros = secciones_mod.cuadros_riesgos(n, riesgos) if riesgos is not None else {}
    riesgos_recortes = secciones_mod.recortes_riesgos(exp, riesgos, salida_recortes) if riesgos is not None else []
    historial_cuadros = secciones_mod.cuadros_historial(n, historial) if historial is not None else {}
    if parte_b is not None and parte_b.notas:
        from . import guia as guia_mod
        xbrl = {}
        for (campo, p), h in hechos.items():
            if h.hay_dato and p.meses == 3 and campo in ("ingresos", "bpa_diluido"):
                xbrl[(campo, _etiqueta(p, anuales, tab))] = h.valor
        comparaciones = guia_mod.frente_a_real(parte_b.notas, parte_b.confirmadas, xbrl, splits=parte_b.splits)
        historial_cuadros["guias"] = parte_b_mod.cuadro_guia_real(n, comparaciones)
    historial_recorte = None
    if historial is not None and historial.fuente is not None:
        historial_recorte = secciones_mod.recorte_texto(exp, historial.fuente.documento, historial.fuente.pagina, ["CONSENSUS ACTUAL SURPRISE", "EPS Normalized", "Revenue (mm)"], salida_recortes, "32")
    faltan += [f"DCF · {k}: {v}" for k, v in cuadros_dcf.get("faltan", {}).items()]
    # F · lo que la bolsa publica, y la evidencia de cada petición (la respuesta literal, pintada)
    acc_portada = ficha.citas.get("acciones_portada")
    f_cuadros = secciones_mod.cuadros_f(n, posicionamiento, acc_portada.valor if acc_portada is not None else None) if posicionamiento is not None else {}
    f_faltan = dict(posicionamiento.faltan) if posicionamiento is not None else {"fuente": "no se pidió la lectura de la bolsa para la sección F"}
    for clave, lista in secciones_mod.recortes_f(posicionamiento, mercado, salida_recortes, comparables, agregador, proxima, historial).items():
        evidencias.setdefault(clave, []).extend(lista)
    if f_cuadros:
        for s in indice:
            if any(numero == numeros["24"] for numero, _ in s.apartados):      # la parte de la cadena de opciones
                s.estado = "parcial" if "iv" not in f_cuadros else ""
    faltan += [f"F · {k}: {v}" for k, v in f_faltan.items()]
    if riesgos is not None:
        faltan += [f"Riesgos · {k}: {v}" for k, v in riesgos.faltan.items()]
    if historial is not None:
        faltan += [f"Historial · {k}: {v}" for k, v in historial.faltan.items()]
    if gobierno.faltan.get("retratos"):
        faltan.append(f"Gobierno · retratos: {gobierno.faltan['retratos']}")
    if parte_b is not None:
        faltan += [f"Parte B · {x}" for x in parte_b.faltas] + [f"Gobierno · traducir {x}" for x in getattr(gobierno, "sin_traducir", [])]
    if modelo_dcf is not None:
        fuentes.append(f"{modelo_dcf.nombre} — libro de valoración del analista · sha256 {modelo_dcf.huella[:12]}")
    if posicion is not None and posicion.fichero is not None:
        fuentes.append(f"{posicion.fichero.name} — fichero de posición y tesis del analista")
    # el precio objetivo de la portada es del analista: el de su fichero de posición o, si no, el «objetivo calculado» de su libro
    objetivo_portada = None
    if posicion is not None and posicion.precio_objetivo is not None:
        objetivo_portada = ("precio objetivo del analista", posicion.precio_objetivo, f"fichero de posición {posicion.fichero.name if posicion.fichero else ''}")
    elif modelo_dcf is not None:
        for rotulo, valor, celda in modelo_dcf.anclajes_objetivo:
            if "calculado" in rotulo.lower() or "objetivo" in rotulo.lower():
                objetivo_portada = (rotulo, valor, f"libro del analista, {celda.cita}")
                break
    # el potencial es el objetivo del analista sobre la cotización oficial: las dos cifras están en la portada y su cociente también
    potencial = objetivo_portada[1] / precio.valor - 1 if objetivo_portada is not None and precio.hay_dato and precio.valor else None
    if proxima is not None:
        faltan.append(f"Fechas clave · próxima presentación: la compañía no la anuncia en ningún adjunto ni en la SEC; se imprime la que publica la bolsa "
                      f"({proxima.fecha:%d/%m/%Y}, {'esperada' if proxima.esperada else 'anunciada'}) y su cuadre con el agregador: {proxima.nota_contraste}")
    if multiplos is not None:
        faltan += [f"Múltiplos · {k}: {v}" for k, v in multiplos.faltan.items()]
    if agregador is not None:
        fuentes.append(f"{agregador.fuente} — resumen del valor (rentabilidad, deuda total, EV/EBITDA, PEG, fecha de resultados), consultado el {f_fecha(hoy)} · {agregador.respuesta[0]}")
    if historial is not None and historial.cartas:
        fuentes.append(f"SEC EDGAR — {len(historial.cartas)} cartas a accionistas (Exhibit 99.1 de los 8-K de resultados, "
                       f"{f_fecha(min(c.presentado for c in historial.cartas))} a {f_fecha(max(c.presentado for c in historial.cartas))})")
    # los números se imprimen limpios: las notas de cuadre bajo los cuadros van al apéndice
    todos_los_cuadros = [cifras, objetivos, segmentos_c, regiones_c, accionistas, filiales, ejecutivos, retribucion, fechas_c, catalizadores_c,
                         resultados, balance, flujo, rentabilidad, rentabilidad_ttm,
                         mercado_cuadro, comparables_cuadro, comparables_sic_cuadro] + [c for c in cuadros_dcf.values() if isinstance(c, Cuadro)] \
        + [c for _, c in cuadros_dcf.get("detalle_escenarios", [])] + list(riesgos_cuadros.values()) + list(historial_cuadros.values()) + list(f_cuadros.values())
    cuadres_apendice = _mover_cuadres(todos_los_cuadros)
    # documentación complementaria: los recortes de cada apartado, en el orden del índice, sin repetir imagen
    por_clave = dict(evidencias)
    for clave, lista in (narrativa_impresa.evidencias.items() if narrativa_impresa is not None else ()):
        por_clave.setdefault(clave, [])
        por_clave[clave] = por_clave[clave] + list(lista)
    por_clave.setdefault("30", []).extend(riesgos_recortes)
    if historial_recorte is not None:
        por_clave.setdefault("32", []).append(historial_recorte)
    documentacion = _documentacion(indice, numeros, por_clave)

    return Informe(
        ticker=ticker.upper(), nombre=ficha.nombre_presentacion or emisor.nombre, fecha_emision=hoy, emisor=emisor, expediente=exp, tablero=tab,
        hechos=hechos, ficha=_ficha(emisor, ficha, precio, exp, hechos, mercado), precio=precio, cifras_resumen=cifras, objetivos=objetivos,
        hitos=guidance.hitos, narrativa=narrativa_impresa, descripcion=ficha.citas.get("descripcion"),
        regiones=regiones_c, grafico_regiones=svg_regiones, grafico_ingresos=svg_ingresos, grafico_deuda=svg_deuda,
        accionistas=accionistas, filiales=filiales, ejecutivos=ejecutivos, retribucion=retribucion,
        citas_call=guidance.citas_call, proxima_presentacion=guidance.proxima_presentacion,
        resultados=resultados, balance=balance, flujo=flujo, rentabilidad=rentabilidad,
        resumen_contraste=tab.resumen, discrepancias=discrepancias, solo_sec=solo_sec, huecos=huecos,
        avisos=[a.texto for a in exp.avisos] + tab.avisos + avisos_graficos, fuentes=fuentes, faltan=faltan,
        periodos_anuales=anuales, periodos_trimestres=trimestres,
        indice=indice, numeros=numeros, titulos={clave: _titulo(indice, numero) for clave, numero in numeros.items()}, evidencias=evidencias, fotos_ejecutivos=fotos_ejecutivos, fotos_consejo=fotos_consejo,
        dcf=cuadros_dcf, riesgos_cuadros=riesgos_cuadros, riesgos_recortes=riesgos_recortes, riesgos_faltan=riesgos.faltan if riesgos is not None else {"item_1a": "no se pidió la lectura del Item 1A"},
        historial_cuadros=historial_cuadros, historial_frases=historial.frases_guia if historial is not None else [],
        historial_faltan=historial.faltan if historial is not None else {"historial": "no se pidió"}, historial_recorte=historial_recorte,
        posicion=posicion, posicion_faltan=posicion.faltan() if posicion is not None else {"fichero": f"el analista no ha rellenado su fichero de posición (formulario: python -m tesis.formulario {ticker.upper()} → posiciones/{ticker.upper()}.json)"},
        segmento_unico=_segmento_unico(exp), objetivo_portada=objetivo_portada, f_cuadros=f_cuadros, f_faltan=f_faltan,
        comparables_cuadro=comparables_cuadro, comparables_faltan=comparables_faltan, mercado_cuadro=mercado_cuadro, mercado_faltan=mercado_faltan,
        comparables_sic_cuadro=comparables_sic_cuadro, rentabilidad_ttm=rentabilidad_ttm, proxima_bolsa=proxima, potencial=potencial,
        recomendacion=posicion.recomendacion if posicion is not None else "", documentacion=documentacion, cuadres_apendice=cuadres_apendice,
        textos_b=parte_b_mod.textos(parte_b.entradas, parte_b.alias) if parte_b is not None else None, segmentos=segmentos_c, geografia=geografia_c,
        grafico_mezcla=svg_mezcla, fechas_clave=fechas_c, catalizadores=catalizadores_c,
        salidas_13g=list(getattr(gobierno, "salidas_13g", [])), clases_acciones=list(parte_b.clases) if parte_b is not None else [],
    )
