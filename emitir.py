"""Línea de órdenes: del expediente del analista al informe.

    python emitir.py NFLX --adjuntos ruta1.pdf ruta2.pdf … [--carpeta ./adjuntos/NFLX]
                     [--dcf modelo_dcf.xlsx] [--posicion posiciones/NFLX.json]
                     [--decisiones decisiones_nflx.json] [--fecha 2026-09-16] [--salida ./salida]

Pasos, en el orden de la tubería: emisor en EDGAR → expediente clasificado y en
orden cronológico → hechos XBRL → extracción con coordenadas → contraste campo ×
periodo → recortes de evidencia → ficha, gobierno, objetivos, regiones → informe →
HTML y PDF. Deja en
`salida/` el PDF, el HTML autocontenido, los recortes y un registro de contraste
(`.contraste.txt`) que es el cuaderno del generador, no del cliente.

Sin IA en tiempo de ejecución: los textos de la tesis los escribe el analista y el
sistema los verifica (docs/fases).

Exige `WC_SEC_CONTACTO` (entorno o `.env`). Sin cotización configurada
(`WC_PRECIO_FUENTE`), todo lo que depende del precio sale N/A y el informe lo dice.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

from tesis import (agregador, auditor, calendario, comparables, contraste, dcf, derivados, entorno, entradas, expediente, ficha, gobierno, guidance, historial, informe,  # noqa: E402
                   mercado_objetivo, multiplos, parte_b, posicion, posicionamiento, precio, recortes, regiones, render, revision, riesgos, sec)
from tesis.hechos import Contraste  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Tesis de inversión desde el expediente del analista y la SEC.")
    ap.add_argument("ticker")
    ap.add_argument("--adjuntos", nargs="*", default=[], help="rutas de los adjuntos (PDF, XLSX)")
    ap.add_argument("--carpeta", help="carpeta con los adjuntos (se toman todos los PDF y XLSX)")
    ap.add_argument("--dcf", help="libro Excel con el DCF del analista (sección D: apartados 12–20)")
    ap.add_argument("--posicion", help="JSON con la posición y la tesis del analista (sección H); por defecto posiciones/<TICKER>.json si existe "
                                       "(se rellena con «python -m tesis.formulario TICKER»)")
    ap.add_argument("--decisiones", help="JSON con las decisiones del analista sobre discrepancias")
    ap.add_argument("--entradas", help="JSON con las entradas del analista (04_entradas.yaml); por defecto <datos>/entradas/<TICKER>/<fecha>/entradas.json")
    ap.add_argument("--fecha", help="fecha de emisión (AAAA-MM-DD); por defecto, hoy")
    ap.add_argument("--salida", default=str(entorno.carpeta("salida")))
    ap.add_argument("--casa", default="Warrants & Co.")
    args = ap.parse_args(argv)

    hoy = date.fromisoformat(args.fecha) if args.fecha else date.today()
    rutas = [Path(r) for r in args.adjuntos]
    if args.carpeta:
        rutas += sorted(p for p in Path(args.carpeta).iterdir() if p.suffix.lower() in (".pdf", ".xlsx", ".xlsm"))
    if not rutas:
        ap.error("hacen falta adjuntos (--adjuntos o --carpeta)")

    print(f"[1/8] Emisor en EDGAR: {args.ticker}")
    emisor = sec.emisor(args.ticker)
    if emisor is None:
        print(f"  {args.ticker} no presenta ante la SEC: las empresas fuera de EE. UU. quedan fuera de esta versión.")
        return 2
    print(f"  {emisor.nombre} · CIK {int(emisor.cik)} · {emisor.bolsa} · {len(emisor.depositos)} depósitos recientes")

    print(f"[2/8] Expediente: {len(rutas)} ficheros")
    exp = expediente.cargar(args.ticker, rutas, emisor.depositos)
    for a in exp.adjuntos:
        print(f"  {a.clave:16} {a.tipo.value:40} periodo={a.periodo_fin} fecha={a.fecha} edgar={a.verificado_en_edgar} ({a.certeza.value})")
    for av in exp.avisos:
        print(f"  [{av.gravedad}] {av.texto}")

    print("[3/8] Hechos XBRL")
    facts, obtenido = sec.companyfacts(emisor.cik)
    periodos = contraste.periodos_del_informe(exp, facts=facts)
    print(f"  ejercicios {[p.clave for p in periodos['anuales']]} · trimestres {[p.clave for p in periodos['trimestres']]}")

    print("[4/8] Extracción y contraste")
    tab = contraste.contrastar(exp, facts, obtenido, periodos, Path(args.decisiones) if args.decisiones else None)
    print("  " + " · ".join(f"{k} {v}" for k, v in tab.resumen.items()))
    for clave, motivo in tab.no_aplican.items():
        print(f"    no aplica · {clave}: {motivo}")

    salida = Path(args.salida)
    salida.mkdir(parents=True, exist_ok=True)
    nombre_base = f"{args.ticker.upper()}_tesis_{hoy.isoformat()}"
    print("[5/8] Recortes de evidencia")
    recs = recortes.recortar_evidencias(exp, tab, salida / f"{nombre_base}_recortes")
    print(f"  {len(recs)} recortes: " + ", ".join(f"{k[0]} p{k[1]}" for k in sorted(recs)))

    print("[6/8] Ficha, gobierno (con retratos), objetivos, regiones, riesgos, historial, precio, DCF, posición")
    carpeta_recortes = salida / f"{nombre_base}_recortes"
    try:
        portada = sec.portada_10k(emisor)
    except (sec.SinContacto, RuntimeError) as e:
        portada = None
        print(f"  sin el 10-K de EDGAR ({e}): auditor, nombre y propuestas salen del adjunto")
    f = ficha.construir(emisor, exp, portada, facts)
    g = gobierno.construir(exp, carpeta_recortes, emisor)
    for k, v in g.faltan.items():
        print(f"    gobierno · falta {k}: {v}")
    print(f"  retratos: {sum(1 for e in g.ejecutivos if e.foto)} de {len(g.ejecutivos)} ejecutivos · {sum(1 for c in g.consejeros if c.foto)} de {len(g.consejeros)} consejeros")
    gu = guidance.construir(exp, emisor.depositos, hoy)
    reg = regiones.construir(exp, tab)
    flujos, instantes = periodos["anuales"] + periodos["trimestres"], periodos["instantes"]
    hechos = derivados.calcular(tab.hechos(), flujos, instantes)
    # auditoría: que las cifras cuadren entre ellas, no solo con su fuente. Lo que falte y la identidad determine se
    # despeja y entra marcado como derivado; lo despejado puede alimentar a su vez otros derivados, así que se recalculan.
    aud = auditor.auditar(hechos, flujos, instantes)
    if aud.derivadas:
        hechos = derivados.calcular(auditor.aplicar(hechos, aud), flujos, instantes)
    r = aud.resumen
    print(f"  auditoría de datos: {r['cuadra']} identidades cuadran · {r['no cuadra']} no cuadran · "
          f"{r['derivada']} despejadas de su identidad · {r['sin datos']} sin datos suficientes")
    for c in aud.contradicciones:
        print("    " + c.linea)
    (salida / f"{nombre_base}.auditoria.txt").write_text(
        f"Auditoría de datos {args.ticker.upper()} {hoy.isoformat()} · " + " · ".join(f"{k} {v}" for k, v in r.items())
        + "\n\n" + aud.como_texto() + "\n", encoding="utf-8")
    ri = riesgos.construir(exp)
    print(f"  riesgos: {len(ri.riesgos)} epígrafes del Item 1A" + (f" (págs. {ri.paginas[0]}–{ri.paginas[1]})" if ri.riesgos else f" — {ri.faltan}"))
    # historial: la tabla de la transcripción, las cartas anteriores depositadas en la SEC y la serie de la bolsa
    hi = historial.construir(exp, hechos, cik=emisor.cik, ticker=args.ticker, splits=[(f, x) for f, x, _ in sec.splits(facts)])
    print(f"  historial: {len(hi.sorpresas)} sorpresas de consenso (transcripción) · {len(hi.frases_guia)} frases de guía frente a real · "
          f"{len(hi.cartas)} cartas de EDGAR → {len(hi.guias)} previsiones frente a real · {len(hi.bolsa)} trimestres de consenso según la bolsa")
    for k, v in hi.faltan.items():
        print(f"    falta {k}: {v}")
    modelo = dcf.cargar(Path(args.dcf), salida / f"{nombre_base}.dcf_recalculado.xlsx") if args.dcf else None
    if modelo is not None and modelo.faltan.get("valores"):
        print(f"  DCF: {modelo.faltan['valores']}")
    # el histórico de cierres se pide también para la fecha del precio que el analista tecleó en su libro
    fecha_libro = dcf.fecha_precio_libro(modelo) if modelo is not None else None
    mer = precio.mercado(args.ticker, hoy, (fecha_libro,) if fecha_libro else ())
    pr = mer.precio
    print(f"  precio: {'%.2f USD · ' % pr.valor + pr.nota if pr.hay_dato else 'N/A — ' + pr.motivo}")
    if mer.cotizacion is not None:
        c = mer.cotizacion
        print(f"  mercado: sesión {c.sesion or '?'} · cierre anterior {c.cierre_anterior} · cap. publicada {c.cap_mercado_fuente} · 52 s {c.rango_52s} · 1Y target {c.objetivo_consenso}"
              f" · cierres pedidos {len(mer.cierres)}" + (f" · {mer.contraste_cierre[0].value} {mer.contraste_cierre[1]}" if mer.contraste_cierre else ""))
    for k, v in mer.faltan.items():
        print(f"    falta {k}: {v}")
    if mer.consenso is not None:
        print(f"  consenso de la bolsa: {mer.consenso.objetivo} USD · {mer.consenso.analistas} analistas · rango {mer.consenso.bajo}–{mer.consenso.alto}"
              + (f" · {mer.contraste_consenso[0].value} {mer.contraste_consenso[1]}" if mer.contraste_consenso else ""))
    # F interina: lo que publica la bolsa; la serie de short interest empieza tras el último split que la SEC registra
    ultimo_split = max((f for f, _, _ in sec.splits(facts)), default=None)
    posi = posicionamiento.construir(args.ticker, split_desde=ultimo_split)
    print("  sección F (bolsa): " + " · ".join(f"{k} {'✓' if getattr(posi, k) is not None else 'N/A'}" for k in ("cadena", "institucional", "insiders", "short"))
          + (f" · IV (Yahoo, excepción) ✓ {len(posi.iv.vencimientos)} vencimientos" if posi.iv is not None else ""))
    for k, v in posi.faltan.items():
        print(f"    pendiente {k}: {v}")
    comp = comparables.construir(args.ticker)
    print(f"  comparables (industria de la bolsa «{comp.industria}»): " + ", ".join(f"{x.ticker}{' ✓' if x.ingresos is not None else ' sin cuentas'}" for x in comp.filas[1:]) if comp.filas else "  comparables: N/A")
    for k, v in comp.faltan.items():
        print(f"    falta {k}: {v}")
    merc = mercado_objetivo.construir(exp, hechos)
    print(f"  tamaño de mercado: {len(merc.declaraciones)} cifras declaradas por la compañía"
          + (f" · faltan {list(merc.faltan)}" if merc.faltan else "")
          + (f" · {len(merc.no_aplican)} conceptos de otro sector, no se cuentan como huecos" if merc.no_aplican else ""))
    # el agregador (Yahoo Finance) solo para lo que ni la SEC ni la bolsa publican, y para cuadrar
    agr = agregador.resumen(args.ticker)
    _o = lambda v, f="{}": f.format(v) if v is not None else "N/A"        # el agregador puede omitir cualquier campo
    print("  agregador: " + (f"ROE {_o(agr.roe, '{:.2%}')} · ROA {_o(agr.roa, '{:.2%}')} · deuda total {_o(agr.deuda_total and agr.deuda_total / 1e6, '{:,.0f}')} M · EV/EBITDA {_o(agr.ev_ebitda)} · PEG {_o(agr.peg)} · resultados {_o(agr.fecha_resultados)}"
                             if agr is not None else "sin respuesta (todo lo que dependa de él sale N/A)"))
    prox = calendario.proxima(args.ticker, agr, hoy)
    print("  próxima presentación: " + (f"{prox.fecha:%d/%m/%Y} {prox.momento} ({'esperada' if prox.esperada else 'anunciada'} según la bolsa) · {prox.contraste.value or '—'} {prox.nota_contraste}" if prox else "N/A"))
    acc_portada = f.citas.get("acciones_portada")
    mult = multiplos.construir(hechos, periodos["trimestres"], periodos["anuales"], pr, acc_portada.valor if acc_portada is not None else None, agr, facts, obtenido)
    print("  múltiplos TTM: " + " · ".join(f"{l.rotulo.split(' (')[0]} {l.valor:.2f}{l.contraste.value}" if l.valor is not None else f"{l.rotulo.split(' (')[0]} N/A" for l in mult.lineas if l.unidad == "x"))
    if modelo is not None:
        cuadres = dcf.cuadrar(modelo, hechos, cierres=mer.cierres, agregador=agr)
        print(f"  DCF: {modelo.nombre} · {len(modelo.supuestos)} supuestos · {len(modelo.escenarios)} escenarios · cuadre: "
              + " · ".join(f"{c.rotulo_modelo[:28]} {c.contraste.value or '—'}" for c in cuadres))
        for k, v in modelo.faltan.items():
            print(f"    falta {k}: {v}")
    ruta_posicion = Path(args.posicion) if args.posicion else Path("posiciones") / f"{args.ticker.upper()}.json"
    pos = posicion.cargar(ruta_posicion) if ruta_posicion.exists() else None
    if pos is not None:
        print(f"  posición: {ruta_posicion} · {len(pos.faltan())} campos sin rellenar")
    else:
        print(f"  posición: sin {ruta_posicion} (la sección H y la recomendación de la portada salen N/A; se rellena con «python -m tesis.formulario {args.ticker.upper()}»)")

    ent = entradas.cargar(args.ticker, hoy, Path(args.entradas) if args.entradas else None)
    pb = parte_b.construir(emisor, hoy, facts, portada, ent, g)
    print(f"  parte B: entradas {'de PRUEBA ' if ent.de_prueba else ''}{ent.ruta or 'sin fichero'} · {len(pb.notas)} notas de resultados · "
          f"{sum(len(n.candidatos) for n in pb.notas)} candidatos de guía ({len(pb.confirmadas)} confirmados) · {len(pb.faltas)} faltas")
    for x in pb.faltas:
        print(f"    falta {x}")

    print("[7/8] Informe")
    inf = informe.construir(args.ticker, hoy, emisor, exp, tab, periodos, f, g, gu, reg, pr, recs, modelo_dcf=modelo, posicion=pos,
                            riesgos=ri, historial=hi, salida_recortes=carpeta_recortes, mercado=mer, posicionamiento=posi, comparables=comp, mercado_objetivo=merc,
                            agregador=agr, multiplos=mult, proxima=prox, parte_b=pb)
    n_evid = sum(len(lista) for _, _, lista in inf.documentacion)
    print(f"  documentación complementaria: {n_evid} piezas en {len(inf.documentacion)} apartados · {len(recs)} recortes de estados junto a sus cuadros · "
          f"{len([x for x in inf.fotos_ejecutivos + inf.fotos_consejo if x.ruta])} retratos")

    print("[8/8] Doble comprobación, HTML y PDF")
    html = render.a_html(inf, casa=args.casa)
    # segunda lectura independiente de cada cifra impresa: los hechos y el libro se vuelven a formatear y se comparan con el HTML
    rev = revision.comprobar(inf, html, modelo)
    print(f"  doble comprobación: {rev.comprobadas} cifras releídas · {len(rev.desacuerdos)} desacuerdos")
    for d in rev.desacuerdos:
        print(f"    ≠ {d}")
    if rev.desacuerdos:
        print("  EMISIÓN DETENIDA: hay cifras impresas que no coinciden con su fuente al releerlas.")
        return 3
    huella = render.a_pdf(html, salida / f"{nombre_base}.pdf", informe=inf, casa=args.casa)
    registro = salida / f"{nombre_base}.contraste.txt"
    with registro.open("w", encoding="utf-8") as fh:
        fh.write(f"Contraste {args.ticker.upper()} {hoy.isoformat()} · resumen {tab.resumen}\n\n")
        for r in tab.resultados:
            v = f"{r.hecho.valor:,.2f}" if r.hecho.valor is not None else "N/A"
            fh.write(f"{r.hecho.contraste.value or ' ':2} {r.campo.clave:22} {r.periodo.clave:12} {v:>22}  {r.nota or r.hecho.motivo or r.hecho.nota}\n")
    print(f"  {salida / (nombre_base + '.pdf')} · sha256 {huella[:16]}")
    print(f"  {registro}")
    bloqueos = tab.bloquea
    if bloqueos:
        print(f"\nBORRADOR: {len(bloqueos)} discrepancias sin decidir bloquean la emisión:")
        for r in bloqueos:
            print(f"  ≠ {r.campo.rotulo} {r.periodo.clave}: {r.nota}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
