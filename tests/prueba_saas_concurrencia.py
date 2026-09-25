"""Dos empresas preparándose a la vez en el mismo servidor. Sin red.

El caso que la trajo (22/09/2026): al abrir Oracle y Netflix seguidos, las dos cargas corrían en hilos distintos y
pypdfium2 —que no es seguro entre hilos— devolvía «PdfiumError: Failed to load document (Data format error)»: el
expediente entero se perdía y la página decía «Error» sin que los ficheros tuvieran nada malo.
"""

import threading
import unittest
from unittest import mock

from tesis.web import saas


class Concurrencia(unittest.TestCase):
    def test_la_lectura_de_documentos_va_de_una_en_una(self):
        """Falla si dos clasificaciones simultáneas se solapan: pypdfium2 se corrompe y el expediente se pierde."""
        simultaneos, maximo = [], []
        cerrojo_prueba = threading.Lock()

        def falso_cargar(ticker, rutas, depositos=None):
            with cerrojo_prueba:
                simultaneos.append(1)
                maximo.append(len(simultaneos))
            threading.Event().wait(0.05)          # el tiempo que tarda en leer un PDF
            with cerrojo_prueba:
                simultaneos.pop()
            raise RuntimeError("sin expediente de prueba")   # basta con haber entrado: lo que se mide es el solape

        with mock.patch.object(saas.expediente, "cargar", falso_cargar), mock.patch.object(saas, "_rutas", lambda t: [saas.RAIZ / "x.pdf"]):
            hilos = [threading.Thread(target=lambda t=t: self.assertRaises(RuntimeError, saas.clasificar, t)) for t in ("AAA", "BBB", "CCC")]
            for h in hilos:
                h.start()
            for h in hilos:
                h.join(10)
        self.assertEqual(max(maximo), 1, f"hubo {max(maximo)} lecturas de documentos a la vez")

    def test_arrancar_la_carga_no_lanza_un_hilo_por_consulta(self):
        """Falla si preguntar por el estado mientras carga arranca otra carga: la página pregunta cada dos segundos."""
        lanzados = []
        with mock.patch.object(saas.threading, "Thread", lambda target, args, daemon: type("H", (), {"start": lambda s: lanzados.append(args)})()):
            saas._ESTADO.pop("ZZZ", None)
            for _ in range(5):
                saas.arrancar_carga("ZZZ")
        saas._ESTADO.pop("ZZZ", None)
        self.assertEqual(len(lanzados), 1, lanzados)


class SinMemoria(unittest.TestCase):
    """Una empresa cada vez: al abrir otra, lo anterior se suelta y el análisis nuevo parte de cero."""

    def tearDown(self):
        saas._ESTADO.clear()

    def test_abrir_otra_empresa_suelta_la_anterior(self):
        """Falla si el estado de una empresa sigue en memoria al abrir otra: su expediente son los textos de todos sus
        PDF, y la página local se va cargando de trabajo ajeno hasta arrastrarse."""
        saas._ESTADO.clear()
        saas.estado("AAA")["adjuntos"] = {"adjuntos": [{"fichero": "x.pdf"}], "avisos": []}
        nuevo = saas.estado("BBB")
        self.assertEqual(list(saas._ESTADO), ["BBB"])
        self.assertIsNone(nuevo["adjuntos"])
        self.assertIsNone(nuevo["traida"])

    def test_una_emision_en_marcha_no_se_suelta(self):
        """Falla si abrir otra empresa se lleva por delante una emisión viva: el proceso seguiría escribiendo y el
        analista se quedaría sin su registro a medio camino."""
        saas._ESTADO.clear()
        viva = saas.estado("AAA")
        viva["emision"] = {"proceso": type("P", (), {"poll": lambda s: None})(), "registro": None, "empezado": None, "orden": [], "fichero": None}
        saas.estado("BBB")
        self.assertEqual(sorted(saas._ESTADO), ["AAA", "BBB"])


if __name__ == "__main__":
    unittest.main()
