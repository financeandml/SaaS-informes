"""Los rótulos de las páginas del SaaS: que ninguno se quede con el nombre de su clave, y solo en español. Sin red.

El caso que las trajo (22/09/2026): el formulario del analista se abría enseñando «titulo», «portada», «pista_tamano»
—los nombres de las claves del diccionario— en lugar de sus rótulos. `formulario.js` añade su diccionario a D con
`Object.assign`, pero `saas.js` ya había pintado la página antes de que existieran esas claves, y nadie repintaba: los
rótulos solo aparecían si el analista cambiaba de idioma y volvía.
"""

import re
import unittest
from pathlib import Path

TABLERO = Path(__file__).resolve().parents[1] / "tesis" / "web" / "tablero"
PAGINAS = ("inicio.html", "dcf.html", "informe.html")          # las que pinta saas.js; el asistente trae sus propios rótulos


def _claves_de(texto: str) -> set:
    """Las claves que declara un bloque de diccionario JS: «clave: "valor"».

    Primero se vacían las cadenas: un texto que acaba en dos puntos —«El libro no trae:»— tiene la misma forma que
    una clave y se colaría como si lo fuera.
    """
    sin_texto = re.sub(r'"(?:[^"\\]|\\.)*"', '""', texto)
    return set(re.findall(r'[\s{]([a-z_0-9]+):\s*""', sin_texto))


def _claves() -> set:
    saas = (TABLERO / "saas.js").read_text(encoding="utf-8")
    return _claves_de(saas[saas.index("es: {"):saas.index("};")])


class Rotulos(unittest.TestCase):
    def test_cada_rotulo_de_las_paginas_esta_en_el_diccionario(self):
        """Falla si una página usa una clave que el diccionario no define: se imprimiría la clave misma, que es lo que
        el analista vio en el formulario («titulo», «portada», «pista_tamano»)."""
        definidas = _claves()
        for pagina in PAGINAS:
            usadas = set(re.findall(r'data-i18n="([^"]+)"', (TABLERO / pagina).read_text(encoding="utf-8")))
            self.assertTrue(usadas, pagina)
            self.assertEqual(usadas - definidas, set(), pagina)

    def test_solo_en_espanol_sin_interruptor_de_idioma(self):
        """Falla si vuelve el diccionario inglés o el botón ES/EN (CLAUDE.md › Idioma: interfaz sin interruptor)."""
        saas = (TABLERO / "saas.js").read_text(encoding="utf-8")
        self.assertNotRegex(saas, r"\ben: \{|en-GB|idioma")
        for pagina in PAGINAS + ("asistente.html",):
            self.assertNotIn('id="idioma"', (TABLERO / pagina).read_text(encoding="utf-8"), pagina)
        self.assertFalse((TABLERO / "formulario.html").exists() or (TABLERO / "formulario.js").exists(), "vuelve el formulario antiguo")

    def test_ninguna_pagina_trae_scripts_ni_estilos_en_linea(self):
        """Falla si una página se salta la CSP estricta (regla 5 de la casa)."""
        for pagina in PAGINAS + ("asistente.html",):
            html = (TABLERO / pagina).read_text(encoding="utf-8")
            self.assertNotRegex(html, r"<script(?![^>]*\ssrc=)", pagina)
            self.assertNotRegex(html, r"\son[a-z]+=", pagina)
            self.assertNotRegex(html, r"<style|\sstyle=", pagina)


class ElJavaScriptSeLee(unittest.TestCase):
    """Una cadena sin cerrar deja el SaaS entero en blanco, y ninguna prueba lo notaba.

    El caso que la trajo (23/09/2026): en `saas.js` el «\\n» de un `.join("\\n")` se convirtió en un salto de línea de
    verdad —la barra invertida se pierde al editar por consola—, así que la cadena quedaba abierta al final de la
    línea. El navegador daba `SyntaxError: Invalid or unexpected token`, no ejecutaba **nada** del fichero y la página
    seguía pintando su armazón estático: cabecera, tabla vacía y botones muertos. Con aspecto de estar bien.
    """

    def test_ninguna_cadena_se_queda_abierta_al_final_de_la_linea(self):
        """Falla si un `'` o un `"` no cierra en su línea: JavaScript no admite un salto dentro de una cadena."""
        for fichero in sorted(TABLERO.glob("*.js")):
            for n, linea in enumerate(_sin_comentarios(fichero.read_text(encoding="utf-8")).split("\n"), 1):
                self.assertIsNone(_cadena_abierta(linea), f"{fichero.name}:{n} deja una cadena abierta: {linea.strip()[:90]}")


def _sin_comentarios(js: str) -> str:
    """El código sin sus comentarios de bloque, conservando los saltos de línea para no mover la numeración."""
    return re.sub(r"/\*.*?\*/", lambda m: re.sub(r"[^\n]", " ", m.group(0)), js, flags=re.S)


def _cadena_abierta(linea: str):
    """La comilla que se queda sin pareja en la línea, o None. Las plantillas «`» sí pueden ocupar varias líneas.

    Un `/` abre una expresión regular —donde una comilla es un carácter más— solo si lo anterior pide un valor; si no,
    es una división. Es la distinción de siempre entre `x = /"/` y `a / b`.
    """
    i, comilla, anterior = 0, None, ""
    while i < len(linea):
        c = linea[i]
        if comilla is not None:
            if c == "\\":
                i += 1
            elif c == comilla:
                comilla = None
        elif c in "\"'":
            comilla = c
        elif c == "/" and i + 1 < len(linea):
            if linea[i + 1] == "/":
                break
            if anterior in "(,=:[!&|?{};+" or anterior == "":
                fin = re.compile(r"/(?:[^/\\\n\[]|\\.|\[(?:[^\]\\]|\\.)*\])*/").match(linea, i)
                i = fin.end() - 1 if fin else i
        if not c.isspace():
            anterior = c
        i += 1
    return comilla


if __name__ == "__main__":
    unittest.main()
