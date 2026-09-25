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

| Parte | Módulos |
|---|---|
| Fuentes | `sec.py` (EDGAR, companyfacts, calendario fiscal), `fuentes.py`, `precio.py` (cierre oficial y sesiones de Nasdaq), `tesoro.py`, `yahoo.py` (solo VI), `posicionamiento.py` (cadena, 13F, directivos, cortos) |
| Datos | `hechos.py`, `campos.py`, `contraste.py`, `derivados.py`, `segmentos.py`, `ixbrl.py`, `guia.py`, `item1a.py`, `calendario.py`, `gobierno.py`, `proxy.py`, `ficha.py` |
| Entradas | `entradas.py`, `asistente.py` + `tablero/asistente.*`, `tarjetas.py` + `config/evidencias.yaml`, `linter.py` + `config/estilo.yaml` |
| Motor | `motor/` (supuestos, proyeccion, terminal, puente, wacc, escenarios, sensibilidad, comparables, excel, datos) |
| Partes | `parte_a.py` (1–3) · `parte_b.py` (4–7) · C en `informe.py` y `secciones.py` (8–11) · `parte_d.py` (12–20) · `parte_e.py` (21–23) · `parte_f.py` (24–26) · `parte_g.py` (27–30) · `parte_h.py` y `secciones.py` (31–35) · `parte_i.py` (36–39) |
| Salida | `informe.py`, `frases.py` + `config/frases.yaml`, `maqueta/`, `render.py`, `qa.py`, `revision.py` |
| SaaS | `saas.py` + `tablero/` (CSP estricta, sin `innerHTML`, solo en español) |

Umbrales solo en `config/*.yaml`. Quedan módulos del camino anterior al asistente (`regiones`, `guidance`, `cartas`,
`historial`, `riesgos`, `mercado_objetivo`, `comparables`, `dcf`, `multiplos`, `agregador`…): `emitir.py` aún llama a
algunos y sus pruebas solo corren con los adjuntos de NFLX/QCOM (las 34 omitidas); retirarlos es trabajo aparte.

## Pruebas

Sin red: `tests/fixtures/cache_sec/` (QCOM, NFLX, WMT, JPM), `tests/fixtures/cache_bolsa/` (Nasdaq y Yahoo) y
`tests/fixtures/<TICKER>/entradas.json` (entradas de prueba, que nunca dan «EMITIDO»). Cada prueba nueva se ha visto
fallar al reintroducir el fallo que caza (CLAUDE.md, regla 16). Estado: `docs/fases/` y la sección «Estado» de `CLAUDE.md`.
