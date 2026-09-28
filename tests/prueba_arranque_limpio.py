"""El repositorio descargado de GitHub funciona tal cual (28/09/2026).

Descargado el ZIP y arrancado, no se podía hacer nada: sin `.env`, la SEC rechazaba la lista de empresas (exige un
contacto) y el desplegable no respondía; el aviso salía en una línea al pie. Además, sin `WC_DATOS` no se veían los datos
de ejemplo de `datos-tesis/` y, sin `WC_PRECIO_FUENTE`, el precio era N/A. Y desde la web no había forma de decidir una
discrepancia SEC ↔ documento: ningún informe con una podía salir EMITIDO.
"""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tesis import entorno
from tesis.web import saas


class _RaizLimpia(unittest.TestCase):
    """Una raíz como la del ZIP: sin `.env`, con `datos-tesis/`."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / "datos-tesis" / "entradas").mkdir(parents=True)
        self.raiz, self.env = entorno.RAIZ, dict(os.environ)
        for k in ("WC_DATOS", "WC_PRECIO_FUENTE", "WC_SEC_CONTACTO"):
            os.environ.pop(k, None)
        entorno.RAIZ = self.tmp

    def tearDown(self):
        entorno.RAIZ = self.raiz
        os.environ.clear()
        os.environ.update(self.env)


class SinConfigurar(_RaizLimpia):
    def test_los_datos_de_ejemplo_se_ven_sin_wc_datos(self):
        """Falla si, sin `WC_DATOS`, el SaaS no usa los `datos-tesis/` que trae el repositorio."""
        self.assertEqual(entorno.carpeta("adjuntos"), self.tmp / "datos-tesis" / "adjuntos")

    def test_el_precio_es_de_nasdaq_sin_configurar(self):
        """Falla si, sin `WC_PRECIO_FUENTE`, el precio queda N/A: Nasdaq es la única fuente admitida (regla 6)."""
        self.assertEqual(entorno.variable("WC_PRECIO_FUENTE"), "nasdaq")

    def test_el_contacto_de_la_sec_no_tiene_valor_por_defecto(self):
        """Falla si el programa se inventa un contacto para la SEC: cada usuario se identifica a sí mismo."""
        self.assertEqual(entorno.variable("WC_SEC_CONTACTO"), "")
        self.assertFalse(saas.configuracion()["sec_contacto"])

    def test_el_contacto_se_pide_y_se_guarda_en_env(self):
        """Falla si el contacto tecleado en la página no queda en `.env` o si se acepta sin correo."""
        self.assertIsNotNone(saas.guardar_contacto("solo nombre"))
        self.assertFalse((self.tmp / ".env").exists())
        self.assertIsNone(saas.guardar_contacto("Ana Pérez ana@ejemplo.com"))
        self.assertEqual(entorno.variable("WC_SEC_CONTACTO"), "Ana Pérez ana@ejemplo.com")
        self.assertTrue(saas.configuracion()["sec_contacto"])
        self.assertIsNone(saas.guardar_contacto("Ana Pérez ana@otro.com"))          # sustituye, no duplica
        self.assertEqual((self.tmp / ".env").read_text(encoding="utf-8").count("WC_SEC_CONTACTO="), 1)


class Decisiones(_RaizLimpia):
    def test_la_decision_exige_motivo_y_se_puede_deshacer(self):
        """Falla si una discrepancia se decide sin motivo (va al pie del informe), si no se guarda donde la lee la
        emisión o si no se puede deshacer."""
        with mock.patch.object(saas, "_entradas_analista", lambda t: None):
            self.assertIsNotNone(saas.decidir("MSFT", "bpa_basico", "2T25", 3.66, ""))
            self.assertIsNone(saas.decidir("MSFT", "bpa_basico", "2T25", 3.66, "Redondeo del BPA a céntimos"))
            d = json.loads(saas.ruta_decisiones("MSFT").read_text(encoding="utf-8"))
            self.assertEqual([(x["campo"], x["periodo"], x["valor"]) for x in d], [("bpa_basico", "2T25", 3.66)])
            self.assertIsNone(saas.decidir("MSFT", "bpa_basico", "2T25", None, ""))
            self.assertEqual(saas.leer_decisiones("MSFT"), [])


if __name__ == "__main__":
    unittest.main()
