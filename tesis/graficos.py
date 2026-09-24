"""Gráficos del informe, en SVG incrustado: el mismo dibujo en pantalla y en papel.

Se dibujan con matplotlib sin interfaz y se devuelven como cadena SVG. Reglas:

- **El color nunca es el único portador**: cada barra lleva su cifra y cada
  serie su rótulo; en blanco y negro se lee igual.
- **Ningún gráfico se dibuja con huecos tapados**: un periodo N/A no aparece
  como cero; aparece como hueco con su marca, o el gráfico no se dibuja y el
  informe lo dice.
- **Rótulo y leyenda salen de los mismos hechos que la tabla**: el gráfico
  recibe `Hecho`s, no números, y quien lo llama no puede pasarle otra cosa.
- **La paleta de los gráficos es propia y única** (`PALETA`): el granate de la
  maqueta se queda en la plantilla —cabeceras, cuadros, rótulos— y no entra en
  ningún gráfico. Hay una prueba que afirma que el SVG no usa otros colores.
"""

from __future__ import annotations

import io
from typing import Dict, List, Optional, Sequence, Tuple

from .hechos import Hecho, Periodo

__all__ = ["barras_con_linea", "tarta", "PALETA", "MARINO", "OCRE", "ESCALA"]

TINTA = "#1a1a1a"
TINTA_SUAVE = "#4a4a4a"
GRIS = "#8a8a8a"
GRIS_CLARO = "#d9d9d9"
PAPEL = "#ffffff"

# Paleta corporativa de los gráficos (decisión del analista, 17/09/2026). Azul marino
# para la serie principal, ocre para la medida secundaria —dos tonos que se separan
# también con visión alterada del color (ΔE OKLab ≥ 30 en protan y deutan)— y, para los
# repartos, una escala de un solo tono de oscuro a claro, ordenada por tamaño: los cuatro
# primeros pasos guardan ≥ 2:1 de contraste con el papel; los dos últimos solo salen con
# más de cuatro partes y siempre con su rótulo y su porcentaje encima.
MARINO = "#1c3760"
OCRE = "#b07d1e"
ESCALA = ["#1c3760", "#3f6390", "#7393b9", "#a3b8d3", "#cdd9e8", "#e8eef5"]
PALETA = (MARINO, OCRE, *ESCALA)
# lo que además puede aparecer en un SVG: tinta de textos y ejes, rejilla y papel
NEUTROS = (TINTA, TINTA_SUAVE, GRIS, GRIS_CLARO, PAPEL)


def _matplotlib():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({
        "font.family": "sans-serif", "font.size": 7.5, "axes.edgecolor": GRIS, "axes.linewidth": 0.5,
        "axes.spines.top": False, "axes.spines.right": False, "xtick.color": TINTA, "ytick.color": TINTA,
        "text.color": TINTA, "axes.labelcolor": TINTA, "svg.fonttype": "none",
    })
    return plt


def _svg(fig) -> str:
    buf = io.StringIO()
    fig.savefig(buf, format="svg", bbox_inches="tight")
    import matplotlib.pyplot as plt
    plt.close(fig)
    s = buf.getvalue()
    return s[s.index("<svg"):]


def _millones(v: float) -> str:
    return f"{v / 1e6:,.0f}".replace(",", ".")


def barras_con_linea(barras: Sequence[Hecho], linea: Sequence[Optional[Hecho]], rotulo_barras: str, rotulo_linea: str,
                     etiquetas: Sequence[str], unidad_linea: str = "%") -> Tuple[str, List[str]]:
    """Barras (mln USD) y, encima, la línea (porcentaje o múltiplo) en su propio panel. Devuelve (svg, avisos).

    Dos medidas de escala distinta no comparten eje: la línea va en un panel superior con
    el mismo eje de periodos, cada punto con su cifra, y así nunca se cruza con las barras
    ni con sus rótulos. Sin ningún dato para la línea, solo se dibujan las barras.
    """
    plt = _matplotlib()
    avisos: List[str] = []
    hay_linea = any(l is not None and l.hay_dato for l in linea)
    if hay_linea:
        fig, (ax_l, ax) = plt.subplots(2, 1, figsize=(3.4, 2.4), dpi=100, sharex=True,
                                       gridspec_kw={"height_ratios": [0.85, 2.0], "hspace": 0.1})
    else:
        fig, ax = plt.subplots(figsize=(3.4, 2.1), dpi=100)
        ax_l = None
    xs = list(range(len(barras)))
    alturas = [h.valor / 1e6 if h.hay_dato else 0 for h in barras]
    tope = max(alturas + [1]) * 1.18
    colores = [MARINO if h.hay_dato else PAPEL for h in barras]
    bordes = [MARINO if h.hay_dato else GRIS for h in barras]
    ax.bar(xs, alturas, color=colores, edgecolor=bordes, linewidth=0.6, width=0.6, label=rotulo_barras, zorder=2)
    for x, h in zip(xs, barras):
        if h.hay_dato:
            # la cifra va dentro de la barra, en blanco sobre el marino; en una barra baja no cabe y sale encima, en tinta
            alta = h.valor / 1e6 > tope * 0.18
            ax.text(x, h.valor / 1e6 - (tope * 0.02 if alta else -tope * 0.01), _millones(h.valor), ha="center",
                    va="top" if alta else "bottom", fontsize=6.5, color=PAPEL if alta else TINTA, zorder=4)
        else:
            ax.text(x, 0, "N/A", ha="center", va="bottom", fontsize=6.5, color=GRIS)
            avisos.append(f"{rotulo_barras} {h.periodo.clave}: {h.motivo}")
    ax.set_xticks(xs, etiquetas)
    ax.set_ylabel("mln USD")
    ax.tick_params(axis="y", labelsize=6.5)
    ax.yaxis.grid(True, color=GRIS_CLARO, linewidth=0.4)
    ax.set_axisbelow(True)
    ax.set_ylim(0, tope)
    asas, nombres = ax.get_legend_handles_labels()
    if hay_linea:
        ys = [l.valor * (100 if unidad_linea == "%" else 1) if (l is not None and l.hay_dato) else None for l in linea]
        xs_ok = [x for x, y in zip(xs, ys) if y is not None]
        ys_ok = [y for y in ys if y is not None]
        ax_l.plot(xs_ok, ys_ok, color=OCRE, marker="o", markersize=3.6, markeredgecolor=PAPEL, markeredgewidth=0.8,
                  linewidth=1.4, label=rotulo_linea, zorder=3)
        margen = (max(ys_ok) - min(ys_ok)) or abs(max(ys_ok)) or 1.0
        for x, y in zip(xs_ok, ys_ok):
            ax_l.text(x, y + margen * 0.18, (f"{y:.1f} %" if unidad_linea == "%" else f"{y:.1f}x").replace(".", ","), ha="center",
                      va="bottom", fontsize=6, color=TINTA, zorder=4)
        ax_l.set_ylim(min(ys_ok) - margen * 0.45, max(ys_ok) + margen * 0.9)
        # sin eje de valores: cada punto lleva su cifra y la leyenda su nombre; el eje solo estorbaría
        ax_l.set_yticks([])
        for lado in ("top", "right", "left"):
            ax_l.spines[lado].set_visible(False)
        ax_l.spines["bottom"].set_color(GRIS_CLARO)
        ax_l.tick_params(axis="x", length=0)
        a2, n2 = ax_l.get_legend_handles_labels()
        asas, nombres = asas + a2, nombres + n2
        for l, h in zip(linea, barras):
            if l is None or not l.hay_dato:
                avisos.append(f"{rotulo_linea} {h.periodo.clave}: sin dato")
    # dos series, una leyenda: el color no es el único portador del nombre de cada una
    ax.legend(asas, nombres, loc="upper center", bbox_to_anchor=(0.5, -0.16), ncol=2, frameon=False, fontsize=6.5,
              handlelength=1.2, columnspacing=1.2)
    return _svg(fig), avisos


def tarta(partes: Sequence[Tuple[str, Hecho]], titulo: str = "") -> Tuple[str, List[str]]:
    """Reparto en tarta con porcentaje y rótulo en cada porción; una escala de un solo tono, de mayor a menor."""
    plt = _matplotlib()
    avisos: List[str] = []
    validas = [(n, h) for n, h in partes if h.hay_dato and h.valor > 0]
    for n, h in partes:
        if not h.hay_dato:
            avisos.append(f"{n}: {h.motivo}")
    if not validas:
        return "", avisos + ["sin datos para la tarta"]
    fig, ax = plt.subplots(figsize=(3.0, 2.0), dpi=100)
    validas.sort(key=lambda par: par[1].valor, reverse=True)
    valores = [h.valor for _, h in validas]
    total = sum(valores)
    etiquetas = [f"{n}\n{v / total * 100:.0f} %".replace(".", ",") for (n, _), v in zip(validas, valores)]
    ax.pie(valores, labels=etiquetas, colors=ESCALA[:len(valores)], startangle=90, counterclock=False,
           wedgeprops={"edgecolor": PAPEL, "linewidth": 1.2}, textprops={"fontsize": 6.5, "color": TINTA})
    ax.set_aspect("equal")
    return _svg(fig), avisos
