"""Parte F (apartados 24–26): riesgos, caso bajista e historial.

24: los cinco riesgos del analista (probabilidad × impacto, mitigante y señal temprana) y el recuento por familia de los
epígrafes del Item 1A (`item1a.py`; los literales solo en el atributo title). 25: disparadores cuantificados del caso
bajista con el supuesto pesimista al que apuntan, el riesgo de cada pilar y el escenario pesimista del motor. 26: guía →
real de las notas de resultados (F2), consenso → BPA publicado de la bolsa y, si algún trimestre falla por más de
`umbrales.fallo_guia_obliga_causas`, las causas del analista (obligatorias).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Sequence

from .entradas import Entradas, comprobar_paso6, verificar_cita
from .formato import Celda, fecha as f_fecha, numero, pct

__all__ = ["ParteF", "construir", "fallos", "rotulo_supuesto"]

FAMILIAS = {"regulatorio": "Regulatorio", "financiero": "Financiero", "competitivo": "Competitivo", "ejecucion": "Ejecución"}
_SUPUESTOS = {"crecimiento_ingresos": "crecimiento de ingresos", "margen_ebit": "margen EBIT", "impuesto_caja": "impuesto en caja",
              "da_pct": "D&A / ingresos", "capex_pct": "capex / ingresos", "fm_pct_incremental": "fondo de maniobra incremental",
              "sbc_pct": "SBC / ingresos", "g": "crecimiento terminal", "ronic": "RONIC", "wacc_ajuste_pp": "ajuste del WACC",
              "multiplo_salida": "múltiplo de salida", "probabilidad": "probabilidad"}


@dataclass
class ParteF:
    cuadros: Dict[str, object] = field(default_factory=dict)      # top, familias, disparadores, pilares, guias, consenso
    grafico_matriz: str = ""
    texto_pesimista: str = ""
    causas: str = ""
    sin_fallos: str = ""
    fallos: List[str] = field(default_factory=list)
    pendientes: Dict[str, str] = field(default_factory=dict)
    faltas: List[str] = field(default_factory=list)


def _c(texto: str, nota: str = "", clase: str = "valor", capa: str = "S") -> Celda:
    return Celda(texto, "", capa, clase, nota)


def _alias(doc: str, alias) -> str:
    from .parte_b import alias_doc
    return alias_doc(doc, alias)


def fallos(comparaciones: Sequence, sorpresas: Sequence, umbral: float, etiqueta_mes: Callable) -> List[str]:
    """Los trimestres que fallan por más del umbral: por debajo del rango de la guía (o de su punto) o del consenso."""
    salida = []
    for x in comparaciones:
        c, d = x.candidato, x.desvio
        if x.real is None or d is None or x.real.valor >= c.bajo:
            continue
        if (d < -umbral * 100) if c.unidad == "%" else (d < -umbral):
            salida.append(f"{c.trimestre} · {c.rotulo}: {'%s p. p.' % numero(d, 1) if c.unidad == '%' else pct(d)} frente a la guía")
    for s in sorpresas:
        if s.sorpresa is not None and s.sorpresa < -umbral:
            salida.append(f"{etiqueta_mes(s.mes)} · BPA de la bolsa: {pct(s.sorpresa)} frente al consenso")
    return salida


def rotulo_supuesto(driver: str) -> str:
    """«esc.base.margen_ebit» → «margen EBIT (escenario base)»: el supuesto de valoración, sin su identificador."""
    partes = str(driver).split(".")
    if len(partes) == 3 and partes[0] == "esc":
        return f"{_SUPUESTOS.get(partes[2], partes[2].replace('_', ' '))} (escenario {partes[1]})"
    return str(driver).replace("_", " ")


def _supuesto(e: Entradas, driver: str) -> str:
    valor = e.valor(driver)
    clave = driver.rsplit(".", 1)[-1]
    unidad = "x" if clave == "multiplo_salida" else " %"
    def cifra(v) -> str:                                    # 2,25 no se imprime «2,2»
        v = float(v)
        return numero(v, 1 if round(v, 1) == round(v, 2) else 2)
    if isinstance(valor, dict):
        cuerpo = " · ".join(f"año {k}: {cifra(v)}{unidad}" for k, v in valor.items())
    elif isinstance(valor, (int, float)):
        cuerpo = f"{cifra(valor)}{unidad}"
    else:
        return ""
    return f"{_SUPUESTOS.get(clave, clave)}: {cuerpo}"


def _riesgos(d: ParteF, n, e: Entradas, textos, umbral, item, alias) -> None:
    from . import graficos
    from .informe import Cuadro, FilaCuadro
    from .item1a import buscar
    top = e.valor("riesgos.top") or []
    filas, puntos = [], []
    for k, r in enumerate(top, 1):
        origen = r.get("origen") or {}
        ep = buscar(item, origen["epigrafe"]) if item is not None and origen.get("epigrafe") else None
        if ep is not None:
            ref, literal = f"Item\xa01A, pág.\xa0{ep.pagina}", ep.texto
        else:
            evs = [ev for ev in origen.get("evidencia") or [] if verificar_cita(ev, textos, umbral)[0]]
            if not evs:
                continue                                  # sin origen verificable no se imprime (queda como falta)
            ev = evs[0]
            ref = f"{_alias(ev.get('doc', ''), alias)}" + (f", pág. {ev['pag']}" if ev.get("pag") else "")
            literal = ev.get("texto", "")
        p, i = r.get("probabilidad"), r.get("impacto")
        if not all(isinstance(v, (int, float)) and 1 <= v <= 5 for v in (p, i)):
            continue
        puntos.append((k, int(p), int(i)))
        filas.append((p * i, FilaCuadro(f"{k}. {r.get('texto_es', '')}", [
            _c(FAMILIAS.get(r.get("familia", ""), r.get("familia", ""))), _c(numero(p)), _c(numero(i)),
            _c(numero(p * i), "probabilidad × impacto", capa="D"), _c(r.get("mitigante", "")), _c(r.get("senal", "")),
            _c(ref, literal)], capa="S", formula=literal)))
    if filas:
        filas.sort(key=lambda x: -x[0])
        d.cuadros["top"] = Cuadro(n.siguiente(), "Los cinco riesgos principales", ["Familia", "Prob.", "Impacto", "P\xa0×\xa0I", "Mitigante",
                                  "Señal temprana", "Origen"], [f for _, f in filas],
                                  "Fuente: analista (probabilidad e impacto de 1 a 5); origen en el Item 1A del 10-K o en la evidencia citada.")
        d.grafico_matriz = graficos.matriz_riesgos(puntos)
    else:
        d.pendientes["top"] = "Pendiente del analista: los cinco riesgos principales con probabilidad, impacto, mitigante y señal (paso 6)."
    if item is None or not item.epigrafes:
        d.pendientes["familias"] = "Pendiente: el 10-K no tiene epígrafes de riesgo reconocibles en el Item 1A; el analista los aporta con su cita."
        return
    por = item.por_familia()
    total = len(item.epigrafes)
    filas = []
    for clave, rotulo in FAMILIAS.items():
        lista = por[clave]
        if not lista:
            continue
        paginas = sorted({ep.pagina for ep in lista if ep.pagina}, key=lambda x: (len(x), x))
        literales = " | ".join(f"{ep.texto} (pág. {ep.pagina}; {ep.motivo})" for ep in lista)
        filas.append(FilaCuadro(rotulo, [_c(numero(len(lista)), literales, capa="D"), _c(pct(len(lista) / total, 0), "epígrafes / total", capa="D"),
                                         _c(", ".join(paginas), literales, capa="H")], capa="D"))
    certezas = {c: sum(1 for ep in item.epigrafes if ep.certeza == c) for c in ("alta", "media", "baja")}
    corregidas = sum(1 for ep in item.epigrafes if ep.motivo == "corregida por el analista")
    nota = (f"Clasificación del sistema por reglas: {certezas['alta']} por la cabecera del 10-K o por el analista, {certezas['media']} por una "
            f"palabra del epígrafe y {certezas['baja']} sin palabra clave (ejecución); corregible por el analista"
            + (f" ({corregidas} corregidas)." if corregidas else "."))
    d.cuadros["familias"] = Cuadro(n.siguiente(), f"Riesgos del Item 1A por familia ({numero(total)} epígrafes)", ["Epígrafes", "Peso", "Páginas"],
                                   filas, "Fuente: SEC EDGAR, Item 1A del 10-K; los epígrafes literales, en el HTML.", [nota])


def _bajista(d: ParteF, n, e: Entradas, item, motor) -> None:
    from .informe import Cuadro, FilaCuadro
    from .item1a import buscar
    filas = []
    for x in e.valor("bear.disparadores") or []:
        umbral = x.get("umbral")
        if not isinstance(umbral, (int, float)):
            continue
        filas.append(FilaCuadro(x.get("descripcion", ""), [
            _c(x.get("metrica", "")), _c(f"{numero(float(umbral), 1 if not float(umbral).is_integer() else 0)}{(' ' + x['unidad']) if x.get('unidad') else ''}"),
            _c(x.get("plazo", "")), _c(_supuesto(e, x.get("driver", "")), x.get("driver", ""))], capa="S"))
    if filas:
        d.cuadros["disparadores"] = Cuadro(n.siguiente(), "Disparadores del caso bajista", ["Métrica", "Umbral", "Plazo", "Supuesto pesimista"],
                                           filas, "Fuente: analista; el supuesto es el del escenario pesimista del motor (apartado 13).")
    else:
        d.pendientes["disparadores"] = "Pendiente del analista: al menos tres disparadores con métrica, umbral y plazo (paso 6)."
    filas = []
    for k, p in enumerate(e.valor("pilares") or [], 1):
        if not p.get("riesgo_es"):
            continue
        ep = buscar(item, p.get("riesgo_1a", "")) if item is not None else None
        if ep is None:
            d.faltas.append(f"pilares[{k}].riesgo_1a: no es un epígrafe del Item 1A")
            continue
        filas.append(FilaCuadro(f"Pilar {k} · {p.get('titulo', '')}", [_c(p["riesgo_es"]), _c(f"Item\xa01A, pág.\xa0{ep.pagina}", ep.texto)],
                                capa="S", formula=ep.texto))
    if filas:
        d.cuadros["pilares"] = Cuadro(n.siguiente(), "Riesgo de cada pilar", ["Riesgo", "Origen"], filas,
                                      "Fuente: analista (apartado 3), con el epígrafe del Item 1A al que remite.")
    else:
        d.pendientes["pilares"] = "Pendiente del analista: el riesgo de cada pilar del apartado 3, con su epígrafe del Item 1A."
    v = getattr(motor, "valoracion", None)
    pes = v.resultados.get("pesimista") if v is not None else None
    if pes is not None:
        d.texto_pesimista = (f"En el escenario pesimista, con una probabilidad del {pct(pes.escenario.probabilidad, 0)}, el valor por acción "
                             f"a {v.parametros.horizonte_meses} meses sería de {numero(pes.vh, 2)} USD: un {pct(v.downside)} frente al precio "
                             f"de {numero(v.precio, 2)} USD del {f_fecha(getattr(motor, 'fecha_precio', None))} (supuestos y flujos en el apartado 13).")


def _historial(d: ParteF, n, e: Entradas, comparaciones, sorpresas, hechos, trimestres, etiqueta, umbral_fallo) -> None:
    from .informe import Cuadro, FilaCuadro
    from .parte_b import cuadro_guia_real
    if comparaciones:
        ultimos = list(dict.fromkeys(x.candidato.trimestre for x in comparaciones))[-8:]           # 8 trimestres (01 › 26)
        d.cuadros["guias"] = cuadro_guia_real(n, [x for x in comparaciones if x.candidato.trimestre in ultimos])

    def etiqueta_mes(mes) -> str:
        p = next((p for p in trimestres if mes is not None and (p.fin.year, p.fin.month) == (mes.year, mes.month)), None)
        return etiqueta(p) if p is not None else (mes.strftime("%m/%Y") if mes else "")

    filas = []
    for s in sorpresas:
        p = next((p for p in trimestres if s.mes is not None and (p.fin.year, p.fin.month) == (s.mes.year, s.mes.month)), None)
        h = hechos.get(("bpa_diluido", p)) if p is not None else None
        sec = (_c(numero(h.valor, 2), "BPA diluido GAAP del 10-Q o 10-K (sección C)", capa="H") if h is not None and h.hay_dato
               else Celda("—", "", "", "valor", "trimestre fuera del alcance de la sección C"))
        filas.append(FilaCuadro(etiqueta_mes(s.mes), [
            _c(f_fecha(s.publicado), s.texto, capa="H"), _c(numero(s.consenso, 2), s.texto, capa="H"), _c(numero(s.real, 2), s.texto, capa="H"),
            _c(pct(s.sorpresa) if s.sorpresa is not None else "—", "la de la bolsa", clase="negativo" if (s.sorpresa or 0) < 0 else "valor", capa="H"),
            sec], capa="H"))
    if filas:
        distinto = any(f.celdas[-1].texto not in ("—", f.celdas[2].texto) for f in filas)
        notas = (["El BPA de la bolsa sigue la definición de su proveedor de consenso y no coincide con el BPA diluido GAAP de la SEC: "
                  "la última columna los enfrenta."] if distinto else [])
        d.cuadros["consenso"] = Cuadro(n.siguiente(), "Consenso frente a BPA publicado", ["Publicado", "Consenso", "BPA publicado",
                                       "Sorpresa", "BPA diluido (SEC)"], filas, "Fuente: Nasdaq (sorpresas de resultados) y SEC EDGAR.", notas)
    d.fallos = fallos(comparaciones, sorpresas, umbral_fallo, etiqueta_mes)
    causas = e.valor("historial.causas")
    d.causas = (causas.get("texto", "") if isinstance(causas, dict) else (causas or "")).strip()
    if d.fallos and not d.causas:
        d.pendientes["causas"] = ("Pendiente del analista: causas y aprendizajes (30–150 palabras), obligatorias por " + "; ".join(d.fallos) + ".")
    elif not d.fallos and (comparaciones or sorpresas):
        d.sin_fallos = (f"Ningún trimestre queda por debajo de la guía ni del consenso en más del {pct(umbral_fallo, 0)}: "
                        "no se exigen causas.")


def construir(n, pb, motor, comparaciones: Sequence, hechos, trimestres: Sequence, etiqueta: Callable, umbral_cita: float,
              umbral_fallo: float) -> ParteF:
    """`pb`: parte_b.ParteB (entradas, textos, alias, Item 1A y sorpresas de la bolsa). Cuadros en el orden de impresión."""
    d = ParteF()
    e, item = pb.entradas, getattr(pb, "item1a", None)
    _riesgos(d, n, e, pb.textos, umbral_cita, item, pb.alias)
    _bajista(d, n, e, item, motor)
    _historial(d, n, e, comparaciones, getattr(pb, "sorpresas", []), hechos, trimestres, etiqueta, umbral_fallo)
    from .item1a import buscar
    existe = (lambda t: item is not None and buscar(item, t) is not None)       # noqa: E731
    d.faltas = comprobar_paso6(e, pb.textos, umbral_cita, existe, d.fallos) + d.faltas
    return d
