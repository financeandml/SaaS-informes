"""Umbrales del proyecto: solo en `config/umbrales.yaml`, nunca en el código (CLAUDE.md, regla 8)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

__all__ = ["umbral"]

_RUTA = Path(__file__).resolve().parent.parent / "config" / "umbrales.yaml"


@lru_cache(maxsize=1)
def _datos() -> dict:
    import yaml
    return yaml.safe_load(_RUTA.read_text(encoding="utf-8")) or {}


def umbral(nombre: str):
    if nombre not in _datos():
        raise KeyError(f"falta «{nombre}» en config/umbrales.yaml")
    return _datos()[nombre]
