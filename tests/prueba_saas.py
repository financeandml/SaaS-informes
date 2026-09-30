"""El SaaS local (tesis.saas): páginas con CSP estricta, buscador de tickers, subida y clasificación de adjuntos, CSRF y rutas. Sin red salvo la caché SEC."""

import io
import json
import tempfile
import unittest
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from unittest import mock

from tests import hay_cache_sec
from tesis.web import saas

RAIZ = Path(__file__).resolve().parents[1]


def _docx(texto: str) -> bytes:
    """Un .docx mínimo con la biblioteca estándar: dos párrafos separados por un salto de página."""
    ns = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
    # El salto va fuera del f-string: Python 3.11 no admite barras invertidas dentro de sus expresiones.
    salto = '<w:r><w:br w:type="page"/></w:r>'
    cuerpo = "".join(f"<w:p>{salto if i else ''}<w:r><w:t>{p}</w:t></w:r></w:p>" for i, p in enumerate(texto.split("|")))
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
        z.writestr("word/document.xml", f'<?xml version="1.0"?><w:document {ns}><w:body>{cuerpo}</w:body></w:document>')
    return b.getvalue()


def _multipart(ficheros):
    limite = "----wc"
    partes = b""
    for nombre, datos in ficheros:
        partes += (f"--{limite}\r\nContent-Disposition: form-data; name=\"fichero\"; filename=\"{nombre}\"\r\nContent-Type: application/octet-stream\r\n\r\n").encode() + datos + b"\r\n"
    return partes + f"--{limite}--\r\n".encode(), f"multipart/form-data; boundary={limite}"


class Saas(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.parches = [mock.patch.object(saas, "ADJUNTOS", Path(cls.tmp.name, "adjuntos")), mock.patch.object(saas, "DCF", Path(cls.tmp.name, "dcf")),
                       mock.patch.object(saas, "SALIDA", Path(cls.tmp.name, "salida"))]
        for p in cls.parches:
            p.start()
        cls.servidor, _ = saas.servir(0, en_hilo=True)
        cls.base = cls.servidor.direccion.rstrip("/")

    @classmethod
    def tearDownClass(cls):
        cls.servidor.shutdown()
        cls.servidor.server_close()
        for p in cls.parches:
            p.stop()
        cls.tmp.cleanup()

    def _pedir(self, ruta, datos=None, cabeceras=None, metodo=None):
        req = urllib.request.Request(self.base + ruta, data=datos, headers=cabeceras or {}, method=metodo or ("POST" if datos is not None else "GET"))
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.status, dict(r.headers), r.read()
        except urllib.error.HTTPError as e:
            return e.code, dict(e.headers), e.read()

    def test_las_cuatro_paginas_salen_con_csp_estricta_y_sin_scripts_en_linea(self):
        """Falla si una página lleva scripts o estilos en línea, si la CSP admite unsafe-inline o si no permite enmarcar el informe."""
        for ruta in ("/", "/dcf", "/asistente", "/informe"):
            estado, cab, cuerpo = self._pedir(ruta)
            self.assertEqual(estado, 200, ruta)
            html = cuerpo.decode("utf-8")
            self.assertNotIn("<script>", html); self.assertNotIn("onclick=", html); self.assertNotIn("style=", html)
            self.assertIn("script-src 'self'", cab["Content-Security-Policy"]); self.assertNotIn("unsafe-inline", cab["Content-Security-Policy"])
            self.assertIn("frame-src 'self'", cab["Content-Security-Policy"])
        js = self._pedir("/saas.js")[2].decode("utf-8")
        self.assertNotIn("innerHTML", js)
        self.assertEqual(self._pedir("/../tesis.html")[0], 404)

    @unittest.skipUnless(hay_cache_sec(), "sin caché SEC")
    def test_el_buscador_de_tickers_pone_primero_el_exacto(self):
        """Falla si «NFLX» no sale primero para «nfl» o si «netflix» no encuentra al emisor por nombre."""
        estado, _, cuerpo = self._pedir("/api/tickers?q=nfl")
        self.assertEqual(estado, 200)
        lista = json.loads(cuerpo)
        self.assertEqual(lista[0]["ticker"], "NFLX")
        self.assertEqual(lista[0]["cik"], "0001065280")
        self.assertIn("NFLX", [x["ticker"] for x in json.loads(self._pedir("/api/tickers?q=netflix")[2])])
        self.assertEqual(json.loads(self._pedir("/api/tickers?q=")[2]), [])
        self.assertEqual([x["ticker"] for x in json.loads(self._pedir("/api/tickers?q=BRK")[2])][:2], ["BRK-A", "BRK-B"])   # prefijo alfabético, no por longitud
        self.assertIn("MSFT", [x["ticker"] for x in json.loads(self._pedir("/api/tickers?q=microsoft")[2])][:1])

    def test_subir_clasificar_ordenar_y_borrar_adjuntos(self):
        """Falla si un Word no se guarda y clasifica (como «desconocido» con el tipo reconocido en el motivo), si un .txt se acepta,
        si el orden no es cronológico, si el estado no lo refleja o si borrar no lo quita."""
        docs = [("carta_q2.docx", _docx("July 16, 2026 Fellow shareholders, Q2'26 revenue grew 17%.|Netflix, Inc.")),
                ("Nota.txt", b"hola"),
                ("informe 10-Q.docx", _docx("UNITED STATES SECURITIES AND EXCHANGE COMMISSION FORM 10-Q For the quarterly period ended March 31, 2026|Netflix, Inc."))]
        cuerpo, tipo = _multipart(docs)
        estado, _, resp = self._pedir("/api/adjuntos?ticker=PRUEBA", cuerpo, {"Content-Type": tipo, "X-Formulario": "saas"})
        self.assertEqual(estado, 200, resp[:200])
        d = json.loads(resp)
        self.assertEqual(sorted(d["guardados"]), ["carta_q2.docx", "informe 10-Q.docx"])
        self.assertEqual(len(d["rechazados"]), 1)
        adj = d["estado"]["adjuntos"]["adjuntos"]
        self.assertEqual(len(adj), 2)
        for a in adj:
            self.assertEqual(a["tipo"], "desconocido")
            self.assertIn("Word reconocido como", a["motivo"])
            self.assertIn("no se usa", a["destino"])
        # cronológico: el 10-Q (cierre 31/03/2026) antes que la carta (16/07/2026), aunque alfabéticamente sea al revés
        self.assertEqual([a["fichero"] for a in adj], ["informe 10-Q.docx", "carta_q2.docx"])
        self.assertEqual([a["orden"] for a in adj], ["2026-03-31", "2026-07-16"])
        estado, _, resp = self._pedir("/api/estado?ticker=PRUEBA")
        e = json.loads(resp)
        self.assertEqual([a["fichero"] for a in e["adjuntos"]["adjuntos"]], [a["fichero"] for a in adj])
        self.assertEqual(e["contraste"]["estado"], "pendiente")           # sin emisor cargado no se contrasta, y se dice
        estado, _, resp = self._pedir("/api/adjuntos/borrar?ticker=PRUEBA", json.dumps({"fichero": "carta_q2.docx"}).encode(),
                                      {"Content-Type": "application/json", "X-Formulario": "saas"})
        self.assertEqual([a["fichero"] for a in json.loads(resp)["estado"]["adjuntos"]["adjuntos"]], ["informe 10-Q.docx"])
        self.assertFalse(Path(saas.ADJUNTOS, "PRUEBA", "carta_q2.docx").exists())

    def test_cada_documento_tiene_su_casilla_y_lo_declarado_queda_escrito(self):
        """Falla si adjuntar en una casilla no deja constancia de en cuál fue, si la casilla admite un formato que ese
        documento no tiene, o si el estado no dice qué documentos faltan todavía: era lo que no se veía por ninguna
        parte cuando el analista adjuntaba cinco PDF de golpe."""
        cuerpo, tipo = _multipart([("nota_q1.pdf", b"%PDF-1.4 no es una hoja de calculo")])
        cabeceras = {"Content-Type": tipo, "X-Formulario": "saas"}
        estado, _, resp = self._pedir("/api/adjuntos?ticker=CASILLA&documento=XLSX", cuerpo, cabeceras)
        d = json.loads(resp)
        self.assertEqual(d["guardados"], [])
        self.assertIn("Hoja de c", d["rechazados"][0])                       # el rechazo nombra la casilla, no «formato no admitido»
        self.assertEqual(self._pedir("/api/adjuntos?ticker=CASILLA&documento=INVENTADO", cuerpo, cabeceras)[0], 400)

        cuerpo, tipo = _multipart([("informe 10-K.docx", _docx("UNITED STATES SECURITIES AND EXCHANGE COMMISSION FORM 10-K For the fiscal year ended May 31, 2026|Oracle"))])
        estado, _, resp = self._pedir("/api/adjuntos?ticker=CASILLA&documento=10K", cuerpo, {"Content-Type": tipo, "X-Formulario": "saas"})
        d = json.loads(resp)
        self.assertEqual(d["guardados"], ["informe 10-K.docx"])
        self.assertEqual(json.loads(Path(saas.ADJUNTOS, "CASILLA", "declarado.json").read_text(encoding="utf-8")), {"informe 10-K.docx": "10K"})
        e = d["estado"]
        self.assertEqual(len(e["documentos"]), len(saas.catalogo.CATALOGO))
        self.assertEqual([x["fichero"] for x in e["adjuntos"]["adjuntos"]][0], "informe 10-K.docx")
        self.assertEqual([x["declarado"] for x in e["adjuntos"]["adjuntos"]], ["10K"])
        self.assertIn("10K", e["faltan_imprescindibles"])                    # un Word no son las cuentas: sigue faltando el 10-K
        estado, _, resp = self._pedir("/api/emitir?ticker=CASILLA", b"{}", {"Content-Type": "application/json", "X-Formulario": "saas"})
        self.assertEqual(estado, 400)
        self.assertIn("Informe anual", json.loads(resp)["error"])            # no se emite sin 10-K, y se dice cuál falta

    def test_una_web_ajena_no_puede_escribir_ni_leer_fuera_de_salida(self):
        """Falla si un POST sin la cabecera propia o desde otro origen escribe, si un ticker con barras pasa, o si /informes sale de salida/<TICKER>."""
        cuerpo, tipo = _multipart([("x.pdf", b"%PDF-1.4")])
        self.assertEqual(self._pedir("/api/adjuntos?ticker=PRUEBA", cuerpo, {"Content-Type": tipo})[0], 403)
        self.assertEqual(self._pedir("/api/adjuntos?ticker=PRUEBA", cuerpo, {"Content-Type": tipo, "X-Formulario": "saas", "Origin": "https://malicioso.example"})[0], 403)
        self.assertEqual(self._pedir("/api/emitir?ticker=PRUEBA", b"{}", {"Content-Type": "application/json"})[0], 403)
        self.assertEqual(self._pedir("/api/estado?ticker=../x")[0], 400)
        Path(saas.SALIDA, "PRUEBA").mkdir(parents=True, exist_ok=True)
        Path(saas.SALIDA, "PRUEBA", "PRUEBA_tesis_2026-01-01.html").write_text("<html></html>", encoding="utf-8")
        Path(saas.SALIDA, "secreto.txt").write_text("no", encoding="utf-8")
        self.assertEqual(self._pedir("/informes/PRUEBA/PRUEBA_tesis_2026-01-01.html")[0], 200)
        self.assertEqual(self._pedir("/informes/PRUEBA/../secreto.txt")[0], 404)
        self.assertEqual(self._pedir("/informes/PRUEBA/%2e%2e/secreto.txt")[0], 404)
        self.assertEqual(self._pedir("/informes/PRUEBA/otro/../../secreto.txt")[0], 404)

    def test_un_rechazo_llega_como_403_aunque_el_cuerpo_sea_grande(self):
        """Falla si al rechazar un POST no se lee su cuerpo: responder y cerrar con datos sin leer en el socket corta la
        conexión, y el cliente ve un error de red en vez del 403 con su motivo (salía como prueba intermitente)."""
        cuerpo, tipo = _multipart([("grande.pdf", b"%PDF-1.4" + b"0" * 2_000_000)])
        estado, _, resp = self._pedir("/api/adjuntos?ticker=PRUEBA", cuerpo, {"Content-Type": tipo})
        self.assertEqual(estado, 403)
        self.assertIn("propia página", json.loads(resp)["error"])
        self.assertFalse(Path(saas.ADJUNTOS, "PRUEBA", "grande.pdf").exists())

    def test_emitir_sin_adjuntos_se_rechaza_y_nada_escribe_en_posiciones(self):
        """Falla si se lanza una emisión sin expediente, o si vuelve el formulario antiguo que escribía en `posiciones/`
        (regla 15: `posiciones/` solo se lee, para migrarla al asistente)."""
        estado, _, resp = self._pedir("/api/emitir?ticker=VACIO", b"{}", {"Content-Type": "application/json", "X-Formulario": "saas"})
        self.assertEqual(estado, 400)
        self.assertIn("sin adjuntos", json.loads(resp)["error"])
        self.assertEqual(self._pedir("/formulario?ticker=PRUEBA")[0], 404)
        self.assertEqual(self._pedir("/api/posicion?ticker=PRUEBA")[0], 404)
        estado, _, _ = self._pedir("/api/posicion?ticker=PRUEBA", b"{}", {"Content-Type": "application/json", "X-Formulario": "posicion"})
        self.assertIn(estado, (403, 404))


if __name__ == "__main__":
    unittest.main()
