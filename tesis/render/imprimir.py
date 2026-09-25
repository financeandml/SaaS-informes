"""Imprime un HTML a PDF con el Chromium de Playwright. Se ejecuta como proceso aparte.

    python -m tesis.render.imprimir informe.html informe.pdf cabecera.html pie.html

Es un proceso aparte a propósito: en esta máquina (Windows, Python 3.14, Playwright
1.61) `navegador.close()` no vuelve —ni con la API asíncrona ni con la síncrona—
aunque Chromium ya haya salido, y la orden se quedaba colgada minutos después de
escribir el PDF. Aquí el PDF se escribe, se anuncia por la salida estándar
(«LISTO sha256») y quien lanzó el proceso lo termina si no acaba solo.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path


def imprimir(ruta_html: Path, ruta_pdf: Path, cabecera: str, pie: str) -> str:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        navegador = p.chromium.launch()
        pagina = navegador.new_page()
        pagina.goto(ruta_html.resolve().as_uri(), wait_until="load")
        pagina.emulate_media(media="print")
        # outline=True: los títulos del HTML pasan al índice de marcadores del PDF; los enlaces internos del índice se conservan
        pagina.pdf(path=str(ruta_pdf), format="A4", print_background=True, prefer_css_page_size=True,
                   display_header_footer=True, header_template=cabecera, footer_template=pie, outline=True)
        # se anuncia antes de cerrar: es `navegador.close()` lo que no vuelve en esta máquina
        huella = hashlib.sha256(ruta_pdf.read_bytes()).hexdigest()
        print(f"LISTO {huella}", flush=True)
        navegador.close()
    return huella


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 4:
        print("uso: python -m tesis.render.imprimir informe.html informe.pdf cabecera.html pie.html", file=sys.stderr)
        return 2
    html, pdf, cabecera, pie = (Path(a) for a in argv)
    imprimir(html, pdf, cabecera.read_text(encoding="utf-8"), pie.read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
