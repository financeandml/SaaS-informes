"""El extractor sobre los PDF reales, y las reglas del contraste (con y sin expediente)."""

import unittest
from datetime import date

from tests import contacto_sec_de_prueba, hay_cache_sec, rutas_nflx
from tesis.datos import campos, expediente, extractor
from tesis.verificacion import contraste
from tesis.fuentes import sec
from tesis.datos.extractor import Candidato
from tesis.datos.hechos import Contraste, Periodo

RUTAS = rutas_nflx()


def _cand(rotulo, contexto, valor, escala=1_000, por_accion=False, periodo=None):
    return Candidato(documento="doc.pdf", pagina=1, rotulo=rotulo, contexto=contexto, periodo=periodo or Periodo.de_meses(date(2026, 6, 30), 3),
                     etiqueta_columna="", valor=valor, crudo=str(valor), escala=escala, por_accion=por_accion, guion=False,
                     porcentaje=False, rect=(0, 0, 1, 1), rect_fila=(0, 0, 1, 1))


class ReglasDeCasado(unittest.TestCase):
    def test_revenue_regional_no_es_el_total(self):
        """Falla si `contexto_excluido` deja de aplicarse: «Revenue» bajo «UCAN» casaba con ingresos
        y cinco trimestres salían discrepantes."""
        c = campos.campo("ingresos")
        self.assertFalse(contraste._casa(c, _cand("Revenue", "UCAN", 4_929_000_000)))
        self.assertTrue(contraste._casa(c, _cand("Revenues", "", 12_559_938_000)))

    def test_basic_se_distingue_por_contexto(self):
        """Falla si el BPA básico y las acciones básicas dejan de distinguirse por la cabecera de bloque."""
        self.assertTrue(contraste._casa(campos.campo("bpa_basico"), _cand("Basic", "Earnings per share", 0.8, por_accion=True)))
        self.assertFalse(contraste._casa(campos.campo("bpa_basico"), _cand("Basic", "Weighted-average shares", 4_249_512_000)))
        self.assertTrue(contraste._casa(campos.campo("acciones_basicas"), _cand("Basic", "Weighted-average shares of common stock", 4_249_512_000)))

    def test_tolerancia_es_la_del_documento(self):
        """Falla si la carta en millones y el 10-Q en miles vuelven a salir discrepantes."""
        c = campos.campo("cfo")
        self.assertTrue(contraste._coincide(2_267_369_000, _cand("Free Cash Flow", "", 2_267_000_000, escala=1_000_000), c))
        self.assertFalse(contraste._coincide(2_267_369_000, _cand("Free Cash Flow", "", 2_267_000_000, escala=1_000), c))

    def test_pista_de_split(self):
        """Falla si una razón 10 entre SEC y documento en acciones no lleva la pista."""
        self.assertIn("split", contraste._pista(6.0, _cand("Basic", "Earnings per share", 0.6, por_accion=True), campos.campo("bpa_basico")))
        self.assertEqual("", contraste._pista(6.0, _cand("Basic", "Earnings per share", 5.0, por_accion=True), campos.campo("bpa_basico")))


@unittest.skipUnless(RUTAS, "sin expediente de NFLX (tests/expediente_nflx.json)")
class ExtractorReal(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import pypdfium2 as pdfium
        cls.k10 = expediente.cargar_adjunto(RUTAS[0]); cls.doc_k = pdfium.PdfDocument(str(cls.k10.ruta))
        cls.q2 = expediente.cargar_adjunto(RUTAS[2]); cls.doc_q = pdfium.PdfDocument(str(cls.q2.ruta))
        cls.web = expediente.cargar_adjunto(RUTAS[6]); cls.doc_w = pdfium.PdfDocument(str(cls.web.ruta))

    def test_10k_cuenta_de_resultados(self):
        """Falla si las columnas se asignan por orden y no por posición, si se pierde la escala o si el
        BPA se multiplica por mil."""
        p = extractor.leer_pagina(self.doc_k[41], 42, self.k10.nombre)
        self.assertEqual([c.periodo.clave for c in p.columnas], ["FY2025", "FY2024", "FY2023"])
        self.assertEqual(p.escala, 1_000)
        ingresos = next(f for f in p.filas if f.rotulo == "Revenues")
        self.assertEqual([c.valor for _, c in sorted(ingresos.celdas.items())], [45_183_036_000, 39_000_966_000, 33_723_297_000])
        basico = next(f for f in p.filas if f.rotulo == "Basic" and "per share" in f.contexto.lower())
        self.assertTrue(all(c.por_accion for c in basico.celdas.values()))
        self.assertEqual(basico.celdas[0].valor, 2.58)
        acciones = next(f for f in p.filas if f.rotulo == "Basic" and "shares" in f.contexto.lower())
        self.assertEqual(acciones.celdas[0].valor, 4_249_512_000)

    def test_10q_columnas_de_tres_y_seis_meses(self):
        """Falla si dos segmentos «Months Ended» en la misma línea se confunden."""
        p = extractor.leer_pagina(self.doc_q[2], 3, self.q2.nombre)
        self.assertEqual([c.periodo.clave for c in p.columnas], ["2T26", "2T25", "6M26", "6M25"])

    def test_pdf_en_configuracion_regional_espanola(self):
        """Falla si «10.542.801» y «0,68» no se leen como millares con punto y coma decimal, o si las ocho
        columnas (cuatro trimestres, ejercicio, dos trimestres, seis meses) no se reparten entre sus segmentos."""
        p = extractor.leer_pagina(self.doc_w[0], 1, self.web.nombre)
        self.assertEqual([c.periodo.clave for c in p.columnas], ["1T25", "2T25", "3T25", "4T25", "FY2025", "1T26", "2T26", "6M26"])
        ingresos = next(f for f in p.filas if f.rotulo == "Revenues")
        self.assertEqual(ingresos.celdas[0].valor, 10_542_801_000)
        basico = next(f for f in p.filas if f.rotulo == "Basic" and "per share" in f.contexto.lower())
        self.assertEqual(basico.celdas[0].valor, 0.68)

    def test_recorte_guarda_rectangulo(self):
        """Falla si un candidato deja de llevar su rectángulo (sin él no hay recorte)."""
        p = extractor.leer_pagina(self.doc_k[41], 42, self.k10.nombre)
        c = next(f for f in p.filas if f.rotulo == "Revenues").celdas[0]
        x0, y0, x1, y1 = c.rect
        self.assertTrue(x1 > x0 and y1 > y0)


@unittest.skipUnless(RUTAS and hay_cache_sec(), "sin expediente de NFLX o sin caché SEC")
class ContrasteReal(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        contacto_sec_de_prueba()
        cls.exp = expediente.cargar("NFLX", RUTAS)
        facts, obtenido = sec.companyfacts("0001065280")
        cls.periodos = contraste.periodos_del_informe(cls.exp)
        cls.tab = contraste.contrastar(cls.exp, facts, obtenido, cls.periodos)

    def test_resumen_de_referencia(self):
        """Falla si cambia la contabilidad del contraste sobre el expediente de referencia. Las cuatro
        discrepancias del split desaparecen al reexpresar como derivado; ninguna queda."""
        r = self.tab.resumen
        self.assertGreaterEqual(r.get("confirmado", 0), 195)
        self.assertEqual(r.get("discrepante", 0), 0)
        self.assertGreaterEqual(r.get("derivado", 0), 20)

    def test_4t_derivado_y_confirmado_por_el_documento(self):
        """Falla si el 4T deja de derivarse (FY − 9M) o de contrastarse con el XLSX."""
        r = self.tab.de("ingresos", Periodo.de_meses(date(2025, 12, 31), 3))
        self.assertIs(r.hecho.contraste, Contraste.DERIVADO)
        self.assertEqual(r.hecho.valor, 12_050_762_000)
        self.assertIsNotNone(r.evidencia)

    def test_4t_no_se_deriva_para_bpa(self):
        """Falla si el 4T de un BPA se calcula restando (no es aditivo)."""
        r = self.tab.de("bpa_basico", Periodo.de_meses(date(2025, 12, 31), 3))
        self.assertIsNot(r.hecho.contraste, Contraste.DERIVADO)

    def test_dividendos_cero_declarado_con_cita(self):
        """Falla si la frase «never declared or paid» del 10-K deja de convertir el N/A en cero con página."""
        r = self.tab.de("dividendos", Periodo.anual(date(2025, 12, 31)))
        self.assertEqual(r.hecho.valor, 0.0)
        self.assertIsNotNone(r.hecho.origen.pagina)
        self.assertIn("never", r.hecho.nota.lower())

    def test_confirmado_lleva_evidencia_con_pagina(self):
        """Falla si un ✓ pierde el candidato del que se recorta la prueba."""
        r = self.tab.de("ingresos", Periodo.anual(date(2025, 12, 31)))
        self.assertIs(r.hecho.contraste, Contraste.CONFIRMADO)
        self.assertEqual(r.evidencia.pagina, 42)


if __name__ == "__main__":
    unittest.main()
