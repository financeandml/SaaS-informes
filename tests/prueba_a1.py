"""A1 · Precio, sesión y volumen desde el histórico oficial (fallos [1], [2], [42] y [66] de la auditoría del 27/09/2026).

La ficha de Nasdaq fecha el cierre del viernes con el jueves («Sep 24» para el cierre del 25/09). Con esa fecha el
precio salía N/A en el log mientras el motor lo usaba, el «cierre anterior» se comparaba con la sesión equivocada y el
volumen se atribuía a otro día. Aquí la fecha, el volumen y el cierre anterior salen del histórico oficial.
"""

import unittest
from datetime import date

from tesis.fuentes import precio
from tesis.fuentes.precio import Cotizacion, Sesion
from tesis.plantillas.secciones import _ultima_operacion

VIERNES, JUEVES, MIERCOLES = date(2026, 9, 25), date(2026, 9, 24), date(2026, 9, 23)
SESIONES = {MIERCOLES: Sesion(None, None, None, 144.56, 30e6), JUEVES: Sesion(None, None, None, 139.54, 56_629_390),
            VIERNES: Sesion(None, None, None, 137.10, 23_671_010)}


def _cot(**cambios):
    base = dict(precio=137.10, fecha=JUEVES, fuente="Nasdaq (web del mercado)", oficial=True, url="u", sesion="Closed",
                volumen=23_671_072, cierre_anterior=139.54, hora="4:00 PM ET")
    base.update(cambios)
    return Cotizacion(**base)


class Sesion_(unittest.TestCase):
    def test_la_fecha_es_la_de_la_sesion_que_cierra_a_ese_precio(self):
        """Falla si la fecha de la ficha («Sep 24») manda sobre el histórico, que dice que 137,10 es el cierre del 25."""
        c = precio._con_sesion(_cot(), SESIONES)
        self.assertEqual(c.fecha, VIERNES)
        self.assertEqual(c.volumen, 23_671_010)          # el del histórico, no el de la ficha
        self.assertEqual(c.hora, "")                     # la hora de la ficha era de otro día

    def test_con_la_sesion_abierta_no_se_toca(self):
        """Falla si un último cruce en sesión abierta se convierte en el cierre de otro día."""
        c = _cot(sesion="Open", fecha=VIERNES, precio=139.54)
        self.assertEqual(precio._con_sesion(c, SESIONES), c)

    def test_sin_sesion_que_cuadre_manda_la_ficha(self):
        """Falla si se inventa una fecha cuando ningún cierre del histórico iguala el precio."""
        c = _cot(precio=150.0)
        self.assertEqual(precio._con_sesion(c, SESIONES), c)

    def test_la_ventana_llega_al_dia_de_emision(self):
        """Falla si el histórico de evidencia acaba en la fecha de la ficha y no en el día de emisión."""
        desde, hasta = precio._ventana(date(2026, 9, 27))
        self.assertEqual(hasta, date(2026, 9, 27))
        self.assertLessEqual(desde, date(2026, 9, 6))


class Cadena(unittest.TestCase):
    def test_la_ultima_operacion_de_la_cadena_se_fecha_con_el_historico(self):
        """Falla si «AS OF SEP 24» se imprime como fecha de un precio que es el cierre del 25."""
        texto = _ultima_operacion("LAST TRADE: $137.10 (AS OF SEP 24, 2026)", SESIONES)
        self.assertIn("el 25/09/2026", texto)
        self.assertIn("137,10 USD", texto)

    def test_sin_historico_queda_la_fecha_del_literal(self):
        self.assertIn("el 24/09/2026", _ultima_operacion("LAST TRADE: $137.10 (AS OF SEP 24, 2026)"))


if __name__ == "__main__":
    unittest.main()
