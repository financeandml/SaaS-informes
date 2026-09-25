"""Las empresas que cierran por semanas (52/53), no a fin de mes. Sin red.

El caso que las trajo (23/09/2026): Qualcomm cierra el domingo más cercano a fin de septiembre —26/09/2021,
25/09/2022, 24/09/2023, 29/09/2024, 28/09/2025— y su informe salía con 405 huecos y **cero cifras confirmadas**.
Tres fallos encadenados, y ninguno se veía como un error: se veía como una empresa sin datos.

1. El ejercicio contado por número de mes daba trece meses, y el informe elige los anuales con `meses == 12`.
2. Los periodos se construían con aritmética («el mismo día del año pasado»), y ninguno coincidía con los hechos de
   la SEC, que van fechados con el cierre real.
3. La cabecera del documento («Year Ended September 28, 2025») se redondeaba a fin de mes, y venía además en un solo
   token con los tres cierres seguidos, así que las columnas del 10-K se quedaban sin periodo: ni una cifra leída.
"""

import unittest
from datetime import date

from tesis.verificacion import contraste
from tesis.fuentes import sec
from tesis.datos.extractor import Linea, Token, _columnas_de, _es_por_accion
from tesis.datos.hechos import Periodo


def _facts(pares, concepto="Revenues"):
    filas = [{"start": i, "end": f, "val": 1, "form": "10-K", "filed": "2025-11-05", "accn": "x"} for i, f in pares]
    return {"facts": {"us-gaap": {concepto: {"units": {"USD": filas}}}}}


def _linea(*trozos):
    """Una línea de cabecera: cada trozo es (texto, x0, x1) y se convierte en un token con su caja."""
    return Linea([Token(t, x0, 700, x1, 710) for t, x0, x1 in trozos])


class Calendario(unittest.TestCase):
    def test_los_cierres_los_pone_el_emisor_no_la_aritmetica(self):
        """Falla si el calendario se calcula en vez de leerse: los cierres de Qualcomm no caen el mismo día dos años
        seguidos, y un periodo inventado no casa con ningún hecho de la SEC."""
        facts = _facts([("2023-09-25", "2024-09-29"), ("2024-09-30", "2025-09-28"),
                        ("2025-09-29", "2025-12-28"), ("2024-09-30", "2025-06-29")])
        anuales = sec.calendario(facts, 12)
        self.assertEqual([p.fin for p in anuales], [date(2024, 9, 29), date(2025, 9, 28)])
        self.assertEqual(anuales[-1].inicio, date(2024, 9, 30))
        self.assertEqual([p.fin for p in sec.calendario(facts, 3)], [date(2025, 12, 28)])
        self.assertEqual([p.fin for p in sec.calendario(facts, 9)], [date(2025, 6, 29)])

    def test_de_dos_comienzos_para_el_mismo_cierre_manda_el_repetido(self):
        """Falla si un intervalo suelto —el de una filial, el de un concepto con otro arranque— se lleva el cierre:
        el ejercicio bueno es el que usan casi todos los conceptos."""
        facts = {"facts": {"us-gaap": {
            "Revenues": {"units": {"USD": [{"start": "2024-09-30", "end": "2025-09-28", "val": 1, "form": "10-K",
                                            "filed": "2025-11-05", "accn": "x"}] * 9
                                   + [{"start": "2024-10-07", "end": "2025-09-28", "val": 1, "form": "10-K",
                                       "filed": "2025-11-05", "accn": "y"}]}}}}}
        self.assertEqual(sec.calendario(facts, 12)[0].inicio, date(2024, 9, 30))

    def test_el_documento_y_la_sec_casan_aunque_empiecen_distinto(self):
        """Falla si se exige el periodo entero: el documento rotula «Year Ended September 28, 2025» —de ahí salen el
        cierre y la duración, no el día de comienzo— y su columna nunca casaría con el hecho de la SEC."""
        del_documento = Periodo.de_meses(date(2025, 9, 28), 12)          # empieza el 1 de octubre, calculado
        de_la_sec = Periodo(fin=date(2025, 9, 28), inicio=date(2024, 9, 30))
        self.assertNotEqual(del_documento, de_la_sec)
        self.assertTrue(contraste._mismo_periodo(del_documento, de_la_sec))
        self.assertFalse(contraste._mismo_periodo(del_documento, Periodo.de_meses(date(2025, 9, 28), 3)))
        self.assertFalse(contraste._mismo_periodo(del_documento, Periodo.instante(date(2025, 9, 28))))


class CabeceraDelDocumento(unittest.TestCase):
    def test_la_columna_se_fecha_con_el_dia_que_dice_la_cabecera(self):
        """Falla si la cabecera se redondea a fin de mes: la columna quedaría fechada el 30 de septiembre, dos días
        después que el hecho de la SEC, y ni una cifra del 10-K casaría con su fuente."""
        lineas = [_linea(("Year Ended", 100, 160)),
                  _linea(("September 28, September 29, September 24,", 200, 500)),
                  _linea(("2025", 220, 250), ("2024", 320, 350), ("2023", 420, 450))]
        columnas, _ = _columnas_de(lineas)
        self.assertEqual([c.fin for c in columnas], [date(2025, 9, 28), date(2024, 9, 29), date(2023, 9, 24)])
        self.assertEqual([c.periodo.meses for c in columnas], [12, 12, 12])

    def test_los_tres_cierres_en_un_solo_token_se_reparten_por_su_posicion(self):
        """Falla si los cierres se buscan token a token: pdfium devuelve los tres en uno solo, y la cabecera del
        10-K entero se quedaba «sin mes», es decir, sin periodo y sin una sola cifra."""
        lineas = [_linea(("As of", 100, 140)),
                  _linea(("September 28, September 29,", 200, 400)),
                  _linea(("2025", 220, 250), ("2024", 340, 370))]
        columnas, _ = _columnas_de(lineas)
        self.assertEqual([c.fin for c in columnas], [date(2025, 9, 28), date(2024, 9, 29)])
        self.assertTrue(all(c.periodo.es_instante for c in columnas))


class RecuentoDeAcciones(unittest.TestCase):
    def test_el_bloque_de_acciones_no_es_un_importe_por_accion(self):
        """Falla si «Shares used in per share calculations» se toma por un importe por acción: sus 1.096 se leerían
        sin escalar y esa fila («Basic») se colaba como BPA, discrepando de la SEC por mil millones."""
        self.assertFalse(_es_por_accion("Shares used in per share calculations Basic"))
        self.assertFalse(_es_por_accion("Weighted-average shares outstanding Basic"))
        self.assertTrue(_es_por_accion("Basic earnings (loss) per share Net income"))
        self.assertTrue(_es_por_accion("Earnings per share Basic"))


if __name__ == "__main__":
    unittest.main()
