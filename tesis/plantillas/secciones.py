"""Los cuadros de las secciones D–I y la evidencia visual de las de texto.

Mismo criterio que `informe`: aquí no se lee ningún documento ni se calcula nada
nuevo; se toman los objetos que producen `dcf`, `riesgos`, `historial`, `gobierno`,
`narrativa` y se colocan en cuadros numerados con su fuente. Cada
celda que viene del libro del analista lleva capa S y su celda de origen; cada
celda que viene de un documento lleva Hd y su página. Lo que no hay sale N/A con
motivo.

La evidencia visual de un apartado de texto es el recorte de cada página que
citan sus frases (con las anclas literales de la cita), y la de una tabla leída
de un documento es el recorte de la región de esa tabla. Se producen aquí, con
`recortes.recortar_lineas`, y la maqueta las imprime debajo del apartado.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from datetime import date, datetime

from ..heredado.dcf import Cuadre, Modelo
from ..datos.expediente import Adjunto, Expediente, Tipo
from .. import rotulos
from ..formato import Celda, fecha as f_fecha, numero, pct, veces
from ..datos.gobierno import Gobierno
from ..datos.hechos import Contraste
from ..heredado.historial import Historial
from .informe import Cuadro, Cuadros, FilaCuadro
from ..datos.recortes import Recorte, recortar_lineas
from ..heredado.riesgos import FAMILIAS, Riesgos

__all__ = ["FotoImpresa", "cuadro_comparables_sic", "cuadro_iv", "cuadro_mercado_objetivo", "cuadro_multiplos_sec", "cuadro_rentabilidad_ttm", "cuadros_comparables",
           "cuadros_dcf", "cuadros_f", "cuadros_historial", "cuadros_riesgos", "fotos", "recorte_texto", "recortes_f", "recortes_riesgos"]


# ---------------------------------------------------------------------------
# Evidencia visual genérica
# ---------------------------------------------------------------------------

def recorte_texto(exp: Expediente, documento: str, pagina: Optional[int], anclas: Sequence[str], salida: Optional[Path], seccion: str) -> Optional[Recorte]:
    """El recorte de la página `pagina` del adjunto `documento` (clave o nombre) que contiene las anclas."""
    if salida is None or pagina is None or not anclas:
        return None
    adj = next((a for a in exp.adjuntos if documento in (a.clave, a.nombre)), None)
    if adj is None or adj.tipo is Tipo.XLSX:
        return None
    return recortar_lineas(adj, pagina, list(anclas), salida, [seccion], sufijo=f"s{seccion}")


# ---------------------------------------------------------------------------
# Equipo directivo: retratos y trayectoria (apartado 6)
# ---------------------------------------------------------------------------

@dataclass
class FotoImpresa:
    nombre: str
    cargo: str
    detalle: str                 # «56 años · CFO desde 2019» o «consejero desde 2002 · 58 años»
    ruta: Optional[Path]
    pie: str
    trayectoria: List[str] = field(default_factory=list)
    nota: str = ""


def fotos(g: Gobierno) -> Tuple[List[FotoImpresa], List[FotoImpresa]]:
    ejecutivos = []
    # sin la proxy en PDF no hay retratos ni trayectorias: la tarjeta repetiría el cuadro de ejecutivos
    for e in (g.ejecutivos if any(x.foto or x.trayectoria for x in g.ejecutivos) else []):
        pie = f"Proxy, pág. {e.pagina_ficha or e.pagina}" + (f" · retrato huella {e.foto.huella}" if e.foto else " · sin retrato en la proxy")
        ejecutivos.append(FotoImpresa(e.nombre, e.cargo, f"{e.edad} años", e.foto.ruta if e.foto else None, pie, e.trayectoria))
    consejo = []
    for c in g.consejeros:
        detalle = " · ".join(x for x in (f"consejero desde {c.desde}" if c.desde else "", f"{c.edad} años" if c.edad else "") if x)
        consejo.append(FotoImpresa(c.nombre, c.cargo.title(), detalle, c.foto.ruta if c.foto else None, f"Proxy, pág. {c.pagina}", [], c.nota))
    return ejecutivos, consejo


# ---------------------------------------------------------------------------
# Sección D: el modelo del analista
# ---------------------------------------------------------------------------

def _s(texto: str, nota: str = "", clase: str = "valor") -> Celda:
    return Celda(texto, "", "S", clase, nota)


def _na(motivo: str) -> Celda:
    return Celda("N/A", "", "", "na", motivo)


def _decimales(formato: str) -> int:
    m = re.search(r"\.(0+)", formato)
    return len(m.group(1)) if m else 0


def _fmt(v: Optional[float], unidad: str, celda=None) -> str:
    if v is None:
        return "N/A"
    formato = (getattr(celda, "formato", None) or "").split(";", 1)[0]
    if "%" in formato:                 # el formato de la celda manda: Excel guarda la fracción; dos decimales como mínimo, como el cuadro de escenarios
        return pct(v, max(_decimales(formato), 2))
    if formato.endswith("\\x") or formato.endswith('"x"'):
        return veces(v, max(_decimales(formato), 1))
    if unidad == "%":
        return pct(v, 1) if abs(v) < 1.5 else pct(v / 100, 1)
    if unidad == "x":
        return veces(v, 1)
    if unidad == "usd":
        return numero(v, 2)
    if unidad == "musd":
        return numero(v, 0)
    return numero(v, 2)


def _cita_columna(e, rotulo: str, k: int) -> str:
    citas = e.citas.get(rotulo) or []
    return citas[k] if k < len(citas) else (e.celdas[rotulo].cita if rotulo in e.celdas else "")


def _unidad_fila(rotulo: str) -> str:
    r = rotulo.lower()
    if "%" in r or "crecimiento" in r or "margen" in r or "tipo impositivo" in r or "peso" in r or "recorrido" in r or "rentabilidad" in r or "diferencia" in r:
        return "%"
    if "por acción" in r or "usd/acción" in r or "precio" in r:
        return "usd"
    if "factor de descuento" in r:
        return "coef"
    return "musd"


def cuadros_dcf(n: Cuadros, m: Optional[Modelo], cuadres: List[Cuadre], precio_oficial=None, mercado=None, multiplos=None) -> Dict[str, object]:
    """Los cuadros de los apartados 12–20 a partir del libro del analista, o N/A con motivo si no hay libro."""
    salida: Dict[str, object] = {"modelo": m, "faltan": dict(m.faltan) if m else {"libro": "el analista no ha adjuntado el libro del DCF (--dcf)"}}
    if m is None:
        if multiplos is not None:
            salida["multiplos_sec"] = cuadro_multiplos_sec(n, multiplos)
        return salida
    fuente = f"Fuente: {m.nombre} (libro de valoración del analista). Cada celda indica hoja!celda de origen al pasar el ratón."
    if m.recalculado is not None:
        fuente += f" El libro llegó guardado sin recalcular: los valores son los de una copia recalculada con el Excel de la máquina ({m.recalculado[0].name}, sha256 {m.recalculado[1][:12]})."

    # 12 · escenarios y valor razonable
    filas = []
    for t in m.tabla_escenarios:
        cc = t.get("celdas") or [t["celda"]] * 5           # cada cifra cita su propia celda, no la del valor
        filas.append(FilaCuadro(t["nombre"], [_s(pct(t["wacc"], 2), cc[0].cita), _s(pct(t["g"], 2), cc[1].cita), _s(numero(t["valor_hoy"], 2), cc[2].cita),
                                              _s(numero(t["valor_rodado"], 2) if t.get("valor_rodado") is not None else "N/A", cc[3].cita if len(cc) > 4 else t["celda"].cita),
                                              _s(pct(t["peso"], 0), cc[-1].cita)], capa="S"))
    if m.valor_razonable:
        vr = m.valor_razonable
        filas.append(FilaCuadro("Valor razonable ponderado", [Celda("", "", "", "valor", ""), Celda("", "", "", "valor", ""),
                                                             _s(numero(vr["hoy"], 2), vr["celda"].cita + (" · " + vr["celda"].formula if vr["celda"].formula else "")),
                                                             _s(numero(vr["rodado"], 2) if vr.get("rodado") is not None else "N/A", vr["celda"].cita), Celda("", "", "", "valor", "")],
                                capa="S", destacada=True, formula=vr["celda"].formula or ""))
    salida["escenarios"] = Cuadro(n.siguiente(), "Valoración intrínseca por escenarios (USD por acción)", ["WACC", "g terminal", "Valor hoy", "Valor rodado 24 m", "Peso"], filas,
                                  fuente + " Los pesos y los parámetros son del analista.")

    # 12 · cuadre con los hechos contrastados: cuando el libro y el dato oficial difieren, rige el oficial
    filas = []
    for c in cuadres:
        glifo = c.contraste.value
        u = _unidad_fila(c.rotulo_modelo)
        clase = "na" if c.valor_informe is None else ("negativo" if c.contraste is Contraste.DISCREPANTE else "valor")
        rige = c.valor_informe if c.valor_informe is not None else c.valor_modelo
        origen_rige = "dato oficial (SEC / bolsa)" if c.valor_informe is not None else "el libro, a falta de dato oficial con que cuadrar"
        filas.append(FilaCuadro(c.rotulo_modelo, [_s(_fmt(c.valor_modelo, u, c.celda), c.celda.cita),
                                                  Celda(_fmt(c.valor_informe, u, c.celda) if c.valor_informe is not None else "N/A", glifo, "H", clase, c.nota),
                                                  Celda(f"{c.campo} {c.periodo}", "", "", "valor", c.nota),
                                                  Celda(_fmt(rige, u, c.celda), "", "H" if c.valor_informe is not None else "S", "valor", origen_rige)], capa="S",
                                destacada=c.contraste is Contraste.DISCREPANTE))
    salida["cuadre"] = Cuadro(n.siguiente(), "Entradas del modelo frente al dato oficial más reciente",
                              ["Libro del analista", "Dato oficial (SEC · bolsa)", "Hecho y periodo", "Rige en el informe"], filas,
                              "El dato oficial es el último contrastado en la sección C (o el cierre oficial de la bolsa para el precio). Cuando el libro y el dato oficial "
                              "difieren, el informe se rige por el oficial en todo lo que calcula (capitalización, múltiplos); las valoraciones de los cuadros siguientes son "
                              "las del libro tal cual las entregó el analista. Al pasar el ratón sobre cada cifra, la explicación de la diferencia.")

    # 12 · supuestos generales
    filas = [FilaCuadro(s.rotulo, [_s(_fmt(s.valor, _unidad_fila(s.rotulo), s.celda), f"{s.celda.cita}" + (" · fórmula " + s.celda.formula if s.celda.formula else " · valor tecleado")),
                                   Celda(s.origen or "—", "", "S", "valor" if s.origen else "na", s.celda.cita)], capa="S",
                        formula=s.celda.formula or "") for s in m.supuestos]
    salida["supuestos"] = Cuadro(n.siguiente(), "Supuestos generales del modelo del analista", ["Valor", "Origen / justificación (del analista)"], filas, fuente, partible=True)

    # 13–15 · cada escenario
    salida["detalle_escenarios"] = []
    for e in m.escenarios:
        cols = e.anios
        filas = []
        for rotulo, valores in e.filas.items():
            u = _unidad_fila(rotulo)
            filas.append(FilaCuadro(rotulo, [_s(_fmt(v, u, e.celdas.get(rotulo)) if v is not None else "—", _cita_columna(e, rotulo, k)) for k, v in enumerate(valores)], capa="S",
                                    destacada=bool(re.search(r"FCFF|flujo de caja libre|free cash", rotulo, re.I)), formula=(e.celdas.get(rotulo).formula or "") if e.celdas.get(rotulo) else ""))
        for rotulo, v in e.resumen.items():
            u = _unidad_fila(rotulo)
            celda = e.celdas.get(rotulo)
            filas.append(FilaCuadro(rotulo, [_s(_fmt(v, u, celda), celda.cita if celda else "")] + [Celda("", "", "", "valor", "")] * (len(cols) - 1), capa="S",
                                    destacada="POR ACCIÓN" in rotulo.upper() or "por acción" in rotulo, formula=(celda.formula or "") if celda else ""))
        parametros = " · ".join(x for x in (f"WACC {pct(e.wacc, 2)}" if e.wacc is not None else "WACC N/A", f"g {pct(e.g, 2)}" if e.g is not None else "g N/A",
                                             f"peso {pct(e.peso, 0)}" if e.peso is not None else "peso N/A") if x)
        salida["detalle_escenarios"].append((e.nombre, Cuadro(n.siguiente(), f"Escenario {e.nombre}: supuestos, FCFF y valoración ({parametros}; M USD salvo indicación)",
                                                                cols, filas, fuente + f" Hoja «{e.hoja}».", partible=True)))

    # 16 · sensibilidad
    if m.sensibilidad:
        s = m.sensibilidad
        base = m.escenario("base")
        filas = []
        for w, fila in zip(s["ejes_wacc"], s["matriz"]):
            celdas = []
            for g, v in zip(s["ejes_g"], fila):
                destacada = base is not None and base.wacc is not None and base.g is not None and abs(w - base.wacc) < 1e-6 and abs(g - base.g) < 1e-6
                celdas.append(Celda(numero(v, 2) if v is not None else "N/A", "●" if destacada else "", "S", "valor" if v is not None else "na",
                                    "caso base" if destacada else f"WACC {pct(w, 2)} · g {pct(g, 2)}"))
            filas.append(FilaCuadro(f"WACC {pct(w, 2)}", celdas, capa="S"))
        salida["sensibilidad"] = Cuadro(n.siguiente(), "Sensibilidad del valor por acción (USD) al WACC y al crecimiento terminal",
                                        [f"g {pct(g, 2)}" for g in s["ejes_g"]], filas, fuente + f" Hoja «{s['celda'].hoja}». La combinación del caso base, si está en la matriz, lleva la nota «caso base».")
    # 17 · múltiplos: el «actual» del libro va sobre el precio que el analista tecleó; sobre la cotización oficial
    # solo se reescala donde la reescala es exacta (PER y P/FCF son lineales en el precio); el EV depende de la
    # deuda neta del libro y no se recalcula.
    oficial_17 = precio_oficial.valor if precio_oficial is not None and precio_oficial.hay_dato else None
    precio_libro = m.supuesto("precio de mercado")

    def _actual_oficial(x) -> Celda:
        if oficial_17 is None:
            return _na("sin cotización oficial (apartado 1)")
        if x.actual is None or precio_libro is None or not precio_libro.valor:
            return _na("sin múltiplo actual o sin precio del libro")
        if "EV" in x.rotulo.upper():
            return _na("el EV depende de la deuda neta del libro; no se recalcula")
        v = x.actual * oficial_17 / precio_libro.valor
        return Celda(veces(v, 1), "∑", "D", "valor", f"{veces(x.actual, 2)} × {numero(oficial_17, 2)} / {numero(precio_libro.valor, 2)} (múltiplo del libro reescalado a la cotización oficial)")

    if m.multiplos:
        _c = lambda x, k: x.celdas[k].cita if k < len(x.celdas) else x.celda.cita
        filas = [FilaCuadro(x.rotulo, [_s(_fmt(x.base, "usd" if "PER" in x.rotulo.upper() else "musd"), _c(x, 0)), _s(veces(x.actual, 1) if x.actual is not None else "N/A", _c(x, 1)),
                                       _actual_oficial(x), _s(veces(x.objetivo, 1) if x.objetivo is not None else "N/A", _c(x, 2)),
                                       _s(numero(x.valor_accion, 2) if x.valor_accion is not None else "N/A", _c(x, 3)),
                                       Celda(x.origen or "—", "", "S", "valor" if x.origen else "na", "")], capa="S") for x in m.multiplos]
        if any(m.rango_multiplos):
            filas.append(FilaCuadro("Rango por múltiplos (mín. – máx.)", [Celda("", "", "", "valor", "")] * 4 +
                                    [_s(f"{numero(m.rango_multiplos[0], 2) if m.rango_multiplos[0] is not None else 'N/A'} – {numero(m.rango_multiplos[1], 2) if m.rango_multiplos[1] is not None else 'N/A'}"),
                                     Celda("", "", "", "valor", "")], capa="S", destacada=True))
        salida["multiplos"] = Cuadro(n.siguiente(), "Valoración por múltiplos (del analista)",
                                     ["Base de cálculo", "Múltiplo actual (precio del libro)", "Actual sobre cotización oficial", "Múltiplo objetivo", "Valor por acción (USD)", "Origen del múltiplo (del analista)"],
                                     filas, fuente + " El «múltiplo actual» usa el precio de mercado que el analista tecleó en su libro; la columna siguiente lo reescala a la cotización oficial del informe donde la reescala es exacta.")
    if multiplos is not None:
        salida["multiplos_sec"] = cuadro_multiplos_sec(n, multiplos)
    # 18 · reverse DCF
    if m.reverse:
        r = m.reverse
        filas = [FilaCuadro(rotulo, [_s(_fmt(v, _unidad_fila(rotulo), c), c.cita), Celda(o or "—", "", "S", "valor" if o else "na", "")], capa="S") for rotulo, v, o, c in r["parametros"]]
        for rotulo, v in r["resumen"].items():
            c = r["celdas"].get(rotulo)
            filas.append(FilaCuadro(rotulo, [_s(_fmt(v, _unidad_fila(rotulo), c), c.cita if c else ""), Celda("", "", "", "valor", "")], capa="S",
                                    destacada="implícito" in rotulo.lower() and "acción" in rotulo.lower(), formula=(c.formula or "") if c else ""))
        salida["reverse"] = Cuadro(n.siguiente(), "Reverse DCF: expectativas implícitas en el precio que el analista tomó como referencia", ["Valor", "Nota"], filas,
                                   fuente + f" Hoja «{r['hoja']}».")
        if r["anios"] and r["filas"]:
            filas = [FilaCuadro(rotulo, [_s(_fmt(v, "musd") if v is not None else "—") for v in valores], capa="S") for rotulo, valores in r["filas"].items()]
            salida["reverse_flujos"] = Cuadro(n.siguiente(), "Reverse DCF: FCFF implícito por año (M USD)", r["anios"], filas, fuente)
    # 20 · precio objetivo, referencias y margen de seguridad: las tres primeras columnas tal cual las calcula el
    # libro; la cuarta, el recorrido de cada valor sobre la cotización oficial del informe (∑, fórmula impresa),
    # que es el margen de seguridad que el índice pide y que el libro no puede dar porque su precio es tecleado.
    oficial = precio_oficial.valor if precio_oficial is not None and precio_oficial.hay_dato else None

    def _sobre_oficial(v: Optional[float]) -> Celda:
        if oficial is None:
            return _na("sin cotización oficial (apartado 1)")
        if v is None:
            return _na("sin valor")
        return Celda(pct(v / oficial - 1, 1), "∑", "D", "valor", f"{numero(v, 2)} / {numero(oficial, 2)} − 1")

    def _recorrido(rotulo: str, v: Optional[float], celda) -> Celda:
        """El recorrido solo tiene sentido sobre un precio: una fila que el libro guarda en porcentaje —un peso, un
        upside ya calculado— dividida entre la cotización daría una cifra sin significado."""
        if "%" in (getattr(celda, "formato", None) or "").split(";", 1)[0] or _unidad_fila(rotulo) == "%":
            return Celda("", "", "", "valor", "")
        return _sobre_oficial(v)

    # La unidad de este cuadro es USD por acción —lo dice su título— y con esa misma unidad lo relee la doble
    # comprobación (`revision.columna_cita`); por encima manda el formato de la celda, así que un «peso» o un
    # «upside» que el libro guarda en porcentaje se imprime en porcentaje. Si las dos reglas se separan, cada cifra
    # parece bien por su lado y la emisión se detiene sin que al libro le pase nada (regla 9).
    filas = [FilaCuadro(t, [_s(_fmt(v, "usd", c), c.cita + (" · " + c.formula if c.formula else "")), Celda("", "", "", "valor", ""), Celda("", "", "", "valor", ""), _recorrido(t, v, c)], capa="S",
                        destacada="calculado" in t.lower() or "objetivo" in t.lower(), formula=c.formula or "") for t, v, c in m.anclajes_objetivo]
    _r = lambda ref, k: ref["celdas"][k].cita if k < len(ref.get("celdas") or []) else ref["celda"].cita
    for ref in m.referencias_precio:
        es_precio_libro = "mercado" in ref["rotulo"].lower() or "entrada" in ref["rotulo"].lower()
        filas.append(FilaCuadro(ref["rotulo"], [_s(numero(ref["valor"], 2), _r(ref, 0)),
                                                _s(pct(ref["sobre_entrada"], 1) if ref.get("sobre_entrada") is not None else "N/A", _r(ref, 1)),
                                                _s(pct(ref["sobre_precio"], 1) if ref.get("sobre_precio") is not None else "N/A", _r(ref, 2)),
                                                _sobre_oficial(ref["valor"]) if not es_precio_libro else Celda("", "", "", "valor", "")], capa="S"))
    c = mercado.cotizacion if mercado is not None else None
    if precio_oficial is not None and precio_oficial.hay_dato:
        filas.append(FilaCuadro("Cotización oficial del informe", [Celda(numero(oficial, 2), "", "Hd", "valor", precio_oficial.nota), Celda("", "", "", "valor", ""),
                                                                   Celda("", "", "", "valor", ""), Celda("0,0\u00a0%", "", "", "cero", "")], capa="Hd", destacada=True))
        cons = mercado.consenso if mercado is not None else None
        if cons is not None:
            detalle = " · ".join(x for x in [f"{cons.analistas} analistas" if cons.analistas else "", f"{cons.compra} compra / {cons.mantener} mantener / {cons.venta} venta" if cons.compra is not None else "",
                                             f"rango {numero(cons.bajo, 2)} – {numero(cons.alto, 2)}" if cons.bajo is not None and cons.alto is not None else "",
                                             f"serie mensual hasta {cons.mes:%m/%Y}" if cons.mes else ""] if x)
            filas.append(FilaCuadro(f"Consenso de analistas publicado por la bolsa ({detalle})",
                                    [Celda(numero(cons.objetivo, 2), "", "Hd", "valor", "página de analistas de Nasdaq (no se conoce la fecha de cada recomendación)"),
                                     Celda("", "", "", "valor", ""), Celda("", "", "", "valor", ""), _sobre_oficial(cons.objetivo)], capa="Hd"))
        if c is not None and c.objetivo_consenso is not None:
            contraste = mercado.contraste_consenso if mercado is not None else None
            glifo = contraste[0].value if contraste else ""
            filas.append(FilaCuadro("«1 Year Target» de la ficha del valor (misma bolsa)",
                                    [Celda(numero(c.objetivo_consenso, 2), glifo, "Hd", "valor" if not contraste or contraste[0] is not Contraste.DISCREPANTE else "negativo",
                                           contraste[1] if contraste else "cifra de la ficha del valor, sin número de analistas ni fecha"),
                                     Celda("", "", "", "valor", ""), Celda("", "", "", "valor", ""), _sobre_oficial(c.objetivo_consenso)], capa="Hd"))
    nota_precio = ("La cotización oficial del informe (apartado 1) es N/A: el «sobre precio de mercado» es el del libro, con el precio que el analista tecleó, y la última columna queda N/A."
                   if oficial is None else f"Cotización oficial del informe: {numero(oficial, 2)} USD ({precio_oficial.nota}); la última columna es valor / cotización − 1.")
    salida["objetivo"] = Cuadro(n.siguiente(), "Precio objetivo, referencias de precio y recorrido (USD por acción)",
                                ["Valor", "Sobre precio de entrada", "Sobre precio de mercado del libro", "Sobre cotización oficial"], filas, fuente + " " + nota_precio)
    return salida


def _linea_multiplo(l) -> FilaCuadro:
    if l.valor is None:
        valor = _na(l.motivo or "sin dato")
    elif l.unidad == "%":
        valor = Celda(pct(l.valor, 1), "∑", "D", "valor", l.formula)
    elif l.unidad == "x":
        valor = Celda(veces(l.valor, 1), "∑", "D", "valor", l.formula)
    elif l.unidad == "musd":
        valor = Celda(numero(l.valor / 1e6), "∑", "D", "valor", l.formula)
    else:
        valor = Celda(numero(l.valor, 2), "∑", "D", "valor", l.formula)
    # sin columna del agregador: Yahoo solo para la volatilidad implícita (regla 6)
    return FilaCuadro(l.rotulo, [valor, Celda(l.componentes or "—", "", "", "valor", l.formula)], capa="D", formula=l.formula)


def cuadro_multiplos_sec(n: Cuadros, m) -> Cuadro:
    """Apartado 17: PER, EV/EBITDA, EV/Ventas, P/FCF y PEG sobre las últimas cifras de la SEC y la cotización oficial."""
    # un múltiplo sin valor (PEG con BPA a la baja) no se imprime como «N/A»: se dice por qué en la nota (06 §3.10)
    filas = [_linea_multiplo(l) for l in m.lineas if not l.rotulo.startswith("RO") and l.valor is not None]
    notas: List[str] = [f"{l.rotulo}: no se calcula ({l.motivo or 'sin dato'})." for l in m.lineas
                        if not l.rotulo.startswith("RO") and l.valor is None]
    fuente = (f"Fuente: cifras de la SEC contrastadas en la sección C, en suma de los cuatro últimos trimestres ({', '.join(m.trimestres)}) y saldos al "
              f"{f_fecha(m.cierre)}; cotización oficial de la bolsa; acciones de la portada del último formulario.")
    if m.faltan:
        fuente += " " + " ".join(f"{k}: {v}." for k, v in m.faltan.items())
    return Cuadro(n.siguiente(), "Múltiplos sobre las últimas cifras de la SEC y la cotización oficial", ["Valor", "Cálculo"], filas, fuente, notas)


def cuadro_rentabilidad_ttm(n: Cuadros, m) -> Optional[Cuadro]:
    """Apartado 11: ROE y ROA de los últimos doce meses con la definición del 10-K (sobre cifras de la SEC)."""
    lineas = [l for l in m.lineas if l.rotulo.startswith("RO")]
    if not lineas:
        return None
    filas = [_linea_multiplo(l) for l in lineas]
    notas = []
    notas.append("Los formularios de la compañía no publican ROE, ROA ni ROIC como cifras; el 10-K define el ROE (beneficio después de impuestos / patrimonio medio) para su plan de "
                 "incentivos y esa es la definición que se aplica. El ROIC no lo publica ninguna fuente: solo la fórmula del cuadro anterior.")
    return Cuadro(n.siguiente(), f"Rentabilidad de los últimos doce meses ({m.trimestres[0]}–{m.fin})", ["Valor", "Cálculo"], filas,
                  "Fuente: beneficio neto TTM y saldos medios de la SEC (sección C).", notas)


# ---------------------------------------------------------------------------
# Sección G: riesgos e historial
# ---------------------------------------------------------------------------

def cuadros_riesgos(n: Cuadros, r: Riesgos) -> Dict[str, Cuadro]:
    salida: Dict[str, Cuadro] = {}
    fuente = (f"Fuente: {r.documento}, Item 1A (págs. {r.paginas[0]}–{r.paginas[1]}); epígrafes literales, en negrita en el original. "
              "La familia es inferencia del sistema: al pasar el ratón, el motivo.") if r.documento else "Fuente: —"
    for fam in FAMILIAS:
        filas = []
        for x in r.por_familia()[fam]:
            texto = x.epigrafe + (f" [{x.nota}]" if x.nota else "")
            filas.append(FilaCuadro(x.cabecera.replace("Risks Related to ", "").replace("Risk Factors Related to ", ""),
                                    [Celda(texto, "", "Hd", "negativo" if x.nota else "valor", f"pág. {x.pagina} · familia por {x.motivo} (certeza {x.certeza.value})"),
                                     Celda(f"pág. {x.pagina}", "", "", "valor", f"familia por {x.motivo} (certeza {x.certeza.value})")], capa="Hd"))
        salida[fam] = Cuadro(n.siguiente(), f"Riesgos {fam}s" if fam != "ejecución" else "Riesgos de ejecución", ["Epígrafe del 10-K (literal)", "Página"], filas,
                             fuente if filas else fuente + f" Ningún epígrafe clasificado como {fam}.", partible=True)
    return salida


def recortes_riesgos(exp: Expediente, r: Riesgos, salida: Optional[Path], maximo_por_familia: int = 1) -> List[Recorte]:
    """Un recorte por familia: el primer epígrafe de cada una, en su página, con su título en negrita."""
    if salida is None or not r.documento:
        return []
    recs: List[Recorte] = []
    for fam in FAMILIAS:
        for x in r.por_familia()[fam][:maximo_por_familia]:
            rec = recorte_texto(exp, r.documento, x.pagina, [x.epigrafe[:90]], salida, f"30_{fam}")
            if rec is not None:
                recs.append(rec)
    return recs


def cuadros_historial(n: Cuadros, h: Historial) -> Dict[str, Cuadro]:
    salida: Dict[str, Cuadro] = {}
    fuente = (f"Fuente: {h.fuente.documento}, pág. {h.fuente.pagina} ({h.proveedor}). El «real» del proveedor es su BPA normalizado; al pasar el ratón, "
              "su cuadre con el BPA diluido de la sección C." if h.fuente else "Fuente: —")
    # en el orden en que se imprimen: previsión de la compañía frente a real, consenso frente a real (transcripción), la serie de la bolsa y el consenso siguiente
    if h.guias:
        from ..heredado.cartas import METRICAS
        metricas = list(METRICAS)
        por_trimestre: Dict[str, Dict[str, object]] = {}
        for g in h.guias:
            por_trimestre.setdefault(g.trimestre, {})[g.metrica] = g
        filas = []
        for trimestre in sorted(por_trimestre, key=lambda k: (k[2:], k[0])):
            celdas = []
            for metrica in metricas:
                g = por_trimestre[trimestre].get(metrica)
                if g is None:
                    celdas.append(_na("la carta no previó esta métrica"))
                    continue
                if g.desvio is None:
                    texto = f"{numero(g.prevista, 2)} → {numero(g.real, 2)} (desvío no definido: previsión nula)"
                elif g.unidad == "%":
                    signo = "+" if g.desvio > 0 else ""
                    texto = f"{numero(g.prevista, 1)} % → {numero(g.real, 1)} % ({signo}{numero(g.desvio * 100, 1)} p.p.)"
                elif g.unidad == "USD":
                    texto = f"{numero(g.prevista, 2)} → {numero(g.real, 2)} ({'+' if g.desvio > 0 else ''}{numero(g.desvio * 100, 1)} %)"
                else:
                    texto = f"{numero(g.prevista)} → {numero(g.real)} ({'+' if g.desvio > 0 else ''}{numero(g.desvio * 100, 1)} %)"
                nota = (f"previsión en la carta del {f_fecha(g.carta_prevision.presentado)} (8-K, Ex. 99.1); real en la carta del {f_fecha(g.carta_real.presentado)}"
                        + (f" · {g.nota}" if g.nota else ""))
                celdas.append(Celda(texto, g.contraste.value, "H", "negativo" if g.desvio is not None and g.desvio < 0 else "valor", nota))
            filas.append(FilaCuadro(trimestre, celdas, capa="H"))
        primera, ultima = min(c.presentado for c in h.cartas), max(c.presentado for c in h.cartas)
        salida["guias"] = Cuadro(n.siguiente(), "Previsión de la compañía frente a lo publicado, trimestre a trimestre (previsión → real, desvío)",
                                 ["Ingresos (M USD)", "EBIT (M USD)", "Margen operativo", "Beneficio neto (M USD)", "BPA diluido (USD)"], filas,
                                 f"Fuente: cartas a accionistas depositadas en la SEC como Exhibit 99.1 de los 8-K de resultados ({len(h.cartas)} cartas, del "
                                 f"{f_fecha(primera)} al {f_fecha(ultima)}): la columna «Forecast» de cada carta frente a la cifra publicada en la carta siguiente. "
                                 "Al pasar el ratón, las dos cartas y el cuadre del real con la sección C. Un desvío en el margen es en puntos porcentuales.",
                                 partible=True)
    filas = []
    for s in h.sorpresas:
        d = 2 if s.metrica.startswith("BPA") else 2
        filas.append(FilaCuadro(f"{s.periodo} · {s.metrica}", [Celda(numero(s.consenso, d), "", "Hd", "valor", ""), Celda(numero(s.real, d), s.contraste.value, "Hd", "valor", s.nota),
                                                                Celda(pct(s.sorpresa, 2), "", "Hd", "negativo" if s.sorpresa < 0 else "valor", "")], capa="Hd"))
    salida["sorpresas"] = Cuadro(n.siguiente(), "Consenso frente a real: últimos trimestres", ["Consenso", "Real", "Sorpresa"], filas, fuente)
    if h.bolsa:
        filas = []
        for s in h.bolsa:
            filas.append(FilaCuadro(f"{s.periodo} · publicado el {f_fecha(s.publicado)}" if s.publicado else s.periodo,
                                    [Celda(numero(s.consenso, 2), "", "Hd", "valor", ""), Celda(numero(s.real, 2), s.contraste.value, "Hd", "valor", s.nota),
                                     Celda(pct(s.sorpresa, 2), "", "Hd", "negativo" if (s.sorpresa or 0) < 0 else "valor", "") if s.sorpresa is not None else _na("la bolsa no publica la sorpresa")],
                                    capa="Hd"))
        salida["bolsa"] = Cuadro(n.siguiente(), "Consenso frente a BPA publicado, según la bolsa", ["Consenso (USD)", "BPA publicado (USD)", "Sorpresa"], filas,
                                 "Fuente: Nasdaq (web del mercado), serie de sorpresas de beneficio de su proveedor de estimaciones; el BPA que publica es el normalizado por ese "
                                 "proveedor y, al pasar el ratón, su cuadre con el BPA GAAP diluido de la sección C.")
    filas = []
    for periodo, metrica, consenso, guia in h.consenso_siguiente:
        filas.append(FilaCuadro(f"{periodo} · {metrica}", [Celda(numero(consenso, 2) if consenso is not None else "N/A", "", "Hd", "valor" if consenso is not None else "na", ""),
                                                            Celda(numero(guia, 2) if guia is not None else "N/A", "", "Hd", "valor" if guia is not None else "na", "guía de la compañía según el proveedor")], capa="Hd"))
    for periodo, metrica, consenso in h.consenso_anual:
        filas.append(FilaCuadro(f"{periodo} · {metrica}", [Celda(numero(consenso, 2) if consenso is not None else "N/A", "", "Hd", "valor" if consenso is not None else "na", ""),
                                                            Celda("—", "", "", "valor", "sin guía anual en la tabla del proveedor")], capa="Hd"))
    salida["consenso"] = Cuadro(n.siguiente(), "Consenso y guía para los próximos periodos", ["Consenso", "Guía de la compañía"], filas, fuente)
    return salida


# ---------------------------------------------------------------------------
# Sección F: lo que la bolsa publica (interino hasta la API del analista)
# ---------------------------------------------------------------------------

def _hd(texto: str, nota: str = "", clase: str = "valor") -> Celda:
    return Celda(texto, "", "Hd", clase, nota)


def _cifra_bolsa(texto: str) -> str:
    """Una cifra tal cual la publica la bolsa («$273,821», «91.60%») en la convención del documento; lo que no es número, tal cual."""
    limpio = texto.replace("$", "").replace(",", "").strip()
    m = re.fullmatch(r"(-?\d+(?:\.(\d+))?)(%?)", limpio)
    if not m:
        return texto
    v, dec = float(m.group(1)), len(m.group(2) or "")
    return pct(v / 100, dec) if m.group(3) else numero(v, dec)


def _n(v: Optional[float], decimales: int = 0) -> Celda:
    return _hd(numero(v, decimales)) if v is not None else _na("la bolsa no publica este dato")


def _ratio(numerador: Optional[float], denominador: Optional[float], rotulo: str) -> Celda:
    if numerador is None or denominador in (None, 0):
        return _na("sin ambos términos")
    return Celda(numero(numerador / denominador, 2), "∑", "D", "valor", f"{rotulo}: {numero(numerador)} / {numero(denominador)}")


def _fecha_bolsa(texto: str) -> str:
    """«September 25, 2026» o «Sep 25, 2026» (la bolsa) → «25/09/2026»; si no se reconoce, el literal."""
    from datetime import datetime as _dt
    for formato in ("%B %d, %Y", "%b %d, %Y", "%m/%d/%Y"):
        try:
            return f_fecha(_dt.strptime(str(texto).strip(), formato).date())
        except ValueError:
            continue
    return str(texto)


def _ultima_operacion(texto: str, sesiones=None) -> str:
    """«LAST TRADE: $75.66 (AS OF SEP 17, 2026 1:46 PM ET)» (literal de la bolsa) → «última operación: 75,66 USD el
    17/09/2026 a las 13:46 (hora de Nueva York)». Sin reconocerlo, nada: el literal inglés no va al cuerpo.

    La fecha del literal es la de la ficha de la bolsa, que llama «Sep 24» al cierre del viernes 25: si una sesión
    posterior del histórico oficial cerró a ese precio, la fecha es la de esa sesión (A1, fallo [42])."""
    m = re.search(r"\$\s*([\d,]+(?:\.\d+)?)\s*\(AS OF (\w{3})\w* (\d{1,2}), (\d{4})(?:\s+(\d{1,2}):(\d{2})\s*([AP]M))?", str(texto or ""), re.I)
    meses = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
    if not m or m.group(2).upper() not in meses:
        return ""
    precio = float(m.group(1).replace(",", ""))
    dia = date(int(m.group(4)), meses.index(m.group(2).upper()) + 1, int(m.group(3)))
    hora = ""
    if m.group(5):
        h = int(m.group(5)) % 12 + (12 if m.group(7).upper() == "PM" else 0)
        hora = f" a las {h:02d}:{m.group(6)} (hora de Nueva York)"
    posteriores = sorted((f for f, s in (sesiones or {}).items() if f > dia and abs(s.cierre - precio) <= 0.0005 * precio), reverse=True)
    if posteriores:
        dia, hora = posteriores[0], " (cierre de la sesión)"
    return f"última operación: {numero(precio, 2)} USD el {f_fecha(dia)}{hora}"


def cuadros_f(n: Cuadros, p, acciones_circulacion: Optional[float] = None, maximo_vencimientos: int = 10, maximo_filas: int = 12,
              sesiones=None, hasta: Optional[date] = None, hoy: Optional[date] = None, resultados: Optional[date] = None) -> Dict[str, Cuadro]:
    """Los cuadros de la parte H (31–35) con lo que publica la bolsa, en el orden en que se imprimen (numeración). Con `hoy`,
    también los calculados sobre la cadena (`parte_h`): strikes y máximo dolor, VI frente a realizada y movimiento en resultados."""
    from ..fuentes.posicionamiento import FUENTE
    salida: Dict[str, Cuadro] = {}
    hora = p.obtenido.strftime("%d/%m/%Y %H:%M") if p.obtenido else ""
    base = f"Fuente: {FUENTE}, consultada el {hora} (la bolsa lo publica; el depósito original no se ha cruzado con EDGAR)."
    if p.cadena is not None and p.cadena.vencimientos:
        c = p.cadena
        filas = []
        for v in c.vencimientos[:maximo_vencimientos]:
            filas.append(FilaCuadro(_fecha_bolsa(v.fecha), [_n(v.vol_calls), _n(v.vol_puts), _ratio(v.vol_puts, v.vol_calls, "volumen puts / volumen calls"),
                                              _n(v.oi_calls), _n(v.oi_puts), _ratio(v.oi_puts, v.oi_calls, "interés abierto puts / calls"), _hd(str(v.contratos))], capa="Hd"))
        tot = {k: c.total(k) for k in ("vol_calls", "vol_puts", "oi_calls", "oi_puts")}
        filas.append(FilaCuadro(f"Total ({len(c.vencimientos)} vencimientos{f', {len(filas)} impresos' if len(filas) < len(c.vencimientos) else ''})", [_n(tot["vol_calls"]), _n(tot["vol_puts"]), _ratio(tot["vol_puts"], tot["vol_calls"], "volumen puts / volumen calls"),
                                                                                _n(tot["oi_calls"]), _n(tot["oi_puts"]), _ratio(tot["oi_puts"], tot["oi_calls"], "interés abierto puts / calls"),
                                                                                _hd(str(sum(v.contratos for v in c.vencimientos)))], capa="Hd", destacada=True))
        salida["cadena"] = Cuadro(n.siguiente(), "Cadena de opciones por vencimiento: volumen e interés abierto (contratos)",
                                  ["Vol. calls", "Vol. puts", "Put/Call vol.", "Int. abierto calls", "Int. abierto puts", "Put/Call int. abierto", "Precios de ejercicio"], filas,
                                  base + f" Cadena completa ({c.total_filas} filas)" + (f"; {_ultima_operacion(c.ultimo, sesiones)}" if _ultima_operacion(c.ultimo) else "")
                                  + ". El volumen es el de la sesión en curso y el interés abierto el del cierre anterior. "
                                  "Put/Call = puts / calls (al pasar el ratón, las cifras). Sin volatilidad implícita: la bolsa no la publica.", partible=True)
        if hoy is not None:
            from . import parte_h
            x = parte_h.cuadro_strikes(n, p, hoy)
            if x is not None:
                salida["strikes"] = x
        iv = cuadro_iv(n, p)
        if iv is not None:
            salida["iv"] = iv
        if hoy is not None:
            salida["vi_realizada"] = parte_h.cuadro_vi_realizada(n, p, sesiones or {}, hasta or hoy, hoy)
            x = parte_h.cuadro_movimiento(n, p, resultados, hoy)
            if x is not None:
                salida["movimiento"] = x
    if p.institucional is not None and (p.institucional.resumen or p.institucional.posiciones):
        i = p.institucional
        filas = [FilaCuadro(rotulos.bolsa(rotulo), [_hd(_cifra_bolsa(valor), f"literal de la bolsa: {rotulo} · {valor}"), Celda("", "", "", "valor", "")], capa="Hd") for rotulo, valor in i.resumen]
        filas += [FilaCuadro(rotulos.bolsa(rotulo), [_n(tenedores), _n(acciones)], capa="Hd", destacada=rotulo.startswith("Total")) for rotulo, tenedores, acciones in i.posiciones]
        salida["institucional"] = Cuadro(n.siguiente(), "Posicionamiento institucional (13F): resumen", ["Tenedores", "Acciones"], filas,
                                         base + " Cifras de la bolsa a partir de los 13F, en la convención del documento (el literal, al pasar el ratón); la fecha de cada 13F varía por gestor.")
        reciente = max((f for _, f, _, _, _ in i.mayores if f), default=None)

        def fecha_13f(fecha):
            # un 13F más de un trimestre anterior al más reciente de la lista es antiguo y se marca (F7)
            if fecha is None:
                return _na("sin fecha")
            antiguo = reciente is not None and (reciente - fecha).days > 100
            return Celda(f"{f_fecha(fecha)} (antiguo)" if antiguo else f_fecha(fecha), "", "Hd", "negativo" if antiguo else "valor",
                         f"13F anterior al más reciente de la lista ({f_fecha(reciente)})" if antiguo else "")
        filas = [FilaCuadro(nombre, [fecha_13f(fecha), _n(acciones), _n(variacion),
                                     Celda(pct(v_pct / 100, 2), "", "Hd", "negativo" if v_pct < 0 else "valor", "") if v_pct is not None else _na("—")], capa="Hd")
                 for nombre, fecha, acciones, variacion, v_pct in i.mayores[:maximo_filas + 3]]
        salida["mayores"] = Cuadro(n.siguiente(), "Mayores tenedores institucionales (13F)", ["Fecha del 13F", "Acciones", "Variación (acciones)", "Variación"], filas,
                                   base + " Los accionistas de más del 5 % según la proxy están en el cuadro de estructura corporativa: fechas distintas, no se comparan.", partible=True)
    if p.insiders is not None and (p.insiders.operaciones or p.insiders.ultimas):
        s = p.insiders
        filas = [FilaCuadro(rotulos.bolsa(rotulo), [_n(m3), _n(m12)], capa="Hd") for rotulo, m3, m12 in s.operaciones]
        filas += [FilaCuadro(rotulos.bolsa(rotulo), [Celda(numero(m3), "", "Hd", "negativo" if (m3 or 0) < 0 else "valor", "") if m3 is not None else _na("—"),
                                      Celda(numero(m12), "", "Hd", "negativo" if (m12 or 0) < 0 else "valor", "") if m12 is not None else _na("—")], capa="Hd",
                             destacada=rotulo.startswith("Net")) for rotulo, m3, m12 in s.acciones]
        salida["insiders"] = Cuadro(n.siguiente(), "Operaciones de directivos (Form 4): recuento y acciones", ["3 meses", "12 meses"], filas,
                                    base + (f" {s.total_operaciones} operaciones registradas en total." if s.total_operaciones else ""))
        impresas = s.ultimas[:maximo_filas + 3]
        cruces = list(s.cruce[:len(impresas)]) if s.cruce else []

        def _form4(c) -> Celda:
            # F9: cada operación con su Form 4 de EDGAR, o el porqué de que no case; la bolsa sigue siendo la fuente de la fila
            if c.casado:
                return Celda(f_fecha(c.presentado), Contraste.CONFIRMADO.value, "H", "valor", f"Form 4 {c.accession} presentado el {f_fecha(c.presentado)}: {c.url}")
            return _na(c.motivo)
        filas = [FilaCuadro(f"{insider} · {rotulos.bolsa(relacion)}", [_hd(f_fecha(fecha)) if fecha else _na("sin fecha"), _hd(rotulos.bolsa(tipo), f"literal de la bolsa: {tipo}"),
                                                                     _n(acciones), _n(precio, 2)] + ([_form4(cruces[i])] if cruces else []), capa="Hd")
                 for i, (insider, relacion, fecha, tipo, acciones, precio) in enumerate(impresas)]
        fuente = base + " «Venta automática» es una venta bajo un plan 10b5-1, según la rotula la bolsa."
        if cruces:
            fuente = (f"Fuente: {FUENTE}, consultada el {hora}; cruzada con los Form 4 del emisor en SEC EDGAR: "
                      f"{sum(1 for c in cruces if c.casado)} de {len(cruces)} operaciones casadas con su depósito (titular, fecha y acciones). "
                      "«Venta automática» es una venta bajo un plan 10b5-1, según la rotula la bolsa.")
        salida["insiders_ultimas"] = Cuadro(n.siguiente(), "Últimas operaciones de directivos",
                                            ["Fecha", "Tipo", "Acciones", "Precio (USD)"] + (["Form 4 (EDGAR)"] if cruces else []), filas,
                                            fuente, partible=True)
    if p.short is not None and p.short.filas:
        filas = []
        for liq, interes, vol, dias in p.short.filas[:maximo_filas]:
            celdas = [_n(interes), _n(vol), _n(dias, 2)]
            if acciones_circulacion and interes is not None:
                celdas.append(Celda(pct(interes / acciones_circulacion, 2), "∑", "D", "valor", f"{numero(interes)} / {numero(acciones_circulacion)} acciones en circulación (portada del último 10-Q)"))
            else:
                celdas.append(_na("sin acciones en circulación"))
            filas.append(FilaCuadro(f_fecha(liq), celdas, capa="Hd"))
        nota_split = f" Serie desde la primera liquidación posterior al split del {f_fecha(p.short.desde)} para no mezclar acciones de antes y de después." if p.short.desde else ""
        salida["short"] = Cuadro(n.siguiente(), "Interés en corto (FINRA, publicado por la bolsa) por fecha de liquidación",
                                 ["Interés corto (acciones)", "Vol. medio diario", "Días para cubrir", "% del capital"], filas, base + nota_split, partible=True)
    return salida


def recortes_f(p, mercado, salida: Optional[Path], comparables=None, agregador=None, proxima=None, historial=None,
               parte_b=None) -> Dict[str, List[Recorte]]:
    """La evidencia de la sección F, de la cotización y de las demás fuentes externas: la respuesta literal de cada petición, pintada.

    Con la parte B, la evidencia del historial (26) sale de lo que ella misma usa —las sorpresas de la bolsa y las notas de
    resultados de EDGAR—: la misma fuente que el cuadro que respalda (regla 13). `historial` es el camino antiguo."""
    import json as json_mod
    from ..fuentes.posicionamiento import FUENTE
    from ..datos.recortes import volcado_api
    recs: Dict[str, List[Recorte]] = {}
    if salida is None:
        return recs
    if proxima is not None:
        rec = volcado_api(proxima.respuesta[0], proxima.respuesta[1], proxima.respuesta[2], salida, "nasdaq_fecha_resultados", "Fecha de la próxima presentación de resultados", FUENTE)
        if rec is not None:
            recs.setdefault("7", []).append(rec)
    if agregador is not None:
        url, cuerpo, obtenido = agregador.respuesta
        rec = volcado_api(url, cuerpo, obtenido, salida, "yahoo_resumen", "Resumen del valor en el agregador: rentabilidad, deuda total, EV/EBITDA, PEG, fecha de resultados", agregador.fuente,
                          extracto=_extracto_api(cuerpo, "yahoo_resumen"))
        if rec is not None:
            recs.setdefault("17", []).append(rec)
    if historial is not None:
        if historial.bolsa_respuesta is not None:
            url, cuerpo, obtenido = historial.bolsa_respuesta
            rec = volcado_api(url, cuerpo, obtenido, salida, "nasdaq_sorpresas", "Consenso frente a BPA publicado (serie de la bolsa)", FUENTE)
            if rec is not None:
                recs.setdefault("32", []).append(rec)
        if historial.cartas:
            resumen = [{"carta_8k_presentada": c.presentado.isoformat(), "accession": c.accession, "url": c.url, "trimestre_publicado": c.trimestre,
                        "prevision_para_el_trimestre_siguiente": {f"{k[0]} · {k[1]}": v for k, v in c.prevision.items()}} for c in historial.cartas]
            cuerpo = json_mod.dumps(resumen, indent=1, ensure_ascii=False)
            rec = volcado_api("https://www.sec.gov/cgi-bin/browse-edgar (8-K, Item 2.02, Exhibit 99.1)", cuerpo, datetime.now(), salida, "edgar_cartas",
                              "Cartas a accionistas depositadas en la SEC: previsión de cada carta para el trimestre siguiente", "SEC EDGAR (Exhibit 99.1 de los 8-K de resultados)")
            if rec is not None:
                recs.setdefault("32", []).append(rec)
    if parte_b is not None:
        if getattr(parte_b, "sorpresas_respuesta", None) is not None:
            url, cuerpo, obtenido = parte_b.sorpresas_respuesta
            rec = volcado_api(url, cuerpo, obtenido, salida, "nasdaq_sorpresas", "Consenso frente a BPA publicado (serie de la bolsa)", FUENTE)
            if rec is not None:
                recs.setdefault("32", []).append(rec)
        if getattr(parte_b, "notas", None):
            resumen = [{"nota_8k_presentada": x.presentado.isoformat(), "url": x.url, "trimestre_publicado": x.publicado,
                        "guia": [{"metrica": c.metrica, "trimestre": c.trimestre, "bajo": c.bajo, "alto": c.alto, "unidad": c.unidad}
                                 for c in x.candidatos]} for x in parte_b.notas]
            cuerpo = json_mod.dumps(resumen, indent=1, ensure_ascii=False)
            rec = volcado_api("https://www.sec.gov/cgi-bin/browse-edgar (8-K, Item 2.02, Exhibit 99.1)", cuerpo, datetime.now(), salida, "edgar_notas",
                              "Notas de resultados depositadas en la SEC: la guía que publica cada una", "SEC EDGAR (Exhibit 99.1 de los 8-K de resultados)")
            if rec is not None:
                recs.setdefault("32", []).append(rec)
    if comparables is not None and comparables.respuesta_sic is not None:
        url, atom, obtenido = comparables.respuesta_sic
        ciks = re.findall(r"<cik>(\d+)</cik>", atom)
        cuerpo = json_mod.dumps({"sic": comparables.sic, "descripcion": comparables.sic_descripcion, "emisores_cik": ciks,
                                 "con_ticker": [x.ticker for x in comparables.filas_sic]}, indent=1, ensure_ascii=False)
        rec = volcado_api(url, cuerpo, obtenido, salida, "edgar_sic", f"Emisores con el SIC {comparables.sic} según EDGAR", "SEC EDGAR (búsqueda por SIC)")
        if rec is not None:
            recs.setdefault("22", []).append(rec)
    piezas = []
    if mercado is not None:
        for clave, apartado, rotulo in (("cotizacion", "1", "Cotización y ficha del valor"), ("resumen", "1", "Resumen del valor: cierre anterior, capitalización, volumen medio"),
                                        ("historico", "1", "Histórico de cierres"), ("consenso", "20", "Consenso de analistas: precio objetivo y recomendaciones")):
            if clave in mercado.crudos:
                url, cuerpo, obtenido = mercado.crudos[clave]
                piezas.append((apartado, clave, url, cuerpo, obtenido, rotulo))
    if p is not None:
        for clave, apartado, rotulo in (("cadena", "24", "Cadena de opciones"), ("institucional", "27", "Posicionamiento institucional (13F)"),
                                        ("insiders", "28", "Operaciones de insiders (Form 4)"), ("short", "29", "Short interest")):
            bloque = getattr(p, clave, None)
            if bloque is not None and bloque.respuesta is not None:
                r = bloque.respuesta
                piezas.append((apartado, clave, r.url, r.cuerpo, r.obtenido, rotulo))
    for apartado, clave, url, cuerpo, obtenido, rotulo in piezas:
        rec = volcado_api(url, cuerpo, obtenido, salida, f"nasdaq_{clave}", rotulo, FUENTE, extracto=_extracto_api(cuerpo, clave))
        if rec is not None:
            recs.setdefault(apartado, []).append(rec)
    if p is not None and p.iv is not None and p.iv.respuesta is not None:
        r = p.iv.respuesta
        rec = volcado_api(r.url, r.cuerpo, r.obtenido, salida, "yahoo_opciones", "Cadena de opciones con volatilidad implícita (excepción Yahoo Finance)", p.iv.fuente,
                          extracto=_extracto_api(r.cuerpo, "yahoo"))
        if rec is not None:
            recs.setdefault("25", []).append(rec)
    if comparables is not None and comparables.respuesta is not None:
        url, cuerpo, obtenido = comparables.respuesta
        rec = volcado_api(url, cuerpo, obtenido, salida, "nasdaq_screener", f"Screener de la bolsa: valores de la industria «{comparables.industria}»", FUENTE)
        if rec is not None:
            recs.setdefault("22", []).append(rec)
    return recs


def _extracto_api(cuerpo: str, clave: str, lineas: int = 26) -> Optional[List[str]]:
    """Las líneas de la respuesta que llevan los datos: en la cadena de opciones, la cabecera de la respuesta y la
    primera fila con strike (las primeras líneas son solo los rótulos de las columnas)."""
    import json
    try:
        bonito = json.dumps(json.loads(cuerpo), indent=1, ensure_ascii=False).splitlines()
    except ValueError:
        return None
    if clave == "yahoo_resumen":
        quiero = ('"returnOnEquity"', '"returnOnAssets"', '"totalDebt"', '"totalCash"', '"ebitda"', '"enterpriseValue"', '"enterpriseToEbitda"', '"pegRatio"',
                  '"trailingEps"', '"sharesOutstanding"', '"earningsDate"', '"isEarningsDateEstimate"', '"mostRecentQuarter"')
        salida = []
        for k, l in enumerate(bonito):
            if any(q in l for q in quiero):
                salida.extend(bonito[k:k + 3])
        return salida[:lineas] if salida else None
    if clave == "yahoo":
        # el primer contrato fuera del dinero: el más cercano al subyacente, no los strikes residuales del principio
        inicio = next((k for k, l in enumerate(bonito) if '"inTheMoney": false' in l), None)
        if inicio is None:
            return None
        cabeza = [l for l in bonito[:40] if '"regularMarketPrice"' in l or '"regularMarketTime"' in l or '"symbol"' in l][:3]
        desde = max(0, inicio - 16)
        return cabeza + ["  ..."] + bonito[desde:desde + lineas - len(cabeza) - 1]
    if clave != "cadena":
        return None
    inicio = next((k for k, l in enumerate(bonito) if '"strike": "' in l), None)
    if inicio is None:
        return None
    cabeza = [l for l in bonito[:6] if '"totalRecord"' in l or '"lastTrade"' in l]
    desde = max(0, inicio - 12)
    return cabeza + ["  ..."] + bonito[desde:desde + lineas - len(cabeza) - 1]


def cuadro_iv(n: Cuadros, p) -> Optional[Cuadro]:
    """Apartado 25 (unificado): IV en el dinero y fuera del dinero por vencimiento, sesgo ∑ y el interés abierto
    del agregador cuadrado con el de la bolsa."""
    if p is None or p.iv is None or not any(x.hay_iv for x in p.iv.vencimientos):
        return None
    v = p.iv
    filas = []
    for x in v.vencimientos:
        def _iv(valor, strike, x=x):
            # la IV puede venir sin su strike (el agregador no siempre lo trae): se imprime la IV y se calla el
            # strike, en vez de romper la emisión entera por una nota al pie
            if valor is None:
                return _na(x.motivo or "sin contrato con volatilidad implícita válida")
            return Celda(pct(valor, 1), "", "Hd", "valor", f"precio de ejercicio {numero(strike, 2)}" if strike is not None else "sin precio de ejercicio declarado")
        sesgo = x.sesgo
        celdas = [_hd(numero(x.subyacente, 2)), _iv(x.iv_call_atm, x.strike_atm), _iv(x.iv_put_atm, x.strike_atm), _iv(x.iv_put_otm, x.strike_put_otm), _iv(x.iv_call_otm, x.strike_call_otm),
                  Celda(f"{'+' if sesgo > 0 else ''}{numero(sesgo * 100, 1)} p.p.", "∑", "D", "negativo" if sesgo < 0 else "valor",
                        f"VI put {numero(x.strike_put_otm, 0) if x.strike_put_otm is not None else 'fuera del dinero'} − "
                        f"VI call {numero(x.strike_call_otm, 0) if x.strike_call_otm is not None else 'fuera del dinero'} = "
                        f"{pct(x.iv_put_otm, 1)} − {pct(x.iv_call_otm, 1)}") if sesgo is not None else _na("sin las dos volatilidades implícitas fuera del dinero"),
                  Celda("sí" if x.contraste_oi and x.contraste_oi[0] is Contraste.CONFIRMADO else ("no" if x.contraste_oi and x.contraste_oi[0] is Contraste.DISCREPANTE else "—"), "", "",
                        "negativo" if x.contraste_oi and x.contraste_oi[0] is Contraste.DISCREPANTE else "valor", x.contraste_oi[1] if x.contraste_oi else "")]
        filas.append(FilaCuadro(f_fecha(x.fecha), celdas, capa="Hd"))
    hora = f", precio del subyacente según el agregador a las {v.hora_precio:%H:%M} (hora local)" if v.hora_precio else ""
    return Cuadro(n.siguiente(), "Volatilidad implícita por vencimiento y sesgo put-call",
                  ["Subyacente (USD)", "VI call en el dinero", "VI put en el dinero", "VI put 90 %", "VI call 110 %", "Sesgo put − call", "Interés abierto cuadra con la bolsa"], filas,
                  f"Fuente: {v.fuente}{hora}. La bolsa (Nasdaq) no publica la volatilidad implícita; el analista autorizó Yahoo Finance como excepción provisional (17/09/2026). "
                  "VI: volatilidad implícita. En el dinero: el precio de ejercicio más cercano al subyacente; 90 % y 110 %: los más cercanos a esos niveles. "
                  "El sesgo es VI put 90 % − VI call 110 %. «Interés abierto cuadra con la bolsa»: el interés abierto total del vencimiento según el "
                  "agregador frente al de la bolsa (cuadro de la cadena), dentro del 2 %; cuando no cuadra, la VI de ese vencimiento no se imprime.", partible=True)


def cuadros_comparables(n: Cuadros, c) -> Optional[Cuadro]:
    """Apartado 22: los valores de la misma industria según la bolsa, con múltiplos ∑ sobre sus cuentas de la SEC."""
    if c is None or not c.filas:
        return None
    filas = []
    for x in c.filas:
        cuentas = f"{x.formulario} al {f_fecha(x.cierre)}" if x.cierre else ""
        celdas = [_hd(x.pais or "—"),
                  Celda(numero(x.capitalizacion / 1e6), "", "Hd", "valor", "capitalización del screener de la bolsa, USD") if x.capitalizacion else _na("sin capitalización en el screener"),
                  Celda(numero(x.ingresos / 1e6), "", "H", "valor", f"{cuentas}, SEC EDGAR, {x.moneda}") if x.ingresos is not None else _na(x.nota_sec or "sin cuentas"),
                  Celda(numero(x.beneficio / 1e6), "", "H", "negativo" if (x.beneficio or 0) < 0 else "valor", f"{cuentas}, SEC EDGAR, {x.moneda}") if x.beneficio is not None else _na(x.nota_sec or "sin cuentas"),
                  Celda(veces(x.p_ventas, 2), "∑", "D", "valor", f"{numero(x.capitalizacion / 1e6)} / {numero(x.ingresos / 1e6)}") if x.p_ventas is not None else _na(x.nota_sec or ("beneficio negativo" if x.beneficio is not None and x.beneficio <= 0 else "sin cuentas en USD")),
                  Celda(veces(x.per, 1), "∑", "D", "valor", f"{numero(x.capitalizacion / 1e6)} / {numero(x.beneficio / 1e6)}") if x.per is not None else _na("beneficio negativo o nulo: PER no definido" if x.beneficio is not None and x.beneficio <= 0 else (x.nota_sec or "sin cuentas en USD")),
                  Celda(f"{x.moneda} · {cuentas}" if cuentas else "—", "", "H", "valor" if cuentas else "na", x.nota_sec)]
        filas.append(FilaCuadro(f"{x.ticker} · {x.nombre}", celdas, capa="Hd", destacada=(x.ticker == c.ticker)))
    hora = c.obtenido.strftime("%d/%m/%Y %H:%M") if c.obtenido else ""
    return Cuadro(n.siguiente(), f"Comparables según la clasificación de la bolsa: industria «{c.industria}» (sector {c.sector})",
                  ["País", "Capitalización (M USD)", "Ingresos anuales (M)", "Beneficio neto (M)", "P/Ventas", "PER", "Cuentas"], filas,
                  f"Fuente: screener de Nasdaq (clasificación sectorial, capitalización y país), consultado el {hora}; cuentas del último ejercicio anual de cada valor "
                  "en SEC EDGAR (formulario y cierre en cada celda). P/Ventas y PER = capitalización / cuentas anuales, solo con cuentas en USD. "
                  "La clasificación es de la bolsa: el 10-K no nombra competidores concretos (texto del apartado).", partible=True)


def _fila_comparable(x, propio: bool) -> FilaCuadro:
    cuentas = f"{x.formulario} al {f_fecha(x.cierre)}" if x.cierre else ""
    celdas = [_hd(x.pais or "—"),
              Celda(numero(x.capitalizacion / 1e6), "", "Hd", "valor", "capitalización del screener de la bolsa, USD") if x.capitalizacion else _na("sin capitalización en el screener de la bolsa"),
              Celda(numero(x.ingresos / 1e6), "", "H", "valor", f"{cuentas}, SEC EDGAR, {x.moneda}") if x.ingresos is not None else _na(x.nota_sec or "sin cuentas"),
              Celda(numero(x.beneficio / 1e6), "", "H", "negativo" if (x.beneficio or 0) < 0 else "valor", f"{cuentas}, SEC EDGAR, {x.moneda}") if x.beneficio is not None else _na(x.nota_sec or "sin cuentas"),
              Celda(veces(x.p_ventas, 2), "∑", "D", "valor", f"{numero(x.capitalizacion / 1e6)} / {numero(x.ingresos / 1e6)}") if x.p_ventas is not None else _na(x.nota_sec or ("beneficio negativo" if x.beneficio is not None and x.beneficio <= 0 else "sin cuentas en USD")),
              Celda(veces(x.per, 1), "∑", "D", "valor", f"{numero(x.capitalizacion / 1e6)} / {numero(x.beneficio / 1e6)}") if x.per is not None else _na("beneficio negativo o nulo: PER no definido" if x.beneficio is not None and x.beneficio <= 0 else (x.nota_sec or "sin cuentas en USD")),
              Celda(f"{x.moneda} · {cuentas}" if cuentas else "—", "", "H", "valor" if cuentas else "na", x.nota_sec)]
    return FilaCuadro(f"{x.ticker} · {x.nombre}", celdas, capa="Hd", destacada=propio)


def cuadro_comparables_sic(n: Cuadros, c) -> Optional[Cuadro]:
    """Apartado 22, segunda clasificación oficial: los emisores que la SEC agrupa en el mismo código SIC."""
    if c is None or not c.sic:
        return None
    filas = [_fila_comparable(x, True) for x in c.filas[:1]] + [_fila_comparable(x, False) for x in c.filas_sic]
    if not c.filas_sic:
        return None
    en_ambas = sorted({x.ticker for x in c.filas_sic} & {x.ticker for x in c.filas[1:]})
    return Cuadro(n.siguiente(), f"Comparables según la clasificación de la SEC: SIC {c.sic} «{c.sic_descripcion}»",
                  ["País", "Capitalización (M USD)", "Ingresos anuales (M)", "Beneficio neto (M)", "P/Ventas", "PER", "Cuentas"], filas,
                  f"Fuente: búsqueda de emisores por SIC en EDGAR (solo los que tienen ticker en la lista oficial de la SEC), capitalización y país del screener de Nasdaq, "
                  f"cuentas del último ejercicio anual en SEC EDGAR. "
                  + (f"Coinciden con la clasificación de la bolsa: {', '.join(en_ambas)}. " if en_ambas else "Ningún valor coincide con la clasificación de la bolsa. ")
                  + "Ni la SEC ni la bolsa publican competidores: publican clasificaciones.", partible=True)


def cuadro_mercado_objetivo(n: Cuadros, m) -> Optional[Cuadro]:
    """Apartado 21: TAM · SAM · SOM con las cifras que la compañía declara, cada una con su frase, documento y página."""
    if m is None or not m.declaraciones:
        return None
    filas = []
    for d in m.declaraciones:
        if d.unidad == "%":
            valor = pct(d.valor / 100, 0)
        elif d.unidad == "USD":
            valor = f"{numero(d.valor / 1e6)} M USD"
        else:
            valor = f"{numero(d.valor / 1e6)} M {d.unidad}"
        fuente = f"{d.cita.origen.documento}, pág. {d.cita.origen.pagina}" if d.cita else "sección C (hecho contrastado con la SEC)"
        filas.append(FilaCuadro(d.concepto, [Celda(d.clase, "", "D", "valor", d.motivo), Celda(valor, "", d.capa, "valor", d.cita.texto if d.cita else ""),
                                             Celda(fuente, "", "", "valor", d.cita.texto if d.cita else "")], capa=d.capa))
    return Cuadro(n.siguiente(), "Tamaño de mercado según lo declarado por la compañía: TAM · SAM · SOM",
                  ["Clasificación", "Cifra", "Fuente (documento oficial, página)"], filas,
                  "Fuente: frases literales de la dirección en los documentos adjuntos (al pasar el ratón, la frase); los ingresos, hecho contrastado con la SEC. "
                  "Ningún documento usa las etiquetas TAM/SAM/SOM: la clasificación es una inferencia del sistema y su motivo se lee al pasar el ratón. Nada se estima.")
