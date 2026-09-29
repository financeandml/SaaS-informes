"""Sistema por puntos: cada apartado del índice, punto a punto, en cumple · no aplica (motivo) · falta (motivo).

Los puntos los declara `docs/spec/01_indice.yaml`; aquí no hay otra lista. Un punto sale:
- «no aplica» si pide algo que el mercado del emisor no publica (`requiere` frente a `emisores.Perfil`), con el motivo del
  perfil; las faltas que son de ese punto dejan de bloquear: lo que no existe ni se pide ni se rellena;
- «falta» si el informe trae una falta suya (`inf.faltan`, atribuida por el índice) o si su comprobación sobre el HTML del
  apartado no se cumple; si el punto no es obligatorio, esa comprobación fallida lo deja en «no aplica»;
- «cumple» en otro caso, con lo que se comprobó o diciendo que no hay comprobación automática: un «cumple» no afirma más
  de lo que se ha mirado.
Cada apartado se mira además entero: impreso, no vacío, sin «pendiente» y sin «N/A» donde el índice no lo admite (06 §3.10).
Lo que no es de ningún apartado va al apartado 0 y sigue bloqueando con su texto.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Callable, Dict, List, Optional, Tuple

from . import indice

__all__ = ["Estado", "Punto", "COMPROBACIONES", "evaluar", "bloqueos", "cubiertas", "resumen"]


class Estado(str, Enum):
    CUMPLE = "cumple"
    NO_APLICA = "no aplica"
    FALTA = "falta"


@dataclass(frozen=True)
class Punto:
    apartado: int
    id: str                            # «8.2»; el número del apartado solo («8») es el apartado entero; «0», sin apartado
    texto: str
    estado: Estado
    motivo: str = ""
    faltas: Tuple[str, ...] = ()       # las del informe que explican el estado (en «no aplica», las que deja de bloquear)


_ENTERO = "El apartado entero"
_SIN_APARTADO = "Sin apartado del índice"
_SIN_COMPROBACION = "sin faltas atribuidas; sin comprobación automática"
_OPCIONAL = "opcional: sin faltas atribuidas; sin comprobación automática"


@dataclass(frozen=True)
class _Contexto:
    trozo: str                         # el HTML del apartado
    ampliado: str                      # con el arranque de su parte si es el primero: los gráficos de C van antes del 8
    texto: str                         # lo que se lee
    hoy: Optional[date]


def _filas(html: str) -> int:
    return sum(1 for fila in re.findall(r"<tr\b.*?</tr>", html, re.S | re.I) if re.search(r"<td\b", fila, re.I))


def _cuadro(c: _Contexto) -> Tuple[bool, str]:
    n = _filas(c.trozo)
    return (True, f"cuadro impreso con {n} filas") if n else (False, "no se imprime ningún cuadro con filas")


def _grafico(c: _Contexto) -> Tuple[bool, str]:
    n = len(re.findall(r"<svg\b|<img\b", c.ampliado, re.I))
    return (True, f"{n} gráficos impresos") if n else (False, "no se imprime ningún gráfico")


def _recortes(c: _Contexto) -> Tuple[bool, str]:
    n = len(re.findall(r"<img\b", c.trozo, re.I))
    return (True, f"{n} recortes impresos") if n else (False, "no se imprime ningún recorte de documento")


def _fechas_futuras(c: _Contexto) -> Tuple[bool, str]:
    """06 §3.9: toda fecha «próxima» es posterior o igual a la del informe."""
    if c.hoy is None:
        return True, "sin fecha del informe con que comparar"
    pasadas = []
    for d in re.findall(r"[Pp]róxim\w+[^.]{0,80}?(\d{2}/\d{2}/\d{4})", c.texto):
        try:
            dia = date(int(d[6:]), int(d[3:5]), int(d[:2]))
        except ValueError:
            pasadas.append(d)                        # una fecha que no existe tampoco es futura
            continue
        if dia < c.hoy:
            pasadas.append(d)
    if pasadas:
        return False, "Fecha «próxima» anterior al informe: " + ", ".join(pasadas)
    return True, "ninguna fecha «próxima» anterior al informe"


COMPROBACIONES: Dict[str, Callable[[_Contexto], Tuple[bool, str]]] = {
    "cuadro": _cuadro, "grafico": _grafico, "recortes": _recortes, "fechas_futuras": _fechas_futuras}


def _cuerpo(trozo: str) -> str:
    return re.sub(r"^\s*<h3\b.*?</h3>", "", trozo, count=1, flags=re.S | re.I)


def evaluar(inf, html: Optional[str], perfil=None, hoy: Optional[date] = None) -> Dict[int, List[Punto]]:
    """Apartado impreso → sus puntos (0: las faltas que no son de ningún apartado). Sin `html`, solo faltas y perfil."""
    from .. import qa
    from ..fuentes import emisores
    perfil = perfil if perfil is not None else emisores.perfil(getattr(inf, "emisor", None))
    faltas = list(dict.fromkeys(str(f) for f in getattr(inf, "faltan", None) or []))      # dos veces la misma, una falta
    por_apartado: Dict[int, List[str]] = {}
    for f in faltas:
        por_apartado.setdefault(indice.apartado_de_falta(f), []).append(f)
    trozos = qa.trozos(html) if html is not None else None
    primeros = {p.apartados[0].numero: p.ancla for p in indice.partes() if p.apartados}
    salida: Dict[int, List[Punto]] = {}
    if por_apartado.get(0):
        salida[0] = [Punto(0, "0", _SIN_APARTADO, Estado.FALTA, f, (f,)) for f in por_apartado[0]]
    for n, a in indice.apartados().items():
        salida[n] = _apartado(a, por_apartado.get(n, []), perfil, trozos, primeros.get(n), hoy)
    return salida


def _apartado(a: indice.Apartado, faltas: List[str], perfil, trozos: Optional[Dict[str, str]], ancla_parte: Optional[str],
              hoy: Optional[date]) -> List[Punto]:
    from .. import qa
    n = a.numero
    de_punto: Dict[str, List[str]] = {p.id: [] for p in a.puntos}
    sueltas: List[str] = []                               # del apartado entero («DCF · libro»)
    for f in faltas:
        ps = indice.puntos_de_falta(n, f)
        for p in ps:
            de_punto[p.id].append(f)
        if not ps:
            sueltas.append(f)
    no_aplica = {p.id: "; ".join(perfil.motivo(c) for c in p.requiere if not perfil.tiene(c))
                 for p in a.puntos if any(not perfil.tiene(c) for c in p.requiere)}
    todo_no_aplica = bool(a.puntos) and len(no_aplica) == len(a.puntos)
    general: List[Punto] = []
    if not todo_no_aplica:
        general += [Punto(n, str(n), _ENTERO, Estado.FALTA, f, (f,)) for f in sueltas]
    trozo = trozos.get(str(n)) if trozos is not None else None
    sin_cuerpo = ""                                        # por qué no hay nada que comprobar en el apartado
    if trozos is not None:
        if trozo is None:
            sin_cuerpo = "el apartado no se imprime"
        else:
            cuerpo = _cuerpo(trozo)
            if not qa.visible(cuerpo) and not re.search(r"<(?:table|img|svg)\b", cuerpo, re.I):
                sin_cuerpo = "apartado vacío: ni contenido ni «No aplica» con su motivo"
            if qa.pendiente(trozo):
                general.append(Punto(n, str(n), _ENTERO, Estado.FALTA, "queda contenido pendiente"))
            if a.sin_na and re.search(r"\bN/A\b", qa.visible(trozo)):
                general.append(Punto(n, str(n), _ENTERO, Estado.FALTA, "«N/A» donde no puede haberlo"))
    ampliado = (trozos.get(ancla_parte, "") if trozos is not None and ancla_parte else "") + (trozo or "")
    contexto = _Contexto(trozo or "", ampliado, qa.visible(trozo or ""), hoy)
    puntos: List[Punto] = []
    for p in a.puntos:
        fs = tuple(de_punto[p.id])
        if p.id in no_aplica:
            # lo que el mercado no publica no se pide: sus faltas (y, si no aplica nada, las del apartado) no bloquean
            cubre = fs + (tuple(sueltas) if todo_no_aplica and p is a.puntos[0] else ())
            puntos.append(Punto(n, p.id, p.texto, Estado.NO_APLICA, no_aplica[p.id], cubre))
        elif fs:
            puntos.append(Punto(n, p.id, p.texto, Estado.FALTA, "; ".join(fs), fs))
        elif sin_cuerpo:
            puntos.append(Punto(n, p.id, p.texto, Estado.FALTA if p.obligatorio else Estado.NO_APLICA,
                                sin_cuerpo if p.obligatorio else f"no se imprime: {sin_cuerpo}"))
        elif p.comprueba and trozos is not None:
            if p.comprueba not in COMPROBACIONES:
                raise ValueError(f"01_indice.yaml, punto {p.id}: comprobación desconocida «{p.comprueba}»")
            ok, detalle = COMPROBACIONES[p.comprueba](contexto)
            estado = Estado.CUMPLE if ok else (Estado.FALTA if p.obligatorio else Estado.NO_APLICA)
            puntos.append(Punto(n, p.id, p.texto, estado, detalle if ok or p.obligatorio else f"no se imprime: {detalle}"))
        else:
            puntos.append(Punto(n, p.id, p.texto, Estado.CUMPLE, _SIN_COMPROBACION if p.obligatorio else _OPCIONAL))
    # un apartado sin cuerpo bloquea aunque ninguno de sus puntos obligatorios lo diga ya (01: «nunca vacío»)
    if sin_cuerpo and not any(x.estado is Estado.FALTA and x.motivo == sin_cuerpo for x in puntos):
        general.insert(0, Punto(n, str(n), _ENTERO, Estado.FALTA, sin_cuerpo))
    return general + puntos


def bloqueos(puntos: Dict[int, List[Punto]]) -> List[str]:
    """Una línea por motivo y apartado, en el orden del índice: «Apartado 8 · 8.2 · motivo» (los puntos que comparten
    motivo van juntos, «Apartado 31 · 31.1, 31.2 · …»); al final, lo que no es de ningún apartado, con su texto."""
    salida: List[str] = []
    for n in sorted(k for k in puntos if k):
        grupos: Dict[str, List[str]] = {}
        for p in puntos[n]:
            if p.estado is not Estado.FALTA:
                continue
            for motivo in p.faltas or (p.motivo,):
                ids = grupos.setdefault(motivo, [])
                if p.id != str(n) and p.id not in ids:
                    ids.append(p.id)
        salida += [f"Apartado {n} · " + (", ".join(ids) + " · " if ids else "") + motivo for motivo, ids in grupos.items()]
    salida += [p.motivo for p in puntos.get(0, []) if p.estado is Estado.FALTA]
    return list(dict.fromkeys(salida))


def cubiertas(puntos: Dict[int, List[Punto]]) -> List[str]:
    """Las faltas que no bloquean porque su punto no aplica al mercado del emisor, una línea por falta: a la página interna
    de QA, no se callan."""
    grupos: Dict[Tuple[int, str, str], List[str]] = {}
    for n in sorted(puntos):
        for p in puntos[n]:
            if p.estado is Estado.NO_APLICA:
                for f in p.faltas:
                    grupos.setdefault((n, p.motivo, f), []).append(p.id)
    return [f"Apartado {n} · {', '.join(ids)} · no aplica ({motivo}): {f}" for (n, motivo, f), ids in grupos.items()]


def resumen(puntos: Dict[int, List[Punto]]) -> List[dict]:
    """Por apartado, para `auditoria.json`, la hoja 0 y la web: número, título, recuento por estado y la lista de puntos.
    El recuento se cuenta sobre la misma lista que se entrega (un total y sus partes, de la misma fuente)."""
    aps = indice.apartados()
    salida = []
    for n in sorted(puntos):
        lista = puntos[n]
        if not lista:
            continue
        salida.append({
            "apartado": n, "titulo": aps[n].titulo if n in aps else _SIN_APARTADO,
            "cumple": sum(1 for p in lista if p.estado is Estado.CUMPLE),
            "no_aplica": sum(1 for p in lista if p.estado is Estado.NO_APLICA),
            "falta": sum(1 for p in lista if p.estado is Estado.FALTA),
            "puntos": [{"id": p.id, "texto": p.texto, "estado": p.estado.value, "motivo": p.motivo, "faltas": list(p.faltas)}
                       for p in lista]})
    return salida
