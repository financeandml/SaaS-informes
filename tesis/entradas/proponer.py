"""Lo que el sistema propone para un campo del asistente, y lo que pasa con ello cuando el analista lo confirma (04 · prop).

Una propuesta no es una entrada: no se escribe en `entradas.json` hasta que el analista la confirma, así que mientras
tanto el campo está vacío y la validación de siempre lo cuenta como falta. Al confirmarla, la página escribe el valor y,
en `_origen`, de dónde salió (fuente, motivo, huella y el valor propuesto). Desde ahí:

- si el analista cambia el valor, ya no es la propuesta: `normalizar` lo anota como suyo;
- si cambian los datos de los que salía, cambia la huella y el campo vuelve a «revisar» (`caducadas`), igual que los
  párrafos del paso 9 (`entradas/propuestas.py`).

Cada propuesta sale de una sola función de este registro (regla 13): la misma que usa el motor o la plantilla cuando
toma ese dato. Sin fuente no hay propuesta, y se dice por qué (`SinPropuesta`); nunca un valor por defecto escondido.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date
from typing import Callable, Dict, List, Optional, Union

__all__ = ["Contexto", "Propuesta", "SinPropuesta", "caducadas", "como_json", "en_bloque", "normalizar", "proponer"]


@dataclass(frozen=True)
class Propuesta:
    valor: object
    fuente: str
    motivo: str
    certeza: str = "alta"

    @property
    def huella(self) -> str:
        """Cambia si cambia el valor o su fuente: es lo que hace caducar una confirmación."""
        return hashlib.sha256(json.dumps([self.valor, self.fuente], sort_keys=True, default=str, ensure_ascii=False)
                              .encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class SinPropuesta:
    motivo: str


@dataclass
class Contexto:
    """Lo que una propuesta necesita saber; lo caro (el emisor de EDGAR) se pide una vez y solo si alguien lo usa."""
    ticker: str
    fecha: date
    datos: dict
    _cache: Dict[str, object] = field(default_factory=dict)

    def emisor(self):
        if "emisor" not in self._cache:
            from ..fuentes import sec
            self._cache["emisor"] = sec.emisor(self.ticker)
        return self._cache["emisor"]

    def portada(self):
        """El último 10-K de EDGAR (texto y DEI): el mismo que lee la ficha del informe."""
        if "portada" not in self._cache:
            from ..fuentes import sec
            self._cache["portada"] = sec.portada_10k(self.emisor())
        return self._cache["portada"]

    def facts(self):
        if "facts" not in self._cache:
            from ..fuentes import sec
            self._cache["facts"] = sec.companyfacts(self.emisor().cik)
        return self._cache["facts"]

    def sesiones(self):
        """Las sesiones de Nasdaq de las tres últimas semanas hasta la fecha del informe (cierre oficial)."""
        if "sesiones" not in self._cache:
            from datetime import timedelta
            from ..fuentes import precio
            self._cache["sesiones"] = precio.sesiones_nasdaq(self.ticker, self.fecha - timedelta(days=21), self.fecha, limite=40)
        return self._cache["sesiones"]

    def valor(self, campo: str):
        return _valor(self.datos, campo)

    def fecha_valoracion(self) -> Optional[date]:
        """La que haya puesto el analista; si no, la propuesta (último cierre oficial en o antes de la fecha del informe)."""
        v = self.valor("meta.fecha_valoracion")
        if v:
            try:
                return date.fromisoformat(str(v))
            except ValueError:
                return None
        p = _REGISTRO["meta.fecha_valoracion"](self)
        return date.fromisoformat(p.valor) if isinstance(p, Propuesta) else None


_REGISTRO: Dict[str, Callable[[Contexto], Union[Propuesta, SinPropuesta]]] = {}


def propone(campo: str):
    def registrar(funcion):
        _REGISTRO[campo] = funcion
        return funcion
    return registrar


def proponer(ticker: str, fecha: date, datos: dict) -> Dict[str, Union[Propuesta, SinPropuesta]]:
    """Una propuesta (o su ausencia, con motivo) por cada campo del registro."""
    ctx = Contexto(ticker.upper(), fecha, datos or {})
    salida: Dict[str, Union[Propuesta, SinPropuesta]] = {}
    for campo, funcion in _REGISTRO.items():
        try:
            salida[campo] = funcion(ctx)
        except Exception as e:                        # sin EDGAR o sin configuración: se dice, no se inventa
            from ..rotulos import fallo
            salida[campo] = SinPropuesta(f"no se pudo calcular ({fallo(e)})")
    return salida


def _config() -> dict:
    import yaml
    from ..rutas import CONFIG
    ruta = CONFIG / "propuestas.yaml"
    return (yaml.safe_load(ruta.read_text(encoding="utf-8")) or {}) if ruta.exists() else {}


def en_bloque(campo: str) -> bool:
    """Si «Confirmar las propuestas de este paso» puede confirmarlo sin que el analista lo mire uno a uno."""
    c = _config()
    return campo in (c.get("en_bloque") or []) and campo not in (c.get("nunca_en_bloque") or [])


def como_json(propuestas: Dict[str, Union[Propuesta, SinPropuesta]]) -> Dict[str, dict]:
    salida = {}
    for campo, p in propuestas.items():
        if isinstance(p, Propuesta):
            salida[campo] = {"valor": p.valor, "fuente": p.fuente, "motivo": p.motivo, "certeza": p.certeza,
                             "huella": p.huella, "bloque": en_bloque(campo)}
        else:
            salida[campo] = {"sin": p.motivo}
    return salida


def _valor(datos: dict, campo: str):
    x = datos
    for k in campo.split("."):
        x = x.get(k) if isinstance(x, dict) else None
    return x


def normalizar(datos: dict) -> dict:
    """Lo confirmado desde una propuesta cuyo valor el analista ha cambiado después ya no es la propuesta: es suyo."""
    origen = datos.get("_origen")
    if not isinstance(origen, dict):
        return datos
    for campo, o in list(origen.items()):
        if isinstance(o, dict) and o.get("tipo") == "propuesta" and _valor(datos, campo) != o.get("valor"):
            origen[campo] = {"tipo": "analista", "antes": {k: o.get(k) for k in ("fuente", "valor")}}
    return datos


def confirmadas(datos: dict) -> List[tuple]:
    """(rótulo en español, fuente) de cada campo cuyo valor es el que propuso el sistema y el analista confirmó."""
    rotulos = _config().get("rotulos") or {}
    origen = datos.get("_origen") if isinstance(datos, dict) else None
    return [(rotulos.get(campo, campo.split(".")[-1].replace("_", " ")), o.get("fuente", ""))
            for campo, o in (origen or {}).items() if isinstance(o, dict) and o.get("tipo") == "propuesta"]


def caducadas(datos: dict, propuestas: Dict[str, Union[Propuesta, SinPropuesta]]) -> List[str]:
    """«campo: …» de cada propuesta confirmada cuyos datos han cambiado desde entonces (la huella es otra)."""
    origen = datos.get("_origen") if isinstance(datos, dict) else None
    faltas = []
    for campo, o in (origen or {}).items():
        if not isinstance(o, dict) or o.get("tipo") != "propuesta":
            continue
        p = propuestas.get(campo)
        if isinstance(p, Propuesta) and p.huella != o.get("huella"):
            faltas.append(f"{campo}: la propuesta cambió desde que la confirmó (antes «{o.get('valor')}», ahora «{p.valor}» · "
                          f"{p.fuente}): revísela")
        elif isinstance(p, SinPropuesta):
            faltas.append(f"{campo}: la propuesta que confirmó ya no se puede calcular ({p.motivo}): revísela")
    return faltas


# ---------------------------------------------------------------- el registro

@propone("meta.sector")
def _sector(ctx: Contexto):
    """El paquete sectorial del SIC que declara el emisor en EDGAR (`config/sectores.yaml`), la misma función que usa el
    motor cuando el analista no lo ha confirmado."""
    from ..motor.datos import ingresos_anuales, paquete_por_sic, sectores
    em = ctx.emisor()
    ingresos = None
    if any(a <= int(em.sic) <= b for a, b in (sectores().get("bloqueo_biotech") or {}).get("sic", [])):   # como el paso 1
        from ..fuentes import sec
        facts, obtenido = sec.companyfacts(em.cik)
        ingresos = ingresos_anuales(facts, obtenido)
    paquete, bloqueo = paquete_por_sic(em.sic, ingresos)
    if bloqueo:
        return SinPropuesta(f"bloqueo v1 — {bloqueo}")
    return Propuesta(paquete, f"SEC EDGAR, SIC {em.sic}", "config/sectores.yaml: del código SIC al paquete sectorial")


@propone("meta.tipo")
def _tipo(ctx: Contexto):
    """Actualización si hay entradas guardadas de un informe anterior del mismo valor; si no, inicio de cobertura."""
    from .asistente import fechas
    anteriores = [f for f in fechas(ctx.ticker) if f < ctx.fecha.isoformat()]
    if anteriores:
        return Propuesta("actualizacion", f"entradas guardadas del {anteriores[-1]}", "hay un informe anterior de este valor")
    return Propuesta("inicio_cobertura", "sin entradas anteriores de este valor", "primer informe de este valor")
