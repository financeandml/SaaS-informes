"""Cuando la compañía cambia de etiqueta XBRL, la partida entera se vacía sin avisar. Sin red: fixtures de QCOM.

El caso que las trajo (24/09/2026): Qualcomm dejó de etiquetar `StockholdersEquity` en 2019 y pasó a
`StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest`; el capex lo declara como
`PaymentsToAcquireProductiveAssets` y los dividendos como `PaymentsOfOrdinaryDividends`. El catálogo se había
quedado con los nombres viejos, así que **patrimonio, capex y dividendos salían N/A en los cinco ejercicios** —y con
ellos el ROE, el ROA, el ROIC, el FCF y el payout—. Ninguna prueba lo notaba: un N/A es un resultado válido, y el
informe se emitía entero con los huecos puestos. Es la causa 3 de `docs/spec/07_regresiones.md`.
"""

import os
import unittest
from datetime import date
from pathlib import Path

import pytest

from tesis import campos, entorno, sec
from tesis.hechos import Periodo

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "cache_sec"
HOY = date(2026, 9, 23)


class EtiquetasDeQualcomm(unittest.TestCase):
    """QCOM con sus respuestas congeladas: sin `WC_SEC_CONTACTO` ninguna descarga es posible, así que todo sale del disco."""

    @classmethod
    def setUpClass(cls):
        cls._env, cls._raiz, cls._cache = dict(os.environ), entorno.RAIZ, sec.CACHE
        os.environ["WC_SEC_CONTACTO"] = ""
        entorno.RAIZ = FIXTURES.parent                  # una raíz sin `.env` del que sacar el contacto
        sec.CACHE = FIXTURES
        cls.facts, _ = sec.companyfacts(sec.emisor("QCOM").cik)
        cls.anuales = sec.calendario(cls.facts, 12)[-5:]

    @classmethod
    def tearDownClass(cls):
        entorno.RAIZ, sec.CACHE = cls._raiz, cls._cache
        os.environ.clear()
        os.environ.update(cls._env)

    def _anuales(self, clave):
        """Los cinco ejercicios del campo, con el periodo que le toca: saldo a una fecha o flujo de un año."""
        c = campos.campo(clave)
        periodos = [Periodo.instante(p.fin) for p in self.anuales] if c.tipo == campos.INSTANTE else list(self.anuales)
        hechos = sec.hechos_xbrl(self.facts, c, HOY, periodos)
        return [h.valor if (h := hechos.get(p)) is not None and h.hay_dato else None for p in periodos]

    @pytest.mark.regresion("R3")
    def test_el_patrimonio_esta_en_los_cinco_ejercicios(self):
        """R3. Falla si el patrimonio vuelve a salir N/A: sin él no hay ROE, ni ROA, ni ROIC, ni comprobación de balance."""
        valores = self._anuales("patrimonio")
        self.assertNotIn(None, valores, "patrimonio con huecos en la ventana del informe")
        self.assertAlmostEqual(valores[-1] / 1e6, 21_206, delta=1)      # FY2025

    @pytest.mark.regresion("R4")
    def test_el_capex_esta_en_fy2021_y_fy2022(self):
        """R4. Falla si el capex vuelve a salir N/A: sin él no hay flujo de caja libre ni capex sobre ventas."""
        valores = self._anuales("capex")
        self.assertNotIn(None, valores[:2], "capex sin FY2021 o FY2022")
        self.assertAlmostEqual(valores[0] / 1e6, 1_888, delta=1)

    @pytest.mark.regresion("R6")
    def test_los_dividendos_pagados_del_ultimo_ejercicio(self):
        """R6. Falla si los dividendos salen N/A: con 3.805 M pagados, ninguna frase puede decir que nunca se pagaron."""
        self.assertAlmostEqual(self._anuales("dividendos")[-1] / 1e6, 3_805, delta=1)

    def test_un_concepto_vivo_no_puede_dejar_el_campo_vacio(self):
        """Falla si un campo sale N/A en todo el informe mientras la compañía publica uno de sus conceptos dentro de
        la ventana: eso ya no es «no lo declara», es que no lo estamos leyendo."""
        gaap = self.facts["facts"]["us-gaap"]
        desde = self.anuales[0].inicio.isoformat()
        vacios = []
        for c in campos.CAMPOS:
            if c.solo_documento or any(v is not None for v in self._anuales(c.clave)):
                continue
            vivos = [k for k in c.conceptos if k in gaap
                     and max((f["end"] for u in gaap[k]["units"].values() for f in u), default="") >= desde]
            if vivos:
                vacios.append(f"{c.clave} vacío aunque QCOM publica {vivos}")
        self.assertEqual(vacios, [])


if __name__ == "__main__":
    unittest.main()
