"""Fase 4 (parte E, apartados 21–23): mercado, competencia y foso defensivo. Citas con página, tarjetas de evidencia,
cuota implícita y el informe de control de QCOM. Sin red: EDGAR y Nasdaq congelados en `tests/fixtures/`."""

import copy
import gzip
import json
import unittest
from datetime import date
from pathlib import Path

from tesis.plantillas import informe, parte_e
from tesis.datos import tablas_html
from tesis.entradas import tarjetas
from tesis.entradas import Entradas, comprobar_paso5, verificar_cita
from tests.prueba_f3 import _Informes

F = Path(__file__).resolve().parent / "fixtures"
DIEZ_K = F / "cache_sec" / "www_sec_gov_Archives_edgar_data_804328_000080432825000085_qcom_20250928_htm.json.gz"
SEP = ("We grant licenses or otherwise provide rights to use our cellular standard-essential patents (including 3G, 4G and 5G) "
       "for cellular devices on a worldwide basis.")


def _paginas_10k() -> dict:
    html = json.loads(gzip.decompress(DIEZ_K.read_bytes()))["datos"]
    return {"10-K": tablas_html.texto_plano(html), **{f"10-K#{k}": v for k, v in tablas_html.folios(tablas_html.paginas(html)).items()}}


class CitasConPagina(unittest.TestCase):
    """03 §6: una cita manual (documento + página + texto) vale si el texto aparece en esa página."""

    @classmethod
    def setUpClass(cls):
        cls.textos = _paginas_10k()

    def test_folios_del_10k(self):
        """La página es el folio impreso al pie del documento de EDGAR («28», «F-12»), no el orden del trozo."""
        self.assertIn("10-K#F-12", self.textos)
        self.assertIn("Examples (some of which are strategic partners", self.textos["10-K#28"])
        self.assertNotIn("10-K#1", self.textos)                       # portada e índice: sin folio

    def test_cita_fuera_de_su_pagina_se_rechaza(self):
        ok, _ = verificar_cita({"doc": "10-K", "pag": "10", "texto": SEP}, self.textos, 0.9)
        self.assertTrue(ok)
        ok, motivo = verificar_cita({"doc": "10-K", "pag": "11", "texto": SEP}, self.textos, 0.9)
        self.assertFalse(ok)
        self.assertIn("página 11", motivo)
        ok, motivo = verificar_cita({"doc": "10-K", "pag": "400", "texto": SEP}, self.textos, 0.9)
        self.assertFalse(ok)
        self.assertTrue(verificar_cita({"doc": "10-K", "texto": SEP}, self.textos, 0.9)[0])   # sin página: el documento

    def test_la_cita_puede_seguir_en_la_pagina_siguiente(self):
        textos = {"D": "uno dos tres cuatro", "D#1": "Primera frase. La cita empieza aquí y", "D#2": "sigue en la otra página. Fin."}
        cita = {"doc": "D", "texto": "La cita empieza aquí y sigue en la otra página."}
        self.assertTrue(verificar_cita(dict(cita, pag="1"), textos, 0.9)[0])
        self.assertFalse(verificar_cita(dict(cita, pag="2"), textos, 0.9)[0])        # empieza en la 1, no en la 2

    def test_tarjetas_de_evidencia(self):
        """Las tarjetas son citas con página que la verificación da por buenas; las del foso encuentran las patentes."""
        for apartado in ("competencia", "moat"):
            lista = tarjetas.proponer(self.textos, apartado)
            self.assertTrue(lista, apartado)
            for t in lista:
                self.assertTrue(verificar_cita(t.cita, self.textos, 0.99)[0], (apartado, t.pag, t.texto[:60]))
        self.assertIn(("10", SEP), {(t.pag, t.texto) for t in tarjetas.proponer(self.textos, "moat", maximo=20)})


class Paso5(unittest.TestCase):
    TEXTOS = {"10-K": "Our patents are licensed worldwide. We compete with many companies.",
              "10-K#3": "Our patents are licensed worldwide.", "10-K#4": "We compete with many companies."}

    def test_faltas(self):
        e = Entradas({"mercado": {"cifras": [{"etiqueta": "x", "clase": "SAM", "valor": 10, "unidad": "millones USD", "anio": 2025,
                                              "metodo": "top_down", "evidencia": [{"doc": "10-K", "pag": "4", "texto": "Our patents are licensed worldwide.",
                                                                                    "texto_es": "Licencia sus patentes."}]}]},
                      "competencia": {"competidores": [{"nombre": "A", "por_que": "Compite"}]},
                      "moat": {"fuentes": [{"tipo": "intangibles", "durabilidad_anios": 5, "tendencia": "crece",
                                            "evidencias": [{"doc": "10-K", "pag": "3", "texto": "Our patents are licensed worldwide."}]}],
                               "amenazas": "Pocas."}})
        faltas = " | ".join(comprobar_paso5(e, self.TEXTOS, 0.9))
        for esperado in ("falta al menos un TAM", "página 4", "competidores: 1 (mínimo 3)", "por_que: 1 palabras",
                         "tendencia «crece»", "texto_es", "moat.amenazas: 1 palabras", "comparables: 0"):
            self.assertIn(esperado, faltas)

    def test_cuota_implicita_es_ingresos_entre_sam(self):
        self.assertAlmostEqual(parte_e.cuota_implicita(44_284e6, {"valor": 180_000, "unidad": "millones USD"}), 44_284 / 180_000)
        self.assertAlmostEqual(parte_e.cuota_implicita(5e9, {"valor": 20, "unidad": "miles de millones USD"}), 0.25)
        self.assertIsNone(parte_e.cuota_implicita(5e9, {"valor": 800, "unidad": "millones de hogares"}))   # no es dinero


class QualcommParteE(_Informes):
    """Informe de control de QCOM: 21–23 completos, en español, sin cifras sin cita y sin N/A."""
    T, HOY = "QCOM", date(2026, 9, 23)

    def _e(self) -> str:
        return self._parte('id="parte-E"', "<!-- ============================== G")

    def test_21_a_23_completos_y_sin_na(self):
        pe = self.inf.parte_e
        self.assertEqual(pe.faltas, [])
        self.assertEqual(pe.pendientes, {})
        texto = self._e()
        self.assertNotIn("N/A", texto)
        self.assertNotIn("Pendiente", texto)
        for rotulo in ("Tamaño de mercado: TAM, SAM y SOM", "Competidores", "Comparables: tamaño, crecimiento y margen",
                       "Fuentes del foso defensivo", "Datos de apoyo del foso defensivo", "Amenazas."):
            self.assertIn(rotulo, texto)
        self.assertTrue(pe.grafico.startswith("<svg") or "<svg" in pe.grafico[:200])

    def test_cifras_con_cita_y_en_espanol(self):
        """Cada cifra del analista lleva su cita con página; el literal inglés solo va en el atributo title."""
        m = self.inf.parte_e.cuadros["mercado"]
        for f in m.filas:
            if f.capa == "S":
                self.assertRegex(f.celdas[-1].texto, r"\[[^\]]+, pág\. [\w-]+\]$", f.rotulo)
        texto = self._e()
        self.assertNotIn("standard-essential", texto)
        self.assertIn("standard-essential", self.html)                 # en el title del HTML
        self.assertIn("patentes esenciales", texto)

    def test_cuota_implicita_en_el_informe(self):
        pe = self.inf.parte_e
        ingresos = self.hechos[("ingresos", sorted(self.anuales, key=lambda p: p.fin)[-1])].valor
        self.assertAlmostEqual(pe.cuota, ingresos / 180_000e6)
        self.assertIn("la cuota implícita sobre el SAM es del 24,6 %", self._e())

    def test_som_por_defecto_son_los_ingresos(self):
        datos = copy.deepcopy(self.ent.datos)
        datos["mercado"]["cifras"] = [c for c in datos["mercado"]["cifras"] if c["clase"] != "SOM"]
        pe = parte_e.construir(informe.Cuadros(), Entradas(datos), self.pb.textos, 0.9, self.hechos, self.anuales,
                               lambda p: str(p.fin.year), motor=self.motor, alias=self.pb.alias)
        self.assertTrue(pe.som_por_defecto)
        fila = next(f for f in pe.cuadros["mercado"].filas if "SOM por defecto" in f.rotulo)
        self.assertEqual(fila.celdas[2].texto.replace("\xa0", " "), "44.284 millones USD")
        self.assertIn("el SOM son los ingresos verificados del ejercicio 2025", pe.texto_21)

    def test_cita_en_otra_pagina_no_se_imprime(self):
        datos = copy.deepcopy(self.ent.datos)
        datos["moat"]["fuentes"][0]["evidencias"][0]["pag"] = "11"
        pe = parte_e.construir(informe.Cuadros(), Entradas(datos), self.pb.textos, 0.9, self.hechos, self.anuales,
                               lambda p: str(p.fin.year), motor=self.motor, alias=self.pb.alias)
        evidencia = pe.cuadros["foso"].filas[0].celdas[-1].texto          # la otra evidencia sí verifica
        self.assertNotIn("patentes esenciales", evidencia)
        self.assertIn("cientos de compañías", evidencia)
        self.assertTrue(any("página 11" in x for x in pe.faltas))
        datos["mercado"]["cifras"][0]["evidencia"][0]["pag"] = "5"           # la cifra con una cita mala no se imprime
        pe = parte_e.construir(informe.Cuadros(), Entradas(datos), self.pb.textos, 0.9, self.hechos, self.anuales,
                               lambda p: str(p.fin.year), motor=self.motor, alias=self.pb.alias)
        self.assertNotIn("TAM", [f.celdas[0].texto for f in pe.cuadros["mercado"].filas])


if __name__ == "__main__":
    unittest.main()
