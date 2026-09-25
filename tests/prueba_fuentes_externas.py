"""Fuentes externas del 18/09/2026 (agregador, calendario, cartas de EDGAR, múltiplos TTM) y la doble comprobación.

Sin red: cada prueba usa respuestas guardadas y dice qué defecto reintroducido la hace fallar.
"""

import json
import unittest
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from tesis import agregador, calendario, cartas, multiplos, precio, revision, yahoo
from tesis.hechos import Capa, Contraste, Estado, Hecho, Periodo, na

RESUMEN_YAHOO = {"quoteSummary": {"result": [{
    "financialData": {"returnOnEquity": {"raw": 0.49541}, "returnOnAssets": {"raw": 0.16085}, "totalDebt": {"raw": 16654660608}, "totalCash": {"raw": 9127910400},
                      "ebitda": {"raw": 14726931456}, "financialCurrency": "USD"},
    "defaultKeyStatistics": {"enterpriseValue": {"raw": 321113063424}, "enterpriseToEbitda": {"raw": 21.804}, "pegRatio": {"raw": 1.41}, "trailingEps": {"raw": 3.13},
                             "sharesOutstanding": {"raw": 4163939676}, "mostRecentQuarter": {"raw": 1782777600}},
    "calendarEvents": {"earnings": {"earningsDate": [{"raw": 1792526400}], "isEarningsDateEstimate": False, "earningsAverage": {"raw": 0.82249}, "revenueAverage": {"raw": 12880510790}}},
}]}}
FECHA_NASDAQ = {"data": {"reportText": "Netflix, Inc. Common Stock is expected* to report earnings on  10/20/2026 after market close.  The report will be for the fiscal Quarter ending Sep 2026.  "
                                       "According to Zacks Investment Research, based on  11 analysts'  forecasts, the consensus EPS forecast for the quarter is $0.82.  "
                                       "The reported EPS for the same quarter last year was $0.59."}}


class _YahooFalso:
    def __init__(self, datos=RESUMEN_YAHOO):
        self.crudos, self.datos = {}, datos

    def json(self, url):
        self.crudos[url] = (json.dumps(self.datos), datetime(2026, 9, 18, 9, 0))
        return self.datos


def _nasdaq_falso(url, cabeceras):
    assert "/earnings-date" in url, url
    precio._CRUDOS[url] = (json.dumps(FECHA_NASDAQ), datetime(2026, 9, 18, 9, 0))
    return FECHA_NASDAQ


class Agregador(unittest.TestCase):
    def test_lee_el_resumen_y_la_fecha_de_resultados(self):
        """Falla si el agregador deja de leer «raw» de cada cifra, si la fecha de resultados no se convierte del epoch o si la moneda se pierde."""
        with mock.patch.object(yahoo, "cliente", lambda: _YahooFalso()):
            a = agregador.resumen("NFLX")
        self.assertAlmostEqual(a.roe, 0.49541)
        self.assertEqual(a.deuda_total, 16654660608.0)
        self.assertEqual(a.ev_ebitda, 21.804)
        self.assertEqual(a.fecha_resultados, date(2026, 10, 20))
        self.assertIs(a.fecha_resultados_estimada, False)
        self.assertEqual(a.moneda, "USD")
        self.assertIn("quoteSummary", a.respuesta[0])

    def test_sin_respuesta_no_hay_resumen(self):
        """Falla si un cuerpo sin «result» produce un resumen con ceros en vez de None."""
        with mock.patch.object(yahoo, "cliente", lambda: _YahooFalso({"quoteSummary": {"result": []}})):
            self.assertIsNone(agregador.resumen("NFLX"))


class Calendario(unittest.TestCase):
    def test_fecha_de_la_bolsa_cuadrada_con_el_agregador(self):
        """Falla si la fecha de la bolsa no se lee de su frase (mes/día/año), si «expected» deja de marcarla como esperada,
        si el trimestre no se deduce de «Quarter ending Sep 2026» o si el cuadre con el agregador deja de hacerse."""
        with mock.patch.object(precio, "_json", _nasdaq_falso), mock.patch.object(yahoo, "cliente", lambda: _YahooFalso()):
            a = agregador.resumen("NFLX")
            p = calendario.proxima("NFLX", a)
        self.assertEqual(p.fecha, date(2026, 10, 20))
        self.assertTrue(p.esperada)
        self.assertEqual(p.momento, "tras el cierre")
        self.assertEqual(p.trimestre, "3T26")
        self.assertEqual(p.consenso_bpa, 0.82)
        self.assertIs(p.contraste, Contraste.CONFIRMADO)
        otro = SimpleNamespace(fecha_resultados=date(2026, 10, 21), fecha_resultados_estimada=True)
        with mock.patch.object(precio, "_json", _nasdaq_falso):
            q = calendario.proxima("NFLX", otro)
        self.assertIs(q.contraste, Contraste.DISCREPANTE)
        self.assertIn("21/10/2026", q.nota_contraste)


CARTA_HTML = """<html><body><table>
<tr><td>(in millions except per share data)</td><td>Q1'25</td><td>Q2'25</td><td>Q3'25</td><td>Q4'25</td><td>Q1'26</td><td>Q2'26 Forecast</td></tr>
<tr><td>Revenue</td><td>$</td><td>10,543</td><td>$</td><td>11,079</td><td>$</td><td>11,510</td><td>$</td><td>12,051</td><td>$</td><td>12,250</td><td>$</td><td>12,574</td></tr>
<tr><td>Operating Margin</td><td>31.7</td><td>%</td><td>34.1</td><td>%</td><td>28.2</td><td>%</td><td>24.5</td><td>%</td><td>32.3</td><td>%</td><td>32.6</td><td>%</td></tr>
<tr><td>Diluted EPS</td><td>$</td><td>0.66</td><td>$</td><td>0.72</td><td>$</td><td>0.59</td><td>$</td><td>0.56</td><td>$</td><td>1.23</td><td>$</td><td>0.78</td></tr>
<tr><td>Free Cash Flow</td><td>$</td><td>2,661</td><td>$</td><td>2,267</td><td>$</td><td>2,660</td><td>$</td><td>1,872</td><td>$</td><td>5,094</td></tr>
</table></body></html>"""
CARTA_SIGUIENTE = CARTA_HTML.replace("Q1'25</td><td>Q2'25</td><td>Q3'25</td><td>Q4'25</td><td>Q1'26</td><td>Q2'26 Forecast", "Q2'25</td><td>Q3'25</td><td>Q4'25</td><td>Q1'26</td><td>Q2'26</td><td>Q3'26 Forecast") \
    .replace("<td>10,543</td><td>$</td><td>11,079</td><td>$</td><td>11,510</td><td>$</td><td>12,051</td><td>$</td><td>12,250</td><td>$</td><td>12,574</td>",
             "<td>11,079</td><td>$</td><td>11,510</td><td>$</td><td>12,051</td><td>$</td><td>12,250</td><td>$</td><td>12,560</td><td>$</td><td>12,860</td>") \
    .replace("<td>0.66</td><td>$</td><td>0.72</td><td>$</td><td>0.59</td><td>$</td><td>0.56</td><td>$</td><td>1.23</td><td>$</td><td>0.78</td>",
             "<td>0.72</td><td>$</td><td>0.59</td><td>$</td><td>0.56</td><td>$</td><td>1.23</td><td>$</td><td>0.80</td><td>$</td><td>0.82</td>")
# una carta antigua, anterior al split 10:1 del 14/11/2025: el BPA previsto para el 4T25 está en acciones de antes
CARTA_ANTIGUA = CARTA_HTML.replace("Q1'25</td><td>Q2'25</td><td>Q3'25</td><td>Q4'25</td><td>Q1'26</td><td>Q2'26 Forecast", "Q3'24</td><td>Q4'24</td><td>Q1'25</td><td>Q2'25</td><td>Q3'25</td><td>Q4'25 Forecast") \
    .replace("<td>0.66</td><td>$</td><td>0.72</td><td>$</td><td>0.59</td><td>$</td><td>0.56</td><td>$</td><td>1.23</td><td>$</td><td>0.78</td>",
             "<td>5.40</td><td>$</td><td>4.27</td><td>$</td><td>6.61</td><td>$</td><td>7.19</td><td>$</td><td>5.87</td><td>$</td><td>5.45</td>")


class CartasEdgar(unittest.TestCase):
    def test_lee_la_tabla_de_la_carta_y_cuadra_prevision_con_real(self):
        """Falla si la columna «Forecast» no se separa de las publicadas, si «$» o «%» sueltos rompen la fila, si una fila sin
        previsión (FCF) desplaza las demás, si el real no se cuadra con el hecho de la sección C o si el desvío del margen deja de ser en puntos."""
        c1 = cartas._leer(CARTA_HTML, date(2026, 4, 16), "A", "u1")
        c2 = cartas._leer(CARTA_SIGUIENTE, date(2026, 7, 16), "B", "u2")
        self.assertEqual(c1.trimestre, "1T26")
        self.assertEqual(c1.prevision[("2T26", "Revenue")], 12574.0)
        self.assertEqual(c1.prevision[("2T26", "Operating Margin")], 32.6)
        self.assertNotIn(("2T26", "Free Cash Flow"), c1.prevision)
        self.assertEqual(c2.reales[("2T26", "Revenue")], 12560.0)
        p = Periodo(fin=date(2026, 6, 30), inicio=date(2026, 4, 1))
        hechos = {("ingresos", p): Hecho("ingresos", p, 12559938000.0, Estado.VALOR, Capa.SEC),
                  ("bpa_diluido", p): Hecho("bpa_diluido", p, 0.80, Estado.VALOR, Capa.SEC, unidad="USD/acción")}
        guias = cartas.guias_frente_a_real([c2, c1], hechos)
        por = {(g.trimestre, g.metrica): g for g in guias}
        g = por[("2T26", "Revenue")]
        self.assertEqual((g.prevista, g.real), (12574.0, 12560.0))
        self.assertIs(g.contraste, Contraste.CONFIRMADO)
        # el margen: previsto 32,6 %, publicado 32,3 % → −0,3 puntos porcentuales (no un cociente)
        self.assertAlmostEqual(por[("2T26", "Operating Margin")].desvio, (32.3 - 32.6) / 100, places=9)
        self.assertIs(por[("2T26", "Diluted EPS")].contraste, Contraste.CONFIRMADO)
        # la previsión del 3T26 aún no tiene real: no sale
        self.assertNotIn(("3T26", "Revenue"), por)
        # un real de la carta que no coincide con el hecho contrastado sale ≠ y lo dice
        otros = dict(hechos)
        otros[("bpa_diluido", p)] = Hecho("bpa_diluido", p, 0.85, Estado.VALOR, Capa.SEC, unidad="USD/acción")
        g2 = next(x for x in cartas.guias_frente_a_real([c2, c1], otros) if (x.trimestre, x.metrica) == ("2T26", "Diluted EPS"))
        self.assertIs(g2.contraste, Contraste.DISCREPANTE)
        self.assertIn("0.85", g2.nota)

    def test_la_prevision_por_accion_anterior_al_split_se_divide(self):
        """Falla si una previsión de BPA escrita antes del split 10:1 se compara tal cual con el real reexpresado después."""
        antigua = cartas._leer(CARTA_ANTIGUA, date(2025, 10, 21), "C", "u3")
        reciente = cartas._leer(CARTA_HTML, date(2026, 4, 16), "A", "u1")
        guias = cartas.guias_frente_a_real([antigua, reciente], {}, splits=[(date(2025, 11, 14), 10.0)])
        g = next(x for x in guias if (x.trimestre, x.metrica) == ("4T25", "Diluted EPS"))
        self.assertAlmostEqual(g.prevista, 0.545)
        self.assertEqual(g.real, 0.56)
        self.assertIn("split", g.nota)
        ingresos = next(x for x in guias if (x.trimestre, x.metrica) == ("4T25", "Revenue"))
        self.assertNotIn("split", ingresos.nota)      # solo las cifras por acción se ajustan


def _hechos_ttm():
    ps = [Periodo(fin=f, inicio=i) for i, f in ((date(2025, 7, 1), date(2025, 9, 30)), (date(2025, 10, 1), date(2025, 12, 31)),
                                                (date(2026, 1, 1), date(2026, 3, 31)), (date(2026, 4, 1), date(2026, 6, 30)))]
    anuales = [Periodo.anual(date(2024, 12, 31)), Periodo.anual(date(2025, 12, 31))]
    h = {}

    def pon(campo, p, v, unidad="USD"):
        h[(campo, p)] = Hecho(campo, p, float(v), Estado.VALOR, Capa.SEC, unidad=unidad)
    for p, ing, ebit, amort, bn, bpa, cfo, capex in zip(ps, (11510, 12051, 12250, 12560), (3248, 2957, 3957, 4193), (87, 86, 99, 101), (2547, 2419, 5283, 3401),
                                                       (0.59, 0.56, 1.23, 0.80), (2825, 2112, 5290, 1744), (165, 239, 196, 219)):
        pon("ingresos", p, ing * 1e6); pon("ebit", p, ebit * 1e6); pon("amortizacion", p, amort * 1e6); pon("beneficio_neto", p, bn * 1e6)
        pon("bpa_diluido", p, bpa, "USD/acción"); pon("cfo", p, cfo * 1e6); pon("capex", p, capex * 1e6)
    cierre, hace_un_anio = Periodo.instante(date(2026, 6, 30)), Periodo.instante(date(2025, 6, 30))
    pon("deuda_bruta", cierre, 14309e6); pon("caja", cierre, 9099e6); pon("inversiones_cp", cierre, 29e6)
    pon("patrimonio", cierre, 30152e6); pon("patrimonio", hace_un_anio, 24952e6); pon("total_activo", cierre, 58450e6); pon("total_activo", hace_un_anio, 53100e6)
    pon("bpa_diluido", anuales[0], 1.98, "USD/acción"); pon("bpa_diluido", anuales[1], 2.53, "USD/acción")
    return h, ps, anuales


class MultiplosSec(unittest.TestCase):
    def test_ttm_con_formula_y_contraste_con_el_agregador(self):
        """Falla si el TTM deja de sumar los cuatro últimos trimestres, si el EV no resta tesorería e inversiones, si el PEG
        usa otra tasa que el crecimiento anual del BPA, si el ROE no usa saldos medios o si el contraste con el agregador
        deja de marcar ✓/≠ con la tolerancia del 2 %."""
        h, ps, anuales = _hechos_ttm()
        precio_h = Hecho("precio", Periodo.instante(date(2026, 9, 17)), 75.31, Estado.VALOR, Capa.DOCUMENTO, certeza=__import__("tesis.hechos", fromlist=["Certeza"]).Certeza.MEDIA)
        agr = SimpleNamespace(ebitda_ttm=14726931456.0, ev_ebitda=21.804, peg=1.41, roe=0.49541, roa=0.16085)
        m = multiplos.construir(h, ps, anuales, precio_h, 4163939676.0, agr)
        L = {l.rotulo.split(" (")[0]: l for l in m.lineas}
        self.assertAlmostEqual(L["Capitalización"].valor / 1e6, 75.31 * 4163.939676, places=3)
        self.assertAlmostEqual(L["Valor de empresa, EV"].valor / 1e6, 75.31 * 4163.939676 + 14309 - 9099 - 29, places=3)
        self.assertEqual(L["EBITDA TTM"].valor, (3248 + 2957 + 3957 + 4193 + 87 + 86 + 99 + 101) * 1e6)
        self.assertIs(L["EBITDA TTM"].contraste, Contraste.CONFIRMADO)
        self.assertAlmostEqual(L["PER"].valor, 75.31 / 3.18, places=6)
        self.assertIs(L["EV / EBITDA"].contraste, Contraste.CONFIRMADO)
        self.assertAlmostEqual(L["Crecimiento del BPA diluido, último ejercicio"].valor, 2.53 / 1.98 - 1)
        self.assertAlmostEqual(L["PEG"].valor, (75.31 / 3.18) / ((2.53 / 1.98 - 1) * 100))
        self.assertIs(L["PEG"].contraste, Contraste.SIN_CONTRASTAR)      # otra definición: no se cuadra
        self.assertEqual(L["PEG"].agregador, 1.41)
        self.assertAlmostEqual(L["ROE"].valor, 13650e6 / ((30152e6 + 24952e6) / 2))
        self.assertIs(L["ROE"].contraste, Contraste.CONFIRMADO)
        self.assertIs(L["ROA"].contraste, Contraste.DISCREPANTE)
        self.assertIn("16,1", L["ROA"].nota_contraste)

    def test_sin_precio_los_multiplos_sobre_precio_son_na_con_motivo(self):
        """Falla si sin cotización oficial aparece un PER o una capitalización, o si falta el motivo."""
        h, ps, anuales = _hechos_ttm()
        m = multiplos.construir(h, ps, anuales, na("precio", Periodo.instante(date(2026, 9, 17)), "sin fuente"), 4163939676.0, None)
        L = {l.rotulo.split(" (")[0]: l for l in m.lineas}
        self.assertIsNone(L["PER"].valor)
        self.assertIn("sin cotización", L["PER"].motivo)
        self.assertIsNone(L["Capitalización"].valor)
        self.assertIsNotNone(L["EBITDA TTM"].valor)      # lo que no depende del precio sí sale
        self.assertIn("precio", m.faltan)


class DobleComprobacion(unittest.TestCase):
    def _informe(self, texto_celda):
        from tesis.formato import Celda
        from tesis.informe import Cuadro, FilaCuadro
        p = Periodo.anual(date(2025, 12, 31))
        hechos = {("ingresos", p): Hecho("ingresos", p, 45183036000.0, Estado.VALOR, Capa.SEC)}
        fila = FilaCuadro("Ingresos", [Celda(texto_celda, "✓", "H", "valor", "")], origen="hecho:ingresos", periodos=("FY2025",))
        c = Cuadro(8, "Estado de resultados (mln USD)", ["2025"], [fila], "Fuente: —")
        inf = SimpleNamespace(hechos=hechos, cifras_resumen=c, objetivos=None, regiones=None, accionistas=None, filiales=None, ejecutivos=None, retribucion=None,
                              resultados=None, balance=None, flujo=None, rentabilidad=None, rentabilidad_ttm=None, mercado_cuadro=None, comparables_cuadro=None,
                              comparables_sic_cuadro=None, dcf={}, riesgos_cuadros={}, historial_cuadros={}, f_cuadros={})
        html = f'<div class="cuadro"><div class="rotulo">Cuadro 8. Estado de resultados (mln USD)</div><table><thead><tr><th></th><th>2025</th></tr></thead><tbody><tr><td>Ingresos</td><td>{texto_celda}</td></tr></tbody></table></div>'
        return inf, html

    def test_caza_una_cifra_impresa_distinta_del_hecho(self):
        """Falla si la doble comprobación deja pasar una celda cuyo texto no es el del hecho releído, o si da desacuerdos con la correcta."""
        inf, html = self._informe("45.183")
        r = revision.comprobar(inf, html)
        self.assertEqual(r.desacuerdos, [])
        self.assertGreaterEqual(r.comprobadas, 2)
        inf, html = self._informe("45.138")
        r = revision.comprobar(inf, html)
        self.assertEqual(len(r.desacuerdos), 1)
        self.assertIn("45.183", r.desacuerdos[0])

    def test_caza_un_html_que_no_imprime_lo_que_dice_el_cuadro(self):
        """Falla si el HTML imprime otra cosa que el cuadro y la doble comprobación no lo ve."""
        inf, html = self._informe("45.183")
        r = revision.comprobar(inf, html.replace("<td>45.183</td>", "<td>45.184</td>"))
        self.assertEqual(len(r.desacuerdos), 1)
        self.assertIn("HTML", r.desacuerdos[0])


if __name__ == "__main__":
    unittest.main()
