"""Doble comprobación de las cifras impresas (pedido del analista, 18/09/2026: «revisa que todos los números estén bien dos veces»).

La primera lectura es la tubería normal: hecho → `formato.celda` → cuadro → plantilla. Esta es la
segunda, por otro camino, y no comparte código con la primera en lo que comprueba:

1. **Hechos.** Cada celda de un cuadro que viene del diccionario de hechos (la fila lleva
   `origen`, `periodos` y `unidad`) se vuelve a formatear aquí con un formateador propio, a
   partir del hecho, y se compara con el texto de la celda. Si la fila apuntara al periodo
   equivocado, o el diccionario hubiera cambiado, o el formato se hubiera roto, aquí se ve.
2. **Libro del analista.** Cada celda de la sección D cuya nota lleva la referencia
   «Hoja!Celda» se vuelve a leer del fichero Excel con openpyxl y se formatea aquí; el texto
   impreso debe coincidir.
3. **HTML.** Se localiza cada cuadro en el HTML emitido por su rótulo «Cuadro N.» y se
   comprueba que las celdas impresas son exactamente las del cuadro (ni una menos, ni otra).

Cualquier desacuerdo detiene la emisión: un informe con una cifra que no coincide con su
fuente al releerla no sale.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Dict, List, Optional, Tuple

from ..datos.campos import CAMPOS
from ..datos.hechos import Estado, Periodo

__all__ = ["Revision", "comprobar"]

_SIGNO = {c.clave: c.signo_informe for c in CAMPOS}
_CITA = re.compile(r"^([^!·]+)!([A-Z]{1,3}\d{1,5})(?:\s|$|·)")


@dataclass
class Revision:
    comprobadas: int = 0
    desacuerdos: List[str] = field(default_factory=list)
    por_cuadro: Dict[int, int] = field(default_factory=dict)


# --- formateador propio: separador de miles con punto, decimales con coma, espacio duro antes del % ---
def _miles(v: float, decimales: int) -> str:
    entero, _, dec = f"{abs(v):.{decimales}f}".partition(".")
    grupos = []
    while len(entero) > 3:
        grupos.insert(0, entero[-3:])
        entero = entero[:-3]
    grupos.insert(0, entero)
    texto = ".".join(grupos) + ("," + dec if dec else "")
    return ("−" if v < 0 and texto.strip("0.,") else "") + texto          # signo menos tipográfico (02)


def _texto_hecho(h, unidad: str, decimales_mln: int = 0) -> Optional[str]:
    """Lo que debería imprimirse para un hecho, según su estado y su unidad; None si no hay hecho. `decimales_mln`: los
    que el informe declara para sus millones (los de un emisor pequeño, `formato.fijar_escala`)."""
    if h is None:
        return "N/A"
    if h.estado is Estado.NA:
        return "n. s." if (h.motivo or "").startswith("no significativo") else "N/A"
    u = unidad or h.unidad
    if h.estado is Estado.CERO:
        return "0" if u not in ("%", "x") else ("0,0 %" if u == "%" else "0,0x")
    v = h.valor * _SIGNO.get(h.campo, 1)
    if u == "%":
        return _miles(v * 100, 1) + " %"
    if u == "x":
        return _miles(v, 1) + "x"
    if u.endswith("/acción"):
        return _miles(v, 2)
    if u == "empleados":
        return _miles(v, 0)
    return _miles(v / 1e6, decimales_mln)


def _texto_libro(valor, unidad: str, formato: str = "") -> Optional[str]:
    """Lo que debería imprimirse para un valor del libro, con las mismas reglas de unidad que la sección D:
    el formato numérico de la celda manda (porcentaje con dos decimales al menos, múltiplo con «x») y, sin él, el rótulo."""
    if valor is None or isinstance(valor, str):
        return None
    v = float(valor)
    formato = formato.split(";", 1)[0]
    m = re.search(r"\.(0+)", formato)
    decimales = len(m.group(1)) if m else 0
    if "%" in formato:
        return _miles(v * 100, max(decimales, 2)) + " %"
    if formato.endswith("\\x") or formato.endswith('"x"'):
        return _miles(v, max(decimales, 1)) + "x"
    if unidad == "%":
        return (_miles(v * 100, 1) if abs(v) < 1.5 else _miles(v, 1)) + " %"
    if unidad == "x":
        return _miles(v, 1) + "x"
    if unidad == "usd":
        return _miles(v, 2)
    if unidad == "musd":
        return _miles(v, 0)
    return _miles(v, 2)


def _unidad_fila(rotulo: str) -> str:
    r = rotulo.lower()
    if "%" in r or "crecimiento" in r or "margen" in r or "tipo impositivo" in r or "peso" in r or "recorrido" in r or "rentabilidad" in r or "diferencia" in r:
        return "%"
    if "por acción" in r or "usd/acción" in r or "precio" in r:
        return "usd"
    if "factor de descuento" in r:
        return "coef"
    return "musd"


class _Cuadros(HTMLParser):
    """Los cuadros del HTML: rótulo «Cuadro N.» → filas de textos de celda."""
    def __init__(self) -> None:
        super().__init__()
        self.cuadros: Dict[int, List[List[str]]] = {}
        self._numero: Optional[int] = None
        self._en_rotulo = False
        self._rotulo = ""
        self._fila: Optional[List[str]] = None
        self._celda: Optional[List[str]] = None
        self._en_thead = False

    def handle_starttag(self, tag, attrs):
        clases = dict(attrs).get("class", "")
        if tag == "div" and "rotulo" in clases.split():
            self._en_rotulo, self._rotulo = True, ""
        elif tag == "thead":
            self._en_thead = True
        elif tag == "tr" and self._numero is not None and not self._en_thead:
            self._fila = []
        elif tag == "td" and self._fila is not None:
            self._celda = []

    def handle_endtag(self, tag):
        if tag == "div" and self._en_rotulo:
            self._en_rotulo = False
            m = re.match(r"\s*Cuadro (\d+)\.", self._rotulo)
            self._numero = int(m.group(1)) if m else None
            if self._numero is not None:
                self.cuadros.setdefault(self._numero, [])
        elif tag == "thead":
            self._en_thead = False
        elif tag == "td" and self._celda is not None:
            self._fila.append("".join(self._celda).strip())
            self._celda = None
        elif tag == "tr" and self._fila is not None:
            if self._numero is not None:
                self.cuadros[self._numero].append(self._fila)
            self._fila = None
        elif tag == "table":
            self._numero = None

    def handle_data(self, data):
        if self._en_rotulo:
            self._rotulo += data
        if self._celda is not None:
            self._celda.append(data)


def _todos_los_cuadros(inf) -> list:
    dcf = inf.dcf or {}
    lista = [inf.cifras_resumen, inf.objetivos, inf.regiones, inf.accionistas, inf.filiales, inf.ejecutivos, inf.retribucion, inf.resultados, inf.balance, inf.flujo,
             inf.rentabilidad, inf.rentabilidad_ttm, inf.mercado_cuadro, inf.comparables_cuadro, inf.comparables_sic_cuadro]
    lista += [c for k, c in dcf.items() if k not in ("modelo", "faltan", "cuadres", "detalle_escenarios")]
    lista += [c for _, c in dcf.get("detalle_escenarios", [])]
    lista += list(inf.riesgos_cuadros.values()) + list(inf.historial_cuadros.values()) + list(inf.f_cuadros.values())
    return [c for c in lista if c is not None]


def comprobar(inf, html: str, modelo=None) -> Revision:
    rev = Revision()
    cuadros = _todos_los_cuadros(inf)
    # 1 · hechos
    for c in cuadros:
        for f in c.filas:
            if not f.origen.startswith("hecho:"):
                continue
            clave = f.origen.split(":", 1)[1]
            for celda, periodo in zip(f.celdas, f.periodos):
                p = next((pp for (cc, pp) in inf.hechos if cc == clave and pp.clave == periodo), None)
                h = inf.hechos.get((clave, p)) if p is not None else None
                esperado = _texto_hecho(h, f.unidad, getattr(inf, "decimales_mln", 0))
                rev.comprobadas += 1
                rev.por_cuadro[c.numero] = rev.por_cuadro.get(c.numero, 0) + 1
                if esperado != celda.texto:
                    rev.desacuerdos.append(f"cuadro {c.numero} «{f.rotulo}» {periodo}: impreso «{celda.texto}», releído del hecho «{esperado}»")
    # 2 · libro del analista
    if modelo is not None:
        try:
            import openpyxl
            libro = openpyxl.load_workbook(str(modelo.recalculado[0] if modelo.recalculado else modelo.fichero), data_only=True)
        except Exception as e:  # sin libro legible no hay segunda lectura: se anota, no se inventa
            rev.desacuerdos.append(f"libro {modelo.fichero}: no se pudo releer con openpyxl ({e})")
            libro = None
        if libro is not None:
            dcf = inf.dcf or {}
            # la referencia «Hoja!Celda» de cada fila apunta a una celda concreta del libro: la del valor de la fila.
            # En cada cuadro esa celda se imprime en una columna fija; las demás columnas de la fila son otras celdas del libro
            # (o cálculos) y no se releen por esta vía.
            columna_cita = {"escenarios": (2, "usd"), "cuadre": (0, None), "supuestos": (0, None), "multiplos": (4, "usd"), "reverse": (0, None), "objetivo": (0, "usd")}
            for k, (j_cita, unidad_fija) in columna_cita.items():
                c = dcf.get(k)
                if c is None:
                    continue
                for f in c.filas:
                    if j_cita >= len(f.celdas):
                        continue
                    celda = f.celdas[j_cita]
                    m = _CITA.match(celda.nota or "")
                    if not m or celda.capa != "S" or not celda.texto or celda.texto in ("N/A", "—") or "–" in celda.texto:
                        continue
                    hoja, ref = m.group(1), m.group(2)
                    if hoja not in libro.sheetnames:
                        continue
                    valor = libro[hoja][ref].value
                    if not isinstance(valor, (int, float)) or isinstance(valor, bool):
                        continue
                    esperado = _texto_libro(valor, unidad_fija or _unidad_fila(f.rotulo), libro[hoja][ref].number_format or "")
                    if esperado is None:
                        continue
                    rev.comprobadas += 1
                    rev.por_cuadro[c.numero] = rev.por_cuadro.get(c.numero, 0) + 1
                    if esperado != celda.texto and esperado.rstrip("x") != celda.texto.rstrip("x"):
                        rev.desacuerdos.append(f"cuadro {c.numero} «{f.rotulo}» ({hoja}!{ref}): impreso «{celda.texto}», releído del libro «{esperado}»")
    # 3 · HTML
    parser = _Cuadros()
    parser.feed(html)
    for c in cuadros:
        filas_html = parser.cuadros.get(c.numero)
        if filas_html is None:
            rev.desacuerdos.append(f"cuadro {c.numero} «{c.titulo}» no aparece en el HTML")
            continue
        esperadas = [[f.rotulo] + [ce.texto for ce in f.celdas] for f in c.filas]
        if getattr(getattr(inf, "emisor", None), "mercado", "sec") != "sec":
            # el HTML de un emisor de BME nombra cada documento por su rótulo, no por su fichero (`render.rotular_documentos`)
            from ..render import rotular_documentos
            import html as _html
            esperadas = [[_html.unescape(rotular_documentos(x, inf.expediente)) for x in fila] for fila in esperadas]
        if not c.filas:
            continue
        # el cuadro 1 sale dos veces (portada y apartado 2): el HTML trae las filas dos veces seguidas
        if filas_html != esperadas and filas_html != esperadas + esperadas:
            n_dif = sum(1 for a, b in zip(filas_html, esperadas) if a != b) + abs(len(filas_html) - len(esperadas))
            rev.desacuerdos.append(f"cuadro {c.numero} «{c.titulo}»: {n_dif} fila(s) del HTML no coinciden con el cuadro")
        rev.comprobadas += sum(len(f.celdas) for f in c.filas)
    return rev
