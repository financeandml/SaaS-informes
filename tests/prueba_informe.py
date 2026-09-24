"""Regla 9 en el informe: la caja de cifras del apartado 2 y la sección C son los mismos objetos."""

import hashlib
import re
import tempfile
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from tests import contacto_sec_de_prueba, hay_cache_sec, rutas_nflx
from tesis import contraste, derivados, expediente, ficha, formato, gobierno, graficos, guidance, historial, informe, mercado_objetivo, precio, regiones, render, riesgos, sec
from tesis.hechos import Capa, Certeza, Contraste, Estado, Hecho, Origen, Periodo, na

RUTAS = rutas_nflx()


class Formato(unittest.TestCase):
    def test_na_cero_valor(self):
        """Falla si la celda deja de distinguir los tres estados o pierde el motivo del N/A."""
        p = Periodo.anual(date(2025, 12, 31))
        self.assertEqual(formato.celda(na("x", p, "no publicado")).texto, "N/A")
        self.assertEqual(formato.celda(na("x", p, "no publicado")).nota, "no publicado")
        cero = Hecho("dividendos", p, 0.0, Estado.CERO, Capa.SEC)
        self.assertEqual(formato.celda(cero).texto, "0")
        v = Hecho("coste_ingresos", p, 23_275_329_000.0, Estado.VALOR, Capa.SEC)
        self.assertEqual(formato.celda(v).texto, "-23.275")     # signo de la casa: coste en negativo, millones con punto
        self.assertEqual(formato.pct(0.295), "29,5 %")


@unittest.skipUnless(RUTAS and hay_cache_sec(), "sin expediente de NFLX o sin caché SEC")
class Concordancia(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        contacto_sec_de_prueba()
        emisor = sec.emisor("NFLX")
        cls.exp = expediente.cargar("NFLX", RUTAS, emisor.depositos)
        facts, obtenido = sec.companyfacts(emisor.cik)
        periodos = contraste.periodos_del_informe(cls.exp)
        tab = contraste.contrastar(cls.exp, facts, obtenido, periodos)
        hoy = date(2026, 9, 16)
        # la prueba afirma lo que pasa SIN fuente de cotización: se aísla del .env de la máquina y no toca la red
        with mock.patch.object(precio, "variable", lambda nombre: ""):
            sin_precio = precio.obtener("NFLX", hoy)
        hechos = derivados.calcular(tab.hechos(), periodos["anuales"] + periodos["trimestres"], periodos["instantes"])
        # E y G salen de los adjuntos, sin red: bastan para afirmar el orden de numeración de los cuadros
        cls.entradas = ("NFLX", hoy, emisor, cls.exp, tab, periodos, ficha.construir(emisor, cls.exp), gobierno.construir(cls.exp),
                        guidance.construir(cls.exp, emisor.depositos, hoy), regiones.construir(cls.exp, tab), sin_precio, {})
        cls.inf = informe.construir(*cls.entradas, riesgos=riesgos.construir(cls.exp), historial=historial.construir(cls.exp, hechos),
                                    mercado_objetivo=mercado_objetivo.construir(cls.exp, hechos))
        cls.html = render.a_html(cls.inf)

    def test_caja_de_cifras_y_seccion_c_son_el_mismo_hecho(self):
        """Falla si el apartado 2 y el cuadro de resultados dejan de construirse del mismo diccionario de hechos:
        cada celda de «Ingresos» y «Beneficio neto» debe imprimir exactamente lo mismo en los dos cuadros."""
        i = self.inf
        for rotulo in ("Ingresos", "Beneficio neto"):
            caja = next(f for f in i.cifras_resumen.filas if f.rotulo == rotulo)
            seccion = next(f for f in i.resultados.filas if f.rotulo == rotulo)
            n = len(i.periodos_anuales)
            self.assertEqual([c.texto for c in caja.celdas[:n]], [c.texto for c in seccion.celdas[:n]])
            self.assertEqual([c.glifo for c in caja.celdas[:n]], [c.glifo for c in seccion.celdas[:n]])

    def test_grafico_y_cuadro_comparten_hechos(self):
        """Falla si el gráfico de ingresos se dibuja con otros números que la tabla."""
        i = self.inf
        ultimo = i.periodos_anuales[-1]
        h = i.hechos[("ingresos", ultimo)]
        self.assertIn(formato.mln(h.valor), i.grafico_ingresos)

    def test_precio_sin_fuente_es_na_con_motivo(self):
        """Falla si sin WC_PRECIO_FUENTE aparece un precio de algún sitio."""
        self.assertIs(self.inf.precio.estado, Estado.NA)
        self.assertIn("WC_PRECIO_FUENTE", self.inf.precio.motivo)
        self.assertTrue(any(d.rotulo == "Precio" and d.texto == "N/A" for d in self.inf.ficha))

    def test_cuadros_numerados_sin_repetir(self):
        """Falla si dos cuadros comparten número."""
        i = self.inf
        numeros = [c.numero for c in (i.cifras_resumen, i.objetivos, i.regiones, i.accionistas, i.filiales, i.ejecutivos, i.retribucion,
                                      i.resultados, i.balance, i.flujo, i.rentabilidad)]
        self.assertEqual(len(numeros), len(set(numeros)))

    def test_cuadros_numerados_por_orden_de_impresion(self):
        """Falla si un cuadro que se imprime antes lleva un número mayor: el tamaño de mercado (E) va antes que los
        riesgos (G) en la maqueta, y la secuencia «Cuadro N.» del HTML debe ser creciente y sin huecos."""
        i = self.inf
        self.assertIsNotNone(i.mercado_cuadro)
        self.assertLess(i.mercado_cuadro.numero, min(c.numero for c in i.riesgos_cuadros.values()))
        numeros = [int(n) for n in re.findall(r"Cuadro (\d+)\.", self.html)]
        self.assertEqual(numeros, sorted(numeros), numeros)          # el cuadro 1 sale dos veces (portada y apartado 2): eso sí
        self.assertEqual(sorted(set(numeros)), list(range(1, max(numeros) + 1)), numeros)

    def test_una_pagina_citada_varias_veces_da_un_recorte_con_su_huella(self):
        """Falla si dos citas de la misma página de un apartado producen dos recortes (el fichero es uno por página y
        apartado: el segundo pisa al primero y la huella impresa deja de ser la de la imagen) o si alguna huella impresa
        no es la del fichero que se incrusta."""
        with tempfile.TemporaryDirectory() as tmp:
            inf = informe.construir(*self.entradas, None, salida_recortes=Path(tmp))
            self.assertGreaterEqual(len(inf.evidencias.get("7", [])), 2, "el apartado 7 cita la carta y la transcripción")
            for clave, lista in inf.evidencias.items():
                self.assertEqual(len({(r.adjunto, r.pagina) for r in lista}), len(lista), f"apartado {clave}: dos recortes de la misma página")
                for r in lista:
                    self.assertEqual(r.huella, hashlib.sha256(Path(r.ruta).read_bytes()).hexdigest()[:16], (clave, str(r.ruta)))

    def test_el_apendice_se_cita_con_su_numero_del_indice(self):
        """Falla si la maqueta vuelve a teclear el número del apéndice en vez de leerlo del índice."""
        fuente = (render.MAQUETA / "tesis.html").read_text(encoding="utf-8")
        self.assertIsNone(re.search(r"apéndice \d", fuente), "número de apéndice tecleado en la maqueta")
        self.assertFalse("apéndice 39" in self.html, "la maqueta imprime «apéndice 39» con un índice de 38 apartados")

    def test_regla_9_regiones_suman_ingresos(self):
        """Falla si la suma de las regiones de un periodo contrastado no cuadra con el ingreso total (y no se declara)."""
        # las notas de cuadre ya no se imprimen bajo el cuadro (números limpios): van al apéndice, con el número del cuadro delante
        cuadres = [c.split("): ", 1)[1] for c in self.inf.cuadres_apendice if c.startswith(f"Cuadro {self.inf.regiones.numero} (")]
        self.assertTrue(cuadres, "sin comprobaciones de suma de regiones")
        self.assertFalse(any(n[:1] in informe._GLIFOS_CUADRE for n in self.inf.regiones.notas), "una nota de cuadre sigue bajo el cuadro")
        # Los ejercicios en que las regiones son todo el ingreso cuadran; en 2023 Netflix aún
        # tenía ingresos por DVD fuera de las regiones (82.839 miles) y el informe lo declara.
        self.assertTrue(any(c.startswith("✓ FY2025") for c in cuadres), cuadres)
        self.assertTrue(any(c.startswith("✓ 2T26") for c in cuadres), cuadres)
        self.assertTrue(any(c.startswith("≠ FY2023") and "82,839,000" in c for c in cuadres), cuadres)
        self.assertFalse(any(c.startswith("≠") and "hoja regional" in c for c in cuadres), "el formulario y la hoja regional deben coincidir: " + str(cuadres))


if __name__ == "__main__":
    unittest.main()


class Graficos(unittest.TestCase):
    """La paleta corporativa de los gráficos: una sola fuente (`graficos.PALETA`) y el granate de la maqueta fuera."""

    def _hechos(self):
        ps = [Periodo.anual(date(a, 12, 31)) for a in range(2021, 2026)]
        barras = [Hecho("ingresos", p, v * 1e6, Estado.VALOR, Capa.SEC) for p, v in zip(ps, [29698, 31616, 33723, 39001, 45183])]
        linea = [Hecho("margen_ebit", p, v, Estado.VALOR, Capa.SEC) for p, v in zip(ps, [0.209, 0.178, 0.206, 0.267, 0.295])]
        linea[1] = na("margen_ebit", ps[1], "sin dato en la prueba")
        partes = [(n, Hecho(n, ps[-1], v * 1e6, Estado.VALOR, Capa.SEC)) for n, v in (("UCAN", 5432), ("EMEA", 4034), ("LATAM", 1584), ("APAC", 1510))]
        return barras, linea, partes

    def test_los_graficos_solo_usan_la_paleta(self):
        """Falla si un gráfico pinta con un color que no está en la paleta (p. ej. el granate de la plantilla, #7a1f2b)."""
        barras, linea, partes = self._hechos()
        svg1, avisos = graficos.barras_con_linea(barras, linea, "Ingresos", "Margen operativo", [str(a) for a in range(2021, 2026)])
        svg2, _ = graficos.tarta(partes)
        permitidos = {c.lower() for c in graficos.PALETA + graficos.NEUTROS}
        for svg in (svg1, svg2):
            usados = {c.lower() for c in re.findall(r"#[0-9a-fA-F]{6}", svg)}
            self.assertTrue(usados <= permitidos, usados - permitidos)
        self.assertIn(graficos.MARINO, svg1)
        self.assertIn(graficos.OCRE, svg1)
        self.assertNotIn("#7a1f2b", svg1 + svg2)
        # el reparto va en la escala de un solo tono, de mayor a menor: las porciones se pintan en el orden de la escala
        # y sus rótulos salen en ese mismo orden, la parte mayor (UCAN) la primera y con el tono más oscuro
        rellenos = [c for c in re.findall(r"fill: (#[0-9a-f]{6})", svg2) if c in graficos.ESCALA]
        self.assertEqual(rellenos, graficos.ESCALA[:4])
        textos = re.findall(r"<text[^>]*>([^<]+)</text>", svg2)
        self.assertEqual([x for x in textos if x.isalpha()], ["UCAN", "EMEA", "LATAM", "APAC"])

    def test_dos_series_llevan_leyenda_y_el_hueco_se_declara(self):
        """Falla si la leyenda deja de nombrar las dos series o si un periodo sin margen se dibuja como si lo tuviera."""
        barras, linea, partes = self._hechos()
        svg, avisos = graficos.barras_con_linea(barras, linea, "Ingresos", "Margen operativo", [str(a) for a in range(2021, 2026)])
        self.assertIn(">Ingresos<", svg.replace(chr(10), ""))
        self.assertIn(">Margen operativo<", svg.replace(chr(10), ""))
        self.assertEqual(avisos, ["Margen operativo FY2022: sin dato"])
        self.assertEqual(svg.count("%</text>"), 4)      # cuatro puntos con cifra, no cinco


class Documentacion(unittest.TestCase):
    """El apartado de documentación complementaria se construye del índice y de los recortes; lo que decide, se afirma con datos mínimos."""

    def test_un_recorte_citado_por_varias_frases_se_imprime_una_vez(self):
        """Falla si el apartado final vuelve a imprimir la misma imagen (misma huella) por cada frase o cuadro que la cita,
        o si los apartados dejan de salir en el orden del índice."""
        rec = lambda huella, ruta: SimpleNamespace(ruta=ruta, alt="", pie=f"pie {huella}", huella=huella, pagina=5)
        indice, numeros = informe._indice()
        por_clave = {"7": [rec("aaaa1111", "a.png"), rec("aaaa1111", "a.png"), rec("bbbb2222", "b.png")], "30": [rec("cccc3333", "c.png")], "1": [rec("dddd4444", "d.png")]}
        doc = informe._documentacion(indice, numeros, por_clave)
        self.assertEqual([n for n, _, _ in doc], [1, 7, numeros["30"]])
        self.assertEqual([r.huella for r in doc[1][2]], ["aaaa1111", "bbbb2222"])
        self.assertEqual(doc[2][1], dict(sum(([a for a in s.apartados] for s in indice), []))[numeros["30"]])
