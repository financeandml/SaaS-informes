"""El contraste: para cada campo × periodo, la SEC frente a los adjuntos, sin elegir por su cuenta.

Es lo que el producto promete (PLANTILLA_TESIS.md §5). Por cada celda que el
informe va a imprimir se ponen al lado el hecho XBRL de la SEC y las casillas
que los adjuntos traen para ese rótulo y ese periodo, y se dice en qué queda:

    ✓  confirmado       SEC y documento coinciden (±½ unidad de la escala del documento)
    ≠  discrepante      ambos existen y no coinciden → bloquea la emisión hasta que el analista decida
    ◐  solo SEC         ningún adjunto lo trae → exige reconocimiento del analista
    ◑  solo documento   la SEC no lo publica → hecho de documento, con certeza
    —  hueco            ni SEC ni adjuntos → se pide al analista
    ∑  derivado         calculado de hechos ya contrastados, con fórmula impresa

Las decisiones que se fijan aquí, y por qué, son las que la prueba de hoy y la
prueba paralela dejaron a la vista:

- **La tolerancia es la del documento que se compara**, no una fija. La carta
  imprime en millones y el 10-Q en miles: 2.267 M y 2.267.369 miles son el mismo
  dato, y con una tolerancia única salían discrepantes.
- **El rótulo se casa con su contexto.** «Revenue» bajo la cabecera «UCAN» es
  el ingreso de una región, no el total; sin mirar la línea de bloque que
  precede a la fila, cinco trimestres de ingresos salían discrepantes.
- **Una discrepancia con razón 10 (o 1/10) entre acciones o BPA lleva la pista
  del split** en la nota. Sigue siendo el analista quien decide; el sistema solo
  le ahorra averiguar por qué.
- **Lo que el documento no trae no se rellena con la SEC, ni al revés.** Un ◐
  o un ◑ se imprimen con su glifo. Lo único que el sistema construye solo es el
  cuarto trimestre (FY − 9M) y los agregados, y salen marcados ∑.
- **Un cero declarado por texto es un cero.** «We have never declared or paid
  any cash dividends» en el 10-K convierte el N/A de dividendos en un cero con
  cita; sin esa frase, sigue siendo N/A.

Las decisiones del analista sobre las discrepancias se leen de un fichero JSON
(`decisiones.json`) y se imprimen como nota al pie de la cifra. El sistema no
las toma nunca por él.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from . import sec as sec_mod
from .campos import CAMPOS, Campo, campo as campo_de

_POR_CLAVE = {c.clave: c for c in CAMPOS}
from .expediente import Adjunto, Expediente, Tipo
from .extractor import Candidato, PaginaLeida, extraer_pdf, extraer_xlsx
from .formato import numero
from .hechos import Capa, Certeza, Contraste, Estado, Hecho, Origen, Periodo, de_valor, derivar, na

__all__ = ["Decision", "Resultado", "Tablero", "contrastar", "periodos_del_informe"]

# Prioridad del documento como evidencia: el formulario depositado antes que la
# copia de la web, y esta antes que la carta, que redondea.
PRIORIDAD = {Tipo.K10: 0, Tipo.Q10: 1, Tipo.XLSX: 2, Tipo.FINWEB: 3, Tipo.TABLAS: 4, Tipo.CARTA: 5, Tipo.NOTA: 6, Tipo.CALL: 7,
             Tipo.DEF14A: 8, Tipo.PRESENTACION: 9}

# Frases que convierten un N/A en un cero con cita. Solo se buscan en el 10-K.
DECLARACIONES_CERO = {
    "dividendos": re.compile(r"(?i)(never|not)\s+(declared|paid)\b[^.]{0,80}\bdividends?\b"),
}


@dataclass
class Decision:
    campo: str
    periodo: str
    valor: float
    motivo: str
    analista: str
    fecha: str


@dataclass
class Resultado:
    campo: Campo
    periodo: Periodo
    hecho: Hecho
    sec: Optional[Hecho]
    candidatos: List[Candidato]
    coincidentes: List[Candidato]
    evidencia: Optional[Candidato]      # el candidato que se recorta como prueba
    nota: str = ""

    @property
    def glifo(self) -> str:
        return self.hecho.contraste.value


@dataclass
class Tablero:
    resultados: List[Resultado]
    paginas: Dict[str, List[PaginaLeida]]     # clave de adjunto → páginas leídas
    resumen: Dict[str, int]
    avisos: List[str] = field(default_factory=list)
    # campos que no son una línea de las cuentas de esta compañía (clave → por qué se dice)
    no_aplican: Dict[str, str] = field(default_factory=dict)
    # desdoblamientos que registra la SEC (fecha, razón): las notas de los cuadros salen de aquí, no escritas a mano
    splits: List[Tuple[date, float]] = field(default_factory=list)
    # cuánto se aparta la numeración del ejercicio del año en que cierra (sec.desfase_fiscal)
    desfase_fiscal: int = 0

    def de(self, campo: str, periodo: Periodo) -> Optional[Resultado]:
        for r in self.resultados:
            if r.campo.clave == campo and r.periodo == periodo:
                return r
        return None

    @property
    def bloquea(self) -> List[Resultado]:
        return [r for r in self.resultados if r.hecho.contraste is Contraste.DISCREPANTE]

    def hechos(self) -> Dict[Tuple[str, Periodo], Hecho]:
        return {(r.campo.clave, r.periodo): r.hecho for r in self.resultados}


# ---------------------------------------------------------------------------
# Qué periodos pide el informe
# ---------------------------------------------------------------------------

def _no_los_tiene_la_compania(resultados: List[Resultado], facts: dict) -> Dict[str, str]:
    """Los campos que no son una línea de las cuentas de esta compañía, separados de los que sí y faltan.

    No es lo mismo «falta un dato» que «esta compañía no tiene esa partida». Oracle no tiene activos de contenido ni
    autocartera —recompra y amortiza las acciones— ni imprime un subtotal de coste de los ingresos; Netflix sí. Un
    campo se declara ajeno cuando **en ningún periodo pedido** hay hecho de la SEC ni candidato en los documentos y
    la compañía no etiqueta ninguno de sus conceptos en ningún depósito: entonces el hueco no es una carencia del
    expediente, y decir lo contrario es contar 131 fallos donde hay 47 partidas que no existen.
    """
    por_campo: Dict[str, List[Resultado]] = {}
    for r in resultados:
        por_campo.setdefault(r.campo.clave, []).append(r)
    salida: Dict[str, str] = {}
    for clave, rs in por_campo.items():
        if any(r.hecho.contraste is not Contraste.HUECO for r in rs) or any(r.candidatos for r in rs):
            continue
        c = rs[0].campo
        conceptos = list(c.conceptos) + [x for grupo in c.conceptos_suma for x in grupo]
        desde = min(r.periodo.inicio or r.periodo.fin for r in rs)
        ultimo = None
        for concepto in conceptos:
            for f in sec_mod._filas_concepto(facts, concepto)[1]:
                if f.get("form") in sec_mod.FORMULARIOS_ESTADOS and (ultimo is None or f["end"] > ultimo):
                    ultimo = f["end"]
        # margen de dos años antes de la ventana: que la compañía lo declarase hasta hace nada es señal de que la
        # partida existe y lo que falta es el dato. Declararla ajena entonces taparía un hueco de verdad.
        limite = date(desde.year - 2, desde.month, 28 if (desde.month, desde.day) == (2, 29) else desde.day)
        if ultimo is not None and ultimo >= limite.isoformat():
            continue
        # sin los nombres de los conceptos: son identificadores de la fuente, que nunca se imprimen (CLAUDE.md › Idioma)
        salida[clave] = (f"la compañía dejó de declarar esta partida en {ultimo[:4]}" if ultimo
                         else "la compañía no declara esta partida en ningún 10-K ni 10-Q") + \
                        ", y tampoco la imprime en los documentos del expediente: no es una línea de sus cuentas, " \
                        "no un dato que falte."
    return salida


def _mismo_periodo(a: Periodo, b: Periodo) -> bool:
    """Dos periodos son el mismo cuando cierran el mismo día y duran lo mismo, aunque no empiecen el mismo día."""
    return a.fin == b.fin and a.es_instante == b.es_instante and a.meses == b.meses


def periodos_del_informe(exp: Expediente, ejercicios: int = 5, trimestres: int = 4,
                         facts: Optional[dict] = None, hasta: Optional[date] = None) -> Dict[str, List[Periodo]]:
    """5 ejercicios cerrados + últimos 4 trimestres, con sus instantes de balance y
    los acumulados que hacen falta para derivar el 4T. Todo sale de las fechas que
    declaran los adjuntos, no de la fecha de hoy.

    Con `facts`, los cierres los pone el calendario real del emisor (`sec.calendario`) en vez de la aritmética de
    «el mismo día del año pasado»: quien cierra por semanas no cierra dos años seguidos el mismo día, y un periodo
    calculado a mano no casa con ningún hecho de la SEC, que van fechados con el cierre real.
    """
    from datetime import timedelta
    k = exp.de_tipo(Tipo.K10)
    q = exp.de_tipo(Tipo.Q10) + exp.de_tipo(Tipo.FINWEB) + exp.de_tipo(Tipo.XLSX) + exp.de_tipo(Tipo.TABLAS)
    if k:
        fin_fy = max(a.periodo_fin for a in k if a.periodo_fin)
        ultimo_q = max((a.periodo_fin for a in q if a.periodo_fin), default=fin_fy)
    elif facts:
        # sin adjuntos, el calendario de la SEC hasta la fecha pedida: sirve para las pruebas y para ver los datos antes
        # de que el analista suba los PDF
        corte = hasta or date.max
        cierres = [p.fin for p in sec_mod.calendario(facts, 12) if p.fin <= corte]
        if not cierres:
            raise ValueError("Sin ejercicios cerrados en la SEC antes de la fecha pedida.")
        fin_fy = cierres[-1]
        ultimo_q = max([p.fin for p in sec_mod.calendario(facts, 3) if p.fin <= corte] + [fin_fy])
    else:
        raise ValueError("Sin cuentas anuales (10-K) en el expediente no hay ejercicio base.")
    anuales, trims = [], []
    if facts:
        anuales = [p for p in sec_mod.calendario(facts, 12) if p.fin <= fin_fy][-ejercicios:]
        nueves = sec_mod.calendario(facts, 9)
        por_fin = {p.fin: p for p in sec_mod.calendario(facts, 3)}
        for fy in anuales:
            # el 4T no lo publica nadie: va del día siguiente al cierre del acumulado de nueve meses al del ejercicio
            nm = next((n for n in nueves if n.inicio == fy.inicio), None)
            if nm is not None and fy.fin not in por_fin:
                por_fin[fy.fin] = Periodo(fin=fy.fin, inicio=nm.fin + timedelta(days=1))
        trims = sorted(p for p in por_fin.values() if p.fin <= ultimo_q)[-trimestres:]
    if len(anuales) < ejercicios or len(trims) < trimestres:
        # sin calendario declarado (o incompleto) se cae a la aritmética: sirve para el emisor de cierres fijos
        anuales = [Periodo.anual(date(fin_fy.year - i, fin_fy.month, fin_fy.day)) for i in range(ejercicios - 1, -1, -1)]
        trims, fin = [], ultimo_q
        for _ in range(trimestres):
            trims.append(Periodo.de_meses(fin, 3))
            fin = Periodo.de_meses(fin, 3).inicio - timedelta(days=1)
        trims.reverse()
    instantes = [Periodo.instante(p.fin) for p in anuales] + [Periodo.instante(p.fin) for p in trims if p.fin != fin_fy]
    # los cierres anteriores al primer ejercicio y al primer trimestre: sin ellos no hay saldo medio (ROE, ROA, ROIC) del primer periodo
    instantes.append(Periodo.instante(anuales[0].inicio - timedelta(days=1)))
    if trims:
        instantes.append(Periodo.instante(trims[0].inicio - timedelta(days=1)))
    instantes = sorted(set(instantes))
    return {"anuales": anuales, "trimestres": trims, "instantes": instantes}


# ---------------------------------------------------------------------------
# Candidatos por campo
# ---------------------------------------------------------------------------

def _leer_todo(exp: Expediente) -> Dict[str, List[PaginaLeida]]:
    paginas: Dict[str, List[PaginaLeida]] = {}
    for a in exp.adjuntos:
        if a.tipo is Tipo.XLSX:
            paginas[a.clave] = extraer_xlsx(a)
        elif a.tipo in (Tipo.K10, Tipo.Q10, Tipo.FINWEB, Tipo.CARTA, Tipo.TABLAS, Tipo.NOTA):
            paginas[a.clave] = extraer_pdf(a)
    return paginas


def _limpiar_rotulo(r: str) -> str:
    return re.sub(r"[\*†‡:]+$", "", r).strip()


def _indice_fila(c: Campo, cand: Candidato) -> Optional[int]:
    """Cuál de los patrones del campo casa con el rótulo; el primero es el más específico."""
    rotulo = _limpiar_rotulo(cand.rotulo)
    return next((i for i, p in enumerate(c.filas) if re.search(p, rotulo, re.I)), None)


def _casa(c: Campo, cand: Candidato) -> bool:
    rotulo = _limpiar_rotulo(cand.rotulo)
    if _indice_fila(c, cand) is None:
        return False
    contexto = _limpiar_rotulo(cand.contexto)
    if c.contexto and not re.search(c.contexto, contexto):
        return False
    if c.contexto_excluido and re.search(c.contexto_excluido, contexto):
        return False
    if c.unidad == "USD/acción" and not cand.por_accion:
        return False
    if c.unidad != "USD/acción" and cand.por_accion:
        return False
    return True


_NO_GAAP = re.compile(r"non[\u2011\u2013\u2014 -]?gaap", re.I)
# una tabla que se anuncia como desglose de otra partida (la retribución en acciones repartida por líneas de gasto,
# la información geográfica) tiene las mismas filas que el estado de resultados y cifras que no son las suyas
_DESGLOSE = re.compile(r"included in the following|geographic information|reconciliation of", re.I)


def es_conciliacion(p: PaginaLeida) -> bool:
    """Una página de conciliación GAAP → non-GAAP (la publican casi todos los emisores con su nota de resultados):
    sus columnas son ajustes —retribución en acciones, amortización de intangibles, reestructuración—, no las cuentas.
    Leerla como si fuera el estado de resultados da cifras verosímiles y equivocadas, que es lo que prohíbe la regla 9."""
    cabecera = " ".join([p.titulo] + [l.texto for l in p.lineas[:12]])
    return bool(_NO_GAAP.search(cabecera) or _DESGLOSE.search(cabecera))


def _candidatos_por_campo(exp: Expediente, paginas: Dict[str, List[PaginaLeida]]) -> Dict[str, List[Tuple[Adjunto, Candidato]]]:
    salida: Dict[str, List[Tuple[Adjunto, Candidato]]] = {c.clave: [] for c in CAMPOS}
    por_clave = {a.clave: a for a in exp.adjuntos}
    for clave, pags in paginas.items():
        a = por_clave[clave]
        for p in pags:
            if es_conciliacion(p):
                continue
            for f in p.filas:
                for cand in f.celdas.values():
                    if cand.periodo is None or cand.porcentaje:
                        continue
                    for c in CAMPOS:
                        if _casa(c, cand):
                            salida[c.clave].append((a, cand))
    # Dentro de una misma página, si un campo tiene una fila más específica que otra —«Total Oracle Corporation
    # stockholders' equity» frente a «Total stockholders' equity», que incluye los minoritarios—, la específica es la
    # que expresa el concepto de la SEC: la genérica se descarta en vez de discrepar contra sí misma (regla 9).
    for clave, pares in salida.items():
        c = _POR_CLAVE[clave]
        if len(c.filas) < 2:
            continue
        mejor = {}
        for a, cand in pares:
            k = (a.clave, cand.pagina)
            i = _indice_fila(c, cand)
            if i is not None and (k not in mejor or i < mejor[k]):
                mejor[k] = i
        salida[clave] = [(a, cand) for a, cand in pares if _indice_fila(c, cand) == mejor.get((a.clave, cand.pagina))]
    return salida


# ---------------------------------------------------------------------------
# El contraste
# ---------------------------------------------------------------------------

def _tolerancia(cand: Candidato, c: Campo) -> float:
    if c.unidad == "USD/acción":
        return 0.005
    if c.unidad == "acciones":
        # Un recuento de acciones presentado en miles antes de un split 10:1 y
        # multiplicado por diez lleva un redondeo de ±5.000: se admite un 0,001 %
        # (42.000 sobre 4.240 millones), que no confunde ninguna otra cifra.
        return max(cand.escala / 2, abs(cand.valor) * 1e-5) + 1e-6
    return cand.escala / 2 + 1e-6


def _coincide(valor_sec: float, cand: Candidato, c: Campo) -> bool:
    return abs(abs(valor_sec) - abs(cand.valor)) <= _tolerancia(cand, c)


def _pista(valor_sec: float, cand: Candidato, c: Campo) -> str:
    if c.unidad in ("USD/acción", "acciones") and cand.valor and valor_sec:
        r = abs(valor_sec) / abs(cand.valor)
        for ratio in (10, 0.1, 2, 0.5, 3, 1 / 3, 4, 0.25):
            if abs(r - ratio) < 0.02 * ratio:
                return f"razón {ratio:g} entre SEC y documento: posible ajuste por split de acciones (el formulario original no está reexpresado)"
    return ""


def _ordenar_evidencia(pares: Sequence[Tuple[Adjunto, Candidato]]) -> List[Tuple[Adjunto, Candidato]]:
    return sorted(pares, key=lambda ac: (PRIORIDAD.get(ac[0].tipo, 9), ac[1].pagina))


def _normalizar(valor: float, c: Campo) -> float:
    """Los costes y salidas se guardan en positivo, como la SEC; el signo lo pone el informe al imprimir."""
    return abs(valor) if c.signo_informe < 0 else valor


def _origen_de(a: Adjunto, cand: Candidato) -> Origen:
    return Origen(documento=a.nombre, formulario=a.tipo.value, presentado=a.fecha, pagina=cand.pagina,
                  rectangulo=cand.rect_fila, referencia=cand.referencia)


def _cargar_decisiones(ruta: Optional[Path]) -> Dict[Tuple[str, str], Decision]:
    if not ruta or not Path(ruta).exists():
        return {}
    datos = json.loads(Path(ruta).read_text(encoding="utf-8"))
    salida = {}
    for d in datos:
        dec = Decision(**d)
        salida[(dec.campo, dec.periodo)] = dec
    return salida


def _contrastar_celda(c: Campo, p: Periodo, hecho_sec: Optional[Hecho],
                      pares: Sequence[Tuple[Adjunto, Candidato]],
                      decision: Optional[Decision]) -> Resultado:
    cands = [cand for _, cand in pares]
    sec_ok = hecho_sec is not None and hecho_sec.hay_dato
    if sec_ok:
        coinciden = [(a, cand) for a, cand in pares if _coincide(hecho_sec.valor, cand, c)]
        if coinciden:
            a, ev = _ordenar_evidencia(coinciden)[0]
            hecho = hecho_sec.con(contraste=Contraste.CONFIRMADO,
                                  nota=(hecho_sec.nota + " · " if hecho_sec.nota else "") + f"contrastado con {a.nombre} pág. {ev.pagina}")
            return Resultado(c, p, hecho, hecho_sec, cands, [cand for _, cand in coinciden], ev)
        if pares:
            a, ev = _ordenar_evidencia(pares)[0]
            lecturas = "; ".join(f"{aa.nombre} pág. {cc.pagina} = {numero(cc.valor, 2)}" for aa, cc in _ordenar_evidencia(pares)[:4])
            pista = _pista(hecho_sec.valor, ev, c)
            if decision is not None:
                hecho = de_valor(c.clave, p, _normalizar(decision.valor, c), Capa.SUPUESTO if decision.valor not in (hecho_sec.valor, ev.valor) else Capa.SEC,
                                 hecho_sec.origen if decision.valor == hecho_sec.valor else _origen_de(a, ev), unidad=c.unidad,
                                 certeza=Certeza.ALTA,
                                 nota=f"discrepancia SEC {numero(hecho_sec.valor, 2)} / documento {numero(ev.valor, 2)} resuelta por {decision.analista} el {decision.fecha}: {decision.motivo}")
                hecho = hecho.con(contraste=Contraste.CONFIRMADO)
                return Resultado(c, p, hecho, hecho_sec, cands, [], ev, nota=hecho.nota)
            hecho = hecho_sec.con(contraste=Contraste.DISCREPANTE,
                                  nota=f"SEC {numero(hecho_sec.valor, 2)} frente a {lecturas}" + (f" · {pista}" if pista else ""))
            return Resultado(c, p, hecho, hecho_sec, cands, [], ev, nota=hecho.nota)
        hecho = hecho_sec.con(contraste=Contraste.SOLO_SEC, nota=(hecho_sec.nota + " · " if hecho_sec.nota else "") + "sin contraste documental")
        return Resultado(c, p, hecho, hecho_sec, [], [], None)
    # la SEC no lo tiene
    if pares:
        ordenados = _ordenar_evidencia(pares)
        a, ev = ordenados[0]
        # ¿los adjuntos coinciden entre sí? (cada uno con su tolerancia)
        distintos = [cand for _, cand in ordenados if abs(abs(cand.valor) - abs(ev.valor)) > max(_tolerancia(cand, c), _tolerancia(ev, c))]
        if distintos and decision is None:
            lecturas = "; ".join(f"{aa.nombre} pág. {cc.pagina} = {numero(cc.valor, 2)}" for aa, cc in ordenados[:4])
            hecho = Hecho(campo=c.clave, periodo=p, valor=_normalizar(ev.valor, c), estado=Estado.CERO if ev.valor == 0 else Estado.VALOR,
                          capa=Capa.DOCUMENTO, unidad=c.unidad, origen=_origen_de(a, ev), certeza=Certeza.BAJA,
                          contraste=Contraste.DISCREPANTE, motivo="los adjuntos no coinciden entre sí",
                          nota=f"la SEC no lo publica y los adjuntos difieren: {lecturas}")
            return Resultado(c, p, hecho, hecho_sec, cands, [], ev, nota=hecho.nota)
        docs = {aa.clave for aa, _ in ordenados}
        certeza = Certeza.ALTA if len(docs) >= 2 else Certeza.MEDIA
        motivo = (hecho_sec.motivo if hecho_sec is not None else "la SEC no lo publica") + f"; leído en {len(docs)} adjunto(s)"
        hecho = de_valor(c.clave, p, _normalizar(ev.valor, c), Capa.DOCUMENTO, _origen_de(a, ev), unidad=c.unidad,
                         certeza=certeza, motivo=motivo, nota=f"según {a.nombre} pág. {ev.pagina}" + (f" ({ev.referencia})" if ev.referencia else ""))
        hecho = hecho.con(contraste=Contraste.SOLO_DOCUMENTO)
        return Resultado(c, p, hecho, hecho_sec, cands, [cand for _, cand in ordenados], ev)
    motivo = hecho_sec.motivo if hecho_sec is not None else "la SEC no lo publica y ningún adjunto lo trae"
    return Resultado(c, p, na(c.clave, p, motivo + "; ningún adjunto lo trae", unidad=c.unidad), hecho_sec, [], [], None)


def _cero_declarado(c: Campo, p: Periodo, exp: Expediente) -> Optional[Hecho]:
    patron = DECLARACIONES_CERO.get(c.clave)
    if not patron:
        return None
    for a in exp.de_tipo(Tipo.K10):
        if a.periodo_fin and p.fin > a.periodo_fin:
            continue
        for i, texto in enumerate(a.paginas, 1):
            m = patron.search(texto)
            if m:
                frase = texto[max(0, m.start() - 40):m.end() + 40].replace("\n", " ").strip()
                origen = Origen(documento=a.nombre, formulario=a.tipo.value, presentado=a.fecha, pagina=i)
                return Hecho(campo=c.clave, periodo=p, valor=0.0, estado=Estado.CERO, capa=Capa.SEC, unidad=c.unidad,
                             origen=origen, contraste=Contraste.CONFIRMADO,
                             nota=f"cero declarado en {a.nombre} pág. {i}: «…{frase}…»")
    return None


def _q4_por_accion(clave: str, p: Periodo, serie) -> Optional[Hecho]:
    """El 4T fiscal de las acciones medias y del BPA, que nadie publica suelto.

    Acciones medias del 4T = 4 × media del ejercicio − 3 × media de los nueve meses (las medias ponderan por días). BPA
    del 4T = beneficio del 4T / esas acciones. Sale como derivado con su fórmula: nunca como hecho publicado.
    """
    from .hechos import derivar
    fin_9m = p.inicio - timedelta(days=1)

    def par(campo: str):
        s = serie(campo)
        fy = next((h for q, h in s.items() if q.meses == 12 and q.fin == p.fin and h.hay_dato), None)
        nm = next((h for q, h in s.items() if q.meses == 9 and q.fin == fin_9m and h.hay_dato), None)
        return fy, nm

    tipo = "diluidas" if clave.endswith("diluidas") or clave.endswith("diluido") else "basicas"
    s_fy, s_9m = par(f"acciones_{tipo}")
    if s_fy is None or s_9m is None:
        return None
    if clave.startswith("acciones"):
        return derivar(clave, p, f"4 × {s_fy.periodo.clave} − 3 × 9M (acciones medias del 4T)", {"fy": s_fy, "nueve_meses": s_9m},
                       lambda fy, nueve_meses: 4 * fy - 3 * nueve_meses, unidad="acciones")
    b_fy, b_9m = par("beneficio_neto")
    if b_fy is None or b_9m is None:
        return None
    if tipo == "diluidas" and b_fy.valor - b_9m.valor < 0:
        # con pérdidas la dilución es antidilutiva: el BPA diluido del trimestre es el básico (ASC 260)
        s_fy, s_9m = par("acciones_basicas")
        if s_fy is None or s_9m is None:
            return None
    return derivar(clave, p, f"(beneficio {b_fy.periodo.clave} − 9M) / (4 × acciones {s_fy.periodo.clave} − 3 × 9M)",
                   {"b_fy": b_fy, "b_9m": b_9m, "s_fy": s_fy, "s_9m": s_9m},
                   lambda b_fy, b_9m, s_fy, s_9m: (b_fy - b_9m) / (4 * s_fy - 3 * s_9m), unidad="USD/acción")


def contrastar(exp: Expediente, facts: dict, obtenido_en: date, periodos: Dict[str, List[Periodo]],
               decisiones: Optional[Path] = None, paginas: Optional[Dict[str, List[PaginaLeida]]] = None) -> Tablero:
    paginas = paginas if paginas is not None else _leer_todo(exp)
    por_campo = _candidatos_por_campo(exp, paginas)
    decs = _cargar_decisiones(decisiones)
    resultados: List[Resultado] = []
    avisos: List[str] = []
    flujos = periodos["anuales"] + periodos["trimestres"]
    ajustes = sec_mod.splits(facts)
    cierres_fy = {p.fin for p in periodos["anuales"]}
    por_campo_sec: Dict[str, Dict[Periodo, Hecho]] = {}

    def serie(clave: str) -> Dict[Periodo, Hecho]:
        # los hechos de otro campo, con los mismos ajustes por split, para derivar el 4T por acción
        if clave not in por_campo_sec:
            cc = campo_de(clave)
            hs = sec_mod.hechos_xbrl(facts, cc, obtenido_en) if cc.conceptos else {}
            if cc.unidad in ("USD/acción", "acciones") and ajustes:
                hs = {q: sec_mod.ajustar_por_split(h, ajustes, cc.unidad == "USD/acción") for q, h in hs.items()}
            por_campo_sec[clave] = hs
        return por_campo_sec[clave]
    for c in CAMPOS:
        pedidos = periodos["instantes"] if c.tipo == "instante" else flujos
        hechos_sec = sec_mod.hechos_xbrl(facts, c, obtenido_en) if c.conceptos else {}
        if c.unidad in ("USD/acción", "acciones") and ajustes:
            # Lo presentado antes de un split se reexpresa como derivado, con fórmula;
            # así la serie es homogénea y el 10-Q previo al split deja de «discrepar».
            hechos_sec = {p: sec_mod.ajustar_por_split(h, ajustes, c.unidad == "USD/acción") for p, h in hechos_sec.items()}
        cands = por_campo[c.clave]
        for p in pedidos:
            h_sec = hechos_sec.get(p)
            if h_sec is None and c.conceptos:
                h_sec = sec_mod.hechos_xbrl(facts, c, obtenido_en, [p])[p]
            # El documento rotula sus columnas «Three months ended June 28, 2026»: de ahí salen el cierre y la
            # duración, no el día en que empezó el periodo. Comparar el periodo entero dejaba fuera todo lo leído a
            # una empresa de cierres por semanas, porque el comienzo calculado nunca es el que declara la SEC.
            pares = [(a, cand) for a, cand in cands if _mismo_periodo(cand.periodo, p)]
            # El 4T no existe en la SEC: se deriva FY − 9M y se contrasta como derivado.
            # Solo para magnitudes aditivas: un BPA o una media de acciones no se
            # restan (y el 9M de 2025 está además sin reexpresar por el split).
            if ((h_sec is None or not h_sec.hay_dato) and p.meses == 3 and p.fin.month == periodos["anuales"][-1].fin.month
                    and c.conceptos and c.unidad == "USD"):
                # el acumulado de nueve meses acaba en el cierre del trimestre anterior, no en el del ejercicio.
                # Se buscan por su cierre, no por un periodo calculado: el comienzo del ejercicio lo pone el emisor.
                fin_9m = p.inicio - timedelta(days=1)
                fy = next((h for q_, h in hechos_sec.items() if q_.meses == 12 and q_.fin == p.fin), None)
                nm = next((h for q_, h in hechos_sec.items() if q_.meses == 9 and q_.fin == fin_9m), None)
                if fy is not None and nm is not None and fy.hay_dato and nm.hay_dato:
                    q4 = sec_mod.q4_derivado(fy, nm)
                    r = _contrastar_celda(c, p, q4, pares, decs.get((c.clave, p.clave)))
                    if r.hecho.contraste is Contraste.CONFIRMADO:
                        r.hecho = q4.con(nota=f"4T = {fy.periodo.clave} − 9M; coincide con {r.evidencia.documento} pág. {r.evidencia.pagina}" if r.evidencia else "")
                    elif r.hecho.contraste is Contraste.SOLO_SEC:
                        r.hecho = q4
                    resultados.append(r)
                    continue
            if ((h_sec is None or not h_sec.hay_dato) and p.meses == 3 and p.fin in cierres_fy
                    and c.clave in ("acciones_basicas", "acciones_diluidas", "bpa_basico", "bpa_diluido")):
                q4 = _q4_por_accion(c.clave, p, serie)
                if q4 is not None:
                    resultados.append(_contrastar_celda(c, p, q4, pares, decs.get((c.clave, p.clave))))
                    continue
            if (h_sec is None or not h_sec.hay_dato) and p.meses == 3 and c.conceptos and c.unidad == "USD":
                # el trimestre que no se publica suelto se saca de los acumulados, que sí se publican
                por_acumulados = sec_mod.trimestre_por_acumulados(facts, c, hechos_sec, p)
                if por_acumulados is not None:
                    h_sec = por_acumulados
            r = _contrastar_celda(c, p, h_sec, pares, decs.get((c.clave, p.clave)))
            if r.hecho.contraste is Contraste.HUECO:
                cero = _cero_declarado(c, p, exp)
                if cero is not None:
                    r = Resultado(c, p, cero, h_sec, [], [], None, nota=cero.nota)
            resultados.append(r)
    no_aplican = _no_los_tiene_la_compania(resultados, facts)
    for r in resultados:
        if r.campo.clave in no_aplican and r.hecho.contraste is Contraste.HUECO:
            r.hecho = r.hecho.con(motivo=no_aplican[r.campo.clave])
    resumen: Dict[str, int] = {}
    for r in resultados:
        clave = r.hecho.contraste.name.lower() or "sin_contrastar"
        if clave == "hueco" and r.campo.clave in no_aplican:
            clave = "no_aplica"
        resumen[clave] = resumen.get(clave, 0) + 1
    return Tablero(resultados=resultados, paginas=paginas, resumen=resumen, avisos=avisos, no_aplican=no_aplican,
                   splits=[(fecha, razon) for fecha, razon, _ in ajustes], desfase_fiscal=sec_mod.desfase_fiscal(facts))
