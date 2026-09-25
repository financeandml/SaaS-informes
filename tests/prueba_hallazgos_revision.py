"""Los hallazgos de la revisión adversarial del 21/09/2026: cada prueba reintroduce el fallo que cazó. Sin red."""

import socket
import tempfile
import unittest
from datetime import date
from pathlib import Path

from tesis import cartas, comparables, historial, multiplos, saas, secciones
from tesis.dcf import Celda as CeldaLibro

RAIZ = Path(__file__).resolve().parents[1]


class Cifras(unittest.TestCase):
    def test_el_formato_de_la_celda_del_libro_decide_la_escala(self):
        """Falla si un WACC 0,105 con formato «0.00%» se imprime como «0» porque su rótulo («Pesimista») no lleva palabra clave,
        o si 0,0325 con formato «0.0%» sale como 3,2 % mientras el cuadro de escenarios dice 3,25 %."""
        self.assertEqual(secciones._fmt(0.105, "musd", CeldaLibro("Supuestos", "C32", None, "0.00%")), "10,50\u00a0%")
        self.assertEqual(secciones._fmt(0.0325, "%", CeldaLibro("Reverse DCF", "C9", None, "0.0%")), "3,25\u00a0%")
        self.assertEqual(secciones._fmt(26.7, "x", CeldaLibro("Resumen", "D20", None, "0.00\\x")), "26,70x")
        self.assertEqual(secciones._fmt(9269.6, "musd", CeldaLibro("Base", "C26", None, "#,##0;\\(#,##0\\);\\-")), "9.270")

    def test_la_cifra_de_la_bolsa_se_imprime_en_la_convencion_del_documento(self):
        """Falla si «$273,821» o «4,164» (miles con coma, del proveedor) se imprimen tal cual: en el documento se leen como decimales."""
        self.assertEqual(secciones._cifra_bolsa("$273,821"), "273.821")
        self.assertEqual(secciones._cifra_bolsa("4,164"), "4.164")
        self.assertEqual(secciones._cifra_bolsa("91.60%"), "91,60\u00a0%")
        self.assertEqual(secciones._cifra_bolsa("n/a"), "n/a")


class Cartas(unittest.TestCase):
    TABLA = ("<html><body><table><tr><td>(in millions except per share data)</td><td>Q1'26</td><td>Q2'26</td><td>Q3'26 Forecast</td></tr>"
             "<tr><td>Revenue</td><td>$</td><td>12,250</td><td>—</td><td>$</td><td>12,860</td></tr>"
             "<tr><td>Diluted EPS</td><td>$(0.12)</td><td>$0.80</td><td>$0.82</td></tr></table></body></html>")

    def test_una_celda_no_numerica_no_desplaza_la_fila(self):
        """Falla si la previsión de 3T26 pasa por cifra publicada de 2T26 al saltarse el «—», o si «$(0.12)» no se lee como negativo."""
        c = cartas._leer(self.TABLA, date(2026, 7, 16), "A", "u")
        self.assertEqual(c.prevision[("3T26", "Revenue")], 12860)
        self.assertNotIn(("2T26", "Revenue"), c.reales)
        self.assertEqual(c.reales[("1T26", "Diluted EPS")], -0.12)
        self.assertEqual(c.avisos, [])
        corta = self.TABLA.replace("<td>$(0.12)</td><td>$0.80</td><td>$0.82</td>", "<td>0.80</td>")
        c = cartas._leer(corta, date(2026, 7, 16), "A", "u")
        self.assertNotIn(("1T26", "Diluted EPS"), c.reales)         # una fila corta no se empareja a ciegas
        self.assertTrue(any("Diluted EPS" in a for a in c.avisos), c.avisos)

    def test_las_cifras_por_accion_van_a_la_base_actual_y_el_split_repetido_cuenta_una_vez(self):
        """Falla si una previsión y un real anteriores al split 10:1 se imprimen sin dividir (5,10 → 5,40 frente a la sección C en 0,54),
        o si el 7:1 de 2015, que la SEC registra con tres fechas, divide por 343."""
        splits = [(date(2015, 6, 23), 7.0), (date(2015, 6, 30), 7.0), (date(2015, 7, 14), 7.0), (date(2025, 11, 14), 10.0)]
        self.assertEqual(cartas._splits_unicos(splits), [(date(2015, 6, 23), 7.0), (date(2025, 11, 14), 10.0)])
        antigua = cartas.Carta(date(2024, 7, 18), "A", "u", "2T24", {}, {("3T24", "Diluted EPS"): 5.10})
        real = cartas.Carta(date(2024, 10, 17), "B", "u", "3T24", {("3T24", "Diluted EPS"): 5.40}, {})
        g = cartas.guias_frente_a_real([antigua, real], {}, splits=splits)[0]
        self.assertAlmostEqual(g.prevista, 0.51)
        self.assertAlmostEqual(g.real, 0.54)
        self.assertIn("split", g.nota)
        self.assertAlmostEqual(g.desvio, 0.30 / 5.10)

    def test_una_prevision_nula_no_inventa_un_desvio(self):
        """Falla si con previsión 0 el desvío sale 0,0 % en vez de quedar sin definir."""
        antigua = cartas.Carta(date(2024, 7, 18), "A", "u", "2T24", {}, {("3T24", "Diluted EPS"): 0.0})
        real = cartas.Carta(date(2024, 10, 17), "B", "u", "3T24", {("3T24", "Diluted EPS"): 0.85}, {})
        self.assertIsNone(cartas.guias_frente_a_real([antigua, real], {})[0].desvio)


class Fuentes(unittest.TestCase):
    def test_el_ultimo_anual_es_el_cierre_mas_reciente_entre_conceptos(self):
        """Falla si «Revenues» de 2017 gana a «RevenueFromContract…» de 2025 solo por ir antes en la lista de conceptos."""
        facts = {"facts": {"us-gaap": {
            "Revenues": {"units": {"USD": [{"start": "2017-01-01", "end": "2017-12-31", "val": 1000, "form": "10-K", "fp": "FY"}]}},
            "RevenueFromContractWithCustomerExcludingAssessedTax": {"units": {"USD": [{"start": "2025-01-01", "end": "2025-12-31", "val": 5000, "form": "10-K", "fp": "FY"}]}}}}}
        self.assertEqual(comparables._ultimo_anual(facts, comparables._INGRESOS)[:2], (5000.0, date(2025, 12, 31)))

    def test_una_fila_de_sorpresas_con_negativos_se_lee(self):
        """Falla si «FQ2 2026 (0.10) 0.05 150.00%» no casa y el trimestre desaparece del cuadro sin motivo."""
        m = historial._FILA_TRIMESTRE.search("FQ2 2026 (0.10) 0.05 150.00%\n")
        self.assertIsNotNone(m)
        self.assertEqual((historial._con_parentesis(m.group(3)), historial._con_parentesis(m.group(4))), (-0.10, 0.05))

    def test_un_cierre_de_29_de_febrero_no_rompe_los_multiplos(self):
        self.assertEqual(multiplos._un_anio_antes(date(2028, 2, 29)), date(2027, 2, 28))
        self.assertEqual(multiplos._un_anio_antes(date(2026, 6, 30)), date(2025, 6, 30))


class Analista(unittest.TestCase):
    def test_una_ruta_absoluta_de_windows_no_sale_de_la_carpeta(self):
        """Falla si «GET /C:\\…\\fuera.css» (sin «/» ni «..») sirve un fichero de fuera de tesis/tablero: en Windows, unir una ruta absoluta descarta la base."""
        with tempfile.TemporaryDirectory() as tmp:
            fuera = Path(tmp, "fuera.css")
            fuera.write_text("body{}", encoding="utf-8")
            servidor, _ = saas.servir(0, en_hilo=True)
            try:
                with socket.create_connection(("127.0.0.1", servidor.server_address[1]), timeout=10) as s:
                    s.sendall(f"GET /{fuera} HTTP/1.0\r\nHost: x\r\n\r\n".encode())
                    r = b""
                    while True:
                        trozo = s.recv(65536)
                        if not trozo:
                            break
                        r += trozo
            finally:
                servidor.shutdown()
                servidor.server_close()
        self.assertTrue(r.startswith(b"HTTP/1.0 404"), r[:60])
        self.assertNotIn(b"body{}", r)


if __name__ == "__main__":
    unittest.main()
