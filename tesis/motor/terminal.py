"""Valor terminal (05 §4): value driver (por defecto), Gordon y múltiplo de salida. Se calculan los tres; rige el
elegido y los otros dos son contraste. Se descuenta en f + N − 1 (fin del año N)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

__all__ = ["Terminal", "terminal"]

METODOS = ("value_driver", "gordon", "multiplo_salida")


@dataclass
class Terminal:
    metodo: str
    valores: Dict[str, Optional[float]]            # VT sin descontar por método
    momento: float
    factor: float
    valor_actual: float                            # el del método que rige
    bloqueos: List[str] = field(default_factory=list)
    avisos: List[str] = field(default_factory=list)

    @property
    def valor(self) -> Optional[float]:
        return self.valores.get(self.metodo)


def terminal(nopat_n: float, fcff_n: float, ebitda_n: float, wacc: float, g: float, ronic: Optional[float],
             multiplo: Optional[float], fraccion: float, n: int, metodo: str, rf: Optional[float],
             g_max: float, wacc_menos_g_min: float, ronic_max_x_wacc: float, contraste_aviso: float = 0.15) -> Terminal:
    bloqueos: List[str] = []
    if rf is not None and g >= rf:
        bloqueos.append(f"g ({g:.2%}) ≥ tipo libre de riesgo ({rf:.2%})")
    if g > g_max:
        bloqueos.append(f"g ({g:.2%}) > máximo admitido ({g_max:.2%})")
    if wacc - g < wacc_menos_g_min:
        bloqueos.append(f"WACC − g = {(wacc - g) * 100:.2f} p. p. < {wacc_menos_g_min * 100:.1f} p. p.")
    valores: Dict[str, Optional[float]] = {m: None for m in METODOS}
    avisos: List[str] = []
    if wacc > g:
        r = ronic if ronic is not None else None
        if r is not None and r > 0:
            valores["value_driver"] = nopat_n * (1 + g) * (1 - g / r) / (wacc - g)
            if r > ronic_max_x_wacc * wacc:
                avisos.append(f"RONIC ({r:.1%}) > {ronic_max_x_wacc:g} × WACC")
        valores["gordon"] = fcff_n * (1 + g) / (wacc - g)
    if multiplo is not None:
        valores["multiplo_salida"] = ebitda_n * multiplo
    if valores.get(metodo) is None:
        bloqueos.append(f"el método de valor terminal elegido ({metodo}) no tiene sus entradas")
    momento = fraccion + n - 1
    factor = (1 + wacc) ** -momento
    vd, go = valores.get("value_driver"), valores.get("gordon")
    if vd and go and abs(vd / go - 1) > contraste_aviso:
        avisos.append(f"value driver y Gordon difieren un {abs(vd / go - 1):.0%} (aviso desde {contraste_aviso:.0%})")
    return Terminal(metodo, valores, momento, factor, (valores.get(metodo) or 0.0) * factor, bloqueos, avisos)
