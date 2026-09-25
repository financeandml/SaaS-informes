"""Configuración: del entorno o de `.env` en la raíz del proyecto, nunca inventada.

Un solo lector para todas las claves (`WC_SEC_CONTACTO`, `WC_PRECIO_FUENTE`,
`WC_DATOS`…), para que configurar `.env` baste en todos los módulos y
ninguno tenga su propia copia de la misma lógica.
"""

from __future__ import annotations

import os
from pathlib import Path

__all__ = ["variable", "carpeta"]

RAIZ = Path(__file__).resolve().parent.parent


def variable(nombre: str) -> str:
    """El valor de la variable en el entorno o, si falta, en `.env`; cadena vacía si no está en ninguno."""
    valor = os.environ.get(nombre, "").strip()
    if valor:
        return valor
    env = RAIZ / ".env"
    if env.exists():
        for linea in env.read_text(encoding="utf-8").splitlines():
            linea = linea.strip()
            if linea.startswith(nombre + "="):
                return linea.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def carpeta(nombre: str) -> Path:
    """La carpeta de datos `nombre` —«adjuntos», «salida»—, bajo `WC_DATOS` si está fijada y en la raíz si no.

    Los adjuntos y las emisiones son cientos de megas de PDF que no son código y no se versionan; con `WC_DATOS`
    viven fuera de la copia de trabajo. Sin la variable, todo se queda exactamente donde estaba.
    """
    raiz = Path(variable("WC_DATOS") or RAIZ).expanduser()
    return (raiz if raiz.is_absolute() else RAIZ / raiz) / nombre
