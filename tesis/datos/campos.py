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

Las cuentas españolas (PGC y NIIF) nombran las partidas en castellano y con el
prefijo y la fórmula del modelo («A.1) RESULTADO DE EXPLOTACIÓN (1+…+13)»); el
contraste quita prefijo y fórmula antes de casar, y los patrones españoles van
después de los de EE. UU. en cada campo. Allí el signo sí dice algo: el modelo
se imprime en Debe/Haber, un gasto va en negativo y un impuesto en positivo es
un ingreso. `signo_debe_haber` dice cómo imprime el modelo cada partida para
guardarla con la convención de la SEC (el gasto en positivo) sin perder el signo
de lo que no es un gasto.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Tuple

__all__ = ["Campo", "CAMPOS", "CONTROLES", "DERIVADOS", "Derivado", "campo", "por_seccion"]

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
    # (patrón de fila, patrón que debe cumplir la cabecera de bloque): el mismo rótulo es dos partidas según el bloque
    # del balance en que va. «Deudas con entidades de crédito» es deuda a largo bajo el pasivo no corriente y a corto
    # bajo el corriente; en los estados de EE. UU. el rótulo ya lo dice, por eso el requisito va por patrón y no por campo
    filas_con_contexto: Tuple[Tuple[str, str], ...] = ()
    # cómo imprime la partida el modelo español (Debe/Haber): −1 si es un gasto o una salida (va en negativo). None =
    # la del informe. La amortización es un gasto que el informe imprime en positivo, y por eso lo declara
    signo_pgc: Optional[int] = None
    # los contrastes en que existe la partida: «sec» (emisor de EE. UU.) y «es» (cuentas españolas). Los gastos de
    # personal por naturaleza no son una línea de los estados de EE. UU.: pedirlos ahí sería contar un hueco que no lo es
    marcos: Tuple[str, ...] = ("sec", "es")

    @property
    def signo_debe_haber(self) -> int:
        if self.signo_pgc is not None:
            return self.signo_pgc
        return -1 if self.signo_informe < 0 else 1


CAMPOS: Tuple[Campo, ...] = (
    # ------------------------------------------------------------- 8. Estado de resultados
    Campo("ingresos", "Ingresos", "Revenues", 8,
          conceptos=("Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet"),
          filas=(r"^Revenues?$", r"^Total (net )?revenues?$", r"^(Total )?net sales$",
                r"^Importe neto de (?:la )?cifra de negocios?$", r"^Cifra de negocios$",
                r"^Ingresos (?:de actividades )?ordinari[oa]s$"),
          contexto_excluido=r"(?i)region|segment|UCAN|EMEA|LATAM|APAC"),
    Campo("coste_ingresos", "Coste de los ingresos", "Cost of revenues", 8, signo_informe=-1,
          conceptos=("CostOfRevenue", "CostOfGoodsAndServicesSold"),
          filas=(r"^Cost of revenues?$", r"^Cost of sales$", r"^Aprovisionamientos$"),
          nota="En las cuentas españolas, los aprovisionamientos: el coste de ventas del modelo por naturaleza."),
    Campo("marketing", "Ventas y marketing", "Sales and marketing", 8, signo_informe=-1,
          conceptos=("SellingAndMarketingExpense", "MarketingExpense"),
          filas=(r"^Sales and marketing$", r"^Marketing$"), marcos=("sec",)),
    Campo("tecnologia", "Investigación y desarrollo", "Technology and development", 8, signo_informe=-1,
          conceptos=("ResearchAndDevelopmentExpense", "TechnologyAndDevelopmentExpense"),
          filas=(r"^Technology and development$", r"^Research and development$"), marcos=("sec",)),
    Campo("generales", "Generales y administrativos", "General and administrative", 8, signo_informe=-1,
          conceptos=("GeneralAndAdministrativeExpense",),
          filas=(r"^General and administrative$",), marcos=("sec",)),
    # Quien publica ventas, generales y administrativos en una sola línea (Qualcomm) no tiene «ventas y marketing»
    # ni «generales» sueltos: se imprime su línea, y las otras dos no salen vacías, sino que no salen.
    Campo("sga", "Ventas, generales y administrativos", "Selling, general and administrative", 8, signo_informe=-1,
          conceptos=("SellingGeneralAndAdministrativeExpense",),
          filas=(r"^Selling, general and administrative$",), marcos=("sec",)),
    # El modelo español presenta los gastos por naturaleza: el de personal es una línea propia de sus cuentas, y en
    # los estados de EE. UU. (por función) no existe, así que allí ni se pide ni cuenta como hueco.
    Campo("gastos_personal", "Gastos de personal", "Staff costs", 8, signo_informe=-1,
          filas=(r"^Gastos de personal$",), marcos=("es",)),
    Campo("ebit", "EBIT (resultado operativo)", "Operating income (EBIT)", 8,
          conceptos=("OperatingIncomeLoss",),
          filas=(r"^Operating income$", r"^Income from operations$", r"^Resultado (?:de )?explotaci[óo]n$",
                r"^Resultado de (?:las )?operaciones$", r"^Beneficio (?:\(p[ée]rdida\) )?de explotaci[óo]n$")),
    Campo("intereses", "Gastos financieros", "Interest expense", 8, signo_informe=-1,
          conceptos=("InterestExpense", "InterestExpenseNonoperating", "InterestExpenseDebt"),
          filas=(r"^Interest expense$", r"^Gastos financieros$")),
    Campo("otros_financieros", "Otros ingresos y gastos", "Interest and other income (expense)", 8,
          conceptos=("NonoperatingIncomeExpense", "OtherNonoperatingIncomeExpense"),
          filas=(r"^Interest and other income \(expense\)$", r"^Other income \(expense\),? net$", r"^Resultado financiero$"),
          nota="En las cuentas españolas es el resultado financiero entero: lleva dentro los gastos financieros, que se leen también aparte."),
    Campo("bai", "Resultado antes de impuestos", "Income before income taxes", 8,
          conceptos=("IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
                     "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments"),
          conceptos_suma=(("IncomeLossFromContinuingOperationsBeforeIncomeTaxesDomestic",
                           "IncomeLossFromContinuingOperationsBeforeIncomeTaxesForeign"),),
          filas=(r"^Income before (provision for )?income taxes$", r"^Resultado (?:consolidado )?antes de impuestos$",
                r"^Resultado del (?:ejercicio|periodo) antes de impuestos$", r"^Beneficio (?:\(p[ée]rdida\) )?antes de impuestos$")),
    Campo("impuestos", "Impuesto sobre beneficios", "Provision for income taxes", 8, signo_informe=-1,
          conceptos=("IncomeTaxExpenseBenefit",),
          filas=(r"^Provision for income taxes$", r"^Income tax expense$", r"^Impuestos? sobre (?:los )?beneficios$",
                r"^Gasto por impuesto sobre (?:las )?ganancias$")),
    Campo("beneficio_neto", "Beneficio neto", "Net income", 8,
          conceptos=("NetIncomeLoss", "ProfitLoss"),
          # en unas cuentas consolidadas con socios externos, el resultado atribuido a la dominante es el del grupo, como
          # «NetIncomeLoss»: va antes que el del ejercicio, que en la misma página lleva dentro la parte de los minoritarios
          filas=(r"^Net income$", r"^Resultado (?:del (?:ejercicio|periodo) )?atribuid[oa] a (?:la )?sociedad dominante$",
                r"^Resultado atribuible a (?:los )?(?:accionistas|propietarios|tenedores de instrumentos de patrimonio neto) de la (?:sociedad )?dominante$",
                r"^Resultado (?:consolidado )?del (?:ejercicio|periodo)$", r"^Beneficio (?:\(p[ée]rdida\) )?del (?:ejercicio|periodo)$"),
          contexto_excluido=r"(?i)per share|shares"),
    # Dos maquetas del mismo bloque: la fila se llama «Basic» bajo «Earnings per share», o el bloque se llama «Basic
    # earnings per share» y la fila es «Net income» (Qualcomm, que además desglosa actividades continuadas). El
    # recuento de acciones vive en el mismo bloque y también dice «per share»: se excluye por su rótulo.
    Campo("bpa_basico", "BPA básico", "EPS, basic", 8, unidad="USD/acción",
          conceptos=("EarningsPerShareBasic",),
          filas=(r"^Basic$", r"^Net income$"), contexto=r"(?i)per share",
          contexto_excluido=r"(?i)shares used|^diluted",
          filas_con_contexto=((r"(?i)^(?:beneficios?|ganancias?|resultados?)(?: \(p[ée]rdidas?\))? b[áa]sic[oa]s? por acci[óo]n", r""),)),
    Campo("bpa_diluido", "BPA diluido", "EPS, diluted", 8, unidad="USD/acción",
          conceptos=("EarningsPerShareDiluted",),
          filas=(r"^Diluted$", r"^Net income$"), contexto=r"(?i)per share",
          contexto_excluido=r"(?i)shares used|^basic\b(?! and)",
          filas_con_contexto=((r"(?i)^(?:beneficios?|ganancias?|resultados?)(?: \(p[ée]rdidas?\))? diluid[oa]s? por acci[óo]n", r""),)),
    Campo("acciones_basicas", "Acciones medias básicas", "Weighted-average shares, basic", 8, unidad="acciones",
          conceptos=("WeightedAverageNumberOfSharesOutstandingBasic",),
          filas=(r"^Basic$",), contexto=r"(?i)weighted|shares"),
    Campo("acciones_diluidas", "Acciones medias diluidas", "Weighted-average shares, diluted", 8, unidad="acciones",
          conceptos=("WeightedAverageNumberOfDilutedSharesOutstanding",),
          filas=(r"^Diluted$",), contexto=r"(?i)weighted|shares"),
    Campo("amortizacion", "Amortización del inmovilizado", "Depreciation and amortization of property, equipment and intangibles", 8,
          conceptos=("DepreciationDepletionAndAmortization", "DepreciationAndAmortization", "DepreciationAmortizationAndAccretionNet"),
          conceptos_suma=(("Depreciation", "AmortizationOfIntangibleAssets"),),
          filas=(r"^Depreciation and amortization( of property, equipment and intangibles)?$", r"^Amortizaci[óo]n del inmovilizado$",
                r"^Dotaci[óo]n (?:a la |para )?amortizaci[óo]n(?: del inmovilizado)?$", r"^Amortizaciones$"),
          signo_pgc=-1,
          nota="Sin la amortización de contenido: esa es coste de los ingresos y no se devuelve al EBITDA."),
    Campo("amortizacion_contenido", "Amortización de contenido", "Amortization of content assets", 8, signo_informe=-1,
          filas=(r"^Amortization of content assets$",), solo_documento=True,
          nota="Netflix la declara con una extensión propia que companyfacts no sirve; sale del adjunto.", marcos=("sec",)),
    Campo("sbc", "Retribución en acciones", "Stock-based compensation", 8, signo_informe=-1,
          conceptos=("ShareBasedCompensation", "AllocatedShareBasedCompensationExpense"),
          filas=(r"^Stock-based compensation expense$",), marcos=("sec",)),
    # ------------------------------------------------------------- 9. Balance
    Campo("caja", "Tesorería y equivalentes", "Cash and cash equivalents", 9, tipo=INSTANTE,
          conceptos=("CashAndCashEquivalentsAtCarryingValue",),
          filas=(r"^Cash and cash equivalents$", r"^Efectivo y otros activos l[íi]quidos equiv(?:alentes|\.)?$",
                r"^Efectivo y equivalentes (?:al|de) efectivo$"),
          contexto_excluido=r"(?i)cash flows|beginning|end of period"),
    Campo("inversiones_cp", "Inversiones a corto plazo", "Short-term investments", 9, tipo=INSTANTE,
          conceptos=("ShortTermInvestments", "MarketableSecuritiesCurrent", "AvailableForSaleSecuritiesDebtSecuritiesCurrent"),
          filas=(r"^Short-term investments$", r"^Marketable securities$", r"^Inversiones financieras a corto plazo$")),
    # A4: valores negociables a largo plazo. Solo títulos de deuda o negociables, no participaciones estratégicas
    # (`LongTermInvestments` mezcla ambas: Qualcomm guarda ahí QSI). Entran en el puente si el analista lo confirma
    # (val.inversiones_lp); sin filas de documento: el mismo rótulo que las de corto plazo emparejaba mal (fallo [4]).
    Campo("inversiones_lp", "Valores negociables a largo plazo", "Non-current marketable securities", 9, tipo=INSTANTE,
          conceptos=("MarketableSecuritiesNoncurrent", "AvailableForSaleSecuritiesDebtSecuritiesNoncurrent")),
    Campo("activo_corriente", "Activo corriente", "Total current assets", 9, tipo=INSTANTE,
          conceptos=("AssetsCurrent",), filas=(r"^Total current assets$", r"^Activo corriente$", r"^Total activos? corrientes?$")),
    Campo("contenido", "Activos de contenido, neto", "Content assets, net", 9, tipo=INSTANTE,
          filas=(r"^Content assets, net$",), solo_documento=True,
          nota="Extensión propia de Netflix; companyfacts no la sirve.", marcos=("sec",)),
    Campo("inmovilizado", "Inmovilizado material, neto", "Property and equipment, net", 9, tipo=INSTANTE,
          conceptos=("PropertyPlantAndEquipmentNet",), filas=(r"^Property and equipment, net$",),
          # PGC: la del activo no corriente, nunca la homónima de los pagos por inversiones del estado de flujos
          filas_con_contexto=((r"^Inmovilizado material$", r"(?i)activos? no corrientes?"),)),
    Campo("fondo_comercio", "Fondo de comercio", "Goodwill", 9, tipo=INSTANTE,
          conceptos=("Goodwill",), filas=(r"^Goodwill$", r"^Fondo de comercio(?: de (?:consolidaci[óo]n|sociedades consolidadas))?$")),
    Campo("intangibles", "Intangibles", "Intangible assets, net", 9, tipo=INSTANTE,
          conceptos=("IntangibleAssetsNetExcludingGoodwill", "FiniteLivedIntangibleAssetsNet"),
          filas=(r"^Intangible assets, net$",),
          # PGC: el del activo no corriente (el del estado de flujos es un pago por inversiones)
          filas_con_contexto=((r"^Inmovilizado intangible$", r"(?i)activos? no corrientes?"),)),
    Campo("total_activo", "Total activo", "Total assets", 9, tipo=INSTANTE,
          conceptos=("Assets",), filas=(r"^Total assets$", r"^Total activos?$")),
    Campo("pasivo_corriente", "Pasivo corriente", "Total current liabilities", 9, tipo=INSTANTE,
          conceptos=("LiabilitiesCurrent",), filas=(r"^Total current liabilities$", r"^Pasivo corriente$", r"^Total pasivos? corrientes?$")),
    Campo("deuda_cp", "Deuda a corto plazo", "Short-term debt", 9, tipo=INSTANTE,
          # primero el total —«Short-term debt» del balance— y luego sus partes: Qualcomm imprime 2.489 (1.991 de
          # vencimiento corriente del largo plazo más 498 de pagarés), y leer solo la parte discrepaba del documento
          conceptos=("DebtCurrent", "LongTermDebtCurrent", "ShortTermBorrowings", "NotesPayableCurrent"),
          filas=(r"^Short-term debt$", r"^Current portion of long-term debt$", r"^Notes payable, current$")),
    # A4 (fallo [7]): quien presenta el papel comercial en su propia línea —Apple: «Commercial paper» junto a «Term
    # debt»— lo deja fuera de `LongTermDebtCurrent`; la deuda bruta lo suma entonces (`derivados.incluye_papel_comercial`).
    Campo("papel_comercial", "Papel comercial", "Commercial paper", 9, tipo=INSTANTE,
          conceptos=("CommercialPaper",), filas=(r"^Commercial paper$",), marcos=("sec",)),
    Campo("deuda_lp", "Deuda a largo plazo", "Long-term debt", 9, tipo=INSTANTE,
          # el orden importa: `LongTermDebt` es el último porque algunos emisores solo lo usan en la nota de valor
          # razonable y lo dejan a cero en el balance (Oracle: un único hecho, 0, en 2022); su deuda no corriente
          # viaja en «LongTermNotesPayable», que es la misma cifra que el balance imprime
          # y en sus trimestres cambia de nombre otra vez, a «LongTermNotesAndLoans»: es la misma línea del balance
          conceptos=("LongTermDebtNoncurrent", "LongTermNotesPayable", "LongTermNotesAndLoans", "LongTermDebt"),
          filas=(r"^Long-term debt$", r"^Notes payable, non-current$")),
    Campo("arrendamientos", "Pasivos por arrendamiento (no corrientes)", "Operating lease liabilities, non-current", 9, tipo=INSTANTE,
          conceptos=("OperatingLeaseLiabilityNoncurrent",), filas=(r"^Operating lease liabilities, non-current$",),
          # en las cuentas españolas, los acreedores por arrendamiento del pasivo no corriente: fuera de la deuda bruta,
          # como aquí se imprimen los arrendamientos
          filas_con_contexto=((r"^Acreedores por arrendamiento financiero$", r"(?i)no corriente|largo plazo"),
                              (r"^Pasivos? por arrendamientos?$", r"(?i)no corriente|largo plazo"))),
    Campo("pasivo_no_corriente", "Pasivo no corriente", "Non-current liabilities", 9, tipo=INSTANTE,
          conceptos=("LiabilitiesNoncurrent",), filas=(r"^Total non-?current liabilities$", r"^Pasivo no corriente$",
                                                     r"^Total pasivos? no corrientes?$"),
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
          filas=(r"^Total (?!liabilities\b)[\w .,'’&-]{2,40}? stockholders['’] equity$", r"^Total stockholders['’] equity$",
                r"^(?:Total )?patrimonio neto atribuid[oa] a (?:la )?sociedad dominante$", r"^(?:Total )?patrimonio neto$")),
    Campo("autocartera", "Autocartera", "Treasury stock", 9, tipo=INSTANTE, signo_informe=-1,
          conceptos=("TreasuryStockValue", "TreasuryStockCommonValue"),
          filas=(r"^Treasury stock", r"^\(?Acciones (?:y participaciones en patrimonio )?propias\)?$")),
    Campo("acciones_circulacion", "Acciones en circulación", "Shares outstanding", 9, tipo=INSTANTE, unidad="acciones",
          conceptos=("dei:EntityCommonStockSharesOutstanding", "CommonStockSharesOutstanding"),
          filas=(r"^Common stock, shares outstanding",)),
    # ------------------------------------------------------------- 10. Flujo de caja
    Campo("cfo", "Flujo de caja operativo", "Net cash provided by operating activities", 10,
          conceptos=("NetCashProvidedByUsedInOperatingActivities",),
          filas=(r"^Net cash provided by (\(used in\) )?operating activities$",
                r"^Flujos? (?:netos? )?(?:de )?efectivo (?:de (?:las )?)?activ(?:idades|\.) (?:de )?explot(?:aci[óo]n|\.)$",
                r"^Efectivo neto (?:generado|procedente|utilizado|aplicado)(?: (?:por|en|de))? (?:las )?actividades de explotaci[óo]n$")),
    Campo("capex", "Capex", "Purchases of property and equipment", 10, signo_informe=-1,
          # «ProductiveAssets» es como etiqueta el capex quien compra equipos y otros activos productivos en la misma
          # línea del flujo de inversión; sin él, Qualcomm no tiene capex en ningún ejercicio y con él se caen el FCF,
          # el capex sobre ventas y la mitad del apartado 10.
          conceptos=("PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets"),
          filas=(r"^Purchases of property and equipment$", r"^Capital expenditures$")),
    Campo("cfi", "Flujo de caja de inversión", "Net cash used in investing activities", 10,
          conceptos=("NetCashProvidedByUsedInInvestingActivities",),
          filas=(r"^Net cash (provided by|used in|provided by \(used in\)) investing activities$",
                r"^Flujos? (?:netos? )?(?:de )?efectivo (?:de (?:las )?)?activ(?:idades|\.) (?:de )?invers(?:i[óo]n|\.)$",
                r"^Efectivo neto (?:generado|procedente|utilizado|aplicado)(?: (?:por|en|de))? (?:las )?actividades de inversi[óo]n$")),
    Campo("cff", "Flujo de caja de financiación", "Net cash used in financing activities", 10,
          conceptos=("NetCashProvidedByUsedInFinancingActivities",),
          filas=(r"^Net cash (provided by|used in|provided by \(used in\)) financing activities$",
                r"^Flujos? (?:netos? )?(?:de )?efectivo (?:de (?:las )?)?activ(?:idades|\.) (?:de )?financ(?:iaci[óo]n|\.)$",
                r"^Efectivo neto (?:generado|procedente|utilizado|aplicado)(?: (?:por|en|de))? (?:las )?actividades de financiaci[óo]n$")),
    Campo("dividendos", "Dividendos pagados", "Dividends paid", 10, signo_informe=-1,
          conceptos=("PaymentsOfDividends", "PaymentsOfOrdinaryDividends", "PaymentsOfDividendsCommonStock"),
          filas=(r"^Dividends paid$", r"^Payments of dividends$", r"^Dividendos$",
                r"^Pagos por dividendos(?: y remuneraciones de otros instrumentos de patrimonio)?$"),
          nota="Si el 10-K declara que nunca se han pagado, es un cero con cita; si no lo dice, N/A."),
    Campo("recompras", "Recompra de acciones", "Repurchases of common stock", 10, signo_informe=-1,
          conceptos=("PaymentsForRepurchaseOfCommonStock",),
          # PGC: la autocartera comprada en el ejercicio, en el flujo de financiación
          filas=(r"^Repurchases of common stock$", r"^Adquisici[óo]n de instrumentos de patrimonio propio$")),
    Campo("adquisiciones", "Adquisiciones (caja)", "Acquisitions, net of cash acquired", 10, signo_informe=-1,
          conceptos=("PaymentsToAcquireBusinessesNetOfCashAcquired",),
          filas=(r"^Acquisitions?, net of cash acquired$",),
          # PGC: la compra de un negocio entre los pagos por inversiones (la de desinversiones es una venta)
          filas_con_contexto=((r"^Unidad de negocio$", r"(?i)^pagos por inversiones"),)),
    Campo("emision_deuda", "Emisión de deuda", "Proceeds from issuance of debt", 10,
          conceptos=("ProceedsFromIssuanceOfLongTermDebt", "ProceedsFromIssuanceOfDebt", "ProceedsFromIssuanceOfSeniorLongTermDebt"),
          filas=(r"^Proceeds from issuance of (?:senior )?notes and other borrowings, net$", r"^Proceeds from issuance of debt$")),
    Campo("amortizacion_deuda", "Amortización de deuda", "Repayments of debt", 10, signo_informe=-1,
          # Qualcomm pasa de «RepaymentsOfLongTermDebt» a «RepaymentsOfOtherLongTermDebt» en el FY23: con solo el primero,
          # N/A desde 2023 con la cifra publicada (fallo [59]). El papel comercial va aparte, como en su estado de flujos
          conceptos=("RepaymentsOfLongTermDebt", "RepaymentsOfOtherLongTermDebt", "RepaymentsOfDebt"),
          filas=(r"^Repayments of debt$",)),
    Campo("fcf_compania", "Free cash flow (definición de la compañía)", "Free cash flow (company definition)", 10,
          filas=(r"^Free cash flow$",), solo_documento=True,
          nota="No-GAAP, tal como lo define la compañía en su carta; el FCF del informe es CFO − capex.", marcos=("sec",)),
)


# las filas del flujo de financiación del PGC bajo «Emisión» y «Devolución y amortización de»: el modelo no imprime su
# total; la emisión y la amortización de deuda del informe son su suma (derivado, con fórmula, en `contraste`)
_PARTES_DEUDA_PGC = (
    ("obligaciones", "Obligaciones y valores similares", r"^Obligaciones y (?:otros )?valores (?:similares|negociables)$"),
    ("especiales", "Deudas con características especiales", r"^Deudas con caracter[íi]sticas especiales$"),
    ("entidades", "Deudas con entidades de crédito", r"^Deudas? con entidades de cr[ée]dito$"),
    ("grupo", "Deudas con empresas del grupo y asociadas", r"^Deudas? con empresas del grupo y asociadas$"),
    ("otras", "Otras deudas", r"^Otras deudas$"),
)


# Cifras de control: se leen de las cuentas españolas para comprobar que los estados cuadran entre sí (el auditor de
# datos), no se imprimen ni se piden. Una es el mismo hecho que el total del activo dicho en la otra mitad del balance;
# la otra, la caja del balance dicha al final del estado de flujos. Cada par se afirma igual (regla 13).
CONTROLES: Tuple[Campo, ...] = (
    Campo("pasivo_y_patrimonio", "Total patrimonio neto y pasivo", "Total equity and liabilities", 9, tipo=INSTANTE,
          filas=(r"^Total patrimonio neto y pasivos?$", r"^Total pasivos? y patrimonio neto$"), solo_documento=True,
          marcos=("es",)),
    Campo("efectivo_final", "Efectivo al final del periodo (estado de flujos)", "Cash at end of period", 10,
          filas=(r"^Efectivo (?:o|y) (?:otros activos l[íi]quidos )?equivalentes al final (?:del )?(?:ejercicio|periodo)$",
                 r"^Efectivo y equivalentes al efectivo al final (?:del )?(?:ejercicio|periodo)$"),
          solo_documento=True, marcos=("es",)),
    # la deuda financiera de unas cuentas españolas: sus partes publicadas, corrientes y no corrientes, que se suman
    # (derivado, con fórmula, en `contraste`); los arrendamientos van aparte, como en EE. UU. (06 §5)
    Campo("deuda_ec_cp", "Deudas con entidades de crédito a corto plazo", "Bank debt, current", 9, tipo=INSTANTE, filas=(),
          filas_con_contexto=((r"^Deudas? con entidades de cr[ée]dito$", r"(?i)(?<!no )corriente|corto plazo"),),
          solo_documento=True, marcos=("es",)),
    Campo("deuda_ec_lp", "Deudas con entidades de crédito a largo plazo", "Bank debt, non-current", 9, tipo=INSTANTE, filas=(),
          filas_con_contexto=((r"^Deudas? con entidades de cr[ée]dito$", r"(?i)no corriente|largo plazo"),),
          solo_documento=True, marcos=("es",)),
    Campo("deuda_otros_cp", "Otros pasivos financieros a corto plazo", "Other financial liabilities, current", 9, tipo=INSTANTE,
          filas=(), filas_con_contexto=((r"^Otros pasivos financieros$", r"(?i)(?<!no )corriente|corto plazo"),),
          solo_documento=True, marcos=("es",)),
    Campo("deuda_otros_lp", "Otros pasivos financieros a largo plazo", "Other financial liabilities, non-current", 9, tipo=INSTANTE,
          filas=(), filas_con_contexto=((r"^Otros pasivos financieros$", r"(?i)no corriente|largo plazo"),),
          solo_documento=True, marcos=("es",)),
    Campo("deuda_grupo_cp", "Deudas con empresas del grupo y asociadas a corto plazo", "Group debt, current", 9, tipo=INSTANTE,
          filas=(r"^Deudas (?:con )?empresas (?:del )?grupo y asociadas a (?:corto plazo|C/P)$",), solo_documento=True, marcos=("es",)),
    Campo("deuda_grupo_lp", "Deudas con empresas del grupo y asociadas a largo plazo", "Group debt, non-current", 9, tipo=INSTANTE,
          filas=(r"^Deudas (?:con )?empresas (?:del )?grupo y asociadas a (?:largo plazo|L/P)$",), solo_documento=True, marcos=("es",)),
    # el subtotal del modelo (II. «Deudas a largo plazo», III. «Deudas a corto plazo»): cuando se publica, manda sobre la
    # suma de sus partes, que el modelo normalizado deja a menudo en blanco
    Campo("deuda_sub_cp", "Deudas a corto plazo (subtotal)", "Current borrowings (subtotal)", 9, tipo=INSTANTE,
          filas=(r"^Deudas a (?:corto plazo|C/P)$",), solo_documento=True, marcos=("es",)),
    Campo("deuda_sub_lp", "Deudas a largo plazo (subtotal)", "Non-current borrowings (subtotal)", 9, tipo=INSTANTE,
          filas=(r"^Deudas a (?:largo plazo|L/P)$",), solo_documento=True, marcos=("es",)),
    # el capex de un estado de flujos español: dos filas bajo «Pagos por inversiones», que se suman (derivado, con
    # fórmula, en `contraste`); nunca las homónimas de «Cobros por desinversiones»
    Campo("pagos_intangible", "Pagos por inversiones en inmovilizado intangible", "Payments for intangible assets", 10,
          filas=(), filas_con_contexto=((r"^Inmovilizado intangible$", r"(?i)^pagos por inversiones"),),
          solo_documento=True, marcos=("es",), signo_pgc=-1),
    # la parte del resultado de un grupo que es de sus socios externos: sin ella, «beneficio neto = BAI − impuesto» no
    # cierra en unas consolidadas con minoritarios, porque el beneficio del informe es el atribuido a la dominante
    Campo("minoritarios", "Resultado atribuido a socios externos", "Net income attributable to noncontrolling interests", 8,
          filas=(r"^Resultado (?:del (?:ejercicio|periodo) )?atribuid[oa] a (?:los )?(?:socios externos|intereses minoritarios|participaciones no dominantes)$",
                 r"^Resultado atribuible a (?:los )?(?:socios externos|intereses minoritarios|participaciones no dominantes)$"),
          solo_documento=True, marcos=("es",)),
    *(Campo(f"{prefijo}_{clave}", f"{titulo}: {rotulo.lower()}", f"{titulo_en}: {clave}", 10, filas=(),
            filas_con_contexto=((patron, bloque),), solo_documento=True, marcos=("es",), signo_pgc=signo)
      for prefijo, titulo, titulo_en, bloque, signo in (
          ("emision", "Emisión de deudas", "Debt issued", r"(?i)^emisi[óo]n$", 1),
          ("devolucion", "Devolución y amortización de deudas", "Debt repaid", r"(?i)^devoluci[óo]n y amortizaci[óo]n", -1))
      for clave, rotulo, patron in _PARTES_DEUDA_PGC),
    Campo("pagos_material", "Pagos por inversiones en inmovilizado material", "Payments for property and equipment", 10,
          filas=(), filas_con_contexto=((r"^Inmovilizado material$", r"(?i)^pagos por inversiones"),),
          solo_documento=True, marcos=("es",), signo_pgc=-1),
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
    # capital invertido = patrimonio + deuda neta, la del glosario (config/definiciones.yaml): una sola definición [14]
    Derivado("roic", "ROIC", "ROIC", 11, "EBIT × (1 − tipo efectivo) / (Patrimonio neto + Deuda bruta − Tesorería − Inversiones a corto plazo), medios",
             ("ebit", "tipo_efectivo", "patrimonio", "deuda_neta"), "%", medios=("patrimonio", "deuda_neta")),
    Derivado("cobertura_intereses", "Cobertura de intereses", "Interest coverage", 11, "EBIT / Gastos financieros", ("ebit", "intereses"), "x"),
    Derivado("payout", "Pay-out", "Pay-out", 11, "Dividendos pagados / Beneficio neto", ("dividendos", "beneficio_neto"), "%"),
)

# El numerador del BPA: el beneficio atribuible a los accionistas ordinarios, neto de dividendos preferentes. No es una
# fila del informe; lo usa la derivación del BPA del 4T (`contraste._q4_por_accion`), que con el beneficio neto daba a
# Oracle, con preferentes desde febrero de 2026, un 1,48 donde es 1,45 (auditoría del 27/09, fallo [19])
BENEFICIO_ORDINARIOS: Tuple[Campo, ...] = (
    Campo("beneficio_ordinarios_diluido", "Beneficio atribuible a los accionistas ordinarios (diluido)",
          "Net income available to common stockholders, diluted", 8,
          conceptos=("NetIncomeLossAvailableToCommonStockholdersDiluted",), solo_documento=False, marcos=("sec",)),
    Campo("beneficio_ordinarios_basico", "Beneficio atribuible a los accionistas ordinarios (básico)",
          "Net income available to common stockholders, basic", 8,
          conceptos=("NetIncomeLossAvailableToCommonStockholdersBasic",), solo_documento=False, marcos=("sec",)),
)

_POR_CLAVE = {c.clave: c for c in CAMPOS + CONTROLES + BENEFICIO_ORDINARIOS}


def campo(clave: str) -> Campo:
    return _POR_CLAVE[clave]


def por_seccion(seccion: int) -> Tuple[Campo, ...]:
    return tuple(c for c in CAMPOS if c.seccion == seccion)
