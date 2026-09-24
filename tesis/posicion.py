"""Lo que solo el analista puede decir (sección H, apartados 33–36) y su posición.

El sistema no redacta la tesis consolidada, ni el checklist de entrada, ni la gestión
del riesgo, ni el plan de seguimiento: son juicio del analista (capa S) y los escribe
él en un fichero con esta forma, que el informe imprime tal cual, rotulado como suyo.
Lo que falte sale N/A con motivo («el analista no lo ha rellenado»), nunca un relleno.

El mismo fichero lleva la posición —precio de entrada, fecha, tamaño, horizonte,
precio objetivo del analista—, que también usa la sección D (apartado 20) para el
margen de seguridad. Si el analista no la rellena aquí, el apartado 20 la toma del
libro del DCF si el libro la trae, y lo dice.

`posiciones/plantilla.json` es la plantilla que el analista copia; el formulario web
(`python -m tesis.formulario TICKER`) rellena este mismo esquema y lo guarda en
`posiciones/<TICKER>.json`, que `emitir.py` toma por defecto si existe.

La recomendación de la portada (comprar · mantener · vender) también es suya y va aquí.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional

__all__ = ["Posicion", "Criterio", "RECOMENDACIONES", "cargar", "guardar", "plantilla", "validar"]

RECOMENDACIONES = ("comprar", "mantener", "vender")


@dataclass
class Criterio:
    criterio: str
    cumplido: Optional[bool]        # None = sin evaluar
    evidencia: str = ""


@dataclass
class Posicion:
    analista: str = ""
    fecha: Optional[date] = None
    # posición
    precio_entrada: Optional[float] = None
    fecha_entrada: Optional[date] = None
    tamano: str = ""
    horizonte: str = ""
    precio_objetivo: Optional[float] = None
    recomendacion: str = ""              # una de RECOMENDACIONES, o vacía
    # 33 tesis consolidada
    argumento: str = ""
    asunciones: List[str] = field(default_factory=list)
    # 34 checklist
    checklist: List[Criterio] = field(default_factory=list)
    # 35 gestión del riesgo
    invalidacion: List[str] = field(default_factory=list)
    tamano_posicion: str = ""
    volatilidad: str = ""
    # 36 seguimiento
    kpis: List[str] = field(default_factory=list)
    fechas_revision: List[date] = field(default_factory=list)
    criterios_salida: List[str] = field(default_factory=list)
    fichero: Optional[Path] = None

    def faltan(self) -> Dict[str, str]:
        f: Dict[str, str] = {}
        motivo = "el analista no lo ha rellenado en el fichero de posición"
        if not self.argumento:
            f["33 · argumento"] = motivo
        if not self.asunciones:
            f["33 · asunciones clave"] = motivo
        if not self.horizonte:
            f["33 · horizonte temporal"] = motivo
        if not self.checklist:
            f["34 · checklist de entrada"] = motivo
        if not self.invalidacion:
            f["35 · invalidación de la tesis"] = motivo
        if not self.tamano_posicion:
            f["35 · tamaño de posición"] = motivo
        if not self.volatilidad:
            f["35 · volatilidad"] = motivo
        if not self.kpis:
            f["36 · KPIs"] = motivo
        if not self.fechas_revision:
            f["36 · fechas de revisión"] = motivo
        if not self.criterios_salida:
            f["36 · criterios de salida"] = motivo
        if self.precio_entrada is None:
            f["posición · precio de entrada"] = motivo
        if not self.recomendacion:
            f["portada · recomendación"] = motivo
        if self.precio_objetivo is None:
            f["portada · precio objetivo"] = motivo
        return f

    @property
    def vacia(self) -> bool:
        return not (self.argumento or self.asunciones or self.checklist or self.invalidacion or self.kpis or self.criterios_salida)


def _fecha(v) -> Optional[date]:
    return date.fromisoformat(v) if isinstance(v, str) and v else None


def _num(v) -> Optional[float]:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def cargar(ruta: Path) -> Posicion:
    d = json.loads(Path(ruta).read_text(encoding="utf-8"))
    pos, tesis, riesgo, seg = d.get("posicion", {}), d.get("tesis", {}), d.get("riesgo", {}), d.get("seguimiento", {})
    return Posicion(
        analista=str(d.get("analista", "")), fecha=_fecha(d.get("fecha")),
        precio_entrada=_num(pos.get("precio_entrada")), fecha_entrada=_fecha(pos.get("fecha_entrada")), tamano=str(pos.get("tamano", "")),
        horizonte=str(pos.get("horizonte", "")) or str(tesis.get("horizonte", "")), precio_objetivo=_num(pos.get("precio_objetivo")),
        recomendacion=str(pos.get("recomendacion", "")).strip().lower() if str(pos.get("recomendacion", "")).strip().lower() in RECOMENDACIONES else "",
        argumento=str(tesis.get("argumento", "")), asunciones=[str(x) for x in tesis.get("asunciones", []) if str(x).strip()],
        checklist=[Criterio(str(c.get("criterio", "")), c.get("cumplido") if isinstance(c.get("cumplido"), bool) else None, str(c.get("evidencia", "")))
                   for c in d.get("checklist", []) if str(c.get("criterio", "")).strip()],
        invalidacion=[str(x) for x in riesgo.get("invalidacion", []) if str(x).strip()], tamano_posicion=str(riesgo.get("tamano_posicion", "")),
        volatilidad=str(riesgo.get("volatilidad", "")),
        kpis=[str(x) for x in seg.get("kpis", []) if str(x).strip()], fechas_revision=[f for f in (_fecha(x) for x in seg.get("fechas_revision", [])) if f],
        criterios_salida=[str(x) for x in seg.get("criterios_salida", []) if str(x).strip()], fichero=Path(ruta),
    )


def plantilla() -> dict:
    """El esquema vacío que el analista rellena. Las claves son las que `cargar` lee; lo vacío sale N/A."""
    return {
        "analista": "",
        "fecha": "",
        "posicion": {"precio_entrada": None, "fecha_entrada": "", "tamano": "", "horizonte": "", "precio_objetivo": None, "recomendacion": ""},
        "tesis": {"argumento": "", "asunciones": [], "horizonte": ""},
        "checklist": [{"criterio": "", "cumplido": None, "evidencia": ""}],
        "riesgo": {"invalidacion": [], "tamano_posicion": "", "volatilidad": ""},
        "seguimiento": {"kpis": [], "fechas_revision": [], "criterios_salida": []},
    }


def validar(d: dict) -> Dict[str, str]:
    """Los errores de un diccionario con la forma de la plantilla, por campo; vacío si es válido.

    Lo vacío no es error (sale N/A en el informe); lo que está y tiene la forma equivocada, sí: una fecha que
    no es AAAA-MM-DD, un precio que no es número, una recomendación fuera de la lista, un checklist sin criterio.
    """
    errores: Dict[str, str] = {}
    if not isinstance(d, dict):
        return {"": "el cuerpo no es un objeto JSON"}
    pos, tesis, riesgo, seg = d.get("posicion", {}) or {}, d.get("tesis", {}) or {}, d.get("riesgo", {}) or {}, d.get("seguimiento", {}) or {}
    for clave, bloque in (("posicion", pos), ("tesis", tesis), ("riesgo", riesgo), ("seguimiento", seg)):
        if not isinstance(bloque, dict):
            errores[clave] = "debe ser un objeto"
    if errores:
        return errores

    def fecha(clave, v):
        if v in (None, ""):
            return
        try:
            date.fromisoformat(str(v))
        except ValueError:
            errores[clave] = "fecha en formato AAAA-MM-DD"

    def numero(clave, v):
        if v in (None, ""):
            return
        if isinstance(v, bool) or not isinstance(v, (int, float)) or v <= 0:
            errores[clave] = "número positivo"

    def lista(clave, v):
        if v is None:
            return
        if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
            errores[clave] = "lista de textos"

    fecha("fecha", d.get("fecha"))
    fecha("posicion.fecha_entrada", pos.get("fecha_entrada"))
    numero("posicion.precio_entrada", pos.get("precio_entrada"))
    numero("posicion.precio_objetivo", pos.get("precio_objetivo"))
    rec = str(pos.get("recomendacion", "") or "").strip().lower()
    if rec and rec not in RECOMENDACIONES:
        errores["posicion.recomendacion"] = "una de: " + ", ".join(RECOMENDACIONES)
    lista("tesis.asunciones", tesis.get("asunciones"))
    lista("riesgo.invalidacion", riesgo.get("invalidacion"))
    lista("seguimiento.kpis", seg.get("kpis"))
    lista("seguimiento.criterios_salida", seg.get("criterios_salida"))
    fechas = seg.get("fechas_revision")
    if fechas is not None:
        if not isinstance(fechas, list):
            errores["seguimiento.fechas_revision"] = "lista de fechas AAAA-MM-DD"
        else:
            for i, f in enumerate(fechas):
                fecha(f"seguimiento.fechas_revision[{i}]", f)
    checklist = d.get("checklist")
    if checklist is not None:
        if not isinstance(checklist, list):
            errores["checklist"] = "lista de criterios"
        else:
            for i, c in enumerate(checklist):
                if not isinstance(c, dict):
                    errores[f"checklist[{i}]"] = "objeto con criterio, cumplido y evidencia"
                elif not str(c.get("criterio") or "").strip() and (c.get("evidencia") or c.get("cumplido") is not None):
                    errores[f"checklist[{i}].criterio"] = "criterio obligatorio si la fila lleva evidencia o evaluación"
                elif c.get("cumplido") not in (None, True, False):
                    errores[f"checklist[{i}].cumplido"] = "true, false o null (sin evaluar)"
    return errores


def guardar(d: dict, ruta: Path) -> None:
    """Escribe el fichero de posición con la forma de la plantilla; falla si no es válido (nada se guarda a medias)."""
    errores = validar(d)
    if errores:
        raise ValueError("; ".join(f"{k}: {v}" for k, v in errores.items()))
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(d, indent=1, ensure_ascii=False) + chr(10), encoding="utf-8")
