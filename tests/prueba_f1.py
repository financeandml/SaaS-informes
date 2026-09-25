"""Fase 1 (esqueleto + parte C + ficha): las regresiones de `docs/spec/07` que se cierran aquí. Sin red: fixtures.

Cada prueba cita el fallo real que caza en los informes de QCOM (23/09/2026) y NFLX (17/09/2026).
"""

import os
import re
import unittest
from datetime import date
from pathlib import Path

import pytest

from tesis.verificacion import contraste
from tesis.datos import derivados, ficha
from tesis import entorno
from tesis.plantillas import indice, informe
from tesis.motor import multiplos
from tesis.fuentes import sec
from tesis.datos.expediente import Expediente
from tesis.datos.hechos import Capa, Origen, Periodo, de_valor, etiqueta_fiscal

RAIZ = Path(__file__).resolve().parent.parent
FIXTURES = RAIZ / "tests" / "fixtures" / "cache_sec"
HOY = date(2026, 9, 23)


class _ConFixtures(unittest.TestCase):
    """La SEC solo desde las respuestas congeladas: sin contacto no hay descarga posible."""

    @classmethod
    def setUpClass(cls):
        cls._env, cls._raiz, cls._cache = dict(os.environ), entorno.RAIZ, sec.CACHE
        os.environ["WC_SEC_CONTACTO"] = ""
        entorno.RAIZ, sec.CACHE = FIXTURES.parent, FIXTURES

    @classmethod
    def tearDownClass(cls):
        entorno.RAIZ, sec.CACHE = cls._raiz, cls._cache
        os.environ.clear()
        os.environ.update(cls._env)


class Qualcomm(_ConFixtures):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.emisor = sec.emisor("QCOM")
        cls.facts, obtenido = sec.companyfacts(cls.emisor.cik)
        cls.exp = Expediente("QCOM", [])
        cls.periodos = contraste.periodos_del_informe(cls.exp, facts=cls.facts, hasta=HOY)
        cls.tab = contraste.contrastar(cls.exp, cls.facts, obtenido, cls.periodos)
        cls.anuales, cls.trimestres = cls.periodos["anuales"], cls.periodos["trimestres"]
        cls.hechos = derivados.calcular(cls.tab.hechos(), cls.anuales + cls.trimestres, cls.periodos["instantes"])
        cls.portada = sec.portada_10k(cls.emisor)
        cls.ficha = ficha.construir(cls.emisor, cls.exp, cls.portada, cls.facts)
        cls.obtenido = obtenido

    def _valor(self, campo, p):
        h = self.hechos.get((campo, p))
        return h.valor if h is not None and h.hay_dato else None

    @pytest.mark.regresion("R1")
    def test_trimestres_con_numero_fiscal(self):
        """R1. El informe llamaba «3T25» al 4T fiscal de Qualcomm (julio–septiembre) y su nota decía que el derivado era el «4T»."""
        cierre = self.anuales[-1].fin
        self.assertEqual([etiqueta_fiscal(p, cierre, self.tab.desfase_fiscal) for p in self.trimestres],
                         ["4T FY25", "1T FY26", "2T FY26", "3T FY26"])
        ingresos = [round(self._valor("ingresos", p) / 1e6) for p in self.trimestres]
        self.assertEqual(ingresos, [11_271, 12_252, 10_599, 9_947])
        cuarto = self.hechos[("ingresos", self.trimestres[0])]
        self.assertIs(cuarto.capa, Capa.DERIVADO, "el 4T fiscal se calcula (ejercicio − 9 meses), no se publica")
        cuadro = informe._cuadro_resultados(informe.Cuadros(), self.hechos, self.tab, self.anuales, self.trimestres)
        self.assertFalse([c for c in cuadro.columnas if re.fullmatch(r"\dT\d\d", c)], "queda un rótulo de trimestre natural")

    @pytest.mark.regresion("R2")
    def test_sga_en_una_linea(self):
        """R2. Qualcomm publica ventas, generales y administrativos en una línea; salían dos filas vacías de Netflix."""
        sga = [round(self._valor("sga", p) / 1e6) for p in self.anuales[-3:]]
        self.assertEqual(sga, [2_483, 2_759, 3_110])
        cuadro = informe._cuadro_resultados(informe.Cuadros(), self.hechos, self.tab, self.anuales, self.trimestres)
        rotulos = [f.rotulo for f in cuadro.filas]
        self.assertIn("Ventas, generales y administrativos", rotulos)
        self.assertNotIn("Ventas y marketing", rotulos)
        self.assertNotIn("Generales y administrativos", rotulos)

    @pytest.mark.regresion("R5")
    def test_amortizacion_trimestral_y_multiplos_ttm(self):
        """R5. La amortización del 2T y 3T del ejercicio abierto salía N/A (no había 10-K de ese ejercicio con que restar
        acumulados) y con ella el EBITDA TTM, el EV/EBITDA y el PER."""
        for p in self.trimestres:
            self.assertIsNotNone(self._valor("amortizacion", p), f"amortización N/A en {p.clave}")
            self.assertIsNotNone(self._valor("ebitda", p), f"EBITDA N/A en {p.clave}")
        precio = de_valor("precio", Periodo.instante(date(2026, 9, 22)), 198.27, Capa.SEC, Origen(documento="Nasdaq"), unidad="USD/acción")
        m = multiplos.construir(self.hechos, self.trimestres, self.anuales, precio, 1_050_000_000, None, self.facts, self.obtenido)
        for rotulo in ("EBITDA TTM (M USD)", "PER (TTM)", "EV / EBITDA (TTM)", "P / FCF (TTM)"):
            linea = m.linea(rotulo)
            self.assertIsNotNone(linea and linea.valor, f"{rotulo} N/A: {linea.motivo if linea else 'sin línea'}")

    @pytest.mark.regresion("R6")
    def test_sin_filas_ni_notas_de_netflix(self):
        """R6. El balance de Qualcomm arrastraba «Activos de contenido» y la nota del split 10:1 de Netflix."""
        cuadro = informe._cuadro_balance(informe.Cuadros(), self.hechos, self.tab, self.anuales, self.trimestres)
        self.assertNotIn("Activos de contenido, neto", [f.rotulo for f in cuadro.filas])
        self.assertFalse([n for n in cuadro.notas if "split" in n])
        flujo = informe._cuadro_flujo(informe.Cuadros(), self.hechos, self.tab, self.anuales, self.trimestres)
        self.assertFalse([n for n in flujo.notas if "never declared" in n or "cero declarado" in n])

    @pytest.mark.regresion("R7")
    def test_auditor_de_la_sec(self):
        """R7. El auditor salía «Cristiano R. Amon President and CEO…» (la primera firma «/s/» del PDF)."""
        self.assertEqual(self.portada.dei.get("AuditorName"), "PricewaterhouseCoopers LLP")
        self.assertEqual(self.ficha.citas["auditor"].texto, "PricewaterhouseCoopers LLP")

    @pytest.mark.regresion("R8")
    def test_free_float_de_la_sec(self):
        """R8. «Valor en manos de no afiliados» salía N/A porque se buscaba con una frase de la portada."""
        c = self.ficha.citas["float_portada"]
        self.assertEqual(c.origen.concepto, "dei:EntityPublicFloat")
        self.assertAlmostEqual(c.valor / 1e9, 167.9, delta=0.1)
        self.assertEqual(c.fecha, date(2025, 3, 28))

    @pytest.mark.regresion("R9")
    def test_fundacion_y_plantilla_propuestas(self):
        """R9. Fundación N/A mientras el apartado 4 citaba «We incorporated in California in 1985»; empleados N/A porque
        el patrón era el de Netflix («full-time employees») y Qualcomm dice «full-time, part-time and temporary workers»."""
        fun = self.ficha.citas["fundacion"]
        self.assertEqual(int(fun.valor), 1985)
        self.assertIn("incorporated in California in 1985", fun.texto)
        emp = self.ficha.citas["empleados"]
        self.assertEqual(emp.valor, 52_000)
        self.assertTrue(emp.nota.startswith("propuesta"))

    @pytest.mark.regresion("R12")
    def test_nombre_y_sede_en_espanol(self):
        """R12. El informe se titulaba «Qualcomm Inc./De» y la sede acababa en «Ca, 92121»."""
        self.assertEqual(self.ficha.nombre_presentacion, "Qualcomm Incorporated")
        self.assertEqual(self.ficha.constitucion, "Delaware (EE. UU.)")
        self.assertTrue(self.ficha.sede.endswith("CA 92121 (EE. UU.)"), self.ficha.sede)
        self.assertEqual(self.ficha.cierre_descrito, "último domingo de septiembre (ejercicio de 52/53 semanas)")


class Netflix(_ConFixtures):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.emisor = sec.emisor("NFLX")
        cls.facts, _ = sec.companyfacts(cls.emisor.cik)

    @pytest.mark.regresion("R28")
    def test_split_detectado_de_los_datos(self):
        """R28. La nota del split 10:1 estaba escrita a mano (y salía en Qualcomm). Sale de la SEC, una vez por split."""
        splits = [(f, r) for f, r, _ in sec.splits(self.facts) if f.year >= 2021]
        self.assertEqual(splits, [(date(2025, 11, 14), 10.0)])
        # el 7:1 de 2015 llega declarado en tres fechas: es un split, no tres (reexpresarlo tres veces daría 343:1)
        self.assertEqual(sum(1 for _, r, _o in sec.splits(self.facts) if r == 7.0), 1)
        tab = contraste.Tablero(resultados=[], paginas={}, resumen={}, splits=[(f, r) for f, r, _ in sec.splits(self.facts)])
        anuales = sec.calendario(self.facts, 12)[-5:]
        self.assertIn("split 10:1 del 14/11/2025", informe._nota_splits(tab, anuales))

    def test_propuestas_de_netflix_con_el_mismo_codigo(self):
        """La misma lógica que Qualcomm, sin patrones de emisor: 16.000 empleados y constitución en 1997."""
        portada = sec.portada_10k(self.emisor)
        f = ficha.construir(self.emisor, Expediente("NFLX", []), portada, self.facts)
        self.assertEqual(f.citas["empleados"].valor, 16_000)
        self.assertEqual(int(f.citas["fundacion"].valor), 1997)
        self.assertEqual(f.nombre_presentacion, "Netflix, Inc.")
        self.assertEqual(f.cierre_descrito, "31 de diciembre")


class Indice(unittest.TestCase):
    @pytest.mark.regresion("R19")
    def test_indice_del_yaml(self):
        """R19. Las letras iban G-H-F con anclas cruzadas y los títulos estaban escritos a mano en tres sitios."""
        import yaml
        datos = yaml.safe_load((RAIZ / "docs" / "spec" / "01_indice.yaml").read_text(encoding="utf-8"))
        secciones, numeros = informe._indice()
        self.assertEqual("".join(s.letra for s in secciones), "ABCDEFGHI")
        impresos = [n for s in secciones for n, _ in s.apartados]
        self.assertEqual(impresos, list(range(1, 40)))
        for s in secciones:
            self.assertEqual(s.titulo, datos["partes"][s.letra]["titulo"])
            for n, titulo in s.apartados:
                self.assertEqual(titulo, datos["apartados"][n]["titulo"])
                self.assertEqual(datos["apartados"][n]["parte"], s.letra)
        plantilla = (RAIZ / "tesis" / "plantillas" / "maqueta" / "tesis.html").read_text(encoding="utf-8")
        self.assertFalse(re.search(r'<h2 id="parte-[A-I]">[A-I]\.', plantilla), "título de parte escrito a mano")
        self.assertFalse(re.search(r"<h3 id=\"ap-[^\"]*\">[^<]*—", plantilla), "título de apartado escrito a mano")
        self.assertNotIn("penúltima", plantilla)
        # 06 §3.5: el formulario (hoy el asistente, generado desde 04) con la misma numeración: cada apartado que cita un
        # paso recibe alguna entrada de ese paso, y toda entrada que pide 01 tiene su campo en algún paso
        from tesis.entradas import asistente
        esquema = asistente.esquema()
        todos = {c["id"] for paso in esquema for c in paso["campos"]}

        def casa(e: str, ids) -> bool:
            e = e[:-2] if e.endswith(".*") else e                    # «val.*»: todo lo que cuelga de val
            return any(e == i or e.startswith(i + ".") or i.startswith(e + ".") for i in ids)
        for paso in esquema:
            m = re.search(r"\(([\d,\s–-]+)[;)]", paso["paso"])
            if not m or paso["numero"] == 2:                        # el paso 2 cita el spec 03, no apartados
                continue
            numeros = set()
            for trozo in m.group(1).split(","):
                a, _, b = trozo.strip().replace("-", "–").partition("–")
                numeros |= set(range(int(a), int(b or a) + 1))
            ids = {c["id"] for c in paso["campos"]}
            for n in sorted(numeros):
                entradas = datos["apartados"][n].get("entradas") or []
                self.assertTrue(not entradas or any(casa(e, ids) for e in entradas), (paso["paso"], n, entradas))
        for n, a in datos["apartados"].items():
            for e in a.get("entradas") or []:
                self.assertTrue(casa(e, todos), (n, e))
        self.assertEqual(indice.titulo("24"), datos["apartados"][31]["titulo"])


if __name__ == "__main__":
    unittest.main()
