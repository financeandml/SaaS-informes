# 07 · Diagnóstico y regresiones

## Causas de fondo del generador actual (no repetir)
1. Plantilla y extractores hechos a medida de Netflix (filas de contenido, nota del split, «nunca ha pagado dividendos», regex con su redacción) aplicados a cualquier emisor.
2. Calendario fiscal supuesto a diciembre y etiquetas tomadas de `frame` (CYaaaaQn) de companyfacts.
3. Una sola etiqueta XBRL por partida, sin alternativas ni composición → N/A donde el dato existe, y N/A en cadena.
4. Valoración leída de un Excel por rótulos, sin motor ni recálculo, con entradas distintas de las oficiales.
5. Sin puerta de calidad: se emite con apartados vacíos, páginas en blanco y logs en el cuerpo.
6. Formulario ajeno al índice (numeración 33–36), con campos duplicados y sin validación; lo guardado no llega al informe.
7. Comparables por clasificación (SIC o industria), sin filtro de antigüedad ni de moneda.

## Fixtures
QCOM (informe 23/09/2026; ejercicio al último domingo de septiembre) y NFLX (17/09/2026; libro `Modelo_DCF_NFLX_Sergio_2026-09-15.xlsx`): congela en `tests/fixtures/` los documentos y las respuestas de API que ya guardó el generador actual, más unas `entradas.json` de prueba marcadas como tales. F7 añade un minorista con cierre en enero (p. ej. WMT) y una financiera (p. ej. JPM).

## Regresiones (una por test)
| id | Fase | Caso | Esperado |
|---|---|---|---|
| R1 | F1 | QCOM trimestres | «4T FY25» = 11.271 (calculado: 44.284 − 33.013), «1T FY26» = 12.252, «2T FY26» = 10.599, «3T FY26» = 9.947, con fecha de cierre; ninguna etiqueta de calendario |
| R2 | F1 | QCOM SG&A | Una línea: 3.110 · 2.759 · 2.483 (FY25–FY23); sin filas vacías de «Ventas y marketing» ni «Generales y administrativos» |
| R3 | F1 | QCOM patrimonio | 2021–2025 presentes; ROE, ROA y ROIC calculados en los 5 ejercicios |
| R4 | F1 | QCOM capex | FY2021 y FY2022 presentes |
| R5 | F1 | QCOM D&A trimestral | Por diferencia de acumulados → EBITDA de los 4 trimestres → EBITDA TTM, PER, EV/EBITDA y P/FCF TTM calculados |
| R6 | F1 | QCOM textos heredados | Dividendos pagados 3.805 M USD en FY25 → ninguna frase «nunca ha pagado»; ninguna nota de split; ninguna fila de contenido |
| R7 | F1 | QCOM auditor | PricewaterhouseCoopers LLP (dei:AuditorName del XBRL inline) |
| R8 | F1 | QCOM free float | dei:EntityPublicFloat |
| R9 | F1 | QCOM fundación y empleados | Propuesta 1985 con la cita «We incorporated in California in 1985» [10-K, pág. 4]; empleados propuestos desde el 10-K; el analista confirma |
| R10 | F2 | QCOM fechas | «Próximos resultados» 04/11/2026 (Nasdaq); nunca la call ya celebrada del 29/07/2026 |
| R11 | F2 | QCOM apartado 4 | En español (texto del analista); sin inglés en el cuerpo |
| R12 | F1 | QCOM nombre | «Qualcomm Incorporated» (sin «/De»); país «EE. UU.» |
| R13 | F6 | QCOM entrada | 130 USD el 22/09/2026 → rechazada (sesión 191,66–199,15) |
| R14 | F6 | QCOM recomendación | «Comprar» con potencial < 15 % o recorrido/riesgo < 1,5 → exige justificación |
| R15 | F3 | QCOM comparables | Solo los del analista; NOK (cuentas de 2017) y ERIC (en SEK) fuera de medianas y marcados |
| R16 | F2 | QCOM guía | Rangos «Business Outlook» de los últimos Ex. 99.1 como candidatos; tras confirmar, Cuadro 2 y apartado 26 completos |
| R17 | F2 | QCOM proxy | Accionistas ≥ 5 %, ejecutivos y Summary Compensation Table desde el HTML de la DEF 14A |
| R18 | F2 | QCOM segmentos | QCT/QTL (y líneas de QCT) y geografía desde XBRL dimensional; cuadre con el consolidado |
| R19 | F1 | Índice | Letras A–I seguidas, anclas parte-A…parte-I y ap-1…ap-39; formulario 27–30 |
| R20 | F7 | Cuerpo | Sin rutas, comandos, etiquetas XBRL ni mensajes de parser; 38 ≤ 1 página y detalle en `auditoria.json`; ninguna página < 25 % salvo fin de parte |
| R21 | F6 | Formulario → informe | Lo guardado aparece en portada y parte G; horizonte y tamaño se piden una vez |
| R22 | F3 | Precio único | Cierre oficial Nasdaq de fecha_valoracion en portada, 12–20 y H; nunca el intradía |
| R23 | F3 | NFLX Excel | Lectura por rangos con nombre o mapa de celdas, nunca por rótulo; ningún WACC = 0; cuadro de diferencias motor/libro |
| R24 | F3 | NFLX deuda neta | Puente con 5.181 M USD (14.309 − 9.128 a 30/06/2026; arrendamientos fuera); los 7.527 del libro solo en la comparación |
| R25 | F3 | NFLX precio | 75,31 (cierre 17/09/2026) en todo el informe; los 80,32 del libro solo en la comparación |
| R26 | F3 | NFLX objetivo | Un solo PO (motor); el consenso no entra en ninguna media |
| R27 | F3 | NFLX periodo parcial | FY2026 cuenta ≈ 105/365 desde el 17/09/2026 (el libro cuenta el año entero con caja a 30/06: doble cómputo) |
| R28 | F1 | NFLX split | Split 10:1 de noviembre de 2025 detectado desde los datos; histórico reexpresado; nota generada |
| R29 | F7 | NFLX cuadres | Formato es-ES en 38 (33.640 frente a 33.723 M USD) |
| R30 | F6 | Parte G vacía | Sin entradas de posición → no se emite; nunca «N/A — el analista no ha adjuntado…» |
| R31 | F3 | Horizonte | PO llevado a val.horizonte_meses; la parte G muestra el mismo horizonte |
| R32 | F7 | Financiera | JPM → bloqueo v1 con mensaje |
| R33 | F7 | Cierre en enero | WMT → etiquetas fiscales y 4T derivado correctos |
