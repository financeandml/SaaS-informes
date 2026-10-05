"""El punto de entrada y dónde viven los datos pesados. Sin red.

Los adjuntos del analista y las emisiones (279 MB) salieron de la copia de trabajo el 24/09/2026 y ahora los sitúa
`WC_DATOS`. Si esa resolución se rompe, el SaaS no encuentra nada y lo enseña como una carpeta vacía —no como un
error—, que es la peor forma de fallar: parece que el analista no ha adjuntado nada.
"""

import os
import unittest
from pathlib import Path

from tesis import __main__ as entrada, entorno

DATOS = Path(__file__).resolve().parents[2] / "datos-tesis"


class DondeVivenLosDatos(unittest.TestCase):
    def setUp(self):
        self.raiz, self.env = entorno.RAIZ, dict(os.environ)
        os.environ.pop("WC_DATOS", None)
        entorno.RAIZ = Path(__file__).resolve().parent / "fixtures"   # una raíz sin `.env` que leer

    def tearDown(self):
        entorno.RAIZ = self.raiz
        os.environ.clear()
        os.environ.update(self.env)

    def test_sin_la_variable_los_datos_siguen_en_la_raiz_del_repositorio(self):
        """Falla si quitar `WC_DATOS` cambia de sitio los datos: quien no la configure tiene que seguir como estaba."""
        self.assertEqual(entorno.carpeta("adjuntos"), entorno.RAIZ / "adjuntos")

    def test_la_variable_lleva_los_datos_fuera_de_la_copia_de_trabajo(self):
        """Falla si se ignora `WC_DATOS` y los 279 MB vuelven al repositorio sin que nadie lo pida."""
        os.environ["WC_DATOS"] = str(DATOS)
        destino = entorno.carpeta("salida")
        self.assertEqual((destino.parent.name, destino.name), ("datos-tesis", "salida"))
        self.assertNotIn(entorno.RAIZ, destino.parents)


class LasTresOrdenes(unittest.TestCase):
    def test_sin_orden_no_hace_nada_y_lo_dice(self):
        """Falla si `python -m tesis` a secas arranca algo: sin orden no se sirve ni se emite, se explica y se sale con 2."""
        self.assertEqual(entrada.main([]), 2)
        self.assertEqual(entrada.main(["inventada"]), 2)

    def test_generar_le_pasa_a_emitir_sus_opciones_tal_cual(self):
        """Falla si `generar` reinterpreta la línea de órdenes: lo antiguo manda, y `emitir.py` la recibe entera."""
        emitir = entrada._emitir()
        original, recibido = emitir.main, []
        emitir.main = lambda argv: (recibido.append(list(argv)), 0)[1]
        try:
            self.assertEqual(entrada.main(["generar", "QCOM", "--fecha", "2026-09-24", "--casa"]), 0)
        finally:
            emitir.main = original
        self.assertEqual(recibido, [["QCOM", "--fecha", "2026-09-24", "--casa"]])

    def test_generar_sin_carpeta_usa_el_expediente_de_la_web(self):
        """Falla si `generar RDG.MC` sin `--carpeta` se niega a emitir cuando la web ya dejó el expediente en
        <datos>/adjuntos/RDG.MC: es la misma carpeta que usa «Generar» y el analista no tiene por qué repetirla."""
        import tempfile
        from unittest import mock
        from tesis.fuentes import emisores
        emitir = entrada._emitir()
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "RDG.MC").mkdir()
            (Path(tmp) / "RDG.MC" / "bme_2025_AN_1.pdf").write_bytes(b"%PDF-1.4")
            with mock.patch.object(entorno, "carpeta", lambda nombre: Path(tmp)), \
                    mock.patch.object(emisores, "emisor", lambda ticker: None):
                self.assertEqual(emitir.main(["RDG.MC", "--fecha", "2026-09-29"]), 1)   # llega al emisor (sin emisor: error)
                with self.assertRaises(SystemExit):                                     # sin expediente, sí se niega
                    emitir.main(["BYTE.MC", "--fecha", "2026-09-29"])

    def test_servir_le_pasa_a_saas_sus_opciones_tal_cual(self):
        """Falla si `servir` deja de ser `tesis.saas`: el puerto y `--sin-navegador` son los de siempre."""
        from tesis.web import saas
        original, recibido = saas.main, []
        saas.main = lambda argv: (recibido.append(list(argv)), 0)[1]
        try:
            self.assertEqual(entrada.main(["servir", "--puerto", "8771", "--sin-navegador"]), 0)
        finally:
            saas.main = original
        self.assertEqual(recibido, [["--puerto", "8771", "--sin-navegador"]])


if __name__ == "__main__":
    unittest.main()
