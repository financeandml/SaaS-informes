# tesis — tesis de inversión de Warrants & Co.
App local http://127.0.0.1:8770 · Python ≥ 3.11 · sin IA en tiempo de ejecución.
Hereda `../../CLAUDE.md`; donde choquen, manda este fichero.

## No negociable
1. Índice, títulos, numeración y anclas: solo `docs/spec/01_indice.yaml`.
2. Toda cifra impresa es un Hecho (`docs/spec/03` §2) con id, fuente y estado. Prohibidos los literales numéricos en plantillas.
3. Nada específico de un emisor en código, plantillas ni notas.
4. Un valor por informe: precio = cierre oficial Nasdaq de `fecha_valoracion`; PO = motor; una recomendación; un horizonte.
5. No se emite con bloqueos de QA (`docs/spec/06` §3). Los logs van a `auditoria.json`, nunca al cuerpo del informe.
6. Fuentes: SEC EDGAR · Nasdaq · Tesoro de EE. UU. · Yahoo solo para IV (excepción marcada). Ninguna más.
7. v1 solo no financieras; financieras, REIT y biotech sin ingresos → bloqueo.
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

## Mapa (objetivo)
`tesis/fuentes` (edgar, nasdaq, yahoo, tesoro) · `tesis/datos` (hechos, calendario, mapeo, segmentos, textos) ·
`tesis/verificacion` · `tesis/entradas` (asistente web) · `tesis/motor` (wacc, proyeccion, terminal, puente, escenarios,
sensibilidad, reverse, multiplos, sotp, objetivo, excel, validacion) · `tesis/plantillas` · `tesis/qa` · `tesis/render` ·
`config/` · `docs/spec/`

## Specs
01 índice · 02 estilo · 03 datos y verificación · 04 entradas · 05 motor · 06 plantillas, QA y render · 07 regresiones

## Comandos
- `python -m tesis servir [--puerto 8770] [--sin-navegador]` · `python -m tesis documentos TICKER` · `python -m tesis generar TICKER --fecha AAAA-MM-DD`
- Lo antiguo sigue valiendo y manda: `servir` es `tesis.saas` y `generar` es `emitir.py`, con sus mismas opciones pasadas tal cual.
- `pytest -q` y `python -m unittest discover -s tests -p "prueba_*.py"` recorren la misma batería (`pytest.ini`).
- Datos pesados fuera de la copia de trabajo: `WC_DATOS` sitúa `adjuntos/` y `salida/`. Sin la variable, vuelven a la raíz.
- Fixtures sin red en `tests/fixtures/cache_sec/` (versionados): QCOM, NFLX, WMT y JPM, con el 10-K de QCOM y NFLX (apunta `sec.CACHE` ahí).
- Dependencias: `jinja2`, `pypdfium2`, `playwright`, `matplotlib`, `pillow` y `pyyaml` (el índice y los umbrales son YAML).

## Estado
F0 ☑ · F1 ☑ esqueleto + C (24/09/2026) · F2 ☐ B · F3 ☐ D · F4 ☐ E · F5 ☐ F · F6 ☐ G + portada + asistente · F7 ☐ A + H + I + cierre
Protocolo: en cada sesión nueva el analista escribe «sigue» → `docs/fases/00_protocolo.md`. Siguiente: F2 (`docs/fases/F2.md`).
«confirmo borrar» (analista, 24/09/2026): hecho en F1 (sin `narrativa.py`, SDK `anthropic`, `--redactar`, `narrativas/` ni restos).
Batería: 176 en verde y 34 omitidas sin los adjuntos de NFLX/QCOM. `python -m tesis regresiones` → **12 de 33** (todas las de F1).
F1: índice desde `01_indice.yaml` (`tesis/indice.py`), trimestres fiscales («4T FY25»), 4T por acción derivado, SG&A en una línea,
filas que la compañía no tiene fuera, notas de split y dividendos desde los datos, ficha con DEI del 10-K de EDGAR (auditor, nombre,
free float, acciones) y propuestas de plantilla y fundación con cita. El asistente web pasa entero a F6.
