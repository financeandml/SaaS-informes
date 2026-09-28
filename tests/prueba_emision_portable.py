"""El estado del informe sobrevive a un `git clone` (29/09/2026).

Al clonar, git pone a todos los ficheros la hora del clonado. «Emitido», «al día» y «el último informe» salían de esas
fechas: en el clon, todos los informes salían emitidos a la hora del clonado, NFLX, ORCL y QCOM «no al día» y, con
varios informes, podía enseñarse uno que no era el último. Ahora salen de `<informe>.emision.json` y del nombre.
"""

import os
import tempfile
import time
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

from tesis.web import saas


class TrasUnClonado(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / "adjuntos" / "QCOM").mkdir(parents=True)
        (self.tmp / "salida" / "QCOM").mkdir(parents=True)
        (self.tmp / "dcf").mkdir()
        self.adjunto = self.tmp / "adjuntos" / "QCOM" / "10k.pdf"
        self.adjunto.write_bytes(b"10-K")
        self.parches = [mock.patch.object(saas, "ADJUNTOS", self.tmp / "adjuntos"), mock.patch.object(saas, "SALIDA", self.tmp / "salida"),
                        mock.patch.object(saas, "DCF", self.tmp / "dcf"), mock.patch.object(saas, "_entradas_analista", lambda t: None)]
        for p in self.parches:
            p.start()
        salida = self.tmp / "salida" / "QCOM"
        for fecha in ("2026-09-26", "2026-09-27"):
            (salida / f"QCOM_tesis_{fecha}.pdf").write_bytes(b"pdf")
        saas.escribir_emision("QCOM", salida / "QCOM_tesis_2026-09-27", datetime(2026, 9, 27, 19, 31))

    def tearDown(self):
        for p in self.parches:
            p.stop()

    def _clonar(self, *primero):
        """Todas las fechas de los ficheros cambian, y en un orden cualquiera (los de `primero`, más antiguos)."""
        ahora = time.time()
        for k, p in enumerate(sorted(self.tmp.rglob("*"), key=lambda p: p not in primero)):
            if p.is_file():
                os.utime(p, (ahora + k, ahora + k))

    def test_al_dia_y_emitido_no_dependen_de_la_fecha_de_los_ficheros(self):
        """Falla si, tras clonar, el informe sale «no al día» o emitido a la hora del clonado."""
        self._clonar(self.tmp / "salida" / "QCOM" / "QCOM_tesis_2026-09-27.pdf")      # el PDF, más viejo que el adjunto
        i = saas.informe_en_disco("QCOM")
        self.assertEqual(i["fichero"], "QCOM_tesis_2026-09-27.pdf")
        self.assertEqual(i["emitido"], "27/09/2026 19:31")
        self.assertTrue(i["al_dia"])

    def test_el_ultimo_es_el_de_fecha_mas_reciente_en_su_nombre(self):
        """Falla si se enseña el informe del 26 porque su fichero quedó con una hora posterior al del 27."""
        self._clonar(self.tmp / "salida" / "QCOM" / "QCOM_tesis_2026-09-27.pdf")
        self.assertEqual(saas.informe_en_disco("QCOM")["fichero"], "QCOM_tesis_2026-09-27.pdf")

    def test_cambiar_un_adjunto_lo_deja_no_al_dia(self):
        """Falla si un documento cambiado o añadido después de emitir no marca el informe como viejo."""
        self.adjunto.write_bytes(b"10-K reexpresado")
        self.assertFalse(saas.informe_en_disco("QCOM")["al_dia"])
        self.adjunto.write_bytes(b"10-K")
        self.assertTrue(saas.informe_en_disco("QCOM")["al_dia"])
        (self.tmp / "adjuntos" / "QCOM" / "10q.pdf").write_bytes(b"10-Q")
        self.assertFalse(saas.informe_en_disco("QCOM")["al_dia"])


if __name__ == "__main__":
    unittest.main()
