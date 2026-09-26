"""Clasificación de los documentos de resultados que no son la carta al estilo de Netflix: nota de prensa del 8-K,
las tablas de su anexo 99.1 y la presentación. Sin red.

El caso que las trajo: el expediente de Oracle (22/09/2026) son una nota de prensa, unas diapositivas y las tablas del
anexo 99.1; los tres salían «desconocido» y no entraban en ningún apartado del informe.
"""

import unittest
from datetime import date
from pathlib import Path

from tesis.datos import documentos
from tesis.web import saas
from tesis.datos.expediente import APARTADO_DE, Adjunto, Certeza, Tipo, clasificar

NOTA = ("Contact: Ken Bond\n"
        "Oracle Investor Relations\n"
        "1.650.607.0349\n\n"
        "Oracle Announces Q1 Results Driven by Triple Digit Growth in Cloud Infrastructure Revenues\n"
        "September 10, 2026\n"
        "- Q1 GAAP Earnings per Share up 55% to $1.56.")
TABLAS = ("ORACLE CORPORATION\n"
          "Q1 FISCAL 2027 FINANCIAL RESULTS\n"
          "CONDENSED CONSOLIDATED STATEMENTS OF OPERATIONS\n"
          "($ in millions, except per share data)\n"
          "REVENUES\nCloud $ 11,607 60%")
SLIDES = "Q1 Fiscal Year 2027\nEarnings\nSeptember 10, 2026\nCopyright 2026, Oracle and/or its affiliates."
WEB = ("Netflix, Inc.\nCondensed Consolidated Statements of Operations\n"
       "(unaudited)\n(in thousands, except per share data)\n"
       "March 31, June 30,\n2026 2026\nRevenues 11,510 12,051")


def _clasificar(p1, primeras=None):
    return clasificar(p1, "", primeras if primeras is not None else p1)


class Clasificacion(unittest.TestCase):
    def test_la_nota_de_resultados_del_8k(self):
        """Falla si la nota de prensa de resultados queda «desconocido» (no se usaría en ningún apartado) o si se le
        atribuye un cierre de periodo que la portada no declara: «Q1» de un ejercicio no natural no dice cuál es."""
        c = _clasificar(NOTA)
        self.assertIs(c["tipo"], Tipo.NOTA)
        self.assertIs(c["certeza"], Certeza.ALTA)
        self.assertEqual(c["fecha"], date(2026, 9, 10))
        self.assertIsNone(c["periodo_fin"])
        self.assertIn("no se le atribuye ninguno", c["motivo"])

    def test_la_nota_titulada_reports_results_tambien_es_la_nota(self):
        """Falla si la nota que se titula «… reports … results» (en minúsculas, y sin «Announces») queda «desconocido»:
        el anexo 99.1 de Apple (30/07/2026) se trajo de EDGAR y la casilla de la nota seguía diciendo «falta»."""
        nota = ("EX-99.1 2 a8-kex991.htm EX-99.1\nExhibit 99.1\n"
                "Apple reports third quarter results\n"
                "June quarter records for total company revenue and EPS\n"
                "CUPERTINO, CALIFORNIA — Apple today announced financial results for its fiscal 2026 third quarter ended June 27, 2026.\n"
                "Apple will provide live streaming of its Q3 2026 financial results conference call beginning at 2:00 p.m. PT on July 30, 2026.\n"
                "Apple periodically provides information for investors on its corporate website, and its investor relations website.")
        c = _clasificar(nota)
        self.assertIs(c["tipo"], Tipo.NOTA)
        self.assertIs(c["certeza"], Certeza.ALTA)
        self.assertIsNone(c["periodo_fin"])        # mismo criterio que la nota con «Announces»: no se le atribuye cierre
        # la primera fecha de esta portada es el cierre del trimestre, no la publicación: tomarla fechaba la nota el 27/06
        self.assertIsNone(c["fecha"])
        # sin el bloque de relación con inversores, un titular así no basta: no se amplía la regla más de lo necesario
        self.assertIs(_clasificar("Apple reports third quarter results\nJune 27, 2026")["tipo"], Tipo.DESCONOCIDO)

    def test_los_titulares_de_resultados_de_cualquier_emisor(self):
        """Falla si la nota de resultados solo se reconoce con los verbos de dos emisores concretos. Los titulares
        habituales («posts», «delivers», «releases») y la fórmula «today announced … results» sin bloque de inversores
        también son la nota; un titular suelto, sin ninguna de las dos pruebas, no."""
        for nota in ("Acme Corp Posts Record Second Quarter Results\nContacts: Investor Relations",
                     "Globex delivers strong fiscal 2026 results\nFor more information, visit our investor relations site",
                     "Initech Releases First Quarter 2026 Financial Results\nInvestor Relations contact: ir@initech.test",
                     "Beta Inc. Reports Fourth Quarter Results\nBeta Inc. today announced financial results for its fourth quarter."):
            self.assertIs(_clasificar(nota)["tipo"], Tipo.NOTA, nota)
        self.assertIs(_clasificar("Acme Corp Posts Record Second Quarter Results\nJune 30, 2026")["tipo"], Tipo.DESCONOCIDO)

    def test_una_nota_con_los_estados_cuenta_tambien_como_cuentas_del_anexo(self):
        """Falla si una nota o una carta que trae en sus páginas los estados condensados no cuenta también como «cuentas
        del anexo 99.1» (la casilla decía «falta» con las cuentas adjuntadas), o si basta con mencionarlos en la prosa."""
        from tesis.datos.expediente import tambien
        estados = "Apple Inc.\nCONDENSED CONSOLIDATED STATEMENTS OF OPERATIONS (Unaudited)\nNet sales: 109,417"
        self.assertEqual(tambien(Tipo.NOTA, ["portada", "texto", estados]), (Tipo.TABLAS,))
        self.assertEqual(tambien(Tipo.CARTA, ["portada", "Condensed Consolidated Statements of Operations\n(unaudited)"]), (Tipo.TABLAS,))
        prosa = "see the condensed consolidated statements of operations included in our Form 10-Q for details"
        self.assertEqual(tambien(Tipo.NOTA, ["portada", prosa]), ())
        self.assertEqual(tambien(Tipo.NOTA, [estados]), ())            # la portada ya es la nota: se miran las siguientes
        self.assertEqual(tambien(Tipo.Q10, ["portada", estados]), ())   # un 10-Q no es un anexo del 8-K

    def test_las_tablas_del_anexo_991_toman_su_cierre_aunque_venga_partido(self):
        """Falla si las tablas del 8-K quedan «desconocido» o si no toman el cierre del periodo porque «Three Months
        Ended» y la fecha vienen en líneas distintas, como los imprime el PDF."""
        # el PDF parte la fecha: «Ended August 31,» y «2026» caen en líneas distintas
        c = _clasificar(TABLAS, TABLAS + "\nThree Months Ended August 31,\r\n2026 compared with\nTotal revenues 19,345")
        self.assertIs(c["tipo"], Tipo.TABLAS)
        self.assertEqual(c["periodo_fin"], date(2026, 8, 31))
        self.assertIn("anexo 99.1", c["motivo"])
        sin_cierre = _clasificar(TABLAS)
        self.assertIs(sin_cierre["tipo"], Tipo.TABLAS)
        self.assertIsNone(sin_cierre["periodo_fin"])
        self.assertIn("no declara el cierre", sin_cierre["motivo"])

    def test_la_presentacion_de_resultados(self):
        """Falla si la portada de diapositivas queda «desconocido», o si un documento largo que menciona «Earnings»
        (una nota, un 10-Q) pasa por presentación."""
        c = _clasificar(SLIDES)
        self.assertIs(c["tipo"], Tipo.PRESENTACION)
        self.assertEqual(c["fecha"], date(2026, 9, 10))
        self.assertIs(_clasificar("Q1 Fiscal Year 2027 Earnings " + "texto de relleno " * 40)["tipo"], Tipo.DESCONOCIDO)

    def test_el_fichero_de_cuentas_de_la_web_no_lo_roba_la_regla_nueva(self):
        """Falla si la regla de las tablas del 8-K (versales) se queda con el fichero de cuentas de la web del emisor."""
        self.assertIs(_clasificar(WEB)["tipo"], Tipo.FINWEB)

    def test_cada_tipo_nuevo_tiene_apartado_clave_propia_y_destino(self):
        """Falla si un tipo nuevo no entra en ningún apartado, comparte clave con otro (un documento pisaría al otro
        en el expediente) o no declara en el SaaS dónde va en el informe."""
        claves = set()
        for tipo in (Tipo.NOTA, Tipo.TABLAS, Tipo.PRESENTACION):
            self.assertIn(tipo, APARTADO_DE, tipo)
            self.assertNotEqual(documentos.destino(tipo), documentos.SIN_DESTINO, tipo)
            claves.add(Adjunto(ruta=Path("x.pdf"), huella="h", paginas=[""], tipo=tipo, apartado=APARTADO_DE[tipo],
                               certeza=Certeza.ALTA, motivo="", periodo_fin=date(2026, 8, 31)).clave)
        self.assertEqual(len(claves), 3, claves)


class Tablas(unittest.TestCase):
    """Qué tabla de un documento son las cuentas y cuál no: una conciliación o un desglose tienen las mismas filas."""

    def _pagina(self, titulo, *lineas):
        from tesis.datos.extractor import Linea, PaginaLeida, Token
        return PaginaLeida(numero=1, lineas=[Linea([Token(t, 0, 10, 0, 10) for t in l.split()]) for l in lineas],
                           escala=1, titulo=titulo, columnas=[], filas=[])

    def test_la_conciliacion_gaap_a_no_gaap_no_son_las_cuentas(self):
        """Falla si la página de conciliación entra como fuente: sus columnas son ajustes (retribución en acciones,
        amortización), así que «Tecnología y desarrollo» saldría por la cuarta parte de su valor y en discrepancia con la SEC."""
        from tesis.verificacion.contraste import es_conciliacion
        p = self._pagina("ORACLE CORPORATION", "($ in millions, except per share data)", "2026 2026 2025 2025",
                         "GAAP Adj. Non-GAAP GAAP Adj. Non-GAAP", "TOTAL REVENUES $ 19,345 $ - $ 19,345")
        self.assertTrue(es_conciliacion(p))

    def test_un_desglose_de_otra_partida_no_son_las_cuentas(self):
        """Falla si la tabla de retribución en acciones por línea de gasto, o la de información geográfica, entra como
        fuente: sus filas se llaman igual que las del estado de resultados («Sales and marketing») y sus cifras son otras."""
        from tesis.verificacion.contraste import es_conciliacion
        self.assertTrue(es_conciliacion(self._pagina(
            "Table of Contents", "Stock-based compensation was included in the following operating expense line items of our "
            "consolidated statements of operations (in millions):", "Year Ended May 31,", "2026 2025", "Sales and marketing 759 757")))
        self.assertTrue(es_conciliacion(self._pagina("Table of Contents", "Geographic Information",
                                                     "Disclosed in the table below is geographic information for each country")))

    def test_el_estado_de_resultados_si_son_las_cuentas(self):
        """Falla si la regla se lleva por delante el estado de resultados (el de la SEC o el de la web del emisor)."""
        from tesis.verificacion.contraste import es_conciliacion
        self.assertFalse(es_conciliacion(self._pagina(
            "CONDENSED CONSOLIDATED STATEMENTS OF OPERATIONS", "($ in millions, except per share data)",
            "Three Months Ended August 31,", "2026 2025", "Total revenues 19,345 14,926")))
        self.assertFalse(es_conciliacion(self._pagina(
            "Consolidated Statements of Operations", "(unaudited)", "(in thousands, except per share data)",
            "Three Months Ended", "June 30, 2026", "Revenues 12,051")))


class PortadasQueNoDicenNada(unittest.TestCase):
    """Los cuatro documentos de Qualcomm (23/09/2026) que salían «desconocido» con aviso grave y, por tanto, sin entrar
    en ningún apartado del informe: la proxy maquetada por el emisor (portada de imagen, sin texto), la carátula del
    8-K, la transcripción de otro proveedor (en versales) y la presentación (rótulo partido en dos líneas y descargo
    legal debajo). Ninguno era ilegible: lo que fallaba era mirar solo la primera página y solo un formato."""

    def test_la_proxy_sin_portada_de_texto_se_reconoce_por_la_convocatoria(self):
        """Falla si un documento cuya primera página es una imagen queda «desconocido»: la proxy de Qualcomm son 121
        páginas de gobierno y retribución que no entrarían en el informe por una portada sin capa de texto."""
        primeras = ("January 22, 2026\nDear Fellow Stockholders:\nYou are cordially invited to attend the 2026 Annual "
                    "Meeting of Stockholders.\n\nNOTICE OF ANNUAL MEETING OF STOCKHOLDERS\nTo Be Held On March 17, 2026\n"
                    "TABLE OF CONTENTS\nPROXY STATEMENT OVERVIEW")
        c = clasificar("", "Qualcomm Inc", primeras)
        self.assertIs(c["tipo"], Tipo.DEF14A)
        self.assertEqual(c["fecha"], date(2026, 3, 17))
        self.assertIs(c["certeza"], Certeza.ALTA)

    def test_la_caratula_del_8k_se_reconoce_y_se_fecha(self):
        """Falla si el 8-K que el analista adjunta entero queda «desconocido» con aviso grave: es un depósito de la SEC
        perfectamente identificado, aunque sus cifras vayan en los anexos."""
        p1 = ("UNITED STATES SECURITIES AND EXCHANGE COMMISSION\nWashington, DC 20549\nFORM 8-K\nCURRENT REPORT\n"
              "Pursuant to Section 13 or 15(d) of the Securities Exchange Act of 1934\n"
              "September 3, 2026\nDate of Report (Date of earliest event reported)\nQUALCOMM Incorporated")
        c = clasificar(p1, "0001104659-26-105718", p1)
        self.assertIs(c["tipo"], Tipo.OCHOK)
        self.assertEqual(c["fecha"], date(2026, 9, 3))
        self.assertEqual(c["accession"], "0001104659-26-105718")

    def test_la_transcripcion_de_otro_proveedor_tambien_es_la_call(self):
        """Falla si solo se reconoce la portada de S&P Global: la de LSEG va en versales y dice «EDITED TRANSCRIPT».
        Y falla si se le atribuye un cierre de trimestre: «Q3 2026» ahí es el trimestre natural, y Qualcomm cierra en
        septiembre, así que el cierre saldría tres meses corrido."""
        p1 = ("LSEG STREETEVENTS\nEDITED TRANSCRIPT\nQCOM.OQ - Q3 2026 Qualcomm Inc Earnings Call\n"
              "EVENT DATE/TIME: JULY 29, 2026 / 8:45PM GMT")
        c = clasificar(p1, "Q3 2026 Qualcomm Inc Earnings Call", p1)
        self.assertIs(c["tipo"], Tipo.CALL)
        self.assertEqual(c["fecha"], date(2026, 7, 29))
        self.assertIsNone(c["periodo_fin"])

    def test_la_presentacion_con_descargo_legal_en_la_portada(self):
        """Falla si el descargo legal de la portada tapa el rótulo de la diapositiva, que además viene partido en dos
        líneas. El PDF declara su propio título: esa es la pista que no depende de la maqueta."""
        p1 = "Third Quarter\nFiscal 2026 Earnings\nJuly 29, 2026\n" + "In this presentation we use Qualcomm. " * 12
        self.assertIs(clasificar(p1, "", p1)["tipo"], Tipo.PRESENTACION)
        self.assertIs(clasificar("portada sin rótulo\n" + "texto " * 200, "Quarterly Earnings Presentation",
                                 "texto")["tipo"], Tipo.PRESENTACION)


class LecturaDelDocumento(unittest.TestCase):
    """Lo que el 10-K de Qualcomm (23/09/2026) enseñó del lector: tres reglas escritas mirando un solo emisor."""

    def test_el_espacio_de_la_capa_de_texto_cuenta_aunque_el_hueco_no_llegue(self):
        """Falla si las palabras solo se separan por distancia: en la cursiva en negrita de los epígrafes del Item 1A
        el hueco entre palabras es menor que el criterio, y los 24 riesgos salían impresos como «ofour revenuesfrom»."""
        from tesis.datos.extractor import _tokens_de
        # «of our»: dos palabras pegadas (hueco de 0,05 em) con el espacio en la capa de texto
        juntas = [("o", 0, 0, 5, 10, False), ("f", 5, 0, 10, 10, False), ("o", 10.5, 0, 15, 10, True),
                  ("u", 15, 0, 20, 10, False), ("r", 20, 0, 25, 10, False)]
        self.assertEqual([t.texto for t in _tokens_de(juntas)], ["of our"])
        sin_espacio = [(c, x0, y0, x1, y1, False) for c, x0, y0, x1, y1, _ in juntas]
        self.assertEqual([t.texto for t in _tokens_de(sin_espacio)], ["ofour"])

    def test_el_item_1a_se_reconoce_sin_la_cabecera_que_imprime_edgar(self):
        """Falla si el Item 1A solo se encuentra en las páginas que empiezan por «Table of Contents» —la cabecera del
        HTML de EDGAR, que el PDF maquetado por la compañía no lleva—: el 10-K se quedaba sin un solo riesgo. Y falla
        si se confunde con la línea del índice, donde al epígrafe le sigue el número de página."""
        from tesis.heredado.riesgos import _ITEM_1A
        self.assertTrue(_ITEM_1A.search("…Law Center.\nItem 1A. Risk Factors\nYou should consider each of the following"))
        self.assertFalse(_ITEM_1A.search("Item 1. Business 4\nItem 1A. Risk Factors 14\nItem 1B. Unresolved Staff Comments 34"))

    def test_las_acciones_de_la_portada_en_las_dos_formas_de_declararlas(self):
        """Falla si solo se lee «As of …, there were N shares» en la primera página: Qualcomm las declara en la
        segunda, con otras palabras y en millones, y sin ellas no hay capitalización, ni PER, ni EV, ni un solo
        múltiplo: los cinco salían N/A con la cotización delante."""
        from tesis.datos.ficha import _acciones_portada
        p1 = "UNITED STATES SECURITIES AND EXCHANGE COMMISSION\nFORM 10-Q"
        p2 = ("Indicate by check mark whether the registrant is a shell company. Yes ☐ No ☒\n"
              "The number of shares outstanding of the registrant’s common stock was 1,050 million at July 27, 2026.")
        a = Adjunto(ruta=Path("q.pdf"), huella="h", paginas=[p1, p2], tipo=Tipo.Q10, apartado=APARTADO_DE[Tipo.Q10],
                    certeza=Certeza.ALTA, motivo="")
        c = _acciones_portada(a)
        self.assertEqual(c.valor, 1_050_000_000.0)
        self.assertEqual(c.fecha, date(2026, 7, 27))
        self.assertEqual(c.origen.pagina, 2)
        self.assertIn("millones", c.nota)
        b = Adjunto(ruta=Path("k.pdf"), huella="h", paginas=["As of January 21, 2026, there were 425,171,000 shares of the registrant’s common stock"],
                    tipo=Tipo.K10, apartado=APARTADO_DE[Tipo.K10], certeza=Certeza.ALTA, motivo="")
        self.assertEqual(_acciones_portada(b).valor, 425_171_000.0)
        # y al revés, que es como lo dicen otros: primero la fecha y después la cifra, con dos puntos
        for texto, valor in (("Number of shares of common stock outstanding as of June 12, 2026: 2,880,471,000.", 2_880_471_000.0),
                             ("The number of shares of registrant’s common stock outstanding as of September 7, 2026 was: 3,023,736,000.", 3_023_736_000.0)):
            c = _acciones_portada(Adjunto(ruta=Path("o.pdf"), huella="h", paginas=[texto], tipo=Tipo.K10,
                                          apartado=APARTADO_DE[Tipo.K10], certeza=Certeza.ALTA, motivo=""))
            self.assertEqual(c.valor, valor, texto[:40])

    def test_el_anexo_99_se_reconoce_igual_para_traerlo_que_para_leerlo(self):
        """Regla 9: el mismo 8-K tenía anexo 99 para traerlo al expediente (búsqueda) y no lo tenía para leer la
        previsión de la carta (prefijo), así que el informe decía «el 8-K no lleva Exhibit 99» de un depósito cuyo
        anexo estaba adjuntado. Falla si vuelve a haber dos detectores."""
        from tesis.heredado import cartas
        from tesis.fuentes import edgar, sec
        for nombre in ("ex99-1.htm", "orcl-ex99_1.htm", "qcom062826erex991.htm", "exhibit991.htm"):
            self.assertTrue(sec.es_anexo_99(nombre), nombre)
        for nombre in ("MetaLinks.json", "img1.gif", "qcom-20260729.htm"):
            self.assertFalse(sec.es_anexo_99(nombre), nombre)
        for modulo in (cartas, edgar):
            fuente = Path(modulo.__file__).read_text(encoding="utf-8")
            self.assertIn("es_anexo_99", fuente, modulo.__name__)
            self.assertNotIn('startswith("ex99")', fuente, modulo.__name__)      # el detector por prefijo, el viejo
            self.assertNotIn("re.compile(r\"ex", fuente, modulo.__name__)         # ni ningún otro propio


class ProcedenciaDeLosAnexos(unittest.TestCase):
    def test_el_anexo_99_del_8k_de_resultados_sin_pistas_es_la_nota(self):
        """Falla si un anexo 99 traído de EDGAR del 8-K de resultados se queda en «desconocido» porque su portada no trae
        ninguna pista: EDGAR dice de dónde salió, y eso lo hace la nota con certeza media, dicho en el motivo. Un
        fichero del mismo 8-K que no es un anexo 99 no se toca."""
        from tesis.datos.expediente import _de_edgar

        def adjunto():
            return Adjunto(ruta=Path("SEC_8-K_2026-07-30_ex99-1_0000000000-26-000001.pdf"), huella="x", paginas=["sin pistas"],
                           tipo=Tipo.DESCONOCIDO, apartado=None, certeza=Certeza.BAJA, motivo="Ninguna pista reconocible en la primera página.")
        dato = {"url": "https://www.sec.gov/Archives/edgar/data/1/000000000026000001/a8-kex991q3.htm", "accession": "0000000000-26-000001",
                "formulario": "8-K", "presentado": "2026-07-30", "periodo": ""}
        a, avisos = adjunto(), []
        _de_edgar(a, dato, avisos)
        self.assertIs(a.tipo, Tipo.NOTA)
        self.assertIs(a.certeza, Certeza.MEDIA)
        self.assertIs(a.apartado, APARTADO_DE[Tipo.NOTA])
        self.assertIn("anexo 99", a.motivo)
        b = adjunto()
        _de_edgar(b, dict(dato, url="https://www.sec.gov/Archives/edgar/data/1/000000000026000001/acme-8k.htm"), [])
        self.assertIs(b.tipo, Tipo.DESCONOCIDO)

    def test_un_anexo_del_8k_con_su_numero_de_acceso_consta_como_de_edgar(self):
        """Falla si solo el 10-K, el 10-Q y la proxy pueden constar como verificados en EDGAR: la nota de resultados
        traída de la SEC salía con «—» en la columna de procedencia, como si no se supiera de dónde venía."""
        from datetime import date as _date
        from tesis.datos.expediente import Expediente, _cruzar_con_edgar
        from tesis.fuentes.sec import Deposito
        dep = Deposito(cik="0000804328", formulario="8-K", presentado=_date(2026, 7, 29), periodo=_date(2026, 7, 29),
                       accession="0000804328-26-000085", documento="qcom.htm", epigrafes="2.02,9.01")
        a = Adjunto(ruta=Path("SEC_8-K_2026-07-29_ex99-1_0000804328-26-000085.pdf"), huella="x", paginas=["y"],
                    tipo=Tipo.NOTA, apartado=APARTADO_DE[Tipo.NOTA], certeza=Certeza.ALTA, motivo="",
                    accession="0000804328-26-000085")
        exp = Expediente(ticker="QCOM", adjuntos=[a], avisos=[])
        _cruzar_con_edgar(exp, [dep])
        self.assertTrue(a.verificado_en_edgar)
        self.assertEqual(a.fecha, _date(2026, 7, 29))


if __name__ == "__main__":
    unittest.main()
