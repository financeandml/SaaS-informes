"""El catálogo de campos: qué pide el informe y cómo lo llama cada fuente.

Un solo sitio para tres vocabularios que nombran lo mismo: el rótulo que imprime
el informe, los conceptos XBRL que la SEC acepta para ese campo (en orden de
preferencia) y los rótulos de fila con los que un estado financiero en PDF o en
hoja de cálculo lo presenta. Cuando un emisor rotula de otro modo, no casa, no
sale, y el contraste lo declara como hueco: el catálogo no se estira sobre la
marcha para que cuadre.

Los patrones de fila van anclados al principio y son de rótulo completo: «Basic»
casa igual con el BPA básico y con las acciones básicas, y lo que los distingue
es el `contexto` —la última línea de cabecera sin cifras que hay encima—, no el
rótulo. Sin eso el extractor atribuía 4.249.512 (miles de acciones) a un BPA.

`signo_informe` es la convención de la casa al imprimir: los costes y las
salidas de caja van en negativo, como en la maqueta de referencia. Los
documentos y la SEC los traen cada uno con su signo, y el contraste compara en
valor absoluto precisamente porque un paréntesis no es una discrepancia.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Tuple

__all__ = ["Campo", "CAMPOS", "DERIVADOS", "Derivado", "campo", "por_seccion"]

FLUJO = "flujo"          # un periodo con inicio y fin (cuenta de resultados, flujos de caja)
INSTANTE = "instante"    # una fecha (balance)


@dataclass(frozen=True)
class Campo:
    clave: str
    rotulo: str                              # como se imprime en el informe (ES)
    rotulo_en: str                           # para el diccionario EN
    seccion: int                             # apartado del índice (8, 9, 10…)
    tipo: str = FLUJO
    unidad: str = "USD"
    signo_informe: int = 1
    conceptos: Tuple[str, ...] = ()          # us-gaap por orden de preferencia
    # Cuando la compañía no etiqueta el agregado y sí sus partes: cada grupo se suma entero o no se usa, y lo que
    # sale es un derivado con su fórmula, nunca un hecho publicado. Oracle no declara el total del pasivo ni la
    # amortización conjunta ni el resultado antes de impuestos: declara sus dos mitades, una por una.
    conceptos_suma: Tuple[Tuple[str, ...], ...] = ()
    filas: Tuple[str, ...] = ()              # patrones de rótulo de fila, anclados
    contexto: Optional[str] = None           # patrón que debe cumplir la cabecera de bloque
    contexto_excluido: Optional[str] = None  # patrón que la cabecera NO debe cumplir
    solo_documento: bool = False             # la SEC no lo publica como concepto propio
    nota: str = ""                           # lo que el informe dice al pie sobre este campo


CAMPOS: Tuple[Campo, ...] = (
    # ------------------------------------------------------------- 8. Estado de resultados
    Campo("ingresos", "Ingresos", "Revenues", 8,
          conceptos=("Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet"),
          filas=(r"^Revenues?$", r"^Total (net )?revenues?$", r"^(Total )?net sales$"),
          contexto_excluido=r"(?i)region|segment|UCAN|EMEA|LATAM|APAC"),
    Campo("coste_ingresos", "Coste de los ingresos", "Cost of revenues", 8, signo_informe=-1,
          conceptos=("CostOfRevenue", "CostOfGoodsAndServicesSold"),
          filas=(r"^Cost of revenues?$", r"^Cost of sales$")),
    Campo("marketing", "Ventas y marketing", "Sales and marketing", 8, signo_informe=-1,
          conceptos=("SellingAndMarketingExpense", "MarketingExpense"),
          filas=(r"^Sales and marketing$", r"^Marketing$")),
    Campo("tecnologia", "Investigación y desarrollo", "Technology and development", 8, signo_informe=-1,
          conceptos=("ResearchAndDevelopmentExpense", "TechnologyAndDevelopmentExpense"),
          filas=(r"^Technology and development$", r"^Research and development$")),
    Campo("generales", "Generales y administrativos", "General and administrative", 8, signo_informe=-1,
          conceptos=("GeneralAndAdministrativeExpense",),
          filas=(r"^General and administrative$",)),
    # Quien publica ventas, generales y administrativos en una sola línea (Qualcomm) no tiene «ventas y marketing»
    # ni «generales» sueltos: se imprime su línea, y las otras dos no salen vacías, sino que no salen.
    Campo("sga", "Ventas, generales y administrativos", "Selling, general and administrative", 8, signo_informe=-1,
          conceptos=("SellingGeneralAndAdministrativeExpense",),
          filas=(r"^Selling, general and administrative$",)),
    Campo("ebit", "EBIT (resultado operativo)", "Operating income (EBIT)", 8,
          conceptos=("OperatingIncomeLoss",),
          filas=(r"^Operating income$", r"^Income from operations$")),
    Campo("intereses", "Gastos financieros", "Interest expense", 8, signo_informe=-1,
          conceptos=("InterestExpense", "InterestExpenseNonoperating", "InterestExpenseDebt"),
          filas=(r"^Interest expense$",)),
    Campo("otros_financieros", "Otros ingresos y gastos", "Interest and other income (expense)", 8,
          conceptos=("NonoperatingIncomeExpense", "OtherNonoperatingIncomeExpense"),
          filas=(r"^Interest and other income \(expense\)$", r"^Other income \(expense\),? net$")),
    Campo("bai", "Resultado antes de impuestos", "Income before income taxes", 8,
          conceptos=("IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
                     "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments"),
          conceptos_suma=(("IncomeLossFromContinuingOperationsBeforeIncomeTaxesDomestic",
                           "IncomeLossFromContinuingOperationsBeforeIncomeTaxesForeign"),),
          filas=(r"^Income before (provision for )?income taxes$",)),
    Campo("impuestos", "Impuesto sobre beneficios", "Provision for income taxes", 8, signo_informe=-1,
          conceptos=("IncomeTaxExpenseBenefit",),
          filas=(r"^Provision for income taxes$", r"^Income tax expense$")),
    Campo("beneficio_neto", "Beneficio neto", "Net income", 8,
          conceptos=("NetIncomeLoss", "ProfitLoss"),
          filas=(r"^Net income$",),
          contexto_excluido=r"(?i)per share|shares"),
    # Dos maquetas del mismo bloque: la fila se llama «Basic» bajo «Earnings per share», o el bloque se llama «Basic
    # earnings per share» y la fila es «Net income» (Qualcomm, que además desglosa actividades continuadas). El
    # recuento de acciones vive en el mismo bloque y también dice «per share»: se excluye por su rótulo.
    Campo("bpa_basico", "BPA básico", "EPS, basic", 8, unidad="USD/acción",
          conceptos=("EarningsPerShareBasic",),
          filas=(r"^Basic$", r"^Net income$"), contexto=r"(?i)per share",
          contexto_excluido=r"(?i)shares used|^diluted"),
    Campo("bpa_diluido", "BPA diluido", "EPS, diluted", 8, unidad="USD/acción",
          conceptos=("EarningsPerShareDiluted",),
          filas=(r"^Diluted$", r"^Net income$"), contexto=r"(?i)per share",
          contexto_excluido=r"(?i)shares used|^basic\b(?! and)"),
    Campo("acciones_basicas", "Acciones medias básicas", "Weighted-average shares, basic", 8, unidad="acciones",
          conceptos=("WeightedAverageNumberOfSharesOutstandingBasic",),
          filas=(r"^Basic$",), contexto=r"(?i)weighted|shares"),
    Campo("acciones_diluidas", "Acciones medias diluidas", "Weighted-average shares, diluted", 8, unidad="acciones",
          conceptos=("WeightedAverageNumberOfDilutedSharesOutstanding",),
          filas=(r"^Diluted$",), contexto=r"(?i)weighted|shares"),
    Campo("amortizacion", "Amortización del inmovilizado", "Depreciation and amortization of property, equipment and intangibles", 8,
          conceptos=("DepreciationDepletionAndAmortization", "DepreciationAndAmortization", "DepreciationAmortizationAndAccretionNet"),
          conceptos_suma=(("Depreciation", "AmortizationOfIntangibleAssets"),),
          filas=(r"^Depreciation and amortization( of property, equipment and intangibles)?$",),
          nota="Sin la amortización de contenido: esa es coste de los ingresos y no se devuelve al EBITDA."),
    Campo("amortizacion_contenido", "Amortización de contenido", "Amortization of content assets", 8, signo_informe=-1,
          filas=(r"^Amortization of content assets$",), solo_documento=True,
          nota="Netflix la declara con una extensión propia que companyfacts no sirve; sale del adjunto."),
    Campo("sbc", "Retribución en acciones", "Stock-based compensation", 8, signo_informe=-1,
          conceptos=("ShareBasedCompensation", "AllocatedShareBasedCompensationExpense"),
          filas=(r"^Stock-based compensation expense$",)),
    # ------------------------------------------------------------- 9. Balance
    Campo("caja", "Tesorería y equivalentes", "Cash and cash equivalents", 9, tipo=INSTANTE,
          conceptos=("CashAndCashEquivalentsAtCarryingValue",),
          filas=(r"^Cash and cash equivalents$",), contexto_excluido=r"(?i)cash flows|beginning|end of period"),
    Campo("inversiones_cp", "Inversiones a corto plazo", "Short-term investments", 9, tipo=INSTANTE,
          conceptos=("ShortTermInvestments", "MarketableSecuritiesCurrent", "AvailableForSaleSecuritiesDebtSecuritiesCurrent"),
          filas=(r"^Short-term investments$", r"^Marketable securities$")),
    # A4: valores negociables a largo plazo. Solo títulos de deuda o negociables, no participaciones estratégicas
    # (`LongTermInvestments` mezcla ambas: Qualcomm guarda ahí QSI). Entran en el puente si el analista lo confirma
    # (val.inversiones_lp); sin filas de documento: el mismo rótulo que las de corto plazo emparejaba mal (fallo [4]).
    Campo("inversiones_lp", "Valores negociables a largo plazo", "Non-current marketable securities", 9, tipo=INSTANTE,
          conceptos=("MarketableSecuritiesNoncurrent", "AvailableForSaleSecuritiesDebtSecuritiesNoncurrent")),
    Campo("activo_corriente", "Activo corriente", "Total current assets", 9, tipo=INSTANTE,
          conceptos=("AssetsCurrent",), filas=(r"^Total current assets$",)),
    Campo("contenido", "Activos de contenido, neto", "Content assets, net", 9, tipo=INSTANTE,
          filas=(r"^Content assets, net$",), solo_documento=True,
          nota="Extensión propia de Netflix; companyfacts no la sirve."),
    Campo("inmovilizado", "Inmovilizado material, neto", "Property and equipment, net", 9, tipo=INSTANTE,
          conceptos=("PropertyPlantAndEquipmentNet",), filas=(r"^Property and equipment, net$",)),
    Campo("fondo_comercio", "Fondo de comercio", "Goodwill", 9, tipo=INSTANTE,
          conceptos=("Goodwill",), filas=(r"^Goodwill$",)),
    Campo("intangibles", "Intangibles", "Intangible assets, net", 9, tipo=INSTANTE,
          conceptos=("IntangibleAssetsNetExcludingGoodwill", "FiniteLivedIntangibleAssetsNet"),
          filas=(r"^Intangible assets, net$",)),
    Campo("total_activo", "Total activo", "Total assets", 9, tipo=INSTANTE,
          conceptos=("Assets",), filas=(r"^Total assets$",)),
    Campo("pasivo_corriente", "Pasivo corriente", "Total current liabilities", 9, tipo=INSTANTE,
          conceptos=("LiabilitiesCurrent",), filas=(r"^Total current liabilities$",)),
    Campo("deuda_cp", "Deuda a corto plazo", "Short-term debt", 9, tipo=INSTANTE,
          # primero el total —«Short-term debt» del balance— y luego sus partes: Qualcomm imprime 2.489 (1.991 de
          # vencimiento corriente del largo plazo más 498 de pagarés), y leer solo la parte discrepaba del documento
          conceptos=("DebtCurrent", "LongTermDebtCurrent", "ShortTermBorrowings", "NotesPayableCurrent"),
          filas=(r"^Short-term debt$", r"^Current portion of long-term debt$", r"^Notes payable, current$")),
    # A4 (fallo [7]): quien presenta el papel comercial en su propia línea —Apple: «Commercial paper» junto a «Term
    # debt»— lo deja fuera de `LongTermDebtCurrent`; la deuda bruta lo suma entonces (`derivados.incluye_papel_comercial`).
    Campo("papel_comercial", "Papel comercial", "Commercial paper", 9, tipo=INSTANTE,
          conceptos=("CommercialPaper",), filas=(r"^Commercial paper$",)),
    Campo("deuda_lp", "Deuda a largo plazo", "Long-term debt", 9, tipo=INSTANTE,
          # el orden importa: `LongTermDebt` es el último porque algunos emisores solo lo usan en la nota de valor
          # razonable y lo dejan a cero en el balance (Oracle: un único hecho, 0, en 2022); su deuda no corriente
          # viaja en «LongTermNotesPayable», que es la misma cifra que el balance imprime
          # y en sus trimestres cambia de nombre otra vez, a «LongTermNotesAndLoans»: es la misma línea del balance
          conceptos=("LongTermDebtNoncurrent", "LongTermNotesPayable", "LongTermNotesAndLoans", "LongTermDebt"),
          filas=(r"^Long-term debt$", r"^Notes payable, non-current$")),
    Campo("arrendamientos", "Pasivos por arrendamiento (no corrientes)", "Operating lease liabilities, non-current", 9, tipo=INSTANTE,
          conceptos=("OperatingLeaseLiabilityNoncurrent",), filas=(r"^Operating lease liabilities, non-current$",)),
    Campo("pasivo_no_corriente", "Pasivo no corriente", "Non-current liabilities", 9, tipo=INSTANTE,
          conceptos=("LiabilitiesNoncurrent",), filas=(r"^Total non-?current liabilities$",),
          nota="Muchos balances no imprimen el total del pasivo, pero sí sus dos mitades: con esta y el pasivo "
               "corriente, el total se despeja (auditoría de datos)."),
    Campo("pasivo_total", "Total pasivo", "Total liabilities", 9, tipo=INSTANTE,
          conceptos=("Liabilities",), conceptos_suma=(("LiabilitiesCurrent", "LiabilitiesNoncurrent"),),
          filas=(r"^Total liabilities$",)),
    Campo("patrimonio", "Patrimonio neto", "Total stockholders' equity", 9, tipo=INSTANTE,
          # el orden importa: si el balance separa el patrimonio del grupo del total con minoritarios, el concepto de
          # la SEC (StockholdersEquity) es el del grupo, y la fila más específica es la que manda. El segundo no es
          # un sinónimo: es el total con minoritarios, y solo entra cuando la compañía dejó de etiquetar el primero
          # —Qualcomm lo hizo en 2019— porque si no el patrimonio sale N/A en todos los ejercicios del informe.
          conceptos=("StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"),
          filas=(r"^Total (?!liabilities\b)[\w .,'’&-]{2,40}? stockholders['’] equity$", r"^Total stockholders['’] equity$")),
    Campo("autocartera", "Autocartera", "Treasury stock", 9, tipo=INSTANTE, signo_informe=-1,
          conceptos=("TreasuryStockValue", "TreasuryStockCommonValue"), filas=(r"^Treasury stock",)),
    Campo("acciones_circulacion", "Acciones en circulación", "Shares outstanding", 9, tipo=INSTANTE, unidad="acciones",
          conceptos=("dei:EntityCommonStockSharesOutstanding", "CommonStockSharesOutstanding"),
          filas=(r"^Common stock, shares outstanding",)),
    # ------------------------------------------------------------- 10. Flujo de caja
    Campo("cfo", "Flujo de caja operativo", "Net cash provided by operating activities", 10,
          conceptos=("NetCashProvidedByUsedInOperatingActivities",),
          filas=(r"^Net cash provided by (\(used in\) )?operating activities$",)),
    Campo("capex", "Capex", "Purchases of property and equipment", 10, signo_informe=-1,
          # «ProductiveAssets» es como etiqueta el capex quien compra equipos y otros activos productivos en la misma
          # línea del flujo de inversión; sin él, Qualcomm no tiene capex en ningún ejercicio y con él se caen el FCF,
          # el capex sobre ventas y la mitad del apartado 10.
          conceptos=("PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets"),
          filas=(r"^Purchases of property and equipment$", r"^Capital expenditures$")),
    Campo("cfi", "Flujo de caja de inversión", "Net cash used in investing activities", 10,
          conceptos=("NetCashProvidedByUsedInInvestingActivities",),
          filas=(r"^Net cash (provided by|used in|provided by \(used in\)) investing activities$",)),
    Campo("cff", "Flujo de caja de financiación", "Net cash used in financing activities", 10,
          conceptos=("NetCashProvidedByUsedInFinancingActivities",),
          filas=(r"^Net cash (provided by|used in|provided by \(used in\)) financing activities$",)),
    Campo("dividendos", "Dividendos pagados", "Dividends paid", 10, signo_informe=-1,
          conceptos=("PaymentsOfDividends", "PaymentsOfOrdinaryDividends", "PaymentsOfDividendsCommonStock"),
          filas=(r"^Dividends paid$", r"^Payments of dividends$"),
          nota="Si el 10-K declara que nunca se han pagado, es un cero con cita; si no lo dice, N/A."),
    Campo("recompras", "Recompra de acciones", "Repurchases of common stock", 10, signo_informe=-1,
          conceptos=("PaymentsForRepurchaseOfCommonStock",),
          filas=(r"^Repurchases of common stock$",)),
    Campo("adquisiciones", "Adquisiciones (caja)", "Acquisitions, net of cash acquired", 10, signo_informe=-1,
          conceptos=("PaymentsToAcquireBusinessesNetOfCashAcquired",),
          filas=(r"^Acquisitions?, net of cash acquired$",)),
    Campo("emision_deuda", "Emisión de deuda", "Proceeds from issuance of debt", 10,
          conceptos=("ProceedsFromIssuanceOfLongTermDebt", "ProceedsFromIssuanceOfDebt", "ProceedsFromIssuanceOfSeniorLongTermDebt"),
          filas=(r"^Proceeds from issuance of (?:senior )?notes and other borrowings, net$", r"^Proceeds from issuance of debt$")),
    Campo("amortizacion_deuda", "Amortización de deuda", "Repayments of debt", 10, signo_informe=-1,
          conceptos=("RepaymentsOfLongTermDebt", "RepaymentsOfDebt"),
          filas=(r"^Repayments of debt$",)),
    Campo("fcf_compania", "Free cash flow (definición de la compañía)", "Free cash flow (company definition)", 10,
          filas=(r"^Free cash flow$",), solo_documento=True,
          nota="No-GAAP, tal como lo define la compañía en su carta; el FCF del informe es CFO − capex."),
)


@dataclass(frozen=True)
class Derivado:
    """Un campo calculado. La fórmula se imprime tal cual; `entradas` son claves de CAMPOS o de DERIVADOS."""
    clave: str
    rotulo: str
    rotulo_en: str
    seccion: int
    formula: str
    entradas: Tuple[str, ...]
    unidad: str = "USD"
    medios: Tuple[str, ...] = ()   # entradas que se toman como media entre el cierre y el anterior


DERIVADOS: Tuple[Derivado, ...] = (
    Derivado("margen_bruto", "Margen bruto", "Gross margin", 8, "(Ingresos − Coste de los ingresos) / Ingresos", ("ingresos", "coste_ingresos"), "%"),
    Derivado("ebitda", "EBITDA", "EBITDA", 8, "EBIT + Amortización del inmovilizado", ("ebit", "amortizacion")),
    Derivado("margen_ebitda", "Margen EBITDA", "EBITDA margin", 8, "EBITDA / Ingresos", ("ebitda", "ingresos"), "%"),
    Derivado("margen_ebit", "Margen operativo", "Operating margin", 8, "EBIT / Ingresos", ("ebit", "ingresos"), "%"),
    Derivado("margen_neto", "Margen neto", "Net margin", 8, "Beneficio neto / Ingresos", ("beneficio_neto", "ingresos"), "%"),
    Derivado("tipo_efectivo", "Tipo impositivo efectivo", "Effective tax rate", 8, "Impuesto sobre beneficios / Resultado antes de impuestos", ("impuestos", "bai"), "%"),
    Derivado("deuda_bruta", "Deuda bruta", "Gross debt", 9, "Deuda a corto plazo + Deuda a largo plazo", ("deuda_cp", "deuda_lp")),
    # (+ papel comercial cuando la compañía lo presenta en línea propia: `derivados.calcular` lo añade con su fórmula)
    Derivado("deuda_neta", "Deuda neta", "Net debt", 9, "Deuda bruta − Tesorería − Inversiones a corto plazo", ("deuda_bruta", "caja", "inversiones_cp")),
    Derivado("dfn_ebitda", "Deuda neta / EBITDA", "Net debt / EBITDA", 9, "Deuda neta / EBITDA", ("deuda_neta", "ebitda"), "x"),
    Derivado("fondo_maniobra", "Fondo de maniobra", "Working capital", 9, "Activo corriente − Pasivo corriente", ("activo_corriente", "pasivo_corriente")),
    Derivado("fcf", "Flujo de caja libre (FCF)", "Free cash flow (FCF)", 10, "Flujo de caja operativo − Capex", ("cfo", "capex")),
    Derivado("retribucion", "Retribución al accionista", "Shareholder returns", 10, "Dividendos pagados + Recompra de acciones", ("dividendos", "recompras")),
    Derivado("retribucion_sobre_fcf", "Retribución / FCF", "Returns / FCF", 10, "Retribución al accionista / FCF", ("retribucion", "fcf"), "%"),
    Derivado("capex_ventas", "Capex / Ingresos", "Capex / Revenues", 10, "Capex / Ingresos", ("capex", "ingresos"), "%"),
    Derivado("roe", "ROE", "ROE", 11, "Beneficio neto / Patrimonio neto medio", ("beneficio_neto", "patrimonio"), "%", medios=("patrimonio",)),
    Derivado("roa", "ROA", "ROA", 11, "Beneficio neto / Total activo medio", ("beneficio_neto", "total_activo"), "%", medios=("total_activo",)),
    Derivado("roic", "ROIC", "ROIC", 11, "EBIT × (1 − tipo efectivo) / (Patrimonio neto + Deuda bruta − Tesorería), medios",
             ("ebit", "tipo_efectivo", "patrimonio", "deuda_bruta", "caja"), "%", medios=("patrimonio", "deuda_bruta", "caja")),
    Derivado("cobertura_intereses", "Cobertura de intereses", "Interest coverage", 11, "EBIT / Gastos financieros", ("ebit", "intereses"), "x"),
    Derivado("payout", "Pay-out", "Pay-out", 11, "Dividendos pagados / Beneficio neto", ("dividendos", "beneficio_neto"), "%"),
)

_POR_CLAVE = {c.clave: c for c in CAMPOS}


def campo(clave: str) -> Campo:
    return _POR_CLAVE[clave]


def por_seccion(seccion: int) -> Tuple[Campo, ...]:
    return tuple(c for c in CAMPOS if c.seccion == seccion)
