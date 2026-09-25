"""Fase 3 (parte D, apartados 12–20): el motor de valoración (05). Casos de oro de 05 §10 y las regresiones R15, R22–R27
y R31. Sin red: EDGAR, Nasdaq y Tesoro congelados en `tests/fixtures/`."""

import html as html_mod
import json
import os
import re
import shutil
import tempfile
import unittest
from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest

from tesis import (calendario, contraste, derivados, entorno, entradas, ficha, gobierno, guidance, informe, multiplos, parte_b,
                   posicionamiento, precio as precio_mod, regiones, render, sec)
from tesis.expediente import Expediente
from tesis.hechos import Capa, Origen, Periodo, de_valor
from tesis.motor import datos as motor_datos, excel
from tesis.motor.escenarios import valorar
from tesis.motor.proyeccion import fraccion, proyectar
from tesis.motor.puente import puente
from tesis.motor.supuestos import Escenario, Parametros
from tesis.motor.terminal import terminal
from tesis.motor.wacc import calcular
from tesis.umbrales import _datos as umbrales

RAIZ = Path(__file__).resolve().parent.parent
F = RAIZ / "tests" / "fixtures"


def _texto(fragmento: str) -> str:
    return " ".join(html_mod.unescape(re.sub(r"<[^>]+>", " ", re.sub(r"<svg.*?</svg>", " ", fragmento, flags=re.S))).split())


def _escenario(nombre="base", p=1.0, g=0.02, margen=0.2, crec=0.0, n=5) -> Escenario:
    return Escenario(nombre, p, "", [crec] * n, [margen] * n, [0.25] * n, [0.05] * n, [0.05] * n, 0.0, [0.0] * n, g=g)


class CasosDeOro(unittest.TestCase):
    def test_1_empresa_sintetica_a_mano(self):
        """Ingresos 1.000, margen 20 %, impuesto 25 %, D&A = capex, sin deuda, 5 años, WACC 10 %, g 2 %, Gordon."""
        pr = proyectar(1000, _escenario(), 0.10, date(2025, 12, 31), date(2025, 12, 31), mitad_de_anio=False)
        tv = terminal(pr.nopat[-1], pr.fcff[-1], pr.ebitda[-1], 0.10, 0.02, None, None, pr.fraccion, 5, "gordon", 0.045, 0.04, 0.02, 3)
        mano = sum(150 / 1.1 ** k for k in range(1, 6)) + 150 * 1.02 / 0.08 / 1.1 ** 5
        self.assertAlmostEqual(pr.suma_valor_actual + tv.valor_actual, mano, delta=0.01)

    def test_2_periodo_parcial(self):
        """A tres meses del cierre, el año 1 cuenta al 25 %."""
        f = fraccion(date(2026, 10, 1), date(2025, 12, 31), date(2026, 12, 31))
        self.assertAlmostEqual(f, 0.25, delta=0.005)
        pr = proyectar(1000, _escenario(), 0.10, date(2026, 10, 1), date(2025, 12, 31), mitad_de_anio=False)
        self.assertAlmostEqual(pr.valor_actual[0], pr.fcff[0] * f * 1.1 ** -f, places=6)

    def test_3_g_pegado_al_wacc_bloquea(self):
        tv = terminal(100, 100, 120, 0.10, 0.09, None, None, 1.0, 5, "gordon", 0.12, 0.10, 0.02, 3)
        self.assertTrue(any("WACC − g" in b for b in tv.bloqueos))

    def test_4_escenarios_desordenados_bloquean(self):
        p = Parametros(fecha_valoracion=date(2025, 12, 31), periodo=5, mitad_de_anio=False, tv_metodo="gordon")
        p.escenarios = {"pesimista": _escenario("pesimista", 0.25, margen=0.30), "base": _escenario("base", 0.5, margen=0.20),
                        "optimista": _escenario("optimista", 0.25, margen=0.25)}
        w = calcular(0.045, date(2025, 12, 31), 1.0, "prueba", 0.055, 0.0, 0.05, "prueba", 0.21, 1000, 0)
        pte = puente(0.0, None, 0.0, 0.0, None, [], False, 10.0, "prueba", None, "prueba")
        v = valorar(p, w, pte, 50.0, 1000, date(2025, 12, 31), umbrales())
        self.assertTrue(any("desordenados" in b for b in v.bloqueos))


class _Informes(unittest.TestCase):
    """Los informes de control de QCOM (23/09/2026) y NFLX (17/09/2026) con las entradas de prueba."""
    T, HOY = "", None

    @classmethod
    def setUpClass(cls):
        cls._env, cls._raiz, cls._cache = dict(os.environ), entorno.RAIZ, sec.CACHE
        cls._bolsa = (precio_mod.CACHE_BOLSA, precio_mod.SOLO_CACHE)
        os.environ["WC_SEC_CONTACTO"], os.environ["WC_PRECIO_FUENTE"] = "", "nasdaq"
        entorno.RAIZ, sec.CACHE = F, F / "cache_sec"
        precio_mod.CACHE_BOLSA, precio_mod.SOLO_CACHE = F / "cache_bolsa", True
        T, hoy = cls.T, cls.HOY
        e = sec.emisor(T)
        facts, obt = sec.companyfacts(e.cik)
        exp = Expediente(T, [])
        per = contraste.periodos_del_informe(exp, facts=facts, hasta=hoy)
        tab = contraste.contrastar(exp, facts, obt, per)
        hechos = derivados.calcular(tab.hechos(), per["anuales"] + per["trimestres"], per["instantes"])
        portada = sec.portada_10k(e)
        fi = ficha.construir(e, exp, portada, facts)
        cls.ent = entradas.cargar(T, ruta=getattr(cls, "RUTA_ENTRADAS", None) or F / T / "entradas.json")
        div, _ = calendario.dividendos(T)
        acc = fi.citas["acciones_portada"].valor
        cls.motor = motor_datos.ejecutar(e, facts, hechos, per, cls.ent.datos, hoy, acc, umbrales(), tab.desfase_fiscal, div)
        m = cls.motor
        m.consenso = precio_mod.consenso_nasdaq(T)
        precio = de_valor("precio", Periodo.instante(m.fecha_precio), m.precio, Capa.SEC, Origen(documento="Nasdaq"), unidad="USD/acción",
                          nota=f"cierre oficial de Nasdaq del {m.fecha_precio:%d/%m/%Y}")
        mult = multiplos.construir(hechos, per["trimestres"], per["anuales"], precio, acc, None, facts, obt, no_aplican=tab.no_aplican)
        g = gobierno.construir(exp, None, e)
        pb = parte_b.construir(e, hoy, facts, portada, cls.ent, g)
        cls.pb, cls.hechos, cls.anuales = pb, hechos, per["anuales"]         # F4 reconstruye la parte E con otras entradas
        x = cls.ent.datos.get("excel")
        cls.libro = excel.importar(RAIZ / x["archivo"], x.get("mapa"), RAIZ / x["recalculado"]) if x else None
        splits = [f for f, _, _ in sec.splits(facts)]
        posi = posicionamiento.construir(T, split_desde=max(splits) if splits else None)          # parte H: la bolsa, en caché
        cls.inf = informe.construir(T, hoy, e, exp, tab, per, fi, g, guidance.construir(exp, e.depositos, hoy), regiones.construir(exp, tab),
                                    precio, {}, multiplos=mult, proxima=calendario.proxima(T, None, hoy), parte_b=pb, motor=m, libro=cls.libro,
                                    posicionamiento=posi)
        cls.html = render.a_html(cls.inf)

    @classmethod
    def tearDownClass(cls):
        entorno.RAIZ, sec.CACHE = cls._raiz, cls._cache
        precio_mod.CACHE_BOLSA, precio_mod.SOLO_CACHE = cls._bolsa
        os.environ.clear()
        os.environ.update(cls._env)

    def _parte(self, desde: str, hasta: str) -> str:
        i = self.html.index(desde)
        return _texto(self.html[i:self.html.index(hasta, i)])

    def _portada(self) -> str:
        return self._parte("PORTADA", "<!-- ============================== A")


class Netflix(_Informes):
    T, HOY = "NFLX", date(2026, 9, 17)

    @pytest.mark.regresion("R25")
    def test_un_solo_precio(self):
        """R25. El informe de NFLX mezclaba 80,32 (precio que el analista tecleó en su libro, del 14/09) con la cotización:
        ahora 75,31, el cierre oficial del 17/09/2026, en portada, 12–20 y G; el 80,32 solo en la comparación con el libro."""
        self.assertEqual((self.motor.precio, self.motor.fecha_precio), (75.31, date(2026, 9, 17)))
        self.assertIn("75,31 USD", self._portada())
        d = self._parte('id="parte-D"', "<!-- ============================== E")
        self.assertIn("75,31 USD", d)
        sin_comparacion = d.split("Motor frente al libro del analista")[0] + d.split("Fuente: libro del analista")[-1]
        self.assertNotIn("80,32", sin_comparacion)
        self.assertIn("80,32", d)

    @pytest.mark.regresion("R24")
    def test_deuda_neta_del_balance(self):
        """R24. El puente restaba 7.527 M (deuda con arrendamientos del libro). Ahora 14.309 − 9.128 = 5.181 M a 30/06/2026,
        arrendamientos fuera; los 7.527 solo en la comparación."""
        pte = self.motor.valoracion.puente
        self.assertEqual(round(pte.deuda_neta / 1e6), 5_181)
        self.assertEqual(pte.fecha_balance, date(2026, 6, 30))
        self.assertFalse([l for l in pte.lineas if l.rotulo.startswith("Arrendamientos")])
        fila = next(f for f in self.inf.parte_d.cuadros["libro"].filas if f.rotulo == "Deuda neta")
        self.assertEqual((fila.celdas[0].texto, fila.celdas[1].texto), ("7.527", "5.181"))

    @pytest.mark.regresion("R27")
    def test_periodo_parcial(self):
        """R27. El libro contaba 2026 entero con la caja de junio ya en el balance (doble cómputo). Ahora ≈ 105/365."""
        r = self.motor.valoracion.base
        self.assertAlmostEqual(r.proyeccion.fraccion, 105 / 365, places=4)
        self.assertAlmostEqual(r.proyeccion.valor_actual[0], r.proyeccion.fcff[0] * r.proyeccion.fraccion * r.proyeccion.factores[0], places=2)

    @pytest.mark.regresion("R26")
    def test_un_solo_precio_objetivo(self):
        """R26. El PO era la media de DCF, múltiplos y consenso. Ahora uno: Σ p·V_h del motor; el consenso solo contrasta."""
        v = self.motor.valoracion
        self.assertAlmostEqual(v.po, sum(r.escenario.probabilidad * r.vh for r in v.resultados.values()), places=9)
        self.assertEqual(self.inf.objetivo_portada[1], v.po)
        self.assertIn("88,71 USD", self._portada())
        self.assertNotIn("90,00 USD", self._portada())
        self.assertIsNotNone(self.inf.parte_d.cuadros.get("consenso"))

    @pytest.mark.regresion("R23")
    def test_libro_por_mapa_de_celdas(self):
        """R23. El libro se leía por rótulo y salía un WACC de 0. Ahora por mapa de celdas (sin mapa no se lee nada),
        ningún WACC = 0 y un cuadro de diferencias motor/libro."""
        self.assertEqual((self.libro["wacc_pes"], self.libro["wacc_base"], self.libro["wacc_opt"]), (0.105, 0.095, 0.09))
        self.assertEqual(excel.importar(RAIZ / self.ent.datos["excel"]["archivo"], None, RAIZ / self.ent.datos["excel"]["recalculado"]), {})
        self.assertTrue(all(r.wacc > 0.05 for r in self.motor.valoracion.resultados.values()))
        filas = {f.rotulo: f for f in self.inf.parte_d.cuadros["libro"].filas}
        self.assertEqual(filas["WACC (base)"].celdas[0].texto, "9,50 %")
        self.assertNotIn("0,00 %", filas["WACC (base)"].celdas[1].texto)

    @pytest.mark.regresion("R31")
    def test_horizonte_unico(self):
        """R31. El PO se llevaba a un horizonte distinto del de la posición. Ahora a val.horizonte_meses (24) y G lo repite."""
        v = self.motor.valoracion
        b = v.base
        self.assertAlmostEqual(b.vh, b.v0 * (1 + v.wacc.ke) ** 2 - v.dpa_horizonte, places=9)
        self.assertIn("Precio objetivo a 24 meses", self._parte('id="parte-D"', "<!-- ============================== E"))
        self.assertIn("24 meses", self._portada())

    def test_5_cuadros_12_a_20_completos(self):
        d = self.inf.parte_d
        for clave in ("escenarios", "wacc", "puente", "entradas", "supuestos", "sensibilidad", "multiplos_sec", "ntm", "historico",
                      "comparables", "inverso", "objetivo"):
            self.assertIn(clave, d.cuadros, clave)
        self.assertEqual([n for n, _, _ in d.escenarios], ["pesimista", "base", "optimista"])
        self.assertFalse(d.bloqueos, d.bloqueos)


class Qualcomm(_Informes):
    T, HOY = "QCOM", date(2026, 9, 23)

    @pytest.mark.regresion("R22")
    def test_precio_unico_cierre_oficial(self):
        """R22. Precio único: el cierre oficial de Nasdaq de la fecha de valoración (22/09/2026, 198,27) en portada, 12–20
        y G; nunca el intradía."""
        self.assertEqual((self.motor.precio, self.motor.fecha_precio), (198.27, date(2026, 9, 22)))
        self.assertIn("198,27 USD", self._portada())
        d = self._parte('id="parte-D"', "<!-- ============================== E")
        self.assertIn("cierre oficial de Nasdaq del 22/09/2026", d)
        self.assertEqual(self.inf.precio.valor, 198.27)

    @pytest.mark.regresion("R15")
    def test_comparables_del_analista(self):
        """R15. Los comparables eran la industria que asigna la bolsa. Ahora solo los del analista; NOK y ERIC (cuentas en
        EUR y SEK) fuera de medianas y marcados."""
        c = {x.ticker: x for x in self.motor.comparables.filas}
        self.assertEqual(set(c), {"AVGO", "TXN", "NXPI", "MRVL", "NOK", "ERIC"})
        self.assertIn("EUR", c["NOK"].excluido)
        self.assertIn("SEK", c["ERIC"].excluido)
        usados = [x for x in c.values() if not x.excluido]
        self.assertEqual({x.ticker for x in usados}, {"AVGO", "TXN", "NXPI", "MRVL"})
        import statistics
        pers = [x.valores["per"] for x in usados if x.valores.get("per") and x.valores["per"] > 0 and "per" not in x.atipicos]
        self.assertAlmostEqual(self.motor.comparables.medianas["per"], statistics.median(pers), places=9)
        rotulos = [f.rotulo for f in self.inf.parte_d.cuadros["comparables"].filas]
        self.assertIn("NOK · NOKIA CORP (excluido)", rotulos)

    def test_antiguedad_de_las_cuentas(self):
        from tesis.motor import comparables
        r = comparables.construir([{"ticker": "NXPI"}], date(2026, 9, 22), dict(umbrales(), comparables_antiguedad_max_meses=3))
        self.assertIn("más de 3 meses", r.filas[0].excluido)

    def test_5_sin_wacc_cero_y_cuadros(self):
        v = self.motor.valoracion
        self.assertTrue(all(r.wacc > 0.05 for r in v.resultados.values()))
        self.assertFalse(self.inf.parte_d.bloqueos, self.inf.parte_d.bloqueos)
        self.assertEqual(len(self.inf.parte_d.escenarios), 3)

    @unittest.skipUnless(shutil.which("soffice") or shutil.which("libreoffice") or os.name == "nt", "sin Excel ni LibreOffice")
    def test_6_exportar_y_recalcular(self):
        """El libro exportado, recalculado por una hoja de cálculo, da lo mismo que el motor ± 0,01."""
        v = self.motor.valoracion
        with tempfile.TemporaryDirectory() as d:
            ruta = excel.exportar(v, self.motor.ingresos_base, Path(d) / "motor.xlsx", umbrales())
            rec = excel.recalcular(ruta, Path(d) / "motor.recalculado.xlsx")
            self.assertIsNotNone(rec)
            x = excel.importar(ruta, recalculado=rec)
        for corto, nombre in (("pes", "pesimista"), ("base", "base"), ("opt", "optimista")):
            self.assertAlmostEqual(x[f"valor_accion_{corto}"], v.resultados[nombre].v0, delta=0.01)
        self.assertAlmostEqual(x["po"], v.po, delta=0.01)


if __name__ == "__main__":
    unittest.main()
