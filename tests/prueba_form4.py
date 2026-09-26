"""F9: las operaciones de directivos que publica la bolsa, cruzadas con su Form 4 de EDGAR. Sin red."""

import unittest
from datetime import date

from tesis.fuentes import form4
from tesis.fuentes.sec import Deposito

XML = """<?xml version="1.0"?>
<ownershipDocument>
  <issuer><issuerCik>0000804328</issuerCik><issuerTradingSymbol>QCOM</issuerTradingSymbol></issuer>
  <reportingOwner><reportingOwnerId><rptOwnerName>AMON CRISTIANO R</rptOwnerName></reportingOwnerId></reportingOwner>
  <nonDerivativeTable>
    <nonDerivativeTransaction>
      <transactionDate><value>2026-08-03</value></transactionDate>
      <transactionCoding><transactionCode>S</transactionCode></transactionCoding>
      <transactionAmounts><transactionShares><value>1200</value></transactionShares>
        <transactionPricePerShare><value>160.10</value></transactionPricePerShare></transactionAmounts>
    </nonDerivativeTransaction>
    <nonDerivativeTransaction>
      <transactionDate><value>2026-08-03</value></transactionDate>
      <transactionCoding><transactionCode>S</transactionCode></transactionCoding>
      <transactionAmounts><transactionShares><value>800</value></transactionShares>
        <transactionPricePerShare><value>160.55</value></transactionPricePerShare></transactionAmounts>
    </nonDerivativeTransaction>
  </nonDerivativeTable>
</ownershipDocument>"""

DEP = Deposito(cik="0000804328", formulario="4", presentado=date(2026, 8, 5), periodo=date(2026, 8, 3),
               accession="0000804328-26-000123", documento="xslF345X05/wk-form4_1.xml", epigrafes="")


def _descargar(url):
    assert url.endswith("/wk-form4_1.xml") and "xslF345X05" not in url, url      # el XML en crudo, no la vista con estilo
    return XML, date(2026, 9, 26)


class Cruce(unittest.TestCase):
    def test_casa_por_titular_fecha_y_acciones(self):
        """Falla si una operación de la bolsa que suma las líneas del mismo día de su Form 4 no se casa con él, o si
        se casa sin decir el número de acceso."""
        c = form4.cruzar([("Amon Cristiano R", "President", date(2026, 8, 3), "Sell", 2000.0, 160.3)], [DEP], _descargar, dias=10)[0]
        self.assertTrue(c.casado)
        self.assertEqual(c.accession, "0000804328-26-000123")
        self.assertEqual(c.presentado, date(2026, 8, 5))
        # también una línea suelta del mismo Form 4
        self.assertTrue(form4.cruzar([("Amon Cristiano R", "", date(2026, 8, 3), "Sell", 800.0, None)], [DEP], _descargar, dias=10)[0].casado)

    def test_la_suma_es_de_las_lineas_del_mismo_codigo(self):
        """Falla si la suma del día mezcla códigos: un ejercicio de opciones (M, 427 + 316 + 531 = 1.274) con la retención
        fiscal del mismo día (F, 441) no casaba con las 1.274 acciones que publica la bolsa (QCOM, Form 4 del 20/08/2026)."""
        lineas = "".join(f"""<nonDerivativeTransaction><transactionDate><value>2026-08-20</value></transactionDate>
            <transactionCoding><transactionCode>{c}</transactionCode></transactionCoding>
            <transactionAmounts><transactionShares><value>{a}</value></transactionShares></transactionAmounts></nonDerivativeTransaction>"""
                         for c, a in (("M", 427), ("M", 316), ("M", 531), ("F", 441)))
        xml = f"<ownershipDocument><reportingOwner><reportingOwnerId><rptOwnerName>GRECH PATRICIA Y</rptOwnerName></reportingOwnerId></reportingOwner><nonDerivativeTable>{lineas}</nonDerivativeTable></ownershipDocument>"
        dep = Deposito(cik="0000804328", formulario="4", presentado=date(2026, 8, 21), periodo=None, accession="0000804328-26-000092",
                       documento="form4.xml", epigrafes="")
        c = form4.cruzar([("Grech Patricia Y", "Officer", date(2026, 8, 20), "Option Execute", 1274.0, 0.0)], [dep],
                         lambda url: (xml, date(2026, 9, 26)), dias=10)[0]
        self.assertTrue(c.casado, c.motivo)

    def test_no_casa_lo_que_no_es_lo_mismo(self):
        """Falla si casa con otro titular, otras acciones o un Form 4 presentado fuera del plazo; cada caso dice por qué."""
        otro = form4.cruzar([("Palkhiwala Akash", "CFO", date(2026, 8, 3), "Sell", 2000.0, None)], [DEP], _descargar, dias=10)[0]
        self.assertFalse(otro.casado)
        self.assertIn("titular", otro.motivo)
        cifras = form4.cruzar([("Amon Cristiano R", "", date(2026, 8, 3), "Sell", 2500.0, None)], [DEP], _descargar, dias=10)[0]
        self.assertFalse(cifras.casado)
        self.assertIn("acciones", cifras.motivo)
        tarde = form4.cruzar([("Amon Cristiano R", "", date(2026, 7, 1), "Sell", 2000.0, None)], [DEP], _descargar, dias=10)[0]
        self.assertFalse(tarde.casado)
        self.assertIn("ningún Form 4", tarde.motivo)
        sin_fecha = form4.cruzar([("Amon Cristiano R", "", None, "Sell", 2000.0, None)], [DEP], _descargar, dias=10)[0]
        self.assertFalse(sin_fecha.casado)

    def test_un_form4_que_no_se_puede_leer_no_se_casa(self):
        """Falla si un fallo de EDGAR se toma por un cruce hecho."""
        def roto(url):
            raise RuntimeError("EDGAR no responde")
        c = form4.cruzar([("Amon Cristiano R", "", date(2026, 8, 3), "Sell", 2000.0, None)], [DEP], roto, dias=10)[0]
        self.assertFalse(c.casado)
        self.assertIn("EDGAR", c.motivo)


class Cuadro(unittest.TestCase):
    def test_el_cuadro_de_ultimas_operaciones_dice_su_form4(self):
        """Falla si el cuadro de últimas operaciones no enseña, fila a fila, el Form 4 casado o por qué no lo está."""
        from tesis.fuentes.posicionamiento import Insiders, Posicionamiento
        from tesis.plantillas import secciones
        from tesis.plantillas.informe import Cuadros
        ultimas = [("Amon Cristiano R", "President", date(2026, 8, 3), "Sell", 2000.0, 160.3),
                   ("Palkhiwala Akash", "CFO", date(2026, 8, 3), "Sell", 2000.0, None)]
        ins = Insiders(ultimas=ultimas)
        ins.cruce = form4.cruzar(ultimas, [DEP], _descargar, dias=10)
        cuadro = secciones.cuadros_f(Cuadros(), Posicionamiento(insiders=ins), None)["insiders_ultimas"]
        self.assertIn("Form 4 (EDGAR)", cuadro.columnas)
        casada, suelta = (f.celdas[-1] for f in cuadro.filas)
        self.assertIn("0000804328-26-000123", casada.nota)
        self.assertEqual(suelta.clase, "na")
        self.assertIn("1 de 2", cuadro.fuente)


if __name__ == "__main__":
    unittest.main()
