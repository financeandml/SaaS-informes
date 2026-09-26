"""F10: el estado «propuesto». Lo que propone el sistema no es una entrada hasta que el analista lo confirma; confirmado,
guarda de dónde salió y caduca si cambian sus datos. Sin red (EDGAR y la bolsa desde tests/fixtures)."""

import json
import re
import unittest
from datetime import date
from pathlib import Path

import pytest

from tesis.entradas import asistente, proponer
from tests.prueba_f6 import _Datos

FECHA = date(2026, 9, 23)


class Propuestas(_Datos):
    def test_la_propuesta_no_es_una_entrada_hasta_confirmarla(self):
        """Falla si proponer un sector lo da por puesto: sin confirmar, el paso 1 sigue pidiéndolo."""
        props = proponer.proponer("QCOM", FECHA, {})
        p = props["meta.sector"]
        self.assertIsInstance(p, proponer.Propuesta)
        self.assertIn("SIC", p.fuente)
        faltas, _ = asistente.validar("QCOM", FECHA, {"meta": {"fecha_informe": FECHA.isoformat()}})
        self.assertIn("meta.sector: obligatorio", faltas[1])

    def test_confirmada_y_vigente_no_falta(self):
        p = proponer.proponer("QCOM", FECHA, {})["meta.sector"]
        datos = {"meta": {"fecha_informe": FECHA.isoformat(), "sector": p.valor},
                 "_origen": {"meta.sector": {"tipo": "propuesta", "fuente": p.fuente, "huella": p.huella, "valor": p.valor}}}
        faltas, _ = asistente.validar("QCOM", FECHA, datos)
        self.assertFalse([f for f in faltas[1] if f.startswith("meta.sector")], faltas[1])

    def test_caduca_si_cambian_sus_datos(self):
        """Falla si una propuesta confirmada cuyos datos han cambiado (otra huella) no vuelve a «revisar» en su paso."""
        p = proponer.proponer("QCOM", FECHA, {})["meta.sector"]
        datos = {"meta": {"fecha_informe": FECHA.isoformat(), "sector": p.valor},
                 "_origen": {"meta.sector": {"tipo": "propuesta", "fuente": "SEC EDGAR, SIC 0000", "huella": "0" * 16, "valor": p.valor}}}
        faltas, _ = asistente.validar("QCOM", FECHA, datos)
        self.assertTrue([f for f in faltas[1] if f.startswith("meta.sector: la propuesta cambió")], faltas[1])

    def test_lo_que_cambia_el_analista_es_suyo(self):
        """Falla si un valor confirmado y cambiado después sigue constando como propuesta del sistema (y caduca con ella)."""
        datos = {"meta": {"sector": "software"},
                 "_origen": {"meta.sector": {"tipo": "propuesta", "fuente": "x", "huella": "0" * 16, "valor": "semiconductores"}}}
        proponer.normalizar(datos)
        self.assertEqual(datos["_origen"]["meta.sector"]["tipo"], "analista")
        self.assertEqual(proponer.caducadas(datos, {"meta.sector": proponer.Propuesta("semiconductores", "y", "z")}), [])
        self.assertEqual(proponer.confirmadas(datos), [])

    def test_unas_entradas_antiguas_sin_origen_no_cambian(self):
        """Falla si un entradas.json de antes de F10 (sin `_origen`) gana faltas nuevas."""
        fixture = json.loads((Path(__file__).parent / "fixtures" / "QCOM" / "entradas.json").read_text(encoding="utf-8"))
        self.assertNotIn("_origen", fixture)
        self.assertEqual(proponer.caducadas(fixture, proponer.proponer("QCOM", FECHA, fixture)), [])

    def test_el_bloque_no_confirma_lo_que_es_criterio_del_analista(self):
        self.assertTrue(proponer.en_bloque("meta.sector"))
        self.assertFalse(proponer.en_bloque("pos.recomendacion"))
        self.assertFalse(proponer.en_bloque("campo.que.no.existe"))
        # si alguien la añade a las dos listas, manda «nunca»
        from unittest import mock
        with mock.patch.object(proponer, "_config", return_value={"en_bloque": ["pos.recomendacion"], "nunca_en_bloque": ["pos.recomendacion"]}):
            self.assertFalse(proponer.en_bloque("pos.recomendacion"))

    def test_el_37_nombra_lo_confirmado_en_espanol(self):
        """Falla si lo confirmado desde una propuesta se imprime con su identificador interno en vez de su rótulo."""
        datos = {"meta": {"sector": "semiconductores"},
                 "_origen": {"meta.sector": {"tipo": "propuesta", "fuente": "SEC EDGAR, SIC 3674", "huella": "x", "valor": "semiconductores"}}}
        self.assertEqual(proponer.confirmadas(datos), [("sector", "SEC EDGAR, SIC 3674")])

    def test_tipo_de_informe(self):
        """Inicio de cobertura sin entradas anteriores; actualización si las hay."""
        self.assertEqual(proponer.proponer("QCOM", FECHA, {})["meta.tipo"].valor, "inicio_cobertura")
        asistente.guardar("QCOM", date(2026, 6, 30), {"meta": {"fecha_informe": "2026-06-30"}})
        self.assertEqual(proponer.proponer("QCOM", FECHA, {})["meta.tipo"].valor, "actualizacion")


class Rubrica(unittest.TestCase):
    def test_cada_criterio_tiene_un_estado_valido(self):
        """Falla si un estado de la rúbrica no es uno de los cinco: sin comillas, YAML lee «no» como el booleano falso y el
        resumen contaba los 14 «no» como «por comprobar» (el total y sus partes no casaban)."""
        import yaml
        from tesis.rutas import SPEC
        criterios = yaml.safe_load((SPEC / "08_rubrica.yaml").read_text(encoding="utf-8"))["criterios"]
        self.assertEqual(len(criterios), 40)
        self.assertEqual([c["id"] for c in criterios], list(range(1, 41)))
        for c in criterios:
            self.assertIn(c["estado"], ("si", "parcial", "no", "por_comprobar", "fuera"), c)


class PropuestasEnElNavegador(_Datos):
    @pytest.mark.lenta
    def test_confirmar_en_bloque_y_guardar(self):
        """Falla si la pastilla «Propuesto» no se pinta cuando llegan los datos, si «Confirmar las propuestas de este paso»
        no escribe el valor y su origen, o si tras guardar y recargar no consta como confirmado."""
        from playwright.sync_api import expect, sync_playwright
        from tesis.web import saas
        srv, _ = saas.servir(8797, en_hilo=True)
        ruta = Path(self.tmp) / "entradas" / "QCOM" / FECHA.isoformat() / "entradas.json"
        try:
            with sync_playwright() as pw:
                pagina = pw.chromium.launch().new_page()
                pagina.goto(f"http://127.0.0.1:8797/asistente?ticker=QCOM&fecha={FECHA.isoformat()}&paso=1")
                pagina.wait_for_function("() => document.querySelector('[data-propuesta=\"meta.sector\"]') !== null", timeout=60000)
                pagina.locator("#confirmar-bloque").click()
                expect(pagina.locator(".propuesta.confirmada").first).to_be_visible()
                pagina.locator("#guardar").click()
                expect(pagina.locator("#estado-guardado")).to_have_text(re.compile("^Guardado en"))
                guardado = json.loads(ruta.read_text(encoding="utf-8"))
                self.assertEqual(guardado["_origen"]["meta.sector"]["tipo"], "propuesta")
                self.assertEqual(guardado["meta"]["sector"], guardado["_origen"]["meta.sector"]["valor"])
                pagina.reload()
                pagina.wait_for_function("() => [...document.querySelectorAll('.propuesta.confirmada')].length >= 2", timeout=60000)
                # sin `close()`: en esta máquina no vuelve (render/imprimir.py); Playwright termina Chromium al salir del `with`
        finally:
            srv.shutdown()
            srv.server_close()


if __name__ == "__main__":
    unittest.main()
