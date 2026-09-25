"""Sección F interina y consenso de la bolsa: lectura de las respuestas de Nasdaq (guardadas del 17/09/2026) sin red.

Cada prueba dice qué defecto reintroducido la hace fallar.
"""

import json
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path
from unittest import mock

from tests import rutas_nflx
from tesis.plantillas import informe, secciones
from tesis.fuentes import posicionamiento, precio
from tesis.datos.hechos import Contraste

RUTAS = rutas_nflx()

CADENA = {"data": {"totalRecord": 5, "lastTrade": "LAST TRADE: $75.66 (AS OF SEP 17, 2026 1:46 PM ET)", "table": {"rows": [
    {"expirygroup": "September 18, 2026", "expiryDate": None, "strike": None},
    {"expirygroup": "", "expiryDate": "Sep 18", "c_Volume": "100", "c_Openinterest": "1,000", "strike": "70.00", "p_Volume": "50", "p_Openinterest": "--"},
    {"expirygroup": "", "expiryDate": "Sep 18", "c_Volume": "--", "c_Openinterest": "500", "strike": "75.00", "p_Volume": "150", "p_Openinterest": "2,000"},
    {"expirygroup": "October 16, 2026", "expiryDate": None, "strike": None},
    {"expirygroup": "", "expiryDate": "Oct 16", "c_Volume": "10", "c_Openinterest": "20", "strike": "80.00", "p_Volume": "30", "p_Openinterest": "40"},
    {"expirygroup": "January 15, 2027", "expiryDate": None, "strike": None},
    {"expirygroup": "", "expiryDate": "Jan 15", "c_Volume": "--", "c_Openinterest": "--", "strike": "90.00", "p_Volume": "--", "p_Openinterest": "--"},
]}}}
SHORT = {"data": {"shortInterestTable": {"rows": [
    {"settlementDate": "08/31/2026", "interest": "91,476,621", "avgDailyShareVolume": "27,650,849", "daysToCover": 3.308275},
    {"settlementDate": "11/28/2025", "interest": "75,214,504", "avgDailyShareVolume": "35,126,358", "daysToCover": 2.141255},
    {"settlementDate": "11/14/2025", "interest": "14,650,481", "avgDailyShareVolume": "4,001,995", "daysToCover": 3.660794},
]}}}
INST = {"data": {"ownershipSummary": {"SharesOutstandingPCT": {"label": "Institutional Ownership", "value": "91.60%"}},
                 "activePositions": {"rows": [{"positions": "Total Institutional Shares", "holders": "3,952", "shares": "3,814,186,622"}]},
                 "newSoldOutPositions": {"rows": []},
                 "holdingsTransactions": {"table": {"rows": [{"ownerName": "Vanguard Group Inc", "date": "12/31/2025", "sharesHeld": "390,014,981", "sharesChange": "4,801,761", "sharesChangePCT": "1.247%"}]}}}}
INSIDERS = {"data": {"numberOfTrades": {"rows": [{"insiderTrade": "Number of Sells", "months3": "14", "months12": "70"}]},
                     "numberOfSharesTraded": {"rows": [{"insiderTrade": "Net Activity", "months3": "(251,785)", "months12": "(3,755,911)"}]},
                     "transactionTable": {"totalRecords": "343", "table": {"rows": [
                         {"insider": "BARTON RICHARD N", "relation": "Director", "lastDate": "9/10/2026", "transactionType": "Automatic Sell", "sharesTraded": "720", "lastPrice": "$75.27"}]}}}}
ANALISTAS = {"data": {"consensusOverview": {"lowPriceTarget": 70.0, "highPriceTarget": 135.0, "priceTarget": 95.82, "buy": 25, "sell": 0, "hold": 7},
                      "historicalConsensus": [{"z": {"date": "08/01/2026"}, "y": 71.71}, {"z": {"date": "09/01/2026"}, "y": 95.82}]}}


def _nasdaq_falso(url: str, cabeceras: dict) -> dict:
    for patron, datos in (("/option-chain?", CADENA), ("/short-interest?", SHORT), ("/institutional-holdings?", INST), ("/insider-trades?", INSIDERS), ("/targetprice", ANALISTAS)):
        if patron in url:
            precio._CRUDOS[url] = (json.dumps(datos), datetime(2026, 9, 17, 19, 55))
            return datos
    raise AssertionError(url)


YAHOO = {"optionChain": {"result": [{"quote": {"regularMarketPrice": 75.31, "regularMarketTime": 1789675200}, "expirationDates": [1789689600, 1792108800],
                                     "options": [{"expirationDate": 1789689600,
                                                  "calls": [{"strike": 75.0, "impliedVolatility": 0.258, "bid": 1.0, "openInterest": 1000},
                                                            {"strike": 83.0, "impliedVolatility": 2.9, "bid": 0.0, "openInterest": 0},
                                                            {"strike": 84.0, "impliedVolatility": 0.516, "bid": 0.1, "openInterest": 400},
                                                            {"strike": 246.0, "impliedVolatility": 6.4, "bid": 0.0, "openInterest": 26}],
                                                  "puts": [{"strike": 75.0, "impliedVolatility": 0.229, "bid": 1.0, "openInterest": 500},
                                                           {"strike": 68.0, "impliedVolatility": 0.531, "bid": 0.1, "openInterest": 1574},
                                                           {"strike": 20.0, "impliedVolatility": 0.0, "bid": 0.0, "openInterest": 0}]}]}]}}
YAHOO_2 = {"optionChain": {"result": [{"options": [{"expirationDate": 1792108800, "calls": [{"strike": 75.0, "impliedVolatility": 0.30, "bid": 1.0, "openInterest": 25}],
                                                    "puts": [{"strike": 75.0, "impliedVolatility": 0.28, "bid": 1.0, "openInterest": 25}]}]}]}}


class _YahooFalso:
    def __init__(self):
        self.crudos = {}

    def json(self, url):
        datos = YAHOO_2 if "date=" in url else YAHOO
        self.crudos[url] = (json.dumps(datos), datetime(2026, 9, 17, 20, 30))
        return datos


class SeccionF(unittest.TestCase):
    def setUp(self):
        from tesis.fuentes import yahoo
        self.parches = [mock.patch.object(precio, "_json", _nasdaq_falso), mock.patch.object(precio, "variable", lambda n: "nasdaq" if n == "WC_PRECIO_FUENTE" else ""),
                        mock.patch.object(yahoo, "cliente", lambda: _YahooFalso())]
        for p in self.parches:
            p.start()

    def tearDown(self):
        for p in self.parches:
            p.stop()

    def test_cadena_agrega_por_vencimiento_y_un_guion_no_es_cero(self):
        """Falla si la fila de cabecera de un vencimiento se cuenta como strike, si «--» se suma como 0 en vez de
        no sumarse, o si el put/call deja de ser un derivado con fórmula."""
        p = posicionamiento.construir("NFLX", split_desde=date(2025, 11, 14))
        c = p.cadena
        self.assertEqual([v.fecha for v in c.vencimientos], ["September 18, 2026", "October 16, 2026", "January 15, 2027"])
        self.assertIsNone(c.vencimientos[2].vol_calls)          # todo «--»: no hay dato, que no es cero
        sep = c.vencimientos[0]
        self.assertEqual((sep.contratos, sep.vol_calls, sep.vol_puts, sep.oi_calls, sep.oi_puts), (2, 100.0, 200.0, 1500.0, 2000.0))
        cuadros = secciones.cuadros_f(informe.Cuadros(), p, acciones_circulacion=4_163_939_676.0)
        fila = cuadros["cadena"].filas[0]
        self.assertEqual(fila.celdas[2].texto, "2,00")          # 200 puts / 100 calls
        self.assertEqual(fila.celdas[2].glifo, "∑")
        self.assertIn("200 / 100", fila.celdas[2].nota)
        self.assertEqual(cuadros["cadena"].filas[2].celdas[0].texto, "N/A")
        total = cuadros["cadena"].filas[-1]
        self.assertTrue(total.rotulo.startswith("Total (3 vencimientos)"))
        self.assertEqual(total.celdas[0].texto, "110")

    def test_short_interest_empieza_despues_del_split(self):
        """Falla si la serie mezcla la liquidación del día del split (14,6 M acciones de antes del 10:1) con las de
        después, o si el % del capital deja de salir de las acciones de la portada del 10-Q con su fórmula."""
        p = posicionamiento.construir("NFLX", split_desde=date(2025, 11, 14))
        self.assertEqual([f[0] for f in p.short.filas], [date(2026, 8, 31), date(2025, 11, 28)])
        cuadro = secciones.cuadros_f(informe.Cuadros(), p, acciones_circulacion=4_163_939_676.0)["short"]
        self.assertEqual(cuadro.filas[0].celdas[3].texto, "2,20 %")
        self.assertEqual(cuadro.filas[0].celdas[3].glifo, "∑")
        sin_acciones = secciones.cuadros_f(informe.Cuadros(), p, acciones_circulacion=None)["short"]
        self.assertEqual(sin_acciones.filas[0].celdas[3].texto, "N/A")

    def test_insiders_e_institucional_con_signo_y_fecha(self):
        """Falla si «(251,785)» no se lee como negativo, si la fecha de cada 13F se pierde, o si el nombre del insider
        no se normaliza."""
        p = posicionamiento.construir("NFLX")
        self.assertEqual(p.insiders.acciones[0][1], -251_785.0)
        self.assertEqual(p.insiders.ultimas[0][0], "Barton Richard N")
        self.assertEqual(p.insiders.total_operaciones, 343)
        self.assertEqual(p.institucional.mayores[0][1], date(2025, 12, 31))
        self.assertEqual(p.institucional.mayores[0][4], 1.247)
        self.assertIsNotNone(p.iv)                # la IV entra por la excepción de Yahoo; sweeps y dark pool ya no están en el índice
        self.assertEqual(p.faltan, {})

    def test_sin_fuente_nasdaq_no_se_pide_nada(self):
        """Falla si con otra fuente de cotización la sección F sale rellena de Nasdaq igualmente."""
        with mock.patch.object(precio, "variable", lambda n: "polygon"):
            p = posicionamiento.construir("NFLX")
        self.assertIsNone(p.cadena)
        self.assertIn("fuente", p.faltan)

    def test_consenso_de_la_bolsa_con_recuento_y_rango(self):
        """Falla si el consenso pierde el recuento de recomendaciones, el rango o el mes del último punto."""
        c = precio.consenso_nasdaq("NFLX")
        self.assertEqual((c.objetivo, c.bajo, c.alto, c.analistas, c.mes), (95.82, 70.0, 135.0, 32, date(2026, 9, 1)))

    def test_volcado_api_guarda_el_cuerpo_y_su_huella(self):
        """Falla si la evidencia de una API deja de guardar el cuerpo completo junto a la imagen o si el pie no
        dice que no es una captura de pantalla."""
        from tesis.datos.recortes import volcado_api
        import hashlib
        with tempfile.TemporaryDirectory() as d:
            cuerpo = json.dumps(SHORT)
            rec = volcado_api("https://api.nasdaq.com/x", cuerpo, datetime(2026, 9, 17, 19, 55), Path(d), "prueba", "rótulo", "Nasdaq")
            self.assertTrue(rec.ruta.exists())
            self.assertEqual((Path(d) / "api_prueba.json").read_text(encoding="utf-8"), cuerpo)
            self.assertIn(hashlib.sha256(cuerpo.encode("utf-8")).hexdigest()[:16], rec.pie)
            self.assertIn("no es captura de pantalla", rec.pie)
            self.assertEqual(rec.pagina, 0)


# ---------------------------------------------------------------------------
# IV (excepción Yahoo), comparables (screener + SEC) y tamaño de mercado (documentos)
# ---------------------------------------------------------------------------

class VolatilidadImplicitaYahoo(unittest.TestCase):
    def setUp(self):
        from tesis.fuentes import yahoo
        self.parches = [mock.patch.object(precio, "_json", _nasdaq_falso), mock.patch.object(precio, "variable", lambda n: "nasdaq" if n == "WC_PRECIO_FUENTE" else ""),
                        mock.patch.object(yahoo, "cliente", lambda: _YahooFalso())]
        for p in self.parches:
            p.start()

    def tearDown(self):
        for p in self.parches:
            p.stop()

    def test_iv_atm_y_fuera_del_dinero_con_sesgo_y_contraste_de_oi(self):
        """Falla si el ATM no es el strike más cercano al subyacente, si un contrato sin mercado (strike 83, IV 2,9, bid 0 y
        OI 0) entra en el cálculo, si el sesgo deja de ser put 90 % − call 110 %, si el OI del agregador no se cuadra con la bolsa,
        o si la IV de un vencimiento cuyo OI no cuadra con la bolsa se imprime igualmente."""
        p = posicionamiento.construir("NFLX")
        v = p.iv
        self.assertEqual(len(v.vencimientos), 2)
        x = v.vencimientos[0]
        self.assertEqual((x.strike_atm, x.iv_call_atm, x.iv_put_atm), (75.0, 0.258, 0.229))
        self.assertEqual((x.strike_put_otm, x.strike_call_otm), (68.0, 84.0))
        self.assertAlmostEqual(x.sesgo, 0.531 - 0.516)
        self.assertEqual((x.oi_calls, x.oi_puts), (1426.0, 2074.0))
        # la bolsa (CADENA) tiene para el 18/09/2026 OI 1.500 + 2.000 = 3.500 y el agregador 3.500 → cuadra y la IV se imprime
        self.assertEqual(x.contraste_oi[0], Contraste.CONFIRMADO)
        self.assertEqual(x.fecha, date(2026, 9, 18))
        # el 16/10/2026 la bolsa tiene 60 y el agregador 50 (16,7 %): no cuadra y la IV de ese vencimiento no se imprime
        y = v.vencimientos[1]
        self.assertEqual(y.contraste_oi[0], Contraste.DISCREPANTE)
        self.assertFalse(y.hay_iv)
        self.assertIn("no cuadra", y.motivo)
        self.assertIn("Yahoo", v.fuente)
        cuadro = secciones.cuadro_iv(informe.Cuadros(), p)
        fila = cuadro.filas[0]
        self.assertEqual(fila.celdas[5].glifo, "∑")
        self.assertIn("53,1", fila.celdas[5].nota)
        self.assertEqual(fila.celdas[6].texto, "sí")                  # F7: un solo ratio put/call (el de la cadena)
        self.assertEqual(cuadro.filas[1].celdas[6].texto, "no")
        self.assertEqual(cuadro.filas[1].celdas[1].texto, "N/A")
        self.assertIn("no cuadra", cuadro.filas[1].celdas[1].nota)

    def test_cadena_a_medio_cargar_no_da_iv(self):
        """Falla si una cadena con bid y ask a cero e interés abierto a cero (lo que el agregador devuelve fuera de sesión)
        produce alguna IV, o si la sección no dice por qué la IV es N/A."""
        from tesis.fuentes import yahoo
        vacia = {"optionChain": {"result": [{"quote": {"regularMarketPrice": 75.31, "regularMarketTime": 1789675200}, "expirationDates": [1789689600],
                                             "options": [{"expirationDate": 1789689600,
                                                          "calls": [{"strike": 75.0, "impliedVolatility": 0.0625, "bid": 0.0, "ask": 0.0, "openInterest": 0, "volume": 3893},
                                                                    {"strike": 82.0, "impliedVolatility": 0.5, "bid": 0.0, "ask": 0.0, "openInterest": 0, "volume": 3430}],
                                                          "puts": [{"strike": 75.0, "impliedVolatility": 1e-5, "bid": 0.0, "ask": 0.0, "openInterest": 0, "volume": 18801},
                                                                   {"strike": 68.0, "impliedVolatility": 0.25, "bid": 0.0, "ask": 0.0, "openInterest": 0, "volume": 1}]}]}]}}

        class _Vacio(_YahooFalso):
            def json(self, url):
                self.crudos[url] = (json.dumps(vacia), datetime(2026, 9, 18, 9, 8))
                return vacia
        with mock.patch.object(yahoo, "cliente", lambda: _Vacio()):
            p = posicionamiento.construir("NFLX")
        self.assertIsNotNone(p.iv)
        self.assertFalse(any(x.hay_iv for x in p.iv.vencimientos))
        self.assertIn("iv", p.faltan)
        self.assertIsNone(secciones.cuadro_iv(informe.Cuadros(), p))

    def test_sin_excepcion_yahoo_la_iv_es_na_con_motivo(self):
        """Falla si sin la excepción autorizada la IV se rellena igualmente o el motivo desaparece."""
        p = posicionamiento.construir("NFLX", con_iv=False)
        self.assertIsNone(p.iv)
        self.assertIn("no se pidió la excepción", p.faltan["iv"])


SCREENER = {"data": {"rows": [
    {"symbol": "NFLX", "name": "Netflix Inc. Common Stock", "lastsale": "$75.31", "marketCap": "313586297000.00", "country": "United States", "industry": "Consumer Electronics/Video Chains", "sector": "Consumer Discretionary"},
    {"symbol": "BBY", "name": "Best Buy Co. Inc. Common Stock", "lastsale": "$94.56", "marketCap": "19831851123.00", "country": "United States", "industry": "Consumer Electronics/Video Chains", "sector": "Consumer Discretionary"},
    {"symbol": "IQ", "name": "iQIYI Inc.", "lastsale": "$1.10", "marketCap": "1061527209.00", "country": "China", "industry": "Consumer Electronics/Video Chains", "sector": "Consumer Discretionary"},
    {"symbol": "AMZN", "name": "Amazon.com", "lastsale": "$251.19", "marketCap": "2709414106151", "country": "United States", "industry": "Catalog/Specialty Distribution", "sector": "Consumer Discretionary"},
]}}
FACTS = {
    "0001065280": {"facts": {"us-gaap": {"Revenues": {"units": {"USD": [{"form": "10-K", "fp": "FY", "start": "2025-10-01", "end": "2025-12-31", "val": 12000000000},
                                                                          {"form": "10-K", "fp": "FY", "start": "2025-01-01", "end": "2025-12-31", "val": 45183036000},
                                                                          {"form": "10-Q", "fp": "Q2", "start": "2026-04-01", "end": "2026-06-30", "val": 12560000000}]}},
                                         "NetIncomeLoss": {"units": {"USD": [{"form": "10-K", "fp": "FY", "start": "2025-01-01", "end": "2025-12-31", "val": 10981201000}]}}}}},
    "0000764478": {"facts": {"us-gaap": {"Revenues": {"units": {"USD": [{"form": "10-K", "fp": "FY", "start": "2025-02-02", "end": "2026-01-31", "val": 41691000000}]}},
                                         "NetIncomeLoss": {"units": {"USD": [{"form": "10-K", "fp": "FY", "start": "2025-02-02", "end": "2026-01-31", "val": 1069000000}]}}}}},
    "0001722608": {"facts": {"us-gaap": {"Revenues": {"units": {"CNY": [{"form": "20-F", "fp": "FY", "start": "2025-01-01", "end": "2025-12-31", "val": 27291300000}]}},
                                         "NetIncomeLoss": {"units": {"CNY": [{"form": "20-F", "fp": "FY", "start": "2025-01-01", "end": "2025-12-31", "val": -206311000}]}}}}},
}
CIKS = {"NFLX": ("0001065280", "NETFLIX INC"), "BBY": ("0000764478", "BEST BUY CO INC"), "IQ": ("0001722608", "iQIYI, Inc.")}


class ComparablesDeLaBolsa(unittest.TestCase):
    def setUp(self):
        from tesis.heredado import comparables
        from tesis.fuentes import sec

        def _json_screener(url, cabeceras):
            if "/screener/" in url:
                precio._CRUDOS[url] = (json.dumps(SCREENER), datetime(2026, 9, 17, 20, 30))
                return SCREENER
            return _nasdaq_falso(url, cabeceras)
        self.parches = [mock.patch.object(precio, "_json", _json_screener), mock.patch.object(precio, "variable", lambda n: "nasdaq" if n == "WC_PRECIO_FUENTE" else ""),
                        mock.patch.object(sec, "cik_de", lambda t: CIKS.get(t.upper())), mock.patch.object(sec, "companyfacts", lambda cik, refrescar=False: (FACTS[cik], date(2026, 9, 17)))]
        for p in self.parches:
            p.start()
        self.comparables = comparables

    def tearDown(self):
        for p in self.parches:
            p.stop()

    def test_misma_industria_con_multiplos_solo_en_usd(self):
        """Falla si entran valores de otra industria (AMZN), si la propia compañía no va primero, si el último ejercicio
        anual se confunde con el trimestre que el 10-K también etiqueta «FY» (companyfacts lo hace), o si se divide
        una capitalización en USD por cuentas en CNY."""
        c = self.comparables.construir("NFLX")
        self.assertEqual(c.industria, "Consumer Electronics/Video Chains")
        self.assertEqual([x.ticker for x in c.filas], ["NFLX", "BBY", "IQ"])
        nflx, bby, iq = c.filas
        self.assertEqual((nflx.ingresos, nflx.cierre, nflx.formulario), (45183036000.0, date(2025, 12, 31), "10-K"))
        self.assertAlmostEqual(nflx.per, 313586297000.0 / 10981201000.0)
        self.assertAlmostEqual(bby.p_ventas, 19831851123.0 / 41691000000.0)
        self.assertEqual((iq.moneda, iq.p_ventas, iq.per), ("CNY", None, None))
        self.assertIn("CNY", iq.nota_sec)
        cuadro = secciones.cuadros_comparables(informe.Cuadros(), c)
        self.assertTrue(cuadro.filas[0].destacada)
        self.assertEqual(cuadro.filas[2].celdas[4].texto, "N/A")          # IQ: P/Ventas
        self.assertEqual(cuadro.filas[1].celdas[5].glifo, "∑")            # BBY: PER derivado con fórmula
        self.assertEqual(c.faltan, {})


@unittest.skipUnless(RUTAS, "sin expediente de NFLX")
class TamanoDeMercado(unittest.TestCase):
    def test_declaraciones_de_la_compania_clasificadas(self):
        """Falla si las cifras de la call (800 M hogares, 670.000 M USD, 45 %, 7 %, 5 %) o de la proxy (325 M suscripciones)
        dejan de leerse literales con su página, o si la clasificación TAM/SAM/SOM pierde su motivo."""
        from tesis.datos import expediente as exp_mod
        from tesis.heredado import mercado_objetivo
        exp = exp_mod.cargar("NFLX", RUTAS)
        m = mercado_objetivo.construir(exp)
        por = {d.concepto: d for d in m.declaraciones}
        self.assertEqual((por["Hogares direccionables"].valor, por["Hogares direccionables"].clase), (800e6, "TAM"))
        self.assertEqual((por["Ingresos direccionables"].valor, por["Ingresos direccionables"].clase), (670e9, "SAM"))
        self.assertEqual(por["Cuota del mercado de ingresos direccionable"].valor, 7.0)
        self.assertEqual(por["Suscripciones de pago"].valor, 325e6)
        self.assertEqual(por["Hogares direccionables"].cita.origen.pagina, 5)
        self.assertTrue(all(d.motivo for d in m.declaraciones))
        self.assertIn("addressable households", por["Hogares direccionables"].cita.texto)
        cuadro = secciones.cuadro_mercado_objetivo(informe.Cuadros(), m)
        self.assertEqual(cuadro.filas[0].celdas[0].texto, "TAM")
        self.assertEqual(cuadro.filas[0].celdas[1].texto, "800 M hogares")


    def test_un_concepto_de_otro_sector_no_es_un_hueco_de_la_compania(self):
        """Falla si a una empresa de bases de datos se le apunta como «falta» la cuota de visionado de televisión: el
        informe de Oracle listaba siete conceptos del vocabulario de Netflix como si fueran huecos suyos (22/09/2026).
        Y falla si, cuando la dirección sí usa el término pero sin cifra, deja de contarse como hueco."""
        from datetime import date

        from tesis.datos import expediente as exp_mod
        from tesis.heredado import mercado_objetivo
        from tesis.datos.hechos import Certeza

        def _exp(texto):
            a = exp_mod.Adjunto(ruta=Path("call.pdf"), huella="h", paginas=[texto], tipo=exp_mod.Tipo.CALL,
                                apartado=exp_mod.APARTADO_DE[exp_mod.Tipo.CALL], certeza=Certeza.ALTA, motivo="",
                                periodo_fin=date(2026, 8, 31), fecha=date(2026, 9, 10))
            return exp_mod.Expediente(ticker="ORCL", adjuntos=[a])

        m = mercado_objetivo.construir(_exp("Cloud revenue grew 28% and RPO reached $455 billion."))
        self.assertIn("Cuota de visionado de televisión", m.no_aplican)
        self.assertNotIn("Cuota de visionado de televisión", m.faltan)
        self.assertIn("TAM", m.faltan)          # el mercado total sí se echa en falta siempre: es del índice
        m = mercado_objetivo.construir(_exp("We keep expanding our addressable households, though we do not size it."))
        self.assertIn("Hogares direccionables", m.faltan)
        self.assertNotIn("Hogares direccionables", m.no_aplican)


class IVSinStrike(unittest.TestCase):
    def test_una_iv_sin_su_strike_no_tumba_la_emision(self):
        """Falla si el cuadro de IV se cae cuando el agregador da la volatilidad y no el strike: la emisión entera de
        Qualcomm se detuvo por la nota al pie de una celda («unsupported format string passed to NoneType»)."""
        x = posicionamiento.IVVencimiento(fecha=date(2026, 10, 16), subyacente=172.5, strike_atm=None,
                                          iv_call_atm=0.31, iv_put_atm=0.33, strike_put_otm=None, iv_put_otm=0.38,
                                          strike_call_otm=None, iv_call_otm=0.29, oi_calls=100.0, oi_puts=80.0)
        p = posicionamiento.Posicionamiento(iv=posicionamiento.VolatilidadImplicita(vencimientos=[x]))
        cuadro = secciones.cuadro_iv(informe.Cuadros(), p)
        fila = cuadro.filas[0]
        self.assertEqual(fila.celdas[1].texto, "31,0 %")
        self.assertIn("sin precio de ejercicio", fila.celdas[1].nota)
        self.assertEqual(fila.celdas[5].glifo, "∑")          # el sesgo sigue saliendo: son las dos IV, no los strikes


if __name__ == "__main__":
    unittest.main()
