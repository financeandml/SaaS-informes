"""Las reglas de lectura de XBRL, sobre el companyfacts real de Netflix en caché."""

import unittest
from datetime import date

from tests import contacto_sec_de_prueba, hay_cache_sec
from tesis.datos import campos
from tesis.fuentes import sec
from tesis.datos.hechos import Capa, Contraste, Estado, Periodo


@unittest.skipUnless(hay_cache_sec(), "sin companyfacts de NFLX en cache_sec/")
class ReglasXbrl(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        contacto_sec_de_prueba()
        cls.facts, cls.obtenido = sec.companyfacts("0001065280")

    def test_solo_10k_10q_valen(self):
        """Falla si vuelve a ganar «el último presentado» sin filtrar el formulario: la DEF 14A
        de abril de 2026 trae NetIncomeLoss FY2025 redondeado a 10.981.000.000."""
        h = sec.hechos_xbrl(self.facts, campos.campo("beneficio_neto"), self.obtenido)[Periodo.anual(date(2025, 12, 31))]
        self.assertEqual(h.valor, 10_981_201_000)
        self.assertEqual(h.origen.formulario, "10-K")

    def test_cuarto_trimestre_no_existe_y_se_deriva(self):
        """Falla si el 4T sale como hecho SEC o si la derivación no cuadra con el ejercicio."""
        c = campos.campo("ingresos")
        h = sec.hechos_xbrl(self.facts, c, self.obtenido, [Periodo.de_meses(date(2025, 12, 31), 3)])
        self.assertIs(list(h.values())[0].estado, Estado.NA)
        todos = sec.hechos_xbrl(self.facts, c, self.obtenido)
        q4 = sec.q4_derivado(todos[Periodo.anual(date(2025, 12, 31))], todos[Periodo.de_meses(date(2025, 9, 30), 9)])
        self.assertEqual(q4.valor, 12_050_762_000)
        self.assertIs(q4.capa, Capa.DERIVADO)
        self.assertIn("9M25", q4.formula)

    def test_dividendos_ausentes_son_na_con_motivo(self):
        """Falla si un concepto ausente sale como cero: la ausencia no es un dato."""
        h = sec.hechos_xbrl(self.facts, campos.campo("dividendos"), self.obtenido, [Periodo.anual(date(2025, 12, 31))])
        h = list(h.values())[0]
        self.assertIs(h.estado, Estado.NA)
        self.assertTrue(h.motivo)

    def test_split_es_hecho_sec_y_reexpresa_como_derivado(self):
        """Falla si el BPA FY2021 (presentado en 2022, antes del split 10:1) no se divide por 10 con fórmula."""
        ajustes = sec.splits(self.facts)
        self.assertIn((date(2025, 11, 14), 10.0), [(f, r) for f, r, _ in ajustes])
        h = sec.hechos_xbrl(self.facts, campos.campo("bpa_basico"), self.obtenido)[Periodo.anual(date(2021, 12, 31))]
        a = sec.ajustar_por_split(h, ajustes, por_accion=True)
        self.assertAlmostEqual(a.valor, h.valor / 10, places=6)
        self.assertIs(a.capa, Capa.DERIVADO)
        self.assertIn("÷ 10", a.formula)
        # lo presentado después del split no se toca
        h25 = sec.hechos_xbrl(self.facts, campos.campo("bpa_basico"), self.obtenido)[Periodo.anual(date(2025, 12, 31))]
        self.assertIs(sec.ajustar_por_split(h25, ajustes, True), h25)

    def test_sinonimo_por_periodo(self):
        """Falla si el primer sinónimo presente bloquea los periodos que solo trae el segundo."""
        c = campos.campo("tecnologia")   # Netflix declara ResearchAndDevelopmentExpense
        h = sec.hechos_xbrl(self.facts, c, self.obtenido)
        self.assertIn(Periodo.anual(date(2025, 12, 31)), h)
        self.assertEqual(h[Periodo.anual(date(2025, 12, 31))].valor, 3_391_390_000)


if __name__ == "__main__":
    unittest.main()
