"""El hecho: la unidad de todo lo que el informe imprime.

Ninguna cifra viaja como número suelto. Un `Hecho` lleva su valor, su estado
—hay dato · es cero · no hay dato—, la capa de la que procede, de dónde salió
(documento, formulario, página, rectángulo, concepto XBRL) y, si es derivado, la
fórmula y los hechos de los que se calculó. Esto último es lo que permite afirmar
por máquina que dos cifras que expresan el mismo hecho son el mismo objeto.

Las comprobaciones viven en el constructor y no en quien lo usa: un `N/A` sin
motivo, un cero rotulado como «valor» o un derivado sin fórmula no se pueden
construir. Cuando algo así llega al informe es porque se construyó mal aquí, y
por eso aquí se rechaza.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date
from enum import Enum
from typing import Callable, Dict, Mapping, Optional, Tuple

__all__ = [
    "Capa", "Certeza", "Cita", "Contraste", "Estado", "Hecho", "Origen", "Periodo",
    "de_valor", "derivar", "na",
]


class Estado(str, Enum):
    VALOR = "valor"
    CERO = "cero"
    NA = "na"


class Capa(str, Enum):
    """De dónde procede la cifra. Se rotula distinto en el informe y no se mezclan."""
    SEC = "H"          # publicado en un formulario SEC (XBRL o texto)
    DOCUMENTO = "Hd"   # leído en un adjunto del analista; la SEC no lo trae como tal
    SUPUESTO = "S"     # estimación o decisión del analista
    DERIVADO = "D"     # cálculo determinista sobre hechos y supuestos


class Certeza(str, Enum):
    ALTA = "alta"
    MEDIA = "media"
    BAJA = "baja"


class Contraste(str, Enum):
    """Resultado del contraste SEC ↔ adjunto. El glifo es el que se imprime."""
    SIN_CONTRASTAR = ""
    CONFIRMADO = "✓"       # SEC y documento coinciden
    DISCREPANTE = "≠"      # ambos existen y no coinciden: decide el analista
    SOLO_SEC = "◐"         # no se halló en los adjuntos
    SOLO_DOCUMENTO = "◑"   # la SEC no lo publica
    HUECO = "—"            # ni SEC ni adjuntos
    DERIVADO = "∑"         # calculado de hechos contrastados


@dataclass(frozen=True, order=True)
class Periodo:
    """Un ejercicio, un trimestre, un acumulado o un instante (balance).

    `inicio` a `None` es un instante. Se ordena por fin y luego por inicio, de
    modo que una lista de periodos queda cronológica sin más.
    """
    fin: date
    inicio: Optional[date] = None

    @property
    def es_instante(self) -> bool:
        return self.inicio is None

    @property
    def meses(self) -> Optional[int]:
        """Duración en meses, medida en días y redondeada.

        Contando por número de mes, el ejercicio de 52/53 semanas —Qualcomm, Apple, Cisco: cierran el domingo más
        cercano a fin de mes, así que el de 2025 va del 29/09/2024 al 28/09/2025— salía de trece meses, y como el
        informe selecciona los anuales con `meses == 12`, la empresa entera se quedaba sin columnas anuales.
        """
        if self.inicio is None:
            return None
        return max(1, round(((self.fin - self.inicio).days + 1) / 30.44))

    @property
    def clave(self) -> str:
        """`FY2025`, `2T26`, `6M26`, `9M25` o `@2026-06-30`. Por cierre, no por año natural."""
        if self.inicio is None:
            return f"@{self.fin.isoformat()}"
        aa = f"{self.fin.year % 100:02d}"
        m = self.meses
        if m == 12:
            return f"FY{self.fin.year}"
        if m == 3:
            return f"{(self.fin.month - 1) // 3 + 1}T{aa}"
        return f"{m}M{aa}"

    @staticmethod
    def instante(fin: date) -> "Periodo":
        return Periodo(fin=fin)

    @staticmethod
    def anual(fin: date) -> "Periodo":
        return Periodo(fin=fin, inicio=date(fin.year - 1, fin.month, fin.day) + _un_dia())

    @staticmethod
    def de_meses(fin: date, meses: int) -> "Periodo":
        """El periodo de `meses` meses que acaba en `fin` (cierres a fin de mes)."""
        mes = fin.month - meses + 1
        anio = fin.year
        while mes <= 0:
            mes += 12
            anio -= 1
        return Periodo(fin=fin, inicio=date(anio, mes, 1))


def _un_dia():
    from datetime import timedelta
    return timedelta(days=1)


@dataclass(frozen=True)
class Origen:
    """De dónde salió la cifra, con lo necesario para volver a ella y recortarla."""
    documento: str                       # nombre del adjunto, «SEC companyfacts», «analista»
    formulario: str = ""                 # 10-K, 10-Q, DEF 14A, 8-K…
    presentado: Optional[date] = None    # fecha de presentación ante la SEC
    pagina: Optional[int] = None         # índice físico del PDF, desde 1
    rectangulo: Optional[Tuple[float, float, float, float]] = None  # x0, y0, x1, y1 en puntos, origen abajo-izquierda
    concepto: str = ""                   # us-gaap:Revenues
    referencia: str = ""                 # accession, URL o celda de hoja de cálculo

    def cita(self) -> str:
        partes = [self.documento]
        if self.formulario:
            partes.append(self.formulario)
        if self.presentado:
            partes.append(self.presentado.strftime("%d/%m/%Y"))
        if self.pagina:
            partes.append(f"pág. {self.pagina}")
        return " · ".join(partes)


@dataclass(frozen=True)
class Hecho:
    campo: str
    periodo: Periodo
    valor: Optional[float]
    estado: Estado
    capa: Capa
    unidad: str = "USD"
    origen: Optional[Origen] = None
    motivo: str = ""                     # obligatorio en N/A; en Hd, por qué se clasificó así
    certeza: Optional[Certeza] = None    # obligatoria en Hd y S
    formula: str = ""                    # obligatoria en D, tal como se imprime
    entradas: Tuple["Hecho", ...] = ()   # obligatorias en D
    contraste: Contraste = Contraste.SIN_CONTRASTAR
    nota: str = ""                       # lo que se imprime al pie: decisión del analista, reexpresión…

    def __post_init__(self) -> None:
        if self.estado is Estado.NA:
            if self.valor is not None:
                raise ValueError(f"{self.campo} {self.periodo.clave}: N/A con valor {self.valor!r}")
            if not self.motivo:
                raise ValueError(f"{self.campo} {self.periodo.clave}: N/A sin motivo")
        elif self.estado is Estado.CERO:
            if self.valor != 0:
                raise ValueError(f"{self.campo} {self.periodo.clave}: estado cero con valor {self.valor!r}")
        elif self.estado is Estado.VALOR:
            if self.valor is None or self.valor == 0:
                raise ValueError(f"{self.campo} {self.periodo.clave}: estado valor con {self.valor!r} (un cero es CERO, un vacío es NA)")
        if self.capa is Capa.DERIVADO and self.estado is not Estado.NA:
            if not self.formula or not self.entradas:
                raise ValueError(f"{self.campo} {self.periodo.clave}: derivado sin fórmula o sin entradas")
        if self.capa in (Capa.DOCUMENTO, Capa.SUPUESTO) and self.certeza is None:
            raise ValueError(f"{self.campo} {self.periodo.clave}: {self.capa.value} sin certeza")

    @property
    def hay_dato(self) -> bool:
        return self.estado is not Estado.NA

    def con(self, **cambios) -> "Hecho":
        return replace(self, **cambios)


@dataclass(frozen=True)
class Cita:
    """Un hecho textual: lo que un documento dice, literal, con su página.

    Sirve para lo que no es una cifra —el auditor, el año de fundación, un
    objetivo anunciado— y viaja con las mismas garantías: origen, capa y
    certeza. El texto es literal del documento; lo que el sistema añade va
    en `nota`, separado, para que nunca se confunda lo leído con lo inferido.
    """
    campo: str
    texto: str
    origen: Origen
    capa: Capa = Capa.SEC
    certeza: Certeza = Certeza.ALTA
    nota: str = ""
    valor: Optional[float] = None       # si el texto contiene la cifra, aquí va ya parseada
    fecha: Optional[date] = None        # a qué fecha se refiere, si el texto la da


def na(campo: str, periodo: Periodo, motivo: str, unidad: str = "USD",
       capa: Capa = Capa.SEC, contraste: Contraste = Contraste.HUECO) -> Hecho:
    return Hecho(campo=campo, periodo=periodo, valor=None, estado=Estado.NA, capa=capa,
                 unidad=unidad, motivo=motivo, contraste=contraste,
                 certeza=Certeza.ALTA if capa in (Capa.DOCUMENTO, Capa.SUPUESTO) else None)


def de_valor(campo: str, periodo: Periodo, valor: float, capa: Capa, origen: Optional[Origen],
             unidad: str = "USD", certeza: Optional[Certeza] = None, motivo: str = "",
             nota: str = "") -> Hecho:
    """Construye el hecho decidiendo él mismo si es un valor o un cero."""
    estado = Estado.CERO if valor == 0 else Estado.VALOR
    return Hecho(campo=campo, periodo=periodo, valor=float(valor), estado=estado, capa=capa,
                 unidad=unidad, origen=origen, certeza=certeza, motivo=motivo, nota=nota)


def derivar(campo: str, periodo: Periodo, formula: str, entradas: Mapping[str, Hecho],
            calculo: Callable[..., Optional[float]], unidad: str = "USD") -> Hecho:
    """Un derivado: si falta una entrada, el resultado es N/A y dice cuál falta.

    `calculo` recibe los valores por nombre; puede devolver `None` (p. ej. una
    división por cero) y entonces el hecho sale N/A con ese motivo.
    """
    faltan = [nombre for nombre, h in entradas.items() if not h.hay_dato]
    if faltan:
        motivo = "no se puede calcular: falta " + ", ".join(
            f"{entradas[n].campo} {entradas[n].periodo.clave} ({entradas[n].motivo})" for n in faltan)
        return Hecho(campo=campo, periodo=periodo, valor=None, estado=Estado.NA, capa=Capa.DERIVADO,
                     unidad=unidad, motivo=motivo, formula=formula, entradas=tuple(entradas.values()),
                     contraste=Contraste.HUECO)
    resultado = calculo(**{n: h.valor for n, h in entradas.items()})
    if resultado is None:
        return Hecho(campo=campo, periodo=periodo, valor=None, estado=Estado.NA, capa=Capa.DERIVADO,
                     unidad=unidad, motivo="la fórmula no está definida con estas entradas (división por cero)",
                     formula=formula, entradas=tuple(entradas.values()), contraste=Contraste.HUECO)
    estado = Estado.CERO if resultado == 0 else Estado.VALOR
    return Hecho(campo=campo, periodo=periodo, valor=float(resultado), estado=estado, capa=Capa.DERIVADO,
                 unidad=unidad, formula=formula, entradas=tuple(entradas.values()),
                 contraste=Contraste.DERIVADO)
