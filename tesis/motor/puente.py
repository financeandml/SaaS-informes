"""Puente de valor de empresa a valor por acción (05 §6), con los importes del último balance publicado (los mismos del
apartado 9) y las acciones diluidas por el método de autocartera, o las diluidas medias del último trimestre si faltan
datos (marcado)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import List, Optional

__all__ = ["Linea", "Puente", "puente", "acciones_diluidas"]


@dataclass
class Linea:
    rotulo: str
    valor: float            # importe positivo; el signo dice si suma o resta
    signo: int
    fuente: str


@dataclass
class Puente:
    lineas: List[Linea]
    acciones: float
    acciones_nota: str
    fecha_balance: Optional[date]
    faltas: List[str] = field(default_factory=list)

    @property
    def ajuste(self) -> float:
        return sum(l.signo * l.valor for l in self.lineas)

    @property
    def deuda_neta(self) -> float:
        """Deuda financiera (y arrendamientos si la política los incluye) − caja − inversiones a corto."""
        return -sum(l.signo * l.valor for l in self.lineas if l.rotulo.startswith(("Deuda", "Arrendamientos", "Caja", "Inversiones")))

    def fondos_propios(self, ev: float) -> float:
        return ev + self.ajuste

    def por_accion(self, ev: float) -> float:
        return self.fondos_propios(ev) / self.acciones


def acciones_diluidas(basicas: Optional[float], opciones: Optional[float], precio_ejercicio: Optional[float],
                      rsu: Optional[float], precio: float, diluidas_medias: Optional[float], trimestre: str) -> tuple:
    """(acciones, nota). Método de autocartera: cada opción en dinero añade N × (1 − K / P)."""
    if basicas is not None and rsu is not None and (opciones is None or precio_ejercicio is not None):
        tsm = opciones * max(0.0, 1 - precio_ejercicio / precio) if opciones else 0.0
        return basicas + tsm + rsu, (f"básicas de la portada + opciones por el método de autocartera ({tsm / 1e6:,.1f} M) "
                                      f"+ RSU pendientes ({rsu / 1e6:,.1f} M)").replace(",", "X").replace(".", ",").replace("X", ".")
    if diluidas_medias is not None:
        return diluidas_medias, (f"diluidas medias del {trimestre}: la SEC no publica en XBRL todas las piezas del método de "
                                 "autocartera (opciones con su precio de ejercicio y RSU pendientes)")
    return None, "sin acciones: ni componentes de la dilución ni diluidas medias"


def puente(deuda_financiera: Optional[float], arrendamientos: Optional[float], caja: Optional[float],
           inversiones_cp: Optional[float], minoritarios: Optional[float], ajustes: List[dict], incluir_arrendamientos: bool,
           acciones: float, acciones_nota: str, fecha_balance: Optional[date], fuente_balance: str) -> Puente:
    lineas: List[Linea] = []
    faltas: List[str] = []
    for rotulo, valor, signo in (("Deuda financiera", deuda_financiera, -1), ("Caja y equivalentes", caja, +1),
                                 ("Inversiones a corto plazo", inversiones_cp, +1)):
        if valor is None:
            faltas.append(f"puente: falta «{rotulo.lower()}» en el último balance")
            continue
        lineas.append(Linea(rotulo, valor, signo, fuente_balance))
    if incluir_arrendamientos:
        if arrendamientos is None:
            faltas.append("puente: la política incluye arrendamientos y el balance no los publica")
        else:
            lineas.append(Linea("Arrendamientos", arrendamientos, -1, fuente_balance))
    if minoritarios:
        lineas.append(Linea("Intereses minoritarios", minoritarios, -1, fuente_balance))
    for a in ajustes:
        signo = -1 if a.get("concepto") in ("minoritarios", "preferentes", "pensiones", "litigios") else +1
        if a.get("signo") in (-1, 1):
            signo = a["signo"]
        lineas.append(Linea(f"Ajuste del analista: {a.get('concepto', 'otros')}", abs(float(a["importe"])) * 1e6, signo,
                            "analista, con evidencia"))
    return Puente(lineas, acciones, acciones_nota, fecha_balance, faltas)
