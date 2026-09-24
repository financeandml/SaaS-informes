# 02 · Maqueta, estilo y lenguaje

Referencias: informes QCOM (23/09/2026) y NFLX (17/09/2026); NFLX es el modelo de redacción. Pasa los valores exactos del CSS actual (colores, fuentes, tamaños, márgenes) a variables en `tesis/render/tema.css`; plantillas y gráficos solo usan esas variables.

## Página
- A4 vertical, márgenes actuales.
- Cabecera: «Warrants & Co.» en negrita a la izquierda; a la derecha «Análisis · <nombre>» y «dd/mm/aaaa · <ESTADO>», con el estado en granate negrita («BORRADOR — NO EMITIDO» o «EMITIDO»). Filete granate fino debajo.
- Pie: «© aaaa Warrants & Co.» · «Análisis / <nombre>» · «Página N de M», sobre filete gris.
- Portada (hoja 1): nombre en granate grande, fecha larga («23 de septiembre de 2026»), subtítulo «Inicio de cobertura: tesis de inversión» o «Actualización: tesis de inversión». Dos columnas según `01_indice.yaml › portada`.
- Índice (hoja 2) a dos columnas: partes en negrita, subtítulos de G y H en gris, entradas enlazadas.

## Color y tipografía
- `--granate` (marca): títulos de parte y apartado, «Cuadro N.», cabeceras de tabla (texto blanco en negrita), estado.
- `--azul` barras · `--ocre` líneas y marcadores · `--gris` fuentes, notas y N/A · `--gris-claro` fondo de recuadros.
- Sans serif actual. Cuerpo ≈ 10 pt justificado; cuadros ≈ 8,5 pt; fuentes y citas ≈ 7 pt en gris.

## Jerarquía
- Parte: «A. Título» en granate grande con filete; salto de página antes.
- Apartado: «1. Título» en granate. Subtítulo: negrita negra.
- Cuadro: «Cuadro N. Título (mln USD)» en granate encima; «Fuente: …» en gris debajo.
- Recuadros: «Lectura:» (fondo gris claro) para diferencias y convenciones; «Riesgo (10-K, Item 1A): «…»» sangrado en gris oscuro.

## Cuadros
- Números a la derecha; totales y filas clave en negrita; subpartidas sangradas; filetes grises finos.
- Periodos: ejercicios «2025»; trimestres fiscales «3T FY26» con la fecha de cierre en cabecera o nota.
- Filas que la compañía no publica o que no aplican al sector: no se imprimen. «N/A» solo si el dato debería existir, en cursiva gris y con el motivo en la línea de fuente.
- Tablas largas repiten cabecera; no se parten tablas de ≤ 12 filas.
- HTML: al pasar el ratón por una celda se ven su fuente, su fórmula y sus contrastes.

## Gráficos
Mismo tema: barras `--azul` con etiqueta de valor, línea `--ocre` con marcadores y etiquetas, leyenda debajo, eje con unidad, fuente debajo. Mínimo: ingresos y margen operativo; deuda neta y DN/EBITDA (C); mezcla por segmento (4); FCFF por escenario y abanico de valor (D); crecimiento frente a margen de comparables (22); matriz de riesgos (24); estructura temporal de IV (32).

## Lenguaje
- Español de España, formal, impersonal y factual. Sin adjetivos valorativos ni tono comercial; palabras vetadas en `config/estilo.yaml`.
- Una cita por frase con hechos, tras el punto, en gris pequeño: «[10-K 2025, pág. 23]»; varias: «[Carta 2T26, pág. 2; 10-Q 2T26, pág. 27]». Los alias de documento se definen en 37.
- Literales en su idioma, entre «», con página. Fuera de «» no hay inglés: países, industrias, cargos e ítems de 8-K se traducen con `config/traducciones.yaml`, y los nombres se limpian («Qualcomm Incorporated», no «Qualcomm Inc./De»; sin «Common Stock»).
- Lo que dice la compañía, atribuido («la compañía prevé…»); lo que opina el analista, marcado como tal.
- Prohibido en el cuerpo: «pendiente», rutas, comandos, etiquetas XBRL, nombres de APIs y mensajes de parser.
- Frases ≤ 35 palabras (aviso desde 40); párrafos ≤ 6 frases.

## Números y fechas (es-ES)
- 12.560 M USD · 33,4 % · 7,2x · +1,5 p.p. · −3.117 (signo menos tipográfico).
- Títulos de cuadro «(mln USD)»; texto «M USD». Importes en millones sin decimales; porcentajes con 1 decimal; por acción con 2; múltiplos con 1.
- Fechas dd/mm/aaaa (portada: fecha larga). Trimestres «3T FY26».

## Extensión
Cuerpo (1–38) de 25 a 35 páginas como referencia; el 39 sin límite. Ninguna página por debajo del 25 % de contenido salvo la última de una parte.

## Pie legal
Texto en `config/emisor.yaml`. El documento no se autocalifica como «recomendación de inversión» en sentido regulatorio salvo decisión expresa.
