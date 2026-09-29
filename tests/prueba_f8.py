"""Fase 8 (cierre de fallos): la emisión de verdad —`emitir.py` de principio a fin— y lo que la puerta de calidad aún no
miraba. Sin red: EDGAR, Nasdaq, Tesoro y Yahoo congelados en `tests/fixtures/`; el 10-K y el 10-Q se imprimen a PDF desde
la copia guardada de EDGAR, como hace el paso 1 del SaaS."""

import json
import os
import re
import shutil
import tempfile
import unittest
from datetime import date
from pathlib import Path

import pytest

from tesis.entradas import asistente, propuestas
from tesis import entorno, qa
from tesis.fuentes import edgar, precio as precio_mod, sec
from tests.prueba_f3 import _Informes
from tests.prueba_f6 import _Datos

F = Path(__file__).resolve().parent / "fixtures"
PRUEBA = "Parte B · entradas de PRUEBA (fixture), no del analista: no se puede emitir con ellas"


@pytest.mark.lenta

def _sin_apartado(bloqueo: str) -> str:
    """El texto de un bloqueo sin el «Apartado N · punto ·» que le antepone el sistema por puntos (fase B)."""
    return re.sub(r"^Apartado \S+ · (?:[\d.]+(?:, [\d.]+)* · )?", "", bloqueo)

class EmisionCompleta(unittest.TestCase):
    """QCOM a 23/09/2026 por el mismo camino que el botón «Emitir» del SaaS: adjuntos traídos de EDGAR y `emitir.py`."""

    @classmethod
    def setUpClass(cls):
        cls._env, cls._raiz, cls._cache = dict(os.environ), entorno.RAIZ, sec.CACHE
        cls._bolsa = (precio_mod.CACHE_BOLSA, precio_mod.SOLO_CACHE)
        cls.tmp = Path(tempfile.mkdtemp())
        os.environ.update(WC_DATOS=str(cls.tmp), WC_SEC_CONTACTO="", WC_PRECIO_FUENTE="nasdaq")
        entorno.RAIZ, sec.CACHE = F, F / "cache_sec"
        precio_mod.CACHE_BOLSA, precio_mod.SOLO_CACHE = F / "cache_bolsa", True
        adjuntos = cls.tmp / "adjuntos" / "QCOM"
        cls.traidos = edgar.traer(sec.emisor("QCOM"), ["10K", "10Q"], adjuntos)
        import emitir
        salida = cls.tmp / "salida"
        cls.codigo = emitir.main(["QCOM", "--carpeta", str(adjuntos), "--fecha", "2026-09-23", "--entradas", str(F / "QCOM" / "entradas.json"),
                                  "--salida", str(salida)])
        base = salida / "QCOM_tesis_2026-09-23"
        cls.auditoria = json.loads(base.with_suffix(".auditoria.json").read_text(encoding="utf-8"))
        cls.html = base.with_suffix(".html").read_text(encoding="utf-8") if base.with_suffix(".html").exists() else ""
        cls.pdf = base.with_suffix(".pdf")

    @classmethod
    def tearDownClass(cls):
        entorno.RAIZ, sec.CACHE = cls._raiz, cls._cache
        precio_mod.CACHE_BOLSA, precio_mod.SOLO_CACHE = cls._bolsa
        os.environ.clear()
        os.environ.update(cls._env)
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_emitir_de_principio_a_fin_solo_bloquea_por_ser_de_prueba(self):
        """Falla si `emitir.py` se rompe por el camino, si el borrador no devuelve 1 o si el camino real añade bloqueos que
        el arnés de las pruebas no ve (el que salió: la ficha del día de la bolsa bloqueaba aunque el precio del informe
        es el cierre oficial del motor)."""
        self.assertEqual([t.estado for t in self.traidos][:2], ["traído", "traído"])
        self.assertEqual(self.codigo, 1)                                  # borrador: nunca «EMITIDO» con entradas de prueba
        self.assertEqual(self.auditoria["bloqueos"], [PRUEBA])
        self.assertIsNone(self.auditoria["emitido"])
        self.assertTrue(self.pdf.exists() and self.pdf.stat().st_size > 100_000)

    def test_el_html_emitido_pasa_la_puerta(self):
        """Falla si el HTML del camino real lleva texto técnico al cuerpo o pierde apartados."""
        self.assertTrue(self.html)
        self.assertEqual(qa.texto_tecnico(self.html), [])
        self.assertEqual(sorted(int(k) for k in qa.apartados(self.html) if k.isdigit()), list(range(1, 40)))

    def test_el_paso_1_manda_en_el_sector_y_el_nombre(self):
        """Falla si el sector y el nombre que confirma el analista en el paso 1 no llegan a la ficha (apartado 1) ni al
        cuadro de entradas del modelo (36), o si el motor sigue con el paquete que propone el SIC (3663 → industrial)."""
        self.assertIn("<td>Sector · paquete del DCF</td><td class=\"valor\">Semiconductores</td>"
                      "<td class=\"muted\">analista (paso 1); el SIC 3663 proponía «Industrial»</td>", self.html)
        self.assertIn("<td>Nombre</td><td class=\"valor\">Qualcomm</td><td class=\"muted\">analista (paso 1)</td>", self.html)
        self.assertRegex(self.html, r"Paquete sectorial</t[dh]>\s*<td[^>]*>semiconductores</td>\s*<td[^>]*>\s*</td>\s*<td[^>]*>paso 1</td>")

    def test_deja_las_propuestas_para_el_paso_9(self):
        """Falla si la emisión no deja junto al PDF las propuestas de plantilla que lee el paso 9 (06 §1) o si la auditoría
        no dice en qué estado estaba cada párrafo."""
        ruta = self.pdf.with_name("QCOM_tesis_2026-09-23.propuestas.json")
        self.assertEqual([p["id"] for p in propuestas.leer(ruta)], ["resumen_factual"])
        self.assertEqual([(p["id"], p["estado"]) for p in self.auditoria["parrafos"]], [("resumen_factual", "aceptado")])

    def test_los_valores_unicos_van_marcados_donde_se_imprimen(self):
        """Falla si precio, PO, recomendación, horizonte, capitalización o acciones diluidas dejan de llevar `data-hecho`
        en alguno de los sitios en que se imprimen (06 §3.3: portada, ficha, parte D, parte G y 36), o si la deuda neta de
        una fecha deja de compararse entre el cuadro 1, el balance y el puente."""
        claves = [m.group(2) for m in qa._DATA_HECHO.finditer(self.html)]
        for clave, veces in (("precio", 6), ("po", 2), ("recomendacion", 3), ("horizonte", 3), ("capitalizacion", 2), ("acciones_diluidas", 1)):
            self.assertGreaterEqual(claves.count(clave), veces, clave)
        self.assertTrue(any(claves.count(k) >= 3 for k in claves if k.startswith("deuda_neta@")))
        self.assertEqual(qa.valores_unicos(self.html), [])


class NetflixPuerta(_Informes):
    """NFLX a 17/09/2026 (Yahoo respondió 429 al congelar la VI, así que no hay VI)."""
    T, HOY = "NFLX", date(2026, 9, 17)

    def test_la_vi_caida_es_aviso_y_no_bloqueo(self):
        """Falla si la caída de la excepción de Yahoo bloquea la emisión (06 §3 la pone entre los avisos) o si deja de
        avisarse."""
        puerta = qa.revisar(self.inf, self.html, self.HOY)
        self.assertFalse([b for b in puerta.bloqueos if "Parte H · iv" in b], puerta.bloqueos)   # con o sin apartado delante
        self.assertTrue([a for a in puerta.avisos if a.startswith("Parte H · iv")])

    def test_sin_valores_contradictorios(self):
        """Falla si en NFLX (otra fecha de cierre y otro horizonte) un concepto marcado sale con dos valores."""
        self.assertEqual(qa.valores_unicos(self.html), [])

    def test_parrafo_de_plantilla_sin_validar_bloquea_y_se_ve_en_el_borrador(self):
        """Falla si el párrafo factual sin aceptar ni editar deja de bloquear (06 §1) o si el borrador deja de enseñarlo."""
        puerta = qa.revisar(self.inf, self.html, self.HOY)
        self.assertTrue([b for b in puerta.bloqueos if b.endswith(
            "Parte A · Párrafo factual del resumen ejecutivo: párrafo de plantilla sin aceptar ni editar (paso 9 del asistente)")],
            puerta.bloqueos)
        self.assertTrue(self.inf.parrafos and self.inf.parrafos[0].estado == "sin validar")
        self.assertIn(self.inf.parrafos[0].frases[0][0], self.html)

    def test_la_puerta_bloquea_un_horizonte_distinto_en_la_portada(self):
        """Falla si la puerta deja de mirar los valores únicos del HTML (06 §3.3): la portada con 12 meses y el resto con 24."""
        roto = self.html.replace('data-hecho="horizonte">24 meses', 'data-hecho="horizonte">12 meses', 1)
        self.assertNotEqual(roto, self.html)
        puerta = qa.revisar(self.inf, roto, self.HOY)
        self.assertTrue([b for b in puerta.bloqueos if b.startswith("Valor único: «horizonte»")], puerta.bloqueos)


class ValorUnico(unittest.TestCase):

    def test_dos_valores_del_mismo_concepto_bloquean(self):
        """Falla si un concepto que sale con dos valores (el horizonte, 12 y 24 meses) pasa, o si el mismo valor con otro
        redondeo, otra fecha u otra caja de letra se toma por distinto."""
        html = ('<p>PORTADA</p><table><tr><td data-hecho="po">110,49 USD</td></tr></table>'
                '<h3 id="ap-20">20. Precio objetivo</h3><td data-hecho="po">110,5 USD</td>'
                '<td data-hecho="deuda_neta@2026-06-28">6.966</td><td data-hecho="deuda_neta@2025-09-28">4.656</td>'
                '<b data-hecho="recomendacion">Mantener</b><span data-hecho="recomendacion">MANTENER</span>'
                '<h3 id="ap-36">36. Modelo</h3><td data-hecho="horizonte">12</td><span data-hecho="horizonte">24</span>')
        reparos = qa.valores_unicos(html)
        self.assertEqual(len(reparos), 1, reparos)
        self.assertIn("«horizonte»", reparos[0])
        self.assertIn("apartado 36", reparos[0])


PROPUESTA = [("En el 3T FY26, los ingresos fueron de 9.947 mln USD.", "8-K 29/07/2026, Ex. 99.1"),
             ("En el ejercicio 2025, la compañía facturó 44.284 mln USD.", "10-K 05/11/2025")]
TITULO = "Párrafo factual del resumen ejecutivo"


class Propuestas(unittest.TestCase):
    """06 §1: el sistema propone, el analista valida y lo validado queda congelado con la huella de la propuesta."""

    def _revision(self, frases, editado=False, huella=None):
        return {"resumen_factual": {"propuesta": huella or propuestas.huella(PROPUESTA), "frases": [list(x) for x in frases], "editado": editado}}

    def test_sin_validar_se_imprime_la_propuesta_y_bloquea(self):
        frases, p, falta = propuestas.aplicar("resumen_factual", TITULO, PROPUESTA, None)
        self.assertEqual(frases, PROPUESTA)
        self.assertEqual(p.estado, "sin validar")
        self.assertIn("sin aceptar ni editar", falta)

    def test_aceptada_o_editada_se_imprime_lo_congelado_con_la_cita_de_la_propuesta(self):
        """Falla si lo editado no se imprime, si se imprime una cita cambiada a mano en el fichero o si bloquea."""
        frases, p, falta = propuestas.aplicar("resumen_factual", TITULO, PROPUESTA, self._revision(PROPUESTA))
        self.assertEqual((frases, p.estado, falta), (PROPUESTA, "aceptado", None))
        editada = [("Los ingresos del 3T FY26 sumaron 9.947 mln USD.", "otra cita"), ("", "10-K 05/11/2025")]
        frases, p, falta = propuestas.aplicar("resumen_factual", TITULO, PROPUESTA, self._revision(editada, editado=True))
        self.assertEqual((frases, p.estado, falta), ([("Los ingresos del 3T FY26 sumaron 9.947 mln USD.", "8-K 29/07/2026, Ex. 99.1")], "editado", None))

    def test_datos_nuevos_la_vuelven_a_pedir(self):
        """Falla si un párrafo validado con otros datos (otra huella) se imprime sin volver a pedirse."""
        frases, p, falta = propuestas.aplicar("resumen_factual", TITULO, PROPUESTA, self._revision(PROPUESTA, huella="0" * 16))
        self.assertEqual((frases, p.estado), (PROPUESTA, "cambió"))
        self.assertIn("los datos cambiaron", falta)

    def test_vaciarla_entera_bloquea(self):
        _, _, falta = propuestas.aplicar("resumen_factual", TITULO, PROPUESTA, self._revision([("", c) for _, c in PROPUESTA], editado=True))
        self.assertIn("sin ninguna frase", falta)

    def test_lo_editado_pasa_el_linter(self):
        """Falla si las frases editadas no llegan al linter como textos del analista."""
        from tesis.qa import linter
        from tesis.entradas import Entradas
        e = Entradas({"revision": {"parrafos": self._revision([("Los ingresos subieron 15.000 mln USD.", "")], editado=True)}})
        self.assertEqual(linter.revisar_entradas(e, [9_947e6]),
                         ["revision.parrafos.resumen_factual[1]: cifra sin respaldo «15.000 mln USD»: no es un Hecho del informe ni está en una evidencia"])


class LinterCifras(unittest.TestCase):

    def test_una_cifra_precisa_casa_solo_con_su_redondeo(self):
        """Falla si vuelve el 1 % para toda cifra: con los más de mil Hechos candidatos de un informe, dejaba pasar más de
        la mitad de las cifras inventadas en millones. Una cifra redonda sigue casando dentro del 1 %."""
        from tesis.qa import linter
        hechos = [12_596e6, 0.279]
        for texto, pasa in (("sumó 12.596 mln USD.", True), ("sumó 12.603 mln USD.", False), ("sumó 12.600 mln USD.", True),
                            ("sumó 12.800 mln USD.", False), ("un margen del 27,9 %.", True), ("un margen del 28,2 %.", False),
                            ("un margen del 28 %.", True)):
            self.assertEqual(linter.revisar(f"La compañía {texto}", hechos) == [], pasa, texto)


class LinterEstilo(unittest.TestCase):

    def test_frases_y_parrafos_largos_avisan_sin_bloquear(self):
        """Falla si una frase desde 40 palabras o un párrafo de más de 6 frases no se avisan (02), si se avisa por debajo o
        si pasan a bloquear. «EE. UU.» no corta la frase."""
        from tesis.qa import linter
        frase = lambda n: " ".join(["palabra"] * n) + "."
        self.assertEqual(linter.avisos(frase(39)), [])
        self.assertEqual(len(linter.avisos(frase(40))), 1)
        self.assertIn("frase de 40 palabras", linter.avisos(frase(40))[0])
        self.assertEqual(linter.avisos(" ".join(["Vende en EE. UU. y Europa."] * 6)), [])
        self.assertEqual(linter.avisos(" ".join(["Vende en EE. UU. y Europa."] * 7)), ["párrafo de 7 frases (02: hasta 6)"])
        self.assertEqual(linter.revisar(frase(45) + " " + " ".join(["Otra frase."] * 8)), [])


LARGA = ("En el ejercicio 2025, la compañía facturó 44.284 mln USD, con un margen operativo del 27,9 %, sostenido por la división "
         "de semiconductores, por la venta de licencias a los fabricantes de teléfonos y por una disciplina de costes que se "
         "mantuvo a lo largo de los cuatro trimestres del ejercicio.")


class QualcommParrafoEditado(_Informes):
    """QCOM con la primera frase del párrafo factual reescrita por el analista y la última con una cifra inventada."""
    T, HOY = "QCOM", date(2026, 9, 23)
    NUEVA = "Los ingresos del 3T FY26 fueron de 9.947 mln USD, en la parte alta del rango de la guía."

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        datos = json.loads((F / "QCOM" / "entradas.json").read_text(encoding="utf-8"))
        r = datos["revision"]["parrafos"]["resumen_factual"]
        r["frases"][0][0], r["frases"][-1][0], r["editado"] = cls.NUEVA, "La retribución al accionista sumó 15.437 mln USD.", True
        r["frases"][1][0] = LARGA
        cls.RUTA_ENTRADAS = Path(cls.tmp) / "entradas.json"
        cls.RUTA_ENTRADAS.write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_se_imprime_lo_editado_y_la_cifra_inventada_bloquea(self):
        """Falla si el informe imprime la propuesta en vez de lo editado, si pierde la cita o si la cifra inventada pasa."""
        self.assertIn(f"{self.NUEVA} <span class=\"cita\">[8-K 29/07/2026, Ex. 99.1]</span>", self.html)
        self.assertEqual(self.inf.parrafos[0].estado, "editado")
        puerta = qa.revisar(self.inf, self.html, self.HOY)
        self.assertTrue([b for b in puerta.bloqueos if "Linter · revision.parrafos.resumen_factual[5]: cifra sin respaldo «15.437 mln USD»" in b],
                        puerta.bloqueos)
        self.assertFalse([b for b in puerta.bloqueos if "sin aceptar ni editar" in b])

    def test_la_frase_larga_editada_avisa_y_no_bloquea(self):
        """Falla si la frase de 50 palabras que escribió el analista no sale en los avisos de QA (02) o si bloquea."""
        puerta = qa.revisar(self.inf, self.html, self.HOY)
        self.assertTrue([a for a in puerta.avisos if a.startswith("Estilo · revision.parrafos.resumen_factual[2]: frase de 50 palabras")], puerta.avisos)
        self.assertFalse([b for b in puerta.bloqueos if "resumen_factual[2]" in b])


class AsistentePaso9(_Datos):
    """El paso 9 con las propuestas de la última generación: la validación al guardar y la página en el navegador."""
    FECHA = date(2026, 9, 23)

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        carpeta = Path(cls.tmp) / "salida" / "QCOM"
        carpeta.mkdir(parents=True)
        cls.huella = propuestas.huella(PROPUESTA)
        propuestas.escribir(carpeta / "QCOM_tesis_2026-09-23.propuestas.json", [propuestas.Parrafo("resumen_factual", TITULO, PROPUESTA, cls.huella)])

    def _faltas(self, revision=None):
        datos = {"meta": {"fecha_informe": "2026-09-23"}}
        if revision is not None:
            datos["revision"] = {"parrafos": {"resumen_factual": revision}}
        return asistente.validar("QCOM", self.FECHA, datos)[0][9]

    def test_validacion_al_guardar(self):
        """Falla si el paso 9 no pide validar la propuesta, si no detecta una huella vieja o si no pasa lo editado por el linter."""
        self.assertEqual(self._faltas(), [f"revision.parrafos: «{TITULO}» sin aceptar ni editar"])
        self.assertEqual(self._faltas({"propuesta": self.huella, "frases": [list(x) for x in PROPUESTA], "editado": False}), [])
        self.assertIn("cambió desde que lo validó", self._faltas({"propuesta": "0" * 16, "frases": [list(x) for x in PROPUESTA]})[0])
        editada = [["Los ingresos no están disponibles (N/A).", PROPUESTA[0][1]], list(PROPUESTA[1])]
        self.assertEqual(self._faltas({"propuesta": self.huella, "frases": editada, "editado": True}),
                         ["revision.parrafos.resumen_factual[1]: «N/A» en un texto del analista"])

    def test_avisa_de_la_frase_larga_mientras_escribe(self):
        """Falla si el asistente deja de avisar (sin bloquear) de una frase desde 40 palabras al guardar."""
        datos = {"meta": {"fecha_informe": "2026-09-23"}, "tesis": {"resumen": {"texto": LARGA}}}
        faltas, avisos = asistente.validar("QCOM", self.FECHA, datos)
        self.assertTrue([a for a in avisos if a.startswith("tesis.resumen: frase de 50 palabras")], avisos)
        self.assertFalse([f for f in faltas[3] if "frase de" in f])

    @pytest.mark.lenta
    def test_aceptar_y_editar_en_el_navegador(self):
        """Falla si los botones del paso 9 no dejan en `entradas.json` la propuesta aceptada con su huella, o lo editado
        marcado como editado y con la cita de la propuesta."""
        from playwright.sync_api import expect, sync_playwright
        from tesis.web import saas
        srv, _ = saas.servir(8795, en_hilo=True)
        ruta = Path(self.tmp) / "entradas" / "QCOM" / "2026-09-23" / "entradas.json"
        try:
            with sync_playwright() as pw:
                navegador = pw.chromium.launch()
                pagina = navegador.new_page()
                pagina.goto("http://127.0.0.1:8795/asistente?ticker=QCOM&fecha=2026-09-23&paso=9")
                pagina.get_by_role("button", name="Aceptar la propuesta").click()
                pagina.locator("#guardar").click()
                expect(pagina.locator("#estado-guardado")).to_have_text(re.compile("^Guardado en"))
                r = json.loads(ruta.read_text(encoding="utf-8"))["revision"]["parrafos"]["resumen_factual"]
                self.assertEqual(r, {"propuesta": self.huella, "frases": [list(x) for x in PROPUESTA], "editado": False})
                self.assertEqual(pagina.locator(".estado-parrafo").inner_text(), "aceptado")
                pagina.get_by_role("button", name="Editar").click()
                pagina.locator("[data-parrafo=resumen_factual] textarea").first.fill("Los ingresos del 3T FY26 sumaron 9.947 mln USD.")
                pagina.get_by_role("button", name="Dar por buena la edición").click()
                self.assertEqual(pagina.locator(".estado-parrafo").inner_text(), "editado")
                pagina.locator("#guardar").click()                   # «Guardando…» al pulsar, «Guardado en…» al volver
                expect(pagina.locator("#estado-guardado")).to_have_text(re.compile("^Guardado en"))
                # sin `navegador.close()`: en esta máquina no vuelve (ver `render/imprimir.py`) y la prueba se quedaba
                # colgada 2 h 16 min; al salir del `with`, Playwright termina Chromium en ~30 s sin dejar procesos
        finally:
            srv.shutdown()
            srv.server_close()
        r = json.loads(ruta.read_text(encoding="utf-8"))["revision"]["parrafos"]["resumen_factual"]
        self.assertEqual(r["frases"][0], ["Los ingresos del 3T FY26 sumaron 9.947 mln USD.", PROPUESTA[0][1]])
        self.assertTrue(r["editado"])


def _anual(anio: int):
    from tesis.datos.hechos import Periodo
    return Periodo(date(anio, 12, 31), date(anio, 1, 1))


def _hechos(series):
    """{(campo, periodo): Hecho} de series anuales {campo: {año: valor}}."""
    from tesis.datos.hechos import Capa, Origen, de_valor
    return {(c, _anual(a)): de_valor(c, _anual(a), v, Capa.SEC, Origen(documento="10-K")) for c, s in series.items() for a, v in s.items()}


class ComprobacionesDeSector(unittest.TestCase):
    """05 §2: cada paquete con sus comprobaciones, como avisos del motor y con los umbrales de `umbrales.sector`."""
    U = {"regla_40_min": 0.40, "sbc_ingresos_max": 0.10, "sbc_proyeccion_pp": 0.03, "ciclo_anios": [7, 10], "ciclo_desvio_pp": 0.05,
         "arrendamientos_ve_max": 0.05, "pensiones_cap_max": 0.02, "apalancamiento_max": 0.60}

    def _p(self, **kw):
        from tesis.motor.supuestos import Escenario, Parametros
        p = Parametros(fecha_valoracion=date(2026, 9, 22), **kw)
        p.escenarios["base"] = Escenario("base", 0.5, "", [0.05] * 5, [0.20] * 5, [0.21] * 5, [0.03] * 5, [0.03] * 5, 0.0, [0.05] * 5)
        return p

    def test_software_regla_40_y_sbc(self):
        """Falla si un software que crece un 10 % con un 20 % de margen de FCF no avisa de la regla del 40, si avisa con 40 %
        justos, o si el SBC del 13,6 % de los ingresos, que el escenario base baja al 5 %, pasa sin aviso."""
        from tesis.motor import sector
        periodos = {"anuales": [_anual(2024), _anual(2025)]}
        h = _hechos({"ingresos": {2024: 100e6, 2025: 110e6}, "fcf": {2025: 22e6}, "sbc": {2025: 15e6}})
        avisos = sector._regla_40(h, periodos, self.U)
        self.assertEqual(len(avisos), 1)
        self.assertIn("= 30,0\u00a0%", avisos[0])
        self.assertEqual(sector._regla_40(_hechos({"ingresos": {2024: 100e6, 2025: 110e6}, "fcf": {2025: 33e6}}), periodos, self.U), [])
        avisos = sector._sbc(h, periodos, self._p(), self.U)
        self.assertEqual(len(avisos), 2, avisos)
        self.assertIn("SBC del 13,6\u00a0% de los ingresos", avisos[0])
        self.assertIn("año 1 del 5,0\u00a0%", avisos[1])
        self.assertEqual(len(sector._sbc(h, periodos, self._p(sbc_politica="dilucion"), self.U)), 1)

    def test_semiconductores_pico_de_ciclo_y_margen_terminal(self):
        """Falla si QCOM valorada a finales de 2022 (margen del 35,9 % frente a una mediana de ciclo del 28,0 %) no avisa de
        pico, o si un margen terminal del 35 % pasa; con el año base de 2025 en la mediana, no avisa."""
        from tesis.fuentes import sec
        from tesis.motor import sector
        cache = sec.CACHE
        sec.CACHE = F / "cache_sec"
        try:
            facts, _ = sec.companyfacts(sec.emisor("QCOM").cik)
        finally:
            sec.CACHE = cache
        p = self._p()
        p.escenarios["base"].margen = [0.27] * 5
        self.assertEqual(sector._ciclo(facts, p, self.U), [])
        p.fecha_valoracion = date(2022, 12, 1)
        avisos = sector._ciclo(facts, p, self.U)
        self.assertEqual(len(avisos), 1, avisos)
        self.assertIn("margen operativo del 35,9\u00a0% frente a una mediana del 28,0\u00a0% en 10 ejercicios", avisos[0])
        self.assertIn("pico de ciclo", avisos[0])
        p.fecha_valoracion, p.escenarios["base"].margen = date(2026, 9, 22), [0.35] * 5
        self.assertIn("margen terminal", " ".join(sector._ciclo(facts, p, self.U)))

    def test_arrendamientos_pensiones_y_apalancamiento(self):
        from types import SimpleNamespace as N
        from tesis.motor import sector
        m = N(ev_mercado=1000e6, cap_mercado=1000e6)
        self.assertEqual(len(sector._arrendamientos(self._p(), m, 100e6, self.U)), 1)
        self.assertEqual(sector._arrendamientos(self._p(arrendamientos="deuda"), m, 100e6, self.U), [])
        self.assertEqual(sector._arrendamientos(self._p(), m, 40e6, self.U), [])
        facts = {"facts": {"us-gaap": {"DefinedBenefitPlanFundedStatusOfPlan": {"units": {"USD": [
            {"end": "2025-12-31", "val": -50e6, "filed": "2026-02-10"}]}}}}}
        self.assertIn("déficit del plan de prestación definida de 50 mln USD", sector._pensiones(facts, self._p(), m, self.U)[0])
        recogido = self._p(ajustes_puente=[{"concepto": "pensiones", "importe": 50}])
        self.assertEqual(sector._pensiones(facts, recogido, m, self.U), [])
        self.assertEqual(sector._pensiones({"facts": {}}, self._p(), m, self.U), [])        # sin plan: no es una partida suya
        w = N(peso_d=0.7, kd=0.03, rf=0.042)
        avisos = sector._kd_apalancamiento(m, w, self.U)
        self.assertEqual(len(avisos), 2, avisos)

    def test_cada_paquete_solo_las_suyas(self):
        """Falla si un paquete corre comprobaciones que no son suyas (general, ninguna) o si deja de correr las suyas."""
        from types import SimpleNamespace as N
        from tesis.motor import datos, sector
        m, w = N(ev_mercado=1000e6, cap_mercado=1000e6), N(peso_d=0.7, kd=0.03, rf=0.042)
        cfg = datos.sectores()
        self.assertEqual(sector.comprobar(self._p(paquete="general"), {}, {"anuales": []}, {"facts": {}}, m, w, 100e6, self.U, cfg), [])
        self.assertEqual(len(sector.comprobar(self._p(paquete="utilities"), {}, {"anuales": []}, {"facts": {}}, m, w, 100e6, self.U, cfg)), 2)
        self.assertEqual(len(sector.comprobar(self._p(paquete="telecom"), {}, {"anuales": []}, {"facts": {}}, m, w, 100e6, self.U, cfg)), 1)


class BloqueoV1(unittest.TestCase):

    def test_biotecnologica_sin_ingresos_y_financieras(self):
        """Falla si una biotecnológica por debajo de 50 mln USD de ingresos (o sin ingresos en la SEC) no se bloquea, si se
        bloquea una con ingresos, o si un banco deja de bloquearse."""
        from tesis.motor.datos import paquete_por_sic
        self.assertIn("biotecnológica con 10 mln USD de ingresos", paquete_por_sic("2836", 10e6)[1])
        self.assertIn("biotecnológica sin ingresos publicados en la SEC", paquete_por_sic("8731", None)[1])
        self.assertEqual(paquete_por_sic("2834", 900e6), ("salud_madura", None))
        self.assertIn("bancos", paquete_por_sic("6021", 5e9)[1])
        self.assertEqual(paquete_por_sic("3674", None), ("semiconductores", None))


class BloqueoV1EnElAsistente(_Datos):

    def test_el_paso_1_mira_los_ingresos_de_la_sec(self):
        """Falla si el paso 1 del asistente no bloquea una biotecnológica sin ingresos en la SEC, o si bloquea una con ellos
        (los ingresos del último ejercicio salen de companyfacts: todavía no hay informe)."""
        from types import SimpleNamespace as N
        from unittest import mock
        from tesis.motor.datos import ingresos_anuales
        cache = sec.CACHE
        sec.CACHE = F / "cache_sec"
        try:
            qcom = sec.companyfacts(sec.emisor("QCOM").cik)
        finally:
            sec.CACHE = cache
        self.assertEqual(ingresos_anuales(*qcom), 44_284e6)
        datos = {"meta": {"fecha_informe": "2026-09-23"}}
        for facts, bloquea in ((({"facts": {}}, date(2026, 9, 23)), True), (qcom, False)):
            with mock.patch.object(sec, "emisor", return_value=N(sic="2836", cik="1", ticker="BIOX")), \
                    mock.patch.object(sec, "companyfacts", return_value=facts):
                faltas = asistente.validar("BIOX", date(2026, 9, 23), datos)[0][1]
            v1 = [f for f in faltas if "bloqueo v1" in f]
            self.assertEqual(bool(v1), bloquea, faltas)


class Paso1(unittest.TestCase):

    def test_obligatorios_y_validaciones(self):
        from tesis.entradas import Entradas, comprobar_paso1
        paquetes = ["general", "semiconductores"]
        bien = {"meta": {"analista": "A", "fecha_valoracion": "2026-09-22", "tipo": "inicio_cobertura", "nombre_presentacion": "Qualcomm",
                         "sector": "semiconductores"}}
        self.assertEqual(comprobar_paso1(Entradas(bien), date(2026, 9, 23), paquetes), [])
        self.assertEqual(comprobar_paso1(Entradas({}), date(2026, 9, 23), paquetes),
                         [f"meta.{x}: obligatorio (paso 1)" for x in ("analista", "fecha_valoracion", "tipo", "nombre_presentacion", "sector")])
        mal = {"meta": dict(bien["meta"], fecha_valoracion="2026-09-24", sector="banca", nombre_presentacion="QUALCOMM INC/DE")}
        faltas = comprobar_paso1(Entradas(mal), date(2026, 9, 23), paquetes, "bancos fuera")
        self.assertEqual([f.split(":")[0] for f in faltas], ["meta.sector", "meta.fecha_valoracion", "meta.sector", "meta.nombre_presentacion"])
        self.assertIn("bloqueo v1", faltas[0])


class QualcommSinPaso1(_Informes):
    """QCOM con el paso 1 vacío salvo la fecha de valoración (sin ella no hay cierre congelado de la bolsa): bloquea por
    cada obligatorio y el motor vuelve a la propuesta del SIC (3663 → industrial)."""
    T, HOY = "QCOM", date(2026, 9, 23)

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        datos = json.loads((F / "QCOM" / "entradas.json").read_text(encoding="utf-8"))
        datos["meta"] = {"fecha_valoracion": datos["meta"]["fecha_valoracion"]}
        cls.RUTA_ENTRADAS = Path(cls.tmp) / "entradas.json"
        cls.RUTA_ENTRADAS.write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_bloquea_y_el_sector_vuelve_a_la_propuesta(self):
        """Falla si el paso 1 vacío no bloquea, o si el sector y la fecha de valoración no salen del paso 1 (`meta`)."""
        puerta = qa.revisar(self.inf, self.html, self.HOY)
        self.assertEqual([_sin_apartado(b) for b in puerta.bloqueos if "Paso 1 ·" in b],
                         [f"Paso 1 · meta.{x}: obligatorio (paso 1)" for x in ("analista", "tipo", "nombre_presentacion", "sector")])
        self.assertEqual((self.motor.parametros.paquete, self.motor.parametros.paquete_confirmado), ("industrial", False))
        self.assertEqual(self.motor.parametros.fecha_valoracion, date(2026, 9, 22))      # la de `meta`, no la del informe
        fila = next(d for d in self.inf.ficha if d.rotulo == "Sector · paquete del DCF")
        self.assertEqual((fila.texto, fila.fuente), ("Industrial", "propuesta por el SIC 3663 (05 §2); la confirma el analista en el paso 1"))


class QualcommCicloEstricto(_Informes):
    """QCOM con el umbral de ciclo a 0,5 p. p.: su año base (27,9 % frente a una mediana del 27,1 %) pasa a ser pico."""
    T, HOY = "QCOM", date(2026, 9, 23)

    @classmethod
    def setUpClass(cls):
        from tesis.umbrales import _datos
        cls._desvio = _datos()["sector"]["ciclo_desvio_pp"]
        _datos()["sector"]["ciclo_desvio_pp"] = 0.005
        try:
            super().setUpClass()
        finally:
            _datos()["sector"]["ciclo_desvio_pp"] = cls._desvio

    def test_el_motor_corre_las_comprobaciones_del_paquete(self):
        """Falla si el motor no corre las comprobaciones del paquete del analista o si su aviso no llega a la puerta (o bloquea)."""
        puerta = qa.revisar(self.inf, self.html, self.HOY)
        ciclo = [a for a in puerta.avisos if a.startswith("Motor: Ciclo (semiconductores): el año base")]
        self.assertEqual(len(ciclo), 1, puerta.avisos)
        self.assertIn("pico de ciclo", ciclo[0])
        self.assertFalse([b for b in puerta.bloqueos if "Ciclo" in b])


class QualcommCitas(_Informes):
    """Lo que el analista puede citar: el 10-K, la DEF 14A, las notas de resultados y, desde F8, el último 10-Q."""
    T, HOY = "QCOM", date(2026, 9, 23)

    def test_el_ultimo_10q_se_puede_citar_por_su_folio(self):
        """Falla si el 10-Q del trimestre en curso deja de ser citable (con sus folios y su alias en el cuerpo) o si una
        cita a un documento que no está no dice cuáles se pueden citar."""
        from tesis.entradas import verificar_cita
        textos = self.pb.textos
        self.assertIn("10-Q 2026-07-29", textos)
        self.assertEqual(self.pb.alias["10-Q 2026-07-29"], "10-Q 3T FY26")
        pagina = next(k for k in textos if k.startswith("10-Q 2026-07-29#") and len(textos[k].split()) > 200)
        literal = " ".join(textos[pagina].split()[100:125])
        self.assertTrue(verificar_cita({"doc": "10-Q 2026-07-29", "pag": pagina.split("#")[1], "texto": literal}, textos, 0.9)[0])
        otra = next(k for k in textos if k.startswith("10-Q 2026-07-29#") and k != pagina and literal[:40] not in textos[k])
        self.assertFalse(verificar_cita({"doc": "10-Q 2026-07-29", "pag": otra.split("#")[1], "texto": literal}, textos, 0.9)[0])
        ok, motivo = verificar_cita({"doc": "10-Q", "pag": "3", "texto": literal}, textos, 0.9)
        self.assertFalse(ok)
        self.assertIn("se pueden citar: 10-K, 10-Q 2026-07-29, 8-K 2024-07-31", motivo)


class OrdenDelPaquete(unittest.TestCase):
    """El backend ordenado en subpaquetes (fuentes, datos, verificacion, entradas, motor, plantillas, qa, render, web,
    heredado): cada ruta del repositorio sale de `rutas` y lo heredado no se cuela en lo nuevo."""

    def test_las_rutas_apuntan_al_repositorio(self):
        """Falla si un módulo movido calcula sus rutas desde su carpeta: la caché de EDGAR, la carpeta de `emitir.py`, la
        maqueta, el tablero, los specs o un fichero de configuración quedarían dentro del paquete (y las pruebas, que
        desvían la caché, no lo verían)."""
        from tesis import rotulos, rutas, umbrales
        from tesis.datos import item1a
        from tesis.entradas import asistente as asis, tarjetas
        from tesis.plantillas import frases, indice, parte_g, parte_i
        from tesis.qa import linter
        from tesis.render import MAQUETA
        from tesis.web import saas
        self.assertTrue((rutas.REPO / "emitir.py").is_file())
        self.assertEqual((sec.RAIZ, saas.RAIZ), (rutas.REPO, rutas.REPO))
        self.assertTrue((MAQUETA / "tesis.html").is_file() and (saas.TABLERO / "asistente.js").is_file())
        for ruta in (asis._SPEC, indice.RUTA, linter._ESTILO, frases._RUTA, parte_g._RUTA, parte_i._DEFINICIONES, item1a._RUTA,
                     tarjetas._RUTA, rotulos._RUTA, umbrales._RUTA):
            self.assertTrue(ruta.is_file(), ruta)

    def test_imprimir_arranca_sin_cargar_el_informe(self):
        """Falla si `python -m tesis.render.imprimir` (un proceso por PDF) vuelve a importar el informe entero al arrancar."""
        import subprocess
        import sys
        r = subprocess.run([sys.executable, "-c", "import sys, tesis.render.imprimir; print(sorted(m for m in sys.modules if m.startswith('tesis')))"],
                           cwd=str(Path(__file__).resolve().parents[1]), capture_output=True, text=True, timeout=60)
        self.assertEqual(r.stdout.strip(), "['tesis', 'tesis.render', 'tesis.render.imprimir', 'tesis.rutas']", r.stderr)

    def test_cada_modulo_en_su_paquete_y_lo_heredado_aparte(self):
        """Falla si vuelve un módulo suelto a la raíz del paquete, si un subpaquete no dice qué contiene o si un módulo nuevo
        importa del camino anterior (`heredado`) fuera de los que F9 retira."""
        import ast
        raiz = Path(__file__).resolve().parents[1] / "tesis"
        self.assertEqual(sorted(p.stem for p in raiz.glob("*.py")), ["__init__", "__main__", "entorno", "formato", "rotulos", "rutas", "umbrales"])
        for paquete in ("fuentes", "datos", "verificacion", "entradas", "motor", "plantillas", "qa", "render", "web", "heredado"):
            self.assertTrue(ast.get_docstring(ast.parse((raiz / paquete / "__init__.py").read_text(encoding="utf-8"))), paquete)
        llaman = set()
        for f in raiz.rglob("*.py"):
            modulo = ".".join(f.relative_to(raiz).with_suffix("").parts)
            for n in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
                if isinstance(n, ast.ImportFrom) and "heredado" in (n.module or "") and not modulo.startswith("heredado."):
                    llaman.add(modulo)
        self.assertEqual(sorted(llaman), ["plantillas.informe", "plantillas.secciones", "web.saas"])


if __name__ == "__main__":
    unittest.main()
