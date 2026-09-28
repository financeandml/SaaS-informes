"""Gráfico de deuda neta con caja neta (28/09/2026).

Microsoft tiene caja neta: su deuda neta es negativa todos los años. El gráfico fijaba el eje de 0 hacia arriba, las
cifras de las barras quedaban fuera, el recorte «tight» las incluía y el SVG medía 4,8 millones de puntos de alto. El
PDF salía con 7.130 páginas en blanco detrás del gráfico.
"""

import re
import unittest
from datetime import date

from tesis.datos.hechos import Capa, Periodo, de_valor
from tesis.plantillas import graficos


class CajaNeta(unittest.TestCase):
    def test_deuda_neta_negativa_cabe_en_el_grafico(self):
        """Falla si con deuda neta negativa el gráfico se desborda (alto de miles de puntos) o pierde el signo."""
        anios = [Periodo.anual(date(a, 6, 30)) for a in range(2022, 2027)]
        barras = [de_valor("deuda_neta", p, -v * 1e6, Capa.SEC, None)
                  for p, v in zip(anios, (60_000, 50_000, 30_000, 40_000, 35_000))]
        lineas = [de_valor("dfn_ebitda", p, -v, Capa.SEC, None, unidad="x") for p, v in zip(anios, (0.6, 0.5, 0.2, 0.3, 0.2))]
        svg, _ = graficos.barras_con_linea(barras, lineas, "Deuda neta", "Deuda neta / EBITDA", [str(a) for a in range(2022, 2027)], "x")
        alto = float(re.search(r'height="([\d.]+)pt"', svg).group(1))
        self.assertLess(alto, 400)
        self.assertIn("−60.000", svg)


if __name__ == "__main__":
    unittest.main()
