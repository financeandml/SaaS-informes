"""Los recortes: la región exacta de la página de la que salió cada tabla, a PNG.

Un recorte es fichero + página + rectángulo → imagen con su huella. La región no
la elige nadie: es la que ocupan las filas que el contraste confirmó en esa
página, ampliada hasta el título del estado y la cabecera de columnas para que
la imagen se lea sola. Por eso el recorte prueba la cifra: la fila de donde
salió está dentro, y el pie dice de qué fichero y página.

Se recorta por página y no por celda a propósito: una cuenta de resultados
recortada entera es evidencia; treinta recortes de una celda cada uno son ruido.
El rectángulo de cada celda sigue guardado en su `Hecho.origen` para el tablero
del analista, que sí quiere señalar una cifra concreta.

Para hojas de cálculo no hay imagen: la referencia es la celda («Income
Statement!K9») y se imprime como tal.

Además de las tablas, dos recortes más, con la misma disciplina:
- `recortar_lineas`: la región de una página que contiene unas anclas de texto
  (las mismas anclas literales con que la narrativa cita la página), ampliada una
  línea por arriba y por abajo. Es la prueba visual de una frase.
- `extraer_imagen`: una imagen incrustada en la página (los retratos de la
  proxy), tal cual está en el documento, con su huella.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from ..verificacion.contraste import Resultado, Tablero
from .expediente import Adjunto, Expediente, Tipo
from .extractor import PaginaLeida
from .hechos import Contraste

__all__ = ["Recorte", "extraer_imagen", "recortar_evidencias", "recortar_lineas", "recortar_pagina", "retratos", "volcado_api"]

ESCALA_IMPRESION = 2.5     # 180 ppp sobre 72 pt: legible impreso y sin pesar más de lo necesario


@dataclass(frozen=True)
class Recorte:
    adjunto: str
    pagina: int
    rectangulo: Tuple[float, float, float, float]   # x0, y0, x1, y1 en puntos, origen abajo-izquierda
    ruta: Path
    huella: str
    pie: str
    alt: str
    campos: Tuple[str, ...]


def _rect_union(rects: Iterable[Tuple[float, float, float, float]]) -> Tuple[float, float, float, float]:
    rs = list(rects)
    return (min(r[0] for r in rs), min(r[1] for r in rs), max(r[2] for r in rs), max(r[3] for r in rs))


def recortar_pagina(adjunto: Adjunto, pagina: PaginaLeida, filas_rect: Sequence[Tuple[float, float, float, float]],
                    salida: Path, campos: Sequence[str], titulo_informe: str = "") -> Recorte:
    """Recorta desde el título del estado (o la cabecera de columnas) hasta la última fila usada."""
    import pypdfium2 as pdfium
    doc = pdfium.PdfDocument(str(adjunto.ruta))
    page = doc[pagina.numero - 1]
    ancho, alto = page.get_size()
    x0, y0, x1, y1 = _rect_union(filas_rect)
    # ampliar hacia arriba hasta la línea del título del estado, si está en la página
    tope = y1
    for k, l in enumerate(pagina.lineas[:8]):
        if pagina.titulo and l.texto.strip() == pagina.titulo.strip():
            tope = max(tope, l.y1)
            # la línea de encima del título suele ser el nombre de la compañía: entra si está pegada
            if k > 0 and pagina.lineas[k - 1].y0 - l.y1 < 30:
                tope = max(tope, pagina.lineas[k - 1].y1)
    if tope == y1:   # sin título reconocible: hasta la cabecera de años
        for l in pagina.lineas:
            if any(t.texto.strip().isdigit() and len(t.texto.strip()) == 4 for t in l.tokens) and l.y1 > y1:
                tope = max(tope, l.y1)
    margen = 14
    izq = max(0.0, min(x0, 30.0) - margen)
    der = min(ancho, max(x1, ancho - 30.0) + margen)
    abajo = max(0.0, y0 - margen)
    arriba = min(alto, tope + margen)
    crop = (izq, abajo, ancho - der, alto - arriba)   # pypdfium2: (izquierda, abajo, derecha, arriba) a recortar
    imagen = page.render(scale=ESCALA_IMPRESION, crop=crop).to_pil()
    salida.mkdir(parents=True, exist_ok=True)
    nombre = f"{adjunto.clave}_p{pagina.numero:03d}.png"
    ruta = salida / nombre
    imagen.save(ruta)
    huella = hashlib.sha256(ruta.read_bytes()).hexdigest()[:16]
    pie = f"Fuente: {adjunto.nombre}, pág. {pagina.numero}"
    if adjunto.fecha:
        pie += f" ({adjunto.tipo.value}, {adjunto.fecha:%d/%m/%Y})"
    alt = f"{pagina.titulo or 'Tabla'} de {adjunto.nombre}, página {pagina.numero}: " + ", ".join(campos)
    return Recorte(adjunto=adjunto.clave, pagina=pagina.numero, rectangulo=(izq, abajo, der, arriba), ruta=ruta,
                   huella=huella, pie=pie, alt=alt, campos=tuple(campos))


def recortar_evidencias(exp: Expediente, tablero: Tablero, salida: Path) -> Dict[Tuple[str, int], Recorte]:
    """Un recorte por (adjunto, página) con al menos una celda confirmada o derivada-confirmada."""
    por_pagina: Dict[Tuple[str, int], List[Resultado]] = {}
    por_clave = {a.clave: a for a in exp.adjuntos}
    for r in tablero.resultados:
        if r.evidencia is None or r.hecho.contraste not in (Contraste.CONFIRMADO, Contraste.DERIVADO, Contraste.SOLO_DOCUMENTO):
            continue
        adjunto = next((a for a in exp.adjuntos if a.nombre == r.evidencia.documento), None)
        if adjunto is None or adjunto.tipo is Tipo.XLSX:
            continue
        por_pagina.setdefault((adjunto.clave, r.evidencia.pagina), []).append(r)
    recortes: Dict[Tuple[str, int], Recorte] = {}
    for (clave, numero), resultados in por_pagina.items():
        adjunto = por_clave[clave]
        pagina = next((p for p in tablero.paginas.get(clave, []) if p.numero == numero), None)
        if pagina is None:
            continue
        rects = [r.evidencia.rect_fila for r in resultados]
        campos = sorted({r.campo.rotulo for r in resultados})
        recortes[(clave, numero)] = recortar_pagina(adjunto, pagina, rects, salida, campos)
    return recortes


# ---------------------------------------------------------------------------
# Recortes de texto (anclas) e imágenes incrustadas
# ---------------------------------------------------------------------------

def _normalizar(t: str) -> str:
    import re
    t = t.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"').replace("­", "")
    return re.sub(r"\s+", " ", t).strip().lower()


def _clave(t: str) -> str:
    """Texto comparable entre el ancla (del texto plano) y la línea del extractor, que omite los «$» y
    reparte los espacios por hueco: se comparan sin espacios ni símbolos de moneda."""
    import re
    return re.sub(r"[\s$€]", "", _normalizar(t))


def _lineas_con_anclas(lineas, anclas: Sequence[str]) -> List[int]:
    """Índices de las líneas que contienen cada ancla; un ancla partida en dos o tres líneas casa con el grupo."""
    textos = [_clave(l.texto) for l in lineas]
    hallados: List[int] = []
    for ancla in anclas:
        a = _clave(ancla)
        if not a:
            continue
        for i, t in enumerate(textos):
            if a in t:
                hallados.append(i)
                break
            if i + 1 < len(textos) and a in t + textos[i + 1]:
                hallados.extend([i, i + 1])
                break
            if i + 2 < len(textos) and a in t + textos[i + 1] + textos[i + 2]:
                hallados.extend([i, i + 1, i + 2])
                break
    return sorted(set(hallados))


def recortar_lineas(adjunto: Adjunto, numero: int, anclas: Sequence[str], salida: Path, campos: Sequence[str],
                    sufijo: str = "", contexto: int = 1) -> Optional[Recorte]:
    """La región de la página `numero` que contiene las anclas, ampliada `contexto` líneas arriba y abajo.

    Devuelve None si ninguna ancla está en la página: no hay recorte sin texto que lo justifique.
    """
    import pypdfium2 as pdfium
    from .extractor import _lineas_de
    doc = pdfium.PdfDocument(str(adjunto.ruta))
    page = doc[numero - 1]
    ancho, alto = page.get_size()
    lineas = _lineas_de(page)
    idx = _lineas_con_anclas(lineas, anclas)
    if not idx:
        return None
    # cada ancla con su contexto; si los bloques quedan lejos, el recorte abarca del primero al último
    elegidas = set()
    for i in idx:
        for k in range(max(0, i - contexto), min(len(lineas), i + contexto + 1)):
            elegidas.add(k)
    ys = [(lineas[k].y0, lineas[k].y1) for k in elegidas]
    xs = [(min(t.x0 for t in lineas[k].tokens), max(t.x1 for t in lineas[k].tokens)) for k in elegidas]
    y0, y1 = min(y for y, _ in ys), max(y for _, y in ys)
    x0, x1 = min(x for x, _ in xs), max(x for _, x in xs)
    margen = 10
    izq, der = max(0.0, x0 - margen), min(ancho, x1 + margen)
    abajo, arriba = max(0.0, y0 - margen), min(alto, y1 + margen)
    crop = (izq, abajo, ancho - der, alto - arriba)
    imagen = page.render(scale=ESCALA_IMPRESION, crop=crop).to_pil()
    salida.mkdir(parents=True, exist_ok=True)
    ruta = salida / f"{adjunto.clave}_p{numero:03d}_{sufijo or 'texto'}.png"
    imagen.save(ruta)
    huella = hashlib.sha256(ruta.read_bytes()).hexdigest()[:16]
    pie = f"Fuente: {adjunto.nombre}, pág. {numero}"
    if adjunto.fecha:
        pie += f" ({adjunto.tipo.value}, {adjunto.fecha:%d/%m/%Y})"
    alt = f"Texto de {adjunto.nombre}, página {numero}: " + "; ".join(a[:60] for a in anclas)
    return Recorte(adjunto=adjunto.clave, pagina=numero, rectangulo=(izq, abajo, der, arriba), ruta=ruta,
                   huella=huella, pie=pie, alt=alt, campos=tuple(campos))


def extraer_imagen(adjunto: Adjunto, numero: int, limites: Tuple[float, float, float, float], salida: Path,
                   nombre: str, rotulo: str) -> Optional[Recorte]:
    """La imagen incrustada cuyos límites en la página son `limites` (x0, y0, x1, y1), tal cual, a PNG."""
    import pypdfium2 as pdfium
    import pypdfium2.raw as pdfium_c
    doc = pdfium.PdfDocument(str(adjunto.ruta))
    page = doc[numero - 1]
    objetivo = None
    for o in page.get_objects(filter=[pdfium_c.FPDF_PAGEOBJ_IMAGE], max_depth=2):
        b = o.get_bounds()
        if all(abs(b[i] - limites[i]) < 2 for i in range(4)):
            objetivo = o
            break
    if objetivo is None:
        return None
    salida.mkdir(parents=True, exist_ok=True)
    ruta = salida / f"{adjunto.clave}_p{numero:03d}_{nombre}.png"
    objetivo.get_bitmap(render=True).to_pil().convert("RGB").save(ruta)
    huella = hashlib.sha256(ruta.read_bytes()).hexdigest()[:16]
    return Recorte(adjunto=adjunto.clave, pagina=numero, rectangulo=tuple(limites), ruta=ruta, huella=huella,
                   pie=f"Fuente: {adjunto.nombre}, pág. {numero}", alt=rotulo, campos=(rotulo,))


def volcado_api(url: str, cuerpo: str, obtenido, salida: Path, nombre: str, rotulo: str, fuente: str,
                extracto: Optional[Sequence[str]] = None, lineas: int = 26) -> Optional[Recorte]:
    """La prueba visual de un dato que viene de una API y no de una página: la respuesta literal del servidor,
    pintada tal cual (extracto), con la URL, la hora de obtención y la huella del cuerpo completo, que se guarda
    entero al lado en `.json` para que cualquiera compruebe la huella. No es una captura de pantalla —la web de
    Nasdaq no se deja capturar por un navegador sin cabeza— y el pie lo dice.

    `extracto`: las líneas a pintar; si no se dan, las primeras `lineas` del cuerpo formateado."""
    from PIL import Image, ImageDraw, ImageFont
    salida.mkdir(parents=True, exist_ok=True)
    ruta_json = salida / f"api_{nombre}.json"
    ruta_json.write_text(cuerpo, encoding="utf-8")
    huella = hashlib.sha256(cuerpo.encode("utf-8")).hexdigest()[:16]
    if extracto is None:
        import json
        try:
            bonito = json.dumps(json.loads(cuerpo), indent=1, ensure_ascii=False)
        except ValueError:
            bonito = cuerpo
        extracto = bonito.splitlines()[:lineas]
    else:
        extracto = list(extracto)[:lineas]
    try:
        fuente_mono = ImageFont.truetype("C:/Windows/Fonts/consola.ttf", 15)
        fuente_pie = ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", 14)
    except OSError:
        fuente_mono = fuente_pie = ImageFont.load_default()
    ancho, alto_linea = 1180, 19
    cab = [f"{fuente} — respuesta literal de la API (extracto)", url, f"Obtenida el {obtenido:%d/%m/%Y %H:%M} (hora local) · sha256 del cuerpo completo {huella} · {len(cuerpo):,} bytes"]
    img = Image.new("RGB", (ancho, alto_linea * (len(extracto) + len(cab)) + 28), "white")
    d = ImageDraw.Draw(img)
    y = 8
    for l in cab:
        d.text((12, y), l[:150], fill=(90, 90, 90), font=fuente_pie)
        y += alto_linea
    d.line((12, y + 2, ancho - 12, y + 2), fill=(200, 200, 200))
    y += 6
    for l in extracto:
        d.text((12, y), l.replace("\t", "  ")[:140], fill=(20, 20, 20), font=fuente_mono)
        y += alto_linea
    ruta = salida / f"api_{nombre}.png"
    img.save(ruta)
    huella_png = hashlib.sha256(ruta.read_bytes()).hexdigest()[:16]
    return Recorte(adjunto=f"api_{nombre}", pagina=0, rectangulo=(0, 0, 0, 0), ruta=ruta, huella=huella_png,
                   pie=f"Fuente: {fuente}, {url} · respuesta literal (no es captura de pantalla) obtenida el {obtenido:%d/%m/%Y %H:%M} hora local · cuerpo completo en api_{nombre}.json, sha256 {huella}",
                   alt=rotulo, campos=(rotulo,))


def retratos(adjunto: Adjunto, numero: int, lado_min: float = 90, lado_max: float = 140) -> List[Tuple[float, float, float, float]]:
    """Límites de las imágenes con forma de retrato (cuadradas, de 90 a 140 pt) de una página."""
    import pypdfium2 as pdfium
    import pypdfium2.raw as pdfium_c
    doc = pdfium.PdfDocument(str(adjunto.ruta))
    page = doc[numero - 1]
    salida = []
    for o in page.get_objects(filter=[pdfium_c.FPDF_PAGEOBJ_IMAGE], max_depth=2):
        x0, y0, x1, y1 = o.get_bounds()
        w, h = x1 - x0, y1 - y0
        if lado_min <= w <= lado_max and lado_min <= h <= lado_max and abs(w - h) < 8:
            salida.append((x0, y0, x1, y1))
    return salida
