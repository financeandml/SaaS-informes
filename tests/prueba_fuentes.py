"""Traer de EDGAR lo que el analista no ha adjuntado. Sin red: la descarga y la impresión se sustituyen.

El caso que las trajo (23/09/2026): faltaban la proxy y la transcripción de la call del expediente de Oracle, y el
informe salía con el gobierno y el apartado 33 en N/A. La proxy está depositada —se puede traer— y la transcripción
no, porque es de un tercero. La diferencia entre «no lo tienes» y «no existe de dónde traerlo» tiene que verse.
"""

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from tesis import documentos, fuentes
from tesis.sec import Deposito

CIK = "0001341439"


def _dep(formulario, presentado, periodo=None, documento="d.htm", accession="0001193125-26-000001", epigrafes=""):
    return Deposito(cik=CIK, formulario=formulario, presentado=date.fromisoformat(presentado),
                    periodo=date.fromisoformat(periodo) if periodo else None, accession=accession,
                    documento=documento, epigrafes=epigrafes)


class _Emisor:
    def __init__(self, depositos):
        self.cik, self.depositos = CIK, depositos


class _Papel:
    """Descarga e impresión de mentira: apuntan lo que se les pide y escriben un PDF de juguete."""

    def __init__(self):
        self.descargas, self.impresiones = [], []

    def descargar(self, url, refrescar=False):
        self.descargas.append(url)
        return "<html><head><title>lo que sea</title></head><body>FORM 10-K</body></html>", date(2026, 9, 23)

    def imprimir(self, html, pdf, html_guardado=None, **kw):
        self.impresiones.append((html, Path(pdf)))
        Path(pdf).write_bytes(b"%PDF-1.4 de prueba")
        if html_guardado:
            Path(html_guardado).parent.mkdir(parents=True, exist_ok=True)
            Path(html_guardado).write_text(html, encoding="utf-8")
        return "huella"


class Catalogo(unittest.TestCase):
    def test_cada_documento_dice_si_se_puede_traer_o_por_que_no(self):
        """Falla si un documento de la lista no declara su fuente oficial ni el motivo de no tenerla: el analista se
        quedaría sin saber si es que no lo ha buscado o es que no existe."""
        for d in documentos.CATALOGO:
            self.assertIn(d.clave, fuentes.FUENTES, d.clave)
            f = fuentes.FUENTES[d.clave]
            self.assertTrue(f.formulario or f.del_8k or f.sin_fuente, d.clave)
            if f.sin_fuente:
                self.assertFalse(fuentes.hay_fuente(d.clave), d.clave)
                self.assertGreater(len(f.sin_fuente), 40, d.clave)     # un motivo, no una etiqueta

    def test_la_transcripcion_no_se_trae_y_se_dice_por_que(self):
        p = _Papel()
        with tempfile.TemporaryDirectory() as tmp:
            salida = fuentes.traer(_Emisor([]), ["CALL"], Path(tmp), descargar=p.descargar, imprimir=p.imprimir)
        self.assertEqual([t.estado for t in salida], ["sin fuente"])
        self.assertIn("tercero", salida[0].motivo)
        self.assertEqual(p.descargas, [])


class DeEdgar(unittest.TestCase):
    def test_se_trae_el_mas_reciente_con_su_nombre_y_su_procedencia(self):
        """Falla si no se trae el depósito más reciente, si el fichero no lleva formulario, periodo y número de acceso
        en el nombre, o si no queda escrito de qué depósito salió (sin eso, el expediente tendría que adivinarlo)."""
        viejo = _dep("DEF 14A", "2024-09-20", "2024-11-13", accession="0001193125-24-000001")
        nuevo = _dep("DEF 14A", "2025-09-26", "2025-11-18", accession="0001193125-25-220801")
        p = _Papel()
        with tempfile.TemporaryDirectory() as tmp:
            salida = fuentes.traer(_Emisor([viejo, nuevo]), ["PROXY"], Path(tmp), descargar=p.descargar, imprimir=p.imprimir)
            self.assertEqual([t.estado for t in salida], ["traído"])
            t = salida[0]
            self.assertEqual(t.fichero, "SEC_DEF-14A_2025-11-18_0001193125-25-220801.pdf")
            self.assertTrue((Path(tmp) / t.fichero).is_file())
            origen = json.loads((Path(tmp) / "origen.json").read_text(encoding="utf-8"))
            self.assertEqual(origen[t.fichero]["accession"], "0001193125-25-220801")
            self.assertEqual(origen[t.fichero]["formulario"], "DEF 14A")
            self.assertEqual(origen[t.fichero]["periodo"], "2025-11-18")
        self.assertEqual(len(p.descargas), 1)
        self.assertIn("000119312525220801/d.htm", p.descargas[0])      # la carpeta del depósito, el documento principal

    def test_el_html_se_imprime_sin_salir_a_la_red_y_declarando_su_deposito(self):
        """Falla si el documento que se imprime puede pedir imágenes a la SEC por su cuenta (sin identificarnos) o si
        no lleva el número de acceso como título: es lo que casa el PDF con su depósito."""
        html = fuentes._para_imprimir("<html><head><title>Oracle</title></head><body>x</body></html>", "0001-25-1")
        self.assertIn("Content-Security-Policy", html)
        self.assertIn("default-src 'none'", html)
        self.assertIn("<title>0001-25-1</title>", html)
        self.assertNotIn("<title>Oracle</title>", html)

    def test_lo_que_ya_esta_adjuntado_no_se_pide_a_la_sec(self):
        p = _Papel()
        with tempfile.TemporaryDirectory() as tmp:
            salida = fuentes.traer(_Emisor([_dep("10-K", "2026-06-22", "2026-05-31")]), ["10K"], Path(tmp),
                                   ya_estan=["10K"], descargar=p.descargar, imprimir=p.imprimir)
        self.assertEqual([t.estado for t in salida], ["ya estaba"])
        self.assertEqual(p.descargas, [])

    def test_si_edgar_no_tiene_ese_formulario_se_dice(self):
        p = _Papel()
        with tempfile.TemporaryDirectory() as tmp:
            salida = fuentes.traer(_Emisor([_dep("10-K", "2026-06-22")]), ["PROXY"], Path(tmp),
                                   descargar=p.descargar, imprimir=p.imprimir)
        self.assertEqual([t.estado for t in salida], ["no publicado"])
        self.assertIn("DEF 14A", salida[0].motivo)

    def test_un_solo_8k_sirve_para_la_nota_las_tablas_la_carta_y_la_presentacion(self):
        """Falla si se pide el mismo 8-K una vez por casilla: son cuatro peticiones a la SEC para el mismo documento,
        y qué es cada anexo lo decide su portada, no la casilla."""
        ocho = _dep("8-K", "2026-09-10", documento="orcl-20260910.htm", accession="0001193125-26-387905", epigrafes="2.02,9.01")
        indice = lambda url, refrescar=False: ({"directory": {"item": [{"name": "orcl-ex99_1.htm"}, {"name": "orcl-ex99_2.htm"},
                                                                       {"name": "MetaLinks.json"}, {"name": "img1.gif"}]}}, date(2026, 9, 23))
        p = _Papel()
        with tempfile.TemporaryDirectory() as tmp:
            salida = fuentes.traer(_Emisor([ocho]), ["NOTA", "TABLAS", "CARTA"], Path(tmp),
                                   descargar=p.descargar, imprimir=p.imprimir, indice=indice)
        self.assertEqual([t.estado for t in salida], ["traído", "traído"])         # los dos anexos, una sola vez
        self.assertEqual(len(p.descargas), 2)
        self.assertTrue(all(d.endswith(".htm") and "ex99" in d for d in p.descargas), p.descargas)
        self.assertIn("portada", salida[0].motivo)

    def test_un_8k_sin_anexos_99_se_dice(self):
        ocho = _dep("8-K", "2026-09-10", epigrafes="2.02")
        indice = lambda url, refrescar=False: ({"directory": {"item": [{"name": "orcl-20260910.htm"}]}}, date(2026, 9, 23))
        p = _Papel()
        with tempfile.TemporaryDirectory() as tmp:
            salida = fuentes.traer(_Emisor([ocho]), ["NOTA"], Path(tmp), descargar=p.descargar, imprimir=p.imprimir, indice=indice)
        self.assertEqual([t.estado for t in salida], ["no publicado"])
        self.assertEqual(p.descargas, [])


if __name__ == "__main__":
    unittest.main()
