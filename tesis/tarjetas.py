"""Tarjetas de evidencia (03 §6): las frases de los documentos con las palabras clave de un apartado
(`config/evidencias.yaml`), con documento y página, para que el analista elija, traduzca y cite. Se proponen; nunca se
imprimen solas. Cada tarjeta es ya una cita {doc, pag, texto} que `entradas.verificar_cita` da por buena.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import List, Mapping, Sequence

from .entradas import normalizar

__all__ = ["Tarjeta", "proponer", "apartados"]

_RUTA = Path(__file__).resolve().parent.parent / "config" / "evidencias.yaml"
_FIN_DE_FRASE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9“\"(])")


@dataclass
class Tarjeta:
    apartado: str
    doc: str
    pag: str
    texto: str
    claves: List[str] = field(default_factory=list)

    @property
    def cita(self) -> dict:
        return {"doc": self.doc, "pag": self.pag, "texto": self.texto}


@lru_cache(maxsize=1)
def _config() -> dict:
    import yaml
    return yaml.safe_load(_RUTA.read_text(encoding="utf-8")) or {}


def apartados() -> List[str]:
    return list(_config()["apartados"])


def proponer(textos: Mapping[str, str], apartado: str, docs: Sequence[str] = ("10-K",), maximo: int = 8) -> List[Tarjeta]:
    """Las frases con más palabras clave distintas del apartado, en orden de documento y página a igualdad. `textos`:
    «documento#página» → texto (las de `parte_b.ParteB.textos`); solo cuentan las páginas de `docs`."""
    claves = _config()["apartados"][apartado]
    corto, largo = _config()["largo_frase"]
    patrones = [(c, re.compile(r"\b" + re.escape(c), re.I)) for c in claves]
    candidatas: List[Tarjeta] = []
    for clave_doc, texto in textos.items():
        doc, _, pag = clave_doc.partition("#")
        if not pag or doc not in docs:
            continue
        for frase in _FIN_DE_FRASE.split(" ".join(texto.split())):
            if corto <= len(frase) <= largo:
                halladas = [c for c, rx in patrones if rx.search(frase)]
                if halladas:
                    candidatas.append(Tarjeta(apartado, doc, pag, frase, halladas))
    vistas, salida = set(), []
    for t in sorted(candidatas, key=lambda t: -len(t.claves)):        # estable: a igualdad, el orden del documento
        n = normalizar(t.texto)
        if n not in vistas:
            vistas.add(n)
            salida.append(t)
    return salida[:maximo]
