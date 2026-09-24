"""La narrativa: ninguna frase sin cita, ninguna cifra sin hecho o sin página. Cada prueba dice qué defecto la hace fallar."""

import copy
import json
import unittest
from datetime import date
from pathlib import Path

from tests import contacto_sec_de_prueba, hay_cache_sec, rutas_nflx
from tesis import contraste, derivados, expediente, narrativa, sec

RUTAS = rutas_nflx()
NARRATIVA_NFLX = Path(__file__).resolve().parents[1] / "narrativas" / "NFLX_2026-09-17.json"


class Cifras(unittest.TestCase):
    def test_cifras_en_convencion_espanola(self):
        """Falla si el lector de cifras confunde años, fechas, etiquetas de periodo o formularios con cifras."""
        frase = "En el 2T26 (a 30/06/2026) los ingresos crecieron un 13 % hasta 12.560 M USD, 0,80 USD por acción; el 10-K de 2025 y un split 10:1 no son cifras; rango 51.000–51.400."
        self.assertEqual(narrativa.cifras_de(frase), [(13.0, 0), (12560.0, 0), (0.80, 2), (51000.0, 0), (51400.0, 0)])

    def test_casa_con_escala_y_tolerancia(self):
        """Falla si una cifra en millones deja de casar con el hecho en unidades, o si casa con lo que no debe."""
        self.assertTrue(narrativa._casa(12560.0, 0, 12_559_938_000.0))     # millones frente a unidades, redondeo de la última cifra
        self.assertTrue(narrativa._casa(33.4, 1, 0.33381))                 # porcentaje frente a ratio
        self.assertTrue(narrativa._casa(2800.0, 0, 2.8))                   # «2.800 M» frente a «$2.8 billion»
        self.assertFalse(narrativa._casa(12561.0, 0, 12_559_938_000.0))    # una unidad de más en la última cifra
        self.assertFalse(narrativa._casa(0.81, 2, 0.80))


@unittest.skipUnless(RUTAS and hay_cache_sec() and NARRATIVA_NFLX.exists(), "sin expediente de NFLX, sin caché SEC o sin narrativa")
class VerificacionSobreNetflix(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        contacto_sec_de_prueba()
        emisor = sec.emisor("NFLX")
        cls.exp = expediente.cargar("NFLX", RUTAS, emisor.depositos)
        facts, obtenido = sec.companyfacts(emisor.cik)
        periodos = contraste.periodos_del_informe(cls.exp)
        tab = contraste.contrastar(cls.exp, facts, obtenido, periodos)
        cls.hechos = derivados.calcular(tab.hechos(), periodos["anuales"] + periodos["trimestres"], periodos["instantes"])
        cls.base = json.loads(NARRATIVA_NFLX.read_text(encoding="utf-8"))

    def _verificar(self, d: dict) -> narrativa.Verificacion:
        return narrativa.verificar(narrativa.de_dict(d), self.exp, self.hechos)

    def test_la_narrativa_emitida_pasa_entera(self):
        """Falla si una frase de la narrativa que se imprime pierde su cita o una cifra deja de coincidir con el hecho."""
        v = self._verificar(self.base)
        self.assertEqual([(r.donde, r.motivo) for r in v.reparos], [])
        self.assertEqual(v.certeza.value, "alta")
        self.assertEqual(len(narrativa.de_dict(self.base).pilares), 5)

    def test_cifra_alterada_retira_la_frase(self):
        """Falla si el verificador deja pasar «12.570 M USD» cuando el hecho contrastado dice 12.559.938 miles."""
        d = copy.deepcopy(self.base)
        f = d["resumen"][1][0]
        self.assertIn("12.560", f["texto"])
        f["texto"] = f["texto"].replace("12.560", "12.570")
        v = self._verificar(d)
        self.assertIn("resumen §2 frase 1", v.retiradas)
        self.assertTrue(any("12570" in r.motivo for r in v.graves))

    def test_ancla_que_no_esta_en_la_pagina_retira_la_frase(self):
        """Falla si una cita a una página que no contiene el ancla se da por buena."""
        d = copy.deepcopy(self.base)
        d["resumen"][0][1]["apoyos"][0]["ancla"] = "grow our business by acquiring competitors"
        v = self._verificar(d)
        self.assertIn("resumen §1 frase 2", v.retiradas)

    def test_pagina_equivocada_retira_la_frase(self):
        """Falla si el ancla se busca en todo el documento y no en la página citada."""
        d = copy.deepcopy(self.base)
        d["resumen"][0][1]["apoyos"][0]["pagina"] = 5
        v = self._verificar(d)
        self.assertIn("resumen §1 frase 2", v.retiradas)

    def test_frase_sin_cita_y_hecho_na_son_graves(self):
        """Falla si una frase sin apoyo o que declara un hecho N/A llega a imprimirse."""
        d = copy.deepcopy(self.base)
        d["resumen"][0][1]["apoyos"] = []
        d["resumen"][1][0]["cifras"].append("fondo_comercio:@2026-06-30")
        v = self._verificar(d)
        self.assertIn("resumen §1 frase 2", v.retiradas)
        self.assertIn("resumen §2 frase 1", v.retiradas)

    def test_dossier_es_determinista_y_nombra_las_paginas(self):
        """Falla si el dossier cambia entre dos llamadas o deja de citar la clave del documento con la página."""
        a = narrativa.dossier(self.exp, self.hechos)
        self.assertEqual(a, narrativa.dossier(self.exp, self.hechos))
        self.assertIn("=== documento CARTA_20260630 (Carta 2T26", a)
        self.assertIn("ingresos:2T26 · 12,559,938,000.0000 · USD · ✓", a)

    def test_sin_sdk_no_hay_redactor(self):
        """Falla si, sin el paquete «anthropic», redactar_con_claude devuelve algo en vez de decir que falta."""
        import importlib.util
        if importlib.util.find_spec("anthropic") is not None:
            self.skipTest("el SDK está instalado")
        with self.assertRaises(narrativa.SinRedactor):
            narrativa.redactar_con_claude("dossier")


if __name__ == "__main__":
    unittest.main()
