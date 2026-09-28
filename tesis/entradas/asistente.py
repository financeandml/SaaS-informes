"""Asistente web de 9 pasos (04): el esquema sale de `docs/spec/04_entradas.yaml`; lo que el analista guarda va a
`<datos>/entradas/<TICKER>/<AAAA-MM-DD>/entradas.json`, versionado, que es lo que lee `emitir.py`.

Validación al guardar: la genérica del esquema (obligatorios, palabras, rangos, listas y valores) y la propia de los
pasos que no necesitan los documentos (7: supuestos del motor; 8: posición, con el rango de la sesión de Nasdaq). Las
citas se verifican contra los documentos al generar el informe (pasos 4–6), y sus faltas salen en la puerta de calidad.
"""

from __future__ import annotations

import json
import re
import shutil
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .. import entorno
from . import Entradas, comprobar_paso8, palabras
from ..rutas import SPEC

__all__ = ["esquema", "ruta", "fechas", "cargar", "guardar", "validar", "migrar_posicion", "propuestas"]

_SPEC = SPEC / "04_entradas.yaml"
# campos que 04 pide en la validación de otro («fuente y fecha obligatorias», «≠ 0 exige justificación»): van detrás de él
_DERIVADOS = {
    "pos.recomendacion": [{"id": "pos.recomendacion_justificacion", "tipo": "texto", "palabras": "20-120", "oblig": False,
                           "nota": "obligatoria si difiere de la que sugiere la regla"}],
    "wacc.erp": [{"id": "wacc.erp_fuente", "tipo": "texto", "oblig": True, "nota": "fuente y fecha de la prima de riesgo"}],
    "wacc.beta_desapalancada": [{"id": "wacc.beta_fuente", "tipo": "texto", "oblig": False, "nota": "fuente y fecha (método bottom-up)"}],
    "wacc.prima": [{"id": "wacc.prima_justificacion", "tipo": "texto", "oblig": False, "nota": "obligatoria si la prima no es cero"}],
    "wacc.kd": [{"id": "wacc.kd_fuente", "tipo": "texto", "oblig": False, "nota": "fuente del coste de la deuda"}],
    "wacc.tipo_marginal": [{"id": "wacc.tipo_marginal_justificacion", "tipo": "texto", "oblig": False, "nota": "obligatoria si no es el 21 %"}],
}


@lru_cache(maxsize=1)
def esquema() -> List[dict]:
    """Los pasos del YAML, con los `valores` que remiten a la configuración ya resueltos en listas."""
    import yaml
    from ..umbrales import umbral
    datos = yaml.safe_load(_SPEC.read_text(encoding="utf-8"))
    sectores = yaml.safe_load((_SPEC.parent.parent.parent / "config" / "sectores.yaml").read_text(encoding="utf-8")) or {}

    def resolver(campo: dict) -> dict:
        c = dict(campo)
        v = c.get("valores")
        if v == "umbrales.recomendacion.escala":
            c["valores"] = list(umbral("recomendacion")["escala"])
        elif isinstance(v, str) and "paquetes" in v:
            c["valores"] = sorted((sectores.get("paquetes") or {}).keys())
        if c.get("campos"):
            c["campos"] = [resolver(x) for x in c["campos"]]
        return c
    pasos = []
    for p in datos["pasos"]:
        campos = []
        for c in p.get("campos", []):
            campos.append(resolver(c))
            campos += [dict(x) for x in _DERIVADOS.get(c["id"], [])]
        pasos.append({"paso": p["paso"], "numero": int(p["paso"].split("·")[0]), "campos": campos})
    return pasos


def ruta(ticker: str, fecha: date) -> Path:
    return entorno.carpeta("entradas") / ticker.upper() / fecha.isoformat() / "entradas.json"


def propuestas(ticker: str, fecha: date) -> List[dict]:
    """06 §1: los párrafos de plantilla de la última generación del informe de esa fecha, que `emitir.py` deja junto al
    PDF; el paso 9 los enseña para aceptarlos o editarlos."""
    from .propuestas import leer
    t = ticker.upper()
    return leer(entorno.carpeta("salida") / t / f"{t}_tesis_{fecha.isoformat()}.propuestas.json")


def fechas(ticker: str) -> List[str]:
    base = entorno.carpeta("entradas") / ticker.upper()
    return sorted(p.parent.name for p in base.glob("*/entradas.json")) if base.exists() else []


def _numero(texto) -> Optional[float]:
    m = re.search(r"-?\d+(?:[.,]\d+)?", str(texto or ""))
    return float(m.group(0).replace(",", ".")) if m else None


def migrar_posicion(datos: dict) -> Tuple[dict, List[str]]:
    """El fichero antiguo de `posiciones/` → los campos `pos.*` (solo se lee: `posiciones/` no se toca). Devuelve también
    lo que no se migra y por qué: el PO es el del motor y el horizonte, el de la valoración (se piden una sola vez)."""
    p, t, r, s = (datos.get(k) or {} for k in ("posicion", "tesis", "riesgo", "seguimiento"))
    pos: dict = {}
    notas: List[str] = []
    if p.get("recomendacion"):
        pos["recomendacion"] = str(p["recomendacion"]).capitalize()
    if p.get("precio_entrada") is not None:
        pos["precio_entrada"] = float(p["precio_entrada"])
    if p.get("fecha_entrada"):
        pos["fecha_entrada"] = str(p["fecha_entrada"])
    if p.get("tamano"):
        pos["tamano_pct"] = _numero(p["tamano"])
    if t.get("argumento"):
        pos["argumento"] = {"texto": t["argumento"]}
    if t.get("asunciones"):
        pos["asunciones"] = [{"texto": a} if isinstance(a, str) else a for a in t["asunciones"]]
    if datos.get("checklist"):
        pos["checklist"] = [{"criterio": c.get("criterio", ""), "tipo": "manual", "evidencia": c.get("evidencia", ""),
                             "cumplido": {True: "si", False: "no"}.get(c.get("cumplido"), "")} for c in datos["checklist"]]
    if r.get("invalidacion"):
        pos["invalidacion"] = [{"metrica": x} if isinstance(x, str) else x for x in r["invalidacion"]]
    if r.get("tamano_posicion"):
        pos["tamano_porque"] = {"texto": r["tamano_posicion"]}
    if s.get("kpis"):
        pos["kpis"] = [{"kpi": x} if isinstance(x, str) else x for x in s["kpis"]]
    if s.get("fechas_revision"):
        pos["fechas_revision"] = [str(x) for x in s["fechas_revision"]]
    if s.get("criterios_salida"):
        pos["salida"] = list(s["criterios_salida"])
    if p.get("precio_objetivo") is not None:
        notas.append(f"precio objetivo del fichero antiguo ({p['precio_objetivo']}) no se migra: el del informe es el del motor")
    if p.get("horizonte"):
        notas.append(f"horizonte del fichero antiguo («{p['horizonte']}») no se migra: se fija una sola vez en la valoración (paso 7)")
    if r.get("volatilidad"):
        notas.append("volatilidad del fichero antiguo no se migra: la calcula el sistema (apartado 29)")
    return pos, notas


def cargar(ticker: str, fecha: date) -> Tuple[dict, List[str]]:
    """(entradas, notas): las guardadas de esa fecha; si no hay, las del informe anterior marcadas «revisar» (04); si
    tampoco, las de `posiciones/<TICKER>.json` migradas. Siempre con la fecha del informe."""
    r = ruta(ticker, fecha)
    if r.exists():
        return json.loads(r.read_text(encoding="utf-8")), []
    notas: List[str] = []
    anteriores = [f for f in fechas(ticker) if f < fecha.isoformat()]
    if anteriores:
        datos = json.loads(ruta(ticker, date.fromisoformat(anteriores[-1])).read_text(encoding="utf-8"))
        datos["_revisar"] = True
        notas.append(f"precargado del informe del {anteriores[-1]}: todo queda por revisar")
    else:
        datos = {}
        vieja = entorno.RAIZ / "posiciones" / f"{ticker.upper()}.json"
        if vieja.exists():
            antigua = json.loads(vieja.read_text(encoding="utf-8"))
            datos["pos"], notas = migrar_posicion(antigua)
            if antigua.get("analista"):
                datos.setdefault("meta", {})["analista"] = antigua["analista"]
            notas.insert(0, f"migrado de posiciones/{ticker.upper()}.json (el fichero no se modifica)")
    datos.pop("_prueba", None)
    datos.setdefault("meta", {})["fecha_informe"] = fecha.isoformat()
    pos = datos.setdefault("pos", {})
    if not pos.get("checklist"):                     # los criterios manuales de config/checklist.yaml, para que los conteste
        from ..plantillas.parte_g import checklist
        pos["checklist"] = [{"id": c["id"], "criterio": c["texto"], "tipo": "manual", "eliminatorio": bool(c.get("eliminatorio"))}
                            for c in checklist()["criterios"] if c["tipo"] == "manual"]
    return datos, notas


def guardar(ticker: str, fecha: date, datos: dict) -> Path:
    """Escribe el fichero y guarda la versión anterior en `versiones/` (04: persistencia versionada)."""
    from .proponer import normalizar
    normalizar(datos)                          # lo confirmado y cambiado después ya no es la propuesta (F10)
    r = ruta(ticker, fecha)
    r.parent.mkdir(parents=True, exist_ok=True)
    if r.exists():
        (r.parent / "versiones").mkdir(exist_ok=True)
        shutil.copy2(r, r.parent / "versiones" / f"entradas-{datetime.now():%Y%m%d-%H%M%S-%f}.json")
    r.write_text(json.dumps(datos, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return r


def _vacio(v) -> bool:
    return v is None or v == "" or v == [] or v == {} or (isinstance(v, dict) and "texto" in v and not str(v["texto"]).strip())


def _texto(v) -> str:
    return str(v.get("texto", "")) if isinstance(v, dict) else str(v or "")


def _campo(c: dict, v, id_: str, faltas: List[str]) -> None:
    """La validación que dice el propio esquema: obligatorio, palabras, rango, listas (min, max, n) y valores."""
    oblig = c.get("oblig", False)                       # «condición» (texto): la valida el paso que la conoce
    if _vacio(v):
        if oblig is True:
            faltas.append(f"{id_}: obligatorio")
        return
    tipo = c.get("tipo")
    if c.get("palabras") and tipo == "texto":
        bajo, alto = (int(x) for x in str(c["palabras"]).split("-"))
        n = palabras(_texto(v))
        if not bajo <= n <= alto:
            faltas.append(f"{id_}: {n} palabras (se piden {bajo}–{alto})")
        from ..qa.linter import revisar                     # 06 §2 mientras se escribe; las cifras frente a los Hechos, al generar
        faltas += [f"{id_}: {r}" for r in revisar(_texto(v))]
    if tipo in ("numero", "pct") and not isinstance(v, (int, float)):
        faltas.append(f"{id_}: tiene que ser un número")
    elif tipo in ("numero", "pct") and c.get("rango"):
        partes = [x.replace(",", ".") for x in re.split(r"\s*[-–]\s*", str(c["rango"])) if x]
        if len(partes) == 2 and all(re.fullmatch(r"-?\d+(?:\.\d+)?", x) for x in partes):      # los que remiten a la configuración, en su paso
            if not float(partes[0]) <= float(v) <= float(partes[1]):
                faltas.append(f"{id_}: fuera del rango {c['rango']}")
    if tipo == "fecha":
        try:
            date.fromisoformat(str(v))
        except ValueError:
            faltas.append(f"{id_}: fecha AAAA-MM-DD")
    if tipo == "enum" and isinstance(c.get("valores"), list) and v not in c["valores"]:
        faltas.append(f"{id_}: «{v}» no es ninguno de {', '.join(map(str, c['valores']))}")
    if tipo in ("lista", "evidencia") and isinstance(v, list):
        if c.get("n") and len(v) != int(c["n"]):
            faltas.append(f"{id_}: {len(v)} (se piden {c['n']})")
        if c.get("min") and len(v) < int(c["min"]):
            faltas.append(f"{id_}: {len(v)} (mínimo {c['min']})")
        if c.get("max") and len(v) > int(c["max"]):
            faltas.append(f"{id_}: {len(v)} (máximo {c['max']})")
        for k, x in enumerate(v, 1):
            if isinstance(x, dict):
                for sub in c.get("campos") or []:
                    _campo(dict(sub, oblig=sub.get("oblig", True)), x.get(sub["id"]), f"{id_}[{k}].{sub['id']}", faltas)


def _paso9(ticker: str, fecha: date, e: Entradas) -> List[str]:
    """Cada propuesta de la última generación, aceptada o editada con su huella vigente; lo editado, por el linter."""
    from ..qa.linter import revisar
    from .propuestas import editadas
    revision = e.valor("revision.parrafos")
    revision = revision if isinstance(revision, dict) else {}
    faltas = []
    for p in propuestas(ticker, fecha):
        r = revision.get(p["id"])
        if not isinstance(r, dict) or not r.get("frases"):
            faltas.append(f"revision.parrafos: «{p['titulo']}» sin aceptar ni editar")
        elif r.get("propuesta") != p.get("huella"):
            faltas.append(f"revision.parrafos: «{p['titulo']}» cambió desde que lo validó (los datos son otros): vuelva a aceptarlo o editarlo")
        elif not any(isinstance(x, list) and x and str(x[0]).strip() for x in r["frases"]):
            faltas.append(f"revision.parrafos: «{p['titulo']}» sin ninguna frase: se edita, no se borra entero")
    return faltas + [f"{id_}: {x}" for id_, t in editadas(revision) for x in revisar(t)]


def validar(ticker: str, fecha: date, datos: dict, regla: Optional[Tuple[str, float, Optional[float]]] = None) -> Tuple[Dict[int, List[str]], List[str]]:
    """({paso: faltas}, avisos). `regla`: (recomendación de la regla, potencial, recorrido/riesgo) si ya hay motor."""
    from ..fuentes import precio
    from ..motor.supuestos import leer
    from ..plantillas.parte_g import checklist
    from ..umbrales import umbral
    e = Entradas(datos)
    salida: Dict[int, List[str]] = {}
    for p in esquema():
        faltas: List[str] = []
        for c in p["campos"]:
            if c.get("tipo") in ("solo_lectura", "accion", "archivo", "escenarios") or p["numero"] == 2:
                continue
            _campo(c, e.valor(c["id"]), c["id"], faltas)
        salida[p["numero"]] = faltas
    try:                                              # v1: financieras, REIT y biotech sin ingresos se bloquean en el paso 1
        from ..fuentes import sec
        from ..motor.datos import ingresos_anuales, paquete_por_sic, sectores
        em = sec.emisor(ticker)
        ingresos = None
        if any(a <= int(em.sic) <= b for a, b in (sectores().get("bloqueo_biotech") or {}).get("sic", [])):   # solo si puede serlo
            facts, obtenido = sec.companyfacts(em.cik)
            ingresos = ingresos_anuales(facts, obtenido)
        _, bloqueo = paquete_por_sic(em.sic, ingresos)
        if bloqueo:
            salida[1].insert(0, f"meta.sector: bloqueo v1 — {bloqueo}")
    except Exception:                                 # sin EDGAR no se sabe el SIC: lo dirá el informe al generarse
        pass
    # F10: lo confirmado desde una propuesta cuyos datos han cambiado vuelve a «revisar», en el paso de su campo
    from .proponer import caducadas, confirmados, proponer
    paso_de = {c["id"]: p["numero"] for p in esquema() for c in p["campos"]}
    ya = confirmados(datos)
    for falta in (caducadas(datos, proponer(ticker, fecha, datos, ya)) if ya else []):
        salida.setdefault(paso_de.get(falta.split(":")[0], 9), []).append(falta)
    if e.valor("esc"):
        salida[7] += leer(datos, fecha).faltas
    salida[9] = salida.get(9, []) + _paso9(ticker, fecha, e)
    val = e.valor("meta.fecha_valoracion")
    fv = date.fromisoformat(str(val)) if val else fecha
    try:
        sesiones = precio.sesiones_nasdaq(ticker.upper(), precio.desde_5a(fv), fv, limite=2000)
    except Exception:
        sesiones = {}

    def rango(dia):
        s = sesiones.get(dia)
        return (s.minimo, s.maximo) if s is not None and s.minimo is not None and s.maximo is not None else None
    cl = checklist()
    f8, avisos = comprobar_paso8(e, fecha, rango, *(regla or (None, None, None)), escala=umbral("recomendacion")["escala"],
                                 tamano_max=cl["tamano_max"], riesgo_max=cl["riesgo_max_posicion"])
    # las del esquema que la comprobación del paso 8 dice mejor (con su motivo) no se repiten
    propias = {x.split(":")[0].split("[")[0] for x in f8}
    salida[8] = [x for x in salida[8] if x.split(":")[0].split("[")[0] not in propias] + f8
    from ..qa.linter import avisos_entradas                  # 02: frases y párrafos largos, mientras escribe (avisan, no bloquean)
    return salida, avisos + avisos_entradas(e)
