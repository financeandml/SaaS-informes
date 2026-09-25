# F0 · Auditoría (24/09/2026)

40 módulos, 11.145 líneas en `tesis/`; 23 ficheros de prueba, 3.518 líneas, **207 en verde** sin red externa. Ningún módulo se ha borrado ni movido: esto solo los clasifica.

## Reutilizar (pasan sus pruebas y no son causa de 07)
| Módulo | Destino |
|---|---|
| `sec.py` (EDGAR, companyfacts, calendario fiscal real, suma de conceptos) | `fuentes/edgar` + `datos/calendario` |
| `fuentes.py` (traer de la fuente lo no adjuntado), `entorno.py` | `fuentes/` |
| `precio.py` (cierre oficial Nasdaq), `posicionamiento.py` (opciones, 13F, insiders, cortos), `agregador.py` + `yahoo.py` (IV, marcada) | `fuentes/nasdaq`, `fuentes/yahoo` |
| `extractor.py` (pdfium: rótulo, periodo, página, rectángulo), `expediente.py` (clasifica adjuntos), `recortes.py` | `datos/textos` |
| `render.py`, `imprimir.py`, `graficos.py`, `formato.py`, `maqueta/` | `render/` |
| `saas.py`, `tablero/` (servidor local, CSP estricta) | `entradas/` |

## Rehacer (causa de 07 o el contrato cambia)
| Módulo | Por qué | Reg. |
|---|---|---|
| `hechos.py` | Hecho sin `id` ni `estado` del 03 §2; hoy capa/certeza/origen | R-todas |
| `campos.py` | mapeo XBRL con alternativas y composición: existe a medias, falta dimensional | R3–R5, R18 |
| `contraste.py`, `auditor.py`, `revision.py` | tres puertas de verificación solapadas → una sola `verificacion/` | R1–R9 |
| `informe.py`, `secciones.py`, `documentos.py` | 38 apartados escritos a mano; el índice son 39 y debe generarlos | R19, R20 |
| `formulario.py` + `tablero/formulario.*` | ajeno al índice (causa 6); debe salir de `04_entradas.yaml` | R13, R21 |
| `dcf.py` | lee el Excel del analista por rótulos (causa 4); pasa a motor interno y el libro solo contrasta | R23–R27 |
| `multiplos.py`, `derivados.py` | absorbidos por `motor/` (única fuente de la valoración) | R5, R22 |
| `comparables.py` | por clasificación, sin filtro de antigüedad ni moneda (causa 7) | R15 |
| `ficha.py`, `gobierno.py`, `regiones.py`, `riesgos.py`, `guidance.py`, `cartas.py`, `historial.py`, `mercado_objetivo.py`, `calendario.py` | extractores con redacción de emisor dentro (causa 1); deben proponer cita al analista | R6, R9, R16, R17 |
| `posicion.py` | a `entradas.json` versionado con tarjetas de evidencia | R21, R30 |

## Borrar
`narrativa.py`, `emitir.py --redactar`, el SDK `anthropic` y `narrativas/`: IA en tiempo de ejecución, prohibida. Restos: `o.json`, `q.json`, `prueba_nflx/`, `docs/PLANTILLA_TESIS.md` (lo sustituyen 01 y 02).

## Fixtures
`tests/fixtures/cache_sec/` 46 respuestas congeladas (2,8 MB): companyfacts y submissions de **QCOM, NFLX, WMT y JPM** y los Ex. 99.1 de QCOM y NFLX. Leídas con `WC_SEC_CONTACTO` vacío —sin contacto no hay descarga posible— las cuatro resuelven: QCOM cierra el 0927, WMT el 0131 (R33), JPM es SIC 6021, banca comercial (R32). Además `dcf/` (libro NFLX), `posiciones/` y `tests/expediente_nflx.json`. La caché de trabajo `cache_sec/` (120 respuestas) no se versiona.

## Bloqueos: resueltos (24/09/2026)
1. `pytest` 9.1.1 instalado **sin jubilar `unittest`**: `pytest.ini` le enseña a recorrer `prueba_*.py`; los dos corredores dan 207.
2. `tesis/__main__.py` con `servir · documentos · generar`: los dos primeros delegan en `tesis.saas` y en `emitir.py` pasándoles las opciones tal cual, así que lo antiguo manda; `documentos TICKER` es lo único nuevo y sale del catálogo.
3. `adjuntos/` y `salida/` movidos a `PROYECTOS VERANO/datos-tesis/` (761 ficheros, 279 MB verificados antes de borrar el origen); los sitúa `WC_DATOS` vía `entorno.carpeta` y sin la variable vuelven a la raíz. El repositorio baja a 43 MB.

## F7 · cierre (25/09/2026)
Retirados con «confirmo borrar»: `formulario.py`, `tablero/formulario.{html,js}`, `posicion.py` y sus pruebas (el asistente
de 04 los sustituye; `posiciones/` solo se lee para migrar). Siguen los del camino anterior que `emitir.py` aún llama
(varios solo alimentan el informe sin entradas del asistente) y cuyas pruebas solo corren con los adjuntos: `regiones`,
`guidance`, `cartas`, `historial`, `riesgos`, `mercado_objetivo`, `comparables`, `dcf` y `auditor`; `derivados` (sección C) y
`multiplos` (cuadro de 17) siguen en uso sin absorberse en `motor/`; `agregador` queda sin llamada (regla 6). Retirarlos
es trabajo aparte.

## F8 · orden del backend (25/09/2026)
`tesis/` pasa de 63 módulos sueltos a un subpaquete por responsabilidad (cada `__init__.py` dice qué contiene; mapa en
`README.md` y `CLAUDE.md`). Solo se mueve: ninguna función cambia de comportamiento (misma batería, 33 de 33 regresiones y
todas las mutaciones cazadas antes y después), salvo `recalcular_con_excel`, que pasa de `dcf` a `motor/excel` para que el
motor no dependa de lo heredado. Las rutas del repositorio salen de `tesis/rutas.py`: movidos, `sec.py` y `saas.py` habrían
apuntado la caché de EDGAR y la carpeta de `emitir.py` dentro del paquete, y las pruebas, que desvían la caché, no lo veían.

| Antes (`tesis/…`) | Ahora (`tesis/…`) |
|---|---|
| `sec`, `precio`, `calendario`, `posicionamiento`, `tesoro`, `yahoo` | `fuentes/` (mismo nombre) |
| `fuentes.py` | `fuentes/edgar.py` |
| `hechos`, `campos`, `derivados`, `expediente`, `documentos`, `extractor`, `recortes`, `tablas_html`, `ixbrl`, `segmentos`, `proxy`, `gobierno`, `ficha`, `item1a`, `guia`, `guidance` | `datos/` |
| `contraste`, `auditor`, `revision` | `verificacion/` |
| `entradas.py` · `asistente`, `propuestas`, `tarjetas` | `entradas/__init__.py` · `entradas/` |
| `multiplos` | `motor/` |
| `informe`, `indice`, `frases`, `graficos`, `secciones`, `parte_a`…`parte_i`, `maqueta/` | `plantillas/` |
| `qa.py` · `linter` | `qa/__init__.py` · `qa/` |
| `render.py` · `imprimir` | `render/__init__.py` · `render/` (`python -m tesis.render.imprimir`) |
| `saas`, `tablero/` | `web/` (`python -m tesis servir` o `python -m tesis.web.saas`) |
| `agregador`, `comparables`, `mercado_objetivo`, `regiones`, `riesgos`, `historial`, `cartas`, `dcf` | `heredado/` |
| `entorno`, `umbrales`, `formato`, `rotulos` | sin cambio; nuevo `rutas` |

