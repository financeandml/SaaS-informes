"""Fase 2 (parte B, apartados 4–7, y la guía de los apartados 2 y 26): las regresiones de `docs/spec/07` que se cierran
aquí. Sin red: respuestas de EDGAR y de Nasdaq congeladas en `tests/fixtures/`.

Cada prueba cita el fallo real que caza en el informe de QCOM del 23/09/2026.
"""

import html as html_mod
import os
import re
import unittest
from datetime import date
from pathlib import Path

import pytest

from tesis.fuentes import calendario, precio as precio_mod, sec
from tesis.verificacion import contraste
from tesis.datos import derivados, ficha, gobierno, guia, guidance, segmentos
from tesis import entorno, entradas, render
from tesis.plantillas import informe, parte_b
from tesis.motor import multiplos
from tesis.heredado import regiones
from tesis.datos.expediente import Expediente
from tesis.datos.hechos import Capa, Origen, Periodo, de_valor, etiqueta_fiscal

RAIZ = Path(__file__).resolve().parent.parent
FIXTURES = RAIZ / "tests" / "fixtures"
HOY = date(2026, 9, 23)
_INGLES = re.compile(r"\b(the|and|our|we|with|which|that|from|of|revenues?|segments?)\b", re.I)


def _texto_visible(fragmento: str) -> str:
    sin_svg = re.sub(r"<svg.*?</svg>", " ", fragmento, flags=re.S)
    return " ".join(html_mod.unescape(re.sub(r"<[^>]+>", " ", sin_svg)).split())


def _apartado(html: str, numero: int) -> str:
    inicio = html.index(f'id="ap-{numero}"')
    fin = html.index('id="ap-', inicio + 10)
    return html[inicio:fin]


class _ConFixtures(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._env, cls._raiz, cls._cache = dict(os.environ), entorno.RAIZ, sec.CACHE
        cls._bolsa = (precio_mod.CACHE_BOLSA, precio_mod.SOLO_CACHE)
        os.environ["WC_SEC_CONTACTO"] = ""
        entorno.RAIZ, sec.CACHE = FIXTURES, FIXTURES / "cache_sec"
        precio_mod.CACHE_BOLSA, precio_mod.SOLO_CACHE = FIXTURES / "cache_bolsa", True

    @classmethod
    def tearDownClass(cls):
        entorno.RAIZ, sec.CACHE = cls._raiz, cls._cache
        precio_mod.CACHE_BOLSA, precio_mod.SOLO_CACHE = cls._bolsa
        os.environ.clear()
        os.environ.update(cls._env)


class Qualcomm(_ConFixtures):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.emisor = sec.emisor("QCOM")
        cls.facts, cls.obtenido = sec.companyfacts(cls.emisor.cik)
        cls.anuales = sec.calendario(cls.facts, 12)
        cls.etiqueta = staticmethod(lambda p: etiqueta_fiscal(p, cls.anuales[-1].fin, sec.desfase_fiscal(cls.facts)))
        cls.entradas = entradas.cargar("QCOM", ruta=FIXTURES / "QCOM" / "entradas.json")
        cls.portada = sec.portada_10k(cls.emisor)
        cls.gobierno = gobierno.construir(Expediente("QCOM", []), None, cls.emisor)
        cls.pb = parte_b.construir(cls.emisor, HOY, cls.facts, cls.portada, cls.entradas, cls.gobierno)

    def _informe(self, pb=None):
        exp = Expediente("QCOM", [])
        per = contraste.periodos_del_informe(exp, facts=self.facts, hasta=HOY)
        tab = contraste.contrastar(exp, self.facts, self.obtenido, per)
        hechos = derivados.calcular(tab.hechos(), per["anuales"] + per["trimestres"], per["instantes"])
        precio = de_valor("precio", Periodo.instante(date(2026, 9, 22)), 198.27, Capa.SEC, Origen(documento="Nasdaq"), unidad="USD/acción")
        mult = multiplos.construir(hechos, per["trimestres"], per["anuales"], precio, 1_050_000_000, None, self.facts, self.obtenido)
        inf = informe.construir("QCOM", HOY, self.emisor, exp, tab, per, ficha.construir(self.emisor, exp, self.portada, self.facts),
                                self.gobierno, guidance.construir(exp, self.emisor.depositos, HOY), regiones.construir(exp, tab), precio, {},
                                multiplos=mult, proxima=calendario.proxima("QCOM", None, HOY), parte_b=pb or self.pb)
        return inf, render.a_html(inf)

    @pytest.mark.regresion("R18")
    def test_segmentos_del_xbrl_dimensional(self):
        """R18. El apartado 4 de Qualcomm traía las regiones de Netflix (UCAN, EMEA…) vacías. Ahora QCT/QTL, las líneas
        de QCT y la geografía salen de los ejes del XBRL inline, cuadrados con el consolidado."""
        s = self.pb.segmentos
        fy25 = next(p for p in s.periodos if self.etiqueta(p) == "2025")
        por_rotulo = {l.rotulo: l for l in s.lineas}
        self.assertEqual(round(por_rotulo["QCT"].valores[fy25].valor / 1e6), 38_367)
        self.assertEqual(round(por_rotulo["QTL"].valores[fy25].valor / 1e6), 5_582)
        lineas_qct = [l for l in s.de_tipo("producto") if l.padre == por_rotulo["QCT"].miembro]
        self.assertEqual({l.rotulo for l in lineas_qct}, {"Teléfonos móviles", "Automoción", "IoT"})
        self.assertEqual(round(sum(l.valores[fy25].valor for l in lineas_qct) / 1e6), 38_367)
        geo, padre = s.geografia()
        self.assertIsNone(padre)
        self.assertEqual({l.rotulo for l in geo}, {"China", "Estados Unidos", "Corea del Sur", "Resto del mundo"})
        self.assertFalse([c for c in s.cuadres if c.startswith("≠")], s.cuadres)
        self.assertEqual(len([c for c in s.cuadres if c.startswith("✓")]), 7)       # 3 ejercicios × 2 + UDM
        self.assertEqual(s.etiqueta_udm, "UDM a 3T FY26")
        self.assertEqual(round(por_rotulo["QCT"].valores[s.udm].valor / 1e6), 38_014)
        self.assertFalse(s.sin_traducir)

    @pytest.mark.regresion("R17")
    def test_accionistas_ejecutivos_y_retribucion_de_edgar(self):
        """R17. Accionistas, ejecutivos y retribución salían vacíos: se leían con patrones del PDF de la proxy de Netflix.
        Ahora del HTML de la DEF 14A, del 10-K, del Exhibit 21 y de los 13G en XML (el último de cada declarante manda)."""
        g = self.gobierno
        self.assertEqual(g.fecha_accionistas, date(2025, 12, 15))
        por_nombre = {a.nombre: a for a in g.accionistas}
        self.assertEqual(por_nombre["BlackRock, Inc."].porcentaje, 8.71)
        self.assertEqual(por_nombre["Vanguard Capital Management"].porcentaje, 7.51)
        self.assertEqual(por_nombre["State Street Corporation"].porcentaje, 5.0)
        self.assertNotIn("Vanguard Group Inc.", por_nombre, "su 13G/A de marzo de 2026 declara 0 %")
        self.assertFalse([n for n in por_nombre if "QUALCOMM" in n.upper()], "13G que presenta la compañía sobre otras")
        # EDGAR lista en los depósitos de Qualcomm también los 13G que Qualcomm presenta sobre otras compañías
        from tesis.datos import proxy
        xml, _ = sec.descargar_texto("https://www.sec.gov/Archives/edgar/data/804328/000110465926059421/primary_doc.xml")
        self.assertEqual(proxy.leer_13g(xml, date(2026, 5, 12), "SCHEDULE 13G/A", "", "").declarante, "QUALCOMM Incorporated")
        self.assertIsNone(proxy.leer_13g(xml, date(2026, 5, 12), "SCHEDULE 13G/A", "", self.emisor.nombre), "13G sobre otra compañía")
        self.assertTrue(g.salidas_13g and "Vanguard Group" in g.salidas_13g[0])
        ejecutivos = {e.nombre: e for e in g.ejecutivos}
        self.assertEqual((ejecutivos["Cristiano R. Amon"].edad, ejecutivos["Cristiano R. Amon"].cargo), (55, "Presidente y consejero delegado (CEO)"))
        self.assertEqual(ejecutivos["Akash Palkhiwala"].cargo, "Director financiero (CFO)")
        self.assertEqual(ejecutivos["Ann Chaplin"].cargo, "Directora jurídica y secretaria del consejo")
        self.assertEqual(g.cabecera_retribucion, ["Año", "Salario", "Acciones", "Incentivo en efectivo", "Otras", "Total"])
        amon = next(r for r in g.retribucion if r.nombre == "Cristiano R. Amon")
        self.assertEqual((amon.anio, amon.total), (2025, 29_701_097))
        self.assertIn(("Qualcomm Technologies, Inc.", "Delaware"), [(f.nombre, f.jurisdiccion) for f in g.filiales])
        self.assertFalse(g.faltan, g.faltan)

    @pytest.mark.regresion("R16")
    def test_guia_como_candidatos_y_frente_a_real(self):
        """R16. La guía «Business Outlook» de Qualcomm no se leía (se buscaba la columna «Forecast» de las cartas de
        Netflix): Cuadro 2 y apartado 26 vacíos. Ahora son candidatos; tras confirmarlos, los dos quedan completos."""
        ultima = self.pb.notas[-1]
        self.assertEqual(ultima.presentado, date(2026, 7, 29))
        cand = {c.metrica: c for c in ultima.candidatos}
        self.assertEqual((cand["ingresos"].trimestre, cand["ingresos"].bajo, cand["ingresos"].alto), ("4T FY26", 9.7e9, 10.5e9))
        self.assertEqual((cand["bpa_diluido"].bajo, cand["bpa_no_gaap"].alto), (1.22, 2.25))
        self.assertEqual(len(guia.vigentes(self.pb.notas, [])), 0, "sin confirmar no se imprime")
        vigentes = guia.vigentes(self.pb.notas, self.pb.confirmadas)
        self.assertEqual({c.trimestre for c in vigentes}, {"4T FY26"})
        self.assertEqual(len(vigentes), 5)
        comp = guia.frente_a_real(self.pb.notas, self.pb.confirmadas, trimestres=8)
        self.assertEqual(sorted({x.candidato.trimestre for x in comp}, key=lambda t: (t[-2:], t[0])),
                         ["4T FY24", "1T FY25", "2T FY25", "3T FY25", "4T FY25", "1T FY26", "2T FY26", "3T FY26"])
        t3 = next(x for x in comp if x.candidato.trimestre == "3T FY26" and x.candidato.metrica == "ingresos")
        self.assertEqual(t3.real.valor, 9_947e6)
        self.assertTrue(t3.dentro)
        inf, html = self._informe()
        self.assertEqual(len(inf.objetivos.filas), 5)
        self.assertEqual(len(inf.parte_f.cuadros["guias"].filas), 24)        # 8 trimestres × ingresos, BPA GAAP y no GAAP
        # el real GAAP de la nota se cuadra con el hecho XBRL del trimestre cuando el informe lo tiene
        self.assertTrue(any("coincide con el hecho XBRL" in c.nota for f in inf.parte_f.cuadros["guias"].filas for c in f.celdas))

    @pytest.mark.regresion("R10")
    def test_proximos_resultados_posteriores_al_informe(self):
        """R10. «Próximos resultados» decía 29/07/2026, la conferencia ya celebrada. Ahora la fecha de Nasdaq, estimada, y
        nunca anterior a la fecha del informe."""
        p = calendario.proxima("QCOM", None, HOY)
        self.assertEqual(p.fecha, date(2026, 11, 4))
        self.assertTrue(p.estimada)
        self.assertIsNone(calendario.proxima("QCOM", None, date(2026, 11, 5)), "una fecha ya pasada no es la próxima")
        _, html = self._informe()
        apartado = _texto_visible(_apartado(html, 7))
        self.assertIn("Próximos resultados (4T FY26) 04/11/2026", apartado)
        self.assertIn("estimada", apartado)
        self.assertNotIn("29/07/2026", apartado.split("Dividendo")[0])

    @pytest.mark.regresion("R11")
    def test_apartado_4_en_espanol(self):
        """R11. El apartado 4 imprimía la descripción del Item 1 en inglés. Ahora el texto del analista en español; sin él,
        un aviso, nunca el inglés del 10-K."""
        inf, html = self._informe()
        texto = _texto_visible(_apartado(html, 4))
        self.assertIn("Qualcomm diseña semiconductores", texto)
        # con el 10-K adjunto, la ficha trae la descripción literal del Item 1, en inglés: no entra en el cuerpo
        from tesis.datos.hechos import Cita
        inf.descripcion = Cita("descripcion", "We develop and commercialize foundational technologies and products used across industries.",
                               Origen(documento="10-K", pagina=4))
        texto = _texto_visible(_apartado(render.a_html(inf), 4))
        self.assertFalse(_INGLES.findall(texto), _INGLES.findall(texto)[:10])
        vacio = parte_b.ParteB(segmentos=self.pb.segmentos, notas=self.pb.notas)
        _, html = self._informe(vacio)
        texto = _texto_visible(_apartado(html, 4))
        self.assertIn("descripción del negocio en español", texto)
        self.assertFalse(_INGLES.findall(texto), _INGLES.findall(texto)[:10])


class Netflix(_ConFixtures):
    def test_mismo_codigo_otro_emisor(self):
        """Sin patrones de emisor: Netflix da sus regiones dentro de «Streaming», y su proxy trae a Vanguard ya en 0 %."""
        e = sec.emisor("NFLX")
        s = segmentos.construir(e, etiqueta=lambda p: p.clave)
        geo, padre = s.geografia()
        self.assertEqual(padre, "nflx:StreamingMember")
        self.assertEqual({l.rotulo for l in geo}, {"Estados Unidos y Canadá", "Europa, Oriente Medio y África", "Latinoamérica", "Asia-Pacífico"})
        self.assertFalse([c for c in s.cuadres if c.startswith("≠")], s.cuadres)
        g = gobierno.construir(Expediente("NFLX", []), None, e)
        self.assertNotIn("The Vanguard Group, Inc.", [a.nombre for a in g.accionistas])
        self.assertIn("Co-consejero delegado (CEO) y presidente", [x.cargo for x in g.ejecutivos])
        notas, _ = guia.notas_edgar(e)
        comp = guia.frente_a_real(notas, [c.id for n in notas for c in n.candidatos], splits=[(date(2025, 11, 14), 10.0)])
        t = next(x for x in comp if x.candidato.trimestre == "2T FY25" and x.candidato.metrica == "bpa_diluido")
        self.assertAlmostEqual(t.candidato.medio, 0.703)          # 7,03 antes del split 10:1, dividido por 10
        self.assertEqual(t.real.valor, 0.72)


class Citas(unittest.TestCase):
    def test_cita_verificada_y_cifras(self):
        textos = {"8-K 2026-07-29": "We expect growth to accelerate from 24% in fiscal 2026 to greater than 60% in fiscal 2027."}
        ok, _ = entradas.verificar_cita({"doc": "8-K 2026-07-29", "texto": "growth to accelerate from 24% in fiscal 2026"}, textos, 0.9)
        self.assertTrue(ok)
        ok, motivo = entradas.verificar_cita({"doc": "8-K 2026-07-29", "texto": "growth to accelerate from 34% in fiscal 2026"}, textos, 0.9)
        self.assertFalse(ok, "una cifra cambiada no es la misma cita")
        ok, motivo = entradas.verificar_cita({"doc": "10-K", "texto": "x"}, textos, 0.9)
        self.assertFalse(ok)


if __name__ == "__main__":
    unittest.main()
