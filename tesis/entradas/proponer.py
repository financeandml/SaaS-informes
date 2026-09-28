"""Lo que el sistema propone para un campo del asistente, y lo que pasa con ello cuando el analista lo confirma (04 · prop).

Una propuesta no es una entrada: no se escribe en `entradas.json` hasta que el analista la confirma, así que mientras
tanto el campo está vacío y la validación de siempre lo cuenta como falta. Al confirmarla, la página escribe el valor y,
en `_origen`, de dónde salió (fuente, motivo, huella y el valor propuesto). Desde ahí:

- si el analista cambia el valor, ya no es la propuesta: `normalizar` lo anota como suyo;
- si cambian los datos de los que salía, cambia la huella y el campo vuelve a «revisar» (`caducadas`), igual que los
  párrafos del paso 9 (`entradas/propuestas.py`).

Cada propuesta sale de una sola función de este registro (regla 13): la misma que usa el motor o la plantilla cuando
toma ese dato. Sin fuente no hay propuesta, y se dice por qué (`SinPropuesta`); nunca un valor por defecto escondido.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date
from typing import Callable, Dict, List, Optional, Union

__all__ = ["Contexto", "Propuesta", "SinPropuesta", "caducadas", "como_json", "en_bloque", "normalizar", "proponer"]


@dataclass(frozen=True)
class Propuesta:
    valor: object
    fuente: str
    motivo: str
    certeza: str = "alta"

    @property
    def huella(self) -> str:
        """Cambia si cambia el valor o su fuente: es lo que hace caducar una confirmación."""
        return hashlib.sha256(json.dumps([self.valor, self.fuente], sort_keys=True, default=str, ensure_ascii=False)
                              .encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class SinPropuesta:
    motivo: str


@dataclass
class Contexto:
    """Lo que una propuesta necesita saber; lo caro (el emisor de EDGAR) se pide una vez y solo si alguien lo usa."""
    ticker: str
    fecha: date
    datos: dict
    _cache: Dict[str, object] = field(default_factory=dict)

    def emisor(self):
        if "emisor" not in self._cache:
            from ..fuentes import sec
            self._cache["emisor"] = sec.emisor(self.ticker)
        return self._cache["emisor"]

    def portada(self):
        """El último 10-K de EDGAR (texto y DEI): el mismo que lee la ficha del informe."""
        if "portada" not in self._cache:
            from ..fuentes import sec
            self._cache["portada"] = sec.portada_10k(self.emisor())
        return self._cache["portada"]

    def facts(self):
        if "facts" not in self._cache:
            from ..fuentes import sec
            self._cache["facts"] = sec.companyfacts(self.emisor().cik)
        return self._cache["facts"]

    def sesiones(self):
        """Las sesiones de Nasdaq hasta la fecha del informe (cierre oficial): la misma petición de cinco años que usan el
        motor y el paso 8 (`precio.desde_5a`), así que va a la misma caché y no se pide dos veces."""
        if "sesiones" not in self._cache:
            from ..fuentes import precio
            self._cache["sesiones"] = precio.sesiones_nasdaq(self.ticker, precio.desde_5a(self.fecha), self.fecha, limite=2000)
        return self._cache["sesiones"]

    def valor(self, campo: str):
        return _valor(self.datos, campo)

    def fecha_valoracion(self) -> Optional[date]:
        """La que haya puesto el analista; si no, la propuesta (último cierre oficial en o antes de la fecha del informe)."""
        v = self.valor("meta.fecha_valoracion")
        if v:
            try:
                return date.fromisoformat(str(v))
            except ValueError:
                return None
        p = _REGISTRO["meta.fecha_valoracion"](self)
        return date.fromisoformat(p.valor) if isinstance(p, Propuesta) else None


_REGISTRO: Dict[str, Callable[[Contexto], Union[Propuesta, SinPropuesta]]] = {}


def propone(campo: str):
    def registrar(funcion):
        _REGISTRO[campo] = funcion
        return funcion
    return registrar


def proponer(ticker: str, fecha: date, datos: dict, campos: Optional[List[str]] = None) -> Dict[str, Union[Propuesta, SinPropuesta]]:
    """Una propuesta (o su ausencia, con motivo) por cada campo del registro, o solo por los de `campos`: la validación
    solo necesita las de lo ya confirmado, y calcularlas todas descargaba el 10-K en cada guardado."""
    ctx = Contexto(ticker.upper(), fecha, datos or {})
    salida: Dict[str, Union[Propuesta, SinPropuesta]] = {}
    for campo, funcion in _REGISTRO.items():
        if campos is not None and campo not in campos:
            continue
        try:
            salida[campo] = funcion(ctx)
        except Exception as e:                        # sin EDGAR o sin configuración: se dice, no se inventa
            from ..rotulos import fallo
            salida[campo] = SinPropuesta(f"no se pudo calcular ({fallo(e)})")
    return salida


def _config() -> dict:
    from ..rutas import CONFIG, leer_yaml
    ruta = CONFIG / "propuestas.yaml"
    return leer_yaml(ruta) if ruta.exists() else {}


def en_bloque(campo: str) -> bool:
    """Si «Confirmar las propuestas de este paso» puede confirmarlo sin que el analista lo mire uno a uno."""
    c = _config()
    return campo in (c.get("en_bloque") or []) and campo not in (c.get("nunca_en_bloque") or [])


def por_defecto(campo: str):
    """El valor de partida de `config/propuestas.yaml › valores`: el que propone el asistente y el que usa el motor si el
    analista no lo da. Sin él, error: un valor de partida escondido en código es lo que esta función evita."""
    valores = _config().get("valores") or {}
    if campo not in valores:
        raise KeyError(f"falta «{campo}» en config/propuestas.yaml › valores")
    return valores[campo]


def como_json(propuestas: Dict[str, Union[Propuesta, SinPropuesta]]) -> Dict[str, dict]:
    salida = {}
    for campo, p in propuestas.items():
        if isinstance(p, Propuesta):
            salida[campo] = {"valor": p.valor, "fuente": p.fuente, "motivo": p.motivo, "certeza": p.certeza,
                             "huella": p.huella, "bloque": en_bloque(campo)}
        else:
            salida[campo] = {"sin": p.motivo}
    return salida


def _valor(datos: dict, campo: str):
    x = datos
    for k in campo.split("."):
        x = x.get(k) if isinstance(x, dict) else None
    return x


def normalizar(datos: dict) -> dict:
    """Lo confirmado desde una propuesta cuyo valor el analista ha cambiado después ya no es la propuesta: es suyo."""
    origen = datos.get("_origen")
    if not isinstance(origen, dict):
        return datos
    for campo, o in list(origen.items()):
        if isinstance(o, dict) and o.get("tipo") == "propuesta" and _valor(datos, campo) != o.get("valor"):
            origen[campo] = {"tipo": "analista", "antes": {k: o.get(k) for k in ("fuente", "valor")}}
    return datos


def confirmadas(datos: dict) -> List[tuple]:
    """(rótulo en español, fuente) de cada campo cuyo valor es el que propuso el sistema y el analista confirmó."""
    rotulos = _config().get("rotulos") or {}
    origen = datos.get("_origen") if isinstance(datos, dict) else None
    return [(rotulos.get(campo, campo.split(".")[-1].replace("_", " ")), o.get("fuente", ""))
            for campo, o in (origen or {}).items() if isinstance(o, dict) and o.get("tipo") == "propuesta"]


def confirmados(datos: dict) -> List[str]:
    """Los campos cuyo valor se confirmó desde una propuesta (los únicos que pueden caducar)."""
    origen = datos.get("_origen") if isinstance(datos, dict) else None
    return [c for c, o in (origen or {}).items() if isinstance(o, dict) and o.get("tipo") == "propuesta"]


def caducadas(datos: dict, propuestas: Dict[str, Union[Propuesta, SinPropuesta]]) -> List[str]:
    """«campo: …» de cada propuesta confirmada cuyos datos han cambiado desde entonces (la huella es otra)."""
    origen = datos.get("_origen") if isinstance(datos, dict) else None
    faltas = []
    for campo, o in (origen or {}).items():
        if not isinstance(o, dict) or o.get("tipo") != "propuesta":
            continue
        p = propuestas.get(campo)
        if isinstance(p, Propuesta) and p.huella != o.get("huella"):
            faltas.append(f"{campo}: la propuesta cambió desde que la confirmó (antes «{o.get('valor')}», ahora «{p.valor}» · "
                          f"{p.fuente}): revísela")
        elif isinstance(p, SinPropuesta):
            faltas.append(f"{campo}: la propuesta que confirmó ya no se puede calcular ({p.motivo}): revísela")
    return faltas


# ---------------------------------------------------------------- el registro

@propone("meta.sector")
def _sector(ctx: Contexto):
    """El paquete sectorial del SIC que declara el emisor en EDGAR (`config/sectores.yaml`), la misma función que usa el
    motor cuando el analista no lo ha confirmado."""
    from ..motor.datos import ingresos_anuales, paquete_por_sic, sectores
    em = ctx.emisor()
    ingresos = None
    if any(a <= int(em.sic) <= b for a, b in (sectores().get("bloqueo_biotech") or {}).get("sic", [])):   # como el paso 1
        from ..fuentes import sec
        facts, obtenido = sec.companyfacts(em.cik)
        ingresos = ingresos_anuales(facts, obtenido)
    paquete, bloqueo = paquete_por_sic(em.sic, ingresos)
    if bloqueo:
        return SinPropuesta(f"bloqueo v1 — {bloqueo}")
    return Propuesta(paquete, f"SEC EDGAR, SIC {em.sic}", "config/sectores.yaml: del código SIC al paquete sectorial")


@propone("meta.tipo")
def _tipo(ctx: Contexto):
    """Actualización si hay entradas guardadas de un informe anterior del mismo valor; si no, inicio de cobertura."""
    from .asistente import fechas
    anteriores = [f for f in fechas(ctx.ticker) if f < ctx.fecha.isoformat()]
    if anteriores:
        return Propuesta("actualizacion", f"entradas guardadas del {anteriores[-1]}", "hay un informe anterior de este valor")
    return Propuesta("inicio_cobertura", "sin entradas anteriores de este valor", "primer informe de este valor")


# ---------------------------------------------------------------- F11: lo que ya tiene fuente oficial o valor en config

def _de_config(campo: str):
    def funcion(ctx: Contexto):
        return Propuesta(por_defecto(campo), "config/propuestas.yaml", "valor de partida de la casa; el motor usa el mismo si no se da")
    return funcion


for _campo in ("val.mitad_de_anio", "val.sbc", "val.arrendamientos", "wacc.beta_metodo", "wacc.prima", "wacc.kd_metodo",
               "wacc.tipo_marginal", "tv.metodo", "pos.salida"):
    propone(_campo)(_de_config(_campo))


@propone("meta.fecha_valoracion")
def _fecha_valoracion(ctx: Contexto):
    """La última sesión con cierre oficial en Nasdaq antes de la fecha del informe (o en ella, si es un día pasado: la de
    hoy puede no haber cerrado todavía)."""
    hoy = date.today()
    validas = [d for d, s in ctx.sesiones().items() if s.cierre is not None and (d <= ctx.fecha if ctx.fecha < hoy else d < ctx.fecha)]
    if not validas:
        return SinPropuesta("Nasdaq no devuelve ninguna sesión cerrada en las tres semanas anteriores a la fecha del informe")
    d = max(validas)
    return Propuesta(d.isoformat(), f"Nasdaq, sesión del {d:%d/%m/%Y}", "último cierre oficial anterior a la fecha del informe")


@propone("meta.nombre_presentacion")
def _nombre(ctx: Contexto):
    """El de la portada del último 10-K, con la misma función que la ficha del informe."""
    from ..datos.ficha import nombre_presentacion
    portada = ctx.portada()
    if portada is None:
        return SinPropuesta("EDGAR no sirve el último 10-K del emisor")
    nombre = nombre_presentacion(portada.nombre_portada, portada.dei.get("EntityRegistrantName") or ctx.emisor().nombre)
    return Propuesta(nombre, f"portada del 10-K de EDGAR ({portada.deposito.accession})", "sin sufijo de estado ni mayúsculas de registro")


@propone("meta.analista")
def _analista(ctx: Contexto):
    """El que firmó las últimas entradas guardadas, de este valor o de otro."""
    from .. import entorno
    rutas = sorted(entorno.carpeta("entradas").glob("*/*/entradas.json"), key=lambda r: r.stat().st_mtime, reverse=True)
    for r in rutas:
        try:
            nombre = str(((json.loads(r.read_text(encoding="utf-8")).get("meta") or {}).get("analista")) or "").strip()
        except (OSError, ValueError):
            continue
        if nombre:
            return Propuesta(nombre, f"entradas de {r.parent.parent.name} del {r.parent.name}", "el analista de las últimas entradas guardadas")
    return SinPropuesta("no hay entradas guardadas con nombre de analista")


def _del_10k(extraer, que: str):
    def funcion(ctx: Contexto):
        portada = ctx.portada()
        if portada is None:
            return SinPropuesta("EDGAR no sirve el último 10-K del emisor")
        r = extraer(portada.texto)
        if not r:
            return SinPropuesta(f"el 10-K no declara {que} de forma reconocible: la aporta el analista con su cita")
        d = portada.deposito
        return Propuesta(r[0], f"10-K {d.periodo:%Y} (EDGAR, {d.accession})" if d.periodo else f"10-K (EDGAR, {d.accession})",
                         f"«{r[-1][:220]}»")
    return funcion


def _empleados(texto):
    from ..datos.ficha import proponer_empleados
    r = proponer_empleados(texto)
    return (int(r[0]), r[2]) if r else None


def _fundacion(texto):
    from ..datos.ficha import proponer_fundacion
    return proponer_fundacion(texto)


propone("perfil.empleados")(_del_10k(_empleados, "la plantilla"))
propone("perfil.fundacion")(_del_10k(_fundacion, "el año de constitución o fundación"))


@propone("val.anio_base")
def _anio_base(ctx: Contexto):
    """Últimos 12 meses si, a la fecha del informe, hay al menos dos 10-Q presentados después del último 10-K; si no, el
    último ejercicio (04, paso 7)."""
    dep = [d for d in ctx.emisor().depositos if d.presentado <= ctx.fecha]
    k = max((d for d in dep if d.formulario == "10-K" and d.periodo), key=lambda d: d.periodo, default=None)
    if k is None:
        return SinPropuesta("sin 10-K en EDGAR anterior a la fecha del informe")
    q = sorted({d.periodo for d in dep if d.formulario == "10-Q" and d.periodo and d.periodo > k.periodo})
    motivo = f"EDGAR: {len(q)} 10-Q tras el 10-K de {k.periodo:%d/%m/%Y}"
    if len(q) >= 2:
        return Propuesta("ultimos_12_meses", motivo, "dos o más trimestres desde el cierre")
    return Propuesta("ultimo_ejercicio", motivo, "menos de dos trimestres desde el cierre")


def _paquete(ctx: Contexto) -> str:
    return ctx.valor("meta.sector") or getattr(_REGISTRO["meta.sector"](ctx), "valor", None) or "general"


@propone("val.periodo_explicito")
def _periodo(ctx: Contexto):
    from ..motor.datos import periodo_propuesto
    paquete = _paquete(ctx)
    return Propuesta(periodo_propuesto(paquete), f"config/sectores.yaml, paquete «{paquete}»", "el extremo alto de la horquilla del paquete")


@propone("val.horizonte_meses")
def _horizonte(ctx: Contexto):
    from ..umbrales import umbral
    return Propuesta(int(umbral("horizonte_meses_defecto")), "config/umbrales.yaml", "horizonte de la casa; el único del informe")


@propone("pos.fecha_entrada")
def _fecha_entrada(ctx: Contexto):
    fv = ctx.fecha_valoracion()
    if fv is None:
        return SinPropuesta("sin fecha de valoración")
    return Propuesta(fv.isoformat(), "fecha de valoración", "la entrada al cierre de la fecha de valoración")


@propone("pos.precio_entrada")
def _precio_entrada(ctx: Contexto):
    fv = ctx.fecha_valoracion()
    s = ctx.sesiones().get(fv) if fv else None
    if s is None or s.cierre is None:
        return SinPropuesta("Nasdaq no da el cierre de la fecha de valoración")
    return Propuesta(round(float(s.cierre), 2), f"Nasdaq, cierre oficial del {fv:%d/%m/%Y}", "el precio único del informe (regla 4)")


def _mas_meses(d: date, meses: int) -> date:
    import calendar as _cal
    anio, mes = divmod(d.month - 1 + meses, 12)
    return date(d.year + anio, mes + 1, min(d.day, _cal.monthrange(d.year + anio, mes + 1)[1]))


@propone("pos.fechas_revision")
def _fechas_revision(ctx: Contexto):
    """La próxima presentación de resultados que publica la bolsa y el fin del horizonte. Ninguna fecha estimada a mano."""
    from ..fuentes import calendario
    from ..umbrales import umbral
    fv = ctx.fecha_valoracion()
    if fv is None:
        return SinPropuesta("sin fecha de valoración")
    meses = int(ctx.valor("val.horizonte_meses") or umbral("horizonte_meses_defecto"))
    fechas, fuentes = [], []
    prox = calendario.proxima(ctx.ticker, None, ctx.fecha)
    if prox is not None and prox.fecha > ctx.fecha:
        fechas.append(prox.fecha.isoformat())
        fuentes.append(f"próximos resultados según Nasdaq ({'esperada' if prox.esperada else 'anunciada'})")
    fechas.append(_mas_meses(fv, meses).isoformat())
    fuentes.append(f"fin del horizonte de {meses} meses")
    return Propuesta(fechas, " · ".join(fuentes), "fechas publicadas y el fin del horizonte")


@propone("pos.kpis")
def _kpis(ctx: Contexto):
    """Los KPI del paquete sectorial (config/sectores.yaml › kpis): el analista pone el verde y el rojo."""
    from ..motor.datos import sectores
    paquete = _paquete(ctx)
    kpis = sectores().get("kpis") or {}
    lista = kpis.get(paquete) or kpis.get("general")
    if not lista:
        return SinPropuesta(f"config/sectores.yaml no tiene KPI para el paquete «{paquete}»")
    return Propuesta([{"kpi": k["kpi"], "fuente": k["fuente"], "frecuencia": k["frecuencia"]} for k in lista],
                     f"config/sectores.yaml, paquete «{paquete if paquete in kpis else 'general'}» (borrador pendiente de revisar por el analista)",
                     "los indicadores del paquete; el verde y el rojo son del analista")


@propone("wacc.erp")
def _erp(ctx: Contexto):
    """La prima de riesgo de mercado de referencia de la casa, con fuente y fecha, si la hay (config/erp.yaml)."""
    import yaml
    from ..rutas import CONFIG
    from ..umbrales import umbral
    ruta = CONFIG / "erp.yaml"
    d = (yaml.safe_load(ruta.read_text(encoding="utf-8")) or {}) if ruta.exists() else {}
    if d.get("valor") is None or not d.get("fuente") or not d.get("fecha"):
        return SinPropuesta("no hay ERP de referencia en config/erp.yaml (valor, fuente y fecha): la fija el analista")
    edad = (ctx.fecha - date.fromisoformat(str(d["fecha"]))).days
    if edad > int(umbral("erp_antiguedad_max_dias")):
        return SinPropuesta(f"la ERP de config/erp.yaml es del {d['fecha']} ({edad} días): hay que actualizarla")
    return Propuesta(float(d["valor"]), f"{d['fuente']}, {d['fecha']}", "ERP de referencia de la casa")


# ---------------------------------------------------------------- F12: series del escenario base por su histórico
# Las mismas funciones que imprime el informe junto a cada supuesto (`motor/historico.py`): lo que se confirma es lo que
# se ve como «histórico». Solo el base: el pesimista y el optimista se dan como diferencia sobre él.


def _historico(ctx: Contexto):
    if "historico" not in ctx._cache:
        from ..motor import historico
        fv = ctx.fecha_valoracion() or ctx.fecha
        ctx._cache["historico"] = historico.series(ctx.facts()[0], fv)
    return ctx._cache["historico"]


def _de_serie(s, convergencia=None):
    """Una serie del histórico como propuesta; `convergencia` = (valor en N, de dónde sale) si converge linealmente."""
    if not s.hay_valor:
        return SinPropuesta(s.motivo)
    fuente = f"SEC (companyfacts): {s.formula}"
    if convergencia is None:
        return Propuesta({"1": s.valor, "N": s.valor}, fuente, s.motivo, s.certeza)
    from ..formato import numero
    final, origen = convergencia
    return Propuesta({"1": s.valor, "N": final}, f"{fuente}; en el año N, {origen}",
                     f"{s.motivo}; converge a {numero(final, 1)} % en el año N", s.certeza)


for _clave in ("da_pct", "capex_pct", "sbc_pct"):
    propone(f"esc.base.{_clave}")((lambda k: lambda ctx: _de_serie(_historico(ctx)[k]))(_clave))


@propone("esc.base.fm_pct_incremental")
def _fm(ctx: Contexto):
    s = _historico(ctx)["fm_pct_incremental"]
    return Propuesta(s.valor, f"SEC (companyfacts): {s.formula}", s.motivo, s.certeza) if s.hay_valor else SinPropuesta(s.motivo)


@propone("esc.base.impuesto_caja")
def _impuesto(ctx: Contexto):
    marginal = ctx.valor("wacc.tipo_marginal")
    marginal = float(marginal if marginal is not None else por_defecto("wacc.tipo_marginal"))
    return _de_serie(_historico(ctx)["impuesto_caja"], (marginal, "el tipo marginal"))


def _g_base(ctx: Contexto) -> float:
    g = _valor(ctx.datos, "esc.base.g")
    return float(g if g is not None and not isinstance(g, dict) else por_defecto("esc.base.g"))


@propone("esc.base.crecimiento_ingresos")
def _crecimiento(ctx: Contexto):
    from ..motor import historico
    s = historico.crecimiento_udm(ctx.facts()[0], ctx.fecha_valoracion() or ctx.fecha)
    return _de_serie(s, (_g_base(ctx), "el crecimiento terminal del base"))


@propone("esc.base.margen_ebit")
def _margen(ctx: Contexto):
    """Año 1: el margen del último ejercicio. Año N: en los paquetes cíclicos, la mediana de ciclo (la misma que comprueba
    `motor/sector.py`); en los demás, el mismo margen, porque una mediana de diez años de una compañía que ha cambiado de
    escala (NFLX: 18 % frente al 30 % actual) no es un margen normalizado sino uno antiguo."""
    from ..motor import historico
    from ..umbrales import umbral
    facts, fv = ctx.facts()[0], ctx.fecha_valoracion() or ctx.fecha
    ultimo = historico.margen_ultimo(facts, fv)
    if not ultimo.hay_valor:
        return SinPropuesta(ultimo.motivo)
    paquete = _paquete(ctx)
    if paquete not in (umbral("sector").get("paquetes_ciclicos") or []):
        return _de_serie(ultimo)
    minimo, maximo = (int(x) for x in umbral("sector")["ciclo_anios"])
    ciclo = historico.margen_ciclo(facts, fv, minimo, maximo)
    if not ciclo.hay_valor:
        return SinPropuesta(f"paquete cíclico «{paquete}»: {ciclo.motivo}")
    return _de_serie(ultimo, (ciclo.valor, f"la mediana de ciclo ({ciclo.motivo})"))


for _nombre in ("pesimista", "base", "optimista"):
    propone(f"esc.{_nombre}.g")((lambda n: lambda ctx: Propuesta(
        float(por_defecto(f"esc.{n}.g")), "config/propuestas.yaml", "crecimiento terminal de partida de la casa (04)"))(_nombre))


@propone("val.inversiones_lp")
def _inversiones_lp(ctx: Contexto):
    """A4 (decisión del analista, 28/09/2026): los valores negociables a largo plazo del último balance entran en el puente
    si el analista confirma la propuesta. Sin ellos en la SEC, no hay propuesta."""
    from ..datos.campos import campo
    from ..fuentes import sec
    from ..formato import numero
    fv = ctx.fecha_valoracion() or ctx.fecha
    facts = ctx.facts()[0]
    # los del último balance, el mismo del puente: un saldo de hace años no es liquidez de hoy
    balances = [p.fin for p, h in sec.hechos_xbrl(facts, campo("total_activo"), fv).items() if p.es_instante and p.fin <= fv and h.hay_dato]
    if not balances:
        return SinPropuesta("sin balance en la SEC anterior a la fecha de valoración")
    fin = max(balances)
    h = next((h for p, h in sec.hechos_xbrl(facts, campo("inversiones_lp"), fv).items() if p.es_instante and p.fin == fin and h.hay_dato), None)
    if h is None or not h.valor:
        return SinPropuesta(f"el balance a {fin:%d/%m/%Y} no trae valores negociables a largo plazo")
    concepto = h.origen.concepto if h.origen else "valores negociables no corrientes"
    return Propuesta("incluir", f"SEC (companyfacts), {concepto}: {numero(h.valor / 1e6)} mln USD a {fin:%d/%m/%Y}",
                     "son liquidez de la compañía y suman al valor por acción")
