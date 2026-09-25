"""El índice del informe, leído de `docs/spec/01_indice.yaml`: la única fuente de letras, títulos, números y anclas.

El informe y el formulario no escriben un título a mano: lo piden aquí. El código interno sigue llamando a cada
apartado por su clave histórica (la numeración del índice de 40 entradas con el que se construyó), porque de esa clave
cuelgan recortes, cuadros y pruebas; `CLAVE_HISTORICA` la traduce al número que se imprime.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Dict, List, Tuple
from ..rutas import SPEC

__all__ = ["Apartado", "Parte", "CLAVE_HISTORICA", "partes", "titulo"]

RUTA = SPEC / "01_indice.yaml"

# número impreso → clave histórica. Las partes F (riesgos), G (tesis) y H (opciones) conservan sus claves antiguas.
CLAVE_HISTORICA: Dict[int, str] = {**{n: str(n) for n in range(1, 24)},
                                   24: "30", 25: "31", 26: "32", 27: "33", 28: "34", 29: "35", 30: "36",
                                   31: "24", 32: "25", 33: "27", 34: "28", 35: "29",
                                   36: "37", 37: "38", 38: "39", 39: "40"}


@dataclass(frozen=True)
class Apartado:
    numero: int
    clave: str          # clave histórica
    titulo: str


@dataclass(frozen=True)
class Parte:
    letra: str
    titulo: str
    subtitulo: str
    apartados: Tuple[Apartado, ...]

    @property
    def ancla(self) -> str:
        return f"parte-{self.letra}"


@lru_cache(maxsize=1)
def partes() -> Tuple[Parte, ...]:
    try:
        import yaml
    except ImportError as e:            # pragma: no cover - solo sin PyYAML
        raise RuntimeError("Falta PyYAML para leer el índice (docs/spec/01_indice.yaml): pip install pyyaml") from e
    datos = yaml.safe_load(RUTA.read_text(encoding="utf-8"))
    por_parte: Dict[str, List[Apartado]] = {}
    for numero in sorted(datos["apartados"]):
        a = datos["apartados"][numero]
        por_parte.setdefault(a["parte"], []).append(Apartado(int(numero), CLAVE_HISTORICA[int(numero)], a["titulo"]))
    salida = []
    for letra, p in datos["partes"].items():
        salida.append(Parte(letra, p["titulo"], p.get("subtitulo", ""), tuple(por_parte.get(letra, []))))
    return tuple(salida)


def titulo(clave_historica: str) -> str:
    """El título que se imprime para un apartado, por su clave histórica."""
    for p in partes():
        for a in p.apartados:
            if a.clave == clave_historica:
                return a.titulo
    raise KeyError(clave_historica)
