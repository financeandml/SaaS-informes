"""La cotización de la bolsa (Nasdaq) y los tres fallos del informe del 17/09/2026: fundación, accionistas, call.

Sin red: la web de Nasdaq se sustituye por las tres respuestas JSON que devolvió el 17/09/2026
a las 13:11 ET, guardadas aquí tal cual. Cada prueba dice qué defecto reintroducido la hace fallar.
"""

import json
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

from tests import contacto_sec_de_prueba, hay_cache_sec, rutas_nflx
from tesis.heredado import dcf
from tesis.datos import expediente, ficha, gobierno, guidance
from tesis.plantillas import informe, secciones
from tesis.fuentes import precio, sec
from tesis.datos.hechos import Contraste

RUTAS = rutas_nflx()
CARPETA = Path(json.loads((Path(__file__).parent / "expediente_nflx.json").read_text(encoding="utf-8"))["carpeta"])
DCF_NFLX = CARPETA / "Modelo_DCF_NFLX_Warrants_Co_2026-09-15.xlsx"

INFO = {"data": {"symbol": "NFLX", "primaryData": {"lastSalePrice": "$75.71", "lastTradeTimestamp": "Sep 17, 2026 12:57 PM ET", "volume": "12,316,261.942111"},
                 "marketStatus": "Open", "keyStats": {"fiftyTwoWeekHighLow": {"label": "52 Week Range:", "value": "65.08 - 124.86"}}}}
RESUMEN = {"data": {"summaryData": {"OneYrTarget": {"value": "$94.50"}, "AverageVolume": {"value": "35,559,146"}, "PreviousClose": {"value": "$76.41"},
                                    "MarketCap": {"value": "315,293,512,267"}, "AnnualizedDividend": {"value": "N/A"}}}}
HISTORICO = {"data": {"tradesTable": {"rows": [{"date": "09/16/2026", "close": "$76.41"}, {"date": "09/15/2026", "close": "$77.90"},
                                               {"date": "09/14/2026", "close": "$80.32"}, {"date": "09/11/2026", "close": "$77.40"}]}}}
ANALISTAS = {"data": {"consensusOverview": {"lowPriceTarget": 70.0, "highPriceTarget": 135.0, "priceTarget": 95.82, "buy": 25, "sell": 0, "hold": 7},
                      "historicalConsensus": [{"z": {"date": "09/01/2026"}, "y": 95.82}]}}


def _nasdaq_falso(url: str, cabeceras: dict) -> dict:
    if "/info?" in url:
        return INFO
    if "/summary?" in url:
        return RESUMEN
    if "/historical?" in url:
        return HISTORICO
    if "/targetprice" in url:
        return ANALISTAS
    raise AssertionError(url)


class MercadoNasdaq(unittest.TestCase):
    def setUp(self):
        self.parches = [mock.patch.object(precio, "_json", _nasdaq_falso), mock.patch.object(precio, "variable", lambda n: "nasdaq" if n == "WC_PRECIO_FUENTE" else "")]
        for p in self.parches:
            p.start()

    def tearDown(self):
        for p in self.parches:
            p.stop()

    def test_precio_con_sesion_abierta_y_cierre_contrastado(self):
        """Falla si el precio intradía se rotula «cierre», si el cierre anterior no se cuadra con el histórico
        de la propia bolsa, o si el histórico no trae la fecha que el analista tecleó en su libro."""
        m = precio.mercado("NFLX", date(2026, 9, 17), (date(2026, 9, 14),))
        self.assertTrue(m.precio.hay_dato)
        self.assertAlmostEqual(m.precio.valor, 75.71)
        self.assertIn("sesión abierta", m.precio.nota)
        self.assertIn("12:57 PM ET", m.precio.nota)
        self.assertNotIn("cierre del", m.precio.nota)
        self.assertEqual(m.contraste_cierre[0], Contraste.CONFIRMADO)
        self.assertEqual(m.cierres[date(2026, 9, 14)], 80.32)
        self.assertEqual(m.cotizacion.rango_52s, (65.08, 124.86))
        self.assertEqual(m.cotizacion.cap_mercado_fuente, 315_293_512_267.0)
        self.assertEqual(m.cotizacion.objetivo_consenso, 94.5)
        # la misma bolsa publica dos consensos distintos (ficha 94,50 · analistas 95,82): el informe lo marca ≠
        self.assertEqual(m.consenso.objetivo, 95.82)
        self.assertEqual(m.contraste_consenso[0], Contraste.DISCREPANTE)
        self.assertEqual(m.faltan, {})

    def test_fuera_de_sesion_el_precio_es_el_cierre_oficial(self):
        """Falla si en After-Hours el informe toma el cruce extrabursátil de primaryData (75,41 a las 17:04) como precio
        en vez del cierre oficial de secondaryData (75,31, «Closed at … 4:00 PM ET»), o si el volumen de la sesión se pierde."""
        despues = {"data": {"symbol": "NFLX", "marketStatus": "After-Hours",
                            "primaryData": {"lastSalePrice": "$75.4137", "lastTradeTimestamp": "Sep 17, 2026 5:04 PM ET", "volume": "27,806,508.49"},
                            "secondaryData": {"lastSalePrice": "$75.31", "lastTradeTimestamp": "Closed at Sep 17, 2026 4:00 PM ET", "volume": ""},
                            "keyStats": {"fiftyTwoWeekHighLow": {"value": "65.08 - 124.86"}}}}
        with mock.patch.dict(INFO, despues):
            m = precio.mercado("NFLX", date(2026, 9, 17))
        self.assertAlmostEqual(m.precio.valor, 75.31)
        self.assertIn("cierre del 17/09/2026", m.precio.nota)
        self.assertIn("75,41", m.precio.nota)
        self.assertEqual(m.cotizacion.fuera_de_sesion, (75.4137, "5:04 PM ET"))
        self.assertAlmostEqual(m.cotizacion.volumen, 27_806_508.49)
        self.assertTrue(m.cotizacion.es_cierre)

    def test_cierre_anterior_discrepante_no_se_da_por_bueno(self):
        """Falla si la ficha y el histórico de Nasdaq dicen cierres distintos y el sistema no lo marca ≠."""
        with mock.patch.dict(RESUMEN["data"]["summaryData"], {"PreviousClose": {"value": "$77.00"}}):
            m = precio.mercado("NFLX", date(2026, 9, 17))
        self.assertEqual(m.contraste_cierre[0], Contraste.DISCREPANTE)

    def test_precio_de_otro_dia_es_na(self):
        """Falla si un precio que no es del día de emisión (ni del último día de mercado anterior) se imprime."""
        m = precio.mercado("NFLX", date(2026, 9, 25))
        self.assertFalse(m.precio.hay_dato)
        self.assertIn("no del día de emisión", m.precio.motivo)

    def test_na_de_nasdaq_no_es_cero(self):
        """Falla si un «N/A» de la ficha de Nasdaq (dividendo) se convierte en 0 o rompe la lectura."""
        self.assertIsNone(precio._num("N/A"))
        self.assertIsNone(precio._num(""))
        self.assertEqual(precio._num("$1,234.5"), 1234.5)

    @unittest.skipUnless(DCF_NFLX.exists(), "sin libro del DCF de NFLX")
    def test_cuadre_del_precio_del_libro_con_el_cierre_oficial(self):
        """Falla si el precio que el analista tecleó (80,32 «cierre del 14/09/2026») no se cuadra con el cierre
        oficial de esa fecha, o si un cierre distinto pasa por ✓, o si sin histórico se inventa un resultado."""
        m = dcf.cargar(DCF_NFLX)
        self.assertEqual(dcf.fecha_precio_libro(m), date(2026, 9, 14))
        c = next(c for c in dcf.cuadrar(m, {}, cierres={date(2026, 9, 14): 80.32}) if c.campo == "precio")
        self.assertEqual(c.contraste, Contraste.CONFIRMADO)
        c = next(c for c in dcf.cuadrar(m, {}, cierres={date(2026, 9, 14): 79.00}) if c.campo == "precio")
        self.assertEqual(c.contraste, Contraste.DISCREPANTE)
        c = next(c for c in dcf.cuadrar(m, {}, cierres={}) if c.campo == "precio")
        self.assertEqual(c.contraste, Contraste.HUECO)

    @unittest.skipUnless(DCF_NFLX.exists(), "sin libro del DCF de NFLX")
    def test_recorrido_sobre_cotizacion_oficial_es_derivado_con_formula(self):
        """Falla si la columna «sobre cotización oficial» del cuadro 20 no sale de valor / cotización − 1 con la fórmula
        impresa, o si se rellena sin cotización."""
        m = dcf.cargar(DCF_NFLX)
        mer = precio.mercado("NFLX", date(2026, 9, 17))
        cuadros = secciones.cuadros_dcf(informe.Cuadros(), m, [], mer.precio, mer)
        objetivo = cuadros["objetivo"]
        self.assertEqual(objetivo.columnas[-1], "Sobre cotización oficial")
        fila = next(f for f in objetivo.filas if f.rotulo.lower().startswith("precio objetivo del inversor"))
        self.assertEqual(fila.celdas[-1].texto, "32,1 %")          # 100 / 75,71 − 1
        self.assertEqual(fila.celdas[-1].glifo, "∑")
        self.assertIn("100,00 / 75,71", fila.celdas[-1].nota)
        self.assertTrue(any("1 Year Target" in f.rotulo for f in objetivo.filas))
        sin_precio = secciones.cuadros_dcf(informe.Cuadros(), m, [], None, None)["objetivo"]
        fila = next(f for f in sin_precio.filas if f.rotulo.lower().startswith("precio objetivo del inversor"))
        self.assertEqual(fila.celdas[-1].texto, "N/A")


@unittest.skipUnless(RUTAS, "sin expediente de NFLX")
class ArreglosDel17(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        contacto_sec_de_prueba()
        cls.exp = expediente.cargar("NFLX", RUTAS)

    @unittest.skipUnless(hay_cache_sec(), "sin caché de la SEC")
    def test_fundacion_y_acciones_de_la_portada_mas_reciente(self):
        """Falla si la fundación vuelve a buscarse solo en el Item 1 (está en la nota 1, pág. 47) o si las acciones
        en circulación se toman del 10-K (4.222 mln, 31/12/2025) en vez de la portada del último 10-Q."""
        f = ficha.construir(sec.emisor("NFLX"), self.exp)
        self.assertEqual(int(f.citas["fundacion"].valor), 1997)
        self.assertEqual(f.citas["fundacion"].origen.pagina, 47)
        self.assertIn("incorporated on August 29, 1997", f.citas["fundacion"].texto)
        acc = f.citas["acciones_portada"]
        self.assertEqual(acc.origen.formulario, "10-Q")
        self.assertEqual(acc.fecha, date(2026, 6, 30))
        self.assertEqual(acc.valor, 4_163_939_676.0)

    def test_accionistas_fila_sin_porcentaje_y_sin_ceros(self):
        """Falla si la fila de Clete Willems (sin porcentaje en la proxy) arrastra la fila del grupo, si «sin
        porcentaje» se confunde con «< 1 %», o si 151.211 acciones se imprimen como «0»."""
        g = gobierno.construir(self.exp)
        por_nombre = {a.nombre: a for a in g.accionistas}
        self.assertEqual(len(g.accionistas), 20)
        self.assertEqual(por_nombre["Clete Willems"].acciones, 6168.0)
        self.assertIsNone(por_nombre["Clete Willems"].porcentaje)
        self.assertIn("no imprime el porcentaje", por_nombre["Clete Willems"].nota)
        self.assertEqual(por_nombre["Anne M. Sweeney"].nota, "menos del 1 %")
        grupo = por_nombre["All current directors and executive officers as a group (16 persons)"]
        self.assertEqual((grupo.acciones, grupo.porcentaje), (52_413_364.0, 1.24))
        cuadro = informe._cuadros_gobierno(informe.Cuadros(), g)[0]
        celdas = {f.rotulo: f.celdas for f in cuadro.filas}
        self.assertEqual(celdas["Richard N. Barton"][0].texto, "151.211")
        self.assertEqual(celdas["Clete Willems"][1].texto, "N/A")
        self.assertEqual(celdas["Clete Willems"][1].clase, "na")
        self.assertEqual(celdas["Anne M. Sweeney"][1].texto, "< 1 %")

    def test_call_un_analista_que_dice_we_expect_no_es_la_direccion(self):
        """Falla si se cita como previsión de la compañía una frase de un analista (la transcripción lo lista
        bajo ANALYSTS) o una frase de quien habla antes de que la transcripción diga quién es."""
        from types import SimpleNamespace
        paginas = [
            "COPYRIGHT S&P Global Market Intelligence Estimates\nCONSENSUS ACTUAL SURPRISE",
            "Contents\nCall Participants 3\nPresentation 4",
            "Call Participants\nEXECUTIVES\nAna Directora\nChief Financial Officer\nANALYSTS\nBernardo Analista\nBanco Ejemplo, Research Division\n",
            "Presentation\nWe expect nothing said before a name to count as anything at all.\nAna Directora\nChief Financial Officer\n"
            "We expect revenue growth of 10% for the full year.\nBernardo Analista\nBanco Ejemplo, Research Division\n"
            "We expect you to raise the guidance for the second half, is that fair?\nSo we expect margins to compress, right.\n",
        ]
        falso = SimpleNamespace(paginas=paginas, nombre="call_falsa.pdf", tipo=expediente.Tipo.CALL, fecha=date(2026, 7, 16))
        ejecutivos, analistas = guidance._participantes(falso)
        self.assertEqual(list(ejecutivos), ["Ana Directora"])
        self.assertEqual(list(analistas), ["Bernardo Analista"])
        g = guidance.Guidance()
        guidance._call(falso, g)
        self.assertEqual([c.texto for c in g.citas_call], ["We expect revenue growth of 10% for the full year."])
        self.assertTrue(g.citas_call[0].nota.startswith("Ana Directora (Chief Financial Officer)"))

    def test_call_solo_ejecutivos_y_nunca_preguntas(self):
        """Falla si vuelven a citarse como «lo que dijo la dirección» las preguntas de analistas que lee el
        moderador, o si una frase de previsión de un ejecutivo (Neumann, «We're guiding…») deja de leerse."""
        call = next(a for a in self.exp.adjuntos if a.tipo is expediente.Tipo.CALL)
        ejecutivos, _ = guidance._participantes(call)
        self.assertEqual(set(ejecutivos), {"Gregory K. Peters", "Spencer Wang", "Spencer Adam Neumann", "Theodore A. Sarandos"})
        g = guidance.Guidance()
        guidance._call(call, g)
        self.assertGreaterEqual(len(g.citas_call), 4)
        for c in g.citas_call:
            self.assertTrue(any(c.nota.startswith(n) for n in ejecutivos), c.nota)
            self.assertNotRegex(c.texto, r"\bquestion\b")
            self.assertFalse(c.texto.startswith("What"), c.texto)
        self.assertTrue(any(c.texto.startswith("We're guiding") and c.nota.startswith("Spencer Adam Neumann") for c in g.citas_call))


if __name__ == "__main__":
    unittest.main()
