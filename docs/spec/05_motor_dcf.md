# 05 · Motor de valoración (determinista, Python puro, con tests)

## 1. Arquitectura
`tesis/motor/`: `wacc.py`, `proyeccion.py` (drivers → FCFF), `terminal.py`, `puente.py`, `escenarios.py`, `sensibilidad.py`, `reverse.py`, `multiplos.py`, `sotp.py`, `objetivo.py`, `excel.py`, `validacion.py`.
Funciones puras: entrada = Hechos + `entradas.json`; salida = objeto `Valoracion` en el que cada cifra intermedia es un Hecho `estimacion` con su fórmula. Se redondea solo al imprimir. Umbrales en `config/umbrales.yaml` (valores por defecto entre paréntesis).

## 2. Paquetes sectoriales v1 (`config/sectores.yaml`)
Todos usan el FCFF común (§3). El paquete fija el periodo explícito por defecto, los drivers extra, los KPIs sugeridos y comprobaciones propias. Propuesta por SIC (los códigos concretos van antes que los rangos); el analista confirma o reclasifica.

| Paquete | SIC orientativo | Periodo | Drivers extra | Comprobaciones |
|---|---|---|---|---|
| general | resto | 5–10 | — | — |
| software | 7370–7374 | 10 | software capitalizado en capex; ingresos diferidos en fondo de maniobra | regla del 40; SBC/ingresos |
| semiconductores | 3674 (QCOM llega por 3663: reclasificar) | 7–10 | construcción por segmentos; margen normalizado de ciclo medio (mediana 7–10 años) | año base en pico o valle de ciclo → aviso |
| consumo_retail | 5200–5999, 2000–2399 | 5–10 | margen bruto + SG&A %; aperturas | cierres en enero/febrero; arrendamientos |
| industrial | 3400–3899 (resto) | 5–10 | cartera de pedidos (KPI) | pensiones en el puente |
| energia_materias | 1000–1499, 2900–2999 | 5–10 | volumen × precio (precio por escenario), coste unitario, capex de mantenimiento/crecimiento | NAV de reservas → v2 |
| utilities | 4900–4949 | 10 | base regulada y ROE permitido | Kd y apalancamiento |
| telecom | 4800–4899 | 7–10 | espectro como capex | arrendamientos |
| media_contenido | 7810–7849, 4833, 4841 | 10 | desfase de contenido: gasto en caja − amortización (% ingresos) | — |
| salud_madura | 2834–2836, 3841–3851 con ingresos | 10 | ingresos por producto con fecha de pérdida de patente (opcional) | — |

Bloqueo v1: 6000–6799 (bancos, aseguradoras, REIT, BDC, SPAC) y biotech con ingresos < `biotech_ingresos_min_musd` (50).
Construcción por segmentos (opcional en cualquier paquete): ingresos y margen EBIT por segmento − costes corporativos no asignados = EBIT consolidado.

## 3. FCFF por año t = 1…N (año base 0 = Hechos verificados)
```
Ingresos_t  = Ingresos_t−1 × (1 + g_t)            [o Σ segmentos]
EBIT_t      = Ingresos_t × m_t
Impuestos_t = max(0, EBIT_t − BIN_t) × τ_t         (bases imponibles negativas acumuladas y consumidas)
NOPAT_t     = EBIT_t − Impuestos_t
FCFF_t      = NOPAT_t + D&A_t − Capex_t − ΔFM_t − SBC_t ± partidas del paquete
D&A_t = Ingresos_t × da_t · Capex_t = Ingresos_t × cx_t · ΔFM_t = (Ingresos_t − Ingresos_t−1) × fm
SBC_t = Ingresos_t × sbc_t   (0 si val.sbc = dilucion; entonces las acciones futuras crecen en SBC/precio)
```
**Periodo parcial (obligatorio).** Fecha de valoración d; f = días desde d hasta el cierre del ejercicio 1 / días del ejercicio. El flujo del año 1 cuenta × f: lo generado antes de d ya está en el balance del puente. Momentos: t₁ = f/2 (mitad de año) o f; t_k = f + (k − 1) − 0,5 (o f + k − 1). DF_k = (1 + WACC)^−t_k.

## 4. Valor terminal
- value_driver (por defecto): VT = NOPAT_N × (1 + g) × (1 − g / RONIC) / (WACC − g).
- gordon: VT = FCFF_N × (1 + g) / (WACC − g).
- multiplo_salida: VT = EBITDA_N × múltiplo.
Se calculan los tres; rige el elegido y los otros dos se imprimen como contraste. El VT se descuenta en f + N − 1.
Bloqueos: g ≥ rf; g > `g_max` (4 %); WACC − g < `wacc_menos_g_min_pp` (2 p.p.).
Avisos: peso del VT > `peso_vt_aviso` (75 %); diferencia value_driver/gordon > `vt_contraste_aviso` (15 %); RONIC > `ronic_max_x_wacc` (3) × WACC.

## 5. WACC
- rf: bono a 10 años de la curva par del Tesoro en fecha_valoracion.
- Beta por regresión: semanal 2 años frente a SPY (cierres Nasdaq), ajuste de Blume (0,67·β + 0,33); se muestran también 5 años mensual, R² y error. R² < `beta_r2_min` (0,10) → aviso para usar bottom-up.
- Bottom-up: β_U del analista (fuente y fecha) → β_L = β_U × (1 + (1 − t) × D/E de mercado).
- Ke = rf + β × ERP + prima. Kd: rating sintético por cobertura EBIT/intereses (`config/rating_sintetico.yaml`, tabla que aporta el analista con fuente y fecha) → rf + diferencial; o rendimiento aportado por el analista. Kd neto = Kd × (1 − t_marginal).
- Pesos a valor de mercado: E = precio × acciones; D = deuda financiera (+ arrendamientos si la política lo incluye).
- WACC por escenario = WACC + ajuste justificado.

## 6. Puente y valor por acción
Fondos propios = VE − deuda financiera − arrendamientos (si la política lo incluye) + caja + inversiones CP − minoritarios − preferentes + asociadas ± ajustes del analista. Todos del último balance publicado: mismos importes que el apartado 9.
Acciones diluidas = básicas de la portada del último filing + opciones por el método de autocartera al precio + RSU pendientes (nota de retribución en acciones). Si faltan datos, diluidas medias del último trimestre (marcado).
V₀ = fondos propios / acciones diluidas.

## 7. Escenarios, PO y métricas (definiciones únicas)
- V_h = V₀ × (1 + Ke)^(h/12) − DPA esperados en h; h = val.horizonte_meses.
- Valor razonable hoy = Σ p_i · V₀,i. **PO = Σ p_i · V_h,i.**
- Potencial = PO / P − 1. Margen de seguridad = 1 − P / valor razonable hoy.
- Downside = V_h,pes / P − 1. Recorrido/riesgo = (PO − P) / (P − V_h,pes); si V_h,pes ≥ P → «sin pérdida en el escenario pesimista».
- Bloqueos: V_pes ≤ V_base ≤ V_opt; probabilidades que suman 100 %; base ≥ `prob_base_min` (40 %).
- Recomendación sugerida: `umbrales.recomendacion` (por defecto: Comprar si potencial ≥ 15 % y recorrido/riesgo ≥ 1,5; Vender si potencial ≤ −10 %; si no, Mantener).

## 8. Sensibilidad, reverse DCF, múltiplos y SOTP
- Sensibilidad: V₀ del base en una rejilla WACC (−1…+1 p.p., paso 0,5) × g (−0,5…+0,5 p.p., paso 0,25); celda base marcada.
- Reverse DCF (brentq; rangos en config): (a) CAGR de ingresos constante con los márgenes del base; (b) margen EBIT terminal con el crecimiento del base; (c) crecimiento constante del FCFF desde el FCFF del año 1. Sin solución en el rango → se dice.
- Múltiplos: TTM de Hechos; NTM = f·Año1 + (1 − f)·Año2 del base. BPA proyectado = (NOPAT − intereses netos × (1 − t)) / acciones diluidas. PEG = PER NTM / (CAGR del BPA a 3 años del base × 100). Histórico propio de 5 años con cierres trimestrales. Comparables: medianas LTM (PER solo con positivos; atípicos > `atipicos_iqr` (3) × IQR marcados).
- Si |valor por múltiplos (mediana) / valor razonable hoy − 1| > `divergencia_multiplos_aviso` (20 %) → aviso impreso en 20.
- SOTP: VE por segmento (métrica × múltiplo justificado) − costes corporativos capitalizados + puente → por acción; frente al DCF.

## 9. Excel
- **Exportar** (`openpyxl`, fórmulas vivas, no valores): hojas Supuestos, Resumen, Pesimista, Base, Optimista, Sensibilidad y Reverse DCF; celdas de entrada en amarillo; columna «Origen / justificación»; rangos con nombre. Test: recalculado (LibreOffice sin interfaz, `formulas` o `pycel`) = motor ± 0,01.
- **Importar para comparar**: solo por rangos con nombre (`precio`, `acciones_diluidas`, `deuda_neta`, `wacc_pes|base|opt`, `g_pes|base|opt`, `valor_accion_pes|base|opt`, `peso_pes|base|opt`, `ingresos_base`, `margen_ebit_base`…) o, en libros antiguos, con un mapa explícito de celdas en `config/excel_mapas/<libro>.yaml`. Nunca por rótulo. Cuadro de diferencias en 12 y 36; rige el motor.

## 10. Casos de oro (tests)
1. Empresa sintética calculada a mano (ingresos 1.000, margen 20 %, sin deuda): VE a mano = motor ± 0,01.
2. Periodo parcial: valoración a 3 meses del cierre → el año 1 cuenta al 25 %.
3. g = WACC − 1 p.p. → bloqueo.
4. Escenarios desordenados → bloqueo.
5. QCOM y NFLX con entradas de fixture: cuadros 12–20 completos, ningún WACC = 0, precio = cierre oficial.
6. Exportar → recalcular → mismo resultado que el motor.
