# Emisión real: lo que aporta el analista, apartado por apartado

El SaaS lee solo SEC EDGAR, Nasdaq y el Tesoro (y Yahoo para la VI). Todo lo demás es del analista: juicio, cifras
propias y evidencias. Dos reglas atraviesan el asistente: toda cifra con unidad que escribe el analista es un Hecho del
informe (con su redondeo) o está en una evidencia suya, y toda evidencia se verifica contra el documento.

## 0. Una vez
- `.env` (copia de `.env.ejemplo`): `WC_SEC_CONTACTO="Nombre Apellido correo"` (EDGAR lo exige), `WC_PRECIO_FUENTE=nasdaq`
  y `WC_DATOS` (la carpeta `datos-tesis`).
- `python -m tesis servir` → http://127.0.0.1:8770.

## 1. Documentos (página «Expediente»)
| Documento | Cómo | Alimenta | Se cita en el asistente como |
|---|---|---|---|
| 10-K del último ejercicio (QCOM: FY2025, 05/11/2025) | «Traer de EDGAR» | C, 4, 24, evidencias | `10-K` |
| 10-Q del ejercicio en curso (QCOM: 1T–3T FY26; el último, 29/07/2026) | «Traer de EDGAR» | C trimestral, 26 | `10-Q AAAA-MM-DD` (el último) |
| Proxy DEF 14A (QCOM: la de 2026) | «Traer de EDGAR» | 5–6, trayectoria de CEO y CFO | `DEF 14A` |
| Notas de resultados, 8-K Ex. 99.1 (últimos 8 trimestres) | «Traer de EDGAR» | 2 (guía vigente), 26 (guía frente a real), citas de la dirección | `8-K AAAA-MM-DD` |
| Transcripción de la call (opcional; no está en EDGAR) | adjuntar el PDF | 26 (consenso) | todavía no es citable |
| Libro DCF propio (opcional) | paso 7, `excel.archivo` | contraste con el motor | — |

`AAAA-MM-DD` es la fecha de presentación en EDGAR. Si una evidencia cita un documento que no está, el bloqueo lista los
citables de esa emisión.

## 2. Cómo se cita (lo que más bloquea)
- `doc`: la clave exacta de la tabla. `pag`: el folio impreso en la página del documento de EDGAR (no el número del
  visor). `texto`: literal, copiado del documento (en inglés). `texto_es`: la versión en español que se imprime.
- Las cifras del literal tienen que estar en esa página; se admite una diferencia de forma (similitud ≥ 0,90), no de cifras.
- Textos propios: sin palabras vetadas, sin inglés, sin «N/A» ni «pendiente»; frases de hasta 35 palabras (aviso desde 40).

## 3. El asistente, paso a paso
| Paso | Apartados | Qué aporta el analista |
|---|---|---|
| 1 | portada, 1 | Analista; fecha del informe (la del día en que emite); fecha de valoración (último cierre de Nasdaq ≤ fecha del informe); tipo; nombre de presentación («Qualcomm»); sector: QCOM → «semiconductores» (el SIC 3663 propone «industrial») |
| 2 | puerta de calidad | En «Expediente»: resolver las discrepancias SEC frente a adjuntos y confirmar las cifras «solo documento» |
| 3 | 2–3 | Resumen (60–120 palabras), por qué ahora (20–60), visión frente al precio (30–80); 5 pilares: título, argumento, ≥ 2 evidencias, KPI, epígrafe literal del Item 1A que lo amenaza con su versión en español y catalizador |
| 4 | 4–7 | Descripción del negocio (80–200); confirmar segmentos; fundación y empleados con evidencia (10-K, *Human Capital*); trayectoria de CEO y CFO (20–60 cada una, con evidencia de la DEF 14A); asignación de capital (30–80); ≥ 3 catalizadores con fecha futura (AAAA-MM-DD o AAAA-Tn) y evidencia; 2–5 citas de la dirección (las del Ex. 99.1 valen) con `texto_es` |
| 5 | 21–23 | TAM (SAM y SOM opcionales) con valor, unidad, año, método y evidencia; ≥ 3 competidores (nombre, ticker, por qué, cuota); 3–10 comparables con 10-K en USD y su justificación; foso: tipo, evidencias, durabilidad y tendencia; amenazas (20–80) |
| 6 | 24–26 | 5 riesgos: epígrafe del Item 1A, versión en español, familia, probabilidad, impacto, mitigante y señal temprana; ≥ 3 disparadores del caso bajista (métrica, umbral, plazo, driver); guía a mano solo si falta; causas si un desvío supera el umbral |
| 7 | 12–20 | Año base, periodo explícito, mitad de año, horizonte, SBC, arrendamientos, ajustes del puente con evidencia; prima de riesgo de mercado **con fuente y fecha** (dato externo del analista); beta (regresión por defecto; *bottom-up* con fuente); prima específica (≠ 0 exige justificación); coste de la deuda (si es rendimiento de bonos, con fuente); tipo marginal (21 %); valor terminal; 3 escenarios con probabilidad, narrativa y series de crecimiento, margen EBIT, impuesto, D&A, capex, fondo de maniobra, SBC, g y RONIC o múltiplo |
| 8 | 27–30 | Recomendación (la regla la propone; si difiere, justificación ≥ 20 palabras); precio y fecha de entrada (dentro del rango de la sesión de Nasdaq); tamaño y por qué; argumento (80–150); 3–7 asunciones con driver y umbral; lista de comprobación; ≥ 3 criterios de invalidación; drawdown tolerado; ≥ 3 KPI con verde y rojo; fechas de revisión futuras; ≥ 3 criterios de salida |
| 9 | 2, portada | Tras el primer borrador: aceptar o editar, frase a frase, el párrafo factual que propone el sistema |

## 4. Emitir
1. «Guardar» en el asistente: las entradas quedan en la carpeta de la fecha del informe, que es la que emite el SaaS.
2. «Informe» → «Emitir»: con bloqueos sale «BORRADOR — NO EMITIDO» con la hoja 0.
3. Paso 9 (aceptar/editar) y los bloqueos de la hoja 0; volver a emitir hasta 0 bloqueos → «EMITIDO dd/mm/aaaa».
4. Si un bloqueo no se entiende o parece del sistema: enviar `<TICKER>_tesis_<fecha>.auditoria.json` (y la hoja 0).

## 5. Fuera de esta versión
Citas de la transcripción de la call; emisores sin 10-K (20-F); bancos, aseguradoras, REIT y biotecnológicas con menos de
50 mln USD de ingresos (bloqueo v1).
