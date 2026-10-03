"""Parte D (apartados 12–20): los cuadros del motor de valoración (05). Un precio (cierre oficial), un PO (motor), un
horizonte; el libro del analista solo en la comparación."""

from __future__ import annotations
from . import lexico

import statistics
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from ..formato import Celda, fecha as f_fecha, mln, numero

__all__ = ["ParteD", "construir"]


def _c(texto: str, nota: str = "", clase: str = "valor", capa: str = "D", hecho: str = "") -> Celda:
    return Celda(texto, "", capa, clase, nota, hecho)


def _dn(pte) -> str:
    """La clave de valor único de la deuda neta del puente: por fecha de balance (06 §3.3)."""
    return f"deuda_neta@{pte.fecha_balance.isoformat()}" if getattr(pte, "fecha_balance", None) else "deuda_neta@puente"


def _na(motivo: str) -> Celda:
    return Celda("N/A", "", "", "na", motivo)


def _usd(v: Optional[float], dec: int = 2) -> str:
    return "N/A" if v is None else f"{numero(v, dec)} {lexico.moneda()}"


def _mln(v: Optional[float]) -> str:
    return "N/A" if v is None else mln(v)


def _pct(v: Optional[float], dec: int = 1) -> str:
    return "N/A" if v is None else f"{numero(v * 100, dec)} %"


@dataclass
class ParteD:
    cuadros: Dict[str, object] = field(default_factory=dict)          # clave → Cuadro
    escenarios: List[tuple] = field(default_factory=list)             # (nombre, narrativa, Cuadro) de 13–15
    avisos: List[str] = field(default_factory=list)
    bloqueos: List[str] = field(default_factory=list)
    sotp: str = ""                                                    # texto de 19 cuando no aplica
    lectura_20: List[str] = field(default_factory=list)
    horizonte_meses: int = 12
    po: Optional[float] = None
    precio: Optional[float] = None
    fecha_precio: Optional[object] = None
    potencial: Optional[float] = None
    margen_seguridad: Optional[float] = None
    recorrido_riesgo: Optional[float] = None
    recomendacion_regla: str = ""


def _fila_deuda_neta(pte, hechos):
    """Deuda neta del puente (sumada de sus líneas) frente a la del apartado 9 (el Hecho derivado de esa fecha). El ✓
    comparaba antes la cifra del puente consigo misma (A4, fallo [45]): ahora son dos cálculos que deben coincidir."""
    from .informe import FilaCuadro
    from ..datos.hechos import Periodo
    h = (hechos or {}).get(("deuda_neta", Periodo.instante(pte.fecha_balance))) if getattr(pte, "fecha_balance", None) else None
    if h is None or not h.hay_dato:
        return FilaCuadro("Deuda neta del puente", [_c(_mln(pte.deuda_neta), capa="H"), _c("N/A", "sin deuda neta del apartado 9 en esa fecha", clase="na"), _c("—")])
    cuadra = abs(h.valor - pte.deuda_neta) <= 0.5e6
    return FilaCuadro("Deuda neta del puente", [_c(_mln(pte.deuda_neta), capa="H"), _c(_mln(h.valor), capa="H", hecho=_dn(pte)),
                                                _c("✓" if cuadra else "≠")])


def _rotulo_sbc(p) -> str:
    """La fila de la SBC dice qué hace con ella la política del analista (decisión 1, 28/09): con «coste de caja» ya está
    dentro del margen EBIT GAAP y no se resta del FCFF; con «dilución» se suma al EBIT y la pagan acciones nuevas."""
    return "SBC (informativa: ya en el margen EBIT)" if p.sbc_politica == "coste_de_caja" else "(+) SBC sumada al EBIT (diluye acciones)"


METRICAS_SOTP = {"ingresos": "Ingresos", "ebit": "EBIT", "ebitda": "EBITDA"}


def construir(n, m, etiqueta, hechos=None, anuales=None, consenso=None, libro: Optional[dict] = None,
              recomendacion_analista: str = "", segmento_unico: bool = False, multiplos=None, sotp=None) -> ParteD:
    """`m`: motor.datos.Motor. `etiqueta(p)`: rótulo fiscal de un periodo. `libro`: {rango: valor} del Excel del analista."""
    from .informe import Cuadro, FilaCuadro
    from ..motor import excel
    d = ParteD(bloqueos=list(m.bloqueos), avisos=list(m.avisos))
    v = m.valoracion
    if v is None:
        return d
    p, w, pte = v.parametros, v.wacc, v.puente
    h = p.horizonte_meses
    d.horizonte_meses, d.po, d.precio, d.fecha_precio = h, v.po, v.precio, m.fecha_precio
    d.potencial, d.margen_seguridad, d.recorrido_riesgo, d.recomendacion_regla = v.potencial, v.margen_seguridad, v.recorrido_riesgo, v.recomendacion
    precio_txt = f"cierre oficial de {lexico.bolsa()} del {f_fecha(m.fecha_precio)}"
    # 12 · escenarios
    filas = []
    for nombre, r in v.resultados.items():
        filas.append(FilaCuadro(nombre.capitalize(), [
            _c(_pct(r.escenario.probabilidad, 0), capa="S"), _c(_pct(r.wacc, 2), "WACC + ajuste del escenario"),
            _c(_pct(r.escenario.g, 2), capa="S"),
            # el RONIC del valor terminal es un supuesto visible (fallo [38]): el del analista o el de partida, y se dice
            _c(_pct(r.ronic, 2) if r.ronic is not None else "—",
               "WACC del escenario + diferencial de partida (umbrales)" if r.ronic_por_defecto else "analista (paso 7)",
               capa="D" if r.ronic_por_defecto else "S"),
            _c(_usd(r.v0), "fondos propios / acciones diluidas"),
            _c(_usd(r.vh), f"V₀ × (1 + Ke)^({h}/12) − dividendos esperados"), _c(_pct(r.peso_vt, 0), "valor actual del VT / EV")], capa="D"))
    filas.append(FilaCuadro("Valor razonable ponderado", [_c("100 %"), _c(""), _c(""), _c(""), _c(_usd(v.valor_razonable), "Σ p · V₀"),
                                                         _c(_usd(v.po), "Σ p · V_h = precio objetivo"), _c("")], capa="D", destacada=True))
    d.cuadros["escenarios"] = Cuadro(n.siguiente(), "Escenarios y valor razonable", ["Probabilidad", "WACC", "g", "RONIC", "Valor hoy",
                                     f"Valor a {h} meses", "Peso del VT"], filas,
                                     f"Fuente: motor de valoración (05) con las entradas del analista; precio: {precio_txt}.")
    # 12 · WACC
    br = w.beta_regresion
    filas = [FilaCuadro("Tipo libre de riesgo (bono a 10 años)", [_c(_pct(w.rf, 2), capa="H"), _c(f"{lexico.rf().replace(' a 10 años', '')} del {f_fecha(w.rf_fecha)}" if lexico.es_bme() else f"Tesoro de EE. UU., curva par del {f_fecha(w.rf_fecha)}")]),
             FilaCuadro("Beta", [_c(numero(w.beta, 2)), _c(w.beta_origen + (f"; bruta {numero(br.bruta, 2)}, R² {numero(br.r2, 2)}, "
                                                                           f"{br.n} semanas" if br else ""))])]
    if w.beta_mensual is not None:
        bm = w.beta_mensual
        filas.append(FilaCuadro("Beta mensual de 5 años (contraste)", [_c(numero(bm.bruta, 2)), _c(f"R² {numero(bm.r2, 2)}, {bm.n} meses")]))
    filas += [FilaCuadro("Prima de riesgo de mercado (ERP)", [_c(_pct(w.erp, 2), capa="S"), _c(p.erp_fuente)]),
              FilaCuadro("Prima específica", [_c(_pct(w.prima, 2), capa="S"), _c("analista" if w.prima else "sin prima específica")]),
              FilaCuadro("Coste de los fondos propios (Ke)", [_c(_pct(w.ke, 2)), _c("rf + β × ERP + prima")], destacada=True),
              FilaCuadro("Coste de la deuda (Kd)", [_c(_pct(w.kd, 2), capa="S"), _c(w.kd_origen)]),
              FilaCuadro("Tipo impositivo marginal", [_c(_pct(w.t, 1), capa="S"), _c("analista")]),
              FilaCuadro("Kd después de impuestos", [_c(_pct(w.kd_neto, 2)), _c("Kd × (1 − t)")]),
              FilaCuadro("Peso de los fondos propios", [_c(_pct(w.peso_e, 1)), _c(f"E = precio × acciones = {_mln(w.e)} M {lexico.moneda()}")]),
              FilaCuadro("Peso de la deuda", [_c(_pct(w.peso_d, 1)), _c(f"D = deuda financiera = {_mln(w.d)} M {lexico.moneda()}")]),
              FilaCuadro("WACC", [_c(_pct(w.wacc, 2)), _c("E/(D+E) × Ke + D/(D+E) × Kd × (1 − t)")], destacada=True)]
    d.cuadros["wacc"] = Cuadro(n.siguiente(), "Construcción del WACC", ["Valor", "Origen"], filas, f"Fuente: {lexico.rf()}; beta {lexico.mercado_beta()}; entradas del analista." if lexico.es_bme()
                               else "Fuente: Tesoro de EE. UU., Nasdaq (cierres de la compañía y de SPY) y entradas del analista.")
    # 12 · puente (escenario base)
    b = v.base
    filas = [FilaCuadro("Valor de empresa (base)", [_c(_mln(b.ev)), _c("Σ VA de los FCFF + VA del valor terminal")], destacada=True)]
    for l in pte.lineas:
        filas.append(FilaCuadro(("(−) " if l.signo < 0 else "(+) ") + l.rotulo, [_c(_mln(l.valor), capa="H"), _c(l.fuente)]))
    filas += [FilaCuadro("Fondos propios", [_c(_mln(b.fondos_propios)), _c("valor de empresa + ajustes del puente")], destacada=True),
              FilaCuadro("Acciones diluidas (millones)", [_c(numero(pte.acciones / 1e6, 1), capa="H", hecho="acciones_diluidas"), _c(pte.acciones_nota)]),
              FilaCuadro("Valor por acción hoy (V₀)", [_c(_usd(b.v0)), _c("fondos propios / acciones diluidas")], destacada=True)]
    d.cuadros["puente"] = Cuadro(n.siguiente(), f"Puente del valor de empresa al valor por acción (escenario base, mln {lexico.moneda()})", ["Importe", "Origen"],
                                 filas, f"Fuente: motor; deuda neta del puente {_mln(pte.deuda_neta)} M {lexico.moneda()}, los mismos importes del apartado 9.")
    # 12 · entradas frente al dato oficial
    filas = [FilaCuadro("Precio", [_c(_usd(v.precio), capa="H", hecho="precio"), _c(_usd(m.precio), capa="H", hecho="precio"), _c("✓")]),
             FilaCuadro(f"Ingresos del año base ({m.etiqueta_base})", [_c(_mln(m.ingresos_base), capa="H"), _c(_mln(m.ingresos_base), capa="H"), _c("✓")]),
             _fila_deuda_neta(pte, hechos)]
    d.cuadros["entradas"] = Cuadro(n.siguiente(), "Entradas del modelo frente al dato oficial", ["Motor", "Dato oficial", "Cuadre"], filas,
                                   f"El motor lee los hechos verificados: precio ({precio_txt}), ingresos ({'cuentas' if lexico.es_bme() else 'SEC'}) y "
                                   f"balance ({'cuentas' if lexico.es_bme() else 'SEC'}). Deben coincidir.")
    # 12 · supuestos generales
    filas = [FilaCuadro(rot, [_c(val, capa="S"), _c(origen)]) for rot, val, origen in (
        ("Fecha de valoración", f_fecha(p.fecha_valoracion), "analista"),
        ("Año base", m.etiqueta_base, "último ejercicio" if p.anio_base == "ultimo_ejercicio" else "últimos doce meses"),
        ("Periodo explícito", f"{p.periodo} años", f"paquete {p.paquete}"),
        ("Convención de descuento", "mitad de año" if p.mitad_de_anio else "fin de año", "analista"),
        ("Periodo parcial del año 1", _pct(b.proyeccion.fraccion_flujo, 1),
         f"flujo del último balance ({f_fecha(b.proyeccion.desde or p.fecha_valoracion)}) al cierre del ejercicio ({f_fecha(b.proyeccion.cierres[0])}); "
         f"descuento desde la valoración ({_pct(b.proyeccion.fraccion, 1)} del ejercicio)"),
        ("Horizonte del precio objetivo", f"{h} meses", "el único del informe (portada, 20 y G)"),
        ("Retribución en acciones", "coste de caja" if p.sbc_politica == "coste_de_caja" else "dilución", "analista"),
        ("Arrendamientos", "fuera de la deuda" if p.arrendamientos == "fuera_de_deuda" else "dentro de la deuda", "analista"),
        ("Valor terminal", {"value_driver": "value driver", "gordon": "Gordon", "multiplo_salida": "múltiplo de salida"}[p.tv_metodo], "los otros dos métodos, como contraste"))]
    d.cuadros["supuestos"] = Cuadro(n.siguiente(), "Supuestos generales", ["Valor", "Origen / justificación"], filas, "Fuente: entradas del analista (paso 7).")
    # 12 · motor frente al libro
    if libro:
        comp = excel.comparar(libro, v)
        filas = []
        for rot, x_libro, x_motor, unidad in comp.filas:
            fmt = (lambda x: _pct(x, 2)) if unidad == "%" else ((lambda x: numero(x)) if unidad in ("M", "M USD", f"M {lexico.moneda()}") else (lambda x: _usd(x)))
            dif = (x_motor - x_libro) if isinstance(x_libro, (int, float)) else None
            filas.append(FilaCuadro(rot, [_c(fmt(x_libro) if x_libro is not None else "N/A", capa="S"), _c(fmt(x_motor)),
                                          _c((("+" if dif > 0 else "") + fmt(dif)) if dif is not None else "N/A")]))
        d.cuadros["libro"] = Cuadro(n.siguiente(), "Motor frente al libro del analista", ["Libro", "Motor (rige)", "Diferencia"], filas,
                                    "Fuente: libro del analista leído por mapa de celdas (nunca por rótulo). Rige el motor; el libro solo se compara.",
                                    comp.faltan)
    # 13–15 · un cuadro por escenario
    for nombre, r in v.resultados.items():
        pr, e = r.proyeccion, r.escenario
        from ..datos.hechos import Periodo
        cols = [etiqueta(Periodo.anual(c)) + "E" for c in pr.cierres]
        pct_fila = lambda rot, s: FilaCuadro(rot, [_c(_pct(x, 1), capa="S") for x in s], capa="S")                  # noqa: E731
        mln_fila = lambda rot, s, formula="", dest=False: FilaCuadro(rot, [_c(_mln(x), formula) for x in s], formula=formula, destacada=dest)  # noqa: E731
        filas = [pct_fila("Crecimiento de ingresos", e.crecimiento), pct_fila("Margen EBIT", e.margen), pct_fila("Impuesto en caja", e.impuesto),
                 pct_fila("D&A (% ingresos)", e.da), pct_fila("Capex (% ingresos)", e.capex), pct_fila("SBC (% ingresos)", e.sbc)]
        filas += [pct_fila(k.replace("_", " ").capitalize() + " (% ingresos)", s) for k, s in e.paquete.items()]
        filas += [mln_fila("Ingresos", pr.ingresos, pr.formulas["ingresos"]), mln_fila("EBIT", pr.ebit, pr.formulas["ebit"]),
                  mln_fila("(−) Impuestos", pr.impuestos, pr.formulas["impuestos"]), mln_fila("NOPAT", pr.nopat, pr.formulas["nopat"]),
                  mln_fila("(+) D&A", pr.da), mln_fila("(−) Capex", pr.capex), mln_fila("(−) Δ fondo de maniobra", pr.dfm),
                  mln_fila(_rotulo_sbc(p), pr.sbc, pr.formulas["sbc"])] + [mln_fila(f"(−) {k.replace('_', ' ')}", s) for k, s in pr.paquete.items()]
        filas += [mln_fila("FCFF", pr.fcff, pr.formulas["fcff"], True),
                  FilaCuadro("Factor de descuento", [_c(numero(x, 4)) for x in pr.factores], formula=pr.formulas["tiempos"]),
                  mln_fila("Valor actual", pr.valor_actual, pr.formulas["valor_actual"])]
        tv = r.terminal
        notas = [f"Periodo parcial: el año 1 cuenta {_pct(pr.fraccion_flujo, 1)} (del último balance, {f_fecha(pr.desde or p.fecha_valoracion)}, al "
                 f"{f_fecha(pr.cierres[0])}); lo anterior ya está en ese balance. Se descuenta desde la valoración.",
                 f"Valor terminal ({ {'value_driver': 'value driver', 'gordon': 'Gordon', 'multiplo_salida': 'múltiplo'}[tv.metodo] }): "
                 f"{_mln(tv.valor)} M {lexico.moneda()}, descontado en t = {numero(tv.momento, 2)}; contraste: "
                 + ", ".join(f"{ {'value_driver': 'value driver', 'gordon': 'Gordon', 'multiplo_salida': 'múltiplo'}[k] } {_mln(x)}" for k, x in tv.valores.items() if k != tv.metodo and x is not None) + ".",
                 *([f"SBC con «dilución»: {_mln(pr.sbc_en_acciones)} M {lexico.moneda()} del periodo explícito se pagan con "
                    f"{numero((r.acciones - pte.acciones) / 1e6, 1)} M de acciones nuevas al precio de hoy; el valor por acción "
                    f"se reparte entre {numero(r.acciones / 1e6, 1)} M."] if pr.sbc_en_acciones else []),
                 f"Valor de empresa {_mln(r.ev)} M {lexico.moneda()} (VT {_pct(r.peso_vt, 0)}) → fondos propios {_mln(r.fondos_propios)} M {lexico.moneda()} → "
                 f"V₀ {_usd(r.v0)} · V_h a {h} meses {_usd(r.vh)} · recorrido sobre el precio {_pct(r.vh / v.precio - 1)}."]
        cuadro = Cuadro(n.siguiente(), f"Escenario {nombre}: drivers, FCFF y valoración (mln {lexico.moneda()})", cols, filas,
                        f"Fuente: motor (05 §3–§7); WACC {_pct(r.wacc, 2)}, g {_pct(e.g, 2)}.", notas + [f"⚠ {a}" for a in r.avisos])
        d.escenarios.append((nombre, e.narrativa, cuadro))
    # 16 · sensibilidad
    mz = m.matriz
    if mz is not None:
        filas = []
        for i, wv in enumerate(mz.waccs):
            celdas = []
            for j, _ in enumerate(mz.gs):
                x = mz.valores[i][j]
                clase = "na" if x is None else ("bajo" if x < v.precio else "valor")
                celdas.append(Celda("N/A" if x is None else numero(x, 2), "◆" if (i, j) == mz.base else "", "D", clase,
                                    "celda del escenario base" if (i, j) == mz.base else ""))
            filas.append(FilaCuadro(f"WACC {_pct(wv, 2)}", celdas))
        d.cuadros["sensibilidad"] = Cuadro(n.siguiente(), "Sensibilidad del valor por acción (base): WACC × g", [f"g {_pct(g, 2)}" for g in mz.gs], filas,
                                           f"Fuente: motor. En granate, por debajo del precio ({_usd(v.precio)}); ◆ la celda del escenario base.")
    # 17 · múltiplos TTM (SEC + cierre oficial), NTM, histórico y comparables
    if multiplos is not None:
        from .secciones import cuadro_multiplos_sec
        d.cuadros["multiplos_sec"] = cuadro_multiplos_sec(n, multiplos)
    if m.ntm is not None:
        t = m.ntm
        filas = [FilaCuadro(rot, [_c(numero(x, 1) + "x" if x is not None else "N/A", formula), _c(formula, capa="")]) for rot, x, formula in (
            ("PER NTM", t.per, "precio / BPA NTM (NOPAT − intereses × (1 − t)) / acciones"), ("EV / EBITDA NTM", t.ev_ebitda, "EV de mercado / EBITDA NTM"),
            ("EV / Ventas NTM", t.ev_ventas, "EV de mercado / ingresos NTM"), ("P / FCF NTM", t.p_fcf, "capitalización / FCF NTM"),
            ("PEG", t.peg, "PER NTM / (CAGR del BPA a 3 años del base × 100)"))]
        d.cuadros["ntm"] = Cuadro(n.siguiente(), "Múltiplos NTM del escenario base", ["Múltiplo", "Cálculo"], filas,
                                  f"NTM = f · año 1 + (1 − f) · año 2 del escenario base; precio: {precio_txt}.")
    if m.historico_per:
        valores = [x for _, x in m.historico_per]
        filas = [FilaCuadro("PER (BPA diluido de los 12 meses anteriores)", [_c(numero(min(valores), 1) + "x"), _c(numero(statistics.median(valores), 1) + "x"),
                                                                             _c(numero(max(valores), 1) + "x"), _c(str(len(valores)))])]
        d.cuadros["historico"] = Cuadro(n.siguiente(), "Histórico propio de 5 años", ["Mínimo", "Mediana", "Máximo", "Trimestres"], filas,
                                        f"Fuente: cierres oficiales de {lexico.bolsa()} al final de cada periodo y BPA diluido {lexico.de_las_cuentas()}; solo con BPA positivo.")
    if m.comparables is not None:
        from ..motor.comparables import MULTIPLOS
        filas = []
        for c in m.comparables.filas:                           # los excluidos, marcados y con «—» (R15; sin «N/A», 06 §3.10)
            celdas = []
            for clave, _ in MULTIPLOS:
                x = c.valores.get(clave)
                if c.excluido or x is None:                     # «—» con su motivo: en 12–20 no hay «N/A» (06 §3.10)
                    celdas.append(_c("—", c.excluido or c.motivos.get(clave, "sin dato del emisor en la SEC"), capa=""))
                else:
                    celdas.append(Celda(numero(x, 1) + "x", "✱" if clave in c.atipicos else "", "H", "valor",
                                        "atípico: fuera de medianas" if clave in c.atipicos else ""))
            rot = f"{c.ticker} · {c.nombre}" + (" (excluido)" if c.excluido else "")
            filas.append(FilaCuadro(rot, celdas + [_c(c.excluido or f"cuentas a {f_fecha(c.cierre_ltm)}", capa="")]))
        filas.append(FilaCuadro("Mediana (excluidos y atípicos fuera)", [_c(numero(x, 1) + "x" if x is not None else "—") for x in
                                                                           (m.comparables.medianas.get(k) for k, _ in MULTIPLOS)] + [_c("")], destacada=True))
        d.cuadros["comparables"] = Cuadro(n.siguiente(), "Comparables del analista (LTM)", ["PER", "EV / EBITDA", "EV / Ventas", "P / FCF", "Nota"], filas,
                                          "Fuente: SEC (cuentas) y Nasdaq (cierre en la fecha de valoración). Fuera de medianas: cuentas con más antigüedad "
                                          "que el umbral o en otra moneda. «—»: sin dato o excluido (motivo al pasar el ratón).", partible=True)
        # valor implícito por acción: mediana de comparables × métrica propia (solo contraste)
        implicitos = _implicitos(m, v)
        if implicitos:
            filas = [FilaCuadro(rot, [_c(_usd(x))]) for rot, x in implicitos.items()]
            d.cuadros["implicito"] = Cuadro(n.siguiente(), "Valor implícito por acción según múltiplos (solo contraste)", [f"{lexico.moneda()}/acción"], filas,
                                            "Mediana de comparables × métrica propia NTM; no entra en el precio objetivo.")
            mediana = statistics.median(implicitos.values())
            if v.valor_razonable and abs(mediana / v.valor_razonable - 1) > 0.20:
                d.lectura_20.append(f"Los múltiplos de los comparables llevan a {_usd(mediana)} por acción (mediana), un "
                                    f"{_pct(abs(mediana / v.valor_razonable - 1), 0)} lejos del valor razonable del DCF: la diferencia se explica o se revisa.")
    # 18 · inverso
    inv = m.inverso
    if inv is not None:
        # cinco intervalos: del ejercicio de hace cinco años al último (fallos [15] y [44]); sin él, N/A con su motivo
        historico, hist_motivo = None, "sin ejercicio de hace cinco años"
        h5 = m.ingresos_hace_5
        ult = hechos.get(("ingresos", anuales[-1])) if hechos is not None and anuales else None
        if h5 is not None and not h5.hay_dato:
            hist_motivo = h5.motivo
        elif h5 is not None and ult is not None and ult.hay_dato and h5.valor > 0 and ult.valor > 0:
            historico = (ult.valor / h5.valor) ** (1 / 5) - 1
        fila = lambda rot, x, base, hist="", motivo="": FilaCuadro(rot, [_c(_pct(x, 1) if x is not None else "sin solución en el rango"),  # noqa: E731
                                                                         _c(_pct(base, 1) if base is not None else "—"), _c(hist or "—", motivo)])
        filas = [fila("CAGR de ingresos implícito (márgenes del base)", inv.cagr_ingresos, inv.base_cagr,
                      _pct(historico, 1) if historico is not None else "—", "" if historico is not None else hist_motivo),
                 fila("Margen EBIT terminal implícito (crecimiento del base)", inv.margen_terminal, inv.base_margen),
                 fila("Crecimiento constante del FCFF implícito", inv.crecimiento_fcff, None)]
        d.cuadros["inverso"] = Cuadro(n.siguiente(), "DCF inverso: lo que descuenta el precio", ["Implícito", "Escenario base", "Histórico 5 años"], filas,
                                      f"Fuente: motor (bisección en los rangos de la configuración de umbrales); precio: {precio_txt}.")
    # 19 · SOTP
    if not p.sotp.get("aplica"):
        # solo es una decisión del analista si la tomó (fallo [32]): sin la casilla, no se le atribuye nada
        d.sotp = ("No aplica: la compañía declara un único segmento operativo." if segmento_unico else
                  "No aplica por decisión del analista (entradas, sotp.aplica = no); el DCF consolidado rige." if "aplica" in p.sotp else
                  "No se calcula: el analista no ha planteado una suma de partes (paso 7, sotp.aplica sin rellenar); el DCF "
                  "consolidado rige.")
    elif sotp is not None and sotp.por_accion is not None:
        from ..formato import mln
        m_ = lexico.moneda()
        filas = [FilaCuadro(x.segmento, [_c(f"{METRICAS_SOTP[x.metrica]} {x.periodo}".strip(), x.origen, capa="H"),
                                         _c(f"{mln(x.valor_metrica)} M {m_}", x.origen, capa="H"),
                                         _c(f"{numero(x.multiplo, 1)}x", x.justificacion, capa="S"),
                                         _c(f"{mln(x.ve)} M {m_}", "métrica × múltiplo")], capa="S") for x in sotp.partes]
        if sotp.costes_corporativos is not None and sotp.multiplo_costes is not None:
            filas.append(FilaCuadro("Costes corporativos capitalizados", [
                _c("costes no repartidos", sotp.costes_origen, capa="S"), _c(f"−{mln(sotp.costes_corporativos)} M {m_}", sotp.costes_origen, capa="S"),
                _c(f"{numero(sotp.multiplo_costes, 1)}x", "analista", capa="S"), _c(f"−{mln(sotp.costes_capitalizados)} M {m_}", "costes × múltiplo")], capa="S"))
        filas += [FilaCuadro("Valor de empresa (suma de partes)", [_c(""), _c(""), _c(""), _c(f"{mln(sotp.ve)} M {m_}", "Σ segmentos − costes corporativos")], destacada=True),
                  FilaCuadro("Puente a los fondos propios", [_c(""), _c(""), _c(""), _c(f"{mln(sotp.ajuste_puente)} M {m_}", "el mismo puente que el DCF (cuadro del puente)")]),
                  FilaCuadro("Valor por acción (SOTP)", [_c(""), _c(""), _c(""), _c(_usd(sotp.por_accion), "fondos propios / acciones diluidas del puente")], destacada=True),
                  FilaCuadro("Frente al valor hoy del DCF (base)", [_c(""), _c(""), _c(""), _c(_pct(sotp.frente_al_dcf), f"SOTP / {_usd(sotp.dcf_v0)} − 1")])]
        d.cuadros["sotp"] = Cuadro(n.siguiente(), "Suma de partes (SOTP)", ["Métrica", "Valor", "Múltiplo", "Valor de empresa"], filas,
                                   "Fuente: segmentos del apartado 4 o cifras del analista con su cita; múltiplos y justificación del analista "
                                   "(paso 7); puente y acciones del motor. El SOTP contrasta el DCF; el precio objetivo sigue siendo el del DCF.")
    else:
        d.sotp = "No se calcula: " + ("; ".join(sotp.faltan) if sotp is not None and sotp.faltan else "sin segmentos valorables") + \
                 ". El DCF consolidado rige."
    # 20 · PO y margen de seguridad
    unicos = {f"Precio objetivo a {h} meses": "po", "Precio (cierre oficial)": "precio"}          # 06 §3.3
    filas = [FilaCuadro(rot, [_c(val, formula, hecho=unicos.get(rot, ""))], destacada=dest) for rot, val, formula, dest in (
        (f"Precio objetivo a {h} meses", _usd(v.po), "Σ p · V_h", True), ("Valor razonable hoy", _usd(v.valor_razonable), "Σ p · V₀", False),
        ("Precio (cierre oficial)", _usd(v.precio), precio_txt, False), ("Potencial", _pct(v.potencial), "PO / precio − 1", True),
        ("Margen de seguridad", _pct(v.margen_seguridad), "1 − precio / valor razonable", False),
        ("Downside pesimista", _pct(v.downside), "V_h pesimista / precio − 1", False),
        ("Recorrido / riesgo", numero(v.recorrido_riesgo, 2) if v.recorrido_riesgo is not None else "sin pérdida en el pesimista",
         "(PO − precio) / (precio − V_h pesimista)", False),
        ("Recomendación sugerida por la regla", v.recomendacion, "regla de recomendación de la configuración de umbrales", True))]
    if recomendacion_analista:
        filas.append(FilaCuadro("Recomendación del analista", [_c(recomendacion_analista.capitalize(), "posición del analista", capa="S", hecho="recomendacion")]))
    d.cuadros["objetivo"] = Cuadro(n.siguiente(), "Precio objetivo y margen de seguridad", ["Valor"], filas,
                                   "Definiciones únicas (05 §7). Un solo precio objetivo, el del motor; el consenso no entra en ninguna media.")
    if consenso is not None:
        filas = [FilaCuadro("Consenso de Nasdaq (precio objetivo medio)", [_c(_usd(consenso.objetivo), capa="H"),
                            _c(f"{consenso.compra or 0} comprar · {consenso.mantener or 0} mantener · {consenso.venta or 0} vender; rango "
                               f"{_usd(consenso.bajo)} – {_usd(consenso.alto)}", capa="")])]
        if consenso.objetivo and abs(consenso.objetivo / v.po - 1) > 0.20:
            d.lectura_20.append(f"El consenso de Nasdaq ({_usd(consenso.objetivo)}) se aleja más de un 20 % del precio objetivo del motor.")
        d.cuadros["consenso"] = Cuadro(n.siguiente(), "Contraste: consenso de mercado", ["Valor", "Detalle"], filas,
                                       "Fuente: Nasdaq. Solo contraste: no entra en el precio objetivo.")
    return d


def _implicitos(m, v) -> Dict[str, float]:
    t, med = m.ntm, (m.comparables.medianas if m.comparables else {})
    if t is None:
        return {}
    acciones, deuda_neta = v.puente.acciones, v.puente.deuda_neta
    salida = {}
    if med.get("per") and t.bpa > 0:
        salida["PER"] = med["per"] * t.bpa
    if med.get("ev_ebitda") and t.ebitda > 0:
        salida["EV / EBITDA"] = (med["ev_ebitda"] * t.ebitda - deuda_neta) / acciones
    if med.get("ev_ventas") and t.ingresos > 0:
        salida["EV / Ventas"] = (med["ev_ventas"] * t.ingresos - deuda_neta) / acciones
    if med.get("p_fcf") and t.fcf > 0:
        salida["P / FCF"] = med["p_fcf"] * t.fcf / acciones
    return salida
