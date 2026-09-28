"""Comprobaciones de los paquetes sectoriales (05 §2): avisos del motor para el analista, no bloqueos.

Cada paquete de `config/sectores.yaml` lista las suyas; los umbrales están en `config/umbrales.yaml` › `sector`. Todas
leen Hechos verificados (o la SEC, para la mediana de ciclo y el plan de pensiones) y las entradas del analista: sin
dato, no hay aviso inventado; se dice que no se pudo comprobar.

- regla_40 (software): crecimiento de ingresos + margen de FCF del último ejercicio frente a `regla_40_min`.
- sbc_ingresos (software): SBC / ingresos del último ejercicio por encima de `sbc_ingresos_max`; y, con la política de
  coste de caja, el SBC del año 1 del escenario base por debajo del histórico en más de `sbc_proyeccion_pp`.
- ciclo (semiconductores): margen operativo del año base y margen terminal del escenario base frente a la mediana de
  `ciclo_anios` ejercicios; a más de `ciclo_desvio_pp`, pico o valle.
- arrendamientos (consumo, telecom): pasivos por arrendamiento fuera de la deuda del puente por encima de
  `arrendamientos_ve_max` del VE de mercado.
- pensiones (industrial): déficit del plan de prestación definida sin ajuste del puente que lo recoja, por encima de
  `pensiones_cap_max` de la capitalización.
- kd_apalancamiento (utilities): D / (D + E) de mercado por encima de `apalancamiento_max`; coste de la deuda por debajo
  del tipo sin riesgo.
"""

from __future__ import annotations

import statistics
from datetime import date
from typing import List, Mapping, Optional

from ..formato import mln, numero, pct

__all__ = ["comprobar"]


def _anuales(hechos, periodos, campo: str):
    return [(p, hechos[(campo, p)].valor) for p in sorted(periodos.get("anuales") or [], key=lambda p: p.fin)
            if hechos.get((campo, p)) is not None and hechos[(campo, p)].hay_dato]


def _regla_40(hechos, periodos, u: Mapping) -> List[str]:
    ingresos, fcf = dict(_anuales(hechos, periodos, "ingresos")), dict(_anuales(hechos, periodos, "fcf"))
    anios = sorted(ingresos, key=lambda p: p.fin)
    if len(anios) < 2 or anios[-1] not in fcf or not ingresos[anios[-2]]:
        return ["Regla del 40 (software): sin dos ejercicios de ingresos y el FCF del último en la SEC; no se comprueba"]
    ult, ant = anios[-1], anios[-2]
    crec, margen = ingresos[ult] / ingresos[ant] - 1, fcf[ult] / ingresos[ult]
    if crec + margen < float(u.get("regla_40_min", 0.40)):
        return [f"Regla del 40 (software): crecimiento de ingresos del {pct(crec)} + margen de FCF del {pct(margen)} = "
                f"{pct(crec + margen)} en el ejercicio cerrado el {ult.fin:%d/%m/%Y}, por debajo del {pct(float(u.get('regla_40_min', 0.40)), 0)}"]
    return []


def _sbc(hechos, periodos, p, u: Mapping) -> List[str]:
    ingresos, sbc = dict(_anuales(hechos, periodos, "ingresos")), dict(_anuales(hechos, periodos, "sbc"))
    comunes = [x for x in sorted(ingresos, key=lambda x: x.fin) if x in sbc and ingresos[x]]
    if not comunes:
        return ["SBC sobre ingresos (software): sin SBC del último ejercicio en la SEC; no se comprueba"]
    ult = comunes[-1]
    ratio = abs(sbc[ult]) / ingresos[ult]
    salida = []
    if ratio > float(u.get("sbc_ingresos_max", 0.10)):
        salida.append(f"SBC del {pct(ratio)} de los ingresos en el ejercicio cerrado el {ult.fin:%d/%m/%Y} (umbral "
                      f"{pct(float(u.get('sbc_ingresos_max', 0.10)), 0)}): con la política «{p.sbc_politica.replace('_', ' ')}», "
                      "compruebe que su coste está en el FCFF o en la dilución")
    base = p.escenarios.get("base")
    if base is not None and p.sbc_politica == "coste_de_caja" and base.sbc:
        if ratio - base.sbc[0] > float(u.get("sbc_proyeccion_pp", 0.03)):
            salida.append(f"SBC del escenario base en el año 1 del {pct(base.sbc[0])} de los ingresos frente al {pct(ratio)} del último "
                          "ejercicio: una caída así sube el FCFF; justifíquela en la narrativa del escenario")
    return salida


def _ciclo(facts, p, u: Mapping) -> List[str]:
    # la misma mediana que propone el asistente como margen terminal del base (F12, regla 13)
    from .historico import margen_ciclo
    minimo, maximo = (int(x) for x in u.get("ciclo_anios", [7, 10]))
    ciclo = margen_ciclo(facts, p.fecha_valoracion, minimo, maximo)
    if not ciclo.hay_valor:
        return [f"Ciclo (semiconductores): {ciclo.motivo}; no se comprueba"]
    margenes = list(ciclo.anios)
    mediana = statistics.median(m for _, m in margenes)
    desvio = float(u.get("ciclo_desvio_pp", 0.05))
    salida = []
    fin, ultimo = margenes[-1]
    if abs(ultimo - mediana) > desvio:
        salida.append(f"Ciclo (semiconductores): el año base (ejercicio cerrado el {fin:%d/%m/%Y}) tiene un margen operativo del "
                      f"{pct(ultimo)} frente a una mediana del {pct(mediana)} en {len(margenes)} ejercicios: año base en "
                      f"{'pico' if ultimo > mediana else 'valle'} de ciclo")
    base = p.escenarios.get("base")
    if base is not None and base.margen and abs(base.margen[-1] - mediana) > desvio:
        salida.append(f"Ciclo (semiconductores): el margen terminal del escenario base ({pct(base.margen[-1])}) se aparta más de "
                      f"{numero(desvio * 100, 0)} p. p. de la mediana de ciclo ({pct(mediana)}); 05 §2 pide un margen normalizado de ciclo medio")
    return salida


def _arrendamientos(p, m, arrend: Optional[float], u: Mapping) -> List[str]:
    if p.arrendamientos != "fuera_de_deuda" or not arrend or not m.ev_mercado:
        return []
    peso = arrend / m.ev_mercado
    if peso > float(u.get("arrendamientos_ve_max", 0.05)):
        return [f"Arrendamientos de {mln(arrend)} mln USD ({pct(peso)} del VE de mercado) fuera de la deuda del puente: en este "
                "sector suelen tratarse como deuda (paso 7, arrendamientos)"]
    return []


def _pensiones(facts, p, m, u: Mapping) -> List[str]:
    filas = (((facts.get("facts") or {}).get("us-gaap") or {}).get("DefinedBenefitPlanFundedStatusOfPlan") or {}).get("units", {}).get("USD", [])
    filas = [f for f in filas if "start" not in f and date.fromisoformat(f["end"]) <= p.fecha_valoracion]
    if not filas or not m.cap_mercado:
        return []                                          # sin plan de prestación definida en la SEC: no es una partida suya
    f = max(filas, key=lambda f: (f["end"], f["filed"]))
    deficit = -float(f["val"])
    recogido = any(a.get("concepto") == "pensiones" for a in p.ajustes_puente)
    if deficit > 0 and not recogido and deficit / m.cap_mercado > float(u.get("pensiones_cap_max", 0.02)):
        return [f"Pensiones: déficit del plan de prestación definida de {mln(deficit)} mln USD a {date.fromisoformat(f['end']):%d/%m/%Y} "
                f"({pct(deficit / m.cap_mercado)} de la capitalización) sin ajuste en el puente (paso 7, ajustes del puente)"]
    return []


def _kd_apalancamiento(m, w, u: Mapping) -> List[str]:
    salida = []
    if w is not None and w.peso_d > float(u.get("apalancamiento_max", 0.60)):
        salida.append(f"Apalancamiento de mercado D / (D + E) del {pct(w.peso_d)}, por encima del "
                      f"{pct(float(u.get('apalancamiento_max', 0.60)), 0)}: revise el coste de la deuda y la beta reapalancada")
    if w is not None and w.kd < w.rf:
        salida.append(f"Coste de la deuda antes de impuestos ({pct(w.kd, 2)}) por debajo del tipo sin riesgo ({pct(w.rf, 2)})")
    return salida


def comprobar(p, hechos, periodos: Mapping, facts: dict, m, w, arrend: Optional[float], u: Mapping, sectores: Mapping) -> List[str]:
    """Los avisos de las comprobaciones del paquete del analista (`p.paquete`)."""
    lista = ((sectores.get("paquetes") or {}).get(p.paquete) or {}).get("comprobaciones") or []
    salida: List[str] = []
    for c in lista:
        if c == "regla_40":
            salida += _regla_40(hechos, periodos, u)
        elif c == "sbc_ingresos":
            salida += _sbc(hechos, periodos, p, u)
        elif c == "ciclo":
            salida += _ciclo(facts, p, u)
        elif c == "arrendamientos":
            salida += _arrendamientos(p, m, arrend, u)
        elif c == "pensiones":
            salida += _pensiones(facts, p, m, u)
        elif c == "kd_apalancamiento":
            salida += _kd_apalancamiento(m, w, u)
    return salida
