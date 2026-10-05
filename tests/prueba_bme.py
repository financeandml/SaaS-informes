"""B4 · Motor y mercado de los emisores de BME: EUR, semestral, rf del BCE y beta frente al índice de BME.

Sin red: las respuestas de la API oficial de BME y del BCE se grabaron el 29/09/2026 con la caché de `precio._json` y
`precio.texto_con_cache` en `tests/fixtures/cache_bolsa/` y se leen con `precio.SOLO_CACHE`. Las cifras de contraste (el
cierre de 4,56 EUR del 22/05/2026 y el rango de 12 meses 4,16–6,90 de Bytetravel, el 2,22 de Treelogic) son las de los
informes de IEAF: oráculo de la prueba, nunca fuente del informe. Cada prueba dice qué fallo reintroducido la hace fallar.
"""

import json
import unittest
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path
from unittest import mock

from tesis.datos.hechos import Capa, Certeza, Origen, Periodo, de_valor
from tesis.fuentes import bce, bme, emisores, precio, tesoro
from tesis.fuentes.sec import Emisor
from tesis.motor import datos as motor_datos, multiplos
from tesis.motor.wacc import beta_regresion
from tesis.umbrales import _datos as umbrales

F = Path(__file__).resolve().parent / "fixtures"
BYTE, TRTK, IBEX_GROWTH = "ES0105817003", "ES0105909008", "ES0S00001149"
FV = date(2026, 5, 26)                                 # la fecha de los informes de IEAF
DESDE_5A = date(2021, 5, 16)                           # la ventana de cinco años que pide el motor para esa fecha


class _SinRed(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._antes = (precio.CACHE_BOLSA, precio.SOLO_CACHE)
        precio.CACHE_BOLSA, precio.SOLO_CACHE = F / "cache_bolsa", True

    @classmethod
    def tearDownClass(cls):
        precio.CACHE_BOLSA, precio.SOLO_CACHE = cls._antes


def _h(campo: str, periodo: Periodo, valor: float, unidad: str = "EUR"):
    return de_valor(campo, periodo, valor, Capa.DOCUMENTO, Origen(documento="cuentas de prueba"), unidad=unidad, certeza=Certeza.ALTA)


def _s(fin: date) -> Periodo:
    return Periodo.de_meses(fin, 6)


# ---------------------------------------------------------------------------
# La API de BME sobre respuestas grabadas
# ---------------------------------------------------------------------------

class ApiBme(_SinRed):
    def test_buscar(self):
        """Falla si el buscador cruza los campos de la API (código de emisor, ISIN, segmento) o pierde el emisor."""
        r = bme.buscar("BYTE")
        self.assertEqual([(e.clave, e.isin, e.segmento, e.sistema, e.cotiza) for e in r], [("05817", BYTE, "BMEGrowth", "MTF", True)])

    def test_valor_con_clasificacion_sectorial(self):
        """Falla si la ficha del valor pierde las acciones admitidas, la moneda o el sector y subsector de la bolsa, de los
        que sale la regla 7 para un emisor sin SIC."""
        v = bme.valor(BYTE)
        self.assertEqual((v.ticker, v.clave, v.acciones, v.moneda, v.segmento), ("BYTE", "05817", 30_674_364.0, "EUR", "BMEGrowth"))
        self.assertEqual((v.sector, v.subsector), ("06", "02"))

    def test_sesiones_por_paginas(self):
        """Falla si el histórico se queda en la primera página de 100 sesiones (la API da 175 en dos páginas)."""
        s = bme.sesiones(BYTE, date(2025, 5, 26), date(2026, 5, 26))
        self.assertEqual(len(s), 175)
        self.assertEqual((min(s), s[min(s)].cierre), (date(2025, 5, 27), 6.9))
        self.assertEqual((s[date(2026, 5, 22)].cierre, s[date(2026, 5, 22)].volumen, s[date(2026, 5, 22)].anterior), (4.56, 250.0, 4.52))

    def test_indice_por_ventanas(self):
        """Falla si el índice se pide por páginas (la API las ignora: repite la primera) o si las ventanas dejan huecos."""
        i = bme.indice(IBEX_GROWTH, date(2024, 5, 26), date(2026, 5, 26))
        dias = sorted(i)
        self.assertEqual((len(i), dias[0], dias[-1], i[date(2026, 5, 22)]), (510, date(2024, 5, 27), date(2026, 5, 26), 1873.5))
        self.assertLessEqual(max((b - a).days for a, b in zip(dias, dias[1:])), 5)

    def test_informacion_financiera(self):
        """Falla si se pierden las cuentas anuales o los semestrales, o si el periodo no se lee de la entrada."""
        docs = bme.informacion_financiera("05817")
        self.assertEqual([(d.clase, d.ejercicio, d.periodo) for d in docs],
                         [("anual", 2025, "AN"), ("semestral", 2025, "1S"), ("anual", 2024, "AN"), ("semestral", 2024, "1S")])
        self.assertTrue(all(d.url.startswith(bme.BASE_DOCUMENTOS + "/MTFDocuments/") for d in docs))

    def test_solo_sesiones_con_negociacion(self):
        """Falla si una sesión de volumen cero, o sin volumen publicado, cuenta como negociada."""
        base = bme.Sesion(date(2026, 5, 20), 2.22, 1199.0, None, None, None, 2.22, 0.0, 0.0)
        historico = {base.fecha: base, date(2026, 5, 21): replace(base, fecha=date(2026, 5, 21), volumen=0.0),
                     date(2026, 5, 22): replace(base, fecha=date(2026, 5, 22), volumen=None)}
        self.assertEqual(list(bme.con_negociacion(historico)), [date(2026, 5, 20)])


# ---------------------------------------------------------------------------
# El precio y la cotización de un emisor de BME (regla 4)
# ---------------------------------------------------------------------------

class MercadoBme(_SinRed):
    def test_cierre_oficial_de_bytetravel_el_22_05_2026(self):
        """IEAF: 4,56 EUR, cierre del 22/05/2026. Falla si se toma otra columna de la sesión («anterior», máximo) o la
        primera sesión de la ventana, o si el precio de la cotización y el cierre oficial no salen de la misma sesión."""
        s = bme.cierre_oficial(BYTE, date(2026, 5, 22))
        m = precio.mercado("BYTE.MC", date(2026, 5, 22))
        self.assertEqual((s.fecha, s.cierre), (date(2026, 5, 22), 4.56))
        self.assertEqual((m.precio.periodo.fin, m.precio.valor), (s.fecha, s.cierre))
        self.assertEqual(m.cotizacion.volumen, 250.0)

    def test_rango_de_52_semanas_a_26_05_2026(self):
        """IEAF: 4,16–6,90 (12 meses). Falla si el rango sale de máximos y mínimos intradía (4,14) o si la ventana deja
        fuera el primer día de las 52 semanas (el 6,90 del 27/05/2025: el máximo bajaría a 6,80)."""
        m = precio.mercado("BYTE.MC", FV)
        self.assertEqual(m.cotizacion.rango_52s, (4.16, 6.9))
        self.assertIn("175 sesiones con negociación", m.notas["rango_52s"])

    def test_emisor_de_bme_en_euros_sin_consenso(self):
        """Falla si el precio de un emisor de BME sale en USD, de Nasdaq, sin la última sesión con negociación rotulada, si
        la falta de consenso de BME se cuenta como un fallo o si la capitalización de la ficha (de otra fecha) se contrasta."""
        m = precio.mercado("BYTE.MC", FV)
        self.assertTrue(m.precio.hay_dato)
        self.assertEqual((m.precio.valor, m.precio.periodo.fin, m.precio.unidad, m.precio.capa), (4.48, date(2026, 5, 25), "EUR/acción", Capa.DOCUMENTO))
        self.assertEqual((m.cotizacion.moneda, m.cotizacion.fuente), ("EUR", "BME (histórico oficial de cierres)"))
        self.assertIn("última sesión con negociación hasta el 26/05/2026", m.precio.nota)
        self.assertIsNone(m.consenso)
        self.assertNotIn("consenso", m.faltan)
        self.assertEqual(m.faltan, {})
        self.assertIsNone(m.cotizacion.cap_mercado_fuente)
        self.assertIn("no la de la sesión del precio", m.notas["cap_mercado_fuente"])
        self.assertEqual(m.contraste_cierre[0].name, "CONFIRMADO")
        self.assertIn("historico", m.crudos)
        self.assertIn('"date":"20260525"', m.crudos["historico"][1])

    def test_valor_poco_liquido(self):
        """Treelogic no negoció el 21 ni el 22/05/2026; IEAF da 2,22 EUR «a 22 may 2026». Falla si el precio exige
        negociación el mismo día o si ignora la ventana de `umbrales.bme_cierre_ventana_dias` (con 1 día: N/A)."""
        m = precio.mercado("TRTK.MC", date(2026, 5, 22))
        self.assertEqual((m.precio.valor, m.precio.periodo.fin), (2.22, date(2026, 5, 20)))
        self.assertEqual(m.cotizacion.rango_52s, (2.22, 3.0))
        with mock.patch.object(bme, "ventana_cierre", return_value=1):
            corta = precio.mercado("TRTK.MC", date(2026, 5, 22))
        self.assertFalse(corta.precio.hay_dato)
        self.assertIn("1 días anteriores", corta.precio.motivo)


# ---------------------------------------------------------------------------
# Tipo sin riesgo y beta
# ---------------------------------------------------------------------------

class RfYBeta(_SinRed):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.byte, cls.trtk = emisores.emisor("BYTE.MC"), emisores.emisor("TRTK.MC")

    def test_rf_del_bce_el_26_05_2026(self):
        """Curva AAA del BCE a 10 años: 3,03 %. Falla si el emisor de BME va al Tesoro de EE. UU., si el porcentaje no se
        pasa a tanto por uno o si el rótulo no sale del mismo sitio que la cifra."""
        r = bce.rf_10a(FV)
        self.assertEqual((round(r.valor * 100, 2), r.fecha), (3.03, FV))
        del_emisor, rotulo = emisores.rf(self.byte, FV)
        self.assertEqual(del_emisor, r)
        self.assertTrue(rotulo.startswith("BCE"))
        with mock.patch.object(tesoro, "rf_10a", return_value="tesoro") as t:
            self.assertEqual(emisores.rf(replace(self.byte, mercado="sec"), FV), ("tesoro", "Tesoro de EE. UU., curva par a 10 años"))
        t.assert_called_once_with(FV)

    def test_beta_solo_con_sesiones_con_negociacion(self):
        """La API también sabe dar los días sin negociación, con el cierre anterior repetido (`onlyWithTurnover=false`).
        Falla si esos días entran en los cierres de la beta: la beta cambia (se reintrodujo quitando `con_negociacion`).
        Y falla si el índice no se toma en las mismas fechas que el valor (su cierre del viernes contra el del martes)."""
        reales = bme.sesiones(BYTE, DESDE_5A, FV)
        indice, rotulo = emisores.cierres_mercado(self.byte, DESDE_5A, FV)
        con_huecos, ultima = dict(reales), None
        for d in sorted(set(indice) | set(reales)):
            if d in reales:
                ultima = reales[d]
            elif ultima is not None:
                con_huecos[d] = replace(ultima, fecha=d, volumen=0.0, efectivo=0.0)
        self.assertGreater(len(con_huecos), len(reales) + 100)
        c = emisores.cierres(self.byte, DESDE_5A, FV)
        with mock.patch.object(bme, "sesiones", return_value=dict(sorted(con_huecos.items()))):
            self.assertEqual(emisores.cierres(self.byte, DESDE_5A, FV), c)
        b = motor_datos._betas_por_sesiones(c, indice, FV, 100)[0]
        mal = beta_regresion({d: s.cierre for d, s in con_huecos.items()}, indice, FV, 2, "semanal", solo_dias_comunes=True)
        self.assertGreater(abs(b.bruta - mal.bruta), 0.01)
        self.assertEqual(b, beta_regresion(c, {d: v for d, v in indice.items() if d in c}, FV, 2, "semanal"))
        self.assertIn("IBEX Growth Market All Share", rotulo)

    def test_minimo_de_sesiones(self):
        """Treelogic: 45 sesiones con negociación desde su salida (enero de 2026). Falla si la beta no exige el mínimo de
        `umbrales.beta_sesiones_min` y lo dice, o si el umbral no sale de la configuración (con 400, tampoco Bytetravel)."""
        indice, _ = emisores.cierres_mercado(self.trtk, DESDE_5A, FV)
        _, _, motivo = motor_datos._betas_por_sesiones(emisores.cierres(self.trtk, DESDE_5A, FV), indice, FV, 100)
        self.assertIn("solo 45 sesiones con negociación", motivo)
        self.assertIn("beta_sesiones_min", motivo)
        c = emisores.cierres(self.byte, DESDE_5A, FV)
        self.assertIsNotNone(motor_datos._betas_por_sesiones(c, indice, FV, 100)[0])
        self.assertIsNone(motor_datos._betas_por_sesiones(c, indice, FV, 400)[0])


# ---------------------------------------------------------------------------
# El motor con un emisor de BME y cuentas sintéticas semestrales
# ---------------------------------------------------------------------------

FY23, FY24 = Periodo.anual(date(2023, 12, 31)), Periodo.anual(date(2024, 12, 31))
S24, S25 = _s(date(2024, 6, 30)), _s(date(2025, 6, 30))


def _hechos_semestrales() -> dict:
    """Cuentas inventadas para la prueba (no son de Bytetravel): ejercicios 2023 y 2024 y primeros semestres 2024 y 2025."""
    h = {}
    for campo, fy23, fy24, s24, s25 in (("ingresos", 8.5e6, 11.2e6, 5.0e6, 9.0e6), ("ebit", 0.5e6, 1.0e6, 0.4e6, 0.9e6),
                                        ("amortizacion", 0.3e6, 0.4e6, 0.2e6, 0.3e6), ("beneficio_neto", 0.3e6, 0.7e6, 0.2e6, 0.6e6),
                                        ("cfo", 0.6e6, 1.1e6, 0.5e6, 0.8e6), ("capex", 0.2e6, 0.3e6, 0.1e6, 0.2e6),
                                        ("intereses", -0.05e6, -0.06e6, -0.03e6, -0.02e6), ("bpa_diluido", 0.01, 0.023, 0.007, 0.02)):
        for p, v in ((FY23, fy23), (FY24, fy24), (S24, s24), (S25, s25)):
            h[(campo, p)] = _h(campo, p, v)
    h[("acciones_diluidas", S25)] = _h("acciones_diluidas", S25, 30.0e6, "acciones")
    for campo, v in (("deuda_bruta", 1.0e6), ("caja", 5.0e6), ("inversiones_cp", 0.0), ("patrimonio", 12.0e6), ("total_activo", 20.0e6)):
        h[(campo, Periodo.instante(S25.fin))] = _h(campo, Periodo.instante(S25.fin), v)
    return h


PERIODOS = {"anuales": [FY23, FY24], "semestres": [S24, S25], "trimestres": [],
            "instantes": [Periodo.instante(FY24.fin), Periodo.instante(S25.fin)]}


def _entradas(sector="software", beta="regresion") -> dict:
    d = json.loads((F / "QCOM" / "entradas.json").read_text(encoding="utf-8"))
    d["meta"] = {"fecha_valoracion": FV.isoformat(), **({"sector": sector} if sector else {})}
    d["val"]["anio_base"] = "ultimos_12_meses"
    d["wacc"]["beta_metodo"] = beta
    if beta == "bottom_up":
        d["wacc"].update({"beta_desapalancada": 1.0, "beta_fuente": "entrada de prueba"})
    d.pop("comparables", None)
    return d


class MotorBme(_SinRed):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.byte, cls.trtk = emisores.emisor("BYTE.MC"), emisores.emisor("TRTK.MC")
        cls.m = motor_datos.ejecutar(cls.byte, {}, _hechos_semestrales(), PERIODOS, _entradas(), FV, 30_674_364.0, umbrales(), 0, None)

    def test_precio_rf_y_beta_de_bme(self):
        """Falla si el motor de un emisor de BME pide Nasdaq, SPY o el Tesoro, si su precio no es el mismo hecho que la
        cotización del informe (regla 13) o si los textos de origen no dicen la fuente real."""
        m = self.m
        self.assertEqual((m.moneda, m.mercado), ("EUR", "bme"))
        self.assertEqual((m.precio, m.fecha_precio), (4.48, date(2026, 5, 25)))
        cot = precio.mercado("BYTE.MC", FV).precio
        self.assertEqual((m.precio, m.fecha_precio), (cot.valor, cot.periodo.fin))
        w = m.valoracion.wacc
        self.assertEqual(round(w.rf * 100, 2), 3.03)
        self.assertEqual(w.rf_fuente, m.fuente_rf)
        self.assertIn("curva al contado AAA", w.rf_fuente)
        self.assertIn("cierres oficiales de BME", w.beta_origen)
        self.assertIn("IBEX Growth Market All Share", w.beta_origen)
        self.assertNotIn("SPY", w.beta_origen)
        self.assertEqual(m.fuente_beta, w.beta_origen)
        self.assertIn("cierre oficial de BME del 25/05/2026", m.fuente_precio)
        self.assertEqual([b for b in m.bloqueos if b.split(":")[0] in ("precio", "rf", "beta", "acciones", "sector", "año base")], [])

    def test_udm_semestral_acciones_y_dpa(self):
        """Falla si el año base UDM no es ejercicio + 1S − 1S anterior, si las acciones no son las del último periodo
        publicado (rotuladas sin «SEC») o si el DPA sin fuente sale 0 en vez de N/A con motivo."""
        m = self.m
        self.assertEqual(m.etiqueta_base, "UDM a 1S25")
        self.assertAlmostEqual(m.ingresos_base, 11.2e6 + 9.0e6 - 5.0e6)
        pte = m.valoracion.puente
        self.assertEqual(pte.acciones, 30.0e6)
        self.assertIn("1S25", pte.acciones_nota)
        self.assertNotIn("SEC", pte.acciones_nota)
        self.assertIsNone(m.dpa_anual)
        self.assertTrue(m.dpa_motivo)
        self.assertTrue(any(a.startswith("DPA N/A") for a in m.avisos))
        self.assertIsNotNone(m.ntm)

    def test_per_historico_de_las_cuentas(self):
        """Sin XBRL, el PER histórico sale del BPA publicado: al cierre de 2024 (el del ejercicio) y al del 1S25 (2024 + 1S25
        − 1S24), con el cierre de la última sesión con negociación. Falla si se pide a companyfacts (vacío: ningún punto),
        si el 1S no resta el anterior o si inventa un punto de 2023, cuando Bytetravel aún no cotizaba."""
        c = emisores.cierres(self.byte, DESDE_5A, FV)
        cierre = lambda fin: c[max(d for d in c if d <= fin)]                                  # noqa: E731
        esperado = [(FY24.fin, cierre(FY24.fin) / 0.023), (S25.fin, cierre(S25.fin) / (0.023 + 0.02 - 0.007))]
        self.assertEqual([f for f, _ in self.m.historico_per], [f for f, _ in esperado])
        for (_, a), (_, b) in zip(self.m.historico_per, esperado):
            self.assertAlmostEqual(a, b)

    def test_pocas_sesiones_bloquea_la_beta_sin_caer_en_spy(self):
        """Falla si con 45 sesiones el motor calcula la beta, la toma de otro mercado o bloquea sin decir por qué; con beta
        bottom-up del analista, la regresión no hace falta y no bloquea."""
        m = motor_datos.ejecutar(self.trtk, {}, _hechos_semestrales(), PERIODOS, _entradas(), FV, 6_037_520.0, umbrales(), 0, None)
        beta = [b for b in m.bloqueos if b.startswith("beta:")]
        self.assertEqual(len(beta), 1)
        self.assertIn("solo 45 sesiones con negociación", beta[0])
        self.assertIn("IBEX Growth Market All Share", beta[0])
        self.assertNotIn("SPY", " ".join(m.bloqueos))
        abajo = motor_datos.ejecutar(self.trtk, {}, _hechos_semestrales(), PERIODOS, _entradas(beta="bottom_up"), FV, 6_037_520.0, umbrales(), 0, None)
        self.assertEqual([b for b in abajo.bloqueos if b.startswith("beta:")], [])
        self.assertTrue(abajo.valoracion.wacc.beta_origen.startswith("bottom-up"))
        # la última sesión de Treelogic (20/05) tiene 6 días: con una ventana de 3, no hay cierre vigente (el mismo umbral
        # que la cotización, `bme.ventana_cierre`)
        with mock.patch.object(bme, "ventana_cierre", return_value=3):
            viejo = motor_datos.ejecutar(self.trtk, {}, _hechos_semestrales(), PERIODOS, _entradas(), FV, 6_037_520.0, umbrales(), 0, None)
        self.assertEqual(len(viejo.bloqueos), 1)
        self.assertIn("sin sesiones con negociación en BME en los 3 días", viejo.bloqueos[0])

    def test_paquete_sin_sic(self):
        """Falla si a un emisor de BME se le propone un paquete sin que el analista lo elija, o si la regla 7 deja pasar
        una financiera, una SOCIMI o una biotecnológica sin ingresos por no tener SIC. La SEC sigue por su SIC."""
        m = motor_datos.ejecutar(self.byte, {}, _hechos_semestrales(), PERIODOS, _entradas(sector=None), FV, 30_674_364.0, umbrales(), 0, None)
        self.assertEqual(len(m.bloqueos), 1)
        self.assertIn("paso 1", m.bloqueos[0])
        self.assertEqual(motor_datos.paquete_del_emisor(self.byte, 19.4e6, umbrales()), ("", None))
        for clasif, ingresos, que in ((("05", "01"), 5e9, "banca"), (("07", "02"), 1e8, "SOCIMI"), (("03", "05"), None, "sin ingresos")):
            with mock.patch.object(emisores, "clasificacion_bolsa", return_value=clasif):
                paquete, bloqueo = motor_datos.paquete_del_emisor(self.byte, ingresos, umbrales())
            self.assertEqual(paquete, "")
            self.assertIn(que, bloqueo)
        with mock.patch.object(emisores, "clasificacion_bolsa", return_value=("03", "05")):
            self.assertEqual(motor_datos.paquete_del_emisor(self.byte, 900e6, umbrales()), ("", None))
        sec = replace(self.byte, mercado="sec", sic="3674", moneda="USD")
        self.assertEqual(motor_datos.paquete_del_emisor(sec, None, umbrales()), motor_datos.paquete_por_sic("3674", None))


# ---------------------------------------------------------------------------
# Múltiplos con doce meses semestrales (hechos sintéticos, sin red)
# ---------------------------------------------------------------------------

class MultiplosSemestrales(unittest.TestCase):
    FY24, FY25 = Periodo.anual(date(2024, 12, 31)), Periodo.anual(date(2025, 12, 31))
    S25, S26 = _s(date(2025, 6, 30)), _s(date(2026, 6, 30))

    def _hechos(self, sin=()):
        h = {}
        for campo, fy24, fy25, s25, s26 in (("ingresos", 11.2e6, 19.4e6, 8.0e6, 12.0e6), ("ebit", 1.0e6, 2.0e6, 0.8e6, 1.1e6),
                                            ("amortizacion", 0.4e6, 0.6e6, 0.3e6, 0.4e6), ("beneficio_neto", 0.7e6, 1.5e6, 0.6e6, 0.9e6),
                                            ("cfo", 1.1e6, 2.2e6, 0.9e6, 1.2e6), ("capex", 0.3e6, 0.5e6, 0.2e6, 0.3e6)):
            for p, v in ((self.FY24, fy24), (self.FY25, fy25), (self.S25, s25), (self.S26, s26)):
                if (campo, p) not in sin:
                    h[(campo, p)] = _h(campo, p, v)
        h[("acciones_diluidas", self.S26)] = _h("acciones_diluidas", self.S26, 30.0e6, "acciones")
        fin = Periodo.instante(self.S26.fin)
        for campo, v in (("deuda_bruta", 1.0e6), ("caja", 5.0e6), ("inversiones_cp", 1.0e6), ("patrimonio", 12.0e6), ("total_activo", 20.0e6)):
            h[(campo, fin)] = _h(campo, fin, v)
        return h

    def _precio(self):
        return de_valor("precio", Periodo.instante(date(2026, 9, 25)), 4.0, Capa.DOCUMENTO, Origen(documento="BME"), unidad="EUR/acción", certeza=Certeza.ALTA)

    def test_udm_ejercicio_mas_1s_menos_1s_anterior(self):
        """Falla si el UDM suma el ejercicio y el 1S sin restar el 1S anterior, si se queda en el ejercicio o si los
        rótulos dicen USD o trimestres (también cuando quien llama no pasa la moneda: sale de los ingresos)."""
        m = multiplos.construir(self._hechos(), [], [self.FY24, self.FY25], self._precio(), 30.0e6, moneda="EUR",
                                semestres=[self.S25, self.S26], fuente="las cuentas publicadas en BME")
        self.assertEqual((m.periodicidad, m.fin, m.trimestres, m.moneda), ("semestral", "1S26", ["2025", "1S26", "1S25"], "EUR"))
        ev = 4.0 * 30.0e6 + 1.0e6 - 5.0e6 - 1.0e6
        self.assertAlmostEqual(m.linea("EV / Ventas (TTM)").valor, ev / (19.4e6 + 12.0e6 - 8.0e6))
        ebitda = m.linea("EBITDA TTM (M EUR)")
        self.assertAlmostEqual(ebitda.valor, (2.0e6 + 1.1e6 - 0.8e6) + (0.6e6 + 0.4e6 - 0.3e6))
        self.assertIn("UDM a 1S26: 2025 + 1S26 − 1S25", ebitda.formula)
        self.assertIsNotNone(m.linea("Capitalización (M EUR)"))
        self.assertFalse(any("USD" in l.rotulo for l in m.lineas))
        per = m.linea("PER (TTM)")
        self.assertAlmostEqual(per.valor, 4.0 / ((1.5e6 + 0.9e6 - 0.6e6) / 30.0e6))
        self.assertIn("acciones medias diluidas del 1S26", per.formula)
        # sin semestre posterior al último ejercicio, los doce meses son el ejercicio; y sin `moneda`, la de los ingresos
        solo = multiplos.construir(self._hechos(), [], [self.FY24, self.FY25], self._precio(), 30.0e6, semestres=[self.S25])
        self.assertEqual((solo.fin, solo.trimestres, solo.moneda), ("2025", ["2025"], "EUR"))
        self.assertIsNotNone(solo.linea("EBITDA TTM (M EUR)"))

    def test_sin_el_1s_anterior_no_se_rellena(self):
        """Falla si, sin los ingresos del 1S25, el UDM se completa con medio ejercicio o con el 1S26 solo: N/A con motivo."""
        m = multiplos.construir(self._hechos(sin={("ingresos", self.S25)}), [], [self.FY24, self.FY25], self._precio(), 30.0e6,
                                moneda="EUR", semestres=[self.S25, self.S26])
        l = m.linea("EV / Ventas (TTM)")
        self.assertIsNone(l.valor)
        valor, usados, motivo = multiplos.udm(self._hechos(sin={("ingresos", self.S25)}), "ingresos", [self.FY24, self.FY25], [self.S25, self.S26])
        self.assertIsNone(valor)
        self.assertIn("1S25", motivo)
        valor, _, motivo = multiplos.udm(self._hechos(), "ingresos", [self.FY24, self.FY25], [self.S26])
        self.assertIsNone(valor)
        self.assertIn("sin el 1S del ejercicio 2025", motivo)

    def test_etiquetas_de_semestre(self):
        """Falla si el semestre se rotula por meses («6M26») o si el 2S se confunde con el 1S."""
        anuales = [self.FY24, self.FY25]
        self.assertEqual([multiplos.etiqueta(p, anuales) for p in (self.S25, self.S26, Periodo(date(2025, 12, 31), date(2025, 7, 1)), self.FY25)],
                         ["1S25", "1S26", "2S25", "2025"])

    def test_la_sec_no_cambia(self):
        """Falla si un emisor trimestral (sin semestres) deja de exigir sus cuatro trimestres o cambia de rótulo."""
        trimestres = [Periodo.de_meses(date(2025, 3, 31), 3), Periodo.de_meses(date(2025, 6, 30), 3)]
        m = multiplos.construir({}, trimestres, [self.FY24], self._precio(), 30.0e6)
        self.assertEqual((m.periodicidad, m.moneda, m.faltan["ttm"]), ("trimestral", "USD", "solo 2 trimestres contrastados: no hay TTM"))


class PerSinBpaPublicado(unittest.TestCase):
    FY24, FY25, S25, S26 = MultiplosSemestrales.FY24, MultiplosSemestrales.FY25, MultiplosSemestrales.S25, MultiplosSemestrales.S26
    _hechos, _precio = MultiplosSemestrales._hechos, MultiplosSemestrales._precio

    def test_quien_no_publica_bpa_tiene_per_con_su_beneficio_y_sus_acciones(self):
        """Falla si el PER de quien no imprime BPA en ningún estado (el PGC no lo pide) queda N/A teniendo beneficio de
        doce meses y acciones de la capitalización: la fórmula lo dice."""
        hechos = self._hechos()
        del hechos[("acciones_diluidas", self.S26)]
        m = multiplos.construir(hechos, [], [self.FY24, self.FY25], self._precio(), 30.0e6, moneda="EUR",
                                semestres=[self.S25, self.S26], no_aplican={"bpa_diluido": "no la imprime"})
        per = m.linea("PER (TTM)")
        self.assertAlmostEqual(per.valor, 4.0 / ((1.5e6 + 0.9e6 - 0.6e6) / 30.0e6))
        self.assertIn("no publica BPA", per.formula)
        # quien sí publica BPA y falta, sigue N/A: el atajo es solo para la partida que no existe
        sin = multiplos.construir(hechos, [], [self.FY24, self.FY25], self._precio(), 30.0e6, moneda="EUR", semestres=[self.S25, self.S26])
        self.assertIsNone(sin.linea("PER (TTM)").valor)


class ComparablesDeBME(unittest.TestCase):
    def tearDown(self):
        from tesis.plantillas import lexico
        lexico.fijar()

    def test_el_cuadro_22_va_en_la_moneda_del_informe(self):
        """Falla si el cuadro de comparables de un informe en EUR rotula «mill. USD», deja fuera a los comparables de BME
        por no ser USD o mezcla en una columna tamaños en dos monedas."""
        from types import SimpleNamespace
        from tesis.motor.comparables import Comparable
        from tesis.plantillas import informe, lexico, parte_e
        lexico.fijar(SimpleNamespace(mercado="bme", moneda="EUR"))
        bme_c = Comparable("PEER.MC", nombre="PEER", moneda="EUR", capitalizacion=50e6, ejercicio="12/2025", ingresos=30e6,
                           crecimiento=0.1, margen_ebit=0.08, mercado="bme", fuente="cuentas oficiales publicadas en BME; cierre oficial de BME Growth",
                           fecha_precio=date(2026, 10, 2))
        usd_c = Comparable("EPAM", nombre="EPAM", moneda="USD", capitalizacion=5e9, ejercicio="12/2025", ingresos=4e9)
        motor = SimpleNamespace(comparables=SimpleNamespace(filas=[bme_c, usd_c]), cap_mercado=20e6, fecha_precio=date(2026, 10, 2))
        d = parte_e.ParteE()
        parte_e._comparables(d, informe.Cuadros(), motor, {}, [], lambda p: str(p.fin.year), "Emisora", "EMI.MC")
        cuadro = d.cuadros["comparables"]
        self.assertIn("Capitalización (mill. EUR)", cuadro.columnas)
        rotulos = [f.rotulo for f in cuadro.filas]
        self.assertTrue(any("PEER.MC" in r for r in rotulos), rotulos)
        self.assertFalse(any("EPAM" in r for r in rotulos), rotulos)
        self.assertIn("EPAM (USD)", " ".join(cuadro.notas))
        self.assertNotIn("SEC", cuadro.fuente)


if __name__ == "__main__":
    unittest.main()


class ComunicacionesQueSeTraen(unittest.TestCase):
    """Lo que trae «Traer de BME» además de las cuentas: las comunicaciones que un analista cita."""

    def _elegidas(self, publicados):
        import re as _re
        return [clave for clave, patron, _ in bme._OIR_UTILES for d in publicados if _re.search(patron, f"{d.tipo} {d.titulo}")]

    def test_las_compras_de_directivos_y_los_avances_se_traen(self):
        """Falla si una compra de directivos titulada «Compras realizadas por…» o el avance de resultados de un semestre
        se quedan en la bolsa: son las comunicaciones que el analista cita en los apartados 6, 10 y 27."""
        doc = lambda tipo, titulo: bme.Documento(id="1", tipo=tipo, clase="OtherRelevantInformation", titulo=titulo,  # noqa: E731
                                                fecha=date(2026, 7, 30), hora="0800", ruta="/x.pdf", ejercicio=None, periodo="", tamano="")
        compras = doc("Operaciones realizadas por directivos", "Compras realizadas por directivos y personas vinculadas")
        avance = doc("Otra información relevante", "Avance de resultados del primer semestre")
        junta = doc("Otra información relevante", "Acuerdos de la Junta Ordinaria de Accionistas")
        self.assertIn("directivos", self._elegidas([compras]))
        self.assertIn("comunicacion", self._elegidas([avance]))
        self.assertIn("comunicacion", self._elegidas([junta]))

    def test_dos_registros_del_mismo_ejercicio_no_quitan_el_sitio_al_anterior(self):
        """Falla si la bolsa registra dos documentos de las cuentas de 2025 y con ellos se agota el cupo de ejercicios
        (el de 2024 se quedaba fuera), o si se trae lo publicado después de la fecha del informe."""
        import tempfile
        from types import SimpleNamespace
        doc = lambda i, ej, per, f: bme.Documento(id=i, tipo="", clase="", titulo=f"{ej} {per}", fecha=f, hora="", ruta=f"/{i}.pdf",  # noqa: E731
                                                  ejercicio=ej, periodo=per, tamano="")
        financiera = [doc("4", 2026, "1S", date(2026, 10, 30)), doc("3", 2025, "AN", date(2026, 4, 24)), doc("2", 2025, "AN", date(2026, 4, 24)),
                      doc("1", 2024, "AN", date(2025, 4, 30)), doc("0", 2023, "AN", date(2024, 4, 30))]
        traidos = []
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(bme, "informacion_financiera", return_value=financiera), \
                mock.patch.object(bme, "descargar", side_effect=lambda d, c: traidos.append(d.id) or Path(c) / f"{d.id}.pdf"):
            bme.traer(SimpleNamespace(clave_bolsa="X"), Path(tmp), anuales=2, semestrales=1, hoy=date(2026, 10, 2), comunicaciones=False)
        self.assertEqual(sorted(traidos), ["1", "2", "3"])


class SegmentosDelAnalista(unittest.TestCase):
    """Apartado 4 de un emisor sin XBRL: las líneas de negocio de la memoria, copiadas por el analista con su cita."""

    def test_lineas_verificadas_y_cuadradas_con_la_cifra_de_negocios(self):
        """Falla si un emisor de BME no puede tener cuadro de segmentos (el 4.2 bloquearía siempre), si se acepta una cifra
        que no está en la línea citada o si no se cuadra la suma con la cifra de negocios consolidada."""
        from tesis.datos import segmentos
        fy = Periodo(fin=date(2025, 12, 31), inicio=date(2025, 1, 1))
        pagina = ("20. Ingresos y gastos\nIngresos Digital Business 12.246.341,18 260.348,19 107.602,97 12.614.292,34\n"
                  "Ingresos Tech 2.920.352,07 453.250,70 158.083,36 3.531.686,13\n")
        textos = {"ccaa.pdf": pagina, "ccaa.pdf#7": pagina}
        cita = lambda t: [{"doc": "ccaa.pdf", "pag": "7", "texto": t}]                       # noqa: E731
        lista = [{"linea": "Digital Business", "tipo": "segmento", "valores": {fy.clave: 12614292.34},
                  "evidencia": cita("Ingresos Digital Business 12.246.341,18 260.348,19 107.602,97 12.614.292,34")},
                 {"linea": "Tech", "tipo": "segmento", "valores": {fy.clave: 9999999.0},
                  "evidencia": cita("Ingresos Tech 2.920.352,07 453.250,70 158.083,36 3.531.686,13")}]
        total = {fy: de_valor("ingresos", fy, 16834046.30, Capa.DOCUMENTO, None, unidad="EUR", certeza=Certeza.ALTA)}
        s = segmentos.del_analista(lista, [fy], total, textos, 0.9, "EUR")
        self.assertEqual([l.rotulo for l in s.lineas], ["Digital Business"])
        self.assertAlmostEqual(s.lineas[0].valores[fy].valor, 12614292.34)
        self.assertEqual(s.lineas[0].valores[fy].origen.pagina, 7)
        self.assertIn("la cifra no está en el literal citado", s.faltan[f"Tech {fy.clave}"])
        self.assertEqual(s.periodos, [fy])
        lista[1]["valores"] = {fy.clave: 3531686.13}
        s = segmentos.del_analista(lista, [fy], total, textos, 0.9, "EUR")
        self.assertTrue(any("no suman" in c for c in s.cuadres), s.cuadres)      # 12,6 + 3,5 ≠ 16,8 (falta Product): se dice la diferencia


class EscalaDeLasCifras(unittest.TestCase):
    """Un emisor de 17 millones de ingresos no se puede leer en millones sin decimales («Total activo 8 12 10»)."""

    def tearDown(self):
        from tesis import formato
        formato.fijar_escala(None)

    def test_los_millones_llevan_decimales_en_un_emisor_pequeno(self):
        """Falla si las cifras en millones de un emisor pequeño salen sin decimales, o si los de uno grande cambian."""
        from tesis import formato
        formato.fijar_escala(16_834_046.30)
        self.assertEqual(formato.mln(12_614_292.34), "12,61")
        self.assertEqual(formato.celda(de_valor("ingresos", Periodo(fin=date(2025, 12, 31), inicio=date(2025, 1, 1)), 10_314_343.63,
                                                Capa.DOCUMENTO, None, unidad="EUR", certeza=Certeza.ALTA)).texto, "10,31")
        formato.fijar_escala(44_284_000_000)
        self.assertEqual(formato.mln(12_614_292_340), "12.614")
        self.assertEqual(formato.mln(12_614_292.34, 1), "12,6")              # quien pide sus decimales los conserva


class NoSignificativo(unittest.TestCase):
    def test_una_ratio_sin_sentido_se_imprime_ns_y_no_na(self):
        """Falla si «deuda neta / EBITDA» con el EBITDA negativo se imprime «N/A»: hay dato y la ratio no significa nada
        («n. s.», con el motivo), y un «N/A» en el resumen o en la portada bloquea la emisión."""
        from tesis import formato
        from tesis.datos.hechos import na
        h = na("dfn_ebitda", Periodo(fin=date(2024, 12, 31), inicio=date(2024, 1, 1)), "no significativo: el EBITDA es negativo (−1 M)")
        c = formato.celda(h, "x")
        self.assertEqual(c.texto, "n. s.")
        self.assertIn("EBITDA es negativo", c.nota)
        self.assertEqual(formato.celda(na("fcf", Periodo(fin=date(2023, 12, 31), inicio=date(2023, 1, 1)), "sin dato")).texto, "N/A")


class AvisoDeBeta(unittest.TestCase):
    def test_el_r2_bajo_no_avisa_si_ya_se_usa_la_beta_bottom_up(self):
        """Falla si con la beta bottom-up elegida el informe sigue avisando de que «conviene la beta bottom-up»."""
        from tesis.motor.wacc import Beta, calcular
        reg = Beta(0.5, 0.67, 0.01, 0.2, 100, date(2024, 9, 25), date(2026, 9, 25), "semanal")
        aviso = lambda origen: [a for a in calcular(0.03, date(2026, 9, 25), 0.9, origen, 0.05, 0.03, 0.065, "", 0.25, 20.0, 4.0,
                                                    reg).avisos if "bottom-up" in a]                              # noqa: E731
        self.assertEqual(aviso("bottom-up: β desapalancada 0.77 reapalancada"), [])
        self.assertEqual(len(aviso("regresión semanal de 2 años")), 1)


class RoeConPatrimonioNegativo(unittest.TestCase):
    def test_la_roe_no_significa_nada_si_el_patrimonio_es_negativo_en_un_cierre(self):
        """Falla si la ROE de un ejercicio con el patrimonio negativo en uno de sus dos cierres sale como cifra (−809 % sobre
        un patrimonio medio que roza el cero) en vez de «no significativo» con su motivo."""
        from tesis.datos import derivados
        fy = Periodo(fin=date(2025, 12, 31), inicio=date(2025, 1, 1))
        h = lambda c, p, v: de_valor(c, p, v, Capa.DOCUMENTO, None, unidad="EUR", certeza=Certeza.ALTA)      # noqa: E731
        hechos = {("beneficio_neto", fy): h("beneficio_neto", fy, -787_922.0),
                  ("patrimonio", Periodo.instante(date(2025, 12, 31))): h("patrimonio", Periodo.instante(date(2025, 12, 31)), -623_089.0),
                  ("patrimonio", Periodo.instante(date(2024, 12, 31))): h("patrimonio", Periodo.instante(date(2024, 12, 31)), 817_898.0)}
        roe = derivados.calcular(hechos, [fy], [Periodo.instante(date(2025, 12, 31)), Periodo.instante(date(2024, 12, 31))])[("roe", fy)]
        self.assertFalse(roe.hay_dato)
        self.assertTrue(roe.motivo.startswith("no significativo"), roe.motivo)


class ApalancamientoSemestral(unittest.TestCase):
    def test_deuda_neta_ebitda_vigente_con_el_ejercicio_de_un_emisor_semestral(self):
        """Falla si la deuda neta / EBITDA vigente de un emisor que publica por semestres sale «sin dato» (solo se buscaban
        cuatro trimestres): la lista de comprobación decía «sin deuda neta o sin EBITDA» con 13,6x en el cuadro 1."""
        from tesis.datos import derivados
        fy = Periodo(fin=date(2025, 12, 31), inicio=date(2025, 1, 1))
        cierre = Periodo.instante(date(2025, 12, 31))
        h = lambda c, p, v: de_valor(c, p, v, Capa.DOCUMENTO, None, unidad="EUR", certeza=Certeza.ALTA)      # noqa: E731
        r = derivados.deuda_neta_ebitda_vigente({("deuda_neta", cierre): h("deuda_neta", cierre, 3_520_000.0),
                                                 ("ebitda", fy): h("ebitda", fy, 259_000.0)})
        self.assertIsNotNone(r)
        self.assertAlmostEqual(r[0], 3_520_000 / 259_000)
        self.assertEqual(r[3], fy)


class DirectivosDeBME(unittest.TestCase):
    """Apartado 34 de un emisor de BME: las notificaciones del modelo de abuso de mercado que publica el propio emisor."""
    NOTIFICACION = ("FORMULARIO DE NOTIFICACIÓN DE LAS OPERACIONES DE LAS PERSONAS CON RESPONSABILIDADES DE DIRECCIÓN\n"
                    "a) Nombre y apellidos - Razón social  |  Name and surname - Company name\nSOCIEDAD DEL CONSEJERO, S.L.\n"
                    "a) Cargo - posición  |  Job title\nConsejero Delegado\n"
                    "ES0105857033 Acción Compra 09/09/2026 GROW 150,00 0,87 EUR\n150,00 0,87\n"
                    "ES0105857033 Acción Compra 08/09/2026 GROW 1.300,00 0,86 EUR\n"
                    "ES0105857033 Acción Otros 05/06/2026 XOFF 20000,00 7,55 EUR\n")

    def test_las_operaciones_se_leen_de_la_notificacion(self):
        """Falla si las compras de directivos que el emisor publica en BME no llegan al apartado 34 (salía «no aplica: no hay
        Form 4» con una docena de notificaciones en el expediente), o si se leen mal el titular, el volumen o el precio."""
        from tesis.datos import directivos_bme
        ins = directivos_bme.insiders([("notificacion.pdf", self.NOTIFICACION)], date(2026, 10, 2))
        self.assertIsNotNone(ins)
        self.assertEqual(ins.fuente, "bme")
        self.assertEqual(ins.ultimas[0], ("SOCIEDAD DEL CONSEJERO, S.L.", "Consejero Delegado", date(2026, 9, 9), "Compra", 150.0, 0.87))
        self.assertEqual(ins.ultimas[1][4], 1300.0)
        self.assertEqual(dict((r, (a, b)) for r, a, b in ins.operaciones)["Compras"], (2, 2))
        self.assertEqual(dict((r, (a, b)) for r, a, b in ins.acciones)["Acciones compradas"], (1450.0, 1450.0))
        self.assertIsNone(directivos_bme.insiders([("otra.pdf", "Acuerdos de la Junta General")], date(2026, 10, 2)))
