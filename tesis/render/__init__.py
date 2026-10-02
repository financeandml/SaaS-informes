"""De los datos del informe al HTML autocontenido y al PDF.

Una sola plantilla (Jinja2) produce el HTML; el PDF se imprime de ese mismo HTML
con el Chromium de Playwright, que ya está instalado en la máquina y pagina CSS
mejor que las alternativas sin navegador. No hay dos maquetas que puedan
discrepar: lo que se ve en pantalla es lo que se imprime.

El HTML es autocontenido —CSS incrustado, recortes como `data:` URI— y declara
una CSP sin scripts: no hay JavaScript en el entregable.
"""

from __future__ import annotations

import base64
import hashlib
from pathlib import Path
from typing import TYPE_CHECKING, Dict, Optional

from .. import rutas

if TYPE_CHECKING:                   # solo para las anotaciones: `python -m tesis.render.imprimir` no carga el informe
    from ..plantillas.informe import Informe

__all__ = ["a_html", "a_pdf"]

MAQUETA = rutas.MAQUETA


def a_html(informe: Informe, casa: str = "Warrants & Co.") -> str:
    from jinja2 import Environment, FileSystemLoader, select_autoescape
    entorno = Environment(loader=FileSystemLoader(str(MAQUETA)), autoescape=select_autoescape(["html"]))
    from ..formato import numero, pct
    entorno.filters.update(numero=numero, pct_es=pct)         # es-ES y menos tipográfico (02), como el resto de cifras
    plantilla = entorno.get_template("tesis.html")
    css = (MAQUETA / "tesis.css").read_text(encoding="utf-8")
    recortes_datos: Dict[str, str] = {}

    def incrustar(ruta) -> None:
        if ruta and str(ruta) not in recortes_datos and Path(ruta).exists():
            datos = base64.b64encode(Path(ruta).read_bytes()).decode("ascii")
            recortes_datos[str(ruta)] = f"data:image/png;base64,{datos}"

    # toda imagen del informe viaja dentro del HTML: recortes de cuadros, evidencias de texto, retratos, riesgos, historial
    for cuadro in (informe.resultados, informe.balance, informe.flujo):
        for r in cuadro.recortes:
            incrustar(r.ruta)
    for lista in informe.evidencias.values():
        for r in lista:
            incrustar(r.ruta)
    if informe.narrativa is not None:
        for lista in informe.narrativa.evidencias.values():
            for r in lista:
                incrustar(r.ruta)
    for f in list(informe.fotos_ejecutivos) + list(informe.fotos_consejo):
        incrustar(f.ruta)
    for r in informe.riesgos_recortes:
        incrustar(r.ruta)
    if informe.historial_recorte is not None:
        incrustar(informe.historial_recorte.ruta)
    html = plantilla.render(i=informe, casa=casa, css=css, recortes_datos=recortes_datos)
    if getattr(informe.emisor, "mercado", "sec") != "sec":
        html = rotular_documentos(html, informe.expediente)
    return html


def rotular_documentos(html: str, exp) -> str:
    """Cada documento del expediente por lo que es y de cuándo («Cuentas anuales 31/12/2025»), no por el nombre del
    fichero que le da la bolsa («bme_2025_AN_118335.pdf»): un lector no sabe qué es lo segundo (fallo [68])."""
    import html as _html
    for a in sorted(getattr(exp, "adjuntos", []) or [], key=lambda a: -len(a.nombre)):
        cuando = a.periodo_fin or a.fecha
        rotulo = f"{a.tipo.value} {cuando:%d/%m/%Y}" if cuando else a.tipo.value
        html = html.replace(a.nombre, _html.escape(rotulo))
    return html


def _cabecera_pie(informe: Informe, casa: str) -> tuple:
    """Cabecera y pie que Chromium repite en cada página: casa, valor, fecha, borrador y numeración."""
    estilo = "font-family:'Segoe UI',Arial,sans-serif;font-size:7pt;color:#4a4a4a;width:100%;padding:0 14mm;"
    cabecera = (f"<div style=\"{estilo}display:flex;justify-content:space-between;align-items:flex-end;"
                f"border-bottom:2px solid #7a1f2b;padding-bottom:1.5mm;margin-top:6mm\">"
                f"<span style=\"font-weight:700;font-size:9pt;color:#1a1a1a;letter-spacing:.04em\">{casa}</span>"
                f"<span style=\"text-align:right\">Análisis · {informe.nombre}<br>{informe.fecha_emision:%d/%m/%Y} · "
                + (f"<b style=\"color:#1f5d3a\">EMITIDO {informe.emitido:%d/%m/%Y}</b>" if getattr(informe, "emitido", None)
                   else "<b style=\"color:#7a1f2b\">BORRADOR — NO EMITIDO</b>") + "</span></div>")
    pie = (f"<div style=\"{estilo}display:flex;justify-content:space-between;border-top:1px solid #d9d9d9;padding-top:1.5mm;margin-bottom:6mm\">"
           f"<span>© {informe.fecha_emision.year} {casa}</span><span>Análisis / {informe.nombre}</span>"
           f"<span>Página <span class=\"pageNumber\"></span> de <span class=\"totalPages\"></span></span></div>")
    return cabecera, pie


def a_pdf(html: str, salida_pdf: Path, salida_html: Optional[Path] = None, informe: Optional[Informe] = None,
          casa: str = "Warrants & Co.") -> str:
    """Imprime el HTML a PDF A4 con Chromium; devuelve la huella sha256 del PDF.

    La impresión corre en un proceso aparte (`tesis.render.imprimir`): el driver de
    Playwright no termina al cerrar en esta máquina y dejaba la orden colgada
    minutos después de escribir el PDF. El hijo anuncia «LISTO sha256» en cuanto
    el PDF está; si después no acaba solo en unos segundos, se le termina.
    """
    import os
    import subprocess
    import sys

    salida_pdf = Path(salida_pdf)
    salida_pdf.parent.mkdir(parents=True, exist_ok=True)
    ruta_html = Path(salida_html) if salida_html else salida_pdf.with_suffix(".html")
    ruta_html.write_text(html, encoding="utf-8")
    cabecera, pie = _cabecera_pie(informe, casa) if informe is not None else ("<span></span>", "<span></span>")
    ruta_cabecera, ruta_pie = salida_pdf.with_suffix(".cabecera.html"), salida_pdf.with_suffix(".pie.html")
    ruta_cabecera.write_text(cabecera, encoding="utf-8")
    ruta_pie.write_text(pie, encoding="utf-8")
    orden = [sys.executable, "-m", "tesis.render.imprimir", str(ruta_html), str(salida_pdf), str(ruta_cabecera), str(ruta_pie)]
    hijo = subprocess.Popen(orden, cwd=str(rutas.REPO), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                            encoding="utf-8", errors="replace")
    huella = ""
    try:
        for linea in hijo.stdout:
            if linea.startswith("LISTO "):
                huella = linea.split()[1].strip()
                break
        if not huella:
            _, err = hijo.communicate(timeout=60)
            raise RuntimeError(f"la impresión a PDF no terminó: {err.strip()[-800:]}")
        try:
            hijo.wait(timeout=10)
        except subprocess.TimeoutExpired:
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(hijo.pid), "/T", "/F"], capture_output=True)
            else:
                hijo.kill()
    finally:
        for f in (ruta_cabecera, ruta_pie):
            f.unlink(missing_ok=True)
    if huella != hashlib.sha256(salida_pdf.read_bytes()).hexdigest():
        raise RuntimeError("la huella del PDF no coincide con la anunciada por el proceso de impresión")
    return huella


def _cerrar_lista(informe: Informe, bloqueos) -> None:
    """El criterio «0 discrepancias y 0 bloqueos» de la lista de comprobación (28) con los de la puerta ya calculada: al
    construir el informe aún no estaban los que la puerta encuentra en el HTML (apartados pendientes, «N/A» donde no
    puede haberlo) y la lista, la hoja 0 y el log contaban cifras distintas (fallo [29])."""
    pg = getattr(informe, "parte_g", None)
    if pg is None:
        return
    discrepancias = sum(1 for b in bloqueos if b.startswith("Discrepancia abierta"))
    pg.cerrar(len(bloqueos) - discrepancias, discrepancias)


def emitir(informe: Informe, salida_pdf: Path, hoy=None, casa: str = "Warrants & Co.", pasadas: int = 2, prueba: bool = False):
    """La emisión de 06 §3–§4: puerta de calidad sobre el HTML, «EMITIDO dd/mm/aaaa» solo con 0 bloqueos (y nunca con
    entradas de prueba), hoja 0 con los bloqueos en el borrador y PDF paginado: si una página queda por debajo de
    `umbrales.relleno_pagina_min` sin ser fin de parte, el cuadro que abre la página siguiente se deja partir y se vuelve a
    imprimir (máximo `pasadas`). Un bloqueo que solo se ve al medir el PDF (maquetación desbordada) lo devuelve a borrador
    y se reimprime con su hoja 0. Devuelve (puerta, huella del PDF, HTML, relleno por página)."""
    import re
    from .. import qa
    from ..plantillas import puntos
    from ..umbrales import umbral
    html = a_html(informe, casa)
    puerta = qa.revisar(informe, html, hoy)
    _cerrar_lista(informe, puerta.bloqueos)
    informe.bloqueos_qa = list(puerta.bloqueos)
    informe.puntos_qa = puntos.resumen(puerta.puntos)              # hoja 0 y web: el estado de cada apartado, punto a punto
    informe.emitido = (hoy or informe.fecha_emision) if puerta.emitible and not prueba else None
    html = a_html(informe, casa)
    huella = a_pdf(html, salida_pdf, informe=informe, casa=casa)
    minimo = float(umbral("relleno_pagina_min"))
    for _ in range(pasadas):
        medidas = qa.relleno(Path(salida_pdf))
        bajas = [k for k, fraccion, fin in medidas if fraccion < minimo and not fin]
        textos = qa.paginas_de(Path(salida_pdf))
        nuevos = set()
        for k in bajas:                                   # k es 1-based: la página siguiente es textos[k]
            m = re.search(r"Cuadro (\d+)\.", textos[k][:600]) if k < len(textos) else None
            if m:
                nuevos.add(int(m.group(1)))
        if not nuevos - informe.partir:
            break
        informe.partir |= nuevos
        html = a_html(informe, casa)
        huella = a_pdf(html, salida_pdf, informe=informe, casa=casa)
    medidas = qa.relleno(Path(salida_pdf))
    bajas = [(k, fraccion) for k, fraccion, fin in medidas if fraccion < minimo and not fin]
    maximo = int(umbral("paginas_max"))
    if len(medidas) > maximo:
        # un PDF desbordado (Microsoft, 28/09/2026: un gráfico de 4,8 millones de puntos de alto dio 7.130 páginas) no es
        # un informe: se bloquea con una línea en vez de enterrar la puerta en miles de avisos de «página vacía»
        puerta.bloqueos.append(f"Maquetación desbordada: el PDF tiene {len(medidas)} páginas (máximo {maximo}); "
                               f"{len(bajas)} casi vacías, la primera la {bajas[0][0] if bajas else '—'}")
    else:
        puerta.avisos += [f"Página {k} ocupada al {fraccion:.0%} sin ser fin de parte" for k, fraccion in bajas]
    if puerta.bloqueos != informe.bloqueos_qa:
        # la cabecera, la hoja 0 y la puerta dicen lo mismo (regla 13): un PDF con un bloqueo no puede decir «EMITIDO»
        informe.bloqueos_qa = list(puerta.bloqueos)
        informe.emitido = None
        _cerrar_lista(informe, puerta.bloqueos)
        html = a_html(informe, casa)
        huella = a_pdf(html, salida_pdf, informe=informe, casa=casa)
        medidas = qa.relleno(Path(salida_pdf))
    return puerta, huella, html, medidas
