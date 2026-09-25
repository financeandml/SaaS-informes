"""Fase 5 (parte F, apartados 24–26): Item 1A de EDGAR, riesgos del analista, caso bajista e historial (guía → real y
consenso → BPA). Sin red: EDGAR y Nasdaq congelados en `tests/fixtures/`."""

import copy
import gzip
import json
import os
import unittest
from datetime import date
from pathlib import Path

from tesis import entorno, guia, informe, item1a, parte_f, sec, tablas_html
from tesis.entradas import Entradas, comprobar_paso6, verificar_cita
from tests.prueba_f3 import _Informes

F = Path(__file__).resolve().parent / "fixtures"
DIEZ_K = {"QCOM": "www_sec_gov_Archives_edgar_data_804328_000080432825000085_qcom_20250928_htm.json.gz",
          "NFLX": "www_sec_gov_Archives_edgar_data_1065280_000106528026000034_nflx_20251231_htm.json.gz"}


def _html(t: str) -> str:
    return json.loads(gzip.decompress((F / "cache_sec" / DIEZ_K[t]).read_bytes()))["datos"]


class ItemUnoA(unittest.TestCase):
    """03 §6: los epígrafes del Item 1A por su tipografía, literales y con la página que ve el lector."""

    @classmethod
    def setUpClass(cls):
        cls.html = {t: _html(t) for t in DIEZ_K}
        cls.item = {t: item1a.leer(h) for t, h in cls.html.items()}

    def test_epigrafes_por_su_tipografia(self):
        q, n = self.item["QCOM"], self.item["NFLX"]
        self.assertEqual((q.estilo, len(q.epigrafes)), ("bi", 24))          # negrita y cursiva; el resumen previo, solo cursiva
        self.assertEqual((n.estilo, len(n.epigrafes)), ("b", 32))
        self.assertTrue(q.epigrafes[0].texto.startswith("We derive a significant portion of our revenues from a small number"))
        self.assertEqual(q.epigrafes[0].cabecera, "RISKS RELATED TO OUR OPERATING BUSINESSES")

    def test_el_resumen_en_cursiva_no_son_los_epigrafes(self):
        """Con más frases en cursiva (un resumen de riesgos) que epígrafes en negrita, los epígrafes son los de negrita."""
        cursiva = "".join(f'<p><i>Summary risk number {k} could adversely affect our business and results.</i></p>' for k in range(6))
        epigrafes = "".join(f'<p><b><i>Heading risk number {k} could adversely affect our business and results.</i></b></p><p>Body text.</p>'
                            for k in range(3))
        html = f'<p><b>Item 1A. Risk Factors</b></p>{cursiva}<p><b>RISKS RELATED TO OUR BUSINESS</b></p>{epigrafes}<p><b>Item 1B. Unresolved</b></p>'
        it = item1a.leer(html)
        self.assertEqual((it.estilo, len(it.epigrafes)), ("bi", 3))
        self.assertEqual(it.epigrafes[0].cabecera, "RISKS RELATED TO OUR BUSINESS")

    def test_cada_epigrafe_esta_en_su_pagina(self):
        """La página del epígrafe es la de las citas: el literal verifica en esa página y no en la siguiente."""
        for t, it in self.item.items():
            textos = {f"10-K#{k}": v for k, v in tablas_html.folios(tablas_html.paginas(self.html[t])).items()}
            textos["10-K"] = ""
            for ep in it.epigrafes:
                self.assertTrue(verificar_cita({"doc": "10-K", "pag": ep.pagina, "texto": ep.texto[:120]}, textos, 0.95)[0], (t, ep.pagina, ep.texto[:50]))

    def test_familias_por_reglas_y_correccion_del_analista(self):
        q = self.item["QCOM"]
        comp = item1a.buscar(q, "Our industry is subject to intense competition")
        self.assertEqual((comp.familia, comp.certeza), ("competitivo", "alta"))            # por la cabecera del 10-K
        self.assertEqual(sum(len(v) for v in q.por_familia().values()), 24)
        corr = item1a.leer(self.html["QCOM"], [{"epigrafe": "We operate in the highly cyclical", "familia": "competitivo"}])
        ep = item1a.buscar(corr, "We operate in the highly cyclical semiconductor industry")
        self.assertEqual((ep.familia, ep.motivo), ("competitivo", "corregida por el analista"))


class Historial(unittest.TestCase):

    def test_la_guia_de_qcom_y_la_de_nflx_salen_por_el_mismo_codigo(self):
        """Rangos (QCOM) y columna «Forecast» (NFLX): las mismas funciones leen, comparan con el real y pintan el cuadro."""
        env, raiz, cache = dict(os.environ), entorno.RAIZ, sec.CACHE
        os.environ["WC_SEC_CONTACTO"] = ""
        entorno.RAIZ, sec.CACHE = F, F / "cache_sec"
        try:
            for t in ("QCOM", "NFLX"):
                e = sec.emisor(t)
                notas, faltan = guia.notas_edgar(e)
                facts, _ = sec.companyfacts(e.cik)
                todos = {c.id for nota in notas for c in nota.candidatos}
                comp = guia.frente_a_real(notas, todos, {}, splits=[(f, r) for f, r, _ in sec.splits(facts)])
                self.assertEqual(faltan, {}, t)
                self.assertGreaterEqual(len({x.candidato.trimestre for x in comp}), 8, t)
                self.assertTrue(all(x.real is not None and x.desvio is not None for x in comp), t)
                self.assertTrue({"ingresos", "bpa_diluido"} <= {x.candidato.metrica for x in comp}, t)
                cuadro = parte_f.construir(informe.Cuadros(), _Pb(Entradas()), None, comp, {}, [], str, 0.9, 0.02).cuadros["guias"]
                self.assertEqual(len({f.rotulo.split(" · ")[0] for f in cuadro.filas}), 8, t)
        finally:
            entorno.RAIZ, sec.CACHE = raiz, cache
            os.environ.clear()
            os.environ.update(env)

    def test_un_desvio_mayor_que_el_umbral_exige_causas(self):
        rango = _comparacion(10, 12, 10.5)                        # dentro del rango
        leve = _comparacion(11, 11, 10.9)                         # guía puntual, −0,9 %
        fallo = _comparacion(10, 12, 9.0)                         # −18 % frente al punto medio
        self.assertEqual(parte_f.fallos([rango, leve], [], 0.02, str), [])
        self.assertEqual(len(parte_f.fallos([rango, leve, fallo], [], 0.02, str)), 1)
        self.assertEqual(len(parte_f.fallos([], [_Sorpresa(-0.03), _Sorpresa(-0.01), _Sorpresa(0.05)], 0.02, lambda m: "3T FY26")), 1)
        e = Entradas({"historial": {"causas": {"texto": ""}}})
        faltas = " | ".join(comprobar_paso6(e, {}, 0.9, lambda _: True, ["3T FY26 · Ingresos: -18,2 % frente a la guía"]))
        self.assertIn("historial.causas: obligatorias", faltas)
        self.assertNotIn("historial.causas", " | ".join(comprobar_paso6(e, {}, 0.9, lambda _: True, [])))


class Paso6(unittest.TestCase):

    def test_faltas(self):
        e = Entradas({"riesgos": {"top": [{"origen": {"epigrafe": "No existe"}, "texto_es": "Riesgo corto", "familia": "otra",
                                           "probabilidad": 6, "impacto": 2, "mitigante": "Nada", "senal": ""}]},
                      "bear": {"disparadores": [{"descripcion": "Caen las ventas de la compañía", "metrica": "ventas", "umbral": -5,
                                                 "plazo": "FY27", "driver": "esc.base.margen_ebit"}]},
                      "esc": {"base": {"margen_ebit": 20}}})
        faltas = " | ".join(comprobar_paso6(e, {}, 0.9, lambda t: False))
        for esperado in ("riesgos.top: 1 (se piden 5)", "no es el comienzo de un epígrafe", "texto_es: 2 palabras", "familia: «otra»",
                         "probabilidad: entero de 1 a 5", "mitigante: 1 palabras", "senal: falta", "bear.disparadores: 1 (mínimo 3)",
                         "no es un supuesto del escenario pesimista"):
            self.assertIn(esperado, faltas)


class QualcommParteF(_Informes):
    """Informe de control de QCOM: 24–26 completos, en español y sin mensajes técnicos."""
    T, HOY = "QCOM", date(2026, 9, 23)

    def _f(self) -> str:
        return self._parte('id="parte-F"', 'id="parte-G"')

    def test_24_a_26_completos(self):
        pf = self.inf.parte_f
        self.assertEqual(pf.faltas, [])
        self.assertEqual(pf.pendientes, {})
        self.assertEqual(set(pf.cuadros), {"top", "familias", "disparadores", "pilares", "guias", "consenso"})
        self.assertIn("<svg", pf.grafico_matriz)
        texto = self._f()
        for prohibido in ("N/A", "Pendiente", "Traceback", "None", "http", "XBRL", ".py", "esc.pesimista"):
            self.assertNotIn(prohibido, texto)
        self.assertIn("En el escenario pesimista, con una probabilidad del 25 %", texto.replace("\xa0", " "))
        self.assertIn("Causas y aprendizajes.", texto)

    def test_epigrafes_literales_solo_en_el_html(self):
        texto = self._f()
        self.assertNotIn("We derive a significant portion", texto)
        self.assertIn("We derive a significant portion", self.html)          # en el atributo title
        self.assertIn("Item 1A, pág. 16", texto)

    def test_sin_causas_con_un_fallo_no_se_emite(self):
        self.assertEqual(self.inf.parte_f.fallos, ["4T FY25 · BPA diluido (GAAP): −224,0\xa0% frente a la guía"])
        pb = copy.copy(self.pb)
        pb.entradas = Entradas(copy.deepcopy(self.ent.datos))
        del pb.entradas.datos["historial"]
        pf = parte_f.construir(informe.Cuadros(), pb, self.motor, _comparaciones(self), self.hechos, [], str, 0.9, 0.02)
        self.assertIn("causas", pf.pendientes)
        self.assertTrue(any(x.startswith("historial.causas: obligatorias") for x in pf.faltas))


# ---------------------------------------------------------------------------- ayudas

class _Pb:
    def __init__(self, e: Entradas):
        self.entradas, self.textos, self.alias, self.item1a, self.sorpresas = e, {}, {}, None, []


def _comparacion(bajo, alto, real):
    c = guia.Candidato(id="2026-07-29|3T FY26|ingresos", metrica="ingresos", rotulo="Ingresos", original="Revenues", trimestre="3T FY26",
                       bajo=bajo, alto=alto, unidad="USD", presentado=date(2026, 7, 29), url="", fila="")
    return guia.Comparacion(c, guia.Real(metrica="ingresos", trimestre="3T FY26", valor=real, unidad="USD", presentado=date(2026, 10, 29),
                                         url="", fila=""))


class _Sorpresa:
    def __init__(self, s):
        self.sorpresa, self.mes = s, date(2026, 6, 1)


def _comparaciones(caso):
    from tesis.informe import _etiqueta
    xbrl = {}
    for (campo, p), h in caso.hechos.items():
        if h.hay_dato and p.meses == 3 and campo in ("ingresos", "bpa_diluido"):
            xbrl[(campo, _etiqueta(p, caso.anuales, None))] = h.valor
    return guia.frente_a_real(caso.pb.notas, caso.pb.confirmadas, xbrl, splits=caso.pb.splits)


if __name__ == "__main__":
    unittest.main()
