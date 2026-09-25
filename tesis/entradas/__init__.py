"""Entradas del analista (`docs/spec/04_entradas.yaml`), por id («perfil.descripcion», «catalizadores»…).

Hasta que exista el asistente web (F6) se leen de un JSON con el mismo esquema: `<datos>/entradas/<TICKER>/<fecha>/
entradas.json`, o la ruta que se pase. Las de prueba (`tests/fixtures/<TICKER>/entradas.json`) llevan `"_prueba"` y el
informe lo dice.

Las evidencias son citas {doc[, pag], texto[, texto_es]} que se verifican contra el texto del documento (03 §6): el texto
normalizado tiene que aparecer (similitud ≥ `umbrales.cita_similitud_min`) y sus cifras, coincidir. Con página, en esa
página (el folio impreso del documento de EDGAR; puede seguir en la siguiente, pero tiene que empezar en la suya).
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

__all__ = ["Entradas", "cargar", "normalizar", "verificar_cita", "comprobar_paso1", "comprobar_paso3", "comprobar_paso4", "comprobar_paso5", "comprobar_paso6", "comprobar_paso8", "palabras"]


@dataclass
class Entradas:
    datos: Dict[str, Any] = field(default_factory=dict)
    ruta: Optional[Path] = None

    @property
    def de_prueba(self) -> bool:
        return bool(self.datos.get("_prueba"))

    def valor(self, id_: str, defecto: Any = None) -> Any:
        actual: Any = self.datos
        for parte in id_.split("."):
            if not isinstance(actual, dict) or parte not in actual:
                return defecto
            actual = actual[parte]
        return actual


def cargar(ticker: str, fecha: Optional[date] = None, ruta: Optional[Path] = None) -> Entradas:
    from .. import entorno
    candidatas = [ruta] if ruta else []
    if fecha is not None:
        candidatas.append(entorno.carpeta("entradas") / ticker.upper() / fecha.isoformat() / "entradas.json")
    for c in candidatas:
        if c is not None and Path(c).exists():
            return Entradas(json.loads(Path(c).read_text(encoding="utf-8")), Path(c))
    return Entradas()


def normalizar(texto: str) -> str:
    t = unicodedata.normalize("NFKC", texto)
    t = t.translate(str.maketrans({"“": '"', "”": '"', "‘": "'", "’": "'", "–": "-", "—": "-", " ": " ", "​": ""}))
    return " ".join(t.lower().split())


def palabras(texto: str) -> int:
    return len(re.findall(r"\w+", texto or ""))


def _cifras(texto: str) -> List[str]:
    return [c.replace(",", "") for c in re.findall(r"\d[\d,]*(?:\.\d+)?", texto)]


def verificar_cita(cita: Mapping[str, Any], textos: Mapping[str, str], umbral: float) -> Tuple[bool, str]:
    """(válida, motivo). `textos`: documento → texto plano (el 10-K, la DEF 14A, cada Ex. 99.1 por «8-K AAAA-MM-DD»…)
    y «documento#página» → texto de esa página."""
    doc, literal, pag = cita.get("doc", ""), cita.get("texto", ""), cita.get("pag")
    if not doc or not literal:
        return False, "cita sin documento o sin texto"
    if doc not in textos:
        citables = ", ".join(sorted({k.split("#")[0] for k in textos}))
        return False, f"documento «{doc}» no disponible para verificar (se pueden citar: {citables or 'ninguno'})"
    buscado = normalizar(literal)
    if pag in (None, ""):
        cuerpo = normalizar(textos[doc])
        completo, donde = cuerpo, f"«{doc}»"
    else:
        clave = f"{doc}#{pag}"
        if clave not in textos:
            return False, f"«{doc}» no tiene página {pag} para verificar"
        claves = [k for k in textos if k.startswith(f"{doc}#")]
        i = claves.index(clave)
        cuerpo = normalizar(textos[clave])
        siguiente = normalizar(textos[claves[i + 1]])[:len(buscado)] if i + 1 < len(claves) else ""
        completo, donde = (f"{cuerpo} {siguiente}" if siguiente else cuerpo), f"la página {pag} de «{doc}»"
    if 0 <= completo.find(buscado) < len(cuerpo):
        return True, f"literal en {donde}"
    # el trozo más parecido: se ancla en la coincidencia más larga y se compara una ventana del mismo largo
    m = SequenceMatcher(None, completo, buscado, autojunk=False).find_longest_match(0, len(completo), 0, len(buscado))
    inicio = max(0, m.a - m.b)
    ventana = completo[inicio:inicio + len(buscado)]
    similitud = SequenceMatcher(None, ventana, buscado, autojunk=False).ratio() if inicio < len(cuerpo) else 0.0
    if similitud < umbral:
        return False, f"el texto no aparece en {donde} (similitud {similitud:.2f} < {umbral:.2f})"
    faltan = [c for c in _cifras(literal) if c not in _cifras(ventana)]
    if faltan:
        return False, f"cifras que no coinciden con {donde}: {', '.join(faltan)}"
    return True, f"similitud {similitud:.2f}"


def _rango(id_: str, texto: str, rango: str, faltas: List[str]) -> None:
    bajo, alto = (int(x) for x in rango.split("-"))
    n = palabras(texto)
    if not bajo <= n <= alto:
        faltas.append(f"{id_}: {n} palabras (se piden {bajo}–{alto})")


def comprobar_paso4(e: Entradas, textos: Mapping[str, str], umbral: float, hoy: date) -> List[str]:
    """Las faltas del paso 4 (apartados 4–7) que la puerta de calidad convertirá en bloqueo al emitir."""
    faltas: List[str] = []
    descripcion = e.valor("perfil.descripcion") or {}
    if not descripcion.get("texto"):
        faltas.append("perfil.descripcion: falta el texto del analista (apartado 4)")
    else:
        _rango("perfil.descripcion", descripcion["texto"], "80-200", faltas)
    if e.valor("perfil.segmentos_ok") is not True:
        faltas.append("perfil.segmentos_ok: el analista no ha confirmado el cuadro de segmentos")
    track = e.valor("equipo.track_record") or []
    if len(track) < 2:
        faltas.append("equipo.track_record: mínimo CEO y CFO")
    for t in track:
        _rango(f"equipo.track_record[{t.get('persona', '?')}]", t.get("texto", ""), "20-60", faltas)
        for c in t.get("evidencias", []):
            ok, motivo = verificar_cita(c, textos, umbral)
            if not ok:
                faltas.append(f"equipo.track_record[{t.get('persona', '?')}]: {motivo}")
    asignacion = e.valor("equipo.asignacion_capital") or {}
    if not asignacion.get("texto"):
        faltas.append("equipo.asignacion_capital: falta el texto del analista")
    else:
        _rango("equipo.asignacion_capital", asignacion["texto"], "30-80", faltas)
    catalizadores = e.valor("catalizadores") or []
    if len(catalizadores) < 3:
        faltas.append(f"catalizadores: {len(catalizadores)} (mínimo 3)")
    for i, c in enumerate(catalizadores, 1):
        fecha = str(c.get("fecha", ""))
        m = re.fullmatch(r"(\d{4})-(\d\d)-(\d\d)", fecha)
        if m and date(*map(int, m.groups())) < hoy:
            faltas.append(f"catalizadores[{i}]: fecha pasada ({fecha})")
        elif not m and not re.fullmatch(r"\d{4}-T[1-4]", fecha):
            faltas.append(f"catalizadores[{i}]: fecha «{fecha}» (AAAA-MM-DD o AAAA-Tn)")
        if not c.get("evidencia"):
            faltas.append(f"catalizadores[{i}]: sin evidencia")
        for ev in c.get("evidencia", []):
            ok, motivo = verificar_cita(ev, textos, umbral)
            if not ok:
                faltas.append(f"catalizadores[{i}]: {motivo}")
    for i, c in enumerate(e.valor("direccion.citas") or [], 1):
        ok, motivo = verificar_cita(c, textos, umbral)
        if not ok:
            faltas.append(f"direccion.citas[{i}]: {motivo}")
        if not c.get("texto_es"):
            faltas.append(f"direccion.citas[{i}]: falta la versión en español (texto_es)")
    return faltas


_CLASES_MERCADO = ("TAM", "SAM", "SOM")
_METODOS_MERCADO = ("top_down", "bottom_up", "declarado_compania")
_FOSOS = ("efectos_de_red", "costes_de_cambio", "intangibles", "ventaja_de_costes", "escala_eficiente", "ninguno")
_TENDENCIAS = ("se_amplia", "estable", "se_estrecha")


def _citas(id_: str, lista, textos: Mapping[str, str], umbral: float, faltas: List[str], minimo: int = 1) -> None:
    """Evidencias que se imprimen: verificadas en su documento (y página) y con su versión en español."""
    lista = list(lista or [])
    if len(lista) < minimo:
        faltas.append(f"{id_}: sin evidencia (mínimo {minimo})")
    for c in lista:
        ok, motivo = verificar_cita(c, textos, umbral)
        if not ok:
            faltas.append(f"{id_}: {motivo}")
        if not c.get("texto_es"):
            faltas.append(f"{id_}: falta la versión en español de la evidencia (texto_es)")


def comprobar_paso5(e: Entradas, textos: Mapping[str, str], umbral: float) -> List[str]:
    """Las faltas del paso 5 (apartados 21–23): mercado, competencia, comparables y foso defensivo."""
    faltas: List[str] = []
    cifras = e.valor("mercado.cifras") or []
    if not any(c.get("clase") == "TAM" for c in cifras):
        faltas.append("mercado.cifras: falta al menos un TAM")
    for i, c in enumerate(cifras, 1):
        id_ = f"mercado.cifras[{i}]"
        if c.get("clase") not in _CLASES_MERCADO:
            faltas.append(f"{id_}: clase «{c.get('clase')}» (TAM, SAM o SOM)")
        if c.get("metodo") not in _METODOS_MERCADO:
            faltas.append(f"{id_}: método «{c.get('metodo')}» ({', '.join(_METODOS_MERCADO)})")
        if not isinstance(c.get("valor"), (int, float)) or c["valor"] <= 0:
            faltas.append(f"{id_}: el valor tiene que ser un número positivo")
        if not (c.get("etiqueta") and c.get("unidad") and c.get("anio")):
            faltas.append(f"{id_}: etiqueta, unidad y año son obligatorios")
        _citas(id_, c.get("evidencia"), textos, umbral, faltas)
    competidores = e.valor("competencia.competidores") or []
    if len(competidores) < 3:
        faltas.append(f"competencia.competidores: {len(competidores)} (mínimo 3)")
    for i, c in enumerate(competidores, 1):
        id_ = f"competencia.competidores[{c.get('nombre') or i}]"
        if not c.get("nombre"):
            faltas.append(f"{id_}: falta el nombre")
        _rango(f"{id_}.por_que", c.get("por_que", ""), "5-25", faltas)
        _citas(id_, c.get("evidencia"), textos, umbral, faltas, minimo=0)
        if c.get("cuota") is not None:
            _citas(f"{id_}.cuota", c.get("cuota_evidencia"), textos, umbral, faltas)
    comparables = e.valor("comparables") or []
    if not 3 <= len(comparables) <= 10:
        faltas.append(f"comparables: {len(comparables)} (entre 3 y 10)")
    for c in comparables:
        _rango(f"comparables[{c.get('ticker', '?')}].justificacion", c.get("justificacion", ""), "5-25", faltas)
    fuentes = e.valor("moat.fuentes") or []
    if not fuentes:
        faltas.append("moat.fuentes: mínimo una fuente del foso defensivo (o «ninguno», con evidencia)")
    for i, f in enumerate(fuentes, 1):
        id_ = f"moat.fuentes[{i}]"
        if f.get("tipo") not in _FOSOS:
            faltas.append(f"{id_}: tipo «{f.get('tipo')}» ({', '.join(_FOSOS)})")
        if f.get("tendencia") not in _TENDENCIAS:
            faltas.append(f"{id_}: tendencia «{f.get('tendencia')}» ({', '.join(_TENDENCIAS)})")
        if not isinstance(f.get("durabilidad_anios"), (int, float)) or f["durabilidad_anios"] <= 0:
            faltas.append(f"{id_}: durabilidad en años, número positivo")
        _citas(id_, f.get("evidencias"), textos, umbral, faltas)
    amenazas = e.valor("moat.amenazas")
    texto = amenazas.get("texto", "") if isinstance(amenazas, dict) else (amenazas or "")
    if not texto:
        faltas.append("moat.amenazas: falta el texto del analista (20–80 palabras)")
    else:
        _rango("moat.amenazas", texto, "20-80", faltas)
    return faltas


_FAMILIAS_RIESGO = ("regulatorio", "financiero", "competitivo", "ejecucion")


def comprobar_paso6(e: Entradas, textos: Mapping[str, str], umbral: float, es_epigrafe, fallos: Sequence[str] = ()) -> List[str]:
    """Las faltas del paso 6 (apartados 24–26). `es_epigrafe(comienzo)`: si es un epígrafe del Item 1A. `fallos`: los
    trimestres que fallan por más de `umbrales.fallo_guia_obliga_causas` (con ellos, las causas son obligatorias)."""
    faltas: List[str] = []
    top = e.valor("riesgos.top") or []
    if len(top) != 5:
        faltas.append(f"riesgos.top: {len(top)} (se piden 5)")
    for i, r in enumerate(top, 1):
        id_ = f"riesgos.top[{i}]"
        origen = r.get("origen") or {}
        if origen.get("epigrafe"):
            if not es_epigrafe(origen["epigrafe"]):
                faltas.append(f"{id_}.origen: «{origen['epigrafe'][:60]}» no es el comienzo de un epígrafe del Item 1A")
        else:
            _citas(f"{id_}.origen", origen.get("evidencia"), textos, umbral, faltas)
        _rango(f"{id_}.texto_es", r.get("texto_es", ""), "8-40", faltas)
        if r.get("familia") not in _FAMILIAS_RIESGO:
            faltas.append(f"{id_}.familia: «{r.get('familia')}» ({', '.join(_FAMILIAS_RIESGO)})")
        for k in ("probabilidad", "impacto"):
            v = r.get(k)
            if not isinstance(v, int) or not 1 <= v <= 5:
                faltas.append(f"{id_}.{k}: entero de 1 a 5")
        _rango(f"{id_}.mitigante", r.get("mitigante", ""), "5-40", faltas)
        if not r.get("senal"):
            faltas.append(f"{id_}.senal: falta la señal temprana")
    disparadores = e.valor("bear.disparadores") or []
    if len(disparadores) < 3:
        faltas.append(f"bear.disparadores: {len(disparadores)} (mínimo 3)")
    for i, d in enumerate(disparadores, 1):
        id_ = f"bear.disparadores[{i}]"
        _rango(f"{id_}.descripcion", d.get("descripcion", ""), "5-30", faltas)
        if not d.get("metrica") or not isinstance(d.get("umbral"), (int, float)) or not d.get("plazo"):
            faltas.append(f"{id_}: métrica, umbral numérico y plazo son obligatorios")
        driver = str(d.get("driver", ""))
        if not driver.startswith("esc.pesimista.") or e.valor(driver) is None:
            faltas.append(f"{id_}.driver: «{driver}» no es un supuesto del escenario pesimista")
    for i, g in enumerate(e.valor("historial.guia_manual") or [], 1):
        _citas(f"historial.guia_manual[{i}]", g.get("evidencia"), textos, umbral, faltas)
    causas = e.valor("historial.causas")
    texto = causas.get("texto", "") if isinstance(causas, dict) else (causas or "")
    if fallos and not texto:
        faltas.append(f"historial.causas: obligatorias por {len(fallos)} fallo(s) por encima del umbral ({'; '.join(fallos)})")
    elif texto:
        _rango("historial.causas", texto, "30-150", faltas)
    return faltas


def _es(v: float, decimales: int = 2) -> str:
    """Un número con coma decimal y punto de millares, como en el informe."""
    return f"{v:,.{decimales}f}".replace(",", " ").replace(".", ",").replace(" ", ".")


def _texto_de(v) -> str:
    return (v.get("texto", "") if isinstance(v, dict) else (v or "")).strip() if v is not None else ""


def comprobar_paso1(e: Entradas, fecha_informe: date, paquetes: Sequence[str], bloqueo_v1: Optional[str] = None) -> List[str]:
    """Faltas del paso 1 (04: metadatos y clasificación), que al generar bloquean como cualquier obligatorio (06 §3.1).
    `paquetes`: los de `config/sectores.yaml`; `bloqueo_v1`: el motivo si el emisor queda fuera de la v1 (05 §2)."""
    faltas: List[str] = []
    for id_ in ("meta.analista", "meta.fecha_valoracion", "meta.tipo", "meta.nombre_presentacion", "meta.sector"):
        if not str(e.valor(id_) or "").strip():
            faltas.append(f"{id_}: obligatorio (paso 1)")
    fv = e.valor("meta.fecha_valoracion")
    if fv:
        try:
            if date.fromisoformat(str(fv)) > fecha_informe:
                faltas.append(f"meta.fecha_valoracion: {date.fromisoformat(str(fv)):%d/%m/%Y} es posterior a la fecha del informe")
        except ValueError:
            faltas.append("meta.fecha_valoracion: fecha AAAA-MM-DD")
    tipo = e.valor("meta.tipo")
    if tipo and tipo not in ("inicio_cobertura", "actualizacion"):
        faltas.append(f"meta.tipo: «{tipo}» no es inicio de cobertura ni actualización")
    sector = e.valor("meta.sector")
    if sector and sector not in paquetes:
        faltas.append(f"meta.sector: «{sector}» no es un paquete sectorial de 05 §2")
    nombre = str(e.valor("meta.nombre_presentacion") or "")
    if re.search(r"/[A-Z]{2}\b|common stock", nombre, re.I):
        faltas.append(f"meta.nombre_presentacion: «{nombre}» lleva sufijo de estado o «Common Stock»")
    if bloqueo_v1:
        faltas.insert(0, f"meta.sector: bloqueo v1 — {bloqueo_v1}")
    return faltas


def comprobar_paso8(e: Entradas, fecha_informe: date, rango_sesion, regla: Optional[str] = None, potencial: Optional[float] = None,
                    recorrido_riesgo: Optional[float] = None, escala: Sequence[str] = ("Comprar", "Mantener", "Vender"),
                    tamano_max: float = 0.10, riesgo_max: float = 0.01) -> Tuple[List[str], List[str]]:
    """(faltas, avisos) del paso 8 (apartados 27–30). `rango_sesion(fecha)` → (mínimo, máximo) de esa sesión de Nasdaq o
    None; `regla`: la recomendación que sugiere la regla de `umbrales.recomendacion` con el potencial y el recorrido/riesgo
    del motor. Tamaño y horizonte se piden una sola vez: el horizonte es el de la valoración (`val.horizonte_meses`)."""
    faltas: List[str] = []
    avisos: List[str] = []
    rec = e.valor("pos.recomendacion")
    if rec not in escala:
        faltas.append(f"pos.recomendacion: una de {', '.join(escala)}")
    elif regla and rec != regla and palabras(_texto_de(e.valor("pos.recomendacion_justificacion"))) < 20:
        datos = []
        if potencial is not None:
            datos.append(f"potencial {_es(potencial * 100, 1)} %")
        if recorrido_riesgo is not None:
            datos.append(f"recorrido/riesgo {_es(recorrido_riesgo)}")
        faltas.append(f"pos.recomendacion: «{rec}» difiere de la regla («{regla}»{': ' + ', '.join(datos) if datos else ''}); "
                      "exige una justificación de 20 palabras o más")
    precio, fecha = e.valor("pos.precio_entrada"), e.valor("pos.fecha_entrada")
    try:
        dia = date.fromisoformat(str(fecha)) if fecha else None
    except ValueError:
        dia = None
    if not isinstance(precio, (int, float)) or precio <= 0:
        faltas.append("pos.precio_entrada: obligatorio, en USD")
    if dia is None:
        faltas.append("pos.fecha_entrada: obligatoria (AAAA-MM-DD)")
    elif dia > fecha_informe:
        avisos.append(f"pos.fecha_entrada: fecha futura ({dia:%d/%m/%Y}): orden límite")
    elif isinstance(precio, (int, float)):
        rango = rango_sesion(dia)
        if rango is None:
            faltas.append(f"pos.fecha_entrada: no hay sesión de Nasdaq el {dia:%d/%m/%Y}")
        elif not rango[0] <= precio <= rango[1]:
            faltas.append(f"pos.precio_entrada: {_es(precio)} USD fuera del rango de la sesión del {dia:%d/%m/%Y} "
                          f"({_es(rango[0])}–{_es(rango[1])})")
        if dia < fecha_informe:
            avisos.append("pos.fecha_entrada: posición ya abierta; la lista de comprobación se evalúa a posteriori")
    tam, dd = e.valor("pos.tamano_pct"), e.valor("pos.drawdown_tolerado")
    if not isinstance(tam, (int, float)) or not 0.5 <= tam <= tamano_max * 100:
        faltas.append(f"pos.tamano_pct: entre 0,5 y {_es(tamano_max * 100, 0)} %")
    if not isinstance(dd, (int, float)) or not 0 < dd <= 100:
        faltas.append("pos.drawdown_tolerado: obligatorio, en %")
    if isinstance(tam, (int, float)) and isinstance(dd, (int, float)) and tam * dd / 1e4 > riesgo_max + 1e-12:
        faltas.append(f"pos.tamano_pct: {_es(tam, 1)} % × drawdown {_es(dd, 0)} % = {_es(tam * dd / 100)} % de la cartera, por encima "
                      f"del riesgo máximo por posición ({_es(riesgo_max * 100, 0)} %)")
    _rango("pos.tamano_porque", _texto_de(e.valor("pos.tamano_porque")), "10-40", faltas)
    _rango("pos.argumento", _texto_de(e.valor("pos.argumento")), "80-150", faltas)
    asunciones = e.valor("pos.asunciones") or []
    if not 3 <= len(asunciones) <= 7:
        faltas.append(f"pos.asunciones: {len(asunciones)} (entre 3 y 7)")
    for i, a in enumerate(asunciones, 1):
        _rango(f"pos.asunciones[{i}].texto", a.get("texto", ""), "5-30", faltas)
        if not a.get("driver") or not a.get("umbral_invalidacion"):
            faltas.append(f"pos.asunciones[{i}]: supuesto de valoración y umbral de invalidación obligatorios")
    for i, c in enumerate(e.valor("pos.checklist") or [], 1):
        if c.get("cumplido") not in ("si", "no", "parcial"):
            faltas.append(f"pos.checklist[{i}]: ¿cumplido? sí, no o parcial")
    invalidacion = e.valor("pos.invalidacion") or []
    if len([x for x in invalidacion if x.get("metrica") and x.get("umbral") and x.get("plazo")]) < 3:
        faltas.append("pos.invalidacion: mínimo 3, con métrica, umbral y plazo")
    kpis = e.valor("pos.kpis") or []
    if len(kpis) < 3:
        faltas.append(f"pos.kpis: {len(kpis)} (mínimo 3)")
    for i, k in enumerate(kpis, 1):
        if not all(k.get(x) for x in ("kpi", "verde", "rojo", "fuente")) or k.get("frecuencia") not in ("trimestral", "anual", "mensual", "evento"):
            faltas.append(f"pos.kpis[{i}]: indicador, verde, rojo, fuente y frecuencia (trimestral, anual, mensual o evento)")
    fechas = e.valor("pos.fechas_revision") or []
    if not fechas:
        faltas.append("pos.fechas_revision: al menos una")
    for f in fechas:
        try:
            if date.fromisoformat(str(f)) <= fecha_informe:
                faltas.append(f"pos.fechas_revision: {f} no es futura")
        except ValueError:
            faltas.append(f"pos.fechas_revision: «{f}» (AAAA-MM-DD)")
    if len(e.valor("pos.salida") or []) < 3:
        faltas.append("pos.salida: mínimo 3 criterios de salida")
    return faltas, avisos


def comprobar_paso3(e: Entradas, textos: Mapping[str, str], umbral: float, es_epigrafe) -> List[str]:
    """Las faltas del paso 3 (apartados 2 y 3): los textos del analista y exactamente cinco pilares, cada uno con dos
    evidencias verificadas, su KPI (uno de los de la posición) y el epígrafe del Item 1A que lo amenaza (06 §3.8)."""
    faltas: List[str] = []
    for id_, rango in (("tesis.resumen", "60-120"), ("tesis.por_que_ahora", "20-60"), ("tesis.vision_vs_mercado", "30-80")):
        texto = _texto_de(e.valor(id_))
        if not texto:
            faltas.append(f"{id_}: falta el texto del analista")
        else:
            _rango(id_, texto, rango, faltas)
    pilares = e.valor("pilares") or []
    if len(pilares) != 5:
        faltas.append(f"pilares: {len(pilares)} (se piden 5)")
    kpis = {k.get("kpi") for k in e.valor("pos.kpis") or []}
    for i, p in enumerate(pilares, 1):
        id_ = f"pilares[{i}]"
        _rango(f"{id_}.titulo", p.get("titulo", ""), "3-10", faltas)
        _rango(f"{id_}.argumento", _texto_de(p.get("argumento")), "40-90", faltas)
        _citas(f"{id_}.evidencias", p.get("evidencias"), textos, umbral, faltas, minimo=2)
        if not p.get("kpi"):
            faltas.append(f"{id_}.kpi: falta el KPI de seguimiento")
        elif kpis and p["kpi"] not in kpis:
            faltas.append(f"{id_}.kpi: «{p['kpi']}» no es ninguno de los KPI de la posición (paso 8)")
        if not p.get("riesgo_1a") or not es_epigrafe(p["riesgo_1a"]):
            faltas.append(f"{id_}.riesgo_1a: no es el comienzo de un epígrafe del Item 1A")
        _rango(f"{id_}.riesgo_es", p.get("riesgo_es", ""), "8-40", faltas)
    return faltas
