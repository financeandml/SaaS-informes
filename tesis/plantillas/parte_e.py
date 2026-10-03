"""Parte E (apartados 21–23): mercado, competencia y foso defensivo.

Las cifras de mercado, los competidores y las fuentes del foso son del analista, cada una con su cita verificada en el
documento y la página (03 §6): lo que no verifica no se imprime y queda como falta. El sistema pone los ingresos
verificados (SOM por defecto y cuota implícita = ingresos / SAM), las cifras de los comparables (SEC y cierre de
Nasdaq, la lista de F3) y los datos de apoyo del foso: ROIC − WACC, estabilidad del margen EBIT e I+D / ingresos.
"""

from __future__ import annotations
from . import lexico

import statistics
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Mapping, Optional, Sequence

from ..entradas import Entradas, comprobar_paso5, verificar_cita
from ..formato import Celda, fecha as f_fecha, numero, pct

__all__ = ["ParteE", "construir", "cuota_implicita", "ESCALAS"]

METODOS = {"top_down": "de arriba abajo", "bottom_up": "de abajo arriba", "declarado_compania": "declarado por la compañía"}
FOSOS = {"efectos_de_red": "Efectos de red", "costes_de_cambio": "Costes de cambio",
         "intangibles": "Intangibles (patentes, licencias, marcas)", "ventaja_de_costes": "Ventaja de costes",
         "escala_eficiente": "Escala eficiente", "ninguno": "Sin foso defensivo"}
TENDENCIAS = {"se_amplia": "se amplía", "estable": "estable", "se_estrecha": "se estrecha"}
# unidades monetarias admitidas para el SAM: con otra unidad (hogares, usuarios) no hay cuota en dinero
ESCALAS = {"USD": 1.0, "miles USD": 1e3, "millones USD": 1e6, "miles de millones USD": 1e9, "billones USD": 1e12,
           "EUR": 1.0, "miles EUR": 1e3, "millones EUR": 1e6, "miles de millones EUR": 1e9, "billones EUR": 1e12}


@dataclass
class ParteE:
    texto_21: str = ""
    cuadros: Dict[str, object] = field(default_factory=dict)          # mercado, competidores, comparables, foso, apoyo
    grafico: str = ""                                                 # SVG: crecimiento frente a margen EBIT
    grafico_fuente: str = ""
    amenazas: str = ""
    pendientes: Dict[str, str] = field(default_factory=dict)          # apartado → lo que falta del analista
    faltas: List[str] = field(default_factory=list)                   # a la puerta de calidad
    cuota: Optional[float] = None
    som_por_defecto: bool = False


def cuota_implicita(ingresos: float, sam: Mapping) -> Optional[float]:
    """Ingresos verificados / SAM, con el SAM en una unidad monetaria de `ESCALAS`; si no, None."""
    escala = ESCALAS.get(str(sam.get("unidad", "")))
    if escala is None or not sam.get("valor"):
        return None
    return ingresos / (float(sam["valor"]) * escala)


def _c(texto: str, nota: str = "", clase: str = "valor", capa: str = "S") -> Celda:
    return Celda(texto, "", capa, clase, nota)


def _cita(ev: Mapping, alias: Optional[Dict[str, str]]) -> str:
    from .parte_b import alias_doc
    doc = alias_doc(ev.get("doc", ""), alias)
    return f"{doc}, pág. {ev['pag']}" if ev.get("pag") not in (None, "") else doc


def _evidencias(lista: Sequence[Mapping], alias) -> tuple:
    """(texto impreso: «versión en español» [documento, pág.], literal original para el atributo title)."""
    impreso = " · ".join(f"«{ev.get('texto_es', '')}» [{_cita(ev, alias)}]" for ev in lista)
    return impreso, " · ".join(ev.get("texto", "") for ev in lista)


def _verificadas(lista, textos, umbral) -> List[Mapping]:
    return [ev for ev in (lista or []) if ev.get("texto_es") and verificar_cita(ev, textos, umbral)[0]]


def _cifra(valor: float, unidad: str, fija: bool = False) -> str:
    """«800.000 millones USD»; `fija`: con espacios de no separación, para que la celda no la parta en tres líneas."""
    texto = f"{numero(valor, 0 if float(valor).is_integer() else 1)} {unidad}"
    return texto.replace(" ", "\xa0") if fija else texto


def _ultimos(hechos, anuales, clave: str, n: int):
    """[(periodo, hecho)] de los n últimos ejercicios."""
    return [(p, hechos.get((clave, p))) for p in sorted(anuales, key=lambda p: p.fin)[-n:]]


def _mercado(d: ParteE, n, e: Entradas, textos, umbral, alias, ingresos, fy: str, anio: int) -> None:
    from .informe import Cuadro, FilaCuadro
    cifras = []
    for c in e.valor("mercado.cifras") or []:
        evs = _verificadas(c.get("evidencia"), textos, umbral)
        if evs and len(evs) == len(c.get("evidencia") or []) and isinstance(c.get("valor"), (int, float)):
            cifras.append((c, evs))
    if not cifras:
        d.pendientes["21"] = ("Pendiente del analista: al menos un TAM con su método y una cita verificada en el documento "
                              "y la página (paso 5).")
        return
    filas = []
    for c, evs in cifras:
        fuente, literal = _evidencias(evs, alias)
        filas.append(FilaCuadro(c.get("etiqueta", ""), [
            _c(c.get("clase", "")), _c(str(c.get("anio", ""))), _c(_cifra(c["valor"], c.get("unidad", ""), True), literal),
            _c(METODOS.get(c.get("metodo", ""), c.get("metodo", ""))), _c(fuente, literal)], capa="S"))
    soms = [c for c, _ in cifras if c.get("clase") == "SOM"]
    if not soms and ingresos is not None:
        d.som_por_defecto = True
        filas.append(FilaCuadro(f"Ingresos del ejercicio {fy} (SOM por defecto)", [
            # sin texto técnico en el cuerpo (fallo [35]): de dónde salen los ingresos, dicho como lo dice el apartado 8
            _c("SOM"), _c(fy), _c(_cifra(ingresos / 1e6, f"millones {lexico.moneda()}", True), "ingresos del estado de resultados (apartado 8)", capa="H"),
            _c("ingresos publicados"), _c(f"estado de resultados del ejercicio {fy} (apartado 8)")], capa="H"))
    sams = [c for c, _ in cifras if c.get("clase") == "SAM" and cuota_implicita(1.0, c) is not None]
    # el SAM del año más cercano al de los ingresos
    sam = min(sams, key=lambda c: abs(int(c.get("anio") or 0) - anio)) if sams else None
    if sam is not None and ingresos is not None:
        d.cuota = cuota_implicita(ingresos, sam)
        filas.append(FilaCuadro("Cuota implícita (ingresos / SAM)", [
            _c(""), _c(f"{fy} / {sam.get('anio')}"), _c(pct(d.cuota), f"{_cifra(ingresos / 1e6, 'millones ' + lexico.moneda())} / "
                                                       f"{_cifra(sam['valor'], sam.get('unidad', ''))}", capa="D"),
            _c("cálculo del sistema"), _c(f"ingresos {fy} (apartado 8) / SAM del analista")], capa="D", destacada=True,
            formula="Ingresos verificados del último ejercicio / SAM"))
    d.cuadros["mercado"] = Cuadro(n.siguiente(), "Tamaño de mercado: TAM, SAM y SOM", ["Clase", "Año", "Cifra", "Método", "Fuente"],
                                  filas, f"Fuente: analista, con cita verificada en el documento y la página; ingresos {lexico.de_las_cuentas()}.")
    tam = next((c for c, _ in cifras if c.get("clase") == "TAM"), None)
    frases = []
    if tam is not None:
        frases.append(f"El analista sitúa el mercado total (TAM) en {_cifra(tam['valor'], tam.get('unidad', ''))} en {tam.get('anio')}"
                      f" ({METODOS.get(tam.get('metodo', ''), '')})")
    if sam is not None:
        frases[-1:] = [(frases[-1] + " y " if frases else "El analista sitúa ") +
                       f"el mercado al que sirve la compañía (SAM) en {_cifra(sam['valor'], sam.get('unidad', ''))} en {sam.get('anio')}"]
    texto = (frases[0] + ". ") if frases else ""
    if soms:
        s = soms[0]
        texto += (f"Como mercado obtenible (SOM) toma «{s.get('etiqueta', '')}»: {_cifra(s['valor'], s.get('unidad', ''))} en "
                  f"{s.get('anio')} ({METODOS.get(s.get('metodo', ''), '')}). ")
    elif d.som_por_defecto:
        texto += f"Sin SOM del analista, el SOM son los ingresos verificados del ejercicio {fy}, {_cifra(ingresos / 1e6, 'millones ' + lexico.moneda())}. "
    if d.cuota is not None:
        texto += (f"Con unos ingresos de {_cifra(ingresos / 1e6, 'millones ' + lexico.moneda())} en el ejercicio {fy}, la cuota implícita sobre el SAM "
                  f"es del {pct(d.cuota)}. ")
    d.texto_21 = texto + f"Cifras, métodos y citas, en el cuadro {d.cuadros['mercado'].numero}."


def _competidores(d: ParteE, n, e: Entradas, textos, umbral, alias) -> None:
    from .informe import Cuadro, FilaCuadro
    lista = e.valor("competencia.competidores") or []
    if not lista:
        d.pendientes["22"] = "Pendiente del analista: mínimo tres competidores, con por qué compiten y su evidencia (paso 5)."
        return
    con_cuota = any(c.get("cuota") is not None and _verificadas(c.get("cuota_evidencia"), textos, umbral) for c in lista)
    filas, distintas = [], {}          # cada evidencia se imprime una vez, bajo el cuadro; la fila lleva su referencia
    for c in lista:
        evs = _verificadas(c.get("evidencia"), textos, umbral)
        for ev in evs:
            distintas.setdefault((ev.get("doc"), str(ev.get("pag")), ev.get("texto")), _evidencias([ev], alias)[0])
        fuente = " · ".join(dict.fromkeys(_cita(ev, alias) for ev in evs))
        literal = " · ".join(ev.get("texto", "") for ev in evs)
        celdas = [_c(c.get("ticker") or "—", "sin cotización en EE. UU." if not c.get("ticker") else ""), _c(c.get("por_que", ""))]
        if con_cuota:
            cev = _verificadas(c.get("cuota_evidencia"), textos, umbral)
            celdas.append(_c(pct(float(c["cuota"]) / 100) if c.get("cuota") is not None and cev else "—",
                             _evidencias(cev, alias)[0] if cev else "sin cuota con evidencia"))
        celdas.append(_c(fuente or "analista", literal))
        filas.append(FilaCuadro(c.get("nombre", ""), celdas, capa="S"))
    columnas = ["Ticker", "Por qué compite"] + (["Cuota"] if con_cuota else []) + ["Evidencia"]
    notas = [f"Evidencia: {v}" for v in distintas.values()]
    notas += [] if con_cuota else ["Sin cuotas de mercado: ninguna tiene una fuente del expediente que las publique."]
    d.cuadros["competidores"] = Cuadro(n.siguiente(), "Competidores", columnas, filas,
                                       f"Fuente: analista, con la evidencia del documento citado ({lexico.negocio()}).", notas)


def _comparables(d: ParteE, n, motor, hechos, anuales, etiqueta, nombre: str, ticker: str) -> None:
    from . import graficos
    from ..datos.ficha import nombre_presentacion
    from .informe import Cuadro, FilaCuadro
    comps = getattr(getattr(motor, "comparables", None), "filas", None) or []
    if not comps:
        return
    ult = _ultimos(hechos, anuales, "ingresos", 2)
    ing = ult[-1][1] if ult else None
    eb = hechos.get(("ebit", ult[-1][0])) if ult else None
    propia = {"cap": getattr(motor, "cap_mercado", None), "ing": ing.valor if ing is not None and ing.hay_dato else None,
              "ej": f_fecha(ult[-1][0].fin)[3:] if ult else ""}
    propia["crec"] = (ing.valor / ult[0][1].valor - 1) if (len(ult) == 2 and propia["ing"] and ult[0][1] is not None
                                                          and ult[0][1].hay_dato and ult[0][1].valor) else None
    propia["margen"] = eb.valor / ing.valor if (eb is not None and eb.hay_dato and propia["ing"]) else None

    def fila(rot, cap, ej, ing_, crec, margen, nota, destacada=False):
        def celda(v, fmt, motivo):
            return _c(fmt(v), nota, capa="H") if v is not None else Celda("N/A", "", "", "na", motivo)
        return FilaCuadro(rot, [_c(ej, nota, capa="H"), celda(cap, lambda x: numero(x / 1e6), "sin precio o acciones"),
                                celda(ing_, lambda x: numero(x / 1e6), "sin ingresos anuales publicados"),
                                celda(crec, pct, "sin dos ejercicios de ingresos"), celda(margen, pct, "sin EBIT anual publicado")],
                          capa="H", destacada=destacada)
    fp = getattr(motor, "fecha_precio", None)
    # una sola moneda por columna, la del informe: sin tipo de cambio, sumar tamaños en dos monedas sería inventarlos
    moneda = lexico.moneda()
    filas = [fila(f"{nombre} ({ticker})", propia["cap"], propia["ej"], propia["ing"], propia["crec"], propia["margen"],
                  f"{lexico.de_las_cuentas()}; cierre oficial de {lexico.bolsa()} del {f_fecha(fp)}", destacada=True)]
    puntos = [(ticker, propia["crec"], propia["margen"], True)] if propia["crec"] is not None and propia["margen"] is not None else []
    fuera, fuentes = [], []
    for c in comps:
        if c.moneda and c.moneda != moneda:
            fuera.append(f"{c.ticker} ({c.moneda})")
            continue
        fuente_c = getattr(c, "fuente", "") or "SEC (companyfacts); cierre oficial de Nasdaq"
        fuentes.append(fuente_c)
        filas.append(fila(f"{nombre_presentacion('', c.nombre)} ({c.ticker})" if c.nombre else c.ticker, c.capitalizacion, c.ejercicio, c.ingresos,
                          c.crecimiento, c.margen_ebit, f"{fuente_c} del {f_fecha(c.fecha_precio)}" if c.fecha_precio else fuente_c))
        if c.crecimiento is not None and c.margen_ebit is not None:
            puntos.append((c.ticker, c.crecimiento, c.margen_ebit, False))
    notas = [f"Fuera del cuadro por presentar en otra moneda que la del informe ({moneda}; sin tipo de cambio no se comparan "
             f"tamaños): {', '.join(fuera)}."] if fuera else []
    origen = ("SEC EDGAR (10-K y 10-Q de cada emisor) y cierres oficiales de Nasdaq" if not fuentes or all(f.startswith("SEC") for f in fuentes)
              else "cuentas oficiales de cada emisor publicadas en su bolsa y cierres oficiales de esa bolsa")
    d.cuadros["comparables"] = Cuadro(
        n.siguiente(), "Comparables: tamaño, crecimiento y margen del último ejercicio",
        ["Cierre del ejercicio", f"Capitalización (mill. {moneda})", f"Ingresos (mill. {moneda})", "Crecimiento de ingresos", "Margen EBIT"],
        filas, f"Fuente: {origen}; lista de comparables del analista.", notas)
    d.grafico = graficos.dispersion(puntos, "Crecimiento de ingresos (último ejercicio)", "Margen EBIT")
    d.grafico_fuente = f"Los mismos datos que el cuadro {d.cuadros['comparables'].numero}."


def _foso(d: ParteE, n, e: Entradas, textos, umbral, alias) -> None:
    from .informe import Cuadro, FilaCuadro
    filas = []
    for f in e.valor("moat.fuentes") or []:
        evs = _verificadas(f.get("evidencias"), textos, umbral)
        if not evs or f.get("tipo") not in FOSOS:
            continue
        texto, literal = _evidencias(evs, alias)
        dur = f.get("durabilidad_anios")
        filas.append(FilaCuadro(FOSOS[f["tipo"]], [
            _c(f"{numero(dur, 0)} años" if isinstance(dur, (int, float)) else "—"),
            _c(TENDENCIAS.get(f.get("tendencia", ""), f.get("tendencia", ""))), _c(texto, literal)], capa="S"))
    if filas:
        d.cuadros["foso"] = Cuadro(n.siguiente(), "Fuentes del foso defensivo", ["Durabilidad", "Tendencia", "Evidencia"], filas,
                                   "Fuente: analista (tipo, durabilidad y tendencia), con evidencias verificadas en el documento y la página.")
    else:
        d.pendientes["23"] = "Pendiente del analista: al menos una fuente del foso defensivo con evidencia verificada (paso 5)."
    amenazas = e.valor("moat.amenazas")
    d.amenazas = (amenazas.get("texto", "") if isinstance(amenazas, dict) else (amenazas or "")).strip()


def _apoyo(d: ParteE, n, hechos, anuales, etiqueta: Callable, wacc: Optional[float]) -> None:
    """Datos de apoyo del sistema (01 › 23): ROIC − WACC, estabilidad del margen EBIT e I+D / ingresos, cinco ejercicios."""
    from .informe import Cuadro, FilaCuadro
    periodos = sorted(anuales, key=lambda p: p.fin)[-5:]
    if not periodos:
        return

    def valor(clave, p):
        h = hechos.get((clave, p))
        return h.valor if h is not None and h.hay_dato else None

    def fila(rotulo, valores, resumen, formula, motivo):
        celdas = [_c(pct(v), formula, capa="D") if v is not None else Celda("N/A", "", "", "na", motivo) for v in valores]
        return FilaCuadro(rotulo, celdas + [_c(resumen, formula, capa="D")], capa="D", formula=formula)

    filas = []
    roic = [valor("roic", p) for p in periodos]
    if wacc is not None and any(v is not None for v in roic):
        dif = [v - wacc if v is not None else None for v in roic]
        hay = [v for v in dif if v is not None]
        filas.append(fila("ROIC − WACC", dif, f"media {pct(statistics.mean(hay))}",
                          f"ROIC del ejercicio (sección C) − WACC del motor hoy ({pct(wacc)})", "sin ROIC del ejercicio"))
    margen = [(valor("ebit", p) / valor("ingresos", p)) if valor("ebit", p) is not None and valor("ingresos", p) else None for p in periodos]
    hay = [v for v in margen if v is not None]
    if len(hay) >= 2:
        resumen = f"σ {numero(statistics.pstdev(hay) * 100, 1)} pp · {pct(min(hay))} a {pct(max(hay))}"
        filas.append(fila("Margen EBIT", margen, resumen, "EBIT / Ingresos (SEC)", "sin EBIT o ingresos del ejercicio"))
    idi = [(valor("tecnologia", p) / valor("ingresos", p)) if valor("tecnologia", p) is not None and valor("ingresos", p) else None
           for p in periodos]
    hay = [v for v in idi if v is not None]
    if hay:
        filas.append(fila("I+D / ingresos", idi, f"media {pct(statistics.mean(hay))}", "Investigación y desarrollo / Ingresos (SEC)",
                          "sin gasto en I+D del ejercicio"))
    if filas:
        d.cuadros["apoyo"] = Cuadro(n.siguiente(), "Datos de apoyo del foso defensivo", [etiqueta(p) for p in periodos] + ["Cinco años"],
                                    filas, f"Fuente: {lexico.cuentas()}, derivados de la sección C y WACC del motor de valoración.")


def construir(n, e: Entradas, textos: Mapping[str, str], umbral: float, hechos, anuales, etiqueta: Callable,
              motor=None, alias: Optional[Dict[str, str]] = None, nombre: str = "", ticker: str = "") -> ParteE:
    """Los cuadros se numeran en el orden de impresión: 21 (mercado), 22 (competidores, comparables), 23 (foso, apoyo)."""
    d = ParteE(faltas=comprobar_paso5(e, textos, umbral))
    ult = _ultimos(hechos, anuales, "ingresos", 1)
    ingresos = ult[0][1].valor if ult and ult[0][1] is not None and ult[0][1].hay_dato else None
    fy = etiqueta(ult[0][0]) if ult else ""
    _mercado(d, n, e, textos, umbral, alias, ingresos, fy, ult[0][0].fin.year if ult else 0)
    _competidores(d, n, e, textos, umbral, alias)
    _comparables(d, n, motor, hechos, anuales, etiqueta, nombre, ticker)
    _foso(d, n, e, textos, umbral, alias)
    v = getattr(motor, "valoracion", None)
    _apoyo(d, n, hechos, anuales, etiqueta, v.wacc.wacc if v is not None else None)
    if not d.amenazas:
        d.pendientes["amenazas"] = "Pendiente del analista: amenazas al foso defensivo (20–80 palabras)."
    return d
