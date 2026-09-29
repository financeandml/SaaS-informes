# B · Cualquier emisor y sistema por puntos (28/09/2026)
Origen: petición del analista del 28/09/2026 —«que cualquier analista lo descargue y trabaje en su localhost; informes
sin errores de cualquier empresa; un sistema por puntos que genere correctamente cada apartado, sin dogmatizar,
estructurado por las partes del índice»— con tres informes de IEAF Lighthouse (Bytetravel, Treelogic y Redegal, BME
Growth) para contrastar datos.

## Decisiones (delegadas por el analista: «los cambios que consideres necesarios»)
1. **Emisores españoles por la API oficial de BME** (bolsa: regla 6), sin dependencias nuevas: buscador, ficha del
   valor, histórico oficial de cierres (regla 4), índices, cuentas anuales, semestrales, información privilegiada y
   «otra información relevante» (`tesis/fuentes/bme.py`). Clave del emisor: su ticker de BME con «.MC» (`RDG.MC`).
2. **Tipo sin riesgo en EUR: curva AAA del BCE a 10 años** (`tesis/fuentes/bce.py`). **Beta frente al índice oficial
   de BME** del segmento del valor (`config/mercados.yaml`: IBEX Growth Market All Share o IBEX 35).
3. **Cifras de las cuentas en PDF** (capa documento, con página y recorte). Sin SEC, el contraste es documento contra
   documento: la columna comparativa de las cuentas del año siguiente o el balance comparativo del semestral. Dos
   documentos que coinciden → «◑» con certeza alta; que difieren → «≠» y decide el analista.
4. **Moneda del emisor** en toda cifra y rótulo (regla 13: la cifra y su unidad, de la misma fuente).
5. **Periodicidad semestral**: «1S25», «2S25» (2S = ejercicio − 1S, derivado) y UDM = ejercicio + 1S − 1S anterior.
6. **Sistema por puntos**: cada apartado de `docs/spec/01_indice.yaml` declara sus puntos (sustituyen a «bloques»);
   cada punto queda en **cumple · no aplica (motivo) · falta (motivo)**. Lo que el mercado del emisor no publica
   (opciones, 13F, Form 4, consenso…) es «No aplica» con su motivo (`tesis/fuentes/emisores.py › Perfil`), nunca un
   fallo ni un relleno. La puerta de calidad bloquea por punto que falta y la hoja 0 los agrupa por apartado.
7. **Los informes de IEAF son oráculo de prueba, nunca fuente** del informe (regla 6): sus cifras históricas publicadas
   se usan para afirmar que el SaaS lee bien las cuentas oficiales (`tests/fixtures/lighthouse/`).
8. Sin plazo reglamentario inventado: la próxima presentación de un emisor de BME es la que el emisor anuncie o el
   analista cite.

## Partes
| Parte | Qué | Ficheros principales |
|---|---|---|
| B1 | Perfil de emisor y fuentes oficiales de España | `fuentes/emisores.py`, `fuentes/bme.py`, `fuentes/bce.py`, `config/mercados.yaml`, `config/fuentes.yaml`, `fuentes/sec.py › Emisor` |
| B2 | Lectura de cuentas españolas (PGC y NIIF, modelo normalizado y libre), expediente y contraste documental | `datos/extractor.py`, `datos/campos.py`, `datos/expediente.py`, `verificacion/contraste.py`, `datos/derivados.py`, `verificacion/auditor.py` |
| B3 | Sistema por puntos: spec, evaluador, puerta y hoja 0 | `docs/spec/01_indice.yaml`, `plantillas/indice.py`, `plantillas/puntos.py`, `qa/__init__.py`, `render/__init__.py` |
| B4 | Motor y mercado en EUR y semestral | `motor/datos.py`, `motor/multiplos.py`, `fuentes/precio.py` |
| B5 | Tubería de emisión por perfil y apartados que no aplican | `emitir.py`, `datos/ficha.py`, `datos/gobierno.py`, `datos/documentos.py`, `fuentes/posicionamiento.py`, `fuentes/calendario.py` |
| B6 | Plantillas adaptativas (moneda, semestres, «No aplica») | `plantillas/informe.py`, `plantillas/parte_*.py`, `plantillas/maqueta/tesis.html`, `formato.py` |
| B7 | Web: buscador de los dos mercados, documentos de BME, panel «Estado por apartados» | `web/saas.py`, `web/tablero/*` |
| B8 | Contraste con los informes de ejemplo y entradas de ejemplo de las tres empresas | `tests/fixtures/lighthouse/`, `datos-tesis/entradas/*.MC/` |
| B9 | Fallos de la auditoría del 27/09 pendientes (plan A) | `docs/fases/A.md` |
| B10 | Cierre: batería, regresiones, emisiones de control, documentación y publicación | `README.md`, `CLAUDE.md` |

## Aceptación
- `RDG.MC`, `TRTK.MC` y `BYTE.MC` se buscan en la web, traen sus documentos de BME, se contrastan y se emiten a PDF.
- Las cifras históricas publicadas de los tres informes de IEAF coinciden con las que el SaaS lee de las cuentas
  oficiales, al redondeo impreso del informe de IEAF (o la diferencia queda explicada en la prueba).
- Cada apartado de los siete informes de control (AAPL, NFLX, ORCL, QCOM y las tres españolas) sale con todos sus
  puntos en «cumple» o «no aplica» con motivo; lo que falta, en la hoja 0 por apartado.
- Batería completa y regresiones en verde; los informes de EE. UU. no pierden nada de lo que ya imprimían.

## Estado (29/09/2026)
- B1 ☑ perfil de emisor, BME (buscador, ficha del valor, cierres, índices, documentos) y BCE.
- B2 ☑ cuentas españolas: modelo normalizado y libre, consolidadas antes que individuales, semestres, 2S derivado,
  reexpresiones (manda el documento más reciente), capex y deuda financiera como suma de sus partes publicadas;
  `tests/prueba_extraccion_es.py` contra las cifras publicadas por IEAF (oráculo) de las tres empresas.
- B3 ☑ sistema por puntos en `01_indice.yaml` + `plantillas/puntos.py`; la puerta bloquea por apartado y punto.
- B4 ☑ motor y mercado en EUR: cierre oficial de BME, beta frente al índice de BME del segmento, rf del BCE, UDM
  semestral, tipo marginal por mercado (`config/mercados.yaml`), acciones admitidas cuando no hay dilución publicada.
- B5 ☑ tubería por mercado: `emitir.py RDG.MC` de principio a fin; ficha (auditor con ROAC, constitución), accionistas
  de las participaciones significativas, ejecutivos y filiales del analista con su cita (paso 4; cierra el fallo 74).
- B6 ☑ plantillas con el léxico del mercado (`plantillas/lexico.py`): moneda, bolsa, cuentas, rf y beta; sin columnas
  ni filas de lo que la compañía no publica; «No aplica» con motivo en 2 (Cuadro 2), 26 y 31–35.
- B7 ☑ web: buscador de los dos mercados, «Traer de la fuente oficial» (EDGAR o BME), catálogo de documentos de BME.
- Pendiente: B8 entradas de ejemplo de las tres empresas españolas; B9 los fallos de la auditoría del 27/09 que siguen
  abiertos (plan A); segmentos por actividad de la memoria, operaciones de directivos de BME como cuadro, comparables de
  BME en el apartado 22, documentos del Mercado Continuo (CNMV no responde: se adjuntan).
