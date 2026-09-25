"""El dato: la unidad `Hecho`, el catálogo de campos y su lectura de los documentos del expediente.

- `hechos`, `campos`, `derivados`: el Hecho (valor · cero · sin dato), qué pide el informe y las fórmulas derivadas.
- `expediente`, `documentos`: qué es cada adjunto y qué documentos hacen falta.
- `extractor`, `recortes`, `tablas_html`, `ixbrl`: números de los PDF con su página y rectángulo, recortes a PNG, tablas
  de los HTML de EDGAR y hechos del XBRL inline con dimensiones.
- `segmentos`, `ficha`, `gobierno`, `proxy`, `item1a`, `guia`, `guidance`: lo que se lee de los documentos para los
  apartados 1, 4–7, 24 y 26 (segmentos, ficha, accionistas y retribución, riesgos del Item 1A, guía e hitos 8-K).
"""
