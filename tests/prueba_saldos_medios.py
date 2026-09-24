"""El saldo medio con un ejercicio de 52/53 semanas. Sin red.

El caso que las trajo (24/09/2026): el ROE, el ROA y el ROIC de Qualcomm salían N/A **en los cinco ejercicios** del
informe. No faltaba el patrimonio —estaba, y bien—: el cierre anterior se calculaba restándole un año a la fecha de
cierre, y quien cierra el domingo más cercano a fin de septiembre no cierra el mismo día del mes dos años seguidos.
Qualcomm cerró el 26/09/2021 y el 25/09/2022, así que se pedía un saldo del día 25 de 2021, que no existe. El
informe se emitía entero con las tres rentabilidades en blanco y sin decir por qué: el motivo hablaba de un saldo
que faltaba, cuando el saldo estaba y la fecha era la inventada.
"""

import unittest
from datetime import date

from tesis import derivados
from tesis.hechos import Capa, Origen, Periodo, de_valor

FUENTE = Origen(documento="companyfacts", formulario="10-K", presentado=date(2022, 11, 2))

# Dos ejercicios contiguos de 52/53 semanas: ni el cierre cae el mismo día del mes, ni el año empieza el día
# siguiente al cierre anterior. Las dos cosas rompían el cálculo del saldo medio.
FY2021 = Periodo(inicio=date(2020, 9, 28), fin=date(2021, 9, 26))
FY2022 = Periodo(inicio=date(2021, 9, 27), fin=date(2022, 9, 25))


def _hechos():
    def h(clave, p, valor):
        return ((clave, p), de_valor(clave, p, valor, Capa.SEC, FUENTE))
    return dict([
        h("patrimonio", Periodo.instante(FY2021.fin), 9_950_000_000),
        h("patrimonio", Periodo.instante(FY2022.fin), 18_013_000_000),
        h("total_activo", Periodo.instante(FY2021.fin), 41_240_000_000),
        h("total_activo", Periodo.instante(FY2022.fin), 49_014_000_000),
        h("beneficio_neto", FY2022, 12_936_000_000),
    ])


class SaldoMedioDe53Semanas(unittest.TestCase):
    def test_el_cierre_anterior_es_el_publicado_y_no_el_de_hace_un_ano(self):
        """Falla si se vuelve a restar un año a la fecha de cierre: el 25/09/2021 no es un cierre de Qualcomm."""
        anterior = derivados._cierre_anterior("patrimonio", FY2022, _hechos())
        self.assertEqual(anterior.fin, date(2021, 9, 26))

    def test_el_roe_sale_en_un_ejercicio_de_52_53_semanas(self):
        """Falla si el ROE vuelve a ser N/A teniendo los dos saldos publicados: es el fallo tal como se veía."""
        salida = derivados.calcular(_hechos(), [FY2022], [Periodo.instante(FY2022.fin)])
        roe = salida[("roe", FY2022)]
        self.assertTrue(roe.hay_dato, roe.motivo)
        medio = (9_950 + 18_013) / 2
        self.assertAlmostEqual(roe.valor, 12_936 / medio, places=4)

    def test_sin_cierre_anterior_publicado_sigue_siendo_N_A_con_su_motivo(self):
        """Falla si se inventa un saldo anterior cuando no hay ninguno: el primer ejercicio del informe no tiene media."""
        hechos = {k: v for k, v in _hechos().items() if k[1] != Periodo.instante(FY2021.fin)}
        salida = derivados.calcular(hechos, [FY2022], [Periodo.instante(FY2022.fin)])
        roe = salida[("roe", FY2022)]
        self.assertFalse(roe.hay_dato)
        self.assertIn("cierre anterior", roe.motivo)


if __name__ == "__main__":
    unittest.main()
