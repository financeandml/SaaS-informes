"""La lista de documentos necesarios del paso 1 y lo que se declara al adjuntar. Sin red.

El caso que las trajo (22/09/2026, Oracle): el analista adjuntaba todo en un montón y no había forma de ver qué le
faltaba —ni la proxy ni la transcripción de la call estaban, y el informe salía con 4–6 y 33 en N/A sin que nadie lo
hubiera avisado antes de emitir—. Ahora cada documento tiene su casilla, su botón y su consecuencia escrita.
"""

import json
import re
import tempfile
import unittest
from pathlib import Path

from tesis import documentos, expediente, revision, secciones
from tesis.expediente import Adjunto, Aviso, Tipo
from tesis.hechos import Certeza


def _adj(tipo=Tipo.DESCONOCIDO, nombre="x.pdf", motivo="Ninguna pista reconocible en la primera página."):
    return Adjunto(ruta=Path(nombre), huella="h", paginas=["texto"], tipo=tipo,
                   apartado=expediente.APARTADO_DE.get(tipo), certeza=Certeza.BAJA, motivo=motivo)


class Catalogo(unittest.TestCase):
    def test_cada_documento_dice_donde_va_y_que_se_pierde_sin_el(self):
        """Falla si una casilla no declara su destino en el informe o su consecuencia: la lista existe para que el
        analista sepa, antes de emitir, qué apartado se quedará en N/A."""
        for d in documentos.CATALOGO:
            for campo in ("titulo", "aporta", "sin_el", "donde"):
                self.assertTrue(getattr(d, campo).strip(), f"{d.clave}.{campo}")
            self.assertIn(d.exigencia, (documentos.IMPRESCINDIBLE, documentos.RECOMENDADO, documentos.OPCIONAL), d.clave)
            self.assertTrue(all(f.startswith(".") for f in d.formatos), d.clave)

    def test_los_apartados_que_cita_son_los_del_indice(self):
        """Falla si la lista del paso 1 cita un apartado por un número que ya no es el suyo (el catálogo decía «25 tamaño
        de mercado» y «32 guía frente a real» con la numeración antigua: el analista buscaba donde no era)."""
        import yaml
        titulos = {n: a["titulo"] for n, a in yaml.safe_load((Path(__file__).resolve().parents[1] / "docs" / "spec" / "01_indice.yaml")
                                                              .read_text(encoding="utf-8"))["apartados"].items()}
        clave = {"segmentos": "Productos", "geografía": "Productos", "riesgos": "Riesgos", "tamaño de mercado": "Tamaño de mercado",
                 "frente a real": "Historial de resultados", "objetivos vigentes": "Resumen ejecutivo", "gobierno": "Estructura corporativa"}
        for d in documentos.CATALOGO:
            for n, que in re.findall(r"(\d+)(?:–\d+)? ([a-záéíóúñ ]+?)(?= ·|;|:|$| \(|,)", d.aporta):
                for palabra, titulo in clave.items():
                    if palabra in que:
                        self.assertIn(titulo, titulos[int(n)], f"{d.clave}: «{n} {que}»")

    def test_la_clave_de_la_casilla_es_la_del_expediente(self):
        """Falla si el catálogo nombra un documento de otra manera que el expediente: la lista del paso 1 no casaría
        con lo adjuntado y todo saldría como «falta» teniéndolo delante."""
        for d in documentos.CATALOGO:
            self.assertEqual(expediente.CLAVE_DE[d.tipo], d.clave, d.clave)
            self.assertIs(expediente.TIPO_DE_CLAVE[d.clave], d.tipo, d.clave)

    def test_el_destino_del_informe_sale_solo_del_catalogo(self):
        """Falla si un tipo del expediente se queda sin destino (regla 9: una sola fuente para «dónde va esto»)."""
        self.assertNotEqual(documentos.destino(Tipo.K10), documentos.SIN_DESTINO)
        self.assertEqual(documentos.destino(Tipo.DESCONOCIDO), documentos.SIN_DESTINO)
        self.assertEqual(documentos.destino("10-K"), documentos.destino(Tipo.K10))

    def test_falta_un_10q_avisa_pero_no_cierra_la_puerta_y_falta_el_10k_si(self):
        """Falla si un 10-Q ausente impide emitir (sería una puerta cerrada donde basta un aviso) o si un 10-K ausente
        no la cierra: sin ejercicio base el contraste no puede correr."""
        solo_anual = [{"fichero": "10k.pdf", "tipo": Tipo.K10.value}]
        self.assertEqual([d.clave for d in documentos.faltan(solo_anual)], ["10Q"])
        self.assertEqual(documentos.faltan(solo_anual, solo_bloqueantes=True), [])
        self.assertEqual([d.clave for d in documentos.faltan([], solo_bloqueantes=True)], ["10K"])

    def test_el_estado_reparte_cada_fichero_en_su_casilla_y_deja_fuera_lo_que_no_encaja(self):
        filas = [{"fichero": "10k.pdf", "tipo": Tipo.K10.value}, {"fichero": "raro.pdf", "tipo": Tipo.DESCONOCIDO.value}]
        est = {e["clave"]: e for e in documentos.estado(filas)}
        self.assertEqual(est["10K"]["estado"], "adjuntado")
        self.assertEqual([f["fichero"] for f in est["10K"]["ficheros"]], ["10k.pdf"])
        self.assertEqual(est["PROXY"]["estado"], "falta")
        self.assertEqual([f["fichero"] for f in documentos.sueltos(filas)], ["raro.pdf"])


class Declaracion(unittest.TestCase):
    """La casilla en la que el analista lo adjunta es una declaración suya, no una lectura del documento (regla 3)."""

    def test_un_pdf_sin_pistas_se_toma_por_lo_declarado_diciendolo(self):
        """Falla si un PDF que no dice lo que es se queda en «desconocido» aunque el analista lo haya puesto en su
        casilla: era el caso de las transcripciones de la call maquetadas por terceros."""
        a, avisos = _adj(), []
        expediente._declarado(a, "CALL", avisos)
        self.assertIs(a.tipo, Tipo.CALL)
        self.assertIs(a.certeza, Certeza.MEDIA)
        self.assertIn("declara", a.motivo.lower())
        self.assertEqual([av.gravedad for av in avisos], ["aviso"])

    def test_si_el_documento_dice_otra_cosa_manda_el_documento(self):
        """Falla si la casilla pisa lo que el documento declara de sí mismo: un 10-K adjuntado por error en la casilla
        de la proxy seguiría siendo un 10-K, y quien lo tiene que saber es el analista."""
        a, avisos = _adj(tipo=Tipo.K10, motivo="La portada dice «FORM 10-K»."), []
        expediente._declarado(a, "PROXY", avisos)
        self.assertIs(a.tipo, Tipo.K10)
        self.assertEqual([av.gravedad for av in avisos], ["grave"])
        self.assertIn("10-K", avisos[0].texto)

    def test_un_word_no_se_convierte_en_cuentas_por_declararlo(self):
        """Falla si declarar un .docx lo asciende a documento de cifras: sin coordenadas no hay evidencia ni recorte."""
        a, avisos = _adj(nombre="cuentas.docx"), []
        expediente._declarado(a, "10K", avisos)
        self.assertIs(a.tipo, Tipo.DESCONOCIDO)

    def test_la_declaracion_sobrevive_al_reinicio(self):
        """Falla si lo declarado no queda escrito junto a los adjuntos: al reiniciar el servidor, la lista de
        documentos volvería a decir que falta todo."""
        from tesis import saas
        with tempfile.TemporaryDirectory() as tmp:
            antes = saas.ADJUNTOS
            try:
                saas.ADJUNTOS = Path(tmp)
                saas.declarar("ZZZ", "informe.pdf", "10K")
                self.assertEqual(expediente.declaraciones(Path(tmp) / "ZZZ"), {"informe.pdf": "10K"})
                saas.declarar("ZZZ", "informe.pdf", "")
                self.assertEqual(expediente.declaraciones(Path(tmp) / "ZZZ"), {})
                (Path(tmp) / "ZZZ" / "declarado.json").write_text("{roto", encoding="utf-8")
                self.assertEqual(expediente.declaraciones(Path(tmp) / "ZZZ"), {})   # ilegible: como si no hubiera
            finally:
                saas.ADJUNTOS = antes


class CifraDelLibro(unittest.TestCase):
    """Regla 9: lo que se imprime de una celda del libro y lo que la doble comprobación relee de esa misma celda."""

    def test_un_porcentaje_del_libro_se_imprime_como_porcentaje(self):
        """Falla si el cuadro del precio objetivo imprime «0,00» donde el libro guarda un 0 con formato de porcentaje:
        la doble comprobación lee «0,00 %», no coinciden y la emisión se detiene sin haber nada malo en el libro.
        Le pasó al informe de Oracle con «Suma de los pesos», «Upside» y «Margen de seguridad» (22/09/2026)."""
        class _C:
            def __init__(self, formato):
                self.formato, self.cita, self.formula = formato, "01 Summary!D79", ""
        # el cuadro del precio objetivo se relee siempre en USD por acción (`revision.columna_cita`: «objetivo» → usd)
        for formato, valor, rotulo in (("0.00%", 0.0, "Suma de los pesos"), ("0.0%", 0.2543, "Upside / (Downside) al precio objetivo"),
                                       ("#,##0.00", 150.0, "Precio objetivo calculado"), ("General", 0.0, "Sum-of-the-Parts")):
            impreso = secciones._fmt(valor, "usd", _C(formato))
            releido = revision._texto_libro(valor, "usd", formato)
            self.assertEqual(impreso, releido, f"{rotulo} ({formato})")

    def test_el_cuadro_del_precio_objetivo_imprime_cada_fila_con_el_formato_de_su_celda(self):
        """Falla si el cuadro imprime las filas del bloque «precio objetivo» como importes: un peso y un upside que el
        libro guarda en porcentaje salen «0,00» y «0,25», la relectura dice «0,00 %» y «25,4 %», y la emisión se
        detiene. Y falla si el recorrido sobre la cotizacion se calcula sobre un porcentaje, que no es un precio."""
        from tesis.dcf import Celda as CeldaLibro, Modelo
        from tesis.informe import Cuadros
        m = Modelo(fichero=Path("libro.xlsx"), huella="h", hojas=["01 Summary"], anclajes_objetivo=[
            ("Suma de los pesos", 0.0, CeldaLibro("01 Summary", "D79", None, "0.00%")),
            ("Upside / (Downside) al precio objetivo", 0.2543, CeldaLibro("01 Summary", "C82", None, "0.0%")),
            ("Precio objetivo calculado", 187.5, CeldaLibro("01 Summary", "C80", None, "#,##0.00")),
            ("Sum-of-the-Parts", 0.0, CeldaLibro("01 Summary", "C78", None, "General")),
        ])
        cuadro = secciones.cuadros_dcf(Cuadros(), m, [])["objetivo"]
        impresas = {f.rotulo: f.celdas[0].texto for f in cuadro.filas}
        self.assertEqual(impresas["Suma de los pesos"], revision._texto_libro(0.0, "usd", "0.00%"))
        self.assertEqual(impresas["Upside / (Downside) al precio objetivo"], revision._texto_libro(0.2543, "usd", "0.0%"))
        self.assertEqual(impresas["Precio objetivo calculado"], revision._texto_libro(187.5, "usd", "#,##0.00"))
        self.assertEqual(impresas["Sum-of-the-Parts"], revision._texto_libro(0.0, "usd", "General"))
        recorridos = {f.rotulo: f.celdas[3].texto for f in cuadro.filas}
        self.assertEqual(recorridos["Suma de los pesos"], "")           # un porcentaje no se divide entre la cotización
        self.assertNotEqual(recorridos["Precio objetivo calculado"], "")

    def test_las_dos_lecturas_usan_la_misma_regla_de_unidad(self):
        """Falla si las reglas de unidad de la sección D y de la relectura se separan: cada cifra se imprimiría bien
        por su lado y la emisión se detendría sin motivo."""
        for rotulo in ("Suma de los pesos", "Precio objetivo calculado", "Margen de seguridad sobre el precio objetivo",
                       "Valor de la empresa", "Crecimiento terminal", "Factor de descuento"):
            self.assertEqual(secciones._unidad_fila(rotulo), revision._unidad_fila(rotulo), rotulo)


if __name__ == "__main__":
    unittest.main()
