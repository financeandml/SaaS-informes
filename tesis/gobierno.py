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

__all__ = ["Accionista", "Consejero", "Ejecutivo", "Filial", "Gobierno", "Retribucion", "construir"]


@dataclass
class Accionista:
    nombre: str
    acciones: float
    porcentaje: Optional[float]      # None = «*» (menos del 1 %)
    direccion: str
    pagina: int
    nota: str = ""


@dataclass
class Ejecutivo:
    nombre: str
    edad: int
    cargo: str
    pagina: int
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
    pagina: int


@dataclass
class Filial:
    nombre: str
    jurisdiccion: str
    porcentaje: Optional[float]
    pagina: int


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


def construir(exp: Expediente, salida_fotos: Optional[Path] = None) -> Gobierno:
    g = Gobierno()
    proxy = max(exp.de_tipo(Tipo.DEF14A), key=lambda a: a.fecha or date.min, default=None)
    k10 = max(exp.de_tipo(Tipo.K10), key=lambda a: a.periodo_fin or date.min, default=None)
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
