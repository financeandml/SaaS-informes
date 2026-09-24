# 03 · Fase 1 — Documentos, datos y verificación

## 1. Documentos
| Documento | Origen | Obligatorio | Apartados |
|---|---|---|---|
| 10-K último + Exhibit 21 | EDGAR + PDF del analista | sí | 1, 4–6, 8–11, 24 |
| 10-Q posteriores al 10-K | EDGAR + PDF | todos | 8–11 |
| 8-K de resultados (Item 2.02, Ex. 99.1) | EDGAR | los 8 últimos (mín. 4) | 2, 7, 26 |
| DEF 14A última | EDGAR + PDF | sí | 5, 6, 34 |
| SC 13D/13G vigentes y Forms 4 de 12 meses | EDGAR (automático) | — | 5, 33, 34 |
| Transcripción de la última call | analista | sí, salvo `docs.sin_call` | 2, 7, 21–23 |
| Presentación a inversores, informes de terceros | analista | no | 7, 21–22 |

- El sistema arma la lista desde `submissions` de EDGAR y descarga lo que está en EDGAR. El analista sube los PDF (para paginar y recortar) y lo que no está en EDGAR.
- PDF de un filing SEC: se identifica (tipo, periodo, fecha, nº de registro) y se compara con el HTML de EDGAR (similitud ≥ `umbrales.pdf_vs_edgar_similitud_min` en los estados financieros); si no cuadra → bloqueo.
- Documento no SEC: fecha y emisor coherentes con el 8-K del periodo. Sus cifras se casan con Hechos SEC cuando es posible (→ `confirmado`); si no, quedan `solo_documento`.
- Fuera de alcance v1 (20-F/40-F, moneda ≠ USD, financieras, REIT, biotech sin ingresos): bloqueo con mensaje.

## 2. Hecho (modelo único de dato)
`Hecho{id, concepto, valor, unidad, escala, periodo{inicio, fin, tipo, etiqueta_fiscal, fecha_cierre}, fuente{tipo: xbrl|html|pdf|api|analista|motor, documento, registro, etiqueta, contexto, pagina, bbox, cita}, contrastes[{fuente, valor, delta, ok}], estado, formula, dependencias}`

Estados: `confirmado` (documento = SEC) · `solo_sec` (XBRL oficial; válido sin acción) · `calculado` · `solo_documento` (lo reconoce el analista) · `supuesto` (analista) · `estimacion` (motor) · `no_publicado` (motivo técnico solo en auditoría) · `discrepante` (bloquea).
Contraste: igualdad a la escala publicada (± media unidad del último dígito).
El render solo imprime números con `h(id)`; un número sin Hecho hace fallar el QA.

## 3. Calendario fiscal
- Periodos según `fy`/`fp`/fechas de cada filing y las DEI (`DocumentFiscalYearFocus`, `DocumentFiscalPeriodFocus`, `CurrentFiscalYearEndDate`). **Prohibido** usar `frame` (CYaaaaQn) de companyfacts para etiquetar o elegir periodos, y suponer cierre en diciembre.
- Etiqueta siempre fiscal («4T FY25») con fecha de cierre; se describen los años de 52/53 semanas.
- Los flujos de los 10-Q son acumulados: trimestre = acumulado − acumulado anterior. 4T = ejercicio − 9 meses (`calculado`). Balance = saldo al cierre.
- BPA del 4T derivado = beneficio del 4T / (4 × acciones medias anuales − suma T1–T3), `calculado`.
- Reexpresiones: para cada periodo, el valor del filing más reciente; cambios > 0,5 % → nota.
- Splits: detectados por los datos (DEI, 8-K, salto de acciones); se reexpresan acciones y cifras por acción; la nota se genera con la fecha y el ratio detectados.

## 4. Mapeo XBRL con alternativas (`config/mapeo_xbrl.yaml`)
Orden por concepto: etiquetas en cascada → composición → línea del estado en el propio filing (`Financial_Report.xlsx` o R*.htm, extensiones del emisor incluidas) → `no_publicado` con las etiquetas probadas (solo en auditoría).

| Concepto | Cascada mínima |
|---|---|
| ingresos | RevenueFromContractWithCustomerExcludingAssessedTax → Revenues → RevenueFromContractWithCustomerIncludingAssessedTax → SalesRevenueNet |
| coste de ventas | CostOfRevenue → CostOfGoodsAndServicesSold → CostOfGoodsSold (+ CostOfServices) |
| SG&A | SellingGeneralAndAdministrativeExpense → SellingAndMarketingExpense + GeneralAndAdministrativeExpense (se imprime como lo publique la compañía) |
| I+D | ResearchAndDevelopmentExpense → ResearchAndDevelopmentExpenseExcludingAcquiredInProcessCost |
| EBIT | OperatingIncomeLoss |
| D&A (flujos) | DepreciationDepletionAndAmortization → DepreciationAndAmortization → DepreciationAmortizationAndAccretionNet → Depreciation + AmortizationOfIntangibleAssets |
| retribución en acciones | ShareBasedCompensation → AllocatedShareBasedCompensationExpense |
| patrimonio | StockholdersEquity → StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest − MinorityInterest |
| capex | PaymentsToAcquirePropertyPlantAndEquipment → PaymentsToAcquireProductiveAssets (+ software capitalizado según paquete) |
| deuda | LongTermDebtNoncurrent, LongTermDebtCurrent, ShortTermBorrowings, CommercialPaper, DebtCurrent (sin doble cómputo) |
| caja / inversiones CP | CashAndCashEquivalentsAtCarryingValue / MarketableSecuritiesCurrent → ShortTermInvestments → AvailableForSaleSecuritiesDebtSecuritiesCurrent |
| dividendos / recompras | PaymentsOfDividends → PaymentsOfDividendsCommonStock / PaymentsForRepurchaseOfCommonStock |

- Numéricos de 5 ejercicios desde `companyfacts`; los adjuntos contrastan los años que cubren.
- DEI de texto (AuditorName, EntityIncorporationStateCountryCode, dirección) desde el XBRL inline del 10-K: `companyfacts` solo trae numéricos (EntityPublicFloat, EntityCommonStockSharesOutstanding).

## 5. Segmentos y geografía
Del XBRL inline del 10-K/10-Q (hechos con `StatementBusinessSegmentsAxis`, `ProductOrServiceAxis`, `StatementGeographicalAxis`, `ConsolidationItemsAxis`). Cuadre: segmentos + eliminaciones = consolidado; si no cuadra, nota con la diferencia en formato es-ES.

## 6. Textos (sin IA; el analista confirma)
- El HTML de EDGAR se trocea por Items (saltando el índice). Cada fragmento se localiza en el PDF por texto normalizado → página + bbox para la cita y el recorte.
- Item 1A: epígrafes por tipografía (negrita/cursiva), literales, con página.
- DEF 14A: tablas con `read_html` + puntuación por cabeceras (propiedad, ejecutivos, Summary Compensation). Por debajo del umbral → el asistente pide el dato con cita.
- Guía: en cada Ex. 99.1, secciones «Outlook / Guidance / Forecast / Business Outlook» y rangos numéricos junto a métricas (ingresos, BPA GAAP/no GAAP, márgenes) → candidatos que el analista confirma; sin candidatos → entrada manual con cita.
- Tarjetas de evidencia: ventanas de texto por palabras clave de cada apartado (`config/evidencias.yaml`: competencia, moat, TAM, estrategia, catalizadores, empleados, fundación, dividendos, segmentos). Se proponen; nunca se imprimen solas.
- Prohibido cualquier patrón escrito para la redacción de un emisor o de un proveedor de transcripciones concreto.
- Cita manual (documento + página + texto): válida si el texto normalizado aparece en esa página (similitud ≥ `umbrales.cita_similitud_min`) y sus cifras coinciden.

## 7. Datos de mercado
- Precio único del informe: cierre oficial Nasdaq de `fecha_valoracion` (último día hábil ≤ fecha del informe). Nunca intradía.
- Nasdaq: histórico de 5 años (beta, volatilidad y múltiplos históricos; SPY como mercado), cadena de opciones, 13F (marcado «dato de la bolsa, no cruzado con EDGAR»), insiders (cruzados con el Form 4), cortos, fecha de resultados y consenso.
- Tesoro de EE. UU.: curva par diaria, 10 años, en `fecha_valoracion`.
- Yahoo (excepción): IV por contrato; se usa por vencimiento solo si su OI total cuadra con Nasdaq (`umbrales.tolerancia_oi_yahoo_nasdaq`).
- Cada respuesta se guarda completa con URL, hora y sha256; caché por URL+fecha. EDGAR: User-Agent con correo y ≤ 10 peticiones/s.

## 8. Salidas
`datos.json` (Hechos) · `auditoria.json` (todas las comprobaciones) · pantalla de verificación: recuento por estado, discrepancias (decide el analista; por defecto rige SEC), huecos con motivo y reconocimiento de `solo_documento`.
