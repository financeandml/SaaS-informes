# Plantilla 1 — Tesis de inversión

Fecha: 2026-09-16 · Estado: **borrador para decidir**, sin código.

Referencia de **formato**: un informe de inicio de cobertura de una casa de análisis
(portada con ficha y tablas, «en una página», capítulos, cifras clave, anexos). Se toma
la maqueta —densidad, tablas, gráficos, notas de fuente al pie de cada cuadro—, no el
contenido, ni la empresa, ni la marca.

El **índice** es el propio del producto (§3). Este documento cubre las secciones A–C
(apartados 1–11); las siguientes se añadirán cuando se reciban.

Restricciones fijadas:

1. **Fuente primaria de datos, la SEC (EDGAR)**, para empresas que presentan
   10-K/10-Q. Empresas fuera de EE. UU.: pendiente, fuera de este documento.
2. **El analista adjunta siempre tres ficheros** por informe: cuentas anuales,
   trimestrales y *guidance* (este último, salvo que esté dentro de los anteriores).
3. **El sistema contrasta cada dato** obtenido de la SEC contra los adjuntos, y cada
   dato que solo esté en los adjuntos contra la SEC. Ninguna cifra entra en el informe
   sin su estado de contraste a la vista (§5).
4. **Lo que ni la SEC ni los adjuntos tengan se pide al analista**, aunque sea una sola
   cifra; nunca se estima, nunca se deja pasar en silencio (§6).
5. **El informe integra imágenes de los adjuntos** donde corresponda: recortes de la
   página exacta de donde sale una tabla o una figura, con fichero y página al pie (§7).

---

## 1. Las capas: de dónde viene cada cifra

| Capa | Qué es | Quién la produce | Cómo se rotula |
|---|---|---|---|
| **Hecho SEC** | dato publicado en un formulario SEC, con concepto XBRL o cita textual | adaptador SEC | fuente, formulario, fecha de presentación, enlace |
| **Hecho de documento** | dato leído por el sistema en un adjunto del analista | extractor, con `certeza` | «según <fichero>, pág. N», con el recorte de la página |
| **Supuesto** | estimación o decisión del analista | el analista | «estimación del analista», con fecha y autor |
| **Derivado** | cálculo determinista sobre hechos y supuestos | motor de cálculo | fórmula visible y lista de entradas |

Un *guidance* de la compañía es **hecho de documento**, no supuesto: es lo que la
empresa dijo, con su fecha. Se rotula «objetivo de la compañía», nunca «estimación».

Y un quinto estado que no es capa sino ausencia: **N/A con motivo**. Solo se llega a
él después de buscar en la SEC, buscar en los adjuntos y preguntar al analista (§6).

---

## 2. Qué publica la SEC y por dónde se accede

Todo público, sin clave, de dominio público, con `User-Agent` identificativo
obligatorio (nombre y correo) y límite de 10 peticiones/segundo. Cuatro sub-adaptadores:

| Sub-adaptador | Punto de entrada | Qué da |
|---|---|---|
| `identidad` | `www.sec.gov/files/company_tickers.json` · `data.sec.gov/submissions/CIK##########.json` | ticker → CIK; nombre, bolsa, SIC, estado de constitución, cierre fiscal, dirección, lista de formularios presentados |
| `hechos_xbrl` | `data.sec.gov/api/xbrl/companyfacts/CIK##########.json` | todos los conceptos US-GAAP y DEI por periodo, con formulario y fecha de presentación, **anuales (10-K) y trimestrales (10-Q)**. Sin dimensiones: no trae segmentos ni geografías |
| `segmentos` | *Financial Statement and Notes Data Sets* o el instance XBRL del 10-K | los mismos conceptos **con ejes** (segmento, geografía, producto) |
| `documentos` | `www.sec.gov/Archives/edgar/data/<CIK>/<accn>/` · búsqueda `efts.sec.gov/LATEST/search-index` | HTML de 10-K, 10-Q, DEF 14A, 8-K (con el anexo 99.1 de resultados), Form 4, SC 13D/G, Exhibit 21 (filiales) |

Decisiones de lectura que se fijan y se prueban:

- **Reexpresiones.** El mismo ejercicio aparece en varios 10-K. Regla: **último
  presentado**, y si difiere del original, nota «reexpresado en <formulario, fecha>».
- **Trimestres.** El 10-Q trae el trimestre y el acumulado; el 4.º trimestre no se
  presenta como tal. Regla: Q4 = FY − 9M acumulado, rotulado **derivado** con fórmula.
- **Sinónimos de concepto.** Cada campo tiene una lista ordenada de conceptos aceptados;
  se toma el primero presente y se registra cuál fue. Si ninguno: hueco (§6).
- **Ejercicio fiscal ≠ año natural.** Se rotula por fecha de cierre.
- **Moneda y escala.** Lo que la empresa reporta, sin conversión. La escala del
  documento («in millions», «in thousands») se detecta por cabecera y se registra: es
  lo que permite comparar `391035000000` de XBRL con `391,035` del PDF.
- **Extensiones propias** de la empresa no se leen en v0.

---

## 3. El índice y de dónde sale cada apartado

Leyenda: **H** hecho SEC · **Hd** hecho de documento · **S** supuesto · **D** derivado
· **T** texto del analista · **Img** recorte de un adjunto (§7) · **N/A** con motivo.
Toda H puede acabar siendo Hd si la SEC no trae ese campo para esa empresa (§6).

### A. Resumen ejecutivo y contexto de la tesis

**1. Ficha de empresa**

| Elemento | Estado | Origen |
|---|---|---|
| Nombre legal, ticker, bolsa, CIK, SIC y descripción del sector | H | `identidad` |
| Estado/país de constitución, sede, web, cierre fiscal | H | `dei:EntityIncorporationStateCountryCode`, `dei:EntityAddress…`, `identidad` |
| Año de fundación | Hd / H (cita) | 10-K Item 1 o cuentas anuales; si ninguno lo dice, hueco |
| Empleados | H | `dei:EntityNumberOfEmployees` o 10-K Item 1 (*Human Capital*) |
| Auditor | H | `dei:AuditorName`, `dei:AuditorLocation` (desde 2022) |
| Acciones en circulación (fecha) | H | `dei:EntityCommonStockSharesOutstanding` |
| Valor de mercado en manos de no afiliados (fecha) | H | `dei:EntityPublicFloat`, rotulado con su fecha; **no** se llama capitalización |
| Precio, capitalización actual, rango 52 semanas, volumen | N/A | la SEC no publica cotizaciones |
| Índices de pertenencia | N/A | sin fuente |
| Última presentación (10-K/10-Q) con fecha | H | `identidad` |
| Recorte de la portada de las cuentas anuales | Img | adjunto 1, pág. 1 |

**2. Resumen ejecutivo y contexto de la tesis**

| Elemento | Estado | Origen |
|---|---|---|
| Texto del resumen | T | analista |
| «Cifras que sostienen el resumen»: caja lateral con 6–8 datos (ventas y crecimiento, margen EBIT, Bº neto, DFN/EBITDA, FCF, acciones) | H / D | los mismos objetos que en la sección C: **un hecho, una fuente** |
| Objetivos de la compañía vigentes | Hd | adjunto 3 (*guidance*), contrastado con el 8-K anexo 99.1 más reciente |
| Contexto: últimos hitos | Hd / H | 8-K presentados en los últimos 12 meses (lista de fechas y asuntos, H); texto T |

**3. Investment case — los 5 pilares**

| Elemento | Estado | Origen |
|---|---|---|
| Cinco pilares: título + párrafo | T | analista, exactamente cinco |
| Evidencias por pilar | H / Hd / D | cada pilar **debe enlazar al menos un hecho** del informe; la plantilla no renderiza un pilar sin evidencia |
| Riesgo que amenaza cada pilar | T (+ cita H) | 10-K Item 1A, epígrafes con enlace |

### B. Perfil corporativo y modelo de negocio

**4. ¿Qué hace la empresa? — productos, servicios y mercados**

| Elemento | Estado | Origen |
|---|---|---|
| Descripción | T (+ cita H) | 10-K Item 1 *Business* |
| Ingresos por segmento (tabla + gráfico) | H | `segmentos`, eje de segmentos; si el 10-K no desglosa, hueco hacia adjunto 1 |
| Ingresos por geografía | H | `segmentos`, eje geográfico; igual |
| Ingresos por producto/servicio | H | eje de producto (`ProductOrServiceAxis`), si existe |
| Concentración de clientes | H si se declara | nota de concentración de riesgo (`ConcentrationRiskPercentage1`) |
| Figura del negocio: mapa de segmentos, cadena de valor, gráfico de la compañía | Img | adjunto 1, página propuesta por el sistema, confirmada por el analista |

**5. Estructura corporativa — accionariado, filiales y participaciones**

| Elemento | Estado | Origen |
|---|---|---|
| Principales accionistas (>5 %) | H con certeza | DEF 14A, tabla *Security Ownership*; SC 13D/13G para cruzar |
| Participación de directivos y consejeros | H con certeza | misma tabla |
| Autocartera | H | `TreasuryStockShares`, `TreasuryStockValue` |
| Filiales | H | **Exhibit 21** del 10-K (lista de filiales y jurisdicción) |
| Participaciones no consolidadas | H | `EquityMethodInvestments` y nota; texto T |
| Organigrama | Img | adjunto 1 si lo trae; si no, el sistema dibuja la lista de filiales (no inventa jerarquía) |

**6. Equipo directivo — CEO, CFO y principales ejecutivos; track record**

| Elemento | Estado | Origen |
|---|---|---|
| Nombre, cargo, edad, desde cuándo | H con certeza | 10-K Item 10 / DEF 14A |
| Retribución (tabla resumen) | H con certeza | DEF 14A, *Summary Compensation Table* |
| Operaciones de insiders (12 meses) | H | Form 4: compras, ventas, fecha, precio declarado |
| Acciones en manos del equipo | H con certeza | DEF 14A |
| Track record (valoración) | T | analista; el sistema aporta los hechos anteriores y la evolución de resultados durante su mandato (D) |
| Fotografías | Img, opcional | solo si el adjunto 1 las trae; el analista decide incluirlas |

**7. Pipeline y catalizadores — hoja de ruta, fechas clave y palancas**

| Elemento | Estado | Origen |
|---|---|---|
| Objetivos de la compañía: cifras, horizonte, fecha en que se dieron | Hd | adjunto 3; contraste con 8-K anexo 99.1 |
| Hoja de ruta / productos anunciados | Hd | adjunto 3; Img de la diapositiva correspondiente |
| Fechas clave anunciadas | H / Hd | solo las que la compañía haya comunicado (8-K, *guidance*). **Nunca** fechas «esperadas» por patrón |
| Próxima presentación de resultados | N/A salvo anuncio | la SEC no publica calendario |
| Palancas de la tesis | T | analista, enlazadas a pilares de §3 |

### C. Análisis fundamental y métricas financieras

Todas las tablas: **5 ejercicios anuales + últimos 4 trimestres** (más TTM derivado).
Cada celda con su glifo de contraste (§5). Bajo cada tabla, el recorte del estado
financiero en las cuentas anuales adjuntas (§7).

**8. Estado de resultados**

| Campo | Concepto (primer candidato) | Capa |
|---|---|---|
| Ingresos | `Revenues` | H |
| Coste de ventas · margen bruto | `CostOfRevenue` · `GrossProfit` | H / D |
| EBITDA | EBIT + D&A | **D**, fórmula impresa |
| EBIT | `OperatingIncomeLoss` | H |
| D&A | `DepreciationDepletionAndAmortization` | H |
| Resultado financiero | `InterestExpense`, `InvestmentIncomeInterest` | H |
| BAI · impuestos · tipo efectivo | `IncomeLossFromContinuingOperationsBeforeIncomeTaxes…` · `IncomeTaxExpenseBenefit` | H / D |
| Bº neto · atribuible | `NetIncomeLoss` · minoritarios | H |
| EPS básico · diluido | `EarningsPerShareBasic` · `EarningsPerShareDiluted` | H |
| Márgenes bruto, EBITDA, operativo, neto | | D |
| Crecimientos interanuales y TACC | | D |

**9. Balance de situación**

| Campo | Concepto | Capa |
|---|---|---|
| Tesorería · inversiones a corto | `CashAndCashEquivalentsAtCarryingValue` · `ShortTermInvestments` | H |
| Clientes · existencias | `AccountsReceivableNetCurrent` · `InventoryNet` | H |
| Inmovilizado material · fondo de comercio · intangibles | `PropertyPlantAndEquipmentNet` · `Goodwill` · `IntangibleAssetsNetExcludingGoodwill` | H |
| Total activo | `Assets` | H |
| Deuda a corto · a largo · arrendamientos | `DebtCurrent`/`LongTermDebtCurrent` · `LongTermDebtNoncurrent` · `OperatingLeaseLiability…` | H |
| Total pasivo · patrimonio neto · minoritarios | `Liabilities` · `StockholdersEquity` · `MinorityInterest` | H |
| Deuda neta · DFN/EBITDA | | **D**, con o sin arrendamientos, y se dice cuál |
| Fondo de maniobra | | D |

**10. Flujo de caja**

| Campo | Concepto | Capa |
|---|---|---|
| Flujo operativo | `NetCashProvidedByUsedInOperatingActivities` | H |
| Capex | `PaymentsToAcquirePropertyPlantAndEquipment` | H |
| FCF | CFO − capex | **D** |
| Dividendos pagados · DPA | `PaymentsOfDividends` · `CommonStockDividendsPerShareDeclared` | H |
| Recompras | `PaymentsForRepurchaseOfCommonStock` | H |
| Retribución total al accionista · % sobre FCF | | D |
| Adquisiciones (caja) | `PaymentsToAcquireBusinessesNetOfCashAcquired` | H |

**11. Rentabilidad y eficiencia**

| Métrica | Fórmula impresa | Capa |
|---|---|---|
| ROE | Bº neto / patrimonio neto medio | D |
| ROA | Bº neto / activo total medio | D |
| ROIC | EBIT × (1 − tipo efectivo) / (patrimonio + deuda − caja), medios | D; la definición es de la plantilla y se imprime |
| Márgenes | de la sección 8 | D (mismos objetos) |
| Rotación de activos · ciclo de caja | | D |
| Pay-out · FCF yield | pay-out D; FCF yield **N/A** (precio) | |

---

## 4. Los tres adjuntos

| # | Apartado | Qué se espera | Obligatorio |
|---|---|---|---|
| 1 | **Cuentas anuales** | 10-K o *annual report* del ejercicio base; se admiten ejercicios anteriores | sí |
| 2 | **Trimestrales** | 10-Q del ejercicio en curso y nota de resultados del último trimestre | sí |
| 3 | **Guidance** | presentación de resultados, *investor day*, plan estratégico | sí, salvo «incluido en 1 o 2» con fichero y página |

Formatos: PDF con capa de texto y hojas de cálculo (`.xlsx`, `.csv`). Un PDF escaneado
sin texto se rechaza con motivo en v0 (OCR: fase posterior). Cada fichero guarda nombre,
hash, tamaño, quién y cuándo; los adjuntos **se congelan con la emisión**. Subida
también por API.

---

## 5. Contraste automático: el sistema confirma cada dato

### 5.1 Qué se hace con cada adjunto al subirlo

1. **Extracción de texto por página** con posiciones (para poder recortar después).
2. **Detección de escala y moneda** por cabeceras («in millions, except per share»).
3. **Localización de tablas** y de sus etiquetas de fila (Revenue, Net sales, Total
   net revenues…) y columnas (ejercicios, trimestres).
4. **Índice de candidatos**: cada número del documento con su etiqueta más cercana,
   periodo inferido, página y rectángulo.

Todo esto es **inferencia** y se guarda como tal, con `certeza`. Lo que la convierte
en hecho es el paso siguiente.

### 5.2 El contraste

Para cada campo × periodo del informe:

```
 hecho SEC ──┐
             ├──▶ ¿coinciden? (misma magnitud tras escala, tolerancia de redondeo
 candidato ──┘     del documento: ±½ unidad de la escala impresa)
 documento
```

| Resultado | Glifo | Qué pasa |
|---|---|---|
| **Confirmado**: SEC y documento coinciden | ✓ | entra en el informe con nota «SEC · <fichero> p. N» y el recorte disponible |
| **Discrepante**: ambos existen y no coinciden | ≠ | **bloquea la emisión**. El analista ve los dos valores y el recorte, decide cuál vale y por qué; la decisión queda registrada y se imprime como nota |
| **Solo SEC**: no se halló en los adjuntos | ◐ | no bloquea, pero exige **reconocimiento** del analista antes de emitir; se imprime con glifo y nota «sin contraste documental» |
| **Solo documento**: la SEC no lo tiene | ◑ | hecho de documento con `certeza`; exige **confirmación** del analista (ve el recorte, acepta o corrige) |
| **Ninguno** | — | hueco (§6) |

Lo que el contraste **no** hace: elegir el valor «que cuadra». Cuando hay dos lecturas,
decide el analista, y su decisión es un dato más del informe.

### 5.3 Dónde se contrasta cada cosa

| Datos | SEC | Adjunto |
|---|---|---|
| Anuales (sección C, ejercicios cerrados) | 10-K vía XBRL | adjunto 1 |
| Trimestrales (últimos 4 trimestres) | 10-Q vía XBRL | adjunto 2 |
| Objetivos de la compañía | 8-K anexo 99.1 (texto) | adjunto 3 |
| Accionistas, consejo, retribución | DEF 14A (texto) | adjunto 1 si los trae |
| Filiales | Exhibit 21 | adjunto 1 si las trae |

El *guidance* solo se contrasta si el informe lo usa (secciones 2 y 7).

### 5.4 El tablero del analista

Una pantalla por emisión, con una fila por campo × periodo, filtrable por resultado.
Cada fila: valor SEC, valor documento, glifo, recorte, y las acciones posibles (decidir,
reconocer, confirmar, corregir). Un contador arriba: «N discrepancias · M sin
contraste · K por confirmar». La emisión no pasa a render hasta que N = 0 y M y K
están reconocidos. Todo queda en `auditoria`.

---

## 6. Huecos: lo que ni la SEC ni los adjuntos tienen

Un **hueco** es un campo × periodo que el informe necesita y que no tiene ni hecho SEC
ni candidato en los adjuntos. Una sola cifra es un hueco. La emisión pasa a
`pendiente_analista` con la lista: qué campo, para qué apartado, por qué la SEC no lo
tiene, en cuál de los tres adjuntos debería estar.

El analista lo resuelve de una de dos formas, sin tercera vía:

- **Aporta el valor** señalando fichero y página → hecho de documento, `certeza` alta
  (lo leyó una persona), con el recorte de esa página.
- **Declara «no está en los adjuntos»** con motivo → N/A **con ese motivo** en el informe.

Los huecos resueltos se recuerdan por informe y se proponen en la siguiente emisión,
señalando que vienen de la anterior.

---

## 7. Imágenes de los adjuntos en el informe

Dos usos, con la misma mecánica (recorte = fichero + página + rectángulo → PNG con hash):

**Evidencia.** Bajo cada tabla de la sección C, el recorte del estado financiero
correspondiente en las cuentas anuales adjuntas (y del trimestral en las columnas de
trimestres). El sistema lo elige solo: es la región donde encontró los candidatos que
confirmó. Pie: «Fuente: <fichero>, pág. N. Contrastado con 10-K <fecha>».

**Figura.** En los apartados 1, 4, 5, 6 y 7, una imagen del documento que ilustra el
apartado: portada, mapa de segmentos, organigrama, equipo, hoja de ruta. Aquí elegir es
juicio, así que el sistema **propone** hasta tres páginas por apartado (por palabras
clave y por presencia de gráficos) y el analista **confirma o cambia**. Un apartado sin
figura confirmada sale sin figura, no con una elegida al azar.

Reglas: resolución fija para impresión; pie obligatorio con fichero y página; el
recorte se congela con la emisión; alternativa textual (`alt`) obligatoria con lo que
muestra la imagen, porque la imagen nunca es el único portador de la información: la
cifra está en la tabla, la imagen la respalda.

---

## 8. Qué cambia en el diseño general

1. `Hecho.origen` gana `'documento'`, con `adjunto_id`, `pagina`, `rectangulo`, `certeza`.
2. Tablas nuevas: `adjunto`, `candidato` (lo extraído), `contraste`, `hueco`, `recorte`.
3. `emision.estado` gana `pendiente_analista`; el paso de contraste va entre la
   construcción de hechos y el render, y lo ejecuta el worker.
4. `informe` guarda `parametros`, `supuestos` y `textos`; `emision` congela hechos,
   adjuntos, recortes y decisiones.
5. Dependencias nuevas a aprobar: lectura de PDF con posiciones y render de página a
   imagen, lectura de hojas de cálculo (ver DISEÑO.md §10).
6. Hoja de ruta: la fase 1b incorpora el extractor y el contraste; la fase 2 emite ya
   con recortes de evidencia.

---

## 9. Lo que este documento no decide

- **Secciones D en adelante** del índice: pendientes de recibir.
- **Narrativa generada** para los apartados T: todo texto es del analista salvo decisión
  contraria.
- **OCR** para PDF escaneados: fase posterior; en v0 se rechazan con motivo.
- **Fuente de cotización**: sin ella, precio, capitalización, rango y FCF yield son N/A.
- **Empresas con 20-F** (IFRS en la SEC): fuera hasta abordar «fuera de EE. UU.».
