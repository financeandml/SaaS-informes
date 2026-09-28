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

from ..datos.hechos import Hecho, Periodo

__all__ = ["barras_con_linea", "tarta", "dispersion", "matriz_riesgos", "PALETA", "MARINO", "OCRE", "ESCALA"]

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
    # con valores negativos (caja neta: deuda neta < 0) el eje baja de cero. Antes empezaba siempre en 0: las cifras de
    # las barras negativas quedaban fuera, el recorte «tight» las incluía y el gráfico medía 4,8 millones de puntos de
    # alto, que el PDF convertía en 7.130 páginas en blanco (Microsoft, 28/09/2026)
    arriba, abajo = max(alturas + [0]), min(alturas + [0])
    rango = (arriba - abajo) or 1.0
    colores = [MARINO if h.hay_dato else PAPEL for h in barras]
    bordes = [MARINO if h.hay_dato else GRIS for h in barras]
    ax.bar(xs, alturas, color=colores, edgecolor=bordes, linewidth=0.6, width=0.6, label=rotulo_barras, zorder=2)
    if abajo < 0:
        ax.axhline(0, color=TINTA, linewidth=0.6, zorder=3)
    for x, h in zip(xs, barras):
        if h.hay_dato:
            # la cifra va dentro de la barra, en blanco sobre el marino; en una barra baja no cabe y sale fuera, en tinta
            v = h.valor / 1e6
            alta = abs(v) > rango * 0.18
            hacia = 1 if v >= 0 else -1
            y = v - hacia * rango * 0.02 if alta else v + hacia * rango * 0.01
            va = ("top" if hacia > 0 else "bottom") if alta else ("bottom" if hacia > 0 else "top")
            ax.text(x, y, _millones(h.valor).replace("-", "−"), ha="center", va=va, fontsize=6.5, color=PAPEL if alta else TINTA, zorder=4)
        else:
            ax.text(x, 0, "N/A", ha="center", va="bottom", fontsize=6.5, color=GRIS)
            avisos.append(f"{rotulo_barras} {h.periodo.clave}: {h.motivo}")
    ax.set_xticks(xs, etiquetas)
    ax.set_ylabel("mln USD")
    ax.tick_params(axis="y", labelsize=6.5)
    ax.yaxis.grid(True, color=GRIS_CLARO, linewidth=0.4)
    ax.set_axisbelow(True)
    ax.set_ylim(abajo - (rango * 0.18 if abajo < 0 else 0), arriba + (rango * 0.18 if arriba > 0 else 0))
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


def dispersion(puntos: Sequence[Tuple[str, float, float, bool]], rotulo_x: str, rotulo_y: str) -> str:
    """Dispersión rotulada (crecimiento frente a margen): cada punto con su nombre; la compañía, en marino y mayor.
    `puntos`: (nombre, x, y, es_la_compania) en tanto por uno. Sin dos puntos, no se dibuja."""
    if len(puntos) < 2:
        return ""
    plt = _matplotlib()
    fig, ax = plt.subplots(figsize=(4.2, 2.6), dpi=100)
    for nombre, x, y, propia in puntos:
        ax.scatter([x * 100], [y * 100], s=46 if propia else 26, color=MARINO if propia else ESCALA[2], zorder=3,
                   edgecolors=PAPEL, linewidths=0.6)
        ax.annotate(nombre, (x * 100, y * 100), textcoords="offset points", xytext=(4, 3), fontsize=6.5,
                    color=TINTA if propia else TINTA_SUAVE, fontweight="bold" if propia else "normal")
    ax.axhline(0, color=GRIS_CLARO, linewidth=0.6, zorder=1)
    ax.axvline(0, color=GRIS_CLARO, linewidth=0.6, zorder=1)
    ax.set_xlabel(rotulo_x)
    ax.set_ylabel(rotulo_y)
    ax.xaxis.set_major_formatter(lambda v, _: f"{v:.0f} %")
    ax.yaxis.set_major_formatter(lambda v, _: f"{v:.0f} %")
    ax.grid(color=GRIS_CLARO, linewidth=0.4, zorder=0)
    return _svg(fig)


def matriz_riesgos(puntos: Sequence[Tuple[int, int, int]]) -> str:
    """Matriz probabilidad × impacto (1–5 × 1–5): cada riesgo, su número en la celda; las celdas, más oscuras cuanto
    mayor el producto. `puntos`: (número del riesgo, probabilidad, impacto)."""
    if not puntos:
        return ""
    plt = _matplotlib()
    fig, ax = plt.subplots(figsize=(2.6, 2.4), dpi=100)
    for p in range(1, 6):
        for i in range(1, 6):
            ax.add_patch(plt.Rectangle((p - 0.5, i - 0.5), 1, 1, facecolor=ESCALA[4 - min(4, (p * i - 1) // 5)], alpha=0.45,
                                       edgecolor=PAPEL, linewidth=1))
    por_celda: Dict[Tuple[int, int], List[int]] = {}
    for n, p, i in puntos:
        por_celda.setdefault((p, i), []).append(n)
    for (p, i), numeros in por_celda.items():
        ax.text(p, i, " · ".join(str(x) for x in numeros), ha="center", va="center", fontsize=7, color=TINTA, fontweight="bold")
    ax.set_xlim(0.5, 5.5)
    ax.set_ylim(0.5, 5.5)
    ax.set_xticks(range(1, 6))
    ax.set_yticks(range(1, 6))
    ax.set_xlabel("Probabilidad")
    ax.set_ylabel("Impacto")
    ax.set_aspect("equal")
    return _svg(fig)
