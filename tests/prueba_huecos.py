"""Por qué una cifra no está, y cuáles no son huecos. Sin red.

El caso que las trajo (23/09/2026): el expediente de Oracle daba **131 celdas sin dato** y no había manera de saber
por qué. Al mirarlas una a una no eran una sola cosa, sino cuatro, y solo una era un fallo del expediente:

1. Oracle etiqueta con otro nombre lo mismo («AvailableForSaleSecuritiesDebtSecuritiesCurrent» por inversiones a
   corto plazo, «NotesPayableCurrent» por deuda a corto, «LongTermNotesAndLoans» en los trimestres).
2. No declara el agregado y sí sus dos mitades: el total del pasivo, la amortización, el resultado antes de impuestos.
3. Publica el flujo de caja **acumulado del ejercicio**, no el del trimestre: la resta entre acumulados es el
   trimestre, y las dos cifras están publicadas.
4. Hay partidas que sencillamente no son suyas —activos de contenido, autocartera, un subtotal de coste de los
   ingresos que dejó de publicar en 2011—: eso no es un dato que falte, y contarlo como tal es contar fallos donde
   no los hay.
"""

import unittest
from datetime import date

from tesis import contraste, sec
from tesis.campos import Campo, campo
from tesis.contraste import Resultado, _no_los_tiene_la_compania
from tesis.hechos import Capa, Contraste, Periodo, na

ANUAL = ("2025-06-01", "2026-05-31")


def _fila(inicio, fin, val, form="10-K", filed="2026-06-22"):
    f = {"end": fin, "val": val, "form": form, "filed": filed, "accn": "0001-26-1"}
    if inicio:
        f["start"] = inicio
    return f


def _facts(**conceptos):
    """companyfacts de juguete: {concepto: [filas]}, más un ejercicio con el que se lee el calendario."""
    datos = {"Revenues": {"units": {"USD": [_fila(*ANUAL, 57_399_000_000)] * 6}}}
    for nombre, filas in conceptos.items():
        datos[nombre] = {"units": {"USD": filas}}
    return {"facts": {"us-gaap": datos}}


class SumaDeConceptos(unittest.TestCase):
    def test_el_total_sale_de_sus_dos_mitades_marcado_como_derivado(self):
        """Falla si un balance que no etiqueta «Liabilities» y sí sus dos mitades deja el total del pasivo en N/A:
        son diez celdas de Oracle, y con ellas se cae la comprobación de que el activo es pasivo más patrimonio."""
        facts = _facts(LiabilitiesCurrent=[_fila(None, "2026-05-31", 41_764_000_000)],
                       LiabilitiesNoncurrent=[_fila(None, "2026-05-31", 176_939_000_000)])
        p = Periodo.instante(date(2026, 5, 31))
        h = sec.hechos_xbrl(facts, campo("pasivo_total"), date(2026, 9, 23), [p])[p]
        self.assertAlmostEqual(h.valor, 218_703_000_000, delta=1)
        self.assertIs(h.capa, Capa.DERIVADO)          # nunca como hecho publicado por la SEC
        self.assertIn("LiabilitiesCurrent", h.formula)
        self.assertEqual(len(h.entradas), 2)

    def test_con_una_mitad_sola_no_se_suma_nada(self):
        """Falla si el grupo entra a medias: un «total» que solo es una de sus partes es una cifra falsa."""
        facts = _facts(LiabilitiesCurrent=[_fila(None, "2026-05-31", 41_764_000_000)])
        p = Periodo.instante(date(2026, 5, 31))
        self.assertFalse(sec.hechos_xbrl(facts, campo("pasivo_total"), date(2026, 9, 23), [p])[p].hay_dato)

    def test_el_concepto_publicado_manda_sobre_la_suma(self):
        """Falla si la suma pisa al agregado que la compañía sí publica: el dato manda sobre el cálculo."""
        facts = _facts(Liabilities=[_fila(None, "2026-05-31", 218_000_000_000)],
                       LiabilitiesCurrent=[_fila(None, "2026-05-31", 41_764_000_000)],
                       LiabilitiesNoncurrent=[_fila(None, "2026-05-31", 176_939_000_000)])
        p = Periodo.instante(date(2026, 5, 31))
        h = sec.hechos_xbrl(facts, campo("pasivo_total"), date(2026, 9, 23), [p])[p]
        self.assertEqual(h.valor, 218_000_000_000)
        self.assertIs(h.capa, Capa.SEC)


class TrimestreEntreAcumulados(unittest.TestCase):
    def test_el_trimestre_sale_de_los_acumulados_que_si_se_publican(self):
        """Falla si el flujo de caja del segundo trimestre queda N/A porque el 10-Q lo presenta acumulado: los dos
        acumulados están publicados y su resta es el trimestre. Eran catorce celdas del expediente de Oracle."""
        facts = _facts(NetCashProvidedByUsedInOperatingActivities=[
            _fila("2025-06-01", "2025-08-31", 8_140_000_000, "10-Q", "2025-09-11"),
            _fila("2025-06-01", "2025-11-30", 15_000_000_000, "10-Q", "2025-12-11")])
        obt = date(2026, 9, 23)
        hechos = sec.hechos_xbrl(facts, campo("cfo"), obt)
        segundo = Periodo(fin=date(2025, 11, 30), inicio=date(2025, 9, 1))
        h = sec.trimestre_por_acumulados(facts, campo("cfo"), hechos, segundo)
        self.assertAlmostEqual(h.valor, 6_860_000_000, delta=1)
        self.assertIs(h.capa, Capa.DERIVADO)
        self.assertIn("acumulado", h.formula)

    def test_sin_el_acumulado_anterior_no_se_deriva_nada(self):
        """Falla si se resta lo que no hay: sin el acumulado del trimestre anterior no se puede saber el trimestre,
        y una resta contra cero daría el acumulado entero como si fuera de tres meses."""
        facts = _facts(NetCashProvidedByUsedInOperatingActivities=[
            _fila("2025-06-01", "2025-11-30", 15_000_000_000, "10-Q", "2025-12-11")])
        hechos = sec.hechos_xbrl(facts, campo("cfo"), date(2026, 9, 23))
        segundo = Periodo(fin=date(2025, 11, 30), inicio=date(2025, 9, 1))
        self.assertIsNone(sec.trimestre_por_acumulados(facts, campo("cfo"), hechos, segundo))


class LoQueNoEsUnHueco(unittest.TestCase):
    """Regla 1 llevada al recuento: decir «131 sin dato» cuando 47 son partidas que la empresa no tiene es contar mal."""

    def _resultados(self, c: Campo, periodos):
        return [Resultado(c, p, na(c.clave, p, "no está").con(contraste=Contraste.HUECO), None, [], [], None)
                for p in periodos]

    def test_una_partida_que_la_compania_no_tiene_no_cuenta_como_dato_que_falta(self):
        """Falla si un campo que la compañía no declara en ningún depósito ni imprime en sus documentos se cuenta
        como hueco: los activos de contenido son de Netflix, no de Oracle."""
        c = campo("contenido")
        periodos = [Periodo.instante(date(2026, 5, 31)), Periodo.instante(date(2025, 5, 31))]
        ajenos = _no_los_tiene_la_compania(self._resultados(c, periodos), _facts())
        self.assertIn("contenido", ajenos)
        self.assertIn("no es una línea de sus cuentas", ajenos["contenido"])

    def test_lo_que_dejo_de_publicar_hace_diez_anios_se_dice_con_su_fecha(self):
        """Falla si no se distingue «nunca lo declaró» de «dejó de declararlo»: Oracle etiquetó el coste de los
        ingresos hasta 2011 y desde entonces presenta sus gastos por naturaleza."""
        c = campo("coste_ingresos")
        facts = _facts(CostOfRevenue=[_fila("2010-06-01", "2011-05-31", 10_000_000_000)])
        periodos = [Periodo(fin=date(2026, 5, 31), inicio=date(2025, 6, 1))]
        ajenos = _no_los_tiene_la_compania(self._resultados(c, periodos), facts)
        self.assertIn("dejó de declarar", ajenos["coste_ingresos"])
        self.assertIn("2011", ajenos["coste_ingresos"])

    def test_si_lo_publica_dentro_de_la_ventana_del_informe_el_hueco_es_un_hueco(self):
        """Falla si un campo que la compañía sí declara —y que falta en el periodo pedido— se declara ajeno: eso
        taparía un dato que de verdad falta."""
        c = campo("coste_ingresos")
        facts = _facts(CostOfRevenue=[_fila("2024-06-01", "2025-05-31", 10_000_000_000)])
        periodos = [Periodo(fin=date(2026, 5, 31), inicio=date(2025, 6, 1))]
        self.assertEqual(_no_los_tiene_la_compania(self._resultados(c, periodos), facts), {})


if __name__ == "__main__":
    unittest.main()
