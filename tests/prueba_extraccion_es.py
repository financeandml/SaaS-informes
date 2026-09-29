"""Cuentas españolas (fase B, 29/09/2026): del PDF oficial de BME a hechos, sin SEC.

Las tres empresas de los informes de ejemplo del analista (Bytetravel, Treelogic y Redegal, BME Growth), con sus cuentas
anuales de 2025 y su último semestral recortados a las páginas de los estados (`tests/fixtures/bme/`). Lo que se afirma:
que el SaaS lee las cifras que publica cada emisor —contrastadas con las del informe de IEAF, que es solo un oráculo de
prueba (`tests/fixtures/lighthouse/`)— y que lo que lee lo lee bien: consolidadas antes que individuales, ninguna tabla
de la memoria tomada por un estado, el 2024 reexpresado de las cuentas de 2025 antes que el del semestral, el segundo
semestre derivado y las partidas del modelo de EE. UU. declaradas ajenas, no huecos.
"""

import unittest
from pathlib import Path

import yaml

from tesis.datos import expediente
from tesis.datos.hechos import Contraste
from tesis.verificacion import contraste

RAIZ = Path(__file__).resolve().parents[1]
BME = RAIZ / "tests" / "fixtures" / "bme"
ORACULO = RAIZ / "tests" / "fixtures" / "lighthouse"
_TAB: dict = {}


def tablero(ticker: str):
    if ticker not in _TAB:
        exp = expediente.cargar(ticker, sorted((BME / ticker).glob("*.pdf")), None)
        periodos = contraste.periodos_del_informe(exp, facts=None)
        _TAB[ticker] = (exp, periodos, contraste.contrastar(exp, None, None, periodos, None))
    return _TAB[ticker]


def hecho(ticker: str, campo: str, clave: str):
    _, periodos, tab = tablero(ticker)
    return next((h for (c, p), h in tab.hechos().items() if c == campo and p.clave == clave), None)


class Oraculo(unittest.TestCase):
    """Falla si una cifra publicada que el SaaS lee de las cuentas oficiales no es la que imprime IEAF (al 0,1)."""

    def _contrastar(self, ticker: str):
        cifras = yaml.safe_load((ORACULO / f"{ticker}.yaml").read_text(encoding="utf-8"))["cifras"]
        for x in cifras:
            h = hecho(ticker, x["campo"], x["periodo"])
            self.assertIsNotNone(h, f"{ticker} {x['campo']} {x['periodo']}: no se lee")
            self.assertTrue(h.hay_dato, f"{ticker} {x['campo']} {x['periodo']}: {h.motivo}")
            self.assertEqual(round(h.valor / 1e6, 1) + 0.0, x["valor"] + 0.0,
                             f"{ticker} {x['campo']} {x['periodo']}: {h.valor} frente a {x['valor']} de IEAF (pág. {x['pagina']})")
            self.assertEqual(h.unidad, "EUR")

    def test_bytetravel(self):
        self._contrastar("BYTE")

    def test_treelogic(self):
        self._contrastar("TRTK")

    def test_redegal(self):
        self._contrastar("RDG")


class Lectura(unittest.TestCase):
    def test_sin_discrepancias_falsas(self):
        """Falla si el comparativo reexpresado (cuentas de 2025, «31/12/2024*») discrepa del semestral anterior en vez de
        mandar el más reciente (03 §3), o si una tabla de la memoria se lee como la partida del estado."""
        for t in ("BYTE", "TRTK", "RDG"):
            _, _, tab = tablero(t)
            self.assertEqual([f"{r.campo.clave} {r.periodo.clave}: {r.nota}" for r in tab.bloquea], [], t)

    def test_reexpresion_manda_el_documento_mas_reciente(self):
        """Falla si el patrimonio de Redegal a 31/12/2024 no sale del comparativo de las cuentas de 2025 con su nota."""
        h = hecho("RDG", "patrimonio", "@2024-12-31")
        self.assertIn("CCAA", h.origen.documento.upper())
        self.assertIn("reexpresado", h.nota)

    def test_explotacion_con_rotulo_cortado(self):
        """Falla si el flujo de explotación de Redegal —rótulo cortado en el propio PDF— no se lee."""
        h = hecho("RDG", "cfo", "FY2025")
        self.assertTrue(h is not None and h.hay_dato)
        self.assertAlmostEqual(h.valor, -662595.23, places=1)

    def test_segundo_semestre_derivado(self):
        """Falla si el 2S no es ejercicio − 1S, marcado como derivado."""
        fy, s1, s2 = (hecho("RDG", "ingresos", k) for k in ("FY2025", "1S25", "2S25"))
        self.assertIs(s2.contraste, Contraste.DERIVADO)
        self.assertAlmostEqual(s2.valor, fy.valor - s1.valor, places=2)

    def test_capex_suma_de_pagos_por_inversiones(self):
        """Falla si el capex no es la suma de las inversiones en inmovilizado intangible y material del estado de flujos,
        o si toma las filas homónimas de «Cobros por desinversiones»."""
        h = hecho("TRTK", "capex", "FY2025")
        self.assertIs(h.contraste, Contraste.DERIVADO)
        self.assertAlmostEqual(h.valor, 486861, places=0)

    def test_partidas_del_modelo_de_eeuu_no_son_huecos(self):
        """Falla si el SG&A o la retribución en acciones salen como dato que falta en unas cuentas españolas (regla 10)."""
        _, _, tab = tablero("TRTK")
        self.assertIn("sga", tab.no_aplican)
        self.assertIn("sbc", tab.no_aplican)
        self.assertNotIn("ingresos", tab.no_aplican)

    def test_consolidadas_antes_que_individuales(self):
        """Falla si en Redegal (trae las dos) los ingresos salen de las individuales (16,62 M) y no del grupo (16,83 M)."""
        self.assertAlmostEqual(hecho("RDG", "ingresos", "FY2025").valor / 1e6, 16.83, places=2)

    def test_individuales_se_dicen(self):
        """Falla si, sin cuentas consolidadas (Treelogic), no se avisa de que las cifras son de la sociedad."""
        _, _, tab = tablero("TRTK")
        self.assertTrue([a for a in tab.avisos if "individuales" in a])

    def test_sin_ceros_con_signo(self):
        """Falla si un cero del modelo en Debe/Haber sale como «−0»."""
        for t in ("BYTE", "TRTK", "RDG"):
            _, _, tab = tablero(t)
            for (c, p), h in tab.hechos().items():
                if h.hay_dato and h.valor == 0:
                    self.assertEqual(str(h.valor), "0.0", f"{t} {c} {p.clave}")


if __name__ == "__main__":
    unittest.main()
