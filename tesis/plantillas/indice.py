"""El índice del informe, leído de `docs/spec/01_indice.yaml`: la única fuente de letras, títulos, números y anclas.

El informe y el formulario no escriben un título a mano: lo piden aquí. El código interno sigue llamando a cada
apartado por su clave histórica (la numeración del índice de 40 entradas con el que se construyó), porque de esa clave
cuelgan recortes, cuadros y pruebas; `CLAVE_HISTORICA` la traduce al número que se imprime.

Cada apartado declara también sus puntos (lo que tiene que traer), qué faltas del informe son suyas y si admite «N/A»:
de ahí salen el sistema por puntos (`puntos.py`) y la puerta de calidad, sin una segunda lista en el código.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Dict, FrozenSet, List, Tuple
from ..rutas import SPEC

__all__ = ["Apartado", "Parte", "PuntoIndice", "CLAVE_HISTORICA", "partes", "titulo", "apartados", "sin_na",
           "apartado_de_falta", "puntos_de_falta"]

RUTA = SPEC / "01_indice.yaml"

# número impreso → clave histórica. Las partes F (riesgos), G (tesis) y H (opciones) conservan sus claves antiguas.
CLAVE_HISTORICA: Dict[int, str] = {**{n: str(n) for n in range(1, 24)},
                                   24: "30", 25: "31", 26: "32", 27: "33", 28: "34", 29: "35", 30: "36",
                                   31: "24", 32: "25", 33: "27", 34: "28", 35: "29",
                                   36: "37", 37: "38", 38: "39", 39: "40"}


@dataclass(frozen=True)
class PuntoIndice:
    """Un punto tal como lo declara el índice. `requiere`: capacidades del mercado del emisor (`emisores.Perfil`);
    `comprueba`: nombre de la comprobación de `puntos.py`; `faltas`: prefijos de las faltas que son de este punto."""
    id: str
    texto: str
    requiere: Tuple[str, ...] = ()
    comprueba: str = ""
    obligatorio: bool = True
    faltas: Tuple[str, ...] = ()


@dataclass(frozen=True)
class Apartado:
    numero: int
    clave: str          # clave histórica
    titulo: str
    puntos: Tuple[PuntoIndice, ...] = ()
    entradas: Tuple[str, ...] = ()
    sin_na: bool = False
    faltas: Tuple[str, ...] = ()
    letra: str = ""


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
        puntos = tuple(PuntoIndice(str(p["id"]), p["texto"], tuple(p.get("requiere") or ()), str(p.get("comprueba") or ""),
                                   bool(p.get("obligatorio", True)), tuple(str(f) for f in p.get("faltas") or ()))
                       for p in a.get("puntos") or ())
        por_parte.setdefault(a["parte"], []).append(Apartado(int(numero), CLAVE_HISTORICA[int(numero)], a["titulo"], puntos,
                                                             tuple(a.get("entradas") or ()), bool(a.get("sin_na", False)),
                                                             tuple(str(f) for f in a.get("faltas") or ()), a["parte"]))
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


@lru_cache(maxsize=1)
def apartados() -> Dict[int, Apartado]:
    """Número impreso → apartado."""
    return {a.numero: a for p in partes() for a in p.apartados}


def sin_na() -> FrozenSet[int]:
    """Los apartados en que no puede imprimirse «N/A» (06 §3.10)."""
    return frozenset(n for n, a in apartados().items() if a.sin_na)


# «pilares[3].kpi» y «competencia.competidores[Apple]» son faltas de «pilares.kpi» y «competencia.competidores»: el índice
# de la lista dice cuál, no de quién es
_INDICE_LISTA = re.compile(r"\[[^\]]*\]")


def _partes_de_falta(texto: str) -> Tuple[str, str, str]:
    """(falta, lo que sigue a su origen, id de entrada) sin índices de lista: «Parte A · pilares[1].kpi: …» →
    («Parte A · pilares.kpi: …», «pilares.kpi: …», «pilares.kpi»)."""
    t = _INDICE_LISTA.sub("", " ".join(str(texto).split()))
    _, sep, resto = t.partition(" · ")
    resto = resto if sep else ""
    return t, resto, resto.split(":", 1)[0].strip()


def _casa(texto: str, prefijo: str) -> bool:
    """Empieza por el prefijo y el prefijo acaba en frontera: «Mercado» casa con «Mercado · precio», no con «Mercados»."""
    if not prefijo or not texto.startswith(prefijo):
        return False
    siguiente = texto[len(prefijo):len(prefijo) + 1]
    return not siguiente or not (siguiente.isalnum() or siguiente == "_")


def _largo_entrada(ident: str, entrada: str) -> int:
    base = entrada[:-2] if entrada.endswith(".*") else entrada          # «val.*»: todo lo que cuelga de val
    return len(base) if ident and (ident == base or ident.startswith(base + ".")) else 0


def _prefijos(a: Apartado) -> Tuple[str, ...]:
    return tuple(dict.fromkeys(a.faltas + tuple(f for p in a.puntos for f in p.faltas)))


def apartado_de_falta(texto: str) -> int:
    """El apartado impreso al que pertenece una falta del informe: el que la reclama con el prefijo más largo (los suyos,
    los de sus puntos o el id de una de sus entradas). 0 si ninguno la reclama o si dos la reclaman por igual: lo que no se
    sabe de quién es no se reparte, y sigue bloqueando."""
    t, resto, ident = _partes_de_falta(texto)
    marcas: Dict[int, Tuple[int, int]] = {}
    for a in apartados().values():
        largos = [len(p) for p in _prefijos(a) if _casa(t, p) or _casa(resto, p)]
        largos += [x for x in (_largo_entrada(ident, e) for e in a.entradas) if x]
        if largos:
            marcas[a.numero] = (max(largos), len(largos))
    if not marcas:
        return 0
    mejor = max(m for m, _ in marcas.values())
    empatados = [n for n, (m, _) in marcas.items() if m == mejor]
    if len(empatados) > 1:
        # a igual prefijo, el que la reclama por más caminos: «Parte E · comparables» es del 22 (origen, punto y entrada),
        # no del 17, que solo comparte la entrada
        caminos = max(marcas[n][1] for n in empatados)
        empatados = [n for n in empatados if marcas[n][1] == caminos]
    return empatados[0] if len(empatados) == 1 else 0


def puntos_de_falta(numero: int, texto: str) -> Tuple[PuntoIndice, ...]:
    """Los puntos del apartado que reclaman la falta con su prefijo más largo. Pueden ser varios (sin pilares no hay ni
    argumento ni riesgo por pilar); ninguno si la falta es del apartado entero («DCF · libro»)."""
    t, resto, _ = _partes_de_falta(texto)
    a = apartados().get(numero)
    if a is None:
        return ()
    largos = {p.id: max((len(f) for f in p.faltas if _casa(t, f) or _casa(resto, f)), default=0) for p in a.puntos}
    mejor = max(largos.values(), default=0)
    return tuple(p for p in a.puntos if mejor and largos[p.id] == mejor)
