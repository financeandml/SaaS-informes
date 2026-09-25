"""La emisión desde el SaaS: qué orden se lanza y cómo se lee su resultado. Sin red y sin emitir de verdad.

El caso que las trajo (22/09/2026, expediente de Oracle): la página daba el código 1 de un proceso que reventaba por
«borrador», que es lo que devuelve una emisión buena con discrepancias sin decidir. Desde el 24/09/2026 no hay IA en
tiempo de ejecución: la orden nunca lleva `--redactar` ni `--narrativa`.
"""

import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

from tesis import saas


class _Proceso:
    """Un subproceso que ya terminó con este código."""

    def __init__(self, codigo):
        self.codigo = codigo

    def poll(self):
        return self.codigo


class Emision(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.parches = [mock.patch.object(saas, n, base / n.lower()) for n in ("ADJUNTOS", "DCF", "SALIDA")]
        for p in self.parches:
            p.start()
        (saas.ADJUNTOS / "PRUEBA").mkdir(parents=True)
        (saas.ADJUNTOS / "PRUEBA" / "10k.pdf").write_bytes(b"%PDF-1.4")
        saas._ESTADO.pop("PRUEBA", None)
        self.addCleanup(self._limpiar)

    def _limpiar(self):
        saas._ESTADO.pop("PRUEBA", None)
        for p in self.parches:
            p.stop()
        self.tmp.cleanup()

    def test_la_emision_no_pide_redactar(self):
        """Falla si la orden de emisión vuelve a llevar redacción por IA («--redactar» o «--narrativa»)."""
        with mock.patch.object(saas.subprocess, "Popen", lambda *a, **k: _Proceso(None)):
            saas.emitir("PRUEBA")
        orden = saas.estado("PRUEBA")["emision"]["orden"]
        self.assertNotIn("--redactar", orden)
        self.assertNotIn("--narrativa", orden)
        self.assertIn("--carpeta", orden)

    def test_una_emision_que_revienta_no_pasa_por_borrador(self):
        """Falla si un código 1 sin PDF (traceback del proceso) se enseña como «terminado · borrador»: son cosas
        distintas, y el analista se creería que tiene informe. El PDF manda, no el código."""
        registro = saas.SALIDA / "PRUEBA" / "emision.log"
        registro.parent.mkdir(parents=True, exist_ok=True)
        registro.write_text("TypeError: no hay con qué autenticarse\n", encoding="utf-8")
        saas.estado("PRUEBA")["emision"] = {"proceso": _Proceso(1), "registro": registro, "empezado": datetime.now(),
                                            "orden": ["emitir.py"], "fichero": registro.open("a", encoding="utf-8")}
        e = saas.estado_emision("PRUEBA")
        self.assertEqual((e["estado"], e["borrador"], e["pdf"]), ("error", False, None))
        # el mismo código 1 con PDF sí es un borrador: hay informe, con discrepancias sin decidir
        (saas.SALIDA / "PRUEBA" / "PRUEBA_tesis_2026-09-22.pdf").write_bytes(b"%PDF-1.4")
        (saas.SALIDA / "PRUEBA" / "PRUEBA_tesis_2026-09-22.html").write_text("<html></html>", encoding="utf-8")
        e = saas.estado_emision("PRUEBA")
        self.assertEqual((e["estado"], e["borrador"]), ("terminado", True))
        self.assertEqual(e["pdf"], "/informes/PRUEBA/PRUEBA_tesis_2026-09-22.pdf")
        self.assertTrue(e["html"].endswith(".html"))

    def test_un_pdf_de_una_emision_anterior_no_se_da_por_recien_hecho(self):
        """Falla si, al reventar una emisión nueva, se enseña el PDF de la emisión anterior como si fuera el suyo."""
        viejo = saas.SALIDA / "PRUEBA" / "PRUEBA_tesis_2026-09-01.pdf"
        viejo.parent.mkdir(parents=True, exist_ok=True)
        viejo.write_bytes(b"%PDF-1.4")
        antiguo = viejo.stat().st_mtime - 3600
        os.utime(viejo, (antiguo, antiguo))
        registro = saas.SALIDA / "PRUEBA" / "emision.log"
        registro.write_text("Traceback\n", encoding="utf-8")
        saas.estado("PRUEBA")["emision"] = {"proceso": _Proceso(1), "registro": registro, "empezado": datetime.now(),
                                            "orden": ["emitir.py"], "fichero": registro.open("a", encoding="utf-8")}
        e = saas.estado_emision("PRUEBA")
        self.assertEqual((e["estado"], e["pdf"]), ("error", None))


if __name__ == "__main__":
    unittest.main()
