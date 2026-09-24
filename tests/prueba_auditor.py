"""El auditor de datos: que las cifras cuadren entre ellas. Sin red.

El caso que las trajo (23/09/2026): el contraste dice si cada cifra coincide con su fuente y la doble comprobación
relee lo impreso, pero ninguna de las dos mira si las cifras se contradicen entre sí. Un activo que no es pasivo más
patrimonio, un beneficio que no es el resultado antes de impuestos menos los impuestos o un BPA que no es el beneficio
entre las acciones pasaban las dos puertas: cada número venía de su fuente.
"""

import unittest
from datetime import date

from tesis import auditor, derivados
from tesis.hechos import Capa, Origen, Periodo, de_valor, na

FY = Periodo.anual(date(2026, 5, 31))
CIERRE = Periodo.instante(date(2026, 5, 31))
ORIGEN = Origen(documento="10k.pdf", formulario="10-K", presentado=date(2026, 6, 22), pagina=67)


def _h(campo, periodo, valor):
    return de_valor(campo, periodo, valor, Capa.SEC, ORIGEN)


def _hechos(**pares):
    salida = {}
    for campo, valor in pares.items():
        periodo = CIERRE if campo in ("total_activo", "pasivo_total", "patrimonio", "deuda_cp", "deuda_lp", "deuda_bruta") else FY
        salida[(campo, periodo)] = _h(campo, periodo, valor)
    return salida


def _de(a, clave):
    return next(c for c in a.comprobaciones if c.identidad == clave and c.estado != "sin datos")


class Comprobar(unittest.TestCase):
    def test_el_balance_que_cuadra_se_da_por_bueno(self):
        a = auditor.auditar(_hechos(total_activo=261_759e6, pasivo_total=218_703e6, patrimonio=43_056e6), [FY], [CIERRE])
        self.assertEqual(_de(a, "balance").estado, "cuadra")

    def test_un_balance_que_no_cuadra_se_dice_con_su_diferencia(self):
        """Falla si un activo que no es la suma del pasivo y el patrimonio pasa como bueno: cada cifra viene de su
        fuente y el conjunto es falso, que es justo lo que ni el contraste ni la doble comprobación miran."""
        a = auditor.auditar(_hechos(total_activo=261_759e6, pasivo_total=218_703e6, patrimonio=20_000e6), [FY], [CIERRE])
        c = _de(a, "balance")
        self.assertEqual(c.estado, "no cuadra")
        self.assertAlmostEqual(c.diferencia, 23_056e6, delta=1)
        self.assertIn("minoritario", c.motivo)          # el motivo dice por dónde suele venir la diferencia
        self.assertEqual(a.contradicciones, [c])

    def test_el_balance_nunca_se_despeja(self):
        """Falla si el activo o el patrimonio salen de la identidad del balance: la diferencia puede ser el interés
        minoritario, y despejarlo lo metería dentro de otra cifra sin que nadie lo viera."""
        a = auditor.auditar(_hechos(total_activo=261_759e6, pasivo_total=218_703e6), [FY], [CIERRE])
        c = next(c for c in a.comprobaciones if c.identidad == "balance")
        self.assertEqual(c.estado, "sin datos")
        self.assertEqual(a.derivadas, {})
        self.assertIn("patrimonio", c.motivo)

    def test_el_bpa_caza_un_error_de_escala(self):
        """Falla si un BPA que no es el beneficio entre las acciones pasa: con las acciones en miles en vez de en
        unidades, las tres cifras son verosímiles por separado."""
        bien = _hechos(beneficio_neto=17_087e6, bpa_diluido=5.83, acciones_diluidas=2_914e6)
        self.assertEqual(_de(auditor.auditar(bien, [FY], [CIERRE]), "bpa").estado, "cuadra")
        mal = _hechos(beneficio_neto=17_087e6, bpa_diluido=5.83, acciones_diluidas=2_914e3)
        self.assertEqual(_de(auditor.auditar(mal, [FY], [CIERRE]), "bpa").estado, "no cuadra")

    def test_sin_las_tres_cifras_el_bpa_no_se_comprueba_y_se_dice_cual_falta(self):
        a = auditor.auditar(_hechos(beneficio_neto=17_087e6, bpa_diluido=5.83), [FY], [CIERRE])
        c = next(c for c in a.comprobaciones if c.identidad == "bpa")
        self.assertEqual(c.estado, "sin datos")
        self.assertIn("acciones diluidas", c.motivo)


class Despejar(unittest.TestCase):
    def test_lo_que_falta_y_la_identidad_determina_se_despeja_marcado_como_derivado(self):
        """Falla si, teniendo el resultado antes de impuestos y el beneficio neto, el impuesto sigue saliendo N/A:
        la identidad lo determina, y despejarlo es un cálculo, no una invención —por eso sale como derivado."""
        hechos = _hechos(bai=19_554e6, beneficio_neto=17_087e6)
        a = auditor.auditar(hechos, [FY], [CIERRE])
        c = next(c for c in a.comprobaciones if c.identidad == "resultado")
        self.assertEqual(c.estado, "derivada")
        h = a.derivadas[("impuestos", FY)]
        self.assertAlmostEqual(h.valor, 2_467e6, delta=1)
        self.assertIs(h.capa, Capa.DERIVADO)
        self.assertIn("Beneficio neto", h.formula)
        self.assertEqual(len(h.entradas), 2)

    def test_despejar_no_pisa_nunca_un_dato_publicado(self):
        """Falla si lo despejado sustituye a una cifra que sí publica la fuente: el dato manda sobre el cálculo."""
        hechos = _hechos(bai=19_554e6, beneficio_neto=17_087e6, impuestos=2_000e6)
        a = auditor.auditar(hechos, [FY], [CIERRE])
        # el desajuste que deja ese impuesto publicado (467 M sobre 17.087 M) se dice en vez de taparlo despejando
        self.assertEqual(_de(a, "resultado").estado, "no cuadra")
        self.assertEqual(a.derivadas, {})
        # y si la auditoría trae un despejado para una cifra que sí se publica —porque se calculó antes de tenerla—,
        # manda el dato: el cálculo rellena huecos, nunca sustituye a la fuente
        a.derivadas.update(auditor.auditar(_hechos(bai=19_554e6, beneficio_neto=17_087e6), [FY], [CIERRE]).derivadas)
        salida = auditor.aplicar(hechos, a)
        self.assertEqual(salida[("impuestos", FY)].valor, 2_000e6)
        self.assertIs(salida[("impuestos", FY)].capa, Capa.SEC)

    def test_un_hueco_se_rellena_y_un_N_A_tambien(self):
        hechos = _hechos(deuda_cp=4_000e6, deuda_lp=100_000e6)
        hechos[("deuda_bruta", CIERRE)] = na("deuda_bruta", CIERRE, "no la publica nadie")
        a = auditor.auditar(hechos, [FY], [CIERRE])
        salida = auditor.aplicar(hechos, a)
        self.assertAlmostEqual(salida[("deuda_bruta", CIERRE)].valor, 104_000e6, delta=1)

    def test_con_dos_huecos_no_se_despeja_nada(self):
        a = auditor.auditar(_hechos(bai=19_554e6), [FY], [CIERRE])
        self.assertEqual(a.derivadas, {})


class Encadenar(unittest.TestCase):
    def test_el_pasivo_total_sale_de_sus_dos_mitades_y_con_el_se_comprueba_el_balance(self):
        """Falla si un balance que no imprime el total del pasivo —Oracle no lo imprime: pone «Total current
        liabilities» y «Total non-current liabilities»— deja el total en N/A, o si el balance se queda sin comprobar
        por no usar lo que la identidad anterior acaba de despejar."""
        hechos = {("pasivo_corriente", CIERRE): _h("pasivo_corriente", CIERRE, 41_764e6),
                  ("pasivo_no_corriente", CIERRE): _h("pasivo_no_corriente", CIERRE, 176_939e6),
                  ("total_activo", CIERRE): _h("total_activo", CIERRE, 261_759e6),
                  ("patrimonio", CIERRE): _h("patrimonio", CIERRE, 42_508e6)}
        a = auditor.auditar(hechos, [FY], [CIERRE])
        self.assertAlmostEqual(a.derivadas[("pasivo_total", CIERRE)].valor, 218_703e6, delta=1)
        # y con él el balance ya se puede comprobar: 261.759 frente a 218.703 + 42.508 = 261.211, dentro de tolerancia
        # (la diferencia, 548, es el interés minoritario que el patrimonio del grupo no lleva)
        self.assertEqual(_de(a, "balance").estado, "cuadra")


class UnaSolaAritmetica(unittest.TestCase):
    """Regla 9: la identidad del auditor y la fórmula del derivado son el mismo hecho dicho dos veces."""

    def test_las_identidades_y_los_derivados_calculan_lo_mismo(self):
        """Falla si el auditor y `derivados` no usan los mismos signos: uno de los dos estaría mintiendo sobre la
        misma cifra, y el desacuerdo solo se ve afirmándolo."""
        entradas = {"ebit": 20_606e6, "amortizacion": 1_671e6, "cfo": 25_000e6, "capex": -9_000e6,
                    "deuda_cp": 4_000e6, "deuda_lp": 100_000e6}
        for ident in auditor.IDENTIDADES:
            formula = derivados.FORMULAS.get(ident.total)
            if formula is None or any(k not in entradas for k, _ in ident.partes):
                continue
            por_identidad = sum(signo * entradas[k] for k, signo in ident.partes)
            por_derivado = formula(**{k: entradas[k] for k, _ in ident.partes})
            self.assertAlmostEqual(por_identidad, por_derivado, delta=1, msg=ident.clave)


if __name__ == "__main__":
    unittest.main()
