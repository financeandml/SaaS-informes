"""Parte H, lo que se calcula sobre lo que publica la bolsa (01 › 31–32).

31: los precios de ejercicio con más interés abierto y el máximo dolor del vencimiento mensual más próximo.
32: la volatilidad implícita en el dinero (la excepción de Yahoo) frente a la realizada a 30 y 90 días (cierres oficiales
de Nasdaq) y el movimiento que descuenta el straddle en el dinero de la cadena de Nasdaq para el primer vencimiento
tras la próxima presentación de resultados. Todo es ∑ (derivado) con su fórmula al pasar el ratón: son lecturas de
mercado, no hechos de la compañía.
"""

from __future__ import annotations

import math
import re
import statistics
from datetime import date, datetime, timedelta
from typing import Mapping, Optional

from ..formato import Celda, fecha as f_fecha, numero, pct

__all__ = ["mensual", "max_dolor", "mayores", "straddle", "vol_realizada", "subyacente", "cuadro_strikes", "cuadro_vi_realizada", "cuadro_movimiento"]


def _fecha(texto: str) -> Optional[date]:
    for formato in ("%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(str(texto).strip(), formato).date()
        except ValueError:
            continue
    return None


def mensual(cadena, hoy: date):
    """(fecha, vencimiento) del mensual más próximo (el tercer viernes del mes) con filas, o None."""
    for v in cadena.vencimientos:
        f = _fecha(v.fecha)
        if f is not None and f >= hoy and f.weekday() == 4 and 15 <= f.day <= 21 and v.strikes:
            return f, v
    return None


def max_dolor(strikes) -> Optional[float]:
    """El precio de ejercicio en el que el conjunto de opciones del vencimiento vale menos al vencer:
    mín_S Σ [interés abierto call × máx(S − K, 0) + interés abierto put × máx(K − S, 0)]."""
    con_oi = [s for s in strikes if (s.oi_calls or 0) + (s.oi_puts or 0) > 0]
    if not con_oi:
        return None

    def valor(precio: float) -> float:
        return sum((s.oi_calls or 0) * max(precio - s.precio, 0) + (s.oi_puts or 0) * max(s.precio - precio, 0) for s in con_oi)
    return min(sorted({s.precio for s in strikes}), key=valor)


def mayores(strikes, n: int = 5):
    return sorted((s for s in strikes if (s.oi_calls or 0) + (s.oi_puts or 0) > 0),
                  key=lambda s: (-((s.oi_calls or 0) + (s.oi_puts or 0)), s.precio))[:n]


def straddle(vencimiento, subyacente_: float):
    """La fila en el dinero (el precio de ejercicio más cercano al subyacente con prima de call y de put)."""
    filas = [s for s in vencimiento.strikes if s.call is not None and s.put is not None]
    return min(filas, key=lambda s: (abs(s.precio - subyacente_), s.precio)) if filas else None


def vol_realizada(sesiones: Mapping, hasta: date, n: int) -> Optional[float]:
    """Desviación típica de los n últimos rendimientos logarítmicos diarios hasta `hasta`, anualizada (× √252)."""
    cierres = [sesiones[f].cierre for f in sorted(f for f in sesiones if f <= hasta)][-(n + 1):]
    r = [math.log(b / a) for a, b in zip(cierres, cierres[1:]) if a and b]
    return statistics.pstdev(r) * math.sqrt(252) if len(r) == n else None


def subyacente(ultimo: str) -> Optional[float]:
    """El precio de la última operación que acompaña a la cadena («LAST TRADE: $194.26 (…)»): el de la misma hora que las primas."""
    m = re.search(r"\$\s*([\d,]+(?:\.\d+)?)", str(ultimo or ""))
    return float(m.group(1).replace(",", "")) if m else None


def _d(texto: str, formula: str, negativo: bool = False) -> Celda:
    return Celda(texto, "∑", "D", "negativo" if negativo else "valor", formula)


def _na(motivo: str) -> Celda:
    return Celda("N/A", "", "", "na", motivo)


def cuadro_strikes(n, p, hoy: date):
    """31 · los precios de ejercicio con más interés abierto y el máximo dolor del mensual más próximo."""
    from .informe import Cuadro, FilaCuadro
    c = getattr(p, "cadena", None)
    m = mensual(c, hoy) if c is not None else None
    if m is None:
        return None
    fecha_m, v = m
    dolor = max_dolor(v.strikes)
    filas = [FilaCuadro(f"{numero(s.precio, 2)} USD", [Celda(numero(s.oi_calls or 0), "", "Hd", "valor", ""), Celda(numero(s.oi_puts or 0), "", "Hd", "valor", ""),
                                                _d(numero((s.oi_calls or 0) + (s.oi_puts or 0)), "interés abierto calls + puts")], capa="Hd")
             for s in mayores(v.strikes)]
    texto = (f"Máximo dolor del vencimiento: {numero(dolor, 2)} USD (el precio de ejercicio en que el conjunto de opciones vale menos al "
             "vencer: mín Σ interés abierto × valor intrínseco)." if dolor is not None else "Sin interés abierto: sin máximo dolor.")
    return Cuadro(n.siguiente(), f"Precios de ejercicio con más interés abierto · vencimiento mensual del {f_fecha(fecha_m)}",
                  ["Int. abierto calls", "Int. abierto puts", "Total"], filas, f"Fuente: Nasdaq, cadena de opciones (la del cuadro anterior). {texto}")


def cuadro_vi_realizada(n, p, sesiones: Mapping, hasta: date, hoy: date):
    """32 · la VI en el dinero del vencimiento más cercano a 30 días frente a la realizada a 30 y 90 días (21 y 63 sesiones)."""
    from .informe import Cuadro, FilaCuadro
    iv = getattr(p, "iv", None)
    con_iv = [x for x in (iv.vencimientos if iv is not None else []) if x.hay_iv and (x.iv_call_atm is not None or x.iv_put_atm is not None)]
    elegido = min(con_iv, key=lambda x: abs((x.fecha - hoy).days - 30), default=None)
    filas, vi = [], None
    if elegido is not None:
        lados = [x for x in (elegido.iv_call_atm, elegido.iv_put_atm) if x is not None]
        vi = sum(lados) / len(lados)
        filas.append(FilaCuadro(f"VI en el dinero · vencimiento del {f_fecha(elegido.fecha)} ({(elegido.fecha - hoy).days} días)",
                                [_d(pct(vi, 1), "media de la VI call y put en el dinero (cuadro de la volatilidad implícita)")], capa="D"))
    else:
        filas.append(FilaCuadro("VI en el dinero", [_na((getattr(p, "faltan", None) or {}).get("iv", "sin volatilidad implícita que cuadre con la bolsa"))], capa="D"))
    r30, r90 = vol_realizada(sesiones, hasta, 21), vol_realizada(sesiones, hasta, 63)
    for rotulo, r, k in (("Volatilidad realizada a 30 días", r30, 21), ("Volatilidad realizada a 90 días", r90, 63)):
        filas.append(FilaCuadro(rotulo, [_d(pct(r, 1), f"desviación típica de los {k} últimos rendimientos diarios × √252, cierres oficiales de Nasdaq hasta el {f_fecha(hasta)}")
                                         if r is not None else _na(f"menos de {k + 1} cierres oficiales")], capa="D"))
    if vi is not None and r30 is not None:
        filas.append(FilaCuadro("VI − realizada a 30 días", [_d(f"{'+' if vi > r30 else ''}{numero((vi - r30) * 100, 1)} p.p.", f"{pct(vi, 1)} − {pct(r30, 1)}", vi < r30)], capa="D"))
    return Cuadro(n.siguiente(), "Volatilidad implícita frente a la realizada", ["Valor"], filas,
                  "Fuente: Yahoo Finance para la VI (excepción autorizada; la bolsa no la publica) y cierres oficiales de Nasdaq para la "
                  "realizada. Una VI por encima de la realizada es lo que el mercado paga por cubrirse.")


def cuadro_movimiento(n, p, resultados: Optional[date], hoy: date):
    """32 · el straddle en el dinero del primer vencimiento tras la presentación de resultados (cadena de Nasdaq)."""
    from .informe import Cuadro, FilaCuadro
    c = getattr(p, "cadena", None)
    s0 = subyacente(c.ultimo) if c is not None else None
    if c is None or resultados is None or not s0:
        return None
    tras = next(((f, v) for f, v in ((_fecha(v.fecha), v) for v in c.vencimientos) if f is not None and f >= resultados and v.strikes), None)
    s = straddle(tras[1], s0) if tras is not None else None
    if s is None:
        return None
    total = s.call + s.put
    fila = FilaCuadro(f"Vencimiento del {f_fecha(tras[0])} ({(tras[0] - hoy).days} días) · precio de ejercicio {numero(s.precio, 2)} USD",
                      [_d(f"±{numero(total, 2)} USD", f"call {numero(s.call, 2)} + put {numero(s.put, 2)} (punto medio compra/venta)"),
                       _d(f"±{pct(total / s0, 1)}", f"{numero(total, 2)} / {numero(s0, 2)} (subyacente de la cadena)")], capa="D")
    return Cuadro(n.siguiente(), f"Movimiento que descuenta el mercado hasta el primer vencimiento tras los resultados del {f_fecha(resultados)}",
                  ["Straddle en el dinero", "Sobre el subyacente"], [fila],
                  "Fuente: Nasdaq, cadena de opciones. El straddle (call + put en el dinero) aproxima el movimiento, en uno u otro sentido, "
                  "que el mercado paga hasta ese vencimiento: incluye la presentación y todo el plazo que queda hasta él, que pesa más "
                  "cuanto más lejos está la fecha.")
