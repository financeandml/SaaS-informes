"""A4 · Deuda, acciones y dilución: una sola definición de cada cosa (fallos [7], [8], [45], [54], [58] y [69])."""

import unittest
from datetime import date
from types import SimpleNamespace

from tesis.datos import derivados
from tesis.datos.hechos import Capa, Origen, Periodo, de_valor
from tesis.motor import datos
from tesis.motor.puente import acciones_diluidas, puente

CIERRE = Periodo.instante(date(2026, 6, 27))


def _h(campo, valor, concepto="", p=CIERRE):
    return de_valor(campo, p, valor, Capa.SEC, Origen(documento="SEC EDGAR", concepto=f"us-gaap:{concepto}" if concepto else ""))


class PapelComercial(unittest.TestCase):
    def test_se_suma_si_la_deuda_a_corto_es_solo_el_vencimiento_del_largo(self):
        """Falla si la deuda bruta de Apple deja fuera los 1.997 M de papel comercial que presenta en línea propia."""
        hechos = {("deuda_cp", CIERRE): _h("deuda_cp", 11_007e6, "LongTermDebtCurrent"), ("deuda_lp", CIERRE): _h("deuda_lp", 71_340e6),
                  ("papel_comercial", CIERRE): _h("papel_comercial", 1_997e6, "CommercialPaper")}
        salida = derivados.calcular(hechos, [], [CIERRE])
        self.assertAlmostEqual(salida[("deuda_bruta", CIERRE)].valor, 84_344e6)
        self.assertIn("Papel comercial", salida[("deuda_bruta", CIERRE)].formula)

    def test_no_se_suma_si_la_deuda_a_corto_ya_es_el_total(self):
        """Falla si el papel comercial se cuenta dos veces (Qualcomm: «Short-term debt» ya lo incluye)."""
        hechos = {("deuda_cp", CIERRE): _h("deuda_cp", 2_489e6, "DebtCurrent"), ("deuda_lp", CIERRE): _h("deuda_lp", 14_000e6),
                  ("papel_comercial", CIERRE): _h("papel_comercial", 498e6, "CommercialPaper")}
        self.assertAlmostEqual(derivados.calcular(hechos, [], [CIERRE])[("deuda_bruta", CIERRE)].valor, 16_489e6)


class Acciones(unittest.TestCase):
    def test_sin_piezas_de_autocartera_portada_mas_efecto_dilutivo(self):
        """Falla si, sin las piezas del método de autocartera, se usan las diluidas medias del trimestre en vez de las
        básicas de la portada (posteriores) más el efecto dilutivo que publica la compañía."""
        n, nota = acciones_diluidas(4_163.9e6, None, None, None, 71.145, 4_261.3e6, "2T FY26", basicas_medias=4_189.3e6)
        self.assertAlmostEqual(n, 4_163.9e6 + 72.0e6, delta=1e3)
        self.assertIn("efecto dilutivo", nota)

    def test_dilucion_adicional_por_autocartera(self):
        """Falla si un warrant en dinero del analista no entra en las acciones (25 M a 161,26 con el precio a 201,97)."""
        base, _ = acciones_diluidas(1_050e6, None, None, None, 201.97, 1_069e6, "3T FY26", basicas_medias=1_060e6)
        con, nota = acciones_diluidas(1_050e6, None, None, None, 201.97, 1_069e6, "3T FY26", basicas_medias=1_060e6,
                                      adicional=[{"instrumento": "warrant", "acciones": 25, "precio_ejercicio": 161.26}])
        self.assertAlmostEqual(con - base, 25e6 * (1 - 161.26 / 201.97), delta=1)
        self.assertIn("warrant", nota)

    def test_valores_a_largo_en_linea_propia_fuera_de_la_deuda_neta(self):
        """Falla si los valores negociables a largo plazo cambian la deuda neta del puente (que es la del apartado 9)."""
        p = puente(100e6, None, 30e6, 20e6, None, [], False, 1e6, "", date(2026, 6, 27), "b", inversiones_lp=40e6)
        self.assertAlmostEqual(p.deuda_neta, 50e6)
        self.assertAlmostEqual(p.ajuste, -100e6 + 30e6 + 20e6 + 40e6)


class DeudaVigente(unittest.TestCase):
    def test_deuda_del_ultimo_balance_entre_ebitda_de_cuatro_trimestres(self):
        """Falla si la deuda neta del último balance se divide por el EBITDA de un ejercicio anterior."""
        trimestres = [Periodo(fin=date(2025, 11, 30), inicio=date(2025, 9, 1)), Periodo(fin=date(2026, 2, 28), inicio=date(2025, 12, 1)),
                      Periodo(fin=date(2026, 5, 31), inicio=date(2026, 3, 1)), Periodo(fin=date(2026, 8, 31), inicio=date(2026, 6, 1))]
        fin = Periodo.instante(date(2026, 8, 31))
        hechos = {("ebitda", q): _h("ebitda", 8_000e6, p=q) for q in trimestres}
        hechos[("deuda_neta", fin)] = _h("deuda_neta", 88_000e6, p=fin)
        hechos[("deuda_neta", Periodo.instante(date(2026, 5, 31)))] = _h("deuda_neta", 97_000e6, p=Periodo.instante(date(2026, 5, 31)))
        ratio, dn, ebitda, _ = derivados.deuda_neta_ebitda_vigente(hechos)
        self.assertAlmostEqual(ratio, 88_000 / 32_000)
        self.assertEqual(dn.valor, 88_000e6)


class HechosMateriales(unittest.TestCase):
    def _emisor(self, epigrafes):
        return SimpleNamespace(depositos=[SimpleNamespace(formulario="8-K", presentado=date(2026, 9, 8), epigrafes=epigrafes)])

    def test_un_8k_de_item_302_sin_citar_avisa_con_su_dilucion(self):
        """Falla si un 8-K con Item 3.02 (warrant) de los doce meses anteriores no se cita y no hay aviso."""
        a = datos.hechos_materiales_sin_citar(self._emisor("1.01,3.02,9.01"), {}, date(2026, 9, 25))
        self.assertEqual(len(a), 1)
        self.assertIn("3.02", a[0])
        self.assertIn("dilución", a[0])

    def test_citado_no_avisa_y_resultados_tampoco(self):
        self.assertEqual(datos.hechos_materiales_sin_citar(self._emisor("3.02"), {"x": [{"doc": "8-K 2026-09-08"}]}, date(2026, 9, 25)), [])
        self.assertEqual(datos.hechos_materiales_sin_citar(self._emisor("2.02,9.01"), {}, date(2026, 9, 25)), [])


if __name__ == "__main__":
    unittest.main()
