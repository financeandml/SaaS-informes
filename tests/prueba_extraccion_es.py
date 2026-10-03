"""Cuentas españolas (fase B, 29/09/2026): del PDF oficial de BME a hechos, sin SEC.

Las tres empresas de los informes de ejemplo del analista (Bytetravel, Treelogic y Redegal, BME Growth), con sus cuentas
anuales de 2025 y su último semestral recortados a las páginas de los estados (`tests/fixtures/bme/`). Lo que se afirma:
que el SaaS lee las cifras que publica cada emisor —contrastadas con las del informe de IEAF, que es solo un oráculo de
prueba (`tests/fixtures/lighthouse/`)— y que lo que lee lo lee bien: consolidadas antes que individuales, ninguna tabla
de la memoria tomada por un estado, el 2024 reexpresado de las cuentas de 2025 antes que el del semestral, el segundo
semestre derivado y las partidas del modelo de EE. UU. declaradas ajenas, no huecos.
"""

import unittest
from pathlib import Path

import yaml

from tesis.datos import expediente
from tesis.datos.hechos import Contraste
from tesis.verificacion import contraste

RAIZ = Path(__file__).resolve().parents[1]
BME = RAIZ / "tests" / "fixtures" / "bme"
ORACULO = RAIZ / "tests" / "fixtures" / "lighthouse"
_TAB: dict = {}


def tablero(ticker: str):
    if ticker not in _TAB:
        exp = expediente.cargar(ticker, sorted((BME / ticker).glob("*.pdf")), None)
        periodos = contraste.periodos_del_informe(exp, facts=None)
        _TAB[ticker] = (exp, periodos, contraste.contrastar(exp, None, None, periodos, None))
    return _TAB[ticker]


def hecho(ticker: str, campo: str, clave: str):
    _, periodos, tab = tablero(ticker)
    return next((h for (c, p), h in tab.hechos().items() if c == campo and p.clave == clave), None)


class Oraculo(unittest.TestCase):
    """Falla si una cifra publicada que el SaaS lee de las cuentas oficiales no es la que imprime IEAF (al 0,1)."""

    def _contrastar(self, ticker: str):
        cifras = yaml.safe_load((ORACULO / f"{ticker}.yaml").read_text(encoding="utf-8"))["cifras"]
        for x in cifras:
            h = hecho(ticker, x["campo"], x["periodo"])
            self.assertIsNotNone(h, f"{ticker} {x['campo']} {x['periodo']}: no se lee")
            self.assertTrue(h.hay_dato, f"{ticker} {x['campo']} {x['periodo']}: {h.motivo}")
            self.assertEqual(round(h.valor / 1e6, 1) + 0.0, x["valor"] + 0.0,
                             f"{ticker} {x['campo']} {x['periodo']}: {h.valor} frente a {x['valor']} de IEAF (pág. {x['pagina']})")
            self.assertEqual(h.unidad, "EUR")

    def test_bytetravel(self):
        self._contrastar("BYTE")

    def test_treelogic(self):
        self._contrastar("TRTK")

    def test_redegal(self):
        self._contrastar("RDG")


class Lectura(unittest.TestCase):
    def test_sin_discrepancias_falsas(self):
        """Falla si el comparativo reexpresado (cuentas de 2025, «31/12/2024*») discrepa del semestral anterior en vez de
        mandar el más reciente (03 §3), o si una tabla de la memoria se lee como la partida del estado."""
        for t in ("BYTE", "TRTK", "RDG"):
            _, _, tab = tablero(t)
            self.assertEqual([f"{r.campo.clave} {r.periodo.clave}: {r.nota}" for r in tab.bloquea], [], t)

    def test_reexpresion_manda_el_documento_mas_reciente(self):
        """Falla si el patrimonio de Redegal a 31/12/2024 no sale del comparativo de las cuentas de 2025 con su nota."""
        h = hecho("RDG", "patrimonio", "@2024-12-31")
        self.assertIn("CCAA", h.origen.documento.upper())
        self.assertIn("reexpresado", h.nota)

    def test_explotacion_con_rotulo_cortado(self):
        """Falla si el flujo de explotación de Redegal —rótulo cortado en el propio PDF— no se lee."""
        h = hecho("RDG", "cfo", "FY2025")
        self.assertTrue(h is not None and h.hay_dato)
        self.assertAlmostEqual(h.valor, -662595.23, places=1)

    def test_segundo_semestre_derivado(self):
        """Falla si el 2S no es ejercicio − 1S, marcado como derivado."""
        fy, s1, s2 = (hecho("RDG", "ingresos", k) for k in ("FY2025", "1S25", "2S25"))
        self.assertIs(s2.contraste, Contraste.DERIVADO)
        self.assertAlmostEqual(s2.valor, fy.valor - s1.valor, places=2)

    def test_capex_suma_de_pagos_por_inversiones(self):
        """Falla si el capex no es la suma de las inversiones en inmovilizado intangible y material del estado de flujos,
        o si toma las filas homónimas de «Cobros por desinversiones»."""
        h = hecho("TRTK", "capex", "FY2025")
        self.assertIs(h.contraste, Contraste.DERIVADO)
        self.assertAlmostEqual(h.valor, 486861, places=0)

    def test_partidas_del_modelo_de_eeuu_no_son_huecos(self):
        """Falla si el SG&A o la retribución en acciones salen como dato que falta en unas cuentas españolas (regla 10)."""
        _, _, tab = tablero("TRTK")
        self.assertIn("sga", tab.no_aplican)
        self.assertIn("sbc", tab.no_aplican)
        self.assertNotIn("ingresos", tab.no_aplican)

    def test_consolidadas_antes_que_individuales(self):
        """Falla si en Redegal (trae las dos) los ingresos salen de las individuales (16,62 M) y no del grupo (16,83 M)."""
        self.assertAlmostEqual(hecho("RDG", "ingresos", "FY2025").valor / 1e6, 16.83, places=2)

    def test_individuales_se_dicen(self):
        """Falla si, sin cuentas consolidadas (Treelogic), no se avisa de que las cifras son de la sociedad."""
        _, _, tab = tablero("TRTK")
        self.assertTrue([a for a in tab.avisos if "individuales" in a])

    def test_socios_externos_cierran_el_resultado(self):
        """Falla si en Redegal (grupo con socios externos) «beneficio neto = BAI − impuesto» no cuadra: el beneficio del
        informe es el atribuido a la dominante y la parte de los minoritarios (4.212,68 EUR en 2025, publicada en la
        cuenta de resultados; la del 2S, ejercicio − 1S) tiene que entrar en la identidad."""
        from tesis.verificacion import auditor
        _, periodos, tab = tablero("RDG")
        self.assertAlmostEqual(next(h.valor for (c, p), h in tab.controles.items()
                                    if c == "minoritarios" and p.clave == "FY2025"), -4212.68, places=2)
        a = auditor.auditar({**tab.controles, **tab.hechos()}, periodos["anuales"] + periodos["trimestres"],
                            periodos["instantes"])
        resultado = {c.periodo: c for c in a.comprobaciones if c.identidad == "resultado" and c.estado != "sin datos"}
        for clave in ("FY2025", "2S25"):
            self.assertEqual(resultado[clave].estado, "cuadra", resultado[clave].linea)
            self.assertIn("socios externos", resultado[clave].rotulo)

    def test_comunicaciones_de_bme_con_su_destino(self):
        """Falla si las participaciones significativas o el documento de incorporación que trae BME salen como
        «desconocido · no se usa en el informe»: las participaciones son el accionariado del apartado 5 (regla 13: lo
        que dice la tabla de adjuntos y lo que hace el informe, de la misma fuente)."""
        from tesis.datos import documentos
        from tesis.datos.expediente import Adjunto, Certeza, Tipo, _de_bme
        for clave, tipo in (("participaciones", Tipo.PARTICIPACIONES), ("incorporacion", Tipo.INCORPORACION)):
            a = Adjunto(ruta=Path(f"bme_2026_{clave}.pdf"), huella="", paginas=["Comunicación"], tipo=Tipo.DESCONOCIDO,
                        apartado=None, certeza=Certeza.BAJA, motivo="")
            _de_bme(a, {"clave": clave, "titulo": clave, "publicado": "2026-07-03", "periodo": "", "ejercicio": None})
            self.assertIs(a.tipo, tipo)
            self.assertNotEqual(documentos.destino(a.tipo), documentos.SIN_DESTINO)
        self.assertIn("5 accionariado", documentos.destino(Tipo.PARTICIPACIONES))

    def test_sin_ceros_con_signo(self):
        """Falla si un cero del modelo en Debe/Haber sale como «−0»."""
        for t in ("BYTE", "TRTK", "RDG"):
            _, _, tab = tablero(t)
            for (c, p), h in tab.hechos().items():
                if h.hay_dato and h.valor == 0:
                    self.assertEqual(str(h.valor), "0.0", f"{t} {c} {p.clave}")


if __name__ == "__main__":
    unittest.main()


class RotuloEnVariasLineas(unittest.TestCase):
    """Un rótulo de dos líneas con sus cifras en una tercera: «FLUJOS DE EFECTIVO DE LAS ACTIVIDADES DE» / «EXPLOTACIÓN» /
    «313.340,73 (2.310.057,82)» (cuentas de 2024 de un emisor de BME Growth)."""

    def test_las_cifras_sin_rotulo_toman_el_de_las_lineas_de_encima(self):
        """Falla si la línea de cifras se descarta por no traer rótulo: el flujo de explotación del ejercicio anterior
        quedaba N/A y salía «N/A» en el cuadro 1 del resumen, donde no puede haberlo."""
        from datetime import date
        from tesis.datos.extractor import Linea, Token, _leer_es
        def linea(y, *trozos):
            return Linea([Token(t, x, y, x + 10 * len(t), y + 8) for x, t in trozos])
        lineas = [linea(100, (60, "Nota"), (400, "31/12/2024"), (500, "31/12/2023*")),
                  linea(120, (60, "FLUJOS DE EFECTIVO DE LAS ACTIVIDADES DE")),
                  linea(131, (60, "EXPLOTACIÓN")),
                  linea(142, (400, "313.340,73"), (500, "(2.310.057,82)")),
                  linea(160, (60, "Resultado del ejercicio antes de impuestos"), (400, "(1.764.500,92)"), (500, "(48.064,59)"))]
        p = _leer_es(lineas, 150, "ccaa.pdf", 600, 800, date(2024, 12, 31), 12, "EUR")
        filas = {f.rotulo: f for f in p.filas}
        self.assertIn("FLUJOS DE EFECTIVO DE LAS ACTIVIDADES DE EXPLOTACIÓN", filas)
        valores = sorted(c.valor for c in filas["FLUJOS DE EFECTIVO DE LAS ACTIVIDADES DE EXPLOTACIÓN"].celdas.values())
        self.assertEqual(valores, [-2310057.82, 313340.73])
        self.assertIn("Resultado del ejercicio antes de impuestos", filas)

    def test_el_rotulo_truncado_se_completa_aunque_la_capa_de_texto_entrelace_la_linea_siguiente(self):
        """Falla si «FLUJOS DE EFECTIVO DE LAS ACTIVIDADES DE» no se completa como explotación cuando la capa de texto mezcla
        «EXPLOTACIÓN» con la fila siguiente («EX RPeLsOuTltAadCoIÓ dNel ejercicio antes de impuestos», cuentas de 2024)."""
        from tesis.datos.extractor import Fila, _completar_truncados
        filas = [Fila("FLUJOS DE EFECTIVO DE LAS ACTIVIDADES DE", "", {}, (0, 0, 1, 1)),
                 Fila("EX RPeLsOuTltAadCoIÓ dNel ejercicio antes de impuestos", "", {}, (0, 0, 1, 1))]
        _completar_truncados(filas)
        self.assertEqual(filas[0].rotulo, "FLUJOS DE EFECTIVO DE LAS ACTIVIDADES DE explotación")


class RecompraDelModeloEspanol(unittest.TestCase):
    def test_la_adquisicion_de_acciones_propias_es_la_recompra(self):
        """Falla si «Adquisición de instrumentos de patrimonio propio» del estado de flujos del PGC no se lee como recompra:
        el apartado 10 imprimía N/A para los 557.117 euros que Redegal dedicó a autocartera en 2025."""
        h = hecho("RDG", "recompras", "FY2025")
        self.assertIsNotNone(h)
        self.assertTrue(h.hay_dato, h.motivo)
        self.assertAlmostEqual(abs(h.valor), 557116.82, places=2)


class PartidasDelPGC(unittest.TestCase):
    """Partidas del balance y del estado de flujos del PGC que el informe imprimía N/A teniéndolas el documento
    (cuentas de 2025 de un emisor de BME Growth, 02/10/2026)."""

    def _valor(self, campo, clave):
        h = hecho("RDG", campo, clave)
        self.assertIsNotNone(h)
        self.assertTrue(h.hay_dato, f"{campo} {clave}: {h.motivo}")
        return h.valor

    def test_el_inmovilizado_material_del_balance(self):
        """Falla si «Inmovilizado material» del activo no corriente no se lee (y nunca la fila homónima de los pagos
        por inversiones del estado de flujos, que es otra partida)."""
        self.assertAlmostEqual(self._valor("inmovilizado", "@2025-12-31"), 54168.13, places=2)
        self.assertAlmostEqual(self._valor("inmovilizado", "@2024-12-31"), 59052.78, places=2)

    def test_la_emision_y_la_amortizacion_de_deuda_suman_sus_partes(self):
        """Falla si la emisión y la devolución de deudas del flujo de financiación no se suman de sus partes publicadas:
        el modelo no imprime su total, solo las filas de debajo (entidades de crédito, grupo, otras deudas…)."""
        self.assertAlmostEqual(self._valor("emision_deuda", "FY2025"), 990321.77, places=2)
        self.assertAlmostEqual(abs(self._valor("amortizacion_deuda", "FY2025")), 136213.70 + 853572.22, places=2)
        self.assertAlmostEqual(abs(self._valor("amortizacion_deuda", "FY2024")), 971658.51 + 723016.42 + 658640.98, places=2)

    def test_una_partida_sin_importe_con_el_signo_del_modelo_no_es_un_epigrafe(self):
        """Falla si «Obligaciones y valores similares (-)», sin cifras, se toma por la cabecera de lo que va debajo: las
        deudas devueltas de debajo perdían su bloque («Devolución y amortización de») y no se leían."""
        from datetime import date
        from tesis.datos.extractor import Linea, Token, _leer_es
        def linea(y, *trozos):
            return Linea([Token(t, x, y, x + 10 * len(t), y + 8) for x, t in trozos])
        lineas = [linea(100, (60, "Nota"), (400, "31/12/2025"), (500, "31/12/2024*")),
                  linea(120, (60, "Devolución y amortización de:")),
                  linea(140, (60, "Obligaciones y valores similares (-)")),
                  linea(160, (60, "Deudas con entidades de crédito (-)"), (400, "(136.213,70)"), (500, "(971.658,51)"))]
        p = _leer_es(lineas, 175, "ccaa.pdf", 600, 800, date(2025, 12, 31), 12, "EUR")
        fila = next(f for f in p.filas if f.rotulo.startswith("Deudas con entidades"))
        self.assertTrue(fila.contexto.startswith("Devolución y amortización"), fila.contexto)

    def test_lo_que_sus_estados_no_imprimen_no_es_un_hueco(self):
        """Falla si el BPA de quien no lo imprime en ningún estado (el PGC no lo pide) cuenta como dato que falta: es
        «no es una línea de sus cuentas» (regla 10) y la fila sale del cuadro, no una de N/A."""
        _, _, tab = tablero("RDG")
        for clave in ("bpa_basico", "bpa_diluido", "acciones_diluidas"):
            self.assertIn(clave, tab.no_aplican)
        # la compra de negocios: «Unidad de negocio» solo está entre los cobros por desinversiones, que es otra partida
        self.assertIn("adquisiciones", tab.no_aplican)
        # lo que sí imprime y se lee no se declara ajeno
        self.assertNotIn("inmovilizado", tab.no_aplican)

    def test_sin_estados_leidos_nada_se_declara_ajeno(self):
        """Falla si, con unas cuentas de las que el lector no reconoce ningún estado (escaneadas, otro modelo), las partidas
        se dan por «no es una línea de sus cuentas»: el hueco es del lector y tiene que verse como N/A."""
        from tesis.verificacion.contraste import _no_lo_imprimen_sus_estados
        _, _, tab = tablero("RDG")
        huecos = [r for r in tab.resultados if r.campo.clave == "ingresos"]
        vacios = [type(r)(r.campo, r.periodo, r.hecho.con(contraste=Contraste.HUECO), r.sec, [], [], None) for r in huecos]
        self.assertEqual(_no_lo_imprimen_sus_estados(vacios, {}, {}), {})
