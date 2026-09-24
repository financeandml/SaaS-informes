"""Guía de la compañía en los Ex. 99.1 de los 8-K de resultados (apartados 2, 7 y 26; 03 §6).

Cada nota de resultados trae dos cosas que interesan:
- **candidatos de guía**: las filas de la tabla «Outlook / Guidance / Estimates / Forecast» con una métrica reconocible
  y un rango o una cifra («Revenues $9.7B - $10.5B», «Diluted EPS $0.82» bajo «Q3'26 Forecast»). Son candidatos: el
  analista los confirma (entradas `guia.confirmadas`) y solo lo confirmado se imprime.
- **reales** del trimestre que publica, de la tabla de resumen (GAAP y no GAAP), para comparar después la guía con lo
  que pasó. El real GAAP se cuadra con el hecho XBRL del mismo trimestre cuando el informe lo tiene.

Sin patrones de un emisor: cabeceras estándar, rótulos de métrica genéricos y el calendario fiscal que la propia nota
escribe («Q4 FY26», «Q3 Fiscal 2026», «Q3'26»).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from datetime import date
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from . import tablas_html

__all__ = ["Candidato", "Real", "Nota", "Comparacion", "leer_nota", "notas_edgar", "vigentes", "frente_a_real", "trimestre"]

_ORDINALES = {"first": 1, "second": 2, "third": 3, "fourth": 4}
_GUIA = re.compile(r"guidance|outlook|forecast|estimates?\b", re.I)

# (patrón del rótulo, métrica, rótulo en español, unidad). El orden importa: lo no GAAP antes que lo GAAP.
_METRICAS: Tuple[Tuple[str, str, str, str], ...] = (
    (r"^non-?gaap (diluted )?(eps|earnings per share)|^adjusted (diluted )?(eps|earnings per share)", "bpa_no_gaap", "BPA diluido no GAAP", "USD/acción"),
    (r"^(gaap )?diluted (eps|earnings per share)|^diluted earnings per share|^eps\b", "bpa_diluido", "BPA diluido (GAAP)", "USD/acción"),
    (r"^(gaap )?(total )?(net )?revenues?$", "ingresos", "Ingresos", "USD"),
    (r"^([A-Z][A-Za-z0-9&]{1,6}) revenues?$", "ingresos_segmento", "Ingresos {0}", "USD"),
    (r"^operating margin", "margen_ebit", "Margen operativo", "%"),
    (r"^operating income", "ebit", "Resultado operativo", "USD"),
    (r"^net income", "beneficio_neto", "Beneficio neto", "USD"),
    (r"^gross margin", "margen_bruto", "Margen bruto", "%"),
    (r"^free cash flow", "fcf", "Flujo de caja libre", "USD"),
)


def trimestre(texto: str) -> Optional[str]:
    """«Q4 FY26», «Q3 Fiscal 2026», «Q3'26», «Third Quarter Fiscal 2026» → «4T FY26». None si no es un trimestre."""
    m = re.search(r"\bQ([1-4])\s*(?:Fiscal\s*|FY\s*)?[’']?\s*(\d{4}|\d{2})\b", texto, re.I)
    if m:
        return f"{m.group(1)}T FY{m.group(2)[-2:]}"
    m = re.search(r"\b(first|second|third|fourth) quarter(?: of)?(?: fiscal)?(?: year)? (\d{4})", texto, re.I)
    if m:
        return f"{_ORDINALES[m.group(1).lower()]}T FY{m.group(2)[-2:]}"
    return None


def _orden(t: str) -> Tuple[int, int]:
    n, anio = re.match(r"(\d)T FY(\d\d)", t).groups()
    return int(anio), int(n)


def _metrica(rotulo: str) -> Optional[Tuple[str, str, str]]:
    limpio = re.sub(r"\s*\(?\d\)?$|\d$", "", " ".join(rotulo.split())).strip()
    limpio = " ".join(re.sub(r"\((?:loss|income|eps|ebt)\)", " ", limpio, flags=re.I).split())   # «Diluted (loss) earnings per share (EPS)»
    if re.match(r"^(less|plus|add|y/y|shares|net cash|growth)\b", limpio, re.I):
        return None
    for patron, metrica, es, unidad in _METRICAS:
        m = re.match(patron, limpio, re.I)
        if m:
            if metrica == "ingresos_segmento":
                return f"{metrica}:{m.group(1)}", es.format(m.group(1)), unidad
            return metrica, es, unidad
    return None


_NUM = r"\(?\$?\(?(-?[\d,]*\.?\d+)\)?\s*(B|M|K|billion|million|%)?"


def _escala(sufijo: Optional[str], unidad: str, en_millones: bool) -> float:
    s = (sufijo or "").lower()
    if s in ("b", "billion"):
        return 1e9
    if s in ("m", "million"):
        return 1e6
    if s == "k":
        return 1e3
    return 1e6 if (unidad == "USD" and en_millones) else 1.0


def _valor(texto: str, unidad: str, en_millones: bool) -> Optional[Tuple[float, float]]:
    """(bajo, alto) de «$9.7B - $10.5B», «$2.05 - $2.25», «$12,860», «33.2%», «($0.72)». None si no es cifra."""
    t = texto.strip()
    if t in ("—", "$—", "-", "–"):
        return None
    m = re.fullmatch(_NUM + r"\s*(?:-|–|—|to)\s*" + _NUM, t, re.I)
    if m:
        v1, s1, v2, s2 = m.groups()
        s1 = s1 or s2
        bajo = float(v1.replace(",", "")) * _escala(s1, unidad, en_millones)
        alto = float(v2.replace(",", "")) * _escala(s2 or s1, unidad, en_millones)
        return (bajo, alto) if bajo <= alto else (alto, bajo)
    m = re.fullmatch(_NUM, t, re.I)
    if m:
        v = float(m.group(1).replace(",", "")) * _escala(m.group(2), unidad, en_millones)
        if t.startswith("(") or t.startswith("$("):
            v = -abs(v)
        return v, v
    return None


@dataclass(frozen=True)
class Candidato:
    id: str
    metrica: str
    rotulo: str
    original: str
    trimestre: str
    bajo: float
    alto: float
    unidad: str
    presentado: date
    url: str
    fila: str

    @property
    def medio(self) -> float:
        return (self.bajo + self.alto) / 2


@dataclass(frozen=True)
class Real:
    metrica: str
    trimestre: str
    valor: float
    unidad: str
    presentado: date
    url: str
    fila: str


@dataclass
class Nota:
    presentado: date
    url: str
    candidatos: List[Candidato] = field(default_factory=list)
    reales: List[Real] = field(default_factory=list)
    texto: str = ""                     # la nota en texto plano, para verificar las citas del analista
    paginas: Dict[str, str] = field(default_factory=dict)     # página → texto (citas con página)

    @property
    def publicado(self) -> Optional[str]:
        """El trimestre cuyos resultados publica la nota: el más reciente entre sus reales."""
        return max((r.trimestre for r in self.reales), key=_orden, default=None)


def _cabecera(t: tablas_html.Tabla) -> Optional[Tuple[int, List[Optional[str]], List[bool]]]:
    """(fila, trimestre de cada celda, es guía) de la primera fila con trimestres."""
    for i, f in enumerate(t.filas[:4]):
        trimestres = [trimestre(c) for c in f]
        if sum(1 for x in trimestres if x) >= 1 and (len(f) > 1 or _GUIA.search(f[0])):
            return i, trimestres, [bool(_GUIA.search(c)) for c in f]
    return None


def leer_nota(html: str, presentado: date, url: str) -> Nota:
    nota = Nota(presentado=presentado, url=url, texto=tablas_html.texto_plano(html),
                paginas=tablas_html.folios(tablas_html.paginas(html)))
    for t in tablas_html.tablas(html):
        cab = _cabecera(t)
        if cab is None:
            continue
        i, trimestres, guia = cab
        en_millones = bool(re.search(r"in millions", " ".join(" ".join(f) for f in t.filas[:i + 1]) + t.antes[-200:], re.I))
        fila_cab = t.filas[i]
        # 1) tabla de guía en rangos: una celda de cabecera con trimestre y «Guidance/Estimates», filas «métrica | rango»
        if len(fila_cab) == 1 and guia[0] and trimestres[0]:
            for f in t.filas[i + 1:]:
                if len(f) != 2:
                    continue
                m = _metrica(f[0])
                v = _valor(f[1], m[2], en_millones) if m else None
                if m and v:
                    nota.candidatos.append(Candidato(f"{presentado.isoformat()}|{trimestres[0]}|{m[0]}", m[0], m[1], f[0],
                                                     trimestres[0], v[0], v[1], m[2], presentado, url, " | ".join(f)))
            continue
        # 2) tabla de columnas por trimestre (resumen de resultados o carta con columna «Forecast»); bloques GAAP/no GAAP
        #    o por segmento según la fila de grupos de encima
        grupos = t.filas[i - 1] if i > 0 else []
        columnas = fila_cab[1:] if not trimestre(fila_cab[0]) else fila_cab
        desplaza = len(fila_cab) - len(columnas)
        bloques = len(grupos) if grupos and len(columnas) % len(grupos) == 0 else 1
        ancho = len(columnas) // bloques if bloques else len(columnas)
        for f in t.filas[i + 1:]:
            if len(f) != len(fila_cab):
                continue
            for j, c in enumerate(columnas):
                tri = trimestres[j + desplaza]
                if tri is None:
                    continue
                grupo = grupos[j // ancho] if bloques > 1 and grupos else ""
                rotulo = f[0]
                no_gaap = bool(re.search(r"non-?gaap", grupo, re.I))
                if grupo and not no_gaap and not re.fullmatch(r"gaap", grupo, re.I):
                    rotulo = f"{grupo} {f[0]}"           # «QCT Revenues»
                elif no_gaap:
                    rotulo = f"Non-GAAP {f[0]}"
                m = _metrica(rotulo)
                if m is None or (no_gaap and not m[0].startswith("bpa")):
                    continue
                v = _valor(f[j + desplaza], m[2], en_millones)
                if v is None:
                    continue
                if guia[j + desplaza]:
                    nota.candidatos.append(Candidato(f"{presentado.isoformat()}|{tri}|{m[0]}", m[0], m[1], rotulo, tri,
                                                     v[0], v[1], m[2], presentado, url, " | ".join((f[0], f[j + desplaza]))))
                else:
                    nota.reales.append(Real(m[0], tri, v[0], m[2], presentado, url, " | ".join((rotulo, f[j + desplaza]))))
    # una métrica por trimestre y nota (la primera tabla que la trae manda)
    vistos, unicos = set(), []
    for r in nota.reales:
        if (r.metrica, r.trimestre) not in vistos:
            vistos.add((r.metrica, r.trimestre))
            unicos.append(r)
    nota.reales = unicos
    vistos, unicos_c = set(), []
    for c in nota.candidatos:
        if c.id not in vistos:
            vistos.add(c.id)
            unicos_c.append(c)
    nota.candidatos = unicos_c
    return nota


def notas_edgar(emisor, maximo: int = 9) -> Tuple[List[Nota], Dict[str, str]]:
    """Las últimas notas de resultados (8-K con Item 2.02 y su Ex. 99), de la más antigua a la más reciente."""
    from . import sec
    faltan: Dict[str, str] = {}
    notas: List[Nota] = []
    ochok = [d for d in emisor.depositos if d.formulario == "8-K" and "2.02" in (d.epigrafes or "")][:maximo]
    for d in ochok:
        carpeta = f"https://www.sec.gov/Archives/edgar/data/{int(emisor.cik)}/{d.accession.replace('-', '')}"
        try:
            indice, _ = sec._descargar(f"{carpeta}/index.json")
            nombre = next((it["name"] for it in indice["directory"]["item"] if sec.es_anexo_99(it["name"])), None)
            if nombre is None:
                faltan[d.accession] = "el 8-K no lleva Ex. 99"
                continue
            html, _ = sec.descargar_texto(f"{carpeta}/{nombre}")
        except (RuntimeError, sec.SinContacto, KeyError) as e:
            faltan[d.accession] = f"EDGAR no sirvió el anexo: {e}"
            continue
        notas.append(leer_nota(html, d.presentado, f"{carpeta}/{nombre}"))
    return sorted(notas, key=lambda n: n.presentado), faltan


def vigentes(notas: Sequence[Nota], confirmadas: Iterable[str]) -> List[Candidato]:
    """La guía vigente: la de la nota más reciente, confirmada por el analista y de un trimestre aún no publicado."""
    confirmadas = set(confirmadas)
    if not notas:
        return []
    ultima = max(notas, key=lambda n: n.presentado)
    publicado = ultima.publicado
    return [c for c in ultima.candidatos if c.id in confirmadas and (publicado is None or _orden(c.trimestre) > _orden(publicado))]


@dataclass
class Comparacion:
    candidato: Candidato
    real: Optional[Real]
    xbrl: Optional[float] = None           # el hecho XBRL del mismo trimestre, si el informe lo tiene
    nota: str = ""

    @property
    def desvio(self) -> Optional[float]:
        """(real − punto medio) / |punto medio|; en %, puntos porcentuales."""
        if self.real is None or not self.candidato.medio:
            return None
        if self.candidato.unidad == "%":
            return self.real.valor - self.candidato.medio
        return (self.real.valor - self.candidato.medio) / abs(self.candidato.medio)

    @property
    def dentro(self) -> Optional[bool]:
        if self.real is None:
            return None
        return self.candidato.bajo <= self.real.valor <= self.candidato.alto


def frente_a_real(notas: Sequence[Nota], confirmadas: Iterable[str], xbrl: Optional[Mapping[Tuple[str, str], float]] = None,
                  trimestres: int = 8, splits: Sequence[Tuple[date, float]] = ()) -> List[Comparacion]:
    """Guía confirmada frente a lo publicado después, para los últimos `trimestres` trimestres ya publicados.
    `xbrl`: (métrica, «4T FY25») → valor del hecho del informe, para cuadrar el real de la nota.
    `splits`: (fecha, factor); una guía por acción anterior a un split y un real posterior no se comparan sin dividir la
    guía por el factor (la nota posterior reexpresa; la anterior no podía)."""
    confirmadas = set(confirmadas)
    reales: Dict[Tuple[str, str], Real] = {}
    for n in sorted(notas, key=lambda n: n.presentado):
        for r in n.reales:
            reales[(r.metrica, r.trimestre)] = r              # la nota más reciente manda (reexpresiones)
    salida: List[Comparacion] = []
    for n in notas:
        for c in n.candidatos:
            if c.id not in confirmadas:
                continue
            r = reales.get((c.metrica, c.trimestre))
            if r is None:
                continue                                      # aún no publicado: es guía vigente, no historial
            ajuste = ""
            if c.unidad == "USD/acción":
                for fecha, factor in splits:
                    if factor and c.presentado < fecha <= r.presentado:
                        c = replace(c, bajo=c.bajo / factor, alto=c.alto / factor)
                        ajuste = f"guía dividida por el split {factor:g}:1 del {fecha:%d/%m/%Y}, posterior a la nota que la dio"
            comp = Comparacion(c, r, nota=ajuste)
            if xbrl and (c.metrica, c.trimestre) in xbrl:
                comp.xbrl = xbrl[(c.metrica, c.trimestre)]
                tol = 0.005 if c.unidad == "USD/acción" else 0.5e6
                cuadre = ("✓ el real de la nota coincide con el hecho XBRL" if abs(comp.xbrl - r.valor) <= tol
                          else f"≠ la nota dice {r.valor:g} y el hecho XBRL {comp.xbrl:g}")
                comp.nota = "; ".join(x for x in (comp.nota, cuadre) if x)
            salida.append(comp)
    ultimos = sorted({x.candidato.trimestre for x in salida}, key=_orden)[-trimestres:]
    return sorted([x for x in salida if x.candidato.trimestre in ultimos],
                  key=lambda x: (_orden(x.candidato.trimestre), x.candidato.metrica))
