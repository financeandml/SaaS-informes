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
from typing import Dict, Optional

from .informe import Informe

__all__ = ["a_html", "a_pdf"]

MAQUETA = Path(__file__).resolve().parent / "maqueta"


def a_html(informe: Informe, casa: str = "Warrants & Co.") -> str:
    from jinja2 import Environment, FileSystemLoader, select_autoescape
    entorno = Environment(loader=FileSystemLoader(str(MAQUETA)), autoescape=select_autoescape(["html"]))
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
    return plantilla.render(i=informe, casa=casa, css=css, recortes_datos=recortes_datos)


def _cabecera_pie(informe: Informe, casa: str) -> tuple:
    """Cabecera y pie que Chromium repite en cada página: casa, valor, fecha, borrador y numeración."""
    estilo = "font-family:'Segoe UI',Arial,sans-serif;font-size:7pt;color:#4a4a4a;width:100%;padding:0 14mm;"
    cabecera = (f"<div style=\"{estilo}display:flex;justify-content:space-between;align-items:flex-end;"
                f"border-bottom:2px solid #7a1f2b;padding-bottom:1.5mm;margin-top:6mm\">"
                f"<span style=\"font-weight:700;font-size:9pt;color:#1a1a1a;letter-spacing:.04em\">{casa}</span>"
                f"<span style=\"text-align:right\">Análisis · {informe.nombre}<br>{informe.fecha_emision:%d/%m/%Y} · "
                f"<b style=\"color:#7a1f2b\">BORRADOR — NO EMITIDO</b></span></div>")
    pie = (f"<div style=\"{estilo}display:flex;justify-content:space-between;border-top:1px solid #d9d9d9;padding-top:1.5mm;margin-bottom:6mm\">"
           f"<span>© {informe.fecha_emision.year} {casa}</span><span>Análisis / {informe.nombre}</span>"
           f"<span>Página <span class=\"pageNumber\"></span> de <span class=\"totalPages\"></span></span></div>")
    return cabecera, pie


def a_pdf(html: str, salida_pdf: Path, salida_html: Optional[Path] = None, informe: Optional[Informe] = None,
          casa: str = "Warrants & Co.") -> str:
    """Imprime el HTML a PDF A4 con Chromium; devuelve la huella sha256 del PDF.

    La impresión corre en un proceso aparte (`tesis.imprimir`): el driver de
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
    orden = [sys.executable, "-m", "tesis.imprimir", str(ruta_html), str(salida_pdf), str(ruta_cabecera), str(ruta_pie)]
    hijo = subprocess.Popen(orden, cwd=str(Path(__file__).resolve().parents[1]), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
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
