"""06 §1: el sistema propone y el analista valida.

Cada párrafo de plantilla (hoy, el párrafo factual del resumen: portada y apartado 2) sale como propuesta con su
huella: frases y citas tal como las escribe `frases.yaml` con los Hechos del informe. En el paso 9 del asistente el
analista la acepta tal cual o la edita frase a frase (la cita de cada frase no se edita), y lo que valida queda
congelado en `entradas.json` → `revision.parrafos.<id>`: `{propuesta: huella, frases: [[texto, cita], …], editado}`.

Al generar el informe se imprime lo congelado si la huella sigue siendo la de la propuesta; si los datos cambiaron
(otra presentación, otro precio), la huella es otra y se vuelve a pedir. Sin validar, la propuesta se imprime en el
borrador y la emisión se bloquea. Lo editado es texto del analista: pasa el linter (06 §2) como los demás.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import List, Mapping, Optional, Sequence, Tuple

__all__ = ["Parrafo", "huella", "aplicar", "escribir", "leer", "editadas"]

Frases = List[Tuple[str, str]]                  # (frase, cita)


@dataclass
class Parrafo:
    id: str
    titulo: str
    frases: Frases                              # la propuesta del sistema
    huella: str
    estado: str = "sin validar"                 # «sin validar» · «aceptado» · «editado» · «cambió»


def huella(frases: Sequence[Tuple[str, str]]) -> str:
    """La de la propuesta: cambia con cualquier cifra, cita o frase."""
    return hashlib.sha256(json.dumps([[t, c] for t, c in frases], ensure_ascii=False).encode("utf-8")).hexdigest()[:16]


def aplicar(id_: str, titulo: str, propuesta: Sequence[Tuple[str, str]], revision: Optional[Mapping]) -> Tuple[Frases, Parrafo, Optional[str]]:
    """(frases que se imprimen, el párrafo para el paso 9, la falta que bloquea o None)."""
    p = Parrafo(id_, titulo, [(t, c) for t, c in propuesta], huella(propuesta))
    if not propuesta:
        return [], p, None
    r = (revision or {}).get(id_) if isinstance(revision, Mapping) else None
    if not isinstance(r, Mapping) or not r.get("frases"):
        return list(p.frases), p, f"{titulo}: párrafo de plantilla sin aceptar ni editar (paso 9 del asistente)"
    congeladas = [x for x in r["frases"] if isinstance(x, (list, tuple)) and len(x) == 2]
    if r.get("propuesta") != p.huella or len(congeladas) != len(p.frases):
        p.estado = "cambió"
        return list(p.frases), p, (f"{titulo}: los datos cambiaron desde que se validó el párrafo; vuelva a aceptarlo o "
                                   "editarlo (paso 9 del asistente)")
    p.estado = "editado" if r.get("editado") else "aceptado"
    # la cita es la de la propuesta (la huella la ata): el analista edita el texto, no de dónde sale
    impresas = [(str(t).strip(), c) for (t, _), (_, c) in zip(congeladas, p.frases) if str(t).strip()]
    if not impresas:                                    # el bloque es obligatorio (01): se edita, no se borra entero
        return list(p.frases), p, f"{titulo}: la edición dejó el párrafo sin ninguna frase (paso 9 del asistente)"
    return impresas, p, None


def editadas(revision: Optional[Mapping]) -> List[Tuple[str, str]]:
    """(«revision.parrafos.<id>[k]», texto) de las frases editadas por el analista: pasan el linter como sus textos."""
    salida: List[Tuple[str, str]] = []
    for id_, r in (revision or {}).items() if isinstance(revision, Mapping) else ():
        if isinstance(r, Mapping) and r.get("editado"):
            salida += [(f"revision.parrafos.{id_}[{k}]", str(x[0])) for k, x in enumerate(r.get("frases") or [], 1)
                       if isinstance(x, (list, tuple)) and x and str(x[0]).strip()]
    return salida


def escribir(ruta: Path, parrafos: Sequence[Parrafo]) -> Path:
    """Las propuestas de una generación, para el paso 9 (junto al PDF: `<ticker>_tesis_<fecha>.propuestas.json`)."""
    ruta.write_text(json.dumps({"parrafos": [asdict(p) for p in parrafos]}, ensure_ascii=False, indent=1), encoding="utf-8")
    return ruta


def leer(ruta: Path) -> List[dict]:
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [p for p in datos.get("parrafos") or [] if isinstance(p, dict) and p.get("id")]
