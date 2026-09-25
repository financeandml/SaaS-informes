"""Fase 7 (partes A, H e I, linter, puerta de calidad y render paginado): regresiones R20, R29, R32 y R33 y la
aceptación de QCOM (emitible salvo por ser entradas de prueba). Sin red: EDGAR, Nasdaq, Tesoro y Yahoo congelados en
`tests/fixtures/`; el PDF lo imprime el Chromium de Playwright."""

import json
import os
import re
import shutil
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

import pytest

from tesis.entradas import asistente
from tesis.verificacion import contraste
from tesis.datos import derivados
from tesis.plantillas import informe
from tesis.qa import linter
from tesis.fuentes import precio as precio_mod, sec
from tesis import qa, render, rotulos
from tesis.datos.expediente import Expediente
from tesis.umbrales import umbral
from tests.prueba_f3 import _Informes

F = Path(__file__).resolve().parent / "fixtures"
PRUEBA = "Parte B · entradas de PRUEBA (fixture), no del analista: no se puede emitir con ellas"
_INGLES_MILES = re.compile(r"\d{1,3}(?:,\d{3}){2,}")          # «82,839,000»: miles a la inglesa


class _Emitido(_Informes):
    """El informe pasado por la emisión entera (06 §3–§4): puerta, hoja 0, PDF y reflujo de las páginas casi vacías."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.tmp = tempfile.mkdtemp()
        cls.pdf = Path(cls.tmp) / f"{cls.T}.pdf"
        cls.puerta, cls.huella, cls.final, cls.medidas = render.emitir(cls.inf, cls.pdf, cls.HOY, prueba=cls.ent.de_prueba)
        cls.ap = qa.apartados(cls.final)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)
        super().tearDownClass()

    def _titulo(self, clave: str) -> str:
        return f"{self.inf.numeros[clave]}. {self.inf.titulos[clave][:24]}"

    def _r20(self):
        """Sin texto técnico en el cuerpo; 38 (clave 39 del índice) en una página como máximo; ninguna página por
        debajo de `relleno_pagina_min` salvo la última de una parte."""
        self.assertEqual(qa.texto_tecnico(self.final), [])
        extension = qa.extension(self.pdf, self._titulo("39"), self._titulo("40"))
        self.assertIsNotNone(extension, "no se encuentran los títulos de 38 y 39 en el PDF")
        self.assertLessEqual(extension, 1.0, "el apartado 38 ocupa más de una página")
        minimo = float(umbral("relleno_pagina_min"))
        self.assertEqual([(k, f) for k, f, fin in self.medidas if f < minimo and not fin], [])


class QualcommEmision(_Emitido):
    T, HOY = "QCOM", date(2026, 9, 23)

    @pytest.mark.regresion("R20")
    def test_r20_cuerpo_limpio_38_en_una_pagina_y_sin_paginas_casi_vacias(self):
        """R20. Falla si una ruta, una etiqueta XBRL, una URL o un mensaje de error llega al cuerpo, si 38 pasa de una
        página o si una página se queda por debajo del 25 % sin ser fin de parte."""
        self._r20()

    def test_puerta_solo_bloquea_por_ser_entradas_de_prueba(self):
        """Falla si QCOM tiene algún bloqueo aparte de ser entradas de prueba, si un borrador sale «EMITIDO» o si le
        falta la hoja 0 con sus bloqueos."""
        self.assertEqual(self.puerta.bloqueos, [PRUEBA])
        self.assertIsNone(self.inf.emitido)
        hoja0 = self.final[:self.final.index("PORTADA")]
        self.assertTrue("BORRADOR — NO EMITIDO" in hoja0 and "entradas de PRUEBA" in hoja0, "sin hoja 0 con sus bloqueos")
        paginas = qa.paginas_de(self.pdf)
        self.assertTrue(all("BORRADOR — NO EMITIDO" in p for p in paginas[1:]), "la cabecera del PDF no marca el borrador")
        self.assertFalse(any("EMITIDO 23/09/2026" in p for p in paginas))

    def test_39_apartados_sin_na_obligatorio_ni_rotulos_sin_traducir(self):
        """Falla si falta un apartado, si hay «N/A» en la portada o en 2, 3, 12–20 o 27–30, si un rótulo de la bolsa
        queda en inglés o si una cifra sale con los miles a la inglesa o con el guion como signo menos."""
        self.assertEqual(sorted(int(k) for k in self.ap if k.isdigit()), list(range(1, 40)))
        for k in sorted(qa._SIN_NA | {"portada"}):
            self.assertNotRegex(self.ap[k], r"\bN/A\b", f"apartado {k}")
        self.assertFalse([a for a in self.puerta.avisos if a.startswith("Rótulo de la bolsa sin traducir")])
        for k, texto in self.ap.items():                       # regla 6: Yahoo solo para la volatilidad implícita
            for m in re.finditer(r"Yahoo|agregador", texto):
                cerca = texto[max(0, m.start() - 200):m.end() + 200]
                self.assertRegex(cerca, r"volatilidad implícita|\bVI\b", f"apartado {k}: «{texto[max(0, m.start() - 60):m.end() + 60]}»")
        for k, texto in self.ap.items():
            self.assertIsNone(_INGLES_MILES.search(texto), f"apartado {k}")
            self.assertIsNone(re.search(r"(?<![\w\d/])-\d{1,3}(?:\.\d{3})*(?:,\d+)?\b(?!-)", texto), f"apartado {k}: signo menos con guion")

    def test_parte_a_textos_factual_citado_y_cinco_pilares(self):
        """Falla si el resumen no lleva los textos del analista y un párrafo factual con una cita por frase, o si un
        pilar sale sin sus dos evidencias, su KPI o el riesgo del Item 1A con su página."""
        a = self.inf.parte_a
        self.assertTrue(a.resumen and a.por_que_ahora and a.vision)
        self.assertGreaterEqual(len(a.factual), 3)
        self.assertTrue(all(cita for _, cita in a.factual))
        self.assertEqual(len(a.pilares), 5)
        for p in a.pilares:
            self.assertGreaterEqual(len(p.evidencias), 2, p.titulo)
            self.assertTrue(p.kpi and p.riesgo_es, p.titulo)
            self.assertRegex(p.riesgo_ref, r"Item 1A, pág\. \d+", p.titulo)
        self.assertIn(" ".join(a.resumen.split())[:80], self.ap["2"])
        self.assertEqual(len(re.findall(r"Item 1A, pág\. \d+", self.ap["3"])), 5)

    def test_parte_h_un_ratio_por_vencimiento_y_13f_antiguos_marcados(self):
        """Falla si la IV repite el ratio put/call de la cadena o si un 13F de más de un trimestre de antigüedad sale
        sin marcar."""
        iv, cadena = self.inf.f_cuadros["iv"], self.inf.f_cuadros["cadena"]
        self.assertFalse([c for c in iv.columnas if c.startswith("Put/Call")])
        self.assertEqual(iv.columnas[-1], "Interés abierto cuadra con la bolsa")
        self.assertEqual([c for c in cadena.columnas if c.startswith("Put/Call")], ["Put/Call vol.", "Put/Call int. abierto"])     # 01 › 31
        for c in (iv, cadena):                  # etiquetas en español (02): ni IV, ni ATM, ni OI, ni strikes, ni «LAST TRADE»
            self.assertIsNone(re.search(r"\b(?:IV|ATM|OI|[Ss]trikes?|LAST TRADE)\b", " ".join(c.columnas) + " " + c.fuente), c.titulo)
        textos = [f.celdas[0].texto for f in self.inf.f_cuadros["mayores"].filas]
        fechas = {t: date(int(t[6:10]), int(t[3:5]), int(t[:2])) for t in textos if re.match(r"\d\d/\d\d/\d{4}", t)}
        reciente = max(fechas.values())
        for t, f in fechas.items():                          # más de un trimestre (100 días) antes del 13F más reciente
            self.assertEqual("(antiguo)" in t, (reciente - f).days > 100, t)
        self.assertTrue(any("(antiguo)" in t for t in fechas), "QCOM tiene un 13F de diciembre entre los de junio")

    def test_parte_h_strikes_volatilidad_y_movimiento_en_resultados(self):
        """Falla si 31 pierde los precios de ejercicio con más interés abierto y el máximo dolor, o 32 la VI frente a la
        realizada a 30 y 90 días y el straddle del primer vencimiento tras los resultados (01 › 31–32)."""
        f = self.inf.f_cuadros
        self.assertIn("mensual del 16/10/2026", f["strikes"].titulo)                 # tercer viernes de octubre
        self.assertIn("Máximo dolor del vencimiento:", f["strikes"].fuente)
        self.assertEqual([fila.rotulo for fila in f["vi_realizada"].filas][1:3], ["Volatilidad realizada a 30 días", "Volatilidad realizada a 90 días"])
        self.assertTrue(all(c.glifo == "∑" for fila in f["vi_realizada"].filas for c in fila.celdas))
        self.assertIn("04/11/2026", f["movimiento"].titulo)
        self.assertRegex(f["movimiento"].filas[0].celdas[1].texto, r"^±\d+,\d\s%$")
        self.assertIn(f["strikes"].numero, (f["cadena"].numero + 1,))

    def test_cuadros_numerados_en_el_orden_en_que_se_leen(self):
        """Falla si un cuadro se numera fuera del orden en que aparece (un cuadro nuevo creado al final e impreso en
        medio) o si un número se repite."""
        numeros = [int(x) for x in re.findall(r"Cuadro (\d+)\.", self.final)]
        self.assertEqual(numeros, sorted(set(numeros)))
        self.assertEqual(numeros, list(range(1, len(numeros) + 1)))

    def test_parte_i_modelo_fuentes_notas_y_citas(self):
        """Falla si I pierde las entradas del modelo, la proyección completa, las fuentes con su huella, las
        definiciones o las citas literales, o si imprime registros internos (JSON, rutas)."""
        d = self.inf.parte_i
        for clave in ("entradas", "proyeccion", "documentos", "apis", "citas"):
            self.assertIn(clave, d.cuadros)
        self.assertIn("Entradas del modelo", self.ap["36"])
        self.assertIn("Proyección completa", self.ap["36"])
        self.assertRegex(self.ap["37"], r"sha256 [0-9a-f]{12}")
        self.assertTrue(d.definiciones)
        self.assertIn(" ".join(d.definiciones[0].split())[:40], self.ap["38"])          # 06 §5
        self.assertLessEqual(len(d.huecos), 15)
        self.assertIn("Citas literales", self.ap["39"])
        self.assertNotRegex(self.ap["38"], r"[{}\[\]]")


class QualcommSinMarcaDePrueba(_Informes):
    """Las mismas entradas sin la marca «_prueba»: lo que queda es lo que vería el analista con las suyas."""
    T, HOY = "QCOM", date(2026, 9, 23)

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        datos = json.loads((F / "QCOM" / "entradas.json").read_text(encoding="utf-8"))
        datos.pop("_prueba", None)
        cls.RUTA_ENTRADAS = Path(cls.tmp) / "entradas.json"
        cls.RUTA_ENTRADAS.write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_emitible_con_cero_bloqueos(self):
        """F7 › Aceptación: QCOM emitible con las entradas de prueba (0 bloqueos) una vez quitada la marca de prueba."""
        puerta = qa.revisar(self.inf, self.html, self.HOY)
        self.assertEqual(puerta.bloqueos, [])
        self.assertTrue(puerta.emitible)


class NetflixCuadres(_Emitido):
    T, HOY = "NFLX", date(2026, 9, 17)

    @pytest.mark.regresion("R29")
    def test_r29_cuadres_de_38_en_formato_espanol(self):
        """R29. Falla si el cuadre de 2023 (streaming 33.640 frente a 33.723 M USD del consolidado) sale en 38 con
        los miles a la inglesa o sin separador, o si 38 lista como huecos partidas que Netflix no tiene."""
        t = self.ap["38"]
        self.assertIn("33.640", t)
        self.assertIn("33.723", t)
        for mal in ("33,640", "33640", "33,723", "33723"):
            self.assertNotIn(mal, t)
        self.assertIsNone(_INGLES_MILES.search(t))
        self.assertNotIn("no es una línea de sus cuentas", t)            # regla 10: no es un hueco
        self.assertIn("No son huecos", t)

    @pytest.mark.regresion("R20")
    def test_r20_netflix_con_la_iv_caida(self):
        """R20 con una fuente caída (Yahoo sin respuesta guardada): el motivo se dice en español, sin URL ni error."""
        self.assertIn("sin conexión y sin copia guardada", self.ap["32"])
        self._r20()


class Asistente(unittest.TestCase):
    """El asistente con EDGAR y la bolsa congelados y WC_DATOS en una carpeta temporal."""

    @classmethod
    def setUpClass(cls):
        cls._env, cls._cache = dict(os.environ), sec.CACHE
        cls._bolsa = (precio_mod.CACHE_BOLSA, precio_mod.SOLO_CACHE)
        cls.tmp = tempfile.mkdtemp()
        os.environ["WC_DATOS"], os.environ["WC_SEC_CONTACTO"] = cls.tmp, ""
        sec.CACHE = F / "cache_sec"
        precio_mod.CACHE_BOLSA, precio_mod.SOLO_CACHE = F / "cache_bolsa", True

    @classmethod
    def tearDownClass(cls):
        sec.CACHE = cls._cache
        precio_mod.CACHE_BOLSA, precio_mod.SOLO_CACHE = cls._bolsa
        os.environ.clear()
        os.environ.update(cls._env)
        shutil.rmtree(cls.tmp, ignore_errors=True)

    @pytest.mark.regresion("R32")
    def test_r32_financiera_bloqueada_en_el_paso_1(self):
        """R32. Falla si JPM (SIC 6021, banco) pasa el paso 1 sin el bloqueo v1 y su motivo."""
        datos, _ = asistente.cargar("JPM", date(2026, 9, 23))
        faltas, _ = asistente.validar("JPM", date(2026, 9, 23), datos)
        self.assertTrue(faltas[1][0].startswith("meta.sector: bloqueo v1 — "), faltas[1])
        self.assertIn("bancos", faltas[1][0])
        faltas, _ = asistente.validar("QCOM", date(2026, 9, 23), datos)               # una no financiera no se bloquea
        self.assertFalse(any("bloqueo v1" in f for f in faltas[1]))

    def test_el_linter_avisa_mientras_se_escribe(self):
        """Falla si el paso 3 acepta un resumen con tono comercial, en inglés o con una cifra sin unidad."""
        datos = {"tesis": {"resumen": {"texto": "The company and its growth are claramente increíbles; los ingresos crecieron un 12."}}}
        faltas = " | ".join(asistente.validar("QCOM", date(2026, 9, 23), datos)[0][3])
        self.assertIn("palabra vetada «claramente»", faltas)
        self.assertIn("palabra vetada «increíble»", faltas)
        self.assertIn("texto en inglés", faltas)
        self.assertIn("cifra sin unidad «12»", faltas)


class CierreEnEnero(unittest.TestCase):
    """WMT cierra su ejercicio el 31 de enero: su 4T es noviembre–enero y su ejercicio 2026 acaba en enero de 2026."""

    @classmethod
    def setUpClass(cls):
        cls._env, cls._cache = dict(os.environ), sec.CACHE
        os.environ["WC_SEC_CONTACTO"] = ""
        sec.CACHE = F / "cache_sec"
        e = sec.emisor("WMT")
        facts, obt = sec.companyfacts(e.cik)
        exp = Expediente("WMT", [])
        cls.per = contraste.periodos_del_informe(exp, facts=facts, hasta=date(2026, 9, 23))
        cls.tab = contraste.contrastar(exp, facts, obt, cls.per)
        cls.hechos = derivados.calcular(cls.tab.hechos(), cls.per["anuales"] + cls.per["trimestres"], cls.per["instantes"])

    @classmethod
    def tearDownClass(cls):
        sec.CACHE = cls._cache
        os.environ.clear()
        os.environ.update(cls._env)

    def _etiqueta(self, p) -> str:
        return informe._etiqueta(p, self.per["anuales"], self.tab)

    @pytest.mark.regresion("R33")
    def test_r33_etiquetas_fiscales_y_4t_derivado(self):
        """R33. Falla si el trimestre agosto–octubre de 2025 no es el 3T FY26 (o el 4T FY26 el de noviembre–enero), si el
        ejercicio que acaba en enero de 2026 no es el 2026 o si el 4T no es exactamente el ejercicio menos sus nueve meses."""
        self.assertEqual([self._etiqueta(p) for p in self.per["trimestres"]], ["3T FY26", "4T FY26", "1T FY27", "2T FY27"])
        self.assertEqual(self._etiqueta(self.per["anuales"][-1]), "2026")
        q4 = next(p for p in self.per["trimestres"] if self._etiqueta(p) == "4T FY26")
        self.assertEqual((q4.inicio, q4.fin), (date(2025, 11, 1), date(2026, 1, 31)))
        h = self.hechos[("ingresos", q4)]
        ejercicio, nueve = sorted(h.entradas, key=lambda x: -x.periodo.meses)
        self.assertEqual((ejercicio.periodo.meses, nueve.periodo.meses), (12, 9))
        self.assertEqual(ejercicio.periodo.fin, q4.fin)
        self.assertEqual(nueve.periodo.fin, q4.inicio - timedelta(days=1))
        self.assertEqual(h.valor, ejercicio.valor - nueve.valor)
        self.assertEqual((ejercicio.valor, h.valor), (713_163e6, 190_656e6))        # 10-K FY2026 − 10-Q de octubre
        self.assertEqual(h.formula, "FY2026 − 9M26")


class Linter(unittest.TestCase):
    VALORES = [8.9e9, 0.334, 195.0, 7.2]

    def test_cifras_con_unidad_casan_con_hechos_o_evidencias(self):
        """Falla si una cifra que no es un Hecho ni está en una evidencia pasa, o si una que sí lo es se rechaza."""
        self.assertEqual(linter.revisar("Ingresos de 8.900 M USD, margen del 33,4 %, PER de 7,2x y precio de 195,00 USD.", self.VALORES), [])
        reparos = linter.revisar("Los ingresos llegarán a 9.400 M USD.", self.VALORES)
        self.assertEqual(len(reparos), 1)
        self.assertIn("cifra sin respaldo «9.400 M USD»", reparos[0])
        self.assertEqual(linter.revisar("Los ingresos llegarán a 9.400 M USD.", self.VALORES, ["revenue of $9.4 billion"]), [])

    def test_referencias_fechas_y_rotulos_no_son_cifras(self):
        texto = ("Según el apartado 18 (pág. 23) del 10-K de 2025, el 23/09/2026 y en el 3T FY26, con 5 pilares, "
                 "el S&P 500 y el Snapdragon 8 Elite; entre 10 y 12 % del mercado.")
        self.assertEqual([r for r in linter.revisar(texto, None) if "sin unidad" in r], [])

    def test_formatos_ingleses_y_marcas_prohibidas(self):
        reparos = " | ".join(linter.revisar("Crecen un 12.5 % hasta 33,640 M USD; N/A y pendiente.", None))
        for esperado in ("formato inglés «12.5»", "formato inglés «33,640»", "«N/A»", "«pendiente»"):
            self.assertIn(esperado, reparos)
        self.assertEqual(linter.revisar("La compañía cita «The Walt Disney Company» y “Game of Thrones”.", None), [])

    def test_candidatos_incluyen_variaciones_del_periodo_anterior(self):
        from tesis.datos.hechos import Capa, Estado, Hecho, Periodo
        a, b = Periodo.de_meses(date(2024, 12, 31), 12), Periodo.de_meses(date(2025, 12, 31), 12)
        hechos = {("ingresos", a): Hecho("ingresos", a, 100e6, Estado.VALOR, Capa.SEC), ("ingresos", b): Hecho("ingresos", b, 112e6, Estado.VALOR, Capa.SEC)}
        self.assertEqual(linter.revisar("Los ingresos crecieron un 12 % hasta 112 M USD.", linter.candidatos(hechos)), [])
        self.assertEqual(len(linter.revisar("Los ingresos crecieron un 15 %.", linter.candidatos(hechos))), 1)


class CalculosDeLaParteH(unittest.TestCase):
    """Los cálculos sobre la cadena, con una cadena sintética y las cuentas hechas a mano."""

    def setUp(self):
        from tesis.fuentes.posicionamiento import Strike
        # interés abierto (calls, puts): 90 → (10, 100) · 100 → (50, 50) · 110 → (200, 10)
        self.strikes = [Strike(90.0, 10, 100, 12.0, 0.5), Strike(100.0, 50, 50, 4.0, 3.0), Strike(110.0, 200, 10, 0.6, 11.0)]

    def test_maximo_dolor_a_mano(self):
        """A 90: puts 50×10 + 10×20 = 700; a 100: call 10×10 + put 10×10 = 200; a 110: calls 10×20 + 50×10 = 700 → 100
        (con las calls pagando como puts saldría 110: el extremo)."""
        from tesis.plantillas import parte_h
        self.assertEqual(parte_h.max_dolor(self.strikes), 100.0)
        self.assertEqual([s.precio for s in parte_h.mayores(self.strikes)], [110.0, 90.0, 100.0])

    def test_straddle_mensual_y_realizada(self):
        from types import SimpleNamespace as N
        from tesis.plantillas import parte_h
        from tesis.fuentes.posicionamiento import Cadena, Vencimiento
        s = parte_h.straddle(Vencimiento("October 16, 2026", None, None, None, None, 3, self.strikes), 101.0)
        self.assertEqual((s.precio, s.call + s.put), (100.0, 7.0))
        c = Cadena([Vencimiento("October 9, 2026", None, None, None, None, 3, self.strikes),
                    Vencimiento("October 16, 2026", None, None, None, None, 3, self.strikes)])
        self.assertEqual(parte_h.mensual(c, date(2026, 9, 23))[0], date(2026, 10, 16))           # el tercer viernes
        dias = [date(2026, 1, 1) + timedelta(days=k) for k in range(30)]
        sesiones = {d: N(cierre=100.0 * (1.01 if k % 2 else 1.0)) for k, d in enumerate(dias)}
        r = parte_h.vol_realizada(sesiones, dias[-1], 21)
        a = __import__("math").log(1.01)                  # 21 rendimientos: 11 de +a y 10 de −a → media a/21
        self.assertAlmostEqual(r, a * (1 - 1 / 21 ** 2) ** 0.5 * 252 ** 0.5, places=9)
        self.assertIsNone(parte_h.vol_realizada(sesiones, dias[-1], 63))                          # sin 64 cierres, nada
        self.assertEqual(parte_h.subyacente("LAST TRADE: $1,194.26 (AS OF SEP 24, 2026)"), 1194.26)


class TextoTecnico(unittest.TestCase):

    def test_identificadores_de_la_fuente_en_el_cuerpo(self):
        """Falla si la puerta deja pasar al cuerpo un miembro o un concepto XBRL, un prefijo us-gaap o una excepción."""
        for fragmento in ("el 10-Q lo etiqueta «HandsetsMember»", "no declara SellingGeneralAndAdministrativeExpense",
                          "ningún concepto us-gaap para esto", "no respondió: URLError"):
            html = f'<h3 id="ap-38">38. Notas</h3><p>{fragmento}</p>'
            self.assertTrue(qa.texto_tecnico(html), fragmento)
        self.assertEqual(qa.texto_tecnico('<h3 id="ap-38">38. Notas</h3><p>Los ingresos de Snapdragon y de QTL crecieron.</p>'), [])


class Regla6(unittest.TestCase):

    def test_el_precio_solo_sale_de_nasdaq(self):
        """Falla si `WC_PRECIO_FUENTE` admite otra fuente que el cierre oficial de Nasdaq (CLAUDE.md, reglas 4 y 6)."""
        from unittest import mock
        bolsa = (precio_mod.CACHE_BOLSA, precio_mod.SOLO_CACHE)
        precio_mod.CACHE_BOLSA, precio_mod.SOLO_CACHE = F / "cache_bolsa", True
        try:
            for fuente in ("yahoo", "polygon"):
                with mock.patch.object(precio_mod, "variable", lambda n, f=fuente: f):
                    c, h = precio_mod._cotizacion("QCOM", date(2026, 9, 23))
                self.assertIsNone(c, fuente)
                self.assertIn("no admitida", h.motivo, fuente)
        finally:
            precio_mod.CACHE_BOLSA, precio_mod.SOLO_CACHE = bolsa


class FallosDeRed(unittest.TestCase):

    def test_el_motivo_se_dice_sin_url_ni_excepcion(self):
        """Falla si el motivo de una consulta caída lleva la URL o el nombre de la excepción al cuerpo, o si el detalle
        no queda para la auditoría."""
        import urllib.error
        rotulos.FALLOS.clear()
        url = "https://query2.finance.yahoo.com/v7/finance/options/NFLX"
        casos = [(urllib.error.HTTPError(url, 429, "Too Many Requests", {}, None), "exceso de peticiones"),
                 (urllib.error.URLError(f"sin respuesta guardada de {url}"), "sin copia guardada"),
                 (ValueError("Expecting value: line 1 column 1"), "formato esperado")]
        for e, esperado in casos:
            texto = rotulos.fallo(e)
            self.assertIn(esperado, texto)
            self.assertEqual(qa._TECNICO.search(texto), None, texto)
        self.assertEqual(len(rotulos.FALLOS), 3)
        self.assertIn(url, rotulos.FALLOS[0] + rotulos.FALLOS[1])
