"""Pruebas de la tubería. Se ejecutan con `python -m unittest discover -s tests -v`.

Las que necesitan el expediente real de Netflix (PDF del 10-K, 10-Q, proxy, carta,
call, cuentas de la web) lo buscan en `tests/expediente_nflx.json`, que lista las
rutas; si falta algún fichero, esas pruebas se saltan y lo dicen. Las que
necesitan la SEC usan la caché de `cache_sec/`; sin ella, se saltan.

Regla de la casa: una prueba nueva no vale hasta haberla visto fallar. Cada
prueba dice en su docstring qué defecto reintroducido la hace fallar.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
MANIFIESTO = Path(__file__).resolve().parent / "expediente_nflx.json"


def rutas_nflx():
    """Las rutas del expediente de Netflix, o None si falta alguna."""
    if not MANIFIESTO.exists():
        return None
    datos = json.loads(MANIFIESTO.read_text(encoding="utf-8"))
    rutas = [Path(datos["carpeta"]) / n for n in datos["ficheros"]]
    return rutas if all(r.exists() for r in rutas) else None


def hay_cache_sec() -> bool:
    return any((RAIZ / "cache_sec").glob("*companyfacts_CIK0001065280*"))


def contacto_sec_de_prueba() -> None:
    """Para las pruebas basta con que exista un contacto; nunca se descarga si hay caché."""
    os.environ.setdefault("WC_SEC_CONTACTO", "Pruebas locales pruebas@localhost.invalid")
