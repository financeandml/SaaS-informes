# tesis — tesis de inversión de Warrants & Co.
App local http://127.0.0.1:8770 · Python ≥ 3.11 · sin IA en tiempo de ejecución.

## No negociable
1. Índice, títulos, numeración y anclas: solo `docs/spec/01_indice.yaml`.
2. Toda cifra impresa es un Hecho (`docs/spec/03` §2) con id, fuente y estado. Prohibidos los literales numéricos en plantillas.
3. Nada específico de un emisor en código, plantillas ni notas.
4. Un valor por informe: precio = cierre oficial Nasdaq de `fecha_valoracion`; PO = motor; una recomendación; un horizonte.
5. No se emite con bloqueos de QA (`docs/spec/06` §3). Los logs van a `auditoria.json`, nunca al cuerpo del informe.
6. Fuentes: SEC EDGAR · Nasdaq · Tesoro de EE. UU. · Yahoo solo para IV (excepción marcada). Ninguna más.
7. v1 solo no financieras; financieras, REIT y biotech sin ingresos → bloqueo.
8. Umbrales solo en `config/*.yaml`, nunca en código.

## Tokens
- Lee solo el spec de la tarea. No vuelques PDFs, HTML ni JSON: `head -c`, `jq`, `rg`.
- Tests offline con `tests/fixtures/`; red solo a través de `cache/`.
- Parches, no reescrituras. Respuesta: cambios (≤ 5 líneas) + tests + bloqueos.

## Mapa (objetivo)
`tesis/fuentes` (edgar, nasdaq, yahoo, tesoro) · `tesis/datos` (hechos, calendario, mapeo, segmentos, textos) · `tesis/verificacion` · `tesis/entradas` (asistente web) · `tesis/motor` (wacc, proyeccion, terminal, puente, escenarios, sensibilidad, reverse, multiplos, sotp, objetivo, excel, validacion) · `tesis/plantillas` · `tesis/qa` · `tesis/render` · `config/` · `docs/spec/`

## Specs
01 índice · 02 estilo · 03 datos y verificación · 04 entradas · 05 motor · 06 plantillas, QA y render · 07 regresiones

## Comandos (ajustar en F0)
`python -m tesis servir` · `python -m tesis documentos TICKER` · `python -m tesis generar TICKER --fecha AAAA-MM-DD` · `pytest -q`

## Estado
F0 ☐ · F1 ☐ · F2 ☐ · F3 ☐ · F4 ☐ · F5 ☐
