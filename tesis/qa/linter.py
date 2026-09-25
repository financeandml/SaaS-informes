"""Linter de los textos del analista (06 §2; bloquea la emisión).

Toda cifra con unidad de importe, porcentaje, puntos o múltiplo es un Hecho del informe (con el redondeo con que se
escribe; la tolerancia de `umbrales.linter_tolerancia`, solo en las cifras redondas) o está en una evidencia de las
entradas; ninguna cifra
va sin unidad; sin palabras vetadas, sin inglés (salvo las siglas y términos de 02 › Lenguaje) y sin «N/A» ni
«pendiente». Los límites de palabras los mira el esquema (asistente._campo). Sin `valores`, la comparación con los
Hechos se salta: el asistente la usa así mientras el analista escribe, cuando aún no hay informe.
"""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Iterable, List, Mapping, Optional, Sequence, Tuple
from ..rutas import CONFIG

__all__ = ["revisar", "revisar_entradas", "candidatos", "textos", "frases", "avisos", "avisos_entradas"]

_ESTILO = CONFIG / "estilo.yaml"
# una cifra es-ES (12.560 · 33,4 · −3.117), sin tocar fechas (23/09/2026), rótulos (3T FY26, 13F, 5G) ni decimales ingleses
_CIFRA = re.compile(r"(?<![\w/.,−-])([−-]?)(\d{1,3}(?:\.\d{3})+|\d+)(?:,(\d+))?(?=x\b|[^\w/]|$)(?![.,]\d)")
_NUM = re.compile(r"[−-]?(?:\d{1,3}(?:\.\d{3})+|\d+)(?:,\d+)?")          # la segunda cifra de un rango («10 y 12 %»)
_INGLES_DECIMAL = re.compile(r"(?<![\w/.,])\d+\.\d{1,2}(?![\d\w])")
# la unidad que sigue a la cifra: clase → escalas con que se compara un Hecho guardado en unidades (USD, ratio…)
_UNIDADES = (
    ("milm", re.compile(r"\s*mil\s+millones(?:\s+de\s+\S+)?", re.I), (1e-9,)),
    ("musd", re.compile(r"\s*(?:M\s*USD|mln\s*USD|M\b|mln\b|millones(?:\s+de\s+\S+)?)", re.I), (1e-6,)),
    ("pct", re.compile(r"\s*%"), (100.0, 1.0)),
    ("pp", re.compile(r"\s*(?:p\.\s?p\.|pb\b|puntos)"), (100.0, 1e4)),
    ("usd", re.compile(r"\s*(?:USD|dólares|\$)"), (1.0,)),
    ("veces", re.compile(r"\s*(?:x\b|veces\b)"), (1.0,)),
)
_CONECTOR = re.compile(r"\s*(?:(?:y|o|a|al|hasta|frente\s+a)\s+|[–-]\s*)(?=[−-]?\d)", re.I)
# lo que sigue a una cifra que se queda sin unidad: el final, un signo de puntuación o un nexo («crecieron un 12.»)
_SIN_UNIDAD = re.compile(r"\s*(?:$|[.,;:)»”\]]|(?:y|o|e|en|con|frente|contra|hasta|desde|entre|sobre|para|por|que)\b)", re.I)


@lru_cache(maxsize=1)
def _estilo() -> dict:
    import yaml
    return yaml.safe_load(_ESTILO.read_text(encoding="utf-8")) or {}


def _tolerancia() -> float:
    from ..umbrales import umbral
    return float(umbral("linter_tolerancia"))


def _numero(signo: str, entero: str, decimales: Optional[str]) -> float:
    v = float(entero.replace(".", "") + ("." + decimales if decimales else ""))
    return -v if signo else v


def _unidad(resto: str) -> Tuple[Optional[str], Tuple[float, ...]]:
    for clase, patron, escalas in _UNIDADES:
        if patron.match(resto):
            return clase, escalas
    return None, ()


def _fuera_de_comillas(texto: str) -> str:
    return re.sub(r"«[^»]*»|“[^”]*”|\"[^\"]*\"", " ", texto)


def _numeros_de(texto: str) -> List[float]:
    """Las cifras de una evidencia, leídas en los dos formatos (el literal suele venir en inglés: «$8.9 billion», «8,900»)."""
    salida = []
    for m in re.finditer(r"\d[\d.,]*", texto):
        t = m.group(0).rstrip(".,")
        for miles, decimal in ((".", ","), (",", ".")):
            try:
                salida.append(float(t.replace(miles, "").replace(decimal, ".")))
            except ValueError:
                pass
    return salida


def candidatos(hechos: Mapping, extras: Iterable[float] = ()) -> List[float]:
    """Los valores con que puede casar una cifra del texto: cada Hecho con dato, su variación y su cambio frente al
    periodo anterior de la misma duración (el texto dice «crecieron un 12 %» o «+2,1 p. p.») y los `extras` del motor."""
    por_campo = {}
    for clave, h in (hechos or {}).items():
        if h is None or getattr(h, "valor", None) is None or not getattr(h, "hay_dato", True):
            continue
        campo, p = clave
        por_campo.setdefault((campo, getattr(p, "meses", 0), getattr(p, "es_instante", False)), []).append((p.fin, float(h.valor)))
    salida = [float(x) for x in extras if x is not None]
    for serie in por_campo.values():
        serie.sort()
        valores = [v for _, v in serie]
        salida += valores
        for k, (fin, v) in enumerate(serie):
            for fin0, v0 in serie[:k]:
                dias = (fin - fin0).days
                if k and (fin0, v0) == serie[k - 1] or 355 <= dias <= 375:        # el anterior y el del año anterior
                    salida.append(v - v0)
                    if v0:
                        salida.append(v / v0 - 1)
    return salida


def revisar(texto: str, valores: Optional[Sequence[float]] = None, evidencias: Sequence[str] = ()) -> List[str]:
    """Los reparos de un texto del analista (vacía si pasa)."""
    estilo = _estilo()
    texto = str(texto or "")
    reparos: List[str] = []
    for palabra in estilo.get("vetadas") or []:
        if re.search(rf"(?<!\w){re.escape(palabra)}(?:e?s)?(?!\w)", texto, re.I):          # también en plural
            reparos.append(f"palabra vetada «{palabra}» (02 › Lenguaje: tono factual)")
    libre = _fuera_de_comillas(texto)
    ingles = sorted({w.lower() for w in re.findall(r"[A-Za-z]+", libre)} & {str(w).lower() for w in estilo.get("ingles") or []})
    if len(ingles) >= 2:
        reparos.append(f"texto en inglés ({', '.join(ingles[:4])}): se escribe en español")
    if re.search(r"\bN/A\b", texto):
        reparos.append("«N/A» en un texto del analista")
    if re.search(r"\bpendiente\b", texto, re.I):
        reparos.append("«pendiente» en un texto del analista")
    for m in _INGLES_DECIMAL.finditer(libre):
        reparos.append(f"cifra con formato inglés «{m.group(0)}» (es-ES: {m.group(0).replace('.', ',')})")
    referencias = {str(x).lower() for x in estilo.get("referencias") or []}
    de_evidencias = [x for e in evidencias for x in _numeros_de(e)]
    tol = _tolerancia()
    for m in _CIFRA.finditer(libre):
        signo, entero, decimales = m.group(1), m.group(2), m.group(3)
        antes = libre[:m.start()].rstrip()
        previa = (antes.split()[-1] if antes.split() else "").strip("([«“\"'")
        resto = libre[m.end():m.end() + 40]
        clase, escalas = _unidad(resto)
        tras = resto
        if clase is None:                                       # «entre 10 y 12 %»: la unidad la pone la segunda cifra
            c = _CONECTOR.match(resto)
            s = _NUM.match(resto, c.end()) if c else None
            if s:
                tras = resto[s.end():]
                clase, escalas = _unidad(tras)
        es_anio = decimales is None and not signo and "." not in entero and 1900 <= int(entero) <= 2100
        if previa.lower().rstrip(":,") in referencias or (clase is None and previa[:1].isupper()):
            continue                                            # «apartado 18», «pág. 23», «Snapdragon 8», «S&P 500»
        if clase is None:
            if not es_anio and _SIN_UNIDAD.match(tras):
                reparos.append(f"cifra sin unidad «{m.group(0)}»")
            continue
        if clase == "musd" and decimales is not None and len(decimales) == 3:
            reparos.append(f"cifra con formato inglés «{m.group(0)}» (los millones no llevan decimales: ¿{entero}.{decimales}?)")
            continue
        if valores is None:
            continue
        x = _numero(signo, entero, decimales)
        margen = 0.5 * 10 ** -(len(decimales) if decimales else 0)
        # casa con el redondeo con que se escribe; la tolerancia relativa, solo si la cifra es redonda («15.000 mln USD»):
        # con más de mil Hechos candidatos, un 1 % para cualquier cifra dejaba pasar más de la mitad de las inventadas
        rel = tol if not decimales and entero.endswith("0") else 0.0
        casa = any(abs(x - v * s) <= max(rel * abs(v * s), margen) or abs(-x - v * s) <= max(rel * abs(v * s), margen)
                   for v in valores for s in escalas)
        casa = casa or any(abs(x - v * s) <= max(rel * abs(v * s), margen) for v in de_evidencias for s in (1.0, 1e3, 1e-3))
        if not casa:
            reparos.append(f"cifra sin respaldo «{m.group(0)} {_rotulo(tras)}»: no es un Hecho del informe ni está en una evidencia")
    return reparos


def _rotulo(resto: str) -> str:
    for _, patron, _ in _UNIDADES:
        u = patron.match(resto)
        if u:
            return u.group(0).strip()
    return ""


def textos(e) -> List[Tuple[str, str]]:
    """(id, texto) de cada texto del analista que se imprime: los campos `texto` con `palabras` del esquema (04),
    también dentro de las listas (pilares, riesgos, criterios…), y las frases que editó de los párrafos de plantilla."""
    from ..entradas.asistente import esquema

    def plano(v) -> str:
        return str(v.get("texto", "")) if isinstance(v, dict) else str(v or "")

    salida: List[Tuple[str, str]] = []
    for paso in esquema():
        for c in paso["campos"]:
            v = e.valor(c["id"])
            if c.get("tipo") == "texto" and c.get("palabras") and plano(v).strip():
                salida.append((c["id"], plano(v)))
            elif isinstance(v, list):
                for k, x in enumerate(v, 1):
                    for sub in c.get("campos") or []:
                        if isinstance(x, dict) and sub.get("tipo") == "texto" and sub.get("palabras") and plano(x.get(sub["id"])).strip():
                            salida.append((f"{c['id']}[{k}].{sub['id']}", plano(x.get(sub["id"]))))
    from ..entradas.propuestas import editadas                    # 06 §1: lo que edita de un párrafo de plantilla es texto suyo
    return salida + editadas(e.valor("revision.parrafos"))


def _evidencias(x, salida: List[str]) -> List[str]:
    if isinstance(x, dict):
        if x.get("doc") and (x.get("texto") or x.get("texto_es")):
            salida += [str(x.get("texto") or ""), str(x.get("texto_es") or "")]
        for v in x.values():
            _evidencias(v, salida)
    elif isinstance(x, list):
        for v in x:
            _evidencias(v, salida)
    return salida


def revisar_entradas(e, valores: Sequence[float]) -> List[str]:
    """«id: reparo» de todos los textos del analista, con las cifras contra los Hechos y las evidencias de las entradas."""
    evs = _evidencias(e.datos, [])
    return [f"{id_}: {r}" for id_, t in textos(e) for r in revisar(t, valores, evs)]


def frases(texto: str) -> List[str]:
    """Las frases de un texto: las corta «.», «!», «?» o «…» seguido de espacio y mayúscula (o de «, ¿, ¡ o paréntesis
    que abren), salvo en una abreviatura de `estilo.abreviaturas` («EE. UU.», «S. A.»)."""
    t = " ".join(str(texto or "").split())
    for a in _estilo().get("abreviaturas") or []:
        t = t.replace(a, a.replace(".", "\x00"))
    trozos = re.split(r"(?<=[.!?…])\s+(?=[«\"¿¡(]?[A-ZÁÉÍÓÚÑÜ])", t)
    return [x.replace("\x00", ".").strip() for x in trozos if x.strip()]


def avisos(texto: str) -> List[str]:
    """02 › Estilo: frases desde `frase_palabras_aviso` palabras y párrafos de más de `parrafo_frases_max` frases (cada
    texto del analista se imprime como un párrafo). Van a la página interna de QA: avisan, no bloquean."""
    from ..umbrales import umbral
    largo, max_frases = int(umbral("frase_palabras_aviso")), int(umbral("parrafo_frases_max"))
    lista = frases(texto)
    salida = []
    for f in lista:
        n = len([w for w in f.split() if re.search(r"\w", w)])
        if n >= largo:
            salida.append(f"frase de {n} palabras (02: hasta 35; aviso desde {largo}): «{' '.join(f.split()[:8])}…»")
    if len(lista) > max_frases:
        salida.append(f"párrafo de {len(lista)} frases (02: hasta {max_frases})")
    return salida


def avisos_entradas(e) -> List[str]:
    """«id: aviso» de estilo de todos los textos del analista, también lo que edita de los párrafos de plantilla."""
    return [f"{id_}: {x}" for id_, t in textos(e) for x in avisos(t)]
