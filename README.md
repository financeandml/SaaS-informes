# tesis — tesis de inversión de Warrants & Co.

SaaS local (http://127.0.0.1:8770) que produce la tesis de inversión de una empresa cotizada en EE. UU. con el índice fijo
de 39 apartados en nueve partes, A–I (`docs/spec/01_indice.yaml`). Solo fuentes oficiales —SEC EDGAR, Nasdaq y el Tesoro
de EE. UU.; Yahoo Finance únicamente para la volatilidad implícita, como excepción marcada—, motor de valoración propio,
las entradas del analista en un asistente de 9 pasos y ninguna IA en tiempo de ejecución. Todo en español.

Las reglas que no se negocian están en `CLAUDE.md`; los contratos, en `docs/spec/` (01 índice · 02 estilo · 03 datos y
verificación · 04 entradas · 05 motor · 06 plantillas, QA y render · 07 regresiones); el trabajo por fases, en `docs/fases/`.

## Uso

```
python -m tesis servir [--puerto 8770] [--sin-navegador]   # el SaaS: expediente → DCF → analista → informe
python -m tesis documentos TICKER                          # qué documentos pide el informe y cuáles están
python -m tesis generar TICKER --fecha AAAA-MM-DD          # emite el informe (es emitir.py, con sus mismas opciones)
python -m tesis regresiones                                # la tabla de 07 a partir de la batería
pytest -q                                                  # la batería entera, sin red
```

`.env` (copiar `.env.ejemplo`): `WC_SEC_CONTACTO` (nombre y correo que la SEC exige en el User-Agent; solo va a EDGAR),
`WC_PRECIO_FUENTE=nasdaq` y `WC_DATOS` (dónde viven `adjuntos/`, `entradas/` y `salida/`, fuera de la copia de trabajo).

## Cómo sale un informe

1. **Expediente.** El ticker se busca en EDGAR; se traen de la fuente los documentos que el analista no adjunta (10-K,
   10-Q, proxy, Ex. 99.1) y se contrasta cada cifra de la sección C con la SEC (confirmada · calculada con fórmula ·
   discrepante · solo SEC · sin dato; lo que la compañía no tiene no es un hueco).
2. **Analista.** El asistente (`/asistente?ticker=…`) se genera desde `04_entradas.yaml`: 9 pasos con sus validaciones
   (palabras, citas verificadas con su página, linter de textos, precio de entrada dentro de la sesión de Nasdaq…).
   Guarda `entradas/<TICKER>/<fecha>/entradas.json` con versiones; `posiciones/` solo se lee, para migrarla.
3. **Motor.** WACC con el tipo del Tesoro y beta frente al SPY, proyección con periodo parcial, valor terminal, puente,
   tres escenarios, sensibilidad, DCF inverso y comparables del analista; exporta un Excel con fórmulas vivas.
4. **Informe.** HTML con el detalle de cada cifra al pasar el ratón y PDF A4 paginado. Antes, la puerta de calidad
   (06 §3): con algún bloqueo sale «BORRADOR — NO EMITIDO» con la hoja 0 de bloqueos; con cero, «EMITIDO dd/mm/aaaa».
   El detalle técnico va a `<informe>.auditoria.json`, nunca al cuerpo.

## Mapa del código (`tesis/`)

Un subpaquete por responsabilidad, en el orden del flujo; cada `__init__.py` dice qué contiene.

| Subpaquete | Módulos |
|---|---|
| `fuentes/` | `sec` (EDGAR: companyfacts, submissions, depósitos, calendario fiscal), `edgar` (trae al expediente los documentos no adjuntos), `precio` (cierre oficial y sesiones de Nasdaq), `calendario` (próxima presentación, dividendos, sorpresas), `posicionamiento` (cadena, 13F, directivos, cortos y VI), `tesoro`, `yahoo` (solo VI) |
| `datos/` | `hechos`, `campos`, `derivados`, `expediente`, `documentos`, `extractor`, `recortes`, `tablas_html`, `ixbrl`, `segmentos`, `ficha`, `gobierno`, `proxy`, `item1a`, `guia`, `guidance` |
| `verificacion/` | `contraste` (SEC frente a adjuntos), `auditor` (identidades), `revision` (doble comprobación de lo impreso) |
| `entradas/` | el paquete (`Entradas`, carga, citas y comprobaciones por paso), `asistente` + `web/tablero/asistente.*`, `propuestas` (06 §1), `tarjetas` + `config/evidencias.yaml` |
| `motor/` | `supuestos`, `proyeccion`, `terminal`, `puente`, `wacc`, `escenarios`, `sensibilidad`, `comparables`, `multiplos`, `sector`, `excel`, `datos` |
| `plantillas/` | `indice`, `informe`, `parte_a` (1–3) · `parte_b` (4–7) · C en `informe` y `secciones` (8–11) · `parte_d` (12–20) · `parte_e` (21–23) · `parte_f` (24–26) · `parte_g` (27–30) · `parte_h` y `secciones` (31–35) · `parte_i` (36–39), `frases` + `config/frases.yaml`, `graficos`, `maqueta/` |
| `qa/` | el paquete (puerta de calidad, 06 §3) y `linter` + `config/estilo.yaml` (06 §2) |
| `render/` | el paquete (HTML y PDF paginado, 06 §4) e `imprimir` (Chromium en proceso aparte) |
| `web/` | `saas` + `tablero/` (CSP estricta, sin `innerHTML`, solo en español) |
| `heredado/` | el camino anterior al asistente: `agregador`, `comparables`, `mercado_objetivo`, `regiones`, `riesgos`, `historial`, `cartas`, `dcf` |

Transversales en la raíz del paquete: `entorno` (configuración y carpetas de datos), `rutas` (dónde está cada cosa del
repositorio), `umbrales`, `formato` (cifras y fechas es-ES) y `rotulos` (traducciones y fallos de red en español).
Umbrales solo en `config/*.yaml`. Lo de `heredado/` aún lo llaman `emitir.py`, `plantillas.informe`,
`plantillas.secciones` y `web.saas`, y sus pruebas solo corren con los adjuntos de NFLX/QCOM (las 34 omitidas); una prueba
impide que otro módulo empiece a depender de él. Retirarlo es F9.

## Pruebas

Sin red: `tests/fixtures/cache_sec/` (QCOM, NFLX, WMT, JPM), `tests/fixtures/cache_bolsa/` (Nasdaq y Yahoo) y
`tests/fixtures/<TICKER>/entradas.json` (entradas de prueba, que nunca dan «EMITIDO»). Cada prueba nueva se ha visto
fallar al reintroducir el fallo que caza (CLAUDE.md, regla 16). Estado: `docs/fases/` y la sección «Estado» de `CLAUDE.md`.

## Desarrollo desde el repositorio

```
git clone <url> && cd <carpeta>
python -m venv .venv && .venv\Scripts\activate            # Windows (en Linux/macOS: source .venv/bin/activate)
pip install -r requirements.txt
python -m playwright install chromium
copy .env.ejemplo .env                                     # y rellenar WC_SEC_CONTACTO (nombre y correo, lo exige la SEC)
pytest -q                                                  # la batería, sin red: ~10 min; `-m "not lenta"` para iterar
```

- **Reglas.** `CLAUDE.md` (las del SaaS) y `docs/CLAUDE_warrants.md` (las de Warrants & Co., que hereda). Los contratos, en
  `docs/spec/`; el estado y lo siguiente, en `CLAUDE.md › Estado`; el plan de corrección de la auditoría del 27/09/2026 (78
  fallos, uno por prueba en `tests/prueba_auditoria_27_09.py`, `pytest -m auditoria`), en `docs/fases/A.md`.
- **Datos de ejemplo.** `datos-tesis/` es una instantánea (29/09/2026) de los datos de trabajo: adjuntos de AAPL, NFLX,
  ORCL y QCOM (documentos públicos de la SEC y de las compañías), las entradas del analista y los informes emitidos. Con
  `WC_DATOS=./datos-tesis` en `.env`, el SaaS arranca con ellos. Las pruebas de la auditoría necesitan esos adjuntos.
- **Modelos y posiciones.** `dcf/` (libros DCF del analista, solo lectura para el programa) y `posiciones/` (solo se leen
  para migrarlas). `Claude outputs/` guarda informes de control.
- **Cachés.** `cache_sec/` y `cache_bolsa/` no se versionan: crecen con cada consulta y se rehacen solas con red. Las
  pruebas usan las respuestas congeladas de `tests/fixtures/`.
