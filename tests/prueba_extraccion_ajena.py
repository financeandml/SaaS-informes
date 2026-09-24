"""Leer los estados financieros de un emisor que no maqueta como Netflix. Sin red.

El caso que las trajo (22/09/2026, Oracle): su balance y su cuenta de resultados ponen las unidades en la misma línea
que los años —«(in millions, except per share data) 2026 2025»— y separan el patrimonio del grupo del total con
minoritarios. Con la regla anterior no se leía ninguna de esas páginas: de 400 cifras del informe solo 14 estaban
confirmadas por los documentos que el analista había adjuntado.
"""

import unittest
from datetime import date
from pathlib import Path

from tesis import contraste
from tesis.campos import campo as campo_de
from tesis.expediente import Tipo
from tesis.extractor import Linea, Token, _columnas_de
from tesis.hechos import Periodo


def _linea(texto, y=100.0):
    """Una línea con sus tokens repartidos a lo ancho, como los devuelve el PDF."""
    tokens, x = [], 40.0
    for palabra in texto.split("  "):
        if palabra.strip():
            tokens.append(Token(palabra.strip(), x, x + 8 * len(palabra), y, y + 9))
        x += 8 * len(palabra) + 16
    return Linea(tokens)


def _cand(rotulo, valor, pagina=1):
    from tesis.extractor import Candidato
    return Candidato(documento="10k.pdf", pagina=pagina, rotulo=rotulo, contexto="", periodo=Periodo.instante(date(2026, 5, 31)),
                     etiqueta_columna="", valor=valor, crudo=str(valor), escala=1_000_000, por_accion=False, guion=False,
                     porcentaje=False, rect=(0, 0, 1, 1), rect_fila=(0, 0, 1, 1))


class Cabecera(unittest.TestCase):
    def test_los_anios_se_leen_aunque_la_linea_traiga_el_rotulo_de_unidades(self):
        """Falla si «(in millions, except per share data)  2026  2025» no se reconoce como cabecera: sin columnas, el
        balance y la cuenta de resultados enteros se descartan y el informe no usa el 10-K."""
        cols, idx = _columnas_de([_linea("ORACLE CORPORATION", 300), _linea("CONSOLIDATED BALANCE SHEETS", 290),
                                  _linea("May 31,", 280), _linea("(in millions, except per share data)  2026  2025", 270)])
        self.assertEqual(len(cols), 2)
        self.assertEqual([c.fin for c in cols], [date(2026, 5, 31), date(2025, 5, 31)])
        self.assertEqual(idx, 3)

    def test_una_fila_de_importes_con_anios_no_es_una_cabecera(self):
        """Falla si una fila de datos con años a la derecha —vencimientos de deuda— se toma por cabecera de la tabla."""
        cols, _ = _columnas_de([_linea("Maturities of debt  1,250  2026  2027")])
        self.assertEqual(cols, [])

    def test_la_cabecera_limpia_de_siempre_sigue_valiendo(self):
        cols, _ = _columnas_de([_linea("Year Ended December 31,", 300), _linea("2025  2024", 290)])
        self.assertEqual([c.fin for c in cols], [date(2025, 12, 31), date(2024, 12, 31)])


class Patrimonio(unittest.TestCase):
    def test_gana_el_patrimonio_del_grupo_sobre_el_total_con_minoritarios(self):
        """Falla si, existiendo las dos filas en el balance, se toma «Total stockholders' equity» (con minoritarios):
        no es el concepto que publica la SEC (StockholdersEquity) y el informe saldría en discrepancia consigo mismo."""
        c = campo_de("patrimonio")
        grupo = _cand("Total Oracle Corporation stockholders’ equity", 42_508)
        total = _cand("Total stockholders’ equity", 43_056)
        self.assertEqual(contraste._indice_fila(c, grupo), 0)
        self.assertEqual(contraste._indice_fila(c, total), 1)
        self.assertTrue(contraste._casa(c, grupo) and contraste._casa(c, total))

    def test_el_balance_solo_aporta_la_fila_del_grupo(self):
        """Falla si del balance salen las dos filas como candidatas del mismo campo: una confirmaría el hecho de la SEC
        y la otra lo desmentiría, y el informe acabaría con una discrepancia inventada por nosotros (regla 9)."""
        from tesis.extractor import Fila, PaginaLeida

        class _Adj:
            clave, tipo, ruta, paginas = "10K_20260531", Tipo.K10, Path("10k.pdf"), [""]

        class _Exp:
            adjuntos = [_Adj()]

        grupo = _cand("Total Oracle Corporation stockholders’ equity", 42_508)
        total = _cand("Total stockholders’ equity", 43_056)
        pagina = PaginaLeida(numero=66, lineas=[], escala=1_000_000, titulo="CONSOLIDATED BALANCE SHEETS", columnas=[],
                             filas=[Fila(rotulo=grupo.rotulo, contexto="", celdas={0: grupo}, rect=(0, 0, 1, 1)),
                                    Fila(rotulo=total.rotulo, contexto="", celdas={0: total}, rect=(0, 0, 1, 1))])
        cands = contraste._candidatos_por_campo(_Exp(), {"10K_20260531": [pagina]})["patrimonio"]
        self.assertEqual([c.valor for _, c in cands], [42_508])

    def test_el_total_de_pasivo_y_patrimonio_nunca_es_el_patrimonio(self):
        """Falla si «Total liabilities and stockholders' equity» (que es el activo) casa con el patrimonio."""
        self.assertFalse(contraste._casa(campo_de("patrimonio"), _cand("Total liabilities and stockholders’ equity", 261_759)))

    def test_sin_minoritarios_vale_la_fila_de_siempre(self):
        self.assertTrue(contraste._casa(campo_de("patrimonio"), _cand("Total stockholders’ equity", 24_743)))


class LibroAjeno(unittest.TestCase):
    """Un libro DCF con otra maqueta: hojas en inglés y bloques que no son los que el lector espera."""

    def test_una_fila_que_no_es_un_escenario_no_se_lee_como_tal(self):
        """Falla si una fila de importes bajo el rótulo «Escenarios» pasa por escenario: «Equity Value 496.514 · 303.615»
        se imprimía como un WACC del 49.651.483 % y un crecimiento del 30.361.500 %."""
        from tesis.dcf import _parece_escenario
        self.assertFalse(_parece_escenario([496514.8, 303615.0, 608375.0, 952026.0]))
        self.assertFalse(_parece_escenario([2934.0, 191755.0, 496515.0, 840166.0]))
        self.assertTrue(_parece_escenario([0.105, 0.025, 36.26, 0.25]))      # fracciones
        self.assertTrue(_parece_escenario([10.5, 2.5, 36.26, 25]))           # en puntos
        self.assertFalse(_parece_escenario([0.095, 0.0325, 0.0, 0.5]))       # sin valor no hay escenario

    def test_las_hojas_se_reconocen_tambien_en_ingles(self):
        """Falla si «08 Sensitivity» no se reconoce como la hoja de sensibilidad."""
        import re

        from tesis import dcf
        fuente = Path(dcf.__file__).read_text(encoding="utf-8")
        patron = re.search(r'libro\.hoja\(r"(sensib[^"]*)"\)', fuente).group(1)
        self.assertTrue(re.search(patron, "08 Sensitivity", re.I))
        self.assertTrue(re.search(patron, "Sensibilidad", re.I))


class Riesgos(unittest.TestCase):
    """El Item 1A de un 10-K que no se maqueta como el de Netflix."""

    def test_la_cabecera_de_familia_se_reconoce_aunque_no_diga_related_to(self):
        """Falla si «Business and Operational Risks» (Oracle) no se reconoce como cabecera: se pega al epígrafe
        siguiente y el Item 1A entero sale como un solo riesgo, que es lo que pasaba."""
        from tesis.riesgos import _es_cabecera
        for cabecera in ("Business and Operational Risks", "Legal and Regulatory Risks", "General Risks", "Risks Related to Our Business"):
            self.assertTrue(_es_cabecera(cabecera), cabecera)
        for epigrafe in ("We may be unsuccessful in developing and selling new products and services.",
                         "Risk of loss is ours until delivery.",
                         "Our AI products may not operate as anticipated, which could adversely affect our revenues."):
            self.assertFalse(_es_cabecera(epigrafe), epigrafe)

    def test_un_epigrafe_cortado_se_completa_con_el_texto_de_su_pagina(self):
        """Falla si un epígrafe cuya última línea comparte renglón con el cuerpo —y deja de contar como negrita— se
        descarta por no acabar en punto: así se perdían 22 de los 23 riesgos de Oracle."""
        from tesis.riesgos import _completar
        pagina = ("Business and Operational Risks\nWe may be unsuccessful in developing and selling new products and services, integrating "
                  "acquired businesses and technologies.\nOur industry is characterized by rapid technological advances.")
        entero = _completar("We may be unsuccessful in developing and selling new products and services, integrating", pagina)
        self.assertTrue(entero.endswith("technologies."), entero)
        self.assertNotIn("Our industry", entero)
        self.assertIsNone(_completar("Una frase que no está en la página", pagina))


if __name__ == "__main__":
    unittest.main()
