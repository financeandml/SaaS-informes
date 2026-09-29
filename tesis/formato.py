"""Cifras y fechas en convención española, y la celda que se imprime a partir de un hecho.

La única puerta por la que una cifra llega a la maqueta: `celda(hecho)`. No
acepta números sueltos, así que un `N/A` sale siempre rotulado `N/A` con su
motivo al pie, un cero sale `0` y no «—», y todo valor lleva su glifo de
contraste y su capa. Los costes y salidas se imprimen en negativo según
`signo_informe` del catálogo; el hecho guarda el valor con la convención de la
SEC (positivo), y el signo se decide aquí, en un solo sitio.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional

from .datos.campos import CAMPOS
from .datos.hechos import Capa, Contraste, Estado, Hecho

__all__ = ["Celda", "celda", "fecha", "mln", "numero", "pct", "veces"]

_SIGNO = {c.clave: c.signo_informe for c in CAMPOS}


def numero(v: float, decimales: int = 0) -> str:
    """es-ES (02): miles con punto, decimales con coma y signo menos tipográfico («−3.117»); sin «−0»."""
    s = f"{v:,.{decimales}f}".replace(",", " ").replace(".", ",").replace(" ", ".")
    if s.startswith("-"):
        return "−" + s[1:] if s.strip("-0.,") else s[1:]
    return s


def mln(v: float, decimales: int = 0) -> str:
    return numero(v / 1e6, decimales)


def pct(v: float, decimales: int = 1) -> str:
    return numero(v * 100, decimales) + " %"


def veces(v: float, decimales: int = 1) -> str:
    return numero(v, decimales) + "x"


def fecha(d: Optional[date]) -> str:
    return d.strftime("%d/%m/%Y") if d else ""


@dataclass(frozen=True)
class Celda:
    texto: str
    glifo: str
    capa: str
    clase: str          # «na» · «cero» · «valor» · «negativo»
    nota: str
    hecho: str = ""     # concepto de valor único (06 §3.3: precio, po, deuda_neta@fecha…); se imprime como data-hecho


def celda(h: Optional[Hecho], unidad: Optional[str] = None) -> Celda:
    """La celda imprimible de un hecho. Sin hecho, N/A con motivo «sin hecho»."""
    if h is None:
        return Celda("N/A", "", "", "na", "sin hecho para esta celda")
    if h.estado is Estado.NA:
        return Celda("N/A", h.contraste.value if h.contraste is not Contraste.SIN_CONTRASTAR else "", h.capa.value, "na", h.motivo)
    u = unidad or h.unidad
    v = h.valor * _SIGNO.get(h.campo, 1)
    if h.estado is Estado.CERO:
        texto = "0" if u not in ("%", "x") else ("0,0 %" if u == "%" else "0,0x")
        return Celda(texto, h.contraste.value, h.capa.value, "cero", h.nota or "cero declarado por la fuente")
    if u == "%":
        texto = pct(v)
    elif u == "x":
        texto = veces(v)
    elif u.endswith("/acción"):                  # USD/acción, EUR/acción: cifra por acción, con dos decimales
        texto = numero(v, 2)
    elif u == "acciones":
        texto = mln(v)
    elif u == "empleados":
        texto = numero(v)
    else:
        texto = mln(v)
    nota = h.nota
    if h.capa is Capa.DERIVADO and h.formula:
        nota = (h.formula + (" · " + nota if nota else ""))
    # 06 §3.3: la deuda neta de una fecha es una sola en todo el informe (cuadro 1, balance, puente)
    unico = f"deuda_neta@{h.periodo.fin.isoformat()}" if h.campo == "deuda_neta" and h.periodo.es_instante else ""
    return Celda(texto, h.contraste.value, h.capa.value, "negativo" if v < 0 else "valor", nota, unico)
