"""B3 · Sistema por puntos: el índice declara los puntos de cada apartado, `puntos.evaluar` los deja en cumple · no aplica ·
falta, y la puerta de calidad bloquea por apartado y punto. Sin red: las faltas de las auditorías del 27/09/2026 y un HTML
sintético con los 39 apartados del índice."""

import json
import re
import tempfile
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest

from tesis import qa, render
from tesis.fuentes import emisores
from tesis.plantillas import indice, puntos
from tesis.plantillas.puntos import Estado

RAIZ = Path(__file__).resolve().parents[1]
SALIDA = RAIZ / "datos-tesis" / "salida"
TICKERS = ("AAPL", "NFLX", "ORCL", "QCOM")
HOY = date(2026, 9, 28)
EEUU = emisores.perfil(None)
BME = emisores.perfil(SimpleNamespace(mercado="bme", bolsa="BME Growth", moneda="EUR"))
PRUEBA = "Parte B · entradas de PRUEBA (fixture), no del analista: no se puede emitir con ellas"
# lo que un emisor de BME no tiene y un punto puede pedir (B.md, decisión 6)
PROPIAS_DE_EEUU = {"opciones", "trece_f", "form4", "corto", "consenso"}

# Un apartado que cumple todas sus comprobaciones: texto, un cuadro con filas y un gráfico.
_NORMAL = ('<p>Contenido del apartado.</p><div class="rotulo">Cuadro 1. Datos</div><table><thead><tr><th>Dato</th></tr></thead>'
           '<tbody><tr><td>1</td></tr></tbody></table><svg viewBox="0 0 1 1"></svg>')


def _html(cuerpos=None, arranques=None) -> str:
    """Un informe con las partes y los 39 apartados del índice; `cuerpos` sustituye el de un apartado y `arranques` pone
    texto entre el título de una parte y su primer apartado (lo que hace la maqueta con la fuente de la parte H)."""
    cuerpos, arranques = cuerpos or {}, arranques or {}
    trozos = ["<!-- PORTADA --><section class=\"hoja\"><h1>Informe</h1></section><!-- ÍNDICE --><h2>Índice</h2>"]
    for p in indice.partes():
        trozos.append(f'<section class="hoja"><h2 id="{p.ancla}">{p.letra}. {p.titulo}</h2>{arranques.get(p.letra, "")}')
        trozos += [f'<h3 id="ap-{a.numero}">{a.numero}. {a.titulo}</h3>{cuerpos.get(a.numero, _NORMAL)}' for a in p.apartados]
        trozos.append("</section>")
    return "".join(trozos)


def _informe(faltan=(), emisor=None, discrepancias=()):
    """Lo que la puerta lee de un Informe, sin construirlo."""
    return SimpleNamespace(faltan=list(faltan), discrepancias=list(discrepancias), emisor=emisor, fecha_emision=HOY, avisos=[],
                           numeros={a.clave: a.numero for a in indice.apartados().values()}, recomendacion="",
                           indice=[SimpleNamespace(letra=p.letra) for p in indice.partes()], objetivo_portada=None)


def _por_id(evaluados):
    return {p.id: p for lista in evaluados.values() for p in lista if p.id != str(p.apartado)}


class Indice(unittest.TestCase):
    def test_el_indice_declara_puntos_en_vez_de_bloques(self):
        """Falla si un apartado conserva «bloques» o se queda sin puntos, si un punto repite id o no cuelga de su apartado,
        si pide una capacidad que ningún perfil conoce o una comprobación que no existe, o si «sin_na» no es 06 §3.10."""
        import yaml
        datos = yaml.safe_load(indice.RUTA.read_text(encoding="utf-8"))
        conocidas = set(emisores._SEC) | set(emisores._BME)
        for n, a in datos["apartados"].items():
            self.assertNotIn("bloques", a, n)
            self.assertTrue(a.get("puntos"), n)
        vistos = set()
        for n, a in indice.apartados().items():
            for p in a.puntos:
                self.assertTrue(p.id.startswith(f"{n}.") and p.id not in vistos, p.id)
                vistos.add(p.id)
                self.assertTrue(p.texto.strip(), p.id)
                self.assertLessEqual(set(p.requiere), conocidas, p.id)
                self.assertTrue(not p.comprueba or p.comprueba in puntos.COMPROBACIONES, p.id)
        doce = {2, 3} | set(range(12, 21)) | set(range(27, 31))
        self.assertEqual(indice.sin_na(), doce)
        self.assertEqual(qa._SIN_NA, {str(k) for k in doce})


# De dónde viene cada falta y a qué apartado va (B.md › B3): una por origen, con el texto con que la escribe el programa.
ESPERADO = {
    "Ficha · fundacion: el 10-K no fecha la constitución ni la fundación: la aporta el analista con su cita": 1,
    "Mercado · cierres: el histórico de Nasdaq no respondió": 1,
    "Paso 1 · meta.analista: obligatorio (paso 1)": 1,
    "Parte A · tesis.resumen: falta el texto del analista": 2,
    "Parte A · Párrafo factual del resumen ejecutivo: párrafo de plantilla sin aceptar ni editar (paso 9 del asistente)": 2,
    "Parte B · guía: el analista no ha confirmado los candidatos de la última nota de resultados (Cuadro 2)": 2,
    "Objetivos · tabla: la nota no trae tabla de guía": 2,
    "Linter · revision.parrafos.resumen_factual[5]: cifra sin respaldo «15.437 mln USD»": 2,
    "Parte A · pilares: 0 (se piden 5)": 3,
    "Parte A · pilares[1].riesgo_1a: no es el comienzo de un epígrafe del Item 1A": 3,
    "Linter · pilares[2].argumento: palabra vetada «claramente»": 3,
    "Parte B · segmentos: el 10-K no trae segmentos": 4,
    "Parte B · perfil.descripcion: falta el texto del analista (apartado 4)": 4,
    "Gobierno · accionistas: no se reconoció la tabla de propiedad en la DEF 14A de EDGAR: pídasela al analista con cita": 5,
    "Gobierno · filiales: el índice del último 10-K no incluye el Exhibit 21": 5,
    "Gobierno · ejecutivos: ni el 10-K ni la DEF 14A traen la lista de ejecutivos con edad y cargo reconocible": 6,
    "Gobierno · retribucion: no se reconoció la Summary Compensation Table en la DEF 14A de EDGAR": 6,
    "Gobierno · consejo: no se hallaron fichas de consejeros («Nombre CARGO», «DIRECTOR SINCE», «AGE») en la proxy": 6,
    "Gobierno · retratos: la proxy no trae retrato asociable a: Cristiano R. Amon": 6,
    "Gobierno · traducir cargo «Executive Vice Chair of the Board»": 6,
    "Parte B · equipo.track_record: mínimo CEO y CFO": 6,
    "Parte B · catalizadores: 0 (mínimo 3)": 7,
    "DCF · libro: el analista no ha adjuntado el libro del DCF (--dcf)": 12,
    "Múltiplos · ttm: solo 3 trimestres contrastados: no hay TTM": 17,
    "Mercado · consenso: el consenso de analistas de Nasdaq no respondió": 20,
    "Parte E · mercado.cifras[1]: documento «Presentación de resultados 3T FY26» no disponible para verificar": 21,
    "Parte E · comparables: 2 (entre 3 y 10)": 22,
    "Parte E · competencia.competidores[Apple Inc.]: falta el nombre": 22,
    "Parte E · moat.amenazas: falta el texto del analista (20–80 palabras)": 23,
    "Parte F · riesgos.top[1].origen: «Risks» no es el comienzo de un epígrafe del Item 1A": 24,
    "Parte F · bear.disparadores: 0 (mínimo 3)": 25,
    "Parte F · historial.causas: obligatorias por 2 fallo(s) por encima del umbral": 26,
    "Parte G · pos.argumento: 0 palabras (se piden 80–150)": 27,
    "Parte G · pos.recomendacion: una de Comprar, Mantener, Vender": 27,
    "Parte G · pos.checklist: falta el criterio del analista «Visión propia»": 28,
    "Parte G · pos.precio_entrada: obligatorio, en USD": 29,
    "Parte G · pos.kpis: 0 (mínimo 3)": 30,
    "Parte H · cadena: Nasdaq no sirvió la cadena de opciones: sin conexión": 31,
    "Parte H · iv: la bolsa no publica volatilidad implícita y Yahoo Finance (excepción) no respondió": 32,
    "Parte H · institucional: Nasdaq no sirvió las posiciones institucionales (13F): sin conexión": 33,
    "Parte H · insiders: Nasdaq no sirvió las operaciones de directivos: sin conexión": 34,
    "Parte H · short: Nasdaq no sirvió el interés en corto: sin conexión": 35,
    PRUEBA: 0,                                                   # no es de ningún apartado: sigue bloqueando con su texto
    "Parte H · fuente: la sección F interina lee la web de Nasdaq y WC_PRECIO_FUENTE no es «nasdaq»": 0,   # de toda la parte H
}


class Atribucion(unittest.TestCase):
    def test_a_cada_origen_va_a_su_apartado(self):
        """Falla si una falta de un origen conocido cae en otro apartado que el del plan (B.md › B3) o si una que no es de
        nadie se reparte a un apartado."""
        for falta, n in ESPERADO.items():
            self.assertEqual(indice.apartado_de_falta(falta), n, falta)

    @unittest.skipUnless(all((SALIDA / t / f"{t}_tesis_2026-09-27.auditoria.json").exists() for t in TICKERS),
                         "sin las auditorías del 27/09/2026 en datos-tesis/salida")
    def test_a_las_faltas_de_las_auditorias_no_se_pierden(self):
        """Con las faltas reales de AAPL, NFLX, ORCL y QCOM (27/09/2026): falla si una no cae en un apartado del 1 al 39 o en
        el 0, si con el perfil de EE. UU. alguna deja de bloquear o si una sale en dos líneas de la hoja 0."""
        for t in TICKERS:
            faltan = json.loads((SALIDA / t / f"{t}_tesis_2026-09-27.auditoria.json").read_text(encoding="utf-8"))["faltan"]
            self.assertTrue(faltan, t)
            for f in faltan:
                self.assertIn(indice.apartado_de_falta(f), range(0, 40), f)
            evaluados = puntos.evaluar(_informe(faltan), None, EEUU)
            lineas = puntos.bloqueos(evaluados)
            for f in set(faltan):
                self.assertEqual(len([b for b in lineas if b == f or b.endswith(" · " + f)]), 1, (t, f))
            self.assertGreaterEqual(len(lineas), len(set(faltan)), t)          # el número de bloqueos por faltas no baja
            self.assertFalse([p for lista in evaluados.values() for p in lista if p.estado is Estado.NO_APLICA], t)


class Perfil(unittest.TestCase):
    FALTAN = ["Parte H · cadena: Nasdaq no sirvió la cadena de opciones: sin conexión",
              "Parte H · institucional: Nasdaq no sirvió las posiciones institucionales (13F): sin conexión",
              "Parte H · short: Nasdaq no sirvió el interés en corto: sin conexión",
              "Mercado · consenso: el consenso de analistas de Nasdaq no respondió"]
    NA = '<p class="na">N/A — la bolsa no lo publica para este valor.</p>'

    def _evaluar(self, perfil):
        html = _html({31: self.NA, 32: self.NA, 33: self.NA + "<p>Los titulares de participaciones significativas, en el apartado 5.</p>",
                      35: self.NA})
        return puntos.evaluar(_informe(self.FALTAN), html, perfil, HOY)

    def test_b_lo_que_bme_no_publica_no_aplica_y_no_bloquea(self):
        """Falla si, con el perfil de BME, un punto que pide opciones, 13F, Form 4, interés en corto o consenso no sale «no
        aplica» con el motivo del perfil, si sus faltas bloquean o si se callan (van a los avisos)."""
        evaluados = self._evaluar(BME)
        piden = {p.id: p for a in indice.apartados().values() for p in a.puntos if set(p.requiere) & PROPIAS_DE_EEUU}
        self.assertTrue({"31.1", "33.1", "34.2", "35.1", "20.3", "26.2"} <= set(piden))
        todos = _por_id(evaluados)
        for i, p in piden.items():
            self.assertIs(todos[i].estado, Estado.NO_APLICA, i)
            self.assertEqual(todos[i].motivo, "; ".join(BME.motivo(c) for c in p.requiere if not BME.tiene(c)), i)
            self.assertTrue(todos[i].motivo, i)
        lineas = " | ".join(puntos.bloqueos(evaluados))
        avisos = " | ".join(puntos.cubiertas(evaluados))
        for f in self.FALTAN:
            self.assertNotIn(f, lineas)
            self.assertIn(f, avisos)
        self.assertFalse([b for b in puntos.bloqueos(evaluados) if re.match(r"Apartado (?:3[1235]|20) ", b)], lineas)
        puerta = qa.revisar(_informe(self.FALTAN, SimpleNamespace(mercado="bme", bolsa="BME Growth", moneda="EUR")),
                            _html({31: self.NA, 32: self.NA, 33: self.NA, 35: self.NA}), HOY)
        self.assertEqual(puerta.bloqueos, [])
        self.assertEqual(len([a for a in puerta.avisos if "no aplica (" in a]), len(self.FALTAN))

    def test_b_con_el_perfil_de_eeuu_las_mismas_faltas_bloquean(self):
        """Falla si, con el perfil de EE. UU., esos mismos puntos salen «no aplica» o sus faltas dejan de bloquear."""
        evaluados = self._evaluar(EEUU)
        todos = _por_id(evaluados)
        for i in ("31.1", "33.1", "35.1", "20.3"):
            self.assertIs(todos[i].estado, Estado.FALTA, i)
        self.assertFalse([p for p in todos.values() if p.estado is Estado.NO_APLICA and set(p.faltas)])
        lineas = puntos.bloqueos(evaluados)
        for f in self.FALTAN:
            self.assertEqual(len([b for b in lineas if b.endswith(" · " + f)]), 1, f)
        self.assertIn("Apartado 31 · 31.1, 31.2 · " + self.FALTAN[0], lineas)


class Apartados(unittest.TestCase):
    ARRANQUE_H = ('<p class="muted">Fuente: la bolsa; para la volatilidad implícita, Yahoo Finance como excepción (en este informe '
                  'queda N/A: Yahoo Finance no respondió).</p>')

    def test_c_el_arranque_de_la_parte_h_no_es_del_apartado_30(self):
        """Falla si la fuente de la parte H (que dice «N/A» para la volatilidad implícita) se cuenta en el apartado 30, el
        último de la G, que no admite «N/A» (06 §3.10): bloqueaba NFLX por una línea que no es suya."""
        html = _html(arranques={"H": self.ARRANQUE_H})
        ap = qa.apartados(html)
        self.assertNotIn("Yahoo Finance no respondió", ap["30"])
        self.assertIn("Yahoo Finance no respondió", ap["parte-H"])
        self.assertTrue(ap["30"].startswith("30. ") and ap["31"].startswith("31. "))
        puerta = qa.revisar(_informe(), html, HOY)
        self.assertFalse([b for b in puerta.bloqueos if b.startswith("Apartado 30")], puerta.bloqueos)

    def test_d_pendiente_de_redaccion_bloquea_y_el_adjetivo_no(self):
        """Falla si «Texto pendiente de redacción» (en minúscula) o «PENDIENTE» no bloquean su apartado, o si «pendiente»
        como adjetivo de un criterio del sistema («sin adquisición transformadora pendiente», NFLX 27/09) bloquea."""
        html = _html({5: "<p>Texto pendiente de redacción por el sistema a partir de los adjuntos.</p>" + _NORMAL,
                      9: "<p>PENDIENTE</p>" + _NORMAL,
                      28: _NORMAL + "<table><tr><td>Sin adquisición transformadora pendiente que cambie el perfil de riesgo</td></tr></table>"})
        bloqueos = qa.revisar(_informe(), html, HOY).bloqueos
        self.assertIn("Apartado 5 · queda contenido pendiente", bloqueos)
        self.assertIn("Apartado 9 · queda contenido pendiente", bloqueos)
        self.assertFalse([b for b in bloqueos if b.startswith("Apartado 28")], bloqueos)

    def test_e_apartado_vacio_bloquea(self):
        """Falla si un apartado sin nada debajo de su título (06 §3.10; 01: «nunca vacío») no bloquea, o si uno con solo un
        gráfico se da por vacío."""
        html = _html({38: "", 16: "<p> </p>", 22: "<svg viewBox=\"0 0 1 1\"><text>x</text></svg>"})
        puerta = qa.revisar(_informe(), html, HOY)
        vacio = [b for b in puerta.bloqueos if "apartado vacío" in b]
        self.assertTrue([b for b in vacio if b.startswith("Apartado 38 · ")], puerta.bloqueos)
        self.assertTrue([b for b in vacio if b.startswith("Apartado 16 · ")], puerta.bloqueos)
        self.assertFalse([b for b in vacio if b.startswith("Apartado 22 · ")], puerta.bloqueos)
        fila = next(r for r in puntos.resumen(puerta.puntos) if r["apartado"] == 38)
        self.assertEqual((fila["cumple"], fila["falta"]), (0, len(indice.apartados()[38].puntos)))

    def test_fecha_proxima_anterior_al_informe_bloquea_en_su_punto(self):
        """Falla si una fecha «próxima» anterior a la del informe (06 §3.9) deja de bloquear o sale sin su punto (7.1)."""
        html = _html({7: "<p>Próximos resultados: 01/09/2026 (anunciada).</p>" + _NORMAL})
        self.assertIn("Apartado 7 · 7.1 · Fecha «próxima» anterior al informe: 01/09/2026", qa.revisar(_informe(), html, HOY).bloqueos)


class Puerta(unittest.TestCase):
    def test_bloqueos_por_punto_ordenados_y_sin_duplicados(self):
        """Falla si los bloqueos de las faltas no dicen su apartado y su punto, si no van en el orden del índice, si una falta
        repetida sale dos veces o si los que no son de un apartado (discrepancias, lo no atribuible) cambian de texto."""
        faltan = ["Parte H · short: Nasdaq no sirvió el interés en corto: sin conexión", PRUEBA,
                  "Gobierno · retratos: la proxy no trae retrato asociable a: Ted Sarandos",
                  "Gobierno · retratos: la proxy no trae retrato asociable a: Ted Sarandos",
                  "Ficha · fundacion: el 10-K no fecha la constitución ni la fundación: la aporta el analista con su cita"]
        puerta = qa.revisar(_informe(faltan, discrepancias=["Ingresos FY2025: SEC 1 frente a 2"]), _html(), HOY)
        self.assertEqual(puerta.bloqueos, [
            "Apartado 1 · 1.1 · Ficha · fundacion: el 10-K no fecha la constitución ni la fundación: la aporta el analista con su cita",
            "Apartado 6 · 6.1 · Gobierno · retratos: la proxy no trae retrato asociable a: Ted Sarandos",
            "Apartado 35 · 35.1 · Parte H · short: Nasdaq no sirvió el interés en corto: sin conexión",
            PRUEBA,
            "Discrepancia abierta: Ingresos FY2025: SEC 1 frente a 2"])
        self.assertEqual(sorted(puerta.puntos), list(range(0, 40)))
        self.assertFalse(puerta.emitible)

    def test_el_recuento_de_cada_apartado_es_el_de_su_lista(self):
        """Regla 13: falla si el recuento cumple/no aplica/falta de un apartado no sale de la misma lista de puntos que se
        entrega (a la hoja 0, a la auditoría y a la web)."""
        evaluados = puntos.evaluar(_informe(Perfil.FALTAN + [PRUEBA]), _html({38: ""}), BME, HOY)
        for fila in puntos.resumen(evaluados):
            estados = [p["estado"] for p in fila["puntos"]]
            self.assertEqual((fila["cumple"], fila["no_aplica"], fila["falta"]),
                             (estados.count("cumple"), estados.count("no aplica"), estados.count("falta")), fila["apartado"])
            self.assertTrue(all(p["motivo"] for p in fila["puntos"]), fila["apartado"])     # todo estado con su motivo
        self.assertEqual(next(r for r in puntos.resumen(evaluados) if r["apartado"] == 0)["falta"], 1)


class Emision(unittest.TestCase):
    def test_la_maquetacion_desbordada_no_sale_emitida(self):
        """Falla si un PDF que se desborda al medirlo (un bloqueo que la puerta del HTML no ve) queda con «EMITIDO» en la
        cabecera, sin su línea en la hoja 0 o con un HTML que no es el del PDF final."""
        from tesis.umbrales import umbral
        maximo = int(umbral("paginas_max"))
        impresos = []

        def a_html(informe, casa="Warrants & Co."):
            return f"<html>{'EMITIDO' if informe.emitido else 'BORRADOR'} · {len(informe.bloqueos_qa)} bloqueos</html>"

        def a_pdf(html, salida_pdf, salida_html=None, informe=None, casa="Warrants & Co."):
            impresos.append((html, informe.emitido))
            return "huella"

        for paginas, emitido in ((maximo + 1, None), (maximo, HOY)):
            impresos.clear()
            informe = SimpleNamespace(emitido=None, bloqueos_qa=[], partir=set(), fecha_emision=HOY)
            with mock.patch.object(render, "a_html", a_html), mock.patch.object(render, "a_pdf", a_pdf), \
                    mock.patch.object(qa, "revisar", lambda inf, html, hoy=None: qa.Puerta()), \
                    mock.patch.object(qa, "relleno", lambda pdf: [(k, 1.0, k == paginas) for k in range(1, paginas + 1)]), \
                    mock.patch.object(qa, "paginas_de", lambda pdf: [""] * paginas):
                puerta, _, html, _ = render.emitir(informe, Path(tempfile.gettempdir()) / "desbordada.pdf", HOY)
            self.assertEqual(informe.emitido, emitido, paginas)
            self.assertEqual(informe.bloqueos_qa, puerta.bloqueos, paginas)
            self.assertEqual(impresos[-1], (html, emitido), paginas)          # el último PDF es el del HTML que se devuelve
            if emitido is None:
                self.assertTrue(puerta.bloqueos[0].startswith("Maquetación desbordada"))
                self.assertEqual(html, "<html>BORRADOR · 1 bloqueos</html>")
            else:
                self.assertEqual((puerta.bloqueos, len(impresos)), ([], 1))
