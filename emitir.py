"""Línea de órdenes: del expediente del analista al informe.

    python emitir.py NFLX --adjuntos ruta1.pdf ruta2.pdf … [--carpeta ./adjuntos/NFLX]
                     [--dcf modelo_dcf.xlsx] [--entradas entradas.json]
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

if hasattr(sys.stdout, "reconfigure"):             # una salida sustituida (StringIO de `unittest -b`) no lo tiene
    sys.stdout.reconfigure(encoding="utf-8")

from tesis.verificacion import auditor, contraste, revision  # noqa: E402
from tesis.fuentes import calendario, posicionamiento, precio, sec  # noqa: E402
from tesis.heredado import dcf  # noqa: E402   (el libro del analista; se retira en F15)
from tesis.datos import derivados, expediente, ficha, gobierno, guidance, recortes  # noqa: E402
from tesis import entorno, entradas, render, rotulos  # noqa: E402
from tesis.plantillas import informe, parte_b  # noqa: E402
from tesis.motor import multiplos  # noqa: E402
from tesis.datos.hechos import Contraste  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Tesis de inversión desde el expediente del analista y la SEC.")
    ap.add_argument("ticker")
    ap.add_argument("--adjuntos", nargs="*", default=[], help="rutas de los adjuntos (PDF, XLSX)")
    ap.add_argument("--carpeta", help="carpeta con los adjuntos (se toman todos los PDF y XLSX)")
    ap.add_argument("--dcf", help="libro Excel con el DCF del analista (sección D: apartados 12–20)")
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

    from tesis.fuentes import emisores
    bme = emisores.es_bme(args.ticker)
    print(f"[1/8] Emisor en {'BME' if bme else 'EDGAR'}: {args.ticker}")
    emisor = emisores.emisor(args.ticker)
    if emisor is None:
        print(f"  {args.ticker} no está ni en la SEC ni en BME: sin emisor no hay informe.")
        return 2
    if emisor.mercado == "bme":
        print(f"  {emisor.nombre} · ISIN {emisor.isin} · {emisor.bolsa} · cifras en {emisor.moneda}")
    else:
        print(f"  {emisor.nombre} · CIK {int(emisor.cik)} · {emisor.bolsa} · {len(emisor.depositos)} depósitos recientes")

    print(f"[2/8] Expediente: {len(rutas)} ficheros")
    exp = expediente.cargar(args.ticker, rutas, emisor.depositos)
    for a in exp.adjuntos:
        print(f"  {a.clave:16} {a.tipo.value:40} periodo={a.periodo_fin} fecha={a.fecha} edgar={a.verificado_en_edgar} ({a.certeza.value})")
    for av in exp.avisos:
        print(f"  [{av.gravedad}] {av.texto}")

    if emisor.mercado == "bme":
        # sin SEC: las cifras salen de las cuentas en PDF y se contrastan documento contra documento
        print("[3/8] Sin XBRL: emisor de BME, las cifras salen de las cuentas anuales y semestrales en PDF")
        facts, obtenido = None, None
    else:
        print("[3/8] Hechos XBRL")
        facts, obtenido = sec.companyfacts(emisor.cik)
    try:
        periodos = contraste.periodos_del_informe(exp, facts=facts)
    except ValueError as e:
        print(f"  {e}")
        return 2
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
        portada = sec.portada_10k(emisor) if emisor.mercado == "sec" else None
    except (sec.SinContacto, RuntimeError) as e:
        portada = None
        print(f"  sin el 10-K de EDGAR ({e}): auditor, nombre y propuestas salen del adjunto")
    f = ficha.construir(emisor, exp, portada, facts)
    g = gobierno.construir(exp, carpeta_recortes, emisor)
    for k, v in g.faltan.items():
        print(f"    gobierno · falta {k}: {v}")
    print(f"  retratos: {sum(1 for e in g.ejecutivos if e.foto)} de {len(g.ejecutivos)} ejecutivos · {sum(1 for c in g.consejeros if c.foto)} de {len(g.consejeros)} consejeros")
    gu = guidance.construir(exp, emisor.depositos, hoy)
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
    # F9: riesgos (24), historial (26), comparables (22), tamaño de mercado (21) y regiones (4) salen de la parte B, de
    # las entradas del analista y de los segmentos XBRL; el camino antiguo (`tesis.heredado`) ya no se construye aquí
    modelo = dcf.cargar(Path(args.dcf), salida / f"{nombre_base}.dcf_recalculado.xlsx") if args.dcf else None
    if modelo is not None and modelo.faltan.get("valores"):
        print(f"  DCF: {modelo.faltan['valores']}")
    # el histórico de cierres se pide también para la fecha del precio que el analista tecleó en su libro
    fecha_libro = dcf.fecha_precio_libro(modelo) if modelo is not None else None
    mer = precio.mercado(args.ticker, hoy, (fecha_libro,) if fecha_libro else ())
    pr = mer.precio
    print(f"  precio: {'%.2f %s · ' % (pr.valor, pr.unidad.split('/')[0]) + pr.nota if pr.hay_dato else 'N/A — ' + pr.motivo}")
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
    ultimo_split = max((f for f, _, _ in sec.splits(facts)), default=None) if facts is not None else None
    posi = posicionamiento.construir(args.ticker, split_desde=ultimo_split)
    print("  sección F (bolsa): " + " · ".join(f"{k} {'✓' if getattr(posi, k) is not None else 'N/A'}" for k in ("cadena", "institucional", "insiders", "short"))
          + (f" · IV (Yahoo, excepción) ✓ {len(posi.iv.vencimientos)} vencimientos" if posi.iv is not None else ""))
    for k, v in posi.faltan.items():
        print(f"    pendiente {k}: {v}")
    if posi.insiders is not None and posi.insiders.ultimas:
        # F9: cada operación de directivos de la bolsa, casada con su Form 4 de EDGAR (o el porqué de que no case)
        from tesis.fuentes import form4
        posi.insiders.cruce = form4.cruzar(posi.insiders.ultimas, emisor.depositos)
        print(f"  Form 4: {sum(1 for c in posi.insiders.cruce if c.casado)} de {len(posi.insiders.cruce)} operaciones de directivos casadas con EDGAR")
    agr = None                     # regla 6: Yahoo solo para la volatilidad implícita (sin ROE, deuda ni múltiplos del agregador)
    prox = calendario.proxima(args.ticker, agr, hoy) if emisor.mercado == "sec" else None   # BME no publica calendario
    print("  próxima presentación: " + (f"{prox.fecha:%d/%m/%Y} {prox.momento} ({'esperada' if prox.esperada else 'anunciada'} según la bolsa) · {prox.contraste.value or '—'} {prox.nota_contraste}" if prox else "N/A"))
    acc_portada = f.citas.get("acciones_portada")
    # F3: el motor de valoración. Precio único = cierre oficial de Nasdaq en la fecha de valoración (nunca el intradía)
    ent = entradas.cargar(args.ticker, hoy, Path(args.entradas) if args.entradas else None)
    from tesis.motor import datos as motor_datos, excel as motor_excel
    from tesis.umbrales import _datos as umbrales_todos
    dividendos_bolsa, _ = calendario.dividendos(args.ticker) if emisor.mercado == "sec" else ([], None)
    mot = motor_datos.ejecutar(emisor, facts, hechos, periodos, ent.datos, hoy, acc_portada.valor if acc_portada is not None else None,
                               umbrales_todos(), tab.desfase_fiscal, dividendos_bolsa) if ent.datos.get("esc") else None
    libro_analista = None
    excel_exportado = None
    if mot is not None and mot.precio is not None:
        from tesis.datos.hechos import Capa as _Capa, Origen as _Origen, Periodo as _Periodo, de_valor as _de_valor
        pr = _de_valor("precio", _Periodo.instante(mot.fecha_precio), mot.precio, _Capa.SEC, _Origen(documento="Nasdaq"), unidad="USD/acción",
                       nota=f"cierre oficial de Nasdaq del {mot.fecha_precio:%d/%m/%Y}")
        mot.consenso = mer.consenso
        v = mot.valoracion
        print(f"  motor: precio {mot.precio:.2f} ({mot.fecha_precio:%d/%m/%Y}) · " + (f"WACC {v.wacc.wacc:.2%} · PO {v.po:.2f} a {v.parametros.horizonte_meses} meses · "
              f"{v.recomendacion}" if v else "sin valoración") + (f" · bloqueos: {'; '.join(mot.bloqueos)}" if mot.bloqueos else ""))
        if v is not None:
            ruta_libro = motor_excel.exportar(v, mot.ingresos_base, salida / f"{nombre_base}.motor.xlsx", umbrales_todos())
            import hashlib as _hashlib
            excel_exportado = (ruta_libro.name, _hashlib.sha256(ruta_libro.read_bytes()).hexdigest())
            print(f"  motor: libro con fórmulas vivas en {ruta_libro.name}")
        x = ent.datos.get("excel") or {}
        if x.get("archivo") and Path(x["archivo"]).exists():
            libro_analista = motor_excel.importar(Path(x["archivo"]), x.get("mapa"), Path(x["recalculado"]) if x.get("recalculado") else None)
    elif mot is not None:
        print(f"  motor: {'; '.join(mot.bloqueos)}")
    mult = multiplos.construir(hechos, periodos["trimestres"], periodos["anuales"], pr, acc_portada.valor if acc_portada is not None else None, agr, facts, obtenido,
                               no_aplican=tab.no_aplican)
    print("  múltiplos TTM: " + " · ".join(f"{l.rotulo.split(' (')[0]} {l.valor:.2f}{l.contraste.value}" if l.valor is not None else f"{l.rotulo.split(' (')[0]} N/A" for l in mult.lineas if l.unidad == "x"))
    if modelo is not None:
        cuadres = dcf.cuadrar(modelo, hechos, cierres=mer.cierres, agregador=agr)
        print(f"  DCF: {modelo.nombre} · {len(modelo.supuestos)} supuestos · {len(modelo.escenarios)} escenarios · cuadre: "
              + " · ".join(f"{c.rotulo_modelo[:28]} {c.contraste.value or '—'}" for c in cuadres))
        for k, v in modelo.faltan.items():
            print(f"    falta {k}: {v}")
    pb = parte_b.construir(emisor, hoy, facts, portada, ent, g, exp=exp)
    print(f"  parte B: entradas {'de PRUEBA ' if ent.de_prueba else ''}{ent.ruta or 'sin fichero'} · {len(pb.notas)} notas de resultados · "
          f"{sum(len(n.candidatos) for n in pb.notas)} candidatos de guía ({len(pb.confirmadas)} confirmados) · {len(pb.faltas)} faltas")
    for x in pb.faltas:
        print(f"    falta {x}")

    print("[7/8] Informe")
    inf = informe.construir(args.ticker, hoy, emisor, exp, tab, periodos, f, g, gu, None, pr, recs, modelo_dcf=modelo,
                            riesgos=None, historial=None, salida_recortes=carpeta_recortes, mercado=mer, posicionamiento=posi, comparables=None, mercado_objetivo=None,
                            agregador=agr, multiplos=mult, proxima=prox, parte_b=pb, motor=mot, libro=libro_analista, excel=excel_exportado)
    # 06 §1: las propuestas de plantilla de esta generación, para aceptarlas o editarlas en el paso 9 del asistente
    from tesis.entradas import propuestas
    propuestas.escribir(salida / f"{nombre_base}.propuestas.json", inf.parrafos)
    print("  párrafos de plantilla: " + (" · ".join(f"{x.titulo} ({x.estado})" for x in inf.parrafos) or "ninguno"))
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
    # puerta de calidad (06 §3), «EMITIDO» solo con 0 bloqueos y sin entradas de prueba, y PDF paginado (06 §4)
    puerta, huella, html, medidas = render.emitir(inf, salida / f"{nombre_base}.pdf", hoy, casa=args.casa, prueba=ent.de_prueba)
    import json as _json
    (salida / f"{nombre_base}.auditoria.json").write_text(_json.dumps({
        "ticker": args.ticker.upper(), "fecha": hoy.isoformat(), "emitido": inf.emitido.isoformat() if inf.emitido else None,
        "pdf_sha256": huella, "entradas": {"fichero": str(ent.ruta) if ent.ruta else None, "prueba": ent.de_prueba},
        "bloqueos": puerta.bloqueos, "avisos": puerta.avisos, "faltan": inf.faltan, "discrepancias": inf.discrepancias,
        "solo_sec": inf.solo_sec, "huecos": inf.huecos, "no_son_partidas": dict(tab.no_aplican),
        "fallos_de_las_fuentes": list(rotulos.FALLOS),          # el detalle técnico que el cuerpo dice en español
        "relleno": [{"pagina": k, "ocupado": f, "fin_de_parte": fin} for k, f, fin in medidas],
        "parrafos": [{"id": x.id, "estado": x.estado, "huella": x.huella} for x in inf.parrafos],
        # F10: los campos que el analista confirmó desde una propuesta del sistema, con fuente y huella
        "confirmados_desde_propuesta": {k: v for k, v in (ent.datos.get("_origen") or {}).items() if isinstance(v, dict) and v.get("tipo") == "propuesta"},
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    from tesis.web import saas as _saas                          # cuándo y con qué entradas: lo que no sobrevive a un git clone
    _saas.escribir_emision(args.ticker.upper(), salida / nombre_base)
    print(f"  puerta de calidad: {len(puerta.bloqueos)} bloqueos · {len(puerta.avisos)} avisos · "
          + (f"EMITIDO {inf.emitido:%d/%m/%Y}" if inf.emitido else "BORRADOR (hoja 0 con los bloqueos)"))
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
    if not inf.emitido:
        print(f"\nBORRADOR: {len(puerta.bloqueos)} bloqueos de la puerta de calidad (hoja 0 del PDF y {nombre_base}.auditoria.json)")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
