"""Parte I (apartados 36–39): el modelo y sus entradas, las fuentes con su huella, las notas metodológicas en una página
como máximo y la documentación (citas literales y fuentes consultadas). Ni registros internos ni JSON: el detalle
completo va a `auditoria.json`.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

from ..formato import Celda, fecha as f_fecha, numero, pct
from ..rutas import CONFIG

__all__ = ["ParteI", "construir", "HUECOS_MAX"]

HUECOS_MAX = 15                      # 01 › 38: huecos materiales, 15 líneas; el resto en auditoria.json
_DEFINICIONES = CONFIG / "definiciones.yaml"
_APARTADO = {"perfil": "4", "equipo": "6", "direccion": "6", "catalizadores": "7", "mercado": "21", "competencia": "22", "moat": "23",
             "riesgos": "24", "historial": "26", "pilares": "3"}


@dataclass
class ParteI:
    cuadros: Dict[str, object] = field(default_factory=dict)     # entradas, proyeccion (36) · documentos, apis (37) · citas, fuentes (39)
    excel: str = ""
    entradas: str = ""                                           # fichero de entradas y su huella (37)
    huecos: List[str] = field(default_factory=list)
    huecos_resto: int = 0
    definiciones: List[str] = field(default_factory=list)
    cuadres: List[str] = field(default_factory=list)             # uno por cuadro, con sus comprobaciones seguidas
    ajenas: List[str] = field(default_factory=list)              # partidas que la compañía no tiene: no son huecos (regla 10)


@lru_cache(maxsize=1)
def _definiciones() -> List[str]:
    import yaml
    return list(yaml.safe_load(_DEFINICIONES.read_text(encoding="utf-8")) or [])


def _c(t: str, nota: str = "", capa: str = "S") -> Celda:
    return Celda(t, "", capa, "valor", nota)


def _serie(v) -> str:
    if isinstance(v, (list, tuple)) and v:
        return f"año 1: {pct(v[0])} · año {len(v)}: {pct(v[-1])}" if len(v) > 1 else pct(v[0])
    return pct(v) if isinstance(v, (int, float)) else "—"


def _modelo(d: ParteI, n, motor, autor: str) -> None:
    from .informe import Cuadro, FilaCuadro
    v = getattr(motor, "valoracion", None)
    if v is None:
        return
    p, w = v.parametros, v.wacc
    filas = [
        ("Fecha de valoración", f_fecha(p.fecha_valoracion), "fecha", "paso 1", autor),
        ("Horizonte del precio objetivo", numero(p.horizonte_meses), "meses", "paso 7", autor),
        ("Periodo explícito", numero(p.periodo), "años", "paso 7", autor),
        ("Convención de mitad de año", "sí" if p.mitad_de_anio else "no", "", "paso 7", autor),
        ("Retribución en acciones", p.sbc_politica.replace("_", " "), "", "paso 7", autor),
        ("Paquete sectorial", p.paquete.replace("_", " "), "", "paso 1" if p.paquete_confirmado else "SIC de la SEC",
         autor if p.paquete_confirmado else "sistema"),
        ("Tipo sin riesgo", pct(w.rf, 2), "%", f"Tesoro de EE. UU., 10 años, {f_fecha(w.rf_fecha)}", "sistema"),
        ("Prima de riesgo de mercado", pct(p.erp), "%", p.erp_fuente or "paso 7", autor),
        ("Beta", numero(w.beta, 2), "", w.beta_origen, "sistema"),
        ("Coste de la deuda antes de impuestos", pct(w.kd, 2), "%", w.kd_origen, autor),
        ("Tipo impositivo marginal", pct(p.tipo_marginal, 0), "%", "paso 7", autor),
        ("WACC", pct(w.wacc, 2), "%", "motor (05 §4)", "sistema"),
        ("Método del valor terminal", p.tv_metodo.replace("_", " "), "", "paso 7", autor),
    ]
    for nombre, e in p.escenarios.items():
        filas += [(f"{nombre.capitalize()} · probabilidad", pct(e.probabilidad, 0), "%", "paso 7", autor),
                  (f"{nombre.capitalize()} · crecimiento de ingresos", _serie(e.crecimiento), "%", "paso 7", autor),
                  (f"{nombre.capitalize()} · margen EBIT", _serie(e.margen), "%", "paso 7", autor),
                  (f"{nombre.capitalize()} · crecimiento terminal", pct(e.g, 2), "%", "paso 7", autor)]
    d.cuadros["entradas"] = Cuadro(n.siguiente(), "Entradas del modelo", ["Valor", "Unidad", "Origen", "Autor"],
                                   [FilaCuadro(r, [Celda(val, "", "S", "valor", "", "horizonte" if r == "Horizonte del precio objetivo" else ""),
                                                   _c(u), _c(o), _c(a)], capa="S") for r, val, u, o, a in filas],
                                   "Fuente: entradas del paso 7 y cálculos del motor de valoración (05).", partible=True)
    pr = v.base.proyeccion
    columnas = [str(c.year) for c in pr.cierres]
    lineas = (("Ingresos", pr.ingresos, 0), ("EBIT", pr.ebit, 0), ("Impuestos", pr.impuestos, 0), ("NOPAT", pr.nopat, 0), ("D&A", pr.da, 0),
              ("Capex", pr.capex, 0), ("Δ fondo de maniobra", pr.dfm, 0), ("SBC", pr.sbc, 0), ("FCFF", pr.fcff, 0))
    filas = [FilaCuadro(r, [_c(numero(x / 1e6), pr.formulas.get(r.lower(), ""), "D") for x in serie], capa="D", destacada=r == "FCFF")
             for r, serie, _ in lineas]
    filas.append(FilaCuadro("Factor de descuento", [_c(numero(x, 3), pr.formulas.get("factores", ""), "D") for x in pr.factores], capa="D"))
    filas.append(FilaCuadro("Valor actual", [_c(numero(x / 1e6), pr.formulas.get("valor_actual", ""), "D") for x in pr.valor_actual], capa="D",
                            destacada=True))
    d.cuadros["proyeccion"] = Cuadro(n.siguiente(), "Proyección completa del escenario base (mln USD)", columnas, filas,
                                     f"Fuente: motor de valoración (05 §3); año 1 por la fracción {numero(pr.fraccion, 3)} del ejercicio en curso.",
                                     partible=True)


def _citas(e, item) -> List[Tuple[str, str, str]]:
    """(apartado, documento y página, texto original) de cada evidencia del analista: el literal solo va aquí y en el HTML."""
    salida: List[Tuple[str, str, str]] = []

    def recorrer(x, apartado):
        if isinstance(x, dict):
            if x.get("doc") and x.get("texto"):
                salida.append((apartado, x["doc"] + (f", pág. {x['pag']}" if x.get("pag") else ""), str(x["texto"])))
                return
            for v in x.values():
                recorrer(v, apartado)
        elif isinstance(x, list):
            for v in x:
                recorrer(v, apartado)
    for clave, apartado in _APARTADO.items():
        recorrer(e.datos.get(clave), apartado)
    if item is not None:
        from ..datos.item1a import buscar
        for r in (e.valor("riesgos.top") or []):
            ep = buscar(item, (r.get("origen") or {}).get("epigrafe", "")) if (r.get("origen") or {}).get("epigrafe") else None
            if ep is not None:
                salida.append(("24", f"10-K, Item 1A, pág. {ep.pagina}", ep.texto))
    orden = {a: k for k, a in enumerate(["3", "4", "6", "7", "21", "22", "23", "24", "26"])}
    vistas, unicas = set(), []
    for fila in sorted(salida, key=lambda x: orden.get(x[0], 99)):
        if fila not in vistas:
            vistas.add(fila)
            unicas.append(fila)
    return unicas


def _fuentes(d: ParteI, n, emisor) -> None:
    from ..fuentes import precio, sec, yahoo
    from .informe import Cuadro, FilaCuadro
    docs, apis = [], []
    depositos = {x.accession.replace("-", ""): x for x in getattr(emisor, "depositos", []) or []}
    for url, (obtenido, huella) in sorted(sec.CONSULTADOS.items()):
        if "/Archives/edgar/data/" in url and not url.endswith("index.json"):
            partes = url.split("/")
            dep = depositos.get(partes[-2]) if len(partes) > 2 else None
            tipo = dep.formulario if dep is not None else "EDGAR"
            docs.append(FilaCuadro(tipo, [_c(f_fecha(dep.periodo) if dep is not None and dep.periodo else "—"),
                                          _c(f_fecha(dep.presentado) if dep is not None else "—"), _c(dep.accession if dep is not None else partes[-2]),
                                          _c("sí"), _c(huella[:12], f"sha256 {huella} · {url}")], capa="H"))
        elif "data.sec.gov" in url:
            apis.append((url, f_fecha(obtenido), huella))
    for url, (cuerpo, hora) in sorted(precio._CRUDOS.items()):
        apis.append((url, hora.strftime("%d/%m/%Y %H:%M"), hashlib.sha256(cuerpo.encode("utf-8")).hexdigest()))
    for url, (cuerpo, hora) in sorted(yahoo.cliente().crudos.items()) if yahoo._CLIENTE is not None else []:
        apis.append((url, hora.strftime("%d/%m/%Y %H:%M"), hashlib.sha256(cuerpo.encode("utf-8")).hexdigest()))
    if docs:
        d.cuadros["documentos"] = Cuadro(n.siguiente(), "Documentos de EDGAR", ["Periodo", "Presentado", "Nº de registro", "Verificado en EDGAR", "Huella"],
                                         docs, "Fuente: SEC EDGAR; la huella es el sha256 de la copia guardada (completa, en el HTML).", partible=True)
    if apis:
        d.cuadros["apis"] = Cuadro(n.siguiente(), "Consultas a las fuentes de datos", ["Hora", "Huella"],
                                   [FilaCuadro(_corta(u), [_c(h, u), _c(x[:12], f"sha256 {x}")], capa="H") for u, h, x in apis],
                                   "SEC EDGAR (API de datos), Nasdaq, Tesoro de EE. UU. y Yahoo Finance (solo volatilidad implícita); respuesta completa guardada en disco.",
                                   partible=True)


def _corta(url: str, largo: int = 70) -> str:
    """La URL sin el esquema y recortada (entera, en el atributo title): una celda no puede ser más ancha que la página."""
    u = url.split("://", 1)[-1]
    return u if len(u) <= largo else u[:largo - 1] + "…"


def _por_cuadro(cuadres: Sequence[str]) -> List[str]:
    """«Cuadro 3 (…): ✓ a» + «Cuadro 3 (…): ✓ b» → «Cuadro 3 (…): ✓ a · ✓ b»: el cuadro se nombra una vez."""
    grupos: Dict[str, List[str]] = {}
    for c in cuadres:
        cabeza, _, nota = c.partition("): ")
        grupos.setdefault(cabeza + ")" if nota else "", []).append(nota or c)
    return [f"{k}: {' · '.join(v)}" if k else " · ".join(v) for k, v in grupos.items()]


def construir(n, motor, pb, emisor, huecos: Sequence[str], excel: Optional[Tuple[str, str]] = None,
              cuadres: Sequence[str] = (), ajenas: Sequence[str] = ()) -> ParteI:
    """`pb`: parte_b.ParteB (entradas, alias, Item 1A). `excel`: (nombre, sha256) del libro exportado por el motor, si lo hubo.
    `huecos`, ya agrupados por partida; `cuadres`, las notas de cuadre que salieron de los cuadros."""
    from .informe import Cuadro, FilaCuadro
    d = ParteI(definiciones=_definiciones(), cuadres=_por_cuadro(cuadres), ajenas=list(ajenas))
    e = pb.entradas
    autor = "analista (entradas de PRUEBA)" if e.de_prueba else "analista"
    _modelo(d, n, motor, autor)
    if excel:
        d.excel = f"Libro exportado por el motor: {excel[0]} · sha256 {excel[1][:12]} (fórmulas vivas; el recálculo coincide con el motor)."
    ruta = getattr(e, "ruta", None)
    cuerpo = json.dumps(e.datos, ensure_ascii=False, sort_keys=True)
    quien = ", ".join(x for x in (str(e.valor("meta.analista") or ""), {"inicio_cobertura": "inicio de cobertura", "actualizacion": "actualización"}
                                   .get(str(e.valor("meta.tipo") or ""), "")) if x)
    d.entradas = (f"Entradas del analista{f' ({quien})' if quien else ''}: {Path(ruta).name if ruta else 'sin fichero'} · sha256 "
                  f"{hashlib.sha256(cuerpo.encode('utf-8')).hexdigest()[:12]}" + (" (entradas de PRUEBA)" if e.de_prueba else ""))
    _fuentes(d, n, emisor)
    citas = _citas(e, getattr(pb, "item1a", None))
    if citas:
        d.cuadros["citas"] = Cuadro(n.siguiente(), "Citas literales de las evidencias, por apartado", ["Documento", "Texto original"],
                                    [FilaCuadro(f"Apartado {a}", [_c(doc), _c(t)], capa="S") for a, doc, t in citas],
                                    "El texto original de cada evidencia; en el cuerpo del informe se imprime la versión en español.", partible=True)
    lista = list(huecos)
    d.huecos, d.huecos_resto = lista[:HUECOS_MAX], max(0, len(lista) - HUECOS_MAX)
    return d
