"""Frases de plantilla (06 §1): variantes de `config/frases.yaml` elegidas por hash(apartado, id), rellenas con cifras
ya formateadas desde Hechos. Devuelven (texto, cita) para imprimir una cita por frase."""

from __future__ import annotations

import hashlib
from functools import lru_cache
from pathlib import Path
from typing import Mapping

__all__ = ["frase", "verbo", "posicion"]

_RUTA = Path(__file__).resolve().parent.parent / "config" / "frases.yaml"


@lru_cache(maxsize=1)
def _frases() -> dict:
    import yaml
    return yaml.safe_load(_RUTA.read_text(encoding="utf-8")) or {}


def verbo(variacion: float) -> str:
    from .umbrales import umbral
    estable = float(umbral("frase_variacion_estable"))
    clave = "igual" if abs(variacion) < estable else ("sube" if variacion > 0 else "baja")
    return _frases()["verbos"][clave]


def posicion(clave: str) -> str:
    return _frases()["posiciones"][clave]


def frase(apartado: str, id_: str, datos: Mapping[str, str]) -> str:
    """La variante de la frase `id_` para el apartado, reproducible: la misma entrada da siempre el mismo texto."""
    variantes = _frases()[id_]
    k = int(hashlib.sha256(f"{apartado}|{id_}".encode()).hexdigest(), 16) % len(variantes)
    return variantes[k].format(**datos)
