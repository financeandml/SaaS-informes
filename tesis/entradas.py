"""Entradas del analista (`docs/spec/04_entradas.yaml`), por id («perfil.descripcion», «catalizadores»…).

Hasta que exista el asistente web (F6) se leen de un JSON con el mismo esquema: `<datos>/entradas/<TICKER>/<fecha>/
entradas.json`, o la ruta que se pase. Las de prueba (`tests/fixtures/<TICKER>/entradas.json`) llevan `"_prueba"` y el
informe lo dice.

Las evidencias son citas {doc[, pag], texto[, texto_es]} que se verifican contra el texto del documento (03 §6): el texto
normalizado tiene que aparecer (similitud ≥ `umbrales.cita_similitud_min`) y sus cifras, coincidir. Con página, en esa
página (el folio impreso del documento de EDGAR; puede seguir en la siguiente, pero tiene que empezar en la suya).
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

__all__ = ["Entradas", "cargar", "normalizar", "verificar_cita", "comprobar_paso4", "comprobar_paso5", "palabras"]


@dataclass
class Entradas:
    datos: Dict[str, Any] = field(default_factory=dict)
    ruta: Optional[Path] = None

    @property
    def de_prueba(self) -> bool:
        return bool(self.datos.get("_prueba"))

    def valor(self, id_: str, defecto: Any = None) -> Any:
        actual: Any = self.datos
        for parte in id_.split("."):
            if not isinstance(actual, dict) or parte not in actual:
                return defecto
            actual = actual[parte]
        return actual


def cargar(ticker: str, fecha: Optional[date] = None, ruta: Optional[Path] = None) -> Entradas:
    from . import entorno
    candidatas = [ruta] if ruta else []
    if fecha is not None:
        candidatas.append(entorno.carpeta("entradas") / ticker.upper() / fecha.isoformat() / "entradas.json")
    for c in candidatas:
        if c is not None and Path(c).exists():
            return Entradas(json.loads(Path(c).read_text(encoding="utf-8")), Path(c))
    return Entradas()


def normalizar(texto: str) -> str:
    t = unicodedata.normalize("NFKC", texto)
    t = t.translate(str.maketrans({"“": '"', "”": '"', "‘": "'", "’": "'", "–": "-", "—": "-", " ": " ", "​": ""}))
    return " ".join(t.lower().split())


def palabras(texto: str) -> int:
    return len(re.findall(r"\w+", texto or ""))


def _cifras(texto: str) -> List[str]:
    return [c.replace(",", "") for c in re.findall(r"\d[\d,]*(?:\.\d+)?", texto)]


def verificar_cita(cita: Mapping[str, Any], textos: Mapping[str, str], umbral: float) -> Tuple[bool, str]:
    """(válida, motivo). `textos`: documento → texto plano (el 10-K, la DEF 14A, cada Ex. 99.1 por «8-K AAAA-MM-DD»…)
    y «documento#página» → texto de esa página."""
    doc, literal, pag = cita.get("doc", ""), cita.get("texto", ""), cita.get("pag")
    if not doc or not literal:
        return False, "cita sin documento o sin texto"
    if doc not in textos:
        return False, f"documento «{doc}» no disponible para verificar"
    buscado = normalizar(literal)
    if pag in (None, ""):
        cuerpo = normalizar(textos[doc])
        completo, donde = cuerpo, f"«{doc}»"
    else:
        clave = f"{doc}#{pag}"
        if clave not in textos:
            return False, f"«{doc}» no tiene página {pag} para verificar"
        claves = [k for k in textos if k.startswith(f"{doc}#")]
        i = claves.index(clave)
        cuerpo = normalizar(textos[clave])
        siguiente = normalizar(textos[claves[i + 1]])[:len(buscado)] if i + 1 < len(claves) else ""
        completo, donde = (f"{cuerpo} {siguiente}" if siguiente else cuerpo), f"la página {pag} de «{doc}»"
    if 0 <= completo.find(buscado) < len(cuerpo):
        return True, f"literal en {donde}"
    # el trozo más parecido: se ancla en la coincidencia más larga y se compara una ventana del mismo largo
    m = SequenceMatcher(None, completo, buscado, autojunk=False).find_longest_match(0, len(completo), 0, len(buscado))
    inicio = max(0, m.a - m.b)
    ventana = completo[inicio:inicio + len(buscado)]
    similitud = SequenceMatcher(None, ventana, buscado, autojunk=False).ratio() if inicio < len(cuerpo) else 0.0
    if similitud < umbral:
        return False, f"el texto no aparece en {donde} (similitud {similitud:.2f} < {umbral:.2f})"
    faltan = [c for c in _cifras(literal) if c not in _cifras(ventana)]
    if faltan:
        return False, f"cifras que no coinciden con {donde}: {', '.join(faltan)}"
    return True, f"similitud {similitud:.2f}"


def _rango(id_: str, texto: str, rango: str, faltas: List[str]) -> None:
    bajo, alto = (int(x) for x in rango.split("-"))
    n = palabras(texto)
    if not bajo <= n <= alto:
        faltas.append(f"{id_}: {n} palabras (se piden {bajo}–{alto})")


def comprobar_paso4(e: Entradas, textos: Mapping[str, str], umbral: float, hoy: date) -> List[str]:
    """Las faltas del paso 4 (apartados 4–7) que la puerta de calidad convertirá en bloqueo al emitir."""
    faltas: List[str] = []
    descripcion = e.valor("perfil.descripcion") or {}
    if not descripcion.get("texto"):
        faltas.append("perfil.descripcion: falta el texto del analista (apartado 4)")
    else:
        _rango("perfil.descripcion", descripcion["texto"], "80-200", faltas)
    if e.valor("perfil.segmentos_ok") is not True:
        faltas.append("perfil.segmentos_ok: el analista no ha confirmado el cuadro de segmentos")
    track = e.valor("equipo.track_record") or []
    if len(track) < 2:
        faltas.append("equipo.track_record: mínimo CEO y CFO")
    for t in track:
        _rango(f"equipo.track_record[{t.get('persona', '?')}]", t.get("texto", ""), "20-60", faltas)
        for c in t.get("evidencias", []):
            ok, motivo = verificar_cita(c, textos, umbral)
            if not ok:
                faltas.append(f"equipo.track_record[{t.get('persona', '?')}]: {motivo}")
    asignacion = e.valor("equipo.asignacion_capital") or {}
    if not asignacion.get("texto"):
        faltas.append("equipo.asignacion_capital: falta el texto del analista")
    else:
        _rango("equipo.asignacion_capital", asignacion["texto"], "30-80", faltas)
    catalizadores = e.valor("catalizadores") or []
    if len(catalizadores) < 3:
        faltas.append(f"catalizadores: {len(catalizadores)} (mínimo 3)")
    for i, c in enumerate(catalizadores, 1):
        fecha = str(c.get("fecha", ""))
        m = re.fullmatch(r"(\d{4})-(\d\d)-(\d\d)", fecha)
        if m and date(*map(int, m.groups())) < hoy:
            faltas.append(f"catalizadores[{i}]: fecha pasada ({fecha})")
        elif not m and not re.fullmatch(r"\d{4}-T[1-4]", fecha):
            faltas.append(f"catalizadores[{i}]: fecha «{fecha}» (AAAA-MM-DD o AAAA-Tn)")
        if not c.get("evidencia"):
            faltas.append(f"catalizadores[{i}]: sin evidencia")
        for ev in c.get("evidencia", []):
            ok, motivo = verificar_cita(ev, textos, umbral)
            if not ok:
                faltas.append(f"catalizadores[{i}]: {motivo}")
    for i, c in enumerate(e.valor("direccion.citas") or [], 1):
        ok, motivo = verificar_cita(c, textos, umbral)
        if not ok:
            faltas.append(f"direccion.citas[{i}]: {motivo}")
        if not c.get("texto_es"):
            faltas.append(f"direccion.citas[{i}]: falta la versión en español (texto_es)")
    return faltas


_CLASES_MERCADO = ("TAM", "SAM", "SOM")
_METODOS_MERCADO = ("top_down", "bottom_up", "declarado_compania")
_FOSOS = ("efectos_de_red", "costes_de_cambio", "intangibles", "ventaja_de_costes", "escala_eficiente", "ninguno")
_TENDENCIAS = ("se_amplia", "estable", "se_estrecha")


def _citas(id_: str, lista, textos: Mapping[str, str], umbral: float, faltas: List[str], minimo: int = 1) -> None:
    """Evidencias que se imprimen: verificadas en su documento (y página) y con su versión en español."""
    lista = list(lista or [])
    if len(lista) < minimo:
        faltas.append(f"{id_}: sin evidencia (mínimo {minimo})")
    for c in lista:
        ok, motivo = verificar_cita(c, textos, umbral)
        if not ok:
            faltas.append(f"{id_}: {motivo}")
        if not c.get("texto_es"):
            faltas.append(f"{id_}: falta la versión en español de la evidencia (texto_es)")


def comprobar_paso5(e: Entradas, textos: Mapping[str, str], umbral: float) -> List[str]:
    """Las faltas del paso 5 (apartados 21–23): mercado, competencia, comparables y foso defensivo."""
    faltas: List[str] = []
    cifras = e.valor("mercado.cifras") or []
    if not any(c.get("clase") == "TAM" for c in cifras):
        faltas.append("mercado.cifras: falta al menos un TAM")
    for i, c in enumerate(cifras, 1):
        id_ = f"mercado.cifras[{i}]"
        if c.get("clase") not in _CLASES_MERCADO:
            faltas.append(f"{id_}: clase «{c.get('clase')}» (TAM, SAM o SOM)")
        if c.get("metodo") not in _METODOS_MERCADO:
            faltas.append(f"{id_}: método «{c.get('metodo')}» ({', '.join(_METODOS_MERCADO)})")
        if not isinstance(c.get("valor"), (int, float)) or c["valor"] <= 0:
            faltas.append(f"{id_}: el valor tiene que ser un número positivo")
        if not (c.get("etiqueta") and c.get("unidad") and c.get("anio")):
            faltas.append(f"{id_}: etiqueta, unidad y año son obligatorios")
        _citas(id_, c.get("evidencia"), textos, umbral, faltas)
    competidores = e.valor("competencia.competidores") or []
    if len(competidores) < 3:
        faltas.append(f"competencia.competidores: {len(competidores)} (mínimo 3)")
    for i, c in enumerate(competidores, 1):
        id_ = f"competencia.competidores[{c.get('nombre') or i}]"
        if not c.get("nombre"):
            faltas.append(f"{id_}: falta el nombre")
        _rango(f"{id_}.por_que", c.get("por_que", ""), "5-25", faltas)
        _citas(id_, c.get("evidencia"), textos, umbral, faltas, minimo=0)
        if c.get("cuota") is not None:
            _citas(f"{id_}.cuota", c.get("cuota_evidencia"), textos, umbral, faltas)
    comparables = e.valor("comparables") or []
    if not 3 <= len(comparables) <= 10:
        faltas.append(f"comparables: {len(comparables)} (entre 3 y 10)")
    for c in comparables:
        _rango(f"comparables[{c.get('ticker', '?')}].justificacion", c.get("justificacion", ""), "5-25", faltas)
    fuentes = e.valor("moat.fuentes") or []
    if not fuentes:
        faltas.append("moat.fuentes: mínimo una fuente del foso defensivo (o «ninguno», con evidencia)")
    for i, f in enumerate(fuentes, 1):
        id_ = f"moat.fuentes[{i}]"
        if f.get("tipo") not in _FOSOS:
            faltas.append(f"{id_}: tipo «{f.get('tipo')}» ({', '.join(_FOSOS)})")
        if f.get("tendencia") not in _TENDENCIAS:
            faltas.append(f"{id_}: tendencia «{f.get('tendencia')}» ({', '.join(_TENDENCIAS)})")
        if not isinstance(f.get("durabilidad_anios"), (int, float)) or f["durabilidad_anios"] <= 0:
            faltas.append(f"{id_}: durabilidad en años, número positivo")
        _citas(id_, f.get("evidencias"), textos, umbral, faltas)
    amenazas = e.valor("moat.amenazas")
    texto = amenazas.get("texto", "") if isinstance(amenazas, dict) else (amenazas or "")
    if not texto:
        faltas.append("moat.amenazas: falta el texto del analista (20–80 palabras)")
    else:
        _rango("moat.amenazas", texto, "20-80", faltas)
    return faltas
