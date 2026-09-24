"""El formulario del analista (servidor local) y el redactor automático con su bucle de verificación. Sin red ni modelo."""

import json
import tempfile
import unittest
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path
from unittest import mock

from tests import contacto_sec_de_prueba, hay_cache_sec, rutas_nflx
from tesis import formulario, narrativa, posicion

RUTAS = rutas_nflx()


class Formulario(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.servidor, cls.hilo = formulario.servir("PRUEBA", 0, Path(cls.tmp.name), en_hilo=True)
        cls.base = cls.servidor.direccion.rstrip("/")

    @classmethod
    def tearDownClass(cls):
        cls.servidor.shutdown()
        cls.servidor.server_close()
        cls.tmp.cleanup()

    def _get(self, ruta):
        with urllib.request.urlopen(self.base + ruta, timeout=10) as r:
            return r.status, r.headers, r.read()

    def _post(self, datos, cabeceras=None):
        req = urllib.request.Request(self.base + "/api/posicion", data=json.dumps(datos).encode("utf-8"),
                                     headers=cabeceras if cabeceras is not None else {"Content-Type": "application/json", "X-Formulario": "posicion"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def test_sirve_la_pagina_con_csp_estricta_y_sin_scripts_en_linea(self):
        """Falla si la página lleva scripts o estilos en línea, si la CSP deja de prohibirlos o si un fichero fuera de la carpeta se sirve."""
        estado, cab, cuerpo = self._get("/")
        self.assertEqual(estado, 200)
        html = cuerpo.decode("utf-8")
        self.assertNotIn("<script>", html)
        self.assertNotIn("onclick=", html)
        self.assertNotIn("style=", html)
        self.assertIn("script-src 'self'", cab["Content-Security-Policy"])
        self.assertNotIn("unsafe-inline", cab["Content-Security-Policy"])
        for ruta in ("/formulario.js", "/formulario.css"):
            self.assertEqual(self._get(ruta)[0], 200)
        for fuera in ("/../maqueta/tesis.css", "/..%2Fmaqueta%2Ftesis.css", "/tesis/../maqueta/tesis.css"):
            with self.assertRaises(urllib.error.HTTPError, msg=fuera) as cm:
                self._get(fuera)
            self.assertEqual(cm.exception.code, 404, fuera)
        js = self._get("/formulario.js")[2].decode("utf-8")
        self.assertNotIn("innerHTML", js)

    def test_carga_la_plantilla_y_guarda_solo_lo_valido(self):
        """Falla si sin fichero no devuelve la plantilla, si un cuerpo inválido se guarda, o si el válido no llega al fichero del ticker."""
        estado, _, cuerpo = self._get("/api/posicion")
        d = json.loads(cuerpo)
        self.assertFalse(d["existe"])
        self.assertEqual(d["posicion"], posicion.plantilla())
        malo = posicion.plantilla()
        malo["posicion"]["recomendacion"] = "holdear"
        estado, r = self._post(malo)
        self.assertEqual(estado, 400)
        self.assertIn("posicion.recomendacion", r["errores"])
        self.assertFalse(Path(self.tmp.name, "PRUEBA.json").exists())
        bueno = posicion.plantilla()
        bueno["analista"] = "Sergio"
        bueno["posicion"]["recomendacion"] = "comprar"
        bueno["posicion"]["precio_objetivo"] = 100
        bueno["tesis"]["argumento"] = "Argumento."
        estado, r = self._post(bueno)
        self.assertEqual(estado, 200)
        ruta = Path(self.tmp.name, "PRUEBA.json")
        self.assertTrue(ruta.exists())
        p = posicion.cargar(ruta)
        self.assertEqual((p.analista, p.recomendacion, p.precio_objetivo, p.argumento), ("Sergio", "comprar", 100.0, "Argumento."))
        self.assertIn("34 · checklist de entrada", r["sin_rellenar"])
        estado, _, cuerpo = self._get("/api/posicion")
        self.assertTrue(json.loads(cuerpo)["existe"])

    def test_una_web_ajena_no_puede_escribir(self):
        """Falla si un POST sin la cabecera propia, con otro Content-Type o desde otro origen llega a escribir el fichero (CSRF hacia 127.0.0.1)."""
        bueno = posicion.plantilla()
        bueno["analista"] = "Intruso"
        for cabeceras in ({"Content-Type": "text/plain"}, {"Content-Type": "application/json"},
                          {"Content-Type": "application/json", "X-Formulario": "posicion", "Origin": "https://malicioso.example"}):
            estado, r = self._post(bueno, cabeceras)
            self.assertEqual(estado, 403, cabeceras)
        ruta = Path(self.tmp.name, "PRUEBA.json")
        if ruta.exists():
            self.assertNotEqual(posicion.cargar(ruta).analista, "Intruso")
        estado, _ = self._post(bueno, {"Content-Type": "application/json", "X-Formulario": "posicion", "Origin": self.base})
        self.assertEqual(estado, 200)

    def test_el_ticker_se_valida(self):
        """Falla si un «ticker» con barras o puntos suspensivos llega a formar una ruta."""
        with self.assertRaises(ValueError):
            formulario.ruta_posicion("../x")


@unittest.skipUnless(RUTAS and hay_cache_sec(), "sin expediente de NFLX o sin caché SEC")
class RedactorVerificado(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tesis import contraste, derivados, expediente, sec
        contacto_sec_de_prueba()
        emisor = sec.emisor("NFLX")
        cls.exp = expediente.cargar("NFLX", RUTAS, emisor.depositos)
        facts, obtenido = sec.companyfacts(emisor.cik)
        periodos = contraste.periodos_del_informe(cls.exp)
        tab = contraste.contrastar(cls.exp, facts, obtenido, periodos)
        cls.hechos = derivados.calcular(tab.hechos(), periodos["anuales"] + periodos["trimestres"], periodos["instantes"])
        cls.buena = narrativa.cargar(Path(__file__).resolve().parents[1] / "narrativas" / "NFLX_2026-09-17.json")

    def test_el_redactor_recibe_los_reparos_y_se_queda_con_la_ronda_mejor(self):
        """Falla si la segunda ronda no recibe los reparos de la primera, si el bucle no para al quedar sin reparos,
        o si se devuelve una ronda con más frases retiradas que otra."""
        llamadas = []
        mala = narrativa.de_dict(narrativa.a_dict(self.buena))
        mala.resumen[0][0] = narrativa.Frase(texto="Netflix ganó 999.999 M USD en 2T26.", apoyos=[narrativa.Apoyo("10K_20251231", 4, "texto que no está en la página")], cifras=[])

        def redactor_falso(texto, modelo, reparos=()):
            llamadas.append(list(reparos))
            return mala if len(llamadas) == 1 else self.buena
        n, rondas = narrativa.redactar_verificada(self.exp, self.hechos, redactar=redactor_falso, rondas=3)
        self.assertEqual(rondas, 2)
        self.assertEqual(llamadas[0], [])
        self.assertTrue(any("resumen §1 frase 1" in r for r in llamadas[1]), llamadas[1])
        self.assertEqual(n.resumen[0][0].texto, self.buena.resumen[0][0].texto)

    def test_si_la_segunda_ronda_es_peor_se_queda_con_la_primera(self):
        """Falla si el bucle devuelve la última ronda en vez de la que menos frases retiradas tiene."""
        mala1 = narrativa.de_dict(narrativa.a_dict(self.buena))
        mala1.resumen[0][0] = narrativa.Frase(texto="Frase uno sin apoyo real.", apoyos=[narrativa.Apoyo("10K_20251231", 4, "no está en la página cuatro")], cifras=[])
        mala2 = narrativa.de_dict(narrativa.a_dict(self.buena))
        mala2.resumen[0][0] = narrativa.Frase(texto="Frase uno sin apoyo real.", apoyos=[narrativa.Apoyo("10K_20251231", 4, "no está en la página cuatro")], cifras=[])
        mala2.resumen[0][1] = narrativa.Frase(texto="Frase dos sin apoyo real.", apoyos=[narrativa.Apoyo("10K_20251231", 4, "tampoco está en la página")], cifras=[])
        rondas_dadas = iter([mala1, mala2])
        n, rondas = narrativa.redactar_verificada(self.exp, self.hechos, redactar=lambda t, m, r=(): next(rondas_dadas), rondas=2)
        self.assertEqual(rondas, 2)
        self.assertIs(n, mala1)      # la de una sola retirada, no la última (dos)

    def test_el_dossier_y_el_ejemplo_de_estilo_no_llevan_datos_de_fuera(self):
        """Falla si el ejemplo de estilo deja de ser un extracto (un párrafo y un pilar) o si las instrucciones piden algo que no sea el dossier."""
        ejemplo = narrativa.ejemplo_de_estilo()
        d = json.loads(ejemplo[ejemplo.index("{"):])
        self.assertEqual((len(d["resumen"]), len(d["pilares"])), (1, 1))
        self.assertIn("Solo puedes usar el dossier adjunto", narrativa.INSTRUCCIONES)
        self.assertIn("$defs", narrativa.ESQUEMA_NARRATIVA)
        self.assertEqual(sorted(narrativa.ESQUEMA_NARRATIVA["properties"]["bloques"]["required"]), ["21", "22", "23", "31"])

    def test_sin_clave_el_redactor_lo_dice(self):
        """Falla si sin ANTHROPIC_API_KEY (ni perfil) redactar_con_claude devuelve algo en vez de SinRedactor."""
        import anthropic

        class _SinClave:
            def __init__(self, *a, **k):
                raise anthropic.AnthropicError("no api key")
        with mock.patch.object(anthropic, "Anthropic", _SinClave), mock.patch.object(narrativa, "variable", lambda n: "", create=True):
            with self.assertRaises(narrativa.SinRedactor):
                narrativa.redactar_con_claude("dossier")


if __name__ == "__main__":
    unittest.main()
