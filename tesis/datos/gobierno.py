"""Accionariado, filiales, ejecutivos y retribución (apartados 5 y 6), leídos de la proxy y del 10-K.

Todo son tablas de texto en documentos depositados, y todo se lee con su página:

- **Accionistas** («Security Ownership of Certain Beneficial Owners and
  Management», DEF 14A): cada fila acaba en «<acciones> <porcentaje|*>»; el
  nombre es la primera línea del bloque y la dirección, si la hay, las de en
  medio. La fecha «as of» del párrafo introductorio viaja con la tabla, porque
  una participación sin fecha no es un dato.
- **Ejecutivos** («Executive Officers as of <fecha>»): nombre, edad y cargo.
- **Retribución** («Summary Compensation Table»): filas «Nombre Año cifras…»;
  se guarda cada columna tal cual y el total es la última. No se interpreta qué
  columna es qué salvo por la cabecera de la propia tabla.
- **Filiales** (Exhibit 21 del 10-K): nombre, jurisdicción y porcentaje.
- **Retratos y trayectoria** (fichas biográficas de la proxy): cada ficha empieza
  por «Nombre CARGO EN MAYÚSCULAS» y «AGE: nn», y lleva un retrato a su altura
  en el margen derecho. El retrato se extrae tal cual (no se recorta de un
  render) y se asocia a la ficha por posición vertical; la trayectoria son las
  viñetas de «Career Snapshot» y «Prior», literales.

Nada de esto se contrasta con la SEC por XBRL porque la SEC no lo publica
como XBRL; es texto de un formulario depositado, y así se rotula (H, cita).
Los cruces con los Schedule 13D/G y los Form 4 quedan para una fase posterior.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import List, Optional, Tuple

from .expediente import Adjunto, Expediente, Tipo, _fecha_larga
from .hechos import Origen
from ..rotulos import fallo

__all__ = ["Accionista", "Consejero", "Ejecutivo", "Filial", "Gobierno", "Retribucion", "construir"]


@dataclass
class Accionista:
    nombre: str
    acciones: Optional[float]
    porcentaje: Optional[float]      # None = «*» (menos del 1 %)
    direccion: str
    pagina: Optional[int]
    nota: str = ""
    fuente: str = ""                 # «DEF 14A a 15/12/2025» · «13G/A del 07/08/2026 (a 30/06/2026)»


@dataclass
class Ejecutivo:
    nombre: str
    edad: Optional[int]
    cargo: str
    pagina: Optional[int]
    foto: object = None                          # Recorte del retrato, si la proxy lo trae
    trayectoria: List[str] = field(default_factory=list)   # viñetas literales de «Career Snapshot» y «Prior»
    pagina_ficha: Optional[int] = None


@dataclass
class Consejero:
    nombre: str
    cargo: str                                   # tal cual lo rotula la proxy (INDEPENDENT DIRECTOR…)
    edad: Optional[int]
    desde: Optional[int]                         # «DIRECTOR SINCE»
    pagina: int
    foto: object = None
    nota: str = ""                               # p. ej. «no se presenta a la reelección», literal de la proxy


@dataclass
class Retribucion:
    nombre: str
    anio: int
    cifras: List[Optional[float]]    # columnas tal cual; None donde el documento pone «—»
    total: Optional[float]
    pagina: Optional[int]
    cargo: str = ""


@dataclass
class Filial:
    nombre: str
    jurisdiccion: str
    porcentaje: Optional[float]
    pagina: Optional[int]


@dataclass
class Gobierno:
    accionistas: List[Accionista] = field(default_factory=list)
    fecha_accionistas: Optional[date] = None
    ejecutivos: List[Ejecutivo] = field(default_factory=list)
    fecha_ejecutivos: Optional[date] = None
    consejeros: List[Consejero] = field(default_factory=list)
    retribucion: List[Retribucion] = field(default_factory=list)
    cabecera_retribucion: List[str] = field(default_factory=list)
    filiales: List[Filial] = field(default_factory=list)
    nota_filiales: str = ""
    origenes: dict = field(default_factory=dict)      # clave → Origen
    faltan: dict = field(default_factory=dict)
    junta: Optional[date] = None                          # próxima junta de accionistas (DEF 14A)
    salidas_13g: List[str] = field(default_factory=list)   # quién dejó de declarar ≥ 5 % después de la proxy
    sin_traducir: List[str] = field(default_factory=list)  # cargos o jurisdicciones que el analista debe revisar


# El número de acciones lleva separador de miles (así no se confunde con un código postal de la dirección);
# la columna del porcentaje puede faltar en una fila —la proxy de Netflix la deja en blanco para un consejero—
# y eso es «no hay dato», distinto del «*» que significa «menos del 1 %».
_FILA_ACCIONISTA = re.compile(r"^(.*?)\s*(\d{1,3}(?:,\d{3})+)\s*(\*|[\d.]+%)?\s*$")
_FILA_EJECUTIVO = re.compile(r"^([A-Z][A-Za-z.'’\- ]+?)\s+(\d{2})\s+([A-Za-z][^\n]{3,80})$")
_FILA_RETRIBUCION = re.compile(r"^([A-Z][A-Za-z.'’\- ]+?)(?:\(\d+\))?\s+(20\d\d)\s+((?:(?:[\d,]+|—|-)\s*){3,})$")
_FILA_FILIAL = re.compile(r"^(.+?)\s+([A-Z][A-Za-z .]+?)\s+(\d{1,3})\s?%\s*$")


def _origen(a: Adjunto, pagina: int) -> Origen:
    return Origen(documento=a.nombre, formulario=a.tipo.value, presentado=a.fecha, pagina=pagina)


def _accionistas(proxy: Adjunto, g: Gobierno) -> None:
    for i, texto in enumerate(proxy.paginas, 1):
        if "Security Ownership of Certain Beneficial Owners" not in texto or "Percent of" not in texto:
            continue
        m = re.search(r"beneficial ownership of our common stock as of\s+(\w+ \d{1,2}, \d{4})", texto, re.I | re.S)
        g.fecha_accionistas = _fecha_larga(" ".join(m.group(1).split())) if m else None
        lineas = texto.splitlines()
        inicio = next((k for k, l in enumerate(lineas) if l.strip().startswith("Class")), None)
        if inicio is None:
            continue
        bloque: List[str] = []
        for l in lineas[inicio + 1:]:
            l = l.strip()
            if not l:
                continue
            m = _FILA_ACCIONISTA.match(l)
            if m:
                cabeza = m.group(1).strip()
                partes = bloque + ([cabeza] if cabeza else [])
                if not partes:
                    continue
                nombre = re.sub(r"\(\d+\)\s*$", "", partes[0]).strip()
                direccion = ", ".join(p for p in partes[1:] if p)
                pct = None if m.group(3) in ("*", None) else float(m.group(3).rstrip("%"))
                nota = "menos del 1 %" if m.group(3) == "*" else ("la proxy no imprime el porcentaje en esta fila" if m.group(3) is None else "")
                g.accionistas.append(Accionista(nombre=nombre, acciones=float(m.group(2).replace(",", "")), porcentaje=pct,
                                                direccion=direccion, pagina=i, nota=nota))
                bloque = []
            else:
                if l.startswith("*") or l.startswith("(1)"):
                    break
                bloque.append(l)
        g.origenes["accionistas"] = _origen(proxy, i)
        if g.accionistas:
            return
    g.faltan["accionistas"] = "no se halló la tabla «Security Ownership» en la proxy"


def _ejecutivos(proxy: Adjunto, g: Gobierno) -> None:
    for i, texto in enumerate(proxy.paginas, 1):
        m = re.search(r"Executive Officers as of\s+(\w+ \d{1,2}, \d{4})", texto)
        if not m:
            continue
        g.fecha_ejecutivos = _fecha_larga(m.group(1))
        for l in texto.splitlines():
            mm = _FILA_EJECUTIVO.match(l.strip())
            if mm and 25 <= int(mm.group(2)) <= 90:
                g.ejecutivos.append(Ejecutivo(nombre=mm.group(1).strip(), edad=int(mm.group(2)), cargo=mm.group(3).strip(), pagina=i))
        g.origenes["ejecutivos"] = _origen(proxy, i)
        if g.ejecutivos:
            return
    g.faltan["ejecutivos"] = "no se halló la lista «Executive Officers as of <fecha>» en la proxy"


_FILA_ANIO = re.compile(r"^(20\d\d)\s+((?:(?:[\d,]+(?:\(\d+\))?|—|-)\s*){3,})$")
_NOMBRE_CAPS = re.compile(r"^[A-ZÀ-Ü][A-ZÀ-Ü.'’\-]+(?:\s+[A-ZÀ-Ü][A-ZÀ-Ü.'’\-]+)*(?:\(\d+\))?$")


def _retribucion(proxy: Adjunto, g: Gobierno) -> None:
    """La tabla va por bloques: el nombre en versales en una o dos líneas, el cargo
    debajo y luego una fila por año «AÑO salario bonus … total». Las notas al pie
    pegadas a una cifra («2,453,590(5)») se quitan; el total es la última columna."""
    for i, texto in enumerate(proxy.paginas, 1):
        lineas = [l.strip() for l in texto.splitlines()]
        if not any(l.startswith("Summary Compensation Table") for l in lineas) or "Salary" not in texto:
            continue
        filas = []
        nombre: List[str] = []
        ultimo_nombre = ""
        for l in lineas:
            m = _FILA_ANIO.match(l)
            if m:
                if nombre:
                    ultimo_nombre = " ".join(nombre); nombre = []
                cifras = [None if c in ("—", "-") else float(re.sub(r"\(\d+\)$", "", c).replace(",", "")) for c in m.group(2).split()]
                if ultimo_nombre:
                    filas.append(Retribucion(nombre=ultimo_nombre.title(), anio=int(m.group(1)), cifras=cifras, total=cifras[-1], pagina=i))
            elif _NOMBRE_CAPS.match(l) and l not in ("TOTAL",) and len(l) > 3:
                nombre.append(re.sub(r"\(\d+\)$", "", l))
            elif not l:
                nombre = []
        if filas:
            g.retribucion.extend(filas)
            g.origenes["retribucion"] = _origen(proxy, i)
            g.cabecera_retribucion = ["Año", "Salario", "Bonus", "Acciones", "Opciones", "Incentivo no accionarial", "Otros", "Total"]
            return
    g.faltan["retribucion"] = "no se halló una «Summary Compensation Table» con filas «Nombre / Año cifras» en la proxy"


JURISDICCIONES = ("The Netherlands", "United States", "United Kingdom", "Delaware", "Mexico", "Singapore", "France",
                  "Germany", "Japan", "Brazil", "India", "Canada", "Ireland", "Luxembourg", "Spain", "Italy", "Australia",
                  "Korea", "South Korea", "Hong Kong", "Switzerland", "Sweden", "Poland", "Cayman Islands", "Bermuda",
                  "California", "Nevada", "New York", "Texas", "Argentina", "Colombia", "Chile", "Taiwan", "Belgium",
                  "Denmark", "Norway", "Finland", "Portugal", "Turkey", "Israel", "China", "Thailand", "Indonesia")


def _filiales(k10: Adjunto, g: Gobierno) -> None:
    for i, texto in enumerate(k10.paginas, 1):
        if not re.search(r"EXHIBIT 21|LIST OF (SIGNIFICANT )?SUBSIDIARIES", texto, re.I):
            continue
        for l in texto.splitlines():
            m = _FILA_FILIAL.match(l.strip())
            if m and not l.strip().startswith("Legal Name"):
                # la jurisdicción es un nombre de país o estado conocido al final; lo anterior es el nombre legal
                cuerpo = (m.group(1) + " " + m.group(2)).strip()
                jur = next((j for j in sorted(JURISDICCIONES, key=len, reverse=True) if cuerpo.endswith(" " + j)), None)
                if jur is None:
                    jur = cuerpo.split()[-1]
                nombre = cuerpo[: -len(jur)].strip()
                g.filiales.append(Filial(nombre=nombre, jurisdiccion=jur, porcentaje=float(m.group(3)), pagina=i))
        nota = re.search(r"\*\s*(Pursuant.*?)(?:\n\s*\n|$)", texto, re.S)
        g.nota_filiales = " ".join(nota.group(1).split())[:400] if nota else ""
        g.origenes["filiales"] = _origen(k10, i)
        if g.filiales:
            return
    g.faltan["filiales"] = "el 10-K adjunto no incluye el Exhibit 21 (lista de filiales): hay que bajarlo de EDGAR"


# palabras en Título («Jay C. Hoag», «Mathias Döpfner», «Reed Hastings*»); nunca en MAYÚSCULAS, que es el cargo
_PALABRA_NOMBRE = r"[A-Z][a-zà-ÿ’'\-]*(?:[A-Z][a-zà-ÿ]+)?\.?"
_NOMBRE = rf"{_PALABRA_NOMBRE}(?: {_PALABRA_NOMBRE}){{1,3}}\*?"
_CABECERA_FICHA = re.compile(rf"^({_NOMBRE})(?:\s+([A-Z][A-Z ,&\-]{{6,}}))?\s*$")
_CARGO_CAPS = re.compile(r"^[A-Z][A-Z ,&\-]{6,}$")
_EDAD = re.compile(r"AGE:\s*(\d{2})")
_DESDE = re.compile(r"SINCE:\s*(\d{4})")


def _fichas_de(lineas) -> List[dict]:
    """Las fichas biográficas de una página: nombre, cargo, edad, «since», línea de cabecera y su altura.

    Una ficha es «Nombre CARGO» (o el cargo en las líneas siguientes) con «AGE: nn» en las
    seis líneas de después. Sin la edad no es una ficha: evita tomar por ficha una cita.
    """
    fichas = []
    textos = [l.texto.strip() for l in lineas]
    for i, t in enumerate(textos):
        m = _CABECERA_FICHA.match(t)
        if not m:
            continue
        nombre, cargo = m.group(1).rstrip("*"), (m.group(2) or "").strip()
        j = i + 1
        while not cargo and j < len(textos) and _CARGO_CAPS.match(textos[j]):
            cargo = textos[j]; j += 1
        while j < len(textos) and _CARGO_CAPS.match(textos[j]) and len(cargo) < 90:
            cargo += " " + textos[j]; j += 1
        # un cargo de tres líneas se centra con el nombre: las líneas en mayúsculas de justo encima también son cargo
        k = i - 1
        while k >= 0 and _CARGO_CAPS.match(textos[k]) and "SINCE" not in textos[k]:
            cargo = textos[k] + " " + cargo; k -= 1
        ventana = " ".join(textos[i:i + 8])
        me, md = _EDAD.search(ventana), _DESDE.search(ventana)
        if not me or not cargo:
            continue
        fichas.append({"nombre": nombre, "cargo": cargo.strip(), "edad": int(me.group(1)),
                       "desde": int(md.group(1)) if md else None, "linea": i, "y": lineas[i].y1})
    return fichas


def _trayectoria(textos: List[str], desde: int, hasta: int) -> List[str]:
    """Viñetas de «Career Snapshot» y «Prior» entre dos cabeceras, literales; las viñetas partidas se unen."""
    salida: List[str] = []
    dentro = False
    for t in textos[desde:hasta]:
        if t.startswith("Career Snapshot") or t.startswith("Prior"):
            dentro = True
            if t.startswith("Prior"):
                salida.append("Prior:")
            continue
        if not dentro:
            continue
        if t.startswith("•"):
            salida.append(t.lstrip("• ").strip())
        elif salida and t and not t[0].isupper() or (salida and t and salida[-1].endswith(("of", "and", ",", "the"))):
            salida[-1] += " " + t
        elif t == "":
            continue
        else:
            dentro = False
    return salida


def _fichas_y_retratos(proxy: Adjunto, g: Gobierno, salida_fotos: Optional[Path]) -> None:
    """Retratos y trayectoria de ejecutivos, y el consejo, desde las fichas biográficas de la proxy."""
    import pypdfium2 as pdfium
    from .extractor import _lineas_de
    from .recortes import extraer_imagen, retratos
    doc = pdfium.PdfDocument(str(proxy.ruta))
    por_nombre = {e.nombre.lower(): e for e in g.ejecutivos}
    vistos_consejo = set()
    for numero in range(1, len(proxy.paginas) + 1):
        texto = proxy.paginas[numero - 1]
        if "AGE:" not in texto:
            continue
        lineas = _lineas_de(doc[numero - 1])
        fichas = _fichas_de(lineas)
        if not fichas:
            continue
        limites = retratos(proxy, numero)
        textos = [l.texto.strip() for l in lineas]
        for k, f in enumerate(fichas):
            # el bloque de la ficha va de su cabecera a la siguiente; el retrato cuyo centro cae dentro es el suyo
            tope = f["y"] + 20
            suelo = fichas[k + 1]["y"] if k + 1 < len(fichas) else -1
            foto = None
            for lim in limites:
                yc = (lim[1] + lim[3]) / 2
                if suelo < yc <= tope:
                    if salida_fotos is not None:
                        slug = re.sub(r"[^a-z0-9]+", "_", f["nombre"].lower()).strip("_")
                        foto = extraer_imagen(proxy, numero, lim, salida_fotos, f"retrato_{slug}", f"Retrato de {f['nombre']}")
                    break
            fin = fichas[k + 1]["linea"] if k + 1 < len(fichas) else len(textos)
            trayectoria = _trayectoria(textos, f["linea"], fin)
            e = por_nombre.get(f["nombre"].lower())
            es_consejero = "DIRECTOR" in f["cargo"] or "CHAIR" in f["cargo"] or f["desde"] is not None
            if e is not None:
                e.foto, e.trayectoria, e.pagina_ficha = foto, trayectoria, numero
            if es_consejero and f["nombre"].lower() not in vistos_consejo:
                vistos_consejo.add(f["nombre"].lower())
                g.consejeros.append(Consejero(nombre=f["nombre"], cargo=f["cargo"], edad=f["edad"], desde=f["desde"], pagina=numero, foto=foto))
    # quien deja el consejo en la próxima junta lo dice la propia proxy; se anota para no presentarlo como vigente
    for numero, texto in enumerate(proxy.paginas, 1):
        for m in re.finditer(r"([A-Z][a-zà-ÿ]+(?: [A-Z]\.)? [A-Z][a-zà-ÿ]+) has informed the Company of (?:his|her|their) decision not to stand for re-election", texto):
            for c in g.consejeros:
                if c.nombre.lower().endswith(m.group(1).split()[-1].lower()):
                    c.nota = f"no se presenta a la reelección en la junta (proxy, pág. {numero})"
    sin_foto = [e.nombre for e in g.ejecutivos if e.foto is None]
    if sin_foto and salida_fotos is not None:
        g.faltan["retratos"] = "la proxy no trae retrato asociable a: " + ", ".join(sin_foto)
    if not g.consejeros:
        g.faltan["consejo"] = "no se hallaron fichas de consejeros («Nombre CARGO», «DIRECTOR SINCE», «AGE») en la proxy"


def _de_edgar(emisor, g: Gobierno) -> None:
    """Apartados 5 y 6 desde EDGAR (03 §6): proxy, 10-K, Exhibit 21 y Schedule 13G/13D en XML. Lo que no se encuentra
    queda en `faltan` con el motivo, para que el asistente lo pida con cita."""
    from . import proxy as px
    from .. import rotulos
    from ..fuentes import sec
    from ..formato import fecha as f_fecha, numero
    def texto(d):
        return sec.descargar_texto(d.url)[0]
    p = emisor.ultimo("DEF 14A")
    conocidos: List[str] = []
    if p is None:
        g.faltan["proxy"] = "EDGAR no tiene DEF 14A de la compañía"
    else:
        html = texto(p)
        filas, fecha, seccion = px.leer_propiedad(html)
        g.fecha_accionistas = fecha
        conocidos = [f.nombre for f in filas]
        if filas:
            g.origenes["accionistas"] = px.origen("DEF 14A", "DEF 14A", p.presentado, p.url, seccion)
        fuente_proxy = f"DEF 14A{' a ' + f_fecha(fecha) if fecha else ''}"
        grandes = [f for f in filas if f.porcentaje is not None and f.porcentaje >= 5 and not f.es_grupo]
        grupo = next((f for f in filas if f.es_grupo), None)
        # 13G/13D posteriores a la proxy: la última declaración de cada declarante manda
        declaraciones = []
        for d in emisor.depositos:
            # todos los 13G/13D en XML (desde dic. 2024): la proxy copia los suyos de ellos, a veces con años de retraso
            if ("13G" in d.formulario or "13D" in d.formulario) and d.documento.endswith(".xml"):
                url = f"https://www.sec.gov/Archives/edgar/data/{int(emisor.cik)}/{d.accession.replace('-', '')}/primary_doc.xml"
                try:
                    x = px.leer_13g(sec.descargar_texto(url)[0], d.presentado, d.formulario, url, emisor.nombre)
                except (RuntimeError, sec.SinContacto):
                    x = None
                if x is not None:
                    declaraciones.append(x)
        dentro, fuera = px.vigentes(declaraciones)
        por_clave = {px.clave_nombre(f.nombre): f for f in grandes}
        for x in dentro:
            por_clave.pop(px.clave_nombre(x.declarante), None)
        salen = {px.clave_nombre(x.declarante): x for x in fuera}
        for clave, f in list(por_clave.items()):
            if clave in salen:
                x = salen[clave]
                g.salidas_13g.append(f"{f.nombre}: {numero(f.porcentaje, 2)} % en la proxy; su {x.formulario.replace('SCHEDULE ', '')} del "
                                     f"{f_fecha(x.presentado)} declara {numero(x.porcentaje, 2)} %")
                por_clave.pop(clave)
        for f in por_clave.values():
            g.accionistas.append(Accionista(nombre=f.nombre, acciones=f.acciones, porcentaje=f.porcentaje, direccion="",
                                            pagina=None, fuente=fuente_proxy))
        for x in dentro:
            g.accionistas.append(Accionista(nombre=x.declarante.title() if x.declarante.isupper() else x.declarante,
                                            acciones=x.acciones, porcentaje=x.porcentaje, direccion="", pagina=None,
                                            fuente=f"{x.formulario} del {f_fecha(x.presentado)}"
                                                   + (f" (a {f_fecha(x.fecha_evento)})" if x.fecha_evento else "")))
        g.accionistas.sort(key=lambda a: -(a.porcentaje or 0))
        # F9: la participación de cada consejero y directivo (las filas de la proxy por debajo del 5 %), antes de su
        # total: el apartado 28 remite aquí para «las acciones de cada consejero y ejecutivo»
        for f in filas:
            if f.es_grupo or (f.porcentaje is not None and f.porcentaje >= 5):
                continue
            g.accionistas.append(Accionista(nombre=f.nombre, acciones=f.acciones, porcentaje=f.porcentaje, direccion="", pagina=None,
                                            nota="menos del 1 %" if f.menos_de_uno else "", fuente=fuente_proxy))
        if grupo is not None:
            g.accionistas.append(Accionista(nombre=re.sub(r"All current (executive officers and directors|directors and executive officers)",
                                                          "Consejeros y directivos actuales", grupo.nombre).replace("as a group", "en conjunto")
                                            .replace("persons", "personas"),
                                            acciones=grupo.acciones, porcentaje=grupo.porcentaje, direccion="", pagina=None,
                                            nota="menos del 1 %" if grupo.menos_de_uno else "", fuente=fuente_proxy))
        if not filas:
            g.faltan["accionistas"] = "no se reconoció la tabla de propiedad en la DEF 14A de EDGAR: pídasela al analista con cita"
        r, columnas = px.leer_retribucion(html, conocidos)
        if r:
            ultimo = max(x.anio for x in r)
            femeninas = set()
            k = emisor.ultimo("10-K")
            if k is not None:
                femeninas = {d.nombre for d in px.leer_ejecutivos(texto(k))[0] if d.femenino}
            for x in r:
                if x.anio != ultimo:
                    continue
                cargo, ok = rotulos.cargo(x.cargo, femenino=x.nombre in femeninas)
                if not ok:
                    g.sin_traducir.append(f"cargo «{x.cargo}»")
                g.retribucion.append(Retribucion(nombre=x.nombre, anio=x.anio, cifras=x.cifras[:-1] if x.total is not None else x.cifras,
                                                 total=x.total, pagina=None, cargo=cargo))
            g.cabecera_retribucion = ["Año"] + columnas
            g.origenes["retribucion"] = px.origen("DEF 14A", "DEF 14A", p.presentado, p.url, "Summary Compensation Table")
        else:
            g.faltan["retribucion"] = "no se reconoció la Summary Compensation Table en la DEF 14A de EDGAR"
        m = re.search(r"(?:annual meeting of (?:stockholders|shareholders|shareowners)[^.]{0,80}?(?:will be held|to be held) on\s+"
                      r"(?:\w+,\s+)?([A-Z][a-z]+ \d{1,2}, \d{4}))", px.tablas_html.texto_plano(html)[:60000], re.I)
        if m:
            g.origenes["junta"] = px.origen("DEF 14A", "DEF 14A", p.presentado, p.url, m.group(0)[:160])
            g.junta = px.fecha_as_of("as of " + m.group(1))
    k = emisor.ultimo("10-K")
    if k is not None:
        ejecutivos, fecha = px.leer_ejecutivos(texto(k))
        origen = px.origen("10-K", "10-K", k.presentado, k.url, "Information about our Executive Officers")
        if not ejecutivos and p is not None:
            ejecutivos, fecha = px.leer_ejecutivos(texto(p))
            origen = px.origen("DEF 14A", "DEF 14A", p.presentado, p.url, "Executive Officers")
        for e in ejecutivos:
            cargo, ok = rotulos.cargo(e.cargo, femenino=e.femenino)
            if not ok:
                g.sin_traducir.append(f"cargo «{e.cargo}»")
            g.ejecutivos.append(Ejecutivo(nombre=e.nombre, edad=e.edad, cargo=cargo, pagina=None))
        if ejecutivos:
            g.fecha_ejecutivos = fecha
            g.origenes["ejecutivos"] = origen
        else:
            g.faltan["ejecutivos"] = "ni el 10-K ni la DEF 14A traen la lista de ejecutivos con edad y cargo reconocible"
        base = k.url.rsplit("/", 1)[0]
        try:
            indice, _ = sec._descargar(base + "/index.json")
            nombres = [it["name"] for it in indice.get("directory", {}).get("item", [])]
        except (RuntimeError, sec.SinContacto):
            nombres = []
        ex21 = next((n for n in nombres if re.search(r"ex-?21", n, re.I)), None)
        if ex21 is None:
            g.faltan["filiales"] = "el índice del último 10-K no incluye el Exhibit 21"
        else:
            for f in px.leer_filiales(sec.descargar_texto(f"{base}/{ex21}")[0]):
                if not f.traducida:
                    g.sin_traducir.append(f"jurisdicción «{f.jurisdiccion}»")
                g.filiales.append(Filial(nombre=f.nombre, jurisdiccion=f.jurisdiccion, porcentaje=None, pagina=None))
            g.origenes["filiales"] = px.origen("Exhibit 21 del 10-K", "10-K", k.presentado, f"{base}/{ex21}", "Subsidiaries")


def construir(exp: Expediente, salida_fotos: Optional[Path] = None, emisor=None) -> Gobierno:
    """Con `emisor`, todo sale de EDGAR (HTML y XML); el PDF de la proxy, si está en el expediente, solo aporta retratos,
    trayectorias y consejo. Sin `emisor` (o sin contacto con la SEC), la lectura antigua de los PDF adjuntos."""
    g = Gobierno()
    if emisor is not None and getattr(emisor, "mercado", "sec") == "bme":
        return _de_bme(exp, g)
    proxy = max(exp.de_tipo(Tipo.DEF14A), key=lambda a: a.fecha or date.min, default=None)
    k10 = max(exp.de_tipo(Tipo.K10), key=lambda a: a.periodo_fin or date.min, default=None)
    if emisor is not None:
        from ..fuentes import sec
        try:
            _de_edgar(emisor, g)
            if proxy is not None:
                _fichas_y_retratos(proxy, g, salida_fotos)
            return g
        except (RuntimeError, sec.SinContacto) as e:
            g = Gobierno()
            g.faltan["edgar"] = f"EDGAR no respondió ({fallo(e)}); se leen los PDF adjuntos"
    if proxy is None:
        g.faltan["proxy"] = "sin DEF 14A en el expediente: accionariado, ejecutivos y retribución quedan sin fuente"
    else:
        _accionistas(proxy, g)
        _ejecutivos(proxy, g)
        _retribucion(proxy, g)
        _fichas_y_retratos(proxy, g, salida_fotos)
    if k10 is None:
        g.faltan["filiales"] = "sin 10-K en el expediente"
    else:
        _filiales(k10, g)
    return g


# --------------------------------------------------------------------------- emisores de BME

_PARTICIPACIONES = re.compile(r"(?i)(?:accionistas?|participaciones?)[^.]{0,80}?(?:igual(?:es)? o superior(?:es)?|superior) al 5\s?%"
                              r"|participaciones significativas")
_PCT = re.compile(r"(\d{1,3}(?:,\d{1,2})?)\s?%+")
_ACCIONES_ES = re.compile(r"^\d{1,3}(?:\.\d{3})+$")
_FIN_TABLA = re.compile(r"(?i)^(?:la (?:compañía|sociedad)|el consejo|de conformidad|en cumplimiento|atentamente|quedamos)")
# la fecha de la posición, no la de la carta: «… superior al 5 % del capital social a 30 de junio de 2026»
_FECHA_CORTE = re.compile(r"(?i)(?:5\s?%|capital social)[^.]{0,60}?\ba (\d{1,2} de \w+ de (?:19|20)\d{2})")
_NOTA_AL_PIE = re.compile(r"^\*{0,3}\d{0,2}\.?\s*(?:propiedad|el consejero|representad|fondo de inversi)|^\*+\s*\S", re.I)


def _de_bme(exp: Expediente, g: Gobierno) -> Gobierno:
    """Gobierno de un emisor de BME. Accionistas: la última comunicación de participaciones significativas que el emisor
    publica en la bolsa (≥ 5 %, con su fecha de corte), leída fila a fila. Lo demás no tiene una fuente que se pueda leer
    con seguridad —el consejo y la dirección vienen en el documento de incorporación, la retribución agregada en la
    memoria—: lo aporta el analista con su cita (regla 12), y el sistema por puntos lo dice."""
    from .expediente import _fecha_es as _fecha_es_texto
    candidatos = []
    for a in exp.adjuntos:
        for k, texto in enumerate(a.paginas, 1):
            if _PARTICIPACIONES.search(" ".join(texto.split())) and _PCT.search(texto):
                candidatos.append((a.fecha or date.min, a, k))
                break
    if not candidatos:
        g.faltan["accionistas"] = ("sin comunicación de participaciones significativas en el expediente: tráela de BME "
                                   "o aporta los accionistas con su cita")
    else:
        _, a, k = max(candidatos, key=lambda x: x[0])
        filas = _filas_participaciones("\n".join(a.paginas[k - 1:]))
        corte = _FECHA_CORTE.search(" ".join(a.paginas[k - 1].split()))
        g.fecha_accionistas = _fecha_es_texto(corte.group(1)) if corte else None
        fuente = f"{a.nombre} (participaciones ≥ 5 %{', a ' + g.fecha_accionistas.strftime('%d/%m/%Y') if g.fecha_accionistas else ''})"
        for nombre, acciones, directa, indirecta, total in filas:
            porcentaje = total if total is not None else (directa if directa is not None else indirecta)
            partes = [f"directa {directa:.2f} %".replace(".", ",") if directa is not None else "",
                      f"indirecta {indirecta:.2f} %".replace(".", ",") if indirecta is not None else ""]
            g.accionistas.append(Accionista(nombre=nombre, acciones=acciones, porcentaje=porcentaje, direccion="", pagina=k,
                                            nota=" · ".join(x for x in partes if x), fuente=fuente))
        if g.accionistas:
            g.origenes["accionistas"] = Origen(documento=a.nombre, formulario="participaciones significativas",
                                               presentado=a.fecha, pagina=k)
        else:
            g.faltan["accionistas"] = f"{a.nombre} no trae una tabla de accionistas legible: aporta los accionistas con su cita"
    g.faltan["ejecutivos"] = ("el consejo y la alta dirección de un emisor de BME están en su documento de incorporación "
                              "y en su web: los aporta el analista con su cita (paso 4)")
    g.faltan["filiales"] = ("las sociedades del grupo están en la memoria de las cuentas consolidadas: las aporta el analista "
                            "con su cita (paso 4)")
    return g


def _filas_participaciones(texto: str):
    """(nombre, acciones, % directo, % indirecto, % total) de cada fila de la tabla de participaciones. El orden de las
    columnas lo dice la cabecera («directa · indirecta · total»); un nombre partido en varias líneas se junta, y «-» es
    «sin participación de ese tipo», no un cero leído."""
    lineas = [l.strip() for l in texto.splitlines() if l.strip()]
    inicio = next((k for k, l in enumerate(lineas) if re.match(r"(?i)^accionistas?\b", l)), None)
    if inicio is None:
        return []
    cabecera = " ".join(lineas[inicio:inicio + 4]).lower()
    con_total = "total" in cabecera
    con_acciones = bool(re.search(r"n[ºo°]\.? ?de acciones|acciones directas|n[úu]mero de acciones", cabecera))
    salida, pendiente = [], []
    for l in lineas[inicio + 1:]:
        if _FIN_TABLA.match(l) or (salida and _NOTA_AL_PIE.match(l)):
            break                                               # fin de la tabla: su texto o sus notas al pie
        if re.match(r"(?i)^(?:directa|indirecta|total|\(?%\)?|participaci[óo]n|n[ºo°]? de acciones)", l) and not _PCT.search(l):
            continue                                            # restos de la cabecera partida
        tokens = l.split()
        valores = [x for x in tokens if _PCT.fullmatch(x) or x in ("-", "–", "—") or _ACCIONES_ES.match(x)]
        if not any(_PCT.fullmatch(x) for x in valores):
            pendiente.append(l)
            continue
        primero = next(i for i, x in enumerate(tokens) if _PCT.fullmatch(x) or x in ("-", "–", "—") or _ACCIONES_ES.match(x))
        nombre = " ".join(pendiente + tokens[:primero]).strip(" *")
        nombre = re.sub(r"(?<=[A-Z.])\d$", "", nombre).strip()          # la llamada a la nota al pie («S.L.U.1»)
        pendiente = []
        celdas = [x for x in tokens[primero:] if _PCT.fullmatch(x) or x in ("-", "–", "—") or _ACCIONES_ES.match(x)]
        acciones = None
        if con_acciones and celdas and not _PCT.fullmatch(celdas[0]):
            primera = celdas.pop(0)                               # la columna de acciones: un número o «-»
            acciones = float(primera.replace(".", "")) if _ACCIONES_ES.match(primera) else None
        pcts = [None if x in ("-", "–", "—") else float(_PCT.fullmatch(x).group(1).replace(",", "."))
                for x in celdas if _PCT.fullmatch(x) or x in ("-", "–", "—")]
        directa = pcts[0] if pcts else None
        indirecta = pcts[1] if len(pcts) > 1 else None
        total = pcts[2] if con_total and len(pcts) > 2 else None
        if nombre and any(x is not None for x in (directa, indirecta, total)):
            salida.append((re.sub(r"\s+", " ", nombre), acciones, directa, indirecta, total))
    return salida
