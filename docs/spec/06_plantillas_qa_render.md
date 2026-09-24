# 06 · Plantillas deterministas, QA y render

## 1. Redacción sin IA
- Jinja2 + biblioteca de frases en `plantillas/frases.yaml`: cada frase tiene id, condiciones y 2–3 variantes; la variante se elige por hash(apartado, id), así que el resultado es reproducible.
- Las frases solo reciben Hechos (`h()`), nunca números sueltos, y añaden las citas de los Hechos que usan.
- Cobertura mínima: variación («crecieron / cayeron / se mantuvieron» según signo y umbral), cambio de margen en p.p., guía vigente, valoración por escenario, lectura de la sensibilidad, recuento de fallos de guía, P/C y cortos.
- El sistema propone y el analista valida: en la vista previa cada párrafo de plantilla lleva «aceptar/editar»; lo aceptado queda congelado en `entradas.json`.
- Los textos del analista se imprimen literales después de pasar el linter.

## 2. Linter de textos del analista (bloquea)
Cifras del texto = Hechos (con tolerancia) o enlazadas a una evidencia · límites de palabras · palabras vetadas · sin inglés salvo las siglas y términos admitidos en 02 · sin «N/A», «pendiente» ni cifras sin unidad.

## 3. Puerta de calidad
Bloqueos (impiden emitir):
1. Entradas obligatorias completas (04).
2. 0 discrepancias abiertas y «solo documento» reconocidos.
3. Valor único por informe para precio, PO, recomendación, horizonte, deuda neta, acciones diluidas y capitalización: cada cifra impresa lleva `data-hecho`; dos valores para un mismo concepto → bloqueo.
4. Validaciones del motor (05 §4 y §7) y entradas del modelo = Hechos oficiales.
5. Índice = `01_indice.yaml` (39 apartados, letras A–I seguidas, anclas y títulos) y formulario con la misma numeración.
6. Cuerpo sin texto técnico: rutas, comandos, etiquetas XBRL, «companyfacts», «no trae», «patrón», URLs de API fuera de 37 y 39.
7. Recomendación coherente con la regla o justificada; entrada válida (04, paso 8).
8. 5 pilares con ≥ 2 evidencias y su riesgo del Item 1A.
9. Fechas «próximas» ≥ fecha del informe.
10. Ningún apartado obligatorio vacío; ningún N/A en la portada ni en 2, 3, 12–20 y 27–30.

Avisos (página interna de QA, no en el informe): los de 05, páginas con relleno < `relleno_pagina_min`, comparables excluidos, 13F antiguos e IV no cuadrada.

## 4. Render
- HTML con tooltips (fuente, fórmula, contrastes) → PDF A4 con el motor de hoy (reutilizar).
- CSS paginado: `break-before: page` solo en partes; `break-inside: avoid` en cuadros de ≤ 12 filas y en figura + pie; `orphans`/`widows` 3; `thead` repetido; recortes a 150–200 ppp, ajustados a la zona citada ± 1 línea.
- Tras generar el PDF se mide el relleno por página (PyMuPDF); si una página queda por debajo del umbral sin ser fin de parte, se deja fluir el bloque siguiente y se regenera (máximo 2 pasadas).
- Estados: vista previa con marca «BORRADOR — NO EMITIDO» y hoja 0 de bloqueos; «Emitir» solo con 0 bloqueos → «EMITIDO dd/mm/aaaa», con huellas en 37.

## 5. Definiciones (se imprimen en 38)
- Deuda neta = deuda financiera (CP + LP) − caja − inversiones CP; arrendamientos operativos fuera salvo que la política diga lo contrario.
- FCF = flujo operativo − capex.
- NOPAT = EBIT × (1 − tipo efectivo); ROIC = NOPAT / capital invertido medio (patrimonio + deuda neta).
- ROE = beneficio atribuido / patrimonio medio; ROA = beneficio / activo medio.
- PEG y NTM (05 §8); recorrido/riesgo, margen de seguridad y PO (05 §7); 4T derivado y etiquetas fiscales (03 §3).
- Precio: cierre oficial Nasdaq de fecha_valoracion. Yahoo: excepción para la IV.
