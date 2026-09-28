"""Configuración: del entorno o de `.env` en la raíz del proyecto, nunca inventada.

Un solo lector para todas las claves (`WC_SEC_CONTACTO`, `WC_PRECIO_FUENTE`,
`WC_DATOS`…), para que configurar `.env` baste en todos los módulos y
ninguno tenga su propia copia de la misma lógica.
"""

from __future__ import annotations

import os
from pathlib import Path

__all__ = ["variable", "carpeta", "guardar"]

RAIZ = Path(__file__).resolve().parent.parent

# Lo que vale sin configurar nada, para que el repositorio descargado funcione tal cual (29/09/2026). Solo lo que no es
# una elección: Nasdaq es la única fuente de precio admitida (CLAUDE.md, reglas 4 y 6). El contacto de la SEC no tiene
# valor por defecto: la SEC exige que cada usuario se identifique a sí mismo, y la página lo pide al arrancar.
_POR_DEFECTO = {"WC_PRECIO_FUENTE": "nasdaq"}


def variable(nombre: str) -> str:
    """El valor de la variable en el entorno o, si falta, en `.env`; si tampoco, el de `_POR_DEFECTO` o cadena vacía."""
    valor = os.environ.get(nombre, "").strip()
    if valor:
        return valor
    env = RAIZ / ".env"
    if env.exists():
        for linea in env.read_text(encoding="utf-8").splitlines():
            linea = linea.strip()
            if linea.startswith(nombre + "="):
                valor = linea.split("=", 1)[1].strip().strip('"').strip("'")
                if valor:
                    return valor
    return _POR_DEFECTO.get(nombre, "")


def guardar(nombre: str, valor: str) -> Path:
    """Escribe `nombre=valor` en `.env` (lo crea si no existe; sustituye la línea si ya estaba). Solo desde el propio
    SaaS, para lo que el usuario teclea en la página (el contacto de la SEC)."""
    if "\n" in valor or "\r" in valor:
        raise ValueError("valor con saltos de línea")
    env = RAIZ / ".env"
    lineas = env.read_text(encoding="utf-8").splitlines() if env.exists() else []
    nuevas = [l for l in lineas if not l.strip().startswith(nombre + "=")] + [f"{nombre}={valor}"]
    env.write_text("\n".join(nuevas) + "\n", encoding="utf-8")
    return env


def carpeta(nombre: str) -> Path:
    """La carpeta de datos `nombre` —«adjuntos», «salida»—, bajo `WC_DATOS` si está fijada.

    Los adjuntos y las emisiones son cientos de megas de PDF que no son código; con `WC_DATOS` viven fuera de la copia
    de trabajo. Sin la variable, `datos-tesis/` del repositorio si existe (los datos de ejemplo que trae el repositorio
    descargado de GitHub) y, si no, la raíz, como siempre.
    """
    fijada = variable("WC_DATOS")
    if not fijada and (RAIZ / "datos-tesis").is_dir():
        fijada = "datos-tesis"
    raiz = Path(fijada or RAIZ).expanduser()
    return (raiz if raiz.is_absolute() else RAIZ / raiz) / nombre
