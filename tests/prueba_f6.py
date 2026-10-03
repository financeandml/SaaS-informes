"""Fase 6 (parte G, portada y asistente): regresiones R13, R14, R21 y R30, el asistente web de 9 pasos generado desde
04_entradas.yaml y la migración de `posiciones/`. Sin red: Nasdaq y EDGAR congelados en `tests/fixtures/`."""

import json
import os
import shutil
import tempfile
import unittest
import urllib.request
from datetime import date
from pathlib import Path

import pytest

from tesis.entradas import asistente
from tesis.fuentes import precio as precio_mod, sec
from tesis.entradas import Entradas, comprobar_paso8
from tests.prueba_f3 import _Informes

F = Path(__file__).resolve().parent / "fixtures"
RAIZ = F.parent.parent
HOY = date(2026, 9, 23)
JUSTIFICACION = ("La posición ya está abierta y se mantiene hasta los resultados del cuarto trimestre, cuando se revisarán la guía, "
                 "la diversificación y el margen de la división de semiconductores.")


class _Datos(unittest.TestCase):
    """WC_DATOS en una carpeta temporal y la bolsa en caché: el asistente escribe ahí y lee la sesión de Nasdaq congelada."""

    @classmethod
    def setUpClass(cls):
        cls._env, cls._bolsa, cls._cache = dict(os.environ), (precio_mod.CACHE_BOLSA, precio_mod.SOLO_CACHE), sec.CACHE
        cls.tmp = tempfile.mkdtemp()
        os.environ["WC_DATOS"], os.environ["WC_SEC_CONTACTO"] = cls.tmp, ""
        precio_mod.CACHE_BOLSA, precio_mod.SOLO_CACHE = F / "cache_bolsa", True
        sec.CACHE = F / "cache_sec"

    @classmethod
    def tearDownClass(cls):
        precio_mod.CACHE_BOLSA, precio_mod.SOLO_CACHE = cls._bolsa
        sec.CACHE = cls._cache
        os.environ.clear()
        os.environ.update(cls._env)
        shutil.rmtree(cls.tmp, ignore_errors=True)


class Posicion(_Datos):

    @pytest.mark.regresion("R13")
    def test_entrada_fuera_de_la_sesion_se_rechaza(self):
        """R13. QCOM a 130 USD el 22/09/2026 → rechazada con el rango de la sesión de Nasdaq (191,66–199,15)."""
        datos, notas = asistente.cargar("QCOM", HOY)                # migrado de posiciones/QCOM.json: 130 USD el 22/09
        self.assertEqual((datos["pos"]["precio_entrada"], datos["pos"]["fecha_entrada"]), (130.0, "2026-09-22"))
        datos["meta"]["fecha_valoracion"] = "2026-09-22"
        faltas, avisos = asistente.validar("QCOM", HOY, datos)
        self.assertIn("pos.precio_entrada: 130,00 USD fuera del rango de la sesión del 22/09/2026 (191,66–199,15)", faltas[8])
        datos["pos"]["precio_entrada"] = 195.0
        faltas, avisos = asistente.validar("QCOM", HOY, datos)
        self.assertFalse(any(f.startswith("pos.precio_entrada") for f in faltas[8]))
        self.assertIn("pos.fecha_entrada: posición ya abierta; la lista de comprobación se evalúa a posteriori", avisos)
        datos["pos"]["fecha_entrada"] = "2026-10-15"
        self.assertTrue(any("orden límite" in a for a in asistente.validar("QCOM", HOY, datos)[1]))

    @pytest.mark.regresion("R14")
    def test_comprar_contra_la_regla_exige_justificacion(self):
        """R14. «Comprar» con potencial < 15 % o recorrido/riesgo < 1,5 (la regla dice otra cosa) → justificación ≥ 20 palabras."""
        rango = lambda d: (190.0, 200.0)                                     # noqa: E731
        e = Entradas({"pos": {"recomendacion": "Comprar", "precio_entrada": 195.0, "fecha_entrada": "2026-09-22"}})
        for potencial, rr in ((0.10, 2.0), (0.30, 1.2)):
            faltas, _ = comprobar_paso8(e, HOY, rango, "Mantener", potencial, rr)
            self.assertTrue(any(f.startswith("pos.recomendacion: «Comprar» difiere de la regla («Mantener»") for f in faltas), (potencial, rr))
        e.datos["pos"]["recomendacion_justificacion"] = {"texto": JUSTIFICACION}
        faltas, _ = comprobar_paso8(e, HOY, rango, "Mantener", 0.10, 2.0)
        self.assertFalse(any(f.startswith("pos.recomendacion") for f in faltas))
        e.datos["pos"]["recomendacion"] = "Mantener"                         # la misma que la regla: no se pide nada
        del e.datos["pos"]["recomendacion_justificacion"]
        self.assertFalse(any(f.startswith("pos.recomendacion") for f in comprobar_paso8(e, HOY, rango, "Mantener", 0.10, 2.0)[0]))

    def test_el_tipo_marginal_de_referencia_es_el_del_mercado_del_emisor(self):
        """Falla si el asistente pide justificar el 25 % de un emisor español (el general del Impuesto sobre Sociedades) como
        si la referencia fuera el 21 % federal de EE. UU.: la validación tiene que leer los supuestos con el mercado del emisor."""
        datos = {"wacc": {"tipo_marginal": 25}, "esc": {"base": {"probabilidad": 100}}}
        pide = lambda t: any(f.startswith("wacc.tipo_marginal") for f in asistente.validar(t, HOY, datos)[0][7])   # noqa: E731
        self.assertFalse(pide("RDG.MC"))
        self.assertTrue(pide("QCOM"))

    def test_tamano_frente_al_drawdown(self):
        e = Entradas({"pos": {"tamano_pct": 3, "drawdown_tolerado": 50}})
        faltas = " | ".join(comprobar_paso8(e, HOY, lambda d: None)[0])
        self.assertIn("pos.tamano_pct: 3,0 % × drawdown 50 % = 1,50 % de la cartera, por encima del riesgo máximo por posición (1 %)", faltas)

    def test_migracion_sin_tocar_posiciones(self):
        vieja = RAIZ / "posiciones" / "QCOM.json"
        antes = (vieja.read_bytes(), vieja.stat().st_mtime)
        datos, notas = asistente.cargar("QCOM", HOY)
        self.assertEqual((vieja.read_bytes(), vieja.stat().st_mtime), antes)
        self.assertEqual((datos["pos"]["recomendacion"], datos["pos"]["tamano_pct"]), ("Comprar", 3.0))
        self.assertTrue(any("no se migra: el del informe es el del motor" in x for x in notas))
        self.assertTrue(any("se fija una sola vez en la valoración" in x for x in notas))
        self.assertEqual([c["id"] for c in datos["pos"]["checklist"]], ["variante"])      # el criterio manual, para que lo conteste

    def test_horizonte_y_tamano_se_piden_una_vez(self):
        """R21 (parte). En el esquema del asistente, un solo horizonte (el de la valoración) y un solo tamaño (el de la posición)."""
        ids = [c["id"] for p in asistente.esquema() for c in p["campos"]]
        self.assertEqual([i for i in ids if "horizonte" in i], ["val.horizonte_meses"])
        self.assertEqual([i for i in ids if "tamano" in i], ["pos.tamano_pct", "pos.tamano_porque"])
        self.assertEqual(len(asistente.esquema()), 9)


class Servidor(_Datos):
    """El asistente en http://127.0.0.1: esquema y entradas por GET; guardado versionado y validado por POST."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from tesis.web import saas
        cls.srv, _ = saas.servir(8793, en_hilo=True)
        cls.base = "http://127.0.0.1:8793"

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
        super().tearDownClass()

    def _post(self, datos, cabecera="saas"):
        r = urllib.request.Request(f"{self.base}/api/asistente?ticker=QCOM&fecha=2026-09-23", method="POST",
                                   data=json.dumps({"entradas": datos}).encode(), headers={"Content-Type": "application/json", "X-Formulario": cabecera})
        try:
            with urllib.request.urlopen(r) as resp:
                return resp.status, json.loads(resp.read())
        except urllib.error.HTTPError as ex:
            return ex.code, json.loads(ex.read())

    def test_guardar_validar_y_versionar(self):
        with urllib.request.urlopen(f"{self.base}/api/asistente?ticker=QCOM&fecha=2026-09-23") as r:
            d = json.loads(r.read())
        self.assertEqual([p["numero"] for p in d["esquema"]], list(range(1, 10)))
        datos = d["entradas"]
        datos["meta"]["fecha_valoracion"] = "2026-09-22"
        codigo, res = self._post(datos)
        self.assertEqual(codigo, 200)
        self.assertIn("pos.precio_entrada: 130,00 USD fuera del rango de la sesión del 22/09/2026 (191,66–199,15)", res["faltas"]["8"])
        datos["pos"]["precio_entrada"] = 195.0
        codigo, res = self._post(datos)
        carpeta = Path(self.tmp) / "entradas" / "QCOM" / "2026-09-23"
        self.assertEqual(json.loads((carpeta / "entradas.json").read_text(encoding="utf-8"))["pos"]["precio_entrada"], 195.0)
        self.assertEqual(len(list((carpeta / "versiones").glob("*.json"))), 1)
        self.assertEqual(self._post(datos, cabecera="otra")[0], 403)             # solo desde la propia página


def _datos_qcom(sin=()):
    datos = json.loads((F / "QCOM" / "entradas.json").read_text(encoding="utf-8"))
    for k in sin:
        datos.pop(k, None)
    return datos


class R21FormularioAlInforme(_Informes):
    """R21. Lo que se guarda en el asistente aparece en la portada y en la parte G."""
    T, HOY = "QCOM", HOY

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        env = dict(os.environ)
        os.environ["WC_DATOS"] = cls.tmp
        try:
            datos = _datos_qcom()
            datos["pos"].update({"precio_entrada": 196.5, "tamano_pct": 2.5, "stop": "185 USD al cierre"})
            cls.RUTA_ENTRADAS = asistente.guardar("QCOM", HOY, datos)
        finally:
            os.environ.clear()
            os.environ.update(env)
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    @pytest.mark.regresion("R21")
    def test_portada_y_parte_g(self):
        portada = self._portada().replace("\xa0", " ")
        for esperado in ("RECOMENDACIÓN: MANTENER", "Entrada 196,50 USD (22/09/2026)", "Tamaño 2,5 % de la cartera", "Stop 185 USD al cierre",
                         "Horizonte 12 meses", "la regla sugiere «Vender»"):
            self.assertIn(esperado, portada)
        g = self._parte('id="parte-G"', 'id="parte-H"').replace("\xa0", " ")
        self.assertIn("Qualcomm combina un negocio de licencias", g)
        self.assertIn("Tamaño de la posición 2,5 %", g)
        self.assertIn("Fechas de revisión: 04/11/2026 · 03/02/2027 · 22/09/2027", g)
        self.assertEqual(self.inf.parte_g.faltas, [])


class R30ParteGVacia(_Informes):
    """R30. Sin entradas de posición no se emite, y la parte G dice qué falta del analista: nunca «N/A — el analista no ha adjuntado…»."""
    T, HOY = "QCOM", HOY

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.RUTA_ENTRADAS = Path(cls.tmp) / "entradas.json"
        cls.RUTA_ENTRADAS.write_text(json.dumps(_datos_qcom(sin=("pos",)), ensure_ascii=False), encoding="utf-8")
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    @pytest.mark.regresion("R30")
    def test_parte_g_vacia_no_se_emite(self):
        g = self._parte('id="parte-G"', 'id="parte-H"')
        self.assertNotIn("N/A", g)
        self.assertNotIn("no ha adjuntado", g)
        for pendiente in ("argumento", "recomendacion", "invalidacion", "tamano", "kpis", "salida"):
            self.assertIn(self.inf.parte_g.pendientes[pendiente], g.replace("\xa0", " "))
        bloqueos = [f for f in self.inf.faltan if f.startswith("Parte G · pos.")]
        self.assertTrue(any("pos.recomendacion" in f for f in bloqueos) and any("pos.precio_entrada" in f for f in bloqueos))
        self.assertIn("RECOMENDACIÓN: VENDER", self._portada())               # sin la del analista, la de la regla


if __name__ == "__main__":
    unittest.main()
