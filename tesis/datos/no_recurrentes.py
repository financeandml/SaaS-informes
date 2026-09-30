"""Partidas no recurrentes dentro de los doce meses de los múltiplos TTM (auditoría del 27/09/2026, fallo [23]).

El PER o el EV/EBITDA de los últimos doce meses llevan dentro lo que haya pasado en ellos: Netflix devengó en el 3T de
2025 una pérdida de 619 M USD por impuestos indirectos en Brasil, que ni la SEC etiqueta aparte ni el TTM aísla. Nadie
lo publica como «no recurrente» en XBRL, así que se busca donde sí se dice: en el texto de los 10-Q y 10-K (o las
cuentas españolas) cuyo periodo cae en la ventana, frases con una clave y un importe (`config/no_recurrentes.yaml`).

Solo avisa (tramo 5): el importe no se resta de nada y la decisión de aislarlo es del analista. La cita es literal, con
el documento y la página física del PDF.
"""

from __future__ import annotations

import re
from datetime import date
from typing import List, Optional, Sequence

from ..formato import numero, pct
from ..rutas import CONFIG, leer_yaml
from .expediente import Expediente, Tipo
from .hechos import Periodo

__all__ = ["detectar"]

_TIPOS = (Tipo.K10, Tipo.Q10, Tipo.CCAA, Tipo.SEMESTRAL)


def _importe(texto: str, reglas: Sequence[dict]) -> Optional[float]:
    for r in reglas:
        m = re.search(r["patron"], texto, re.I)
        if m:
            crudo = m.group(1)
            crudo = crudo.replace(",", "") if r.get("decimal", ".") == "." else crudo.replace(".", "").replace(",", ".")
            try:
                return float(crudo) * float(r["escala"])
            except ValueError:
                continue
    return None


def _paginas(ruta) -> List[str]:
    import pypdfium2 as pdfium
    doc = pdfium.PdfDocument(str(ruta))
    try:
        return [doc[i].get_textpage().get_text_range() for i in range(len(doc))]
    finally:
        doc.close()


def detectar(exp: Expediente, trimestres: Sequence[Periodo], ebit_ttm: Optional[float]) -> List[str]:
    """Avisos, uno por importe distinto, de las frases de partida no recurrente de los documentos de la ventana TTM."""
    from ..umbrales import umbral
    if len(trimestres) < 1 or not ebit_ttm:
        return []
    desde: date = trimestres[0].inicio or trimestres[0].fin
    hasta: date = trimestres[-1].fin
    cfg = leer_yaml(CONFIG / "no_recurrentes.yaml")
    clave = re.compile("|".join(f"(?:{c})" for c in cfg.get("claves") or []), re.I)
    fuera = re.compile("|".join(f"(?:{c})" for c in cfg.get("excluir") or []) or r"(?!x)x", re.I)
    minimo = abs(ebit_ttm) * float(umbral("no_recurrente_min_ebit_ttm"))
    vistos, avisos = set(), []
    docs = sorted((a for a in exp.adjuntos if a.tipo in _TIPOS and a.periodo_fin and desde <= a.periodo_fin <= hasta
                   and str(a.ruta).lower().endswith(".pdf")), key=lambda a: a.periodo_fin)
    for a in docs:
        try:
            paginas = _paginas(a.ruta)
        except Exception:                                           # un PDF ilegible no para la emisión: se lee lo demás
            continue
        for n, texto in enumerate(paginas, 1):
            plano = " ".join(texto.split())
            for frase in re.split(r"(?<=[.;])\s+", plano):
                if not clave.search(frase) or fuera.search(frase):
                    continue
                # una frase que solo cita ejercicios anteriores a la ventana habla de otro periodo (la comparación del
                # 10-K con el año anterior, un cargo de hace tres ejercicios)
                anios = [int(x) for x in re.findall(r"\b(?:19|20)\d\d\b", frase)]
                if anios and max(anios) < desde.year:
                    continue
                importe = _importe(frase, cfg.get("importes") or [])
                if importe is None or importe < minimo or round(importe / 1e6) in vistos:
                    continue
                vistos.add(round(importe / 1e6))
                cita = frase if len(frase) <= 260 else frase[:257] + "…"
                avisos.append(f"Múltiplos TTM · posible partida no recurrente de {numero(importe / 1e6)} M (un {pct(importe / abs(ebit_ttm))} "
                              f"del EBIT de los doce meses) en {a.nombre}, pág. {n} del PDF: «{cita}». Los múltiplos TTM la llevan "
                              f"dentro sin aislar: el analista decide si la ajusta.")
    return avisos
