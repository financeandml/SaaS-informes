"""Parte B (apartados 4–7) y la guía de la compañía (Cuadro 2 y apartado 26), ya rehechas (F2).

Todo lo que se imprime sale de EDGAR, de Nasdaq o de las entradas del analista (04, paso 4), en español. Lo que falta
no se rellena: queda en `faltas` para la puerta de calidad y el asistente.
"""

from __future__ import annotations
from . import lexico

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Callable, Dict, List, Optional, Sequence, Set, Tuple

from ..datos import guia as guia_mod
from ..entradas import Entradas
from ..formato import Celda, celda, fecha as f_fecha, numero
from ..rotulos import fallo
from ..datos.segmentos import Segmentos

__all__ = ["ParteB", "Textos", "cuadro_segmentos", "cuadro_objetivos", "cuadro_fechas", "cuadro_catalizadores",
           "cuadro_guia_real", "textos", "siguiente_trimestre"]


@dataclass
class ParteB:
    segmentos: Optional[Segmentos] = None
    notas: List[guia_mod.Nota] = field(default_factory=list)
    entradas: Entradas = field(default_factory=Entradas)
    dividendos: List = field(default_factory=list)          # calendario.Dividendo
    dividendos_url: str = ""
    faltas: List[str] = field(default_factory=list)          # del paso 4 y de las fuentes: a la puerta de calidad
    splits: Sequence[Tuple[date, float]] = ()
    clases: List[str] = field(default_factory=list)          # clases de acciones registradas (portada del 10-K), en español
    alias: Dict[str, str] = field(default_factory=dict)      # «10-K» → «10-K 2025»: cómo se cita cada documento en el cuerpo
    textos: Dict[str, str] = field(default_factory=dict)     # documento (y «documento#página») → texto: verifica las citas
    item1a: Optional[object] = None                          # item1a.Item1A del último 10-K (parte F)
    sorpresas: List = field(default_factory=list)            # calendario.Sorpresa: consenso frente a BPA de la bolsa (26)
    sorpresas_respuesta: Optional[Tuple[str, str, object]] = None   # (url, cuerpo, obtenido): la evidencia literal del 26
    cortos: Optional[Tuple[date, float]] = None              # último interés en corto de la bolsa (28)

    @property
    def confirmadas(self) -> Set[str]:
        return set(self.entradas.valor("guia.confirmadas") or [])


def clase_de_accion(titulo: str) -> str:
    """«Common Stock, par value $0.0001 per share» → «Acciones ordinarias (valor nominal 0,0001 USD por acción)»."""
    import re
    t = " ".join(titulo.split())
    tipo = "Acciones ordinarias" if re.search(r"common stock|ordinary shares", t, re.I) else (
        "Acciones preferentes" if re.search(r"preferred", t, re.I) else t)
    clase = re.search(r"class ([A-Z])\b", t, re.I)
    if clase and tipo != t:
        tipo += f" de clase {clase.group(1).upper()}"
    nominal = re.search(r"par value \$?([\d.]+)", t, re.I)
    if nominal and tipo != t:
        tipo += f" (valor nominal {nominal.group(1).replace('.', ',')} USD por acción)"
    return tipo


def siguiente_trimestre(t: Optional[str]) -> Optional[str]:
    """«3T FY26» → «4T FY26»; «4T FY26» → «1T FY27»."""
    if not t:
        return None
    n, anio = int(t[0]), int(t[-2:])
    return f"{n + 1}T FY{anio:02d}" if n < 4 else f"1T FY{(anio + 1) % 100:02d}"


def _mln(v: Optional[float]) -> str:
    return numero(v / 1e6) if v is not None else "N/A"


def cuadro_segmentos(n, s: Segmentos, etiqueta: Callable) -> Tuple[object, object, str, List[str]]:
    """(cuadro de segmentos y líneas, cuadro de geografía, gráfico de mezcla, rótulos sin traducir)."""
    from . import graficos
    from .informe import Cuadro, FilaCuadro
    columnas = [s.etiqueta_udm if p == s.udm else etiqueta(p) for p in s.periodos]
    filas = []
    origen = ", ".join(f"{o.formulario} del {f_fecha(o.presentado)}" if o.presentado else o.formulario for o in s.origenes.values())
    for seg in s.de_tipo("segmento"):
        filas.append(FilaCuadro(seg.rotulo, [celda(seg.valores.get(p), "M USD") for p in s.periodos], capa="H", destacada=True))
        for linea in [l for l in s.de_tipo("producto") if l.padre == seg.miembro]:
            filas.append(FilaCuadro(linea.rotulo, [celda(linea.valores.get(p), "M USD") for p in s.periodos], capa="H", sangria=True))
    for linea in [l for l in s.de_tipo("producto") if l.padre is None]:
        filas.append(FilaCuadro(linea.rotulo, [celda(linea.valores.get(p), "M USD") for p in s.periodos], capa="H"))
    for linea in s.de_tipo("conciliacion"):
        filas.append(FilaCuadro(linea.rotulo, [celda(linea.valores.get(p), "M USD") for p in s.periodos], capa="H", sangria=True))
    if filas:
        filas.append(FilaCuadro("Ingresos consolidados", [celda(s.consolidado.get(p), "M USD") for p in s.periodos], capa="H", destacada=True))
    notas = list(s.cuadres)
    if s.udm is not None:
        notas.append(f"{s.etiqueta_udm}: ejercicio + acumulado del año en curso − acumulado del año anterior (10-Q).")
    segmentos = Cuadro(n.siguiente(), "Ingresos por segmento y línea de negocio (mln USD)", columnas, filas,
                       f"Fuente: SEC EDGAR, estados del {origen}; ejes de segmento, producto y conciliación.", notas)
    geo, padre = s.geografia()
    desgloses = s.desgloses_geograficos()
    # dos ejes geográficos del mismo total, uno detrás de otro y dicho en la nota: no se suman entre sí [21]
    filas_geo = [FilaCuadro(l.rotulo, [celda(l.valores.get(p), "M USD") for p in s.periodos], capa="H", sangria=i > 0)
                 for i, d in enumerate(desgloses) for l in d]
    notas_geo = ([f"Dos desgloses geográficos del mismo total, que no se suman entre sí: {', '.join(l.rotulo for l in desgloses[0])}; "
                  f"y, en sangría, {', '.join(l.rotulo for l in desgloses[1])}."] if len(desgloses) > 1 else [])
    de_que = ""
    if padre is not None:
        linea_padre = next((l for l in s.lineas if l.miembro == padre or l.miembro.endswith("|" + padre)), None)
        de_que = f" de {linea_padre.rotulo}" if linea_padre is not None else ""
    geografia = Cuadro(n.siguiente(), f"Ingresos por geografía{de_que} (mln USD)", columnas, filas_geo,
                       f"Fuente: SEC EDGAR, estados del {origen}; eje geográfico. El 10-Q no suele desglosarlo: sin él, "
                       "la columna de los últimos doce meses queda N/A.", notas_geo)
    # la mezcla, al nivel más fino que suma el total: las líneas de cada segmento que las desglosa, el segmento si no
    ultimo = s.periodos[-1] if s.periodos else None
    partes = []
    for seg in s.de_tipo("segmento"):
        hijas = [l for l in s.de_tipo("producto") if l.padre == seg.miembro and ultimo in l.valores]
        partes += [(l.rotulo, l.valores[ultimo]) for l in hijas] or ([(seg.rotulo, seg.valores[ultimo])] if ultimo in seg.valores else [])
    if len([p for p in partes if p[1].hay_dato and (p[1].valor or 0) > 0]) < 2:
        partes = [(l.rotulo, l.valores[ultimo]) for l in s.de_tipo("producto") if ultimo in l.valores] or \
                 [(l.rotulo, l.valores[ultimo]) for l in geo if ultimo in l.valores]
    svg, _ = graficos.tarta(partes) if partes else ("", [])
    return segmentos, geografia, svg, s.sin_traducir


def cuadro_objetivos(n, vigentes: Sequence[guia_mod.Candidato], hay_candidatos: bool):
    from .informe import Cuadro, FilaCuadro
    filas = []
    for c in vigentes:
        if c.unidad == "USD":
            rango = f"{_mln(c.bajo)} – {_mln(c.alto)} mln USD" if c.bajo != c.alto else f"{_mln(c.bajo)} mln USD"
        elif c.unidad == "USD/acción":
            rango = f"{numero(c.bajo, 2)} – {numero(c.alto, 2)} USD" if c.bajo != c.alto else f"{numero(c.bajo, 2)} USD"
        else:
            rango = f"{numero(c.bajo, 1)} – {numero(c.alto, 1)} %" if c.bajo != c.alto else f"{numero(c.bajo, 1)} %"
        filas.append(FilaCuadro(c.rotulo, [Celda(c.trimestre, "", "H", "valor", ""), Celda(rango, "", "H", "valor", c.fila),
                                           Celda(f_fecha(c.presentado), "", "H", "valor", ""),
                                           Celda("8-K, Ex. 99.1", "", "", "valor", c.url)], capa="H"))
    if filas:
        fuente = "Fuente: SEC EDGAR, nota de resultados (8-K, Ex. 99.1), tabla de guía. Guía de la compañía confirmada por el analista; no es una estimación propia."
    elif hay_candidatos:
        fuente = "Pendiente: el analista no ha confirmado ninguno de los candidatos de guía de la última nota de resultados."
    else:
        # 01: lo que la compañía no publica no se imprime como N/A (AAPL y ORCL, fallos 70 y 71 de la auditoría)
        fuente = ("No aplica: la compañía no publica una tabla de objetivos cuantitativos vigentes en su última "
                  "comunicación de resultados.")
    return Cuadro(n.siguiente(), "Objetivos vigentes de la compañía", ["Periodo", "Rango", "Comunicado el", "Documento"], filas, fuente)


def cuadro_fechas(n, hoy: date, proxima, dividendos: Sequence, junta: Optional[date], origen_junta, trimestre: Optional[str],
                  url_dividendos: str = ""):
    """Próximos resultados (siempre ≥ fecha del informe), dividendo y junta."""
    from .informe import Cuadro, FilaCuadro
    filas = []
    if proxima is not None:
        calificativo = ("estimada por el proveedor de la bolsa (algoritmo; la compañía no la ha anunciado)" if proxima.estimada
                        else "esperada según la bolsa" if proxima.esperada else "anunciada")
        texto = f_fecha(proxima.fecha) + (f", {proxima.momento}" if proxima.momento else "")
        filas.append(FilaCuadro("Próximos resultados" + (f" ({trimestre})" if trimestre else ""),
                                [Celda(texto, "", "H", "valor", proxima.texto), Celda(f"Nasdaq · {calificativo}", "", "", "valor", "")]))
    elif lexico.es_bme():
        # BME no publica calendario de resultados: la fecha es la que anuncie el emisor, nunca un plazo supuesto
        filas.append(FilaCuadro("Próximos resultados", [Celda("sin anunciar", "", "", "valor", "el emisor no ha anunciado la fecha en BME"),
                                                         Celda("comunicaciones del emisor en BME", "", "", "valor", "")]))
    else:
        filas.append(FilaCuadro("Próximos resultados", [Celda("N/A", "", "", "na", "la bolsa no publica una fecha posterior a la del informe"),
                                                         Celda("Nasdaq", "", "", "valor", "")]))
    futuros = [d for d in dividendos if (d.pago and d.pago >= hoy) or (d.ex and d.ex >= hoy)]
    if futuros:
        d = min(futuros, key=lambda d: d.pago or d.ex)
        texto = (f"pago el {f_fecha(d.pago)}" if d.pago else "") + (f" (ex-dividendo el {f_fecha(d.ex)})" if d.ex else "")
        if d.importe is not None:
            texto = f"{numero(d.importe, 2)} USD por acción, " + texto
        filas.append(FilaCuadro("Dividendo", [Celda(texto, "", "H", "valor", d.texto), Celda("Nasdaq · declarado el " + f_fecha(d.declarado) if d.declarado else "Nasdaq", "", "", "valor", url_dividendos)]))
    elif dividendos:
        ultimo = max(dividendos, key=lambda d: d.ex or date.min)
        filas.append(FilaCuadro("Dividendo", [Celda(f"sin anunciar; el último, ex-dividendo el {f_fecha(ultimo.ex)}", "", "H", "valor", ""),
                                              Celda("Nasdaq", "", "", "valor", url_dividendos)]))
    elif lexico.es_bme():
        # sin calendario de dividendos de la bolsa no se puede afirmar que no paga: lo dicen las cuentas (estado de flujos,
        # apartado 10) y lo que anuncie el emisor
        filas.append(FilaCuadro("Dividendo", [Celda("sin anunciar", "", "", "valor", "BME no publica calendario de dividendos; los pagados, en el apartado 10"),
                                              Celda("comunicaciones del emisor en BME", "", "", "valor", "")]))
    else:
        filas.append(FilaCuadro("Dividendo", [Celda("no paga dividendo", "", "H", "cero", "la bolsa no registra dividendos"),
                                              Celda("Nasdaq", "", "", "valor", url_dividendos)]))
    if junta is not None and junta >= hoy:
        filas.append(FilaCuadro("Junta de accionistas", [Celda(f_fecha(junta), "", "H", "valor", ""), Celda("DEF 14A", "", "", "valor", "")]))
    elif junta is not None:
        filas.append(FilaCuadro("Junta de accionistas", [Celda(f"sin convocar; la última, el {f_fecha(junta)}", "", "H", "valor", ""),
                                                         Celda("DEF 14A", "", "", "valor", getattr(origen_junta, "referencia", ""))]))
    return Cuadro(n.siguiente(), "Fechas clave", ["Fecha", "Fuente"], filas,
                  ("Fuente: comunicaciones del emisor en BME y entradas del analista. Solo fechas iguales o posteriores a la del informe."
                   if lexico.es_bme() else
                   "Fuente: Nasdaq (calendario de resultados y dividendos) y SEC EDGAR (DEF 14A). Solo fechas iguales o posteriores a la del informe."))


def _fecha_catalizador(texto: str) -> str:
    """«2026-11-04» → «04/11/2026»; «2027-T4» → «4T 2027» (trimestre natural)."""
    import re
    m = re.fullmatch(r"(\d{4})-(\d\d)-(\d\d)", texto)
    if m:
        return f"{m.group(3)}/{m.group(2)}/{m.group(1)}"
    m = re.fullmatch(r"(\d{4})-T([1-4])", texto)
    return f"{m.group(2)}T {m.group(1)}" if m else texto


_TIPOS = {"resultados": "Resultados", "producto": "Producto", "regulatorio": "Regulatorio", "corporativo": "Corporativo", "macro": "Macro"}


def cuadro_catalizadores(n, e: Entradas):
    from .informe import Cuadro, FilaCuadro
    filas = []
    for c in e.valor("catalizadores") or []:
        ev = (c.get("evidencia") or [{}])[0]
        prob = c.get("probabilidad")
        filas.append(FilaCuadro(c.get("evento", ""), [
            Celda(_fecha_catalizador(str(c.get("fecha", ""))), "", "S", "valor", ""),
            Celda(_TIPOS.get(c.get("tipo", ""), c.get("tipo", "")), "", "S", "valor", ""),
            Celda(str(c.get("pilar", "—")), "", "S", "valor", ""),
            Celda("positivo" if c.get("impacto") == "positivo" else "negativo", "", "S", "valor" if c.get("impacto") == "positivo" else "negativo", ""),
            Celda(f"{numero(prob, 0)} %" if prob is not None else "N/A", "", "S", "valor" if prob is not None else "na", ""),
            Celda(alias_doc(ev.get("doc", "—")), "", "", "valor", ev.get("texto", "")),
        ], capa="S"))
    fuente = ("Fuente: analista; cada catalizador lleva su evidencia, verificada en el documento citado."
              if filas else "Pendiente: el analista no ha registrado catalizadores (mínimo 3).")
    return Cuadro(n.siguiente(), "Catalizadores", ["Fecha o ventana", "Tipo", "Pilar", "Impacto", "Probabilidad", "Evidencia"], filas, fuente)


def cuadro_guia_real(n, comparaciones: Sequence[guia_mod.Comparacion]):
    """Métricas consolidadas; la guía por segmento queda en el Cuadro 2 (vigente) y no alarga este."""
    from .informe import Cuadro, FilaCuadro
    filas = []
    for x in [c for c in comparaciones if not c.candidato.metrica.startswith("ingresos_segmento")]:
        c, r = x.candidato, x.real
        if c.unidad == "USD":
            guia, real = (f"{_mln(c.bajo)} – {_mln(c.alto)}" if c.bajo != c.alto else _mln(c.bajo)), _mln(r.valor)
        elif c.unidad == "USD/acción":
            guia, real = (f"{numero(c.bajo, 2)} – {numero(c.alto, 2)}" if c.bajo != c.alto else numero(c.bajo, 2)), numero(r.valor, 2)
        else:
            guia, real = (f"{numero(c.bajo, 1)} – {numero(c.alto, 1)} %" if c.bajo != c.alto else f"{numero(c.bajo, 1)} %"), f"{numero(r.valor, 1)} %"
        d = x.desvio
        if d is None:
            desvio = Celda("N/A", "", "D", "na", "sin punto medio")
        elif c.unidad == "%":
            desvio = Celda(f"{'+' if d > 0 else ''}{numero(d, 1)} p. p.", "", "D", "negativo" if d < 0 else "valor", "real − punto medio de la guía")
        else:
            v = round(d * 100, 1) + 0.0                     # sin «-0,0 %»
            desvio = Celda(f"{'+' if v > 0 else ''}{numero(v, 1)} %", "", "D", "negativo" if v < 0 else "valor", "(real − punto medio) / punto medio")
        dentro = "punto" if c.bajo == c.alto else ("dentro" if x.dentro else ("por encima" if r.valor > c.alto else "por debajo"))
        glifo = "✓" if x.nota.startswith("✓") or "✓" in x.nota else ("≠" if "≠" in x.nota else "")
        filas.append(FilaCuadro(f"{c.trimestre} · {c.rotulo}", [
            Celda(guia, "", "H", "valor", f"nota del {f_fecha(c.presentado)}: {c.fila}"),
            Celda(real, glifo, "H", "valor", f"nota del {f_fecha(r.presentado)}: {r.fila}" + (f" · {x.nota}" if x.nota else "")),
            desvio, Celda(dentro, "", "D", "negativo" if dentro == "por debajo" else "valor", "")], capa="H"))
    fuente = ("Fuente: SEC EDGAR, notas de resultados (8-K, Ex. 99.1): la guía de cada nota y el real de la nota que publica ese "
              "trimestre; el real GAAP se cuadra con la cifra contrastada de la SEC (sección C) cuando el informe la tiene. Guía confirmada por el analista.")
    return Cuadro(n.siguiente(), "Guía de la compañía frente a lo publicado", ["Guía", "Real", "Desvío", "Frente al rango"], filas,
                  fuente if filas else "Pendiente: sin guía confirmada de trimestres ya publicados.", partible=True)


@dataclass
class Textos:
    descripcion: str = ""
    track_record: List[Dict] = field(default_factory=list)
    asignacion_capital: str = ""
    citas_direccion: List[Dict] = field(default_factory=list)
    de_prueba: bool = False


def alias_doc(clave: str, alias: Optional[Dict[str, str]] = None) -> str:
    """El documento como se cita en el cuerpo (02 › Lenguaje): «8-K 2026-07-29» → «8-K 29/07/2026, Ex. 99.1»."""
    import re
    if alias and clave in alias:
        return alias[clave]
    m = re.fullmatch(r"8-K (\d{4})-(\d\d)-(\d\d)", clave)
    if m:
        return f"8-K {m.group(3)}/{m.group(2)}/{m.group(1)}, Ex. 99.1"
    return clave


def _con_alias(lista: List[Dict], alias: Optional[Dict[str, str]] = None) -> List[Dict]:
    return [dict(c, doc=alias_doc(c.get("doc", ""), alias)) for c in lista]


def textos(e: Entradas, alias: Optional[Dict[str, str]] = None) -> Textos:
    return Textos(descripcion=(e.valor("perfil.descripcion") or {}).get("texto", ""),
                  track_record=[dict(t, evidencias=_con_alias(t.get("evidencias", []), alias)) for t in (e.valor("equipo.track_record") or [])],
                  asignacion_capital=(e.valor("equipo.asignacion_capital") or {}).get("texto", ""),
                  citas_direccion=_con_alias(list(e.valor("direccion.citas") or []), alias), de_prueba=e.de_prueba)


def construir(emisor, hoy: date, facts: Optional[dict], portada=None, entradas: Optional[Entradas] = None, gobierno=None,
              exp=None) -> ParteB:
    """Todo lo de la parte B que no es el gobierno corporativo: segmentos, guía, dividendos, clases de acciones y las
    faltas del paso 4 (entradas del analista verificadas contra el texto de los documentos)."""
    from ..fuentes import calendario, sec
    from .. import entradas as ent
    from ..datos import guia, hechos as hechos_mod, item1a, segmentos as seg_mod, tablas_html
    from ..umbrales import umbral
    pb = ParteB(entradas=entradas or Entradas())
    if getattr(emisor, "mercado", "sec") != "sec":
        return _construir_documental(pb, emisor, hoy, exp)
    anuales = sec.calendario(facts, 12)
    cierre = anuales[-1].fin if anuales else None
    desfase = sec.desfase_fiscal(facts)
    etiqueta = lambda p: hechos_mod.etiqueta_fiscal(p, cierre, desfase)            # noqa: E731
    try:
        pb.segmentos = seg_mod.construir(emisor, pb.entradas.valor("perfil.rotulos") or {}, etiqueta)
        pb.faltas += [f"segmentos: {v}" for v in pb.segmentos.faltan.values()]
    except (RuntimeError, sec.SinContacto) as e:
        pb.faltas.append(f"segmentos: EDGAR no sirvió el 10-K ({fallo(e)})")
    pb.notas, faltan = guia.notas_edgar(emisor)
    pb.faltas += [f"guía · {k}: {v}" for k, v in faltan.items()]
    if pb.notas and pb.notas[-1].candidatos and not (pb.confirmadas & {c.id for c in pb.notas[-1].candidatos}):
        pb.faltas.append("guía: el analista no ha confirmado los candidatos de la última nota de resultados (Cuadro 2)")
    pb.dividendos, pb.dividendos_url = calendario.dividendos(emisor.ticker)
    pb.sorpresas, url_sorpresas = calendario.sorpresas(emisor.ticker)
    if pb.sorpresas:
        # la respuesta literal va a la documentación del 26 (antes la pedía por su cuenta `heredado.historial`)
        from ..fuentes.precio import pedir_crudo
        try:
            _, cuerpo, obtenido = pedir_crudo(url_sorpresas)       # caché por URL y día: no repite la petición
            pb.sorpresas_respuesta = (url_sorpresas, cuerpo, obtenido)
        except Exception:
            pass
    pb.cortos = calendario.cortos(emisor.ticker)
    pb.splits = [(f, r) for f, r, _ in sec.splits(facts)]
    if portada is not None and portada.dei.get("Security12bTitle"):
        pb.clases = [clase_de_accion(portada.dei["Security12bTitle"])]
    textos: Dict[str, str] = {}

    def con_paginas(doc: str, html: str) -> None:
        textos.update({f"{doc}#{k}": v for k, v in tablas_html.folios(tablas_html.paginas(html)).items()})

    if portada is not None:
        textos["10-K"] = portada.texto
        try:
            crudo = sec.descargar_texto(portada.deposito.url)[0]
            con_paginas("10-K", crudo)
            pb.item1a = item1a.leer(crudo, pb.entradas.valor("riesgos.familias") or [])
        except (RuntimeError, sec.SinContacto):
            pass
        if portada.deposito.periodo:
            pb.alias["10-K"] = f"10-K {etiqueta(hechos_mod.Periodo(fin=portada.deposito.periodo, inicio=portada.deposito.periodo.replace(year=portada.deposito.periodo.year - 1)))}"
    p = emisor.ultimo("DEF 14A")
    if p is not None:
        try:
            crudo = sec.descargar_texto(p.url)[0]
            textos["DEF 14A"] = tablas_html.texto_plano(crudo)
            con_paginas("DEF 14A", crudo)
            pb.alias["DEF 14A"] = f"DEF 14A {p.presentado.year}"
        except (RuntimeError, sec.SinContacto):
            pass
    q = emisor.ultimo("10-Q")
    if q is not None:                                  # el trimestre en curso: MD&A, guía y riesgos nuevos
        try:
            crudo = sec.descargar_texto(q.url)[0]
            clave = f"10-Q {q.presentado.isoformat()}"
            textos[clave] = tablas_html.texto_plano(crudo)
            con_paginas(clave, crudo)
            if q.periodo:
                pb.alias[clave] = f"10-Q {etiqueta(hechos_mod.Periodo(fin=q.periodo, inicio=q.periodo - timedelta(days=90)))}"
        except (RuntimeError, sec.SinContacto):
            pass
    for nota in pb.notas:
        textos[f"8-K {nota.presentado.isoformat()}"] = nota.texto
        textos.update({f"8-K {nota.presentado.isoformat()}#{k}": v for k, v in nota.paginas.items()})
    pb.textos = textos
    pb.faltas += ent.comprobar_paso4(pb.entradas, textos, float(umbral("cita_similitud_min")), hoy)
    if pb.entradas.de_prueba:
        pb.faltas.append("entradas de PRUEBA (fixture), no del analista: no se puede emitir con ellas")
    return pb


def _construir_documental(pb: ParteB, emisor, hoy: date, exp) -> ParteB:
    """La parte B de un emisor sin SEC (BME): no hay segmentos XBRL, notas de resultados del 8-K ni calendario de
    Nasdaq; lo que el perfil del emisor no publica lo declara el sistema por puntos como «No aplica». Las citas del
    analista se verifican contra el texto de los documentos oficiales del expediente, página a página
    («<documento>#<página>»), con el mismo `comprobar_paso4` que en EE. UU."""
    from .. import entradas as ent
    from ..umbrales import umbral
    textos: Dict[str, str] = {}
    for a in (exp.adjuntos if exp is not None else []):
        textos[a.nombre] = "\n".join(a.paginas)              # el documento entero, para citas sin página
        for k, texto in enumerate(a.paginas, 1):
            if texto.strip():
                textos[f"{a.nombre}#{k}"] = texto
        pb.alias[a.nombre] = f"{a.tipo.value} {a.periodo_fin:%d/%m/%Y}" if a.periodo_fin else a.tipo.value
    pb.textos = textos
    pb.faltas += ent.comprobar_paso4(pb.entradas, textos, float(umbral("cita_similitud_min")), hoy)
    if pb.entradas.de_prueba:
        pb.faltas.append("entradas de PRUEBA (fixture), no del analista: no se puede emitir con ellas")
    return pb
