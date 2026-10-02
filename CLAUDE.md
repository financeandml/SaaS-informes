# tesis — tesis de inversión de Warrants & Co.
App local http://127.0.0.1:8770 · Python ≥ 3.11 · sin IA en tiempo de ejecución.
Hereda `../../CLAUDE.md` (copia en `docs/CLAUDE_warrants.md` para quien clone el repositorio); donde choquen, manda este fichero.

## No negociable
1. Índice, títulos, numeración y anclas: solo `docs/spec/01_indice.yaml`.
2. Toda cifra impresa es un Hecho (`docs/spec/03` §2) con id, fuente y estado. Prohibidos los literales numéricos en plantillas.
3. Nada específico de un emisor en código, plantillas ni notas.
4. Un valor por informe: precio = cierre oficial de la bolsa principal del emisor en `fecha_valoracion` (Nasdaq o NYSE en EE. UU.); si esa bolsa no lo publica de forma accesible, excepción rotulada según la regla 6. PO = motor; una recomendación; un horizonte.
5. No se emite con bloqueos de QA (`docs/spec/06` §3). Los logs van a `auditoria.json`, nunca al cuerpo del informe.
6. Fuentes: solo oficiales, listadas en `config/fuentes.yaml`: el propio emisor, reguladores y registros (SEC EDGAR, CNMV y equivalentes), bolsas, bancos centrales y tesoros (Tesoro de EE. UU., Reserva Federal, BCE), organismos estadísticos, ClinicalTrials.gov y FDA. Excepción supletoria, solo si la oficial no publica el dato o no responde: Investing y, si falla, Yahoo Finance. Todo dato excepcional lleva su nivel en el Hecho y se rotula en el cuerpo, en el 38 y en la QA. Una serie, una sola fuente. Ninguna más.
7. Sectores: financieras, REIT y biotech sin ingresos siguen bloqueados hasta que su fase (F20 bancos y aseguradoras, F21 REIT, extractivas y biotech) cierre su paquete; cada bloqueo se levanta al cerrar la suya, sin costes ni fuentes de pago.
8. Umbrales solo en `config/*.yaml`, nunca en código.
9. **Nunca inventes datos.** Sin dato publicado, `N/A` con motivo. Prohibido rellenar con ceros, medias o estimaciones.
10. **Tres estados siempre**: hay dato · el dato es cero · no hay dato. Y «no es una partida de esta empresa» no es un hueco.
11. **Inferencia ≠ hecho.** Toda clasificación y toda cifra derivada viaja con su certeza, su fórmula y su motivo.
12. **Mejor pedir que inventar**: si un parser no encuentra el dato, el asistente se lo pide al analista con cita verificable.
13. **Un hecho, una fuente.** Un total y sus partes, una cifra y su rótulo, salen del mismo sitio y hay una prueba que afirma que concuerdan.
14. Interfaz: nada de `innerHTML` (`elemento()` + `textContent`), CSP estricta (sin scripts en línea, sin `eval`, sin CDN), SQL parametrizado.
15. **No añadas dependencias** sin pedírmelo. No toques `adjuntos/`, `dcf/`, `posiciones/` ni `cache_sec/` sin avisar.
16. **Una prueba nueva no vale hasta haberla visto fallar**: reintroduce el fallo que dice cazar y comprueba que lo caza.

## Idioma
Todo en español: informe, interfaz (sin interruptor ES/EN), documentación y respuestas. Código en español (comentarios: el porqué, no el qué). En inglés solo las siglas y términos admitidos en `docs/spec/02` › Lenguaje, y los identificadores de las fuentes, que nunca se imprimen. Donde choque con `../../CLAUDE.md`, manda esto.

## Tokens
- Lee solo el spec de la tarea. No vuelques PDFs, HTML ni JSON: `head -c`, `jq`, `rg`.
- Tests offline con `tests/fixtures/`; red solo a través de `cache_sec/`.
- Parches, no reescrituras. Respuesta: cambios (≤ 5 líneas) + tests + bloqueos.
- En Windows, `PYTHONIOENCODING=utf-8`; los heredocs de Bash se comen las barras invertidas: edita con Write/Edit.

## Mapa
`tesis/fuentes` (emisores, sec, edgar, bme, bce, precio, calendario, posicionamiento, tesoro, yahoo) · `tesis/datos` (hechos, campos, derivados,
expediente, extractor, segmentos, ficha, gobierno, item1a, guia…) · `tesis/verificacion` (contraste, auditor, revision) ·
`tesis/entradas` (Entradas, asistente, propuestas, tarjetas) · `tesis/motor` (supuestos, wacc, proyeccion, terminal, puente,
escenarios, sensibilidad, comparables, multiplos, sector, excel, datos) · `tesis/plantillas` (indice, informe, parte_a…i,
secciones, frases, graficos, maqueta/) · `tesis/qa` (puerta, linter) · `tesis/render` (HTML, PDF, imprimir) · `tesis/web`
(saas, tablero/) · `tesis/heredado` (camino anterior; F9 lo retira) · raíz: entorno, rutas, umbrales, formato, rotulos ·
`config/` · `docs/spec/`. Las rutas del repositorio (config, specs, maqueta, raíz) salen de `tesis/rutas.py`.

## Specs
01 índice · 02 estilo · 03 datos y verificación · 04 entradas · 05 motor · 06 plantillas, QA y render · 07 regresiones

## Comandos
- Asistente del analista (9 pasos): http://127.0.0.1:8770/asistente?ticker=TICKER[&fecha=AAAA-MM-DD].
- `python -m tesis servir [--puerto 8770] [--sin-navegador]` · `python -m tesis documentos TICKER` · `python -m tesis generar TICKER --fecha AAAA-MM-DD`
- Lo antiguo sigue valiendo y manda: `servir` es `tesis.web.saas` y `generar` es `emitir.py`, con sus mismas opciones pasadas tal cual.
- `pytest -q` y `python -m unittest discover -s tests -p "prueba_*.py"` recorren la misma batería (`pytest.ini`).
- Datos pesados fuera de la copia de trabajo: `WC_DATOS` sitúa `adjuntos/`, `entradas/` y `salida/`. Sin la variable, vuelven a la raíz.
- Fixtures sin red (versionados): `tests/fixtures/cache_sec/` (QCOM, NFLX, WMT, JPM; 10-K, 10-Q, DEF 14A, Ex. 21, 13G y notas de QCOM y NFLX: apunta `fuentes.sec.CACHE` ahí), `tests/fixtures/cache_bolsa/` (Nasdaq y la VI de Yahoo: `fuentes.precio.CACHE_BOLSA` y `SOLO_CACHE = True`) y `tests/fixtures/<TICKER>/entradas.json` (entradas de prueba) y `tests/fixtures/NFLX/libro_nflx*.xlsx` (copia congelada de `dcf/NFLX.xlsx`, solo lectura).
- Dependencias: `jinja2`, `pypdfium2`, `playwright`, `matplotlib`, `pillow`, `openpyxl` y `pyyaml`. LibreOffice (opcional) solo para la prueba de recálculo del Excel exportado.

## Estado
F0 ☑ · F1 ☑ esqueleto + C · F2 ☑ B · F3 ☑ D · F4 ☑ E · F5 ☑ F · F6 ☑ G + portada + asistente · F7 ☑ A + H + I + cierre · F8 ☑ cierre de fallos (25/09/2026) · T0 ☑ base en verde (26/09/2026) · F9 ☑ camino antiguo fuera de la emisión, Form 4 y participación de la dirección (26/09/2026) · F10 ☑ estado «propuesto» y rúbrica (26/09/2026) · F11 ☑ propuestas deterministas (28/09/2026) · B (en curso, 29/09/2026) ☑ B1–B7 cualquier emisor: España por BME y BCE, cuentas en PDF contrastadas documento contra documento, sistema por puntos por apartado (`docs/fases/B.md`)
Protocolo: `docs/fases/00_protocolo.md`. Lo que queda fuera, en `docs/fases/F7.md` y `F8.md` › «No hecho».
Alcance (analista, 26/09/2026): cualquier emisor, cualquier fecha de informe y cualquier documento; la tesis de 39 apartados y, en F31, los formatos cortos. Idioma: solo español. Cumplimiento normativo: fuera de alcance, no se toca. Validación (F33): solo avisa, nunca bloquea. Plan: T0 → F9 → F10–F33.
Siguiente: B9 (fallos de la auditoría del 27/09, `docs/fases/A.md`: A5 ☑ el 30/09, A2, A3 y A6 ☑ el 02/10 —[56] FINRA pendiente de red—, sigue A8; 26 de 78 abiertos) y B8 (entradas de ejemplo de las empresas españolas); la emisión real de QCOM (`docs/emision_real.md`) sigue pendiente.
«confirmo borrar» (analista, 24/09/2026): hecho en F1 (sin `narrativa.py`, SDK `anthropic`, `--redactar`, `narrativas/` ni restos).
Batería: 431 en verde y 26 xfail en 6 min 11 s (02/10/2026, Linux y Python 3.11; `prueba_posicionamiento › ComparablesDeLaBolsa` necesita la caché de trabajo `cache_sec/`); `pytest -m "not lenta"` para iterar. `python -m tesis regresiones` → **33 de 33**.
F2: segmentos (XBRL inline), accionistas/13G/ejecutivos/retribución/filiales de EDGAR, guía de los Ex. 99.1 confirmada, fechas de Nasdaq.
F3: `tesis/motor/` (supuestos, proyeccion con periodo parcial, terminal, puente, wacc con beta frente a SPY y rf del Tesoro, escenarios,
sensibilidad e inverso, comparables del analista, excel con fórmulas vivas e importación por mapa), `parte_d.py`; precio único = cierre oficial.
F4: citas con página (folio impreso del documento de EDGAR), `tarjetas.py` + `config/evidencias.yaml`, `entradas.comprobar_paso5`,
`parte_e.py` (TAM/SAM/SOM con SOM por defecto y cuota implícita, competidores, comparables con gráfico, foso y datos de apoyo).
F5: `item1a.py` + `config/riesgos.yaml` (epígrafes por tipografía, con folio y familia corregible), `calendario.sorpresas` (Nasdaq),
`entradas.comprobar_paso6` y `parte_f.py` (5 riesgos con matriz, disparadores, riesgo por pilar, guía → real, consenso y causas).
F6: `asistente.py` + `tablero/asistente.*` (9 pasos desde 04, guardado versionado, migración de `posiciones/` sin tocarlo),
`entradas.comprobar_paso8`, `parte_g.py` (27–30 con criterios automáticos) y portada con la posición del analista.
F7: `parte_a.py` + `frases.py` (resumen factual con cita por frase y 5 pilares), `parte_h.py` (strikes, máximo dolor, VI frente a
realizada, movimiento en resultados), `parte_i.py` (38 en una página), `qa.py` + `render.emitir` (puerta de calidad, hoja 0,
EMITIDO/BORRADOR, relleno), `linter.py` + `config/estilo.yaml`; fuera `formulario.py`, `posicion.py`, el inglés del tablero y el agregador.
F8: `emitir.py` entero en la batería, VI caída como aviso, valor único con `data-hecho`, aceptar/editar del párrafo de
plantilla (`propuestas.py`, paso 9), avisos de longitud y cifras al redondeo impreso en el linter, paso 1 conectado al motor
y a la ficha, `motor/sector.py` (05 §2) y bloqueo v1 de biotecnológicas. Backend ordenado en subpaquetes (§ Mapa); las líneas
de fases anteriores citan los módulos por su nombre de entonces (correspondencia en `docs/estado.md` › F8).
