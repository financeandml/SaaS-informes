"""El auditor de datos: que los números cuadren entre sí, y que lo que falte se derive o se diga.

El contraste compara cada cifra con su fuente (documento contra SEC) y la doble comprobación relee lo impreso. Entre
las dos queda un hueco: **las cifras pueden ser correctas una a una y contradecirse entre ellas**. Un activo que no es
la suma del pasivo y el patrimonio, un beneficio que no es el resultado antes de impuestos menos los impuestos, un BPA
que no es el beneficio entre las acciones: cada número viene de su fuente y parece bueno, y el conjunto es falso.

Este módulo es el único sitio donde vive esa aritmética. Hace tres cosas, en este orden:

1. **Comprueba** cada identidad contable sobre los hechos ya contrastados, periodo a periodo, con su tolerancia.
2. **Cierra** las que tienen un solo hueco y son exactas: si de «BAI − impuestos = beneficio neto» falta el último
   término, sale de los otros dos, con su fórmula y marcado como derivado (nunca como dato publicado).
3. **Declara** lo que no puede saber: qué término falta, en qué periodo y por qué, para que salga N/A con su motivo.

Lo que no hace: cuadrar a la fuerza. Si una identidad no cuadra, se dice cuánto y dónde; no se toca ninguna cifra.
Una identidad que puede no cerrar por un concepto que el informe no lleva —los intereses minoritarios en el balance—
lo lleva escrito en su nota, y por eso no se cierra nunca a partir de ella.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from .formato import numero
from .hechos import Capa, Hecho, Periodo, derivar

__all__ = ["Identidad", "Comprobacion", "Auditoria", "IDENTIDADES", "auditar", "aplicar"]

Hechos = Dict[Tuple[str, Periodo], Hecho]

INSTANTE, FLUJO = "instante", "flujo"


@dataclass(frozen=True)
class Identidad:
    """Una igualdad entre cifras publicadas: total = Σ partes (cada parte con su signo)."""
    clave: str
    rotulo: str
    total: str
    partes: Tuple[Tuple[str, int], ...]
    ambito: str
    cerrable: bool = False          # ¿se puede despejar el término que falte? Solo si la igualdad es exacta
    tolerancia: float = 0.005       # 0,5 % del total: los estados vienen redondeados a millones
    nota: str = ""


IDENTIDADES: Tuple[Identidad, ...] = (
    Identidad("pasivo", "Total pasivo = Pasivo corriente + Pasivo no corriente", "pasivo_total",
              (("pasivo_corriente", 1), ("pasivo_no_corriente", 1)), INSTANTE, cerrable=True,
              nota="muchos balances no imprimen el total del pasivo y sí sus dos mitades: entonces el total sale de ellas."),
    Identidad("balance", "Activo total = Pasivo total + Patrimonio neto", "total_activo",
              (("pasivo_total", 1), ("patrimonio", 1)), INSTANTE, cerrable=False, tolerancia=0.02,
              nota="si no cierra, la diferencia suele ser el interés minoritario, que este informe no lleva como campo "
                   "propio: el patrimonio que imprime es el del grupo, como el concepto de la SEC."),
    Identidad("deuda", "Deuda bruta = Deuda a corto plazo + Deuda a largo plazo", "deuda_bruta",
              (("deuda_cp", 1), ("deuda_lp", 1)), INSTANTE, cerrable=True),
    Identidad("resultado", "Beneficio neto = Resultado antes de impuestos − Impuesto sobre beneficios", "beneficio_neto",
              (("bai", 1), ("impuestos", -1)), FLUJO, cerrable=True,
              nota="el impuesto se guarda con su signo contable; aquí se resta del resultado antes de impuestos."),
    Identidad("ebitda", "EBITDA = EBIT + Amortización del inmovilizado", "ebitda",
              (("ebit", 1), ("amortizacion", 1)), FLUJO, cerrable=True),
    Identidad("fcf", "Flujo de caja libre = Flujo de caja operativo − Capex", "fcf",
              (("cfo", 1), ("capex", -1)), FLUJO, cerrable=True,
              nota="el capex se guarda con su signo contable (salida de caja)."),
    Identidad("bpa", "Beneficio neto = BPA diluido × Acciones diluidas", "beneficio_neto",
              (("bpa_diluido", 0), ("acciones_diluidas", 0)), FLUJO, cerrable=False, tolerancia=0.01,
              nota="las tres cifras se publican por separado: si no cuadran, o una está mal leída o mal escalada, o el BPA no se "
                   "calcula sobre todo el beneficio —dividendo preferente, acciones emitidas a mitad de periodo—, o es el "
                   "redondeo del BPA a céntimos sobre miles de millones de acciones."),
)


@dataclass
class Comprobacion:
    identidad: str
    rotulo: str
    periodo: str
    estado: str                      # «cuadra» | «no cuadra» | «derivada» | «sin datos»
    total: Optional[float] = None
    suma: Optional[float] = None
    diferencia: Optional[float] = None
    motivo: str = ""

    @property
    def linea(self) -> str:
        glifo = {"cuadra": "✓", "no cuadra": "≠", "derivada": "∑", "sin datos": "—"}[self.estado]
        cifras = ""
        if self.total is not None and self.suma is not None:
            cifras = f" · {numero(self.total)} frente a {numero(self.suma)} (dif. {numero(self.diferencia)})"
        return f"{glifo} {self.rotulo} · {self.periodo}{cifras}{(' · ' + self.motivo) if self.motivo else ''}"


@dataclass
class Auditoria:
    comprobaciones: List[Comprobacion] = field(default_factory=list)
    derivadas: Dict[Tuple[str, Periodo], Hecho] = field(default_factory=dict)

    @property
    def resumen(self) -> Dict[str, int]:
        r = {"cuadra": 0, "no cuadra": 0, "derivada": 0, "sin datos": 0}
        for c in self.comprobaciones:
            r[c.estado] = r.get(c.estado, 0) + 1
        return r

    @property
    def contradicciones(self) -> List[Comprobacion]:
        return [c for c in self.comprobaciones if c.estado == "no cuadra"]

    def como_texto(self) -> str:
        return "\n".join(c.linea for c in self.comprobaciones)


def _valor(hechos: Hechos, clave: str, p: Periodo) -> Optional[Hecho]:
    h = hechos.get((clave, p))
    return h if h is not None and h.hay_dato else None


def _bpa(hechos: Hechos, ident: Identidad, p: Periodo) -> Optional[Comprobacion]:
    """La única identidad que no es una suma: beneficio = BPA × acciones."""
    neto, bpa, acciones = _valor(hechos, "beneficio_neto", p), _valor(hechos, "bpa_diluido", p), _valor(hechos, "acciones_diluidas", p)
    faltan = [k for k, h in (("beneficio neto", neto), ("BPA diluido", bpa), ("acciones diluidas", acciones)) if h is None]
    if faltan:
        return Comprobacion(ident.clave, ident.rotulo, p.clave, "sin datos", motivo="falta " + ", ".join(faltan))
    producto = bpa.valor * acciones.valor
    dif = neto.valor - producto
    cuadra = abs(dif) <= ident.tolerancia * max(abs(neto.valor), 1.0)
    return Comprobacion(ident.clave, ident.rotulo, p.clave, "cuadra" if cuadra else "no cuadra",
                        neto.valor, producto, dif, "" if cuadra else ident.nota)


def _comprobar(hechos: Hechos, ident: Identidad, p: Periodo) -> Tuple[Comprobacion, Optional[Tuple[str, Hecho]]]:
    """Comprueba la identidad en ese periodo; si falta exactamente un término y la igualdad es exacta, lo despeja."""
    if ident.clave == "bpa":
        return _bpa(hechos, ident, p), None
    total = _valor(hechos, ident.total, p)
    partes = {k: _valor(hechos, k, p) for k, _ in ident.partes}
    ausentes = [k for k, h in partes.items() if h is None] + ([] if total is not None else [ident.total])
    if not ausentes:
        suma = sum(signo * partes[k].valor for k, signo in ident.partes)
        dif = total.valor - suma
        cuadra = abs(dif) <= ident.tolerancia * max(abs(total.valor), 1.0)
        return Comprobacion(ident.clave, ident.rotulo, p.clave, "cuadra" if cuadra else "no cuadra",
                            total.valor, suma, dif, "" if cuadra else ident.nota), None
    if len(ausentes) > 1 or not ident.cerrable:
        return Comprobacion(ident.clave, ident.rotulo, p.clave, "sin datos",
                            motivo="falta " + ", ".join(ausentes) + ("" if ident.cerrable else "; no se despeja: " + (ident.nota or "la igualdad no es exacta"))), None
    hueco = ausentes[0]
    entradas = {k: h for k, h in partes.items() if h is not None}
    if total is not None:
        entradas[ident.total] = total
    signos = dict(ident.partes)
    if hueco == ident.total:
        formula = " ".join(f"{'+' if s > 0 else '−'} {k}" for k, s in ident.partes).lstrip("+ ")
        calculo = lambda **kw: sum(signos[k] * v for k, v in kw.items())
    else:
        otras = [(k, s) for k, s in ident.partes if k != hueco]
        formula = f"({ident.total} " + " ".join(f"{'−' if s > 0 else '+'} {k}" for k, s in otras) + f") / {signos[hueco]:+d}"
        calculo = lambda **kw: (kw[ident.total] - sum(signos[k] * kw[k] for k, _ in otras)) / signos[hueco]
    h = derivar(hueco, p, f"{ident.rotulo}: {formula}", entradas, calculo,
                unidad=next(iter(entradas.values())).unidad)
    return Comprobacion(ident.clave, ident.rotulo, p.clave, "derivada" if h.hay_dato else "sin datos",
                        motivo=f"«{hueco}» no lo publica ninguna fuente para {p.clave}: se despeja de la identidad y sale marcado como derivado"), (hueco, h)


def auditar(hechos: Hechos, flujos: Sequence[Periodo], instantes: Sequence[Periodo]) -> Auditoria:
    """Pasa todas las identidades por todos los periodos del informe."""
    a = Auditoria()
    # lo que una identidad despeja queda disponible para las siguientes: el total del pasivo sale de sus dos mitades
    # y, con él, ya se puede comprobar que el activo es el pasivo más el patrimonio. Por eso el orden del catálogo importa.
    mesa = dict(hechos)
    for ident in IDENTIDADES:
        for p in (instantes if ident.ambito == INSTANTE else flujos):
            comp, derivada = _comprobar(mesa, ident, p)
            a.comprobaciones.append(comp)
            if derivada is not None and derivada[1].hay_dato:
                a.derivadas[(derivada[0], p)] = derivada[1]
                mesa[(derivada[0], p)] = derivada[1]
    return a


def aplicar(hechos: Hechos, auditoria: Auditoria) -> Hechos:
    """Los hechos con lo despejado añadido. Nunca pisa un dato publicado: solo rellena huecos."""
    salida = dict(hechos)
    for clave, h in auditoria.derivadas.items():
        actual = salida.get(clave)
        if actual is None or not actual.hay_dato:
            salida[clave] = h
    return salida
