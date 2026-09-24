"""Los tres estados y las reglas del constructor de `Hecho`."""

import unittest
from datetime import date

from tesis.hechos import Capa, Certeza, Contraste, Estado, Hecho, Origen, Periodo, de_valor, derivar, na


class Estados(unittest.TestCase):
    def test_na_sin_motivo_no_se_construye(self):
        """Falla si el constructor deja de exigir `motivo` en un N/A."""
        with self.assertRaises(ValueError):
            Hecho("x", Periodo.anual(date(2025, 12, 31)), None, Estado.NA, Capa.SEC)

    def test_cero_no_es_valor_ni_na(self):
        """Falla si `de_valor` deja de distinguir el cero del valor."""
        h = de_valor("dividendos", Periodo.anual(date(2025, 12, 31)), 0, Capa.SEC, None)
        self.assertIs(h.estado, Estado.CERO)
        with self.assertRaises(ValueError):
            Hecho("x", Periodo.anual(date(2025, 12, 31)), 0, Estado.VALOR, Capa.SEC)

    def test_documento_exige_certeza(self):
        """Falla si un hecho de documento puede nacer sin certeza (regla 3)."""
        with self.assertRaises(ValueError):
            Hecho("x", Periodo.anual(date(2025, 12, 31)), 1.0, Estado.VALOR, Capa.DOCUMENTO)


class Derivados(unittest.TestCase):
    def test_derivado_con_entrada_na_es_na_y_dice_cual(self):
        """Falla si un derivado se calcula con un cero donde falta una entrada."""
        p = Periodo.anual(date(2025, 12, 31))
        ingresos = de_valor("ingresos", p, 100.0, Capa.SEC, None)
        coste = na("coste_ingresos", p, "no publicado")
        m = derivar("margen_bruto", p, "(I − C) / I", {"ingresos": ingresos, "coste_ingresos": coste}, lambda ingresos, coste_ingresos: 1)
        self.assertIs(m.estado, Estado.NA)
        self.assertIn("coste_ingresos", m.motivo)
        self.assertIn("no publicado", m.motivo)

    def test_derivado_guarda_formula_y_entradas(self):
        """Falla si el derivado pierde la fórmula o las entradas (regla 9: un hecho, una fuente)."""
        p = Periodo.anual(date(2025, 12, 31))
        a = de_valor("cfo", p, 10.0, Capa.SEC, None); b = de_valor("capex", p, 4.0, Capa.SEC, None)
        f = derivar("fcf", p, "CFO − Capex", {"cfo": a, "capex": b}, lambda cfo, capex: cfo - capex)
        self.assertEqual(f.valor, 6.0)
        self.assertEqual(f.formula, "CFO − Capex")
        self.assertIs(f.entradas[0], a)
        self.assertIs(f.contraste, Contraste.DERIVADO)


class Periodos(unittest.TestCase):
    def test_claves(self):
        self.assertEqual(Periodo.anual(date(2025, 12, 31)).clave, "FY2025")
        self.assertEqual(Periodo.de_meses(date(2026, 6, 30), 3).clave, "2T26")
        self.assertEqual(Periodo.de_meses(date(2026, 6, 30), 6).clave, "6M26")
        self.assertEqual(Periodo.instante(date(2026, 6, 30)).clave, "@2026-06-30")
        self.assertEqual(Periodo.de_meses(date(2025, 12, 31), 3).inicio, date(2025, 10, 1))

    def test_el_ejercicio_de_52_semanas_son_doce_meses(self):
        """Falla si el ejercicio de las empresas que cierran el domingo más cercano a fin de mes —Qualcomm, Apple,
        Cisco— cuenta trece meses: el informe elige los anuales con `meses == 12`, así que la empresa se quedaba sin
        una sola columna anual y todas sus cifras salían N/A (Qualcomm: 405 huecos y cero confirmadas)."""
        fy25 = Periodo(fin=date(2025, 9, 28), inicio=date(2024, 9, 29))      # 10-K de Qualcomm, ejercicio 2025
        self.assertEqual(fy25.meses, 12)
        self.assertEqual(fy25.clave, "FY2025")
        fy21 = Periodo(fin=date(2021, 9, 26), inicio=date(2020, 9, 28))      # el de 53 semanas
        self.assertEqual(fy21.meses, 12)
        trimestre = Periodo(fin=date(2026, 6, 28), inicio=date(2026, 3, 30))
        self.assertEqual(trimestre.meses, 3)
        self.assertEqual(Periodo(fin=date(2026, 6, 28), inicio=date(2025, 9, 29)).meses, 9)


if __name__ == "__main__":
    unittest.main()
