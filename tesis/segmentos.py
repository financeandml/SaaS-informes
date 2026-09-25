"""Ingresos por segmento, línea de producto y geografía (apartado 4), del XBRL inline del 10-K y del último 10-Q.

Tres ejercicios del 10-K y los últimos doce meses (UDM) = ejercicio + acumulado del año en curso − acumulado del año
anterior, los dos del último 10-Q. Cada periodo se cuadra: segmentos + partidas de conciliación = ingresos
consolidados; líneas de un segmento = el segmento; geografías = consolidado. Lo que no cuadra se dice con la diferencia.

Nada de nombres de un emisor: los ejes son los de la taxonomía US GAAP y los rótulos salen de `config/traducciones.yaml`
o del analista (`perfil.rotulos`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Dict, List, Mapping, Optional, Tuple

from . import ixbrl, rotulos
from .hechos import Capa, Hecho, Origen, Periodo, de_valor, derivar, na

__all__ = ["Linea", "Segmentos", "construir", "desde_documentos"]

INGRESOS = ("RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "RevenueFromContractWithCustomerIncludingAssessedTax")
SEGMENTO, PRODUCTO, GEOGRAFIA, CONSOLIDACION = ("StatementBusinessSegmentsAxis", "ProductOrServiceAxis",
                                                 "StatementGeographicalAxis", "ConsolidationItemsAxis")
_OPERATIVOS = "OperatingSegmentsMember"
TOLERANCIA = 0.005     # 0,5 % del consolidado: por debajo, redondeos de la propia tabla


@dataclass
class Linea:
    tipo: str                 # segmento · producto · conciliacion · geografia
    miembro: str              # «qcom:QCTMember» (con el segmento delante si es una línea dentro de él: «seg|prod»)
    rotulo: str
    traducido: bool
    padre: Optional[str] = None
    valores: Dict[Periodo, Hecho] = field(default_factory=dict)


@dataclass
class Segmentos:
    lineas: List[Linea] = field(default_factory=list)
    periodos: List[Periodo] = field(default_factory=list)       # ejercicios y, al final, UDM si hay 10-Q posterior
    udm: Optional[Periodo] = None
    etiqueta_udm: str = ""
    consolidado: Dict[Periodo, Hecho] = field(default_factory=dict)
    cuadres: List[str] = field(default_factory=list)
    origenes: Dict[str, Origen] = field(default_factory=dict)
    faltan: Dict[str, str] = field(default_factory=dict)

    def de_tipo(self, tipo: str) -> List[Linea]:
        return [l for l in self.lineas if l.tipo == tipo]

    def geografia(self) -> Tuple[List[Linea], Optional[str]]:
        """El desglose geográfico más completo que publica el 10-K y de qué total cuelga (None = consolidado, o una
        línea de producto): un emisor puede dar las regiones de su producto y aparte solo su país."""
        grupos: Dict[Optional[str], List[Linea]] = {}
        for l in self.de_tipo("geografia"):
            grupos.setdefault(l.padre, []).append(l)
        if not grupos:
            return [], None
        padre = max(grupos, key=lambda k: (len(grupos[k]), k is None))
        return grupos[padre], padre

    @property
    def sin_traducir(self) -> List[str]:
        return [l.miembro for l in self.lineas if not l.traducido]


_NEUTROS_GEO = {"ConcentrationRiskByBenchmarkAxis", "ConcentrationRiskByTypeAxis"}   # ingresos por país etiquetados
                                                                                     # como concentración de riesgo


def _clasifica(ctx: ixbrl.Contexto) -> Optional[Tuple[str, str, Optional[str]]]:
    """(tipo, clave, padre) de un contexto de ingresos, o None si es un cruce que no se imprime."""
    ejes = {e.split(":")[-1]: m for e, m in ctx.dims}
    consolidacion = ejes.pop(CONSOLIDACION, None)
    if consolidacion is not None and consolidacion.split(":")[-1] == _OPERATIVOS:
        consolidacion = None
    if consolidacion is not None:
        # una partida de conciliación se rotula por el miembro que la concreta (resto de segmentos, un acuerdo…)
        if len(ejes) <= 1:
            otro = next(iter(ejes.values()), None)
            return "conciliacion", f"{consolidacion}|{otro}" if otro else consolidacion, None
        return None
    if GEOGRAFIA in ejes and set(ejes) - {GEOGRAFIA} <= _NEUTROS_GEO:
        return "geografia", ejes[GEOGRAFIA], None
    if set(ejes) == {GEOGRAFIA, PRODUCTO}:          # regiones de una línea de producto (p. ej. la única que hay)
        return "geografia", f"{ejes[PRODUCTO]}|{ejes[GEOGRAFIA]}", ejes[PRODUCTO]
    if set(ejes) == {SEGMENTO}:
        return "segmento", ejes[SEGMENTO], None
    if set(ejes) == {SEGMENTO, PRODUCTO}:
        return "producto", f"{ejes[SEGMENTO]}|{ejes[PRODUCTO]}", ejes[SEGMENTO]
    if set(ejes) == {PRODUCTO}:
        return "producto", ejes[PRODUCTO], None
    if set(ejes) == {GEOGRAFIA}:
        return "geografia", ejes[GEOGRAFIA], None
    return None


def _anuales(doc: ixbrl.Documento) -> Dict[Tuple[str, str, Optional[str]], Dict[Periodo, ixbrl.HechoIX]]:
    """Por (tipo, clave, padre) y periodo, el hecho de ingresos; un concepto por clave (el primero de `INGRESOS` que la trae)."""
    salida: Dict[Tuple[str, str, Optional[str]], Dict[Periodo, ixbrl.HechoIX]] = {}
    for concepto in INGRESOS:
        for h in doc.de(concepto):
            clase = _clasifica(h.contexto)
            if clase is None or h.contexto.inicio is None:
                continue
            p = Periodo(fin=h.contexto.fin, inicio=h.contexto.inicio)
            por_periodo = salida.setdefault(clase, {})
            por_periodo.setdefault(p, h)
    return salida


def _consolidado(doc: ixbrl.Documento) -> Dict[Periodo, ixbrl.HechoIX]:
    salida: Dict[Periodo, ixbrl.HechoIX] = {}
    for concepto in INGRESOS:
        for h in doc.de(concepto):
            if h.contexto.dims or h.contexto.inicio is None:
                continue
            salida.setdefault(Periodo(fin=h.contexto.fin, inicio=h.contexto.inicio), h)
    return salida


def _origen(doc: ixbrl.Documento, formulario: str, presentado: Optional[date], concepto: str) -> Origen:
    return Origen(documento=formulario, formulario=formulario, presentado=presentado,
                  concepto=concepto, referencia=doc.url)


def _mismo_largo(a: Periodo, b: Periodo) -> bool:
    return abs(((a.fin - a.inicio).days) - ((b.fin - b.inicio).days)) <= 8


def desde_documentos(k10: ixbrl.Documento, presentado_k: Optional[date], q10: Optional[ixbrl.Documento] = None,
                     presentado_q: Optional[date] = None, propios: Optional[Mapping[str, str]] = None,
                     etiqueta=None, ejercicios: int = 3, etiquetas_en: Optional[Mapping[str, str]] = None) -> Segmentos:
    """`etiqueta(p)` rotula un periodo en el calendario fiscal de la compañía (la del informe)."""
    s = Segmentos()
    anuales_k = _anuales(k10)
    total_k = _consolidado(k10)
    fy = sorted({p for p in total_k if p.meses == 12})[-ejercicios:]
    if not fy:
        s.faltan["segmentos"] = "el 10-K no publica ingresos anuales por segmento"
        return s
    s.periodos = list(fy)
    s.origenes["10-K"] = _origen(k10, "10-K", presentado_k, "ingresos por eje")
    ultimo_fy = fy[-1]

    # UDM con el último 10-Q, si es posterior al 10-K
    acumulado: Optional[Periodo] = None
    anterior: Optional[Periodo] = None
    anuales_q: Dict = {}
    total_q: Dict = {}
    if q10 is not None:
        anuales_q = _anuales(q10)
        total_q = _consolidado(q10)
        fines = [p for p in total_q if p.fin > ultimo_fy.fin and p.meses < 12]
        if fines:
            fin = max(p.fin for p in fines)
            acumulado = max((p for p in fines if p.fin == fin), key=lambda p: p.fin - p.inicio)
            anterior = next((p for p in total_q if p.fin < acumulado.inicio and _mismo_largo(p, acumulado)
                             and abs((acumulado.fin - p.fin).days - 364) <= 8), None)
    if acumulado is not None and anterior is not None and acumulado.inicio - ultimo_fy.fin <= timedelta(days=8):
        s.udm = Periodo(fin=acumulado.fin, inicio=acumulado.fin - timedelta(days=364))
        s.periodos.append(s.udm)
        s.origenes["10-Q"] = _origen(q10, "10-Q", presentado_q, "ingresos por eje")
        s.etiqueta_udm = f"UDM a {etiqueta(Periodo(fin=acumulado.fin, inicio=acumulado.fin - timedelta(days=90)))}" if etiqueta else "UDM"

    def _hecho(campo: str, h: Optional[ixbrl.HechoIX], p: Periodo, formulario: str, presentado, doc) -> Hecho:
        if h is None:
            return na(campo, p, f"el {formulario} no desglosa este eje en {etiqueta(p) if etiqueta else p.clave}")
        return de_valor(campo, p, h.valor, Capa.SEC, _origen(doc, formulario, presentado, h.concepto))

    def _udm(campo: str, fy_h: Hecho, cur: Optional[ixbrl.HechoIX], ant: Optional[ixbrl.HechoIX]) -> Hecho:
        if cur is None or ant is None:
            return na(campo, s.udm, "el último 10-Q no desglosa este eje (solo lo publica el 10-K)")
        acum = de_valor(campo, acumulado, cur.valor, Capa.SEC, _origen(q10, "10-Q", presentado_q, cur.concepto))
        prev = de_valor(campo, anterior, ant.valor, Capa.SEC, _origen(q10, "10-Q", presentado_q, ant.concepto))
        return derivar(campo, s.udm, f"{etiqueta(ultimo_fy) if etiqueta else ultimo_fy.clave} + acumulado del año − acumulado del año anterior",
                       {"fy": fy_h, "acumulado": acum, "anterior": prev}, lambda fy, acumulado, anterior: fy + acumulado - anterior)

    # consolidado
    for p in fy:
        s.consolidado[p] = _hecho("ingresos", total_k.get(p), p, "10-K", presentado_k, k10)
    if s.udm is not None:
        s.consolidado[s.udm] = _udm("ingresos", s.consolidado[ultimo_fy], total_q.get(acumulado), total_q.get(anterior))

    # líneas: solo las que el último 10-K publica (una línea recién desaparecida no se imprime como hueco)
    for (tipo, clave, padre), por_periodo in anuales_k.items():
        if ultimo_fy not in por_periodo:
            continue
        miembro = clave.split("|")[-1]
        rotulo, traducido = rotulos.miembro(miembro, propios, (etiquetas_en or {}).get(miembro))
        linea = Linea(tipo=tipo, miembro=clave, rotulo=rotulo, traducido=traducido, padre=padre)
        campo = f"ingresos[{clave}]"
        for p in fy:
            linea.valores[p] = _hecho(campo, por_periodo.get(p), p, "10-K", presentado_k, k10)
        if s.udm is not None:
            en_q = anuales_q.get((tipo, clave, padre))
            if en_q is None:
                par = _renombrado((tipo, clave, padre), anuales_q)
                if par is not None:
                    en_q = anuales_q[par]
                    # sin los nombres de los miembros XBRL: son identificadores de la fuente, que nunca se imprimen
                    s.cuadres.append(f"◐ {rotulo}: el 10-Q y el 10-K la etiquetan con nombres distintos; se tratan como la misma línea")
            en_q = en_q or {}
            linea.valores[s.udm] = _udm(campo, linea.valores[ultimo_fy], en_q.get(acumulado), en_q.get(anterior))
        s.lineas.append(linea)
    orden = {"segmento": 0, "producto": 1, "conciliacion": 2, "geografia": 3}
    s.lineas.sort(key=lambda l: (orden[l.tipo], -(l.valores[ultimo_fy].valor or 0)))
    _cuadrar(s, etiqueta)
    if not s.de_tipo("segmento") and not s.de_tipo("geografia") and not s.de_tipo("producto"):
        s.faltan["segmentos"] = "el 10-K no etiqueta ingresos con ejes de segmento, producto ni geografía"
    return s


def _local(miembro: str) -> str:
    return miembro.split(":")[-1].lower().removesuffix("member")


def _renombrado(clave: Tuple[str, str, Optional[str]], otros: Mapping) -> Optional[Tuple[str, str, Optional[str]]]:
    """La misma línea con otro nombre de miembro entre depósitos («MobileHandsetsMember» en el 10-K, «HandsetsMember» en
    el 10-Q): mismo tipo y mismo padre, y un nombre termina en el otro. Solo si el candidato es único."""
    tipo, texto, padre = clave
    a = _local(texto.split("|")[-1])
    candidatos = [k for k in otros if k[0] == tipo and k[2] == padre and k[1] != texto
                  and (a.endswith(_local(k[1].split("|")[-1])) or _local(k[1].split("|")[-1]).endswith(a))]
    return candidatos[0] if len(candidatos) == 1 else None


def _cuadrar(s: Segmentos, etiqueta) -> None:
    from .formato import numero

    def _suma(lineas: List[Linea], p: Periodo) -> Optional[float]:
        valores = [l.valores[p].valor for l in lineas if l.valores.get(p) is not None and l.valores[p].hay_dato]
        return sum(valores) if len(valores) == len(lineas) and lineas else None

    for p in s.periodos:
        total = s.consolidado.get(p)
        if total is None or not total.hay_dato:
            continue
        rotulo = s.etiqueta_udm if p == s.udm else (etiqueta(p) if etiqueta else p.clave)
        grupos = [("segmentos + conciliación", s.de_tipo("segmento") + s.de_tipo("conciliacion"), total, "del consolidado")] \
            if s.de_tipo("segmento") else []
        geo, padre = s.geografia()
        if padre is None:
            grupos.append(("geografías", geo, total, "del consolidado"))
        else:
            linea_padre = next((l for l in s.lineas if l.miembro == padre or l.miembro.endswith("|" + padre)), None)
            if linea_padre is not None and linea_padre.valores.get(p) is not None:
                grupos.append(("geografías", geo, linea_padre.valores[p], f"de {linea_padre.rotulo}"))
        productos_sueltos = [l for l in s.de_tipo("producto") if l.padre is None]
        if productos_sueltos and not s.de_tipo("segmento"):
            grupos.append(("líneas de producto", productos_sueltos, total, "del consolidado"))
        for nombre, lineas, referencia, de_que in grupos:
            suma = _suma(lineas, p)
            if suma is None or referencia is None or not referencia.hay_dato:
                continue
            dif = suma - referencia.valor
            if abs(dif) > TOLERANCIA * abs(referencia.valor):
                s.cuadres.append(f"≠ {rotulo}: {nombre} suman {numero(suma / 1e6)} mln USD frente a {numero(referencia.valor / 1e6)} "
                                 f"{de_que} (diferencia {numero(dif / 1e6)} mln USD)")
            else:
                s.cuadres.append(f"✓ {rotulo}: {nombre} = total {de_que} ({numero(referencia.valor / 1e6)} mln USD)")
        for seg in s.de_tipo("segmento"):
            hijas = [l for l in s.de_tipo("producto") if l.padre == seg.miembro]
            suma, h = _suma(hijas, p), seg.valores.get(p)
            if suma is None or h is None or not h.hay_dato:
                continue
            dif = suma - h.valor
            if abs(dif) > TOLERANCIA * abs(h.valor):
                s.cuadres.append(f"≠ {rotulo}: las líneas de {seg.rotulo} suman {numero(suma / 1e6)} mln USD frente a "
                                 f"{numero(h.valor / 1e6)} del segmento (diferencia {numero(dif / 1e6)})")


def construir(emisor, propios: Optional[Mapping[str, str]] = None, etiqueta=None) -> Segmentos:
    """Descarga (o lee de la caché) el último 10-K y el último 10-Q de EDGAR y construye los cuadros."""
    from . import sec
    k = emisor.ultimo("10-K")
    if k is None:
        s = Segmentos()
        s.faltan["segmentos"] = "sin 10-K en EDGAR"
        return s
    k10 = ixbrl.leer(sec.descargar_texto(k.url)[0], k.url)
    q = emisor.ultimo("10-Q")
    q10 = None
    if q is not None and q.presentado > k.presentado:
        try:
            q10 = ixbrl.leer(sec.descargar_texto(q.url)[0], q.url)
        except (RuntimeError, sec.SinContacto):
            q10 = None
    return desde_documentos(k10, k.presentado, q10, q.presentado if q10 is not None else None, propios, etiqueta,
                            etiquetas_en=_etiquetas_del_deposito(k))


def _etiquetas_del_deposito(d) -> Dict[str, str]:
    """Los rótulos que el propio depósito da a sus miembros (linkbase `*_lab.xml` del índice). Sin él, vacío."""
    from . import sec
    base = d.url.rsplit("/", 1)[0]
    try:
        indice, _ = sec._descargar(base + "/index.json")
        nombre = next((it["name"] for it in indice.get("directory", {}).get("item", []) if it["name"].endswith("_lab.xml")), None)
        if nombre is None:
            return {}
        return ixbrl.etiquetas(sec.descargar_texto(f"{base}/{nombre}")[0])
    except (RuntimeError, sec.SinContacto, KeyError):
        return {}
