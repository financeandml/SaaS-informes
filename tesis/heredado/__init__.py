"""El camino anterior al asistente de 9 pasos, clasificado aparte hasta que F9 lo retire. Lo que producen se imprime
en las ramas sin parte B de la maqueta; con parte B solo quedan dos restos: la lista de fuentes de 37 nombra las cartas
que lee `historial` y la documentación lleva los volcados de API de `historial` y `comparables`.

- `agregador`: lo que publica Yahoo del valor (la regla 6 lo dejó fuera; solo lo usan sus pruebas).
- `comparables`, `mercado_objetivo`: los comparables de la bolsa y el TAM declarado (22 y 21 antiguos).
- `regiones`, `riesgos`, `historial`, `cartas`: ingresos por región, Item 1A de los PDF, historial y cartas anteriores.
- `dcf`: el libro de valoración del analista con el formato antiguo (sección D antes del motor).

Quién los llama todavía: `emitir.py` (los construye y se los pasa al informe), `plantillas.informe` y
`plantillas.secciones` (las ramas sin parte B, el cuadro de regiones y los recortes de la sección H) y `web.saas`
(el resumen del libro en la página DCF).
"""
