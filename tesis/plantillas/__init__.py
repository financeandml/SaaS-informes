"""El informe como datos y lo que se imprime: índice, partes A–I, frases de plantilla, cuadros, gráficos y la maqueta.

- `indice`: el índice de `docs/spec/01_indice.yaml` (letras, números, títulos y anclas).
- `informe`: reúne hechos, cuadros y partes en el objeto `Informe` que lee la maqueta; no calcula ni lee documentos.
- `parte_a` … `parte_i`: los apartados de cada parte (la C vive en `informe` y `secciones`).
- `secciones`: cuadros de las secciones C–I y evidencia visual (con restos del camino anterior: `heredado`).
- `frases` (+ `config/frases.yaml`): el párrafo de plantilla (06 §1); `graficos`: SVG incrustados.
- `maqueta/`: la plantilla Jinja2 y su CSS (`tesis.html`, `tesis.css`).
"""
