"""Cifras y fechas en convención española, y la celda que se imprime a partir de un hecho.

La única puerta por la que una cifra llega a la maqueta: `celda(hecho)`. No
acepta números sueltos, así que un `N/A` sale siempre rotulado `N/A` con su
motivo al pie, un cero sale `0` y no «—», y todo valor lleva su glifo de
contraste y su capa. Los costes y salidas se imprimen en negativo según
`signo_informe` del catálogo; el hecho guarda el valor con la convención de la
SEC (positivo), y el signo se decide aquí, en un solo sitio.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from datetime import date
from typing import Optional

from .datos.campos import CAMPOS
from .datos.hechos import Capa, Contraste, Estado, Hecho

__all__ = ["Celda", "celda", "fecha", "mln", "numero", "pct", "veces"]

_SIGNO = {c.clave: c.signo_informe for c in CAMPOS}


def numero(v: float, decimales: int = 0) -> str:
    """es-ES (02): miles con punto, decimales con coma y signo menos tipográfico («−3.117»); sin «−0»."""
    # redondeo comercial (la mitad, hacia arriba) sobre el decimal que se lee, no sobre el binario: 9,95 ÷ 10 es en coma
    # flotante 0,99499…, y el BPA reexpresado de 0,995 se imprime 1,00, como lo redondea cualquiera (fallo [51])
    if math.isfinite(float(v)):
        v = Decimal(repr(round(float(v), 10))).quantize(Decimal(1).scaleb(-decimales), rounding=ROUND_HALF_UP)
    s = f"{v:,.{decimales}f}".replace(",", " ").replace(".", ",").replace(" ", ".")
    if s.startswith("-"):
        return "−" + s[1:] if s.strip("-0.,") else s[1:]
    return s


# decimales de las cifras en millones del informe en curso: los del tamaño del emisor (`fijar_escala`)
_DECIMALES_MLN = 0


def fijar_escala(ingresos: Optional[float]) -> int:
    """Los decimales con que se imprimen los millones según los ingresos del último ejercicio del emisor
    (`config/umbrales.yaml › mln_decimales`): en uno de 17 millones, «10,31» y no «10». None vuelve a cero."""
    global _DECIMALES_MLN
    _DECIMALES_MLN = 0
    if ingresos is not None:
        from .umbrales import umbral
        for tramo in umbral("mln_decimales") or []:
            if abs(ingresos) < float(tramo["hasta"]):
                _DECIMALES_MLN = int(tramo["decimales"])
                break
    return _DECIMALES_MLN


def mln(v: float, decimales: Optional[int] = None) -> str:
    return numero(v / 1e6, _DECIMALES_MLN if decimales is None else decimales)


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
        # hay dato, pero la ratio no significa nada (un denominador negativo): «n. s.», no un hueco
        texto = "n. s." if h.motivo.startswith("no significativo") else "N/A"
        return Celda(texto, h.contraste.value if h.contraste is not Contraste.SIN_CONTRASTAR else "", h.capa.value, "na", h.motivo)
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
