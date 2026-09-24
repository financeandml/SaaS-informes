"""Paso 4 de la prueba: el sistema contrasta cada dato. Uno por uno.

Es el corazón de lo que el SaaS promete y lo que PLANTILLA_TESIS.md §5 fija:
para cada campo × periodo del informe se pone al lado el hecho XBRL de la SEC y
la casilla del adjunto, y se dice en qué han quedado:

    ✓  confirmado        SEC y documento coinciden (±½ unidad de la escala impresa)
    ≠  discrepante       los dos existen y no coinciden → bloquea la emisión
    ◐  solo SEC          no se halló en los adjuntos → exige reconocimiento
    ◑  solo documento    la SEC no lo publica → hecho de documento, con certeza
    —  ninguno           hueco: se pide al analista
    ∑  derivado          calculado de hechos ya contrastados, con fórmula impresa

Y además de la tabla del informe, dos comprobaciones que van más allá de ella,
porque el analista pidió «palabra por palabra, dato por dato»:

**Barrido literal.** Cada hecho XBRL que la SEC atribuye a uno de los tres
formularios adjuntos (10-K y dos 10-Q) se busca escrito en el PDF de ese mismo
formulario. Son cientos de cifras, no las veinte de la tabla, y da una medida
honesta de cuánto del documento está confirmado y cuánto no.

**Integridad textual.** El texto del PDF adjunto se compara palabra a palabra con
el texto del HTML que la SEC sirve del mismo depósito. Si el analista hubiese
subido una versión alterada, un borrador o un documento de otro emisor, se ve
aquí, antes de leer una sola cifra.

Lo que este módulo NO hace: elegir «el valor que cuadra». Si hay discrepancia,
se imprimen los dos valores con su página y decide el analista.
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

AQUI = Path(__file__).resolve().parent
DATOS = AQUI / "datos"
SEC = DATOS / "sec"
TEXTO = DATOS / "texto"

GLIFO = {"confirmado": "✓", "discrepante": "≠", "solo_sec": "◐", "solo_documento": "◑",
         "ninguno": "—", "derivado": "∑"}

# Los tres formularios adjuntos, por número de acceso: los que la SEC cita en `accn`.
ACCN_ADJUNTOS = {"0001065280-26-000034": "10K_20251231",
                 "0001065280-26-000138": "10Q_20260331",
                 "0001065280-26-000212": "10Q_20260630"}
FICHERO_SEC = {"10K_20251231": "10-K_2026-01-23_0001065280-26-000034.txt",
               "10Q_20260331": "10-Q_2026-04-17_0001065280-26-000138.txt",
               "10Q_20260630": "10-Q_2026-07-17_0001065280-26-000212.txt"}


# ---------------------------------------------------------------------------
# El catálogo: qué campos publica el informe y cómo se llaman en cada sitio
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Campo:
    clave: str
    rotulo: str
    conceptos: tuple                  # conceptos XBRL en orden de preferencia
    fila: str                         # regex del rótulo de fila en el documento
    estado: tuple                     # tipos de tabla donde buscar la fila
    unidad: str = "USD"               # USD | shares | USD/shares | pure
    abs: bool = False                 # el documento imprime el signo contable, la SEC el importe
    ocurrencia: int = 1               # «Diluted» aparece dos veces: BPA y acciones
    instante: bool = False            # partida de balance


CAMPOS: tuple = (
    # Cuenta de resultados
    Campo("ingresos", "Ingresos", ("Revenues",), r"^Revenues?$", ("resultados", "?", "no_gaap")),
    Campo("coste_ingresos", "Coste de los ingresos", ("CostOfRevenue",), r"^Cost of revenues$", ("resultados",)),
    Campo("marketing", "Ventas y marketing", ("SellingAndMarketingExpense",), r"^Sales and marketing$", ("resultados",)),
    Campo("tecnologia", "Tecnología y desarrollo", ("ResearchAndDevelopmentExpense",), r"^Technology and development$", ("resultados",)),
    Campo("generales", "Generales y administrativos", ("GeneralAndAdministrativeExpense",), r"^General and administrative$", ("resultados",)),
    Campo("ebit", "Resultado operativo (EBIT)", ("OperatingIncomeLoss",), r"^Operating income$", ("resultados", "?")),
    Campo("intereses", "Gastos financieros", ("InterestExpenseNonoperating", "InterestExpense"), r"^Interest expense$", ("resultados",), abs=True),
    Campo("otros_financieros", "Intereses y otros ingresos (gastos)", ("NonoperatingIncomeExpense",), r"^Interest and other income \(expense\)$", ("resultados",)),
    Campo("bai", "Resultado antes de impuestos", ("IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",), r"^Income before income taxes$", ("resultados",)),
    Campo("impuestos", "Impuesto sobre beneficios", ("IncomeTaxExpenseBenefit",), r"^Provision for income taxes$", ("resultados",), abs=True),
    Campo("beneficio_neto", "Beneficio neto", ("NetIncomeLoss",), r"^Net income$", ("resultados", "flujos", "integral", "?")),
    Campo("bpa_basico", "BPA básico", ("EarningsPerShareBasic",), r"^Basic$", ("resultados",), unidad="USD/shares", ocurrencia=1),
    Campo("bpa_diluido", "BPA diluido", ("EarningsPerShareDiluted",), r"^Diluted( EPS)?$", ("resultados", "?"), unidad="USD/shares", ocurrencia=1),
    Campo("acciones_basicas", "Acciones medias básicas", ("WeightedAverageNumberOfSharesOutstandingBasic",), r"^Basic$", ("resultados",), unidad="shares", ocurrencia=2),
    Campo("acciones_diluidas", "Acciones medias diluidas", ("WeightedAverageNumberOfDilutedSharesOutstanding",), r"^Diluted$|^Shares \(FD\)$", ("resultados", "?"), unidad="shares", ocurrencia=2),
    Campo("amortizacion", "Depreciación y amortización (inmovilizado e intangibles)", ("DepreciationDepletionAndAmortization",), r"^Depreciation and amortization of property, equipment and intangibles$", ("flujos",)),
    Campo("amortizacion_contenido", "Amortización de contenidos", (), r"^Amortization of content assets$", ("flujos",)),
    Campo("sbc", "Retribución en acciones", ("ShareBasedCompensation",), r"^Stock-based compensation expense$", ("flujos",)),
    # Balance
    Campo("caja", "Tesorería y equivalentes", ("CashAndCashEquivalentsAtCarryingValue",), r"^Cash and cash equivalents$", ("balance",), instante=True),
    Campo("inversiones_cp", "Inversiones a corto plazo", ("ShortTermInvestments",), r"^Short-term investments$", ("balance",), instante=True),
    Campo("activo_corriente", "Activo corriente", ("AssetsCurrent",), r"^Total current assets$", ("balance",), instante=True),
    Campo("contenido", "Activos de contenido, netos", ("FiniteLivedIntangibleAssetsNet",), r"^Content assets, net$", ("balance",), instante=True),
    Campo("inmovilizado", "Inmovilizado material, neto", ("PropertyPlantAndEquipmentNet",), r"^Property and equipment, net$", ("balance",), instante=True),
    Campo("total_activo", "Total activo", ("Assets",), r"^Total assets$", ("balance",), instante=True),
    Campo("pasivo_corriente", "Pasivo corriente", ("LiabilitiesCurrent",), r"^Total current liabilities$", ("balance",), instante=True),
    Campo("deuda_cp", "Deuda a corto plazo", ("ShortTermBorrowings", "LongTermDebtCurrent", "DebtCurrent"), r"^Short-term debt$", ("balance",), instante=True),
    Campo("deuda_lp", "Deuda a largo plazo", ("LongTermDebtNoncurrent",), r"^Long-term debt$", ("balance",), instante=True),
    Campo("pasivo_total", "Total pasivo", ("Liabilities",), r"^Total liabilities$", ("balance",), instante=True),
    Campo("patrimonio", "Patrimonio neto", ("StockholdersEquity",), r"^Total stockholders.? equity$", ("balance",), instante=True),
    Campo("autocartera", "Autocartera (coste)", ("TreasuryStockCommonValue", "TreasuryStockValue"), r"^Treasury stock at cost", ("balance",), instante=True, abs=True),
    Campo("arrendamientos", "Pasivos por arrendamiento operativo", ("OperatingLeaseLiability",), r"^$", (), instante=True),
    # Flujos de caja
    Campo("cfo", "Flujo de caja de explotación", ("NetCashProvidedByUsedInOperatingActivities",), r"^Net cash provided by operating activities$", ("flujos", "no_gaap", "?")),
    Campo("capex", "Inversión en inmovilizado (capex)", ("PaymentsToAcquirePropertyPlantAndEquipment",), r"^Purchases of property and equipment$", ("flujos", "no_gaap"), abs=True),
    Campo("adquisiciones", "Adquisiciones (caja)", ("PaymentsToAcquireBusinessesNetOfCashAcquired",), r"^Acquisitions?$", ("flujos",), abs=True),
    Campo("cfi", "Flujo de caja de inversión", ("NetCashProvidedByUsedInInvestingActivities",), r"^Net cash (provided by|used in|provided by \(used in\)) investing activities$", ("flujos",)),
    Campo("cff", "Flujo de caja de financiación", ("NetCashProvidedByUsedInFinancingActivities",), r"^Net cash (provided by|used in|provided by \(used in\)) financing activities$", ("flujos",)),
    Campo("recompras", "Recompra de acciones", ("PaymentsForRepurchaseOfCommonStock",), r"^Repurchases of common stock$", ("flujos",), abs=True),
    Campo("dividendos", "Dividendos pagados", ("PaymentsOfDividends", "PaymentsOfDividendsCommonStock"), r"^Dividends paid$", ("flujos",), abs=True),
    Campo("emision_deuda", "Emisión de deuda", ("ProceedsFromIssuanceOfDebt", "ProceedsFromIssuanceOfLongTermDebt"), r"^Proceeds from issuance of debt$", ("flujos",)),
    Campo("amortizacion_deuda", "Amortización de deuda", ("RepaymentsOfLongTermDebt", "RepaymentsOfDebt"), r"^Repayments of debt$", ("flujos",), abs=True),
    Campo("fcf_doc", "Flujo de caja libre (no GAAP, según la compañía)", (), r"^Non-GAAP free cash flow$|^Free Cash Flow$", ("no_gaap", "?")),
)
POR_CLAVE = {c.clave: c for c in CAMPOS}


# ---------------------------------------------------------------------------
# Periodos
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Periodo:
    clave: str          # «FY2025», «Q2'26», «6M'26», «@2025-12-31»
    inicio: Optional[str]
    fin: str
    meses: int          # 0 = instante
    rotulo: str
    derivado: Optional[str] = None      # fórmula si el periodo no existe como tal en XBRL

    @property
    def llave(self) -> str:
        return f"{self.inicio or ''}..{self.fin}" if self.meses else f"@{self.fin}"


def _fy(a: int) -> Periodo:
    return Periodo(f"FY{a}", f"{a}-01-01", f"{a}-12-31", 12, f"{a}")


def _q(q: int, a: int) -> Periodo:
    ini = {1: "01-01", 2: "04-01", 3: "07-01", 4: "10-01"}[q]
    fin = {1: "03-31", 2: "06-30", 3: "09-30", 4: "12-31"}[q]
    return Periodo(f"Q{q}'{a % 100:02d}", f"{a}-{ini}", f"{a}-{fin}", 3, f"{q}T {a}",
                   derivado="FY − 9M" if q == 4 else None)


ANUALES = [_fy(a) for a in (2021, 2022, 2023, 2024, 2025)]
TRIMESTRES = [_q(2, 2025), _q(3, 2025), _q(4, 2025), _q(1, 2026), _q(2, 2026)]
SEMESTRES = [Periodo("6M'25", "2025-01-01", "2025-06-30", 6, "1S 2025"),
             Periodo("6M'26", "2026-01-01", "2026-06-30", 6, "1S 2026")]
NUEVE_MESES = Periodo("9M'25", "2025-01-01", "2025-09-30", 9, "9M 2025")
INSTANTES_ANUALES = [Periodo(f"@{a}-12-31", None, f"{a}-12-31", 0, f"31-dic-{a}") for a in (2021, 2022, 2023, 2024, 2025)]
INSTANTES_TRIM = [Periodo(f"@{f}", None, f, 0, r) for f, r in
                  (("2025-06-30", "30-jun-25"), ("2025-09-30", "30-sep-25"), ("2026-03-31", "31-mar-26"), ("2026-06-30", "30-jun-26"))]


# ---------------------------------------------------------------------------
# Hechos SEC
# ---------------------------------------------------------------------------

def cargar_facts() -> dict:
    return json.loads((SEC / "companyfacts.json").read_text(encoding="utf-8"))["facts"]


def hecho_sec(facts: dict, campo: Campo, per: Periodo) -> Optional[dict]:
    """El hecho XBRL de ese campo en ese periodo: el último presentado, y si
    difiere de una presentación anterior, se dice (reexpresión)."""
    for concepto in campo.conceptos:
        for tax in ("us-gaap", "dei", "srt"):
            v = facts.get(tax, {}).get(concepto)
            if not v:
                continue
            lst = v["units"].get(campo.unidad) or []
            if per.meses:
                cand = [r for r in lst if r.get("start") == per.inicio and r["end"] == per.fin]
            else:
                cand = [r for r in lst if "start" not in r and r["end"] == per.fin]
            if not cand:
                continue
            cand.sort(key=lambda r: r["filed"])
            ult = cand[-1]
            anteriores = [r for r in cand[:-1] if abs(r["val"] - ult["val"]) > 0.5]
            return dict(valor=ult["val"], concepto=f"{tax}:{concepto}", form=ult["form"], filed=ult["filed"],
                        accn=ult["accn"], fy=ult.get("fy"), fp=ult.get("fp"),
                        reexpresado=[dict(valor=r["val"], form=r["form"], filed=r["filed"]) for r in anteriores] or None)
    return None


def derivar_q4(facts: dict, campo: Campo, a: int) -> Optional[dict]:
    """Q4 = FY − 9M, con las dos entradas citadas. Solo para flujos (no instantes)."""
    fy = hecho_sec(facts, campo, _fy(a))
    m9 = hecho_sec(facts, campo, Periodo("9M", f"{a}-01-01", f"{a}-09-30", 9, ""))
    if not fy or not m9:
        return None
    if campo.unidad == "USD/shares":
        return None       # un BPA trimestral no es la resta de dos BPA
    return dict(valor=fy["valor"] - m9["valor"], concepto=fy["concepto"], form="derivado",
                filed=max(fy["filed"], m9["filed"]), accn=None, fy=a, fp="Q4", reexpresado=None,
                formula=f"FY{a} ({fy['valor']:,}) − 9M{a} ({m9['valor']:,})",
                entradas=[fy, m9])


# ---------------------------------------------------------------------------
# Candidatos de los documentos
# ---------------------------------------------------------------------------

def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.replace("’", "'").replace("`", "'")).strip()


def candidatos(tablas: dict, campo: Campo) -> dict:
    """{llave de periodo: [candidatos]} para un campo, de todos los adjuntos."""
    salida: dict = defaultdict(list)
    for doc, lista in tablas.items():
        for t in lista:
            if not t["columnas"] or t["tipo"] not in campo.estado:
                continue
            vistos = 0
            for f in t["filas"]:
                if not re.search(campo.fila, _norm(f["etiqueta"]), re.I):
                    continue
                vistos += 1
                if vistos != campo.ocurrencia and not (campo.ocurrencia == 1 and vistos > 1 and t["tipo"] != "resultados"):
                    # Segunda aparición de «Basic»/«Diluted» en la cuenta: son acciones.
                    if not (vistos > campo.ocurrencia and campo.ocurrencia == 2):
                        continue
                    if vistos != campo.ocurrencia:
                        continue
                for col, celda in zip(t["columnas"], f["celdas"]):
                    if col.get("prevision"):
                        continue
                    if celda is None:
                        salida[_llave(col)].append(dict(doc=doc, pagina=t["pagina"], linea=f["linea"], valor=None,
                                                          escala=t["escala"], literal=f["literal"], hueco=True,
                                                          certeza=t["certeza"]))
                        continue
                    # Las acciones van «in thousands» como los importes; el BPA y los % no.
                    escala = 1 if campo.unidad in ("USD/shares", "pure") else t["escala"]
                    salida[_llave(col)].append(dict(doc=doc, pagina=t["pagina"], linea=f["linea"],
                                                      valor=celda * escala, escala=escala, literal=f["literal"],
                                                      hueco=False, certeza=t["certeza"]))
    return salida


def _llave(col: dict) -> str:
    return f"{col['inicio'] or ''}..{col['fin']}" if col["meses"] else f"@{col['fin']}"


def previsiones(tablas: dict) -> list:
    """Las columnas «Forecast» de la carta: objetivos de la compañía, con fecha."""
    salida = []
    for doc, lista in tablas.items():
        for t in lista:
            if not t["columnas"]:
                continue
            for j, col in enumerate(t["columnas"]):
                if not col.get("prevision"):
                    continue
                for f in t["filas"]:
                    v = f["celdas"][j] if j < len(f["celdas"]) else None
                    if v is not None and not f["etiqueta"].startswith("1 "):
                        salida.append(dict(doc=doc, pagina=t["pagina"], linea=f["linea"], concepto=f["etiqueta"],
                                           periodo=col["etiqueta"], fin=col["fin"], valor=v, escala=t["escala"]))
    return salida


# ---------------------------------------------------------------------------
# El contraste
# ---------------------------------------------------------------------------

def tolerancia(campo: Campo, escala: int) -> float:
    if campo.unidad == "USD/shares":
        return 0.005
    if campo.unidad == "pure":
        return 0.0005
    return escala / 2


def contrastar(campo: Campo, per: Periodo, sec: Optional[dict], cands: list) -> dict:
    con_valor = [c for c in cands if not c["hueco"]]
    huecos = [c for c in cands if c["hueco"]]
    fila = dict(campo=campo.clave, rotulo=campo.rotulo, periodo=per.__dict__, sec=sec, documentos=cands)
    if sec is None and not con_valor:
        fila.update(resultado="ninguno", nota="Ni la SEC ni los adjuntos traen esta cifra." +
                    (" Los adjuntos la imprimen como hueco (—)." if huecos else ""))
        # Rule 2: hueco declarado en el documento ≠ no hay dato
        if huecos:
            fila.update(resultado="solo_documento", valor=0.0,
                        nota="El documento imprime un guion en esta casilla: importe nulo declarado, no ausencia. La SEC no publica el concepto para este periodo.")
    elif sec is None:
        vals = sorted({round(c["valor"], 6) for c in con_valor})
        fila.update(resultado="solo_documento", valor=con_valor[0]["valor"],
                    nota=("La SEC no publica este concepto con esa etiqueta; se toma del documento y exige confirmación del analista."
                          if len(vals) == 1 else f"Los adjuntos no coinciden entre sí: {vals}. Decide el analista."))
        if len(vals) > 1:
            fila["resultado"] = "discrepante"
    elif not con_valor:
        fila.update(resultado="solo_sec", valor=sec["valor"],
                    nota="Sin contraste documental: los adjuntos no cubren este periodo o no imprimen la fila. Exige reconocimiento del analista.")
    else:
        ok, mal = [], []
        for c in con_valor:
            a, b = sec["valor"], c["valor"]
            if campo.abs:
                a, b = abs(a), abs(b)
            (ok if abs(a - b) <= tolerancia(campo, c["escala"]) else mal).append(c)
        if ok and not mal:
            fila.update(resultado="confirmado", valor=sec["valor"],
                        nota=f"Coincide en {len(ok)} casilla(s) de {len({c['doc'] for c in ok})} adjunto(s).")
        elif ok and mal:
            fila.update(resultado="discrepante", valor=sec["valor"],
                        nota=f"Coincide en {len(ok)} casilla(s) y difiere en {len(mal)}: " +
                             "; ".join(f"{c['doc']} p.{c['pagina']} = {c['valor']:,}" for c in mal))
        else:
            fila.update(resultado="discrepante", valor=None,
                        nota="SEC y documento no coinciden: " +
                             "; ".join(f"{c['doc']} p.{c['pagina']} = {c['valor']:,}" for c in mal) +
                             f" frente a SEC {sec['valor']:,}. Decide el analista.")
    if sec and sec.get("reexpresado"):
        fila["nota"] += " Reexpresado: en " + ", ".join(f"{r['form']} de {r['filed']} decía {r['valor']:,}" for r in sec["reexpresado"]) + "."
    fila["glifo"] = GLIFO[fila["resultado"]]
    return fila


def matriz(facts: dict, tablas: dict) -> list:
    filas = []
    for campo in CAMPOS:
        cands = candidatos(tablas, campo)
        periodos = (INSTANTES_ANUALES + INSTANTES_TRIM) if campo.instante else (ANUALES + TRIMESTRES + SEMESTRES + [NUEVE_MESES])
        for per in periodos:
            if per.derivado and not campo.instante:
                sec = derivar_q4(facts, campo, int(per.fin[:4]))
                fila = contrastar(campo, per, sec, cands.get(per.llave, []))
                if sec:
                    fila["derivado"] = dict(formula=sec["formula"], entradas=sec["entradas"])
                    if fila["resultado"] == "solo_sec":
                        fila["nota"] = "Derivado de dos hechos SEC (FY − 9M); ningún adjunto imprime el trimestre por separado."
                filas.append(fila)
                continue
            sec = hecho_sec(facts, campo, per)
            filas.append(contrastar(campo, per, sec, cands.get(per.llave, [])))
    return filas


# ---------------------------------------------------------------------------
# Derivados del informe: una fórmula, sus entradas, y solo de cifras contrastadas
# ---------------------------------------------------------------------------

def _valor(idx: dict, campo: str, per: str) -> Optional[float]:
    f = idx.get((campo, per))
    if not f or f["resultado"] in ("ninguno",) or f.get("valor") is None:
        return None
    return f["valor"]


def derivados(filas: list) -> list:
    idx = {(f["campo"], f["periodo"]["clave"]): f for f in filas}
    out = []

    def d(clave, rotulo, per, formula, entradas, valor, unidad="USD"):
        out.append(dict(campo=clave, rotulo=rotulo, periodo=per, formula=formula, entradas=entradas,
                        valor=valor, unidad=unidad, resultado="derivado", glifo="∑",
                        estado_entradas=[idx[e]["resultado"] for e in entradas if e in idx]))

    pers = [p.clave for p in ANUALES + TRIMESTRES + SEMESTRES]
    for per in pers:
        ing = _valor(idx, "ingresos", per); ebit = _valor(idx, "ebit", per); da = _valor(idx, "amortizacion", per)
        bn = _valor(idx, "beneficio_neto", per); cfo = _valor(idx, "cfo", per); capex = _valor(idx, "capex", per)
        bai = _valor(idx, "bai", per); imp = _valor(idx, "impuestos", per); cost = _valor(idx, "coste_ingresos", per)
        rec = _valor(idx, "recompras", per); div = _valor(idx, "dividendos", per)
        if ing is not None and cost is not None:
            d("margen_bruto", "Margen bruto", per, "(Ingresos − Coste de los ingresos) / Ingresos", [("ingresos", per), ("coste_ingresos", per)], (ing - cost) / ing, "pure")
        if ebit is not None and da is not None:
            d("ebitda", "EBITDA", per, "EBIT + D&A (inmovilizado e intangibles; no incluye amortización de contenidos)", [("ebit", per), ("amortizacion", per)], ebit + da)
            if ing:
                d("margen_ebitda", "Margen EBITDA", per, "EBITDA / Ingresos", [("ebit", per), ("amortizacion", per), ("ingresos", per)], (ebit + da) / ing, "pure")
        if ebit is not None and ing:
            d("margen_ebit", "Margen operativo", per, "EBIT / Ingresos", [("ebit", per), ("ingresos", per)], ebit / ing, "pure")
        if bn is not None and ing:
            d("margen_neto", "Margen neto", per, "Beneficio neto / Ingresos", [("beneficio_neto", per), ("ingresos", per)], bn / ing, "pure")
        if bai and imp is not None:
            d("tipo_efectivo", "Tipo impositivo efectivo", per, "Impuesto / Resultado antes de impuestos", [("impuestos", per), ("bai", per)], abs(imp) / bai, "pure")
        if cfo is not None and capex is not None:
            d("fcf", "Flujo de caja libre", per, "Flujo de explotación − Capex", [("cfo", per), ("capex", per)], cfo - abs(capex))
            if rec is not None:
                d("retribucion_accionista", "Retribución al accionista (recompras + dividendos)", per,
                  "Recompras + Dividendos (dividendos: sin hecho → se suma solo lo publicado)", [("recompras", per), ("dividendos", per)], abs(rec) + abs(div or 0))
    # Crecimientos interanuales
    for campo in ("ingresos", "ebit", "beneficio_neto", "bpa_diluido", "cfo"):
        for a in (2022, 2023, 2024, 2025):
            v, v0 = _valor(idx, campo, f"FY{a}"), _valor(idx, campo, f"FY{a-1}")
            if v is not None and v0:
                d(f"crec_{campo}", f"Crecimiento interanual · {POR_CLAVE[campo].rotulo}", f"FY{a}", f"{POR_CLAVE[campo].rotulo} FY{a} / FY{a-1} − 1", [(campo, f"FY{a}"), (campo, f"FY{a-1}")], v / v0 - 1, "pure")
        for q, q0 in (("Q2'26", "Q2'25"),):
            v, v0 = _valor(idx, campo, q), _valor(idx, campo, q0)
            if v is not None and v0:
                d(f"crec_{campo}", f"Crecimiento interanual · {POR_CLAVE[campo].rotulo}", q, f"{POR_CLAVE[campo].rotulo} {q} / {q0} − 1", [(campo, q), (campo, q0)], v / v0 - 1, "pure")
    v, v0 = _valor(idx, "ingresos", "FY2025"), _valor(idx, "ingresos", "FY2021")
    if v and v0:
        d("tacc_ingresos", "TACC ingresos 2021–2025", "FY2025", "(Ingresos FY2025 / Ingresos FY2021)^(1/4) − 1", [("ingresos", "FY2025"), ("ingresos", "FY2021")], (v / v0) ** 0.25 - 1, "pure")
    # TTM
    fy25 = {c: _valor(idx, c, "FY2025") for c in ("ingresos", "ebit", "beneficio_neto", "cfo", "capex")}
    s25 = {c: _valor(idx, c, "6M'25") for c in fy25}
    s26 = {c: _valor(idx, c, "6M'26") for c in fy25}
    for c in fy25:
        if None not in (fy25[c], s25[c], s26[c]):
            d(f"ttm_{c}", f"Últimos doce meses · {POR_CLAVE[c].rotulo}", "TTM jun-26", f"FY2025 − 1S 2025 + 1S 2026", [(c, "FY2025"), (c, "6M'25"), (c, "6M'26")], fy25[c] - s25[c] + s26[c])
    # Balance: deuda neta y ratios
    for per in [p.clave for p in INSTANTES_ANUALES + INSTANTES_TRIM]:
        caja = _valor(idx, "caja", per); inv = _valor(idx, "inversiones_cp", per)
        dcp = _valor(idx, "deuda_cp", per); dlp = _valor(idx, "deuda_lp", per); arr = _valor(idx, "arrendamientos", per)
        pn = _valor(idx, "patrimonio", per); ta = _valor(idx, "total_activo", per)
        ac = _valor(idx, "activo_corriente", per); pc = _valor(idx, "pasivo_corriente", per)
        if None not in (caja, dcp, dlp):
            d("deuda_neta", "Deuda financiera neta (sin arrendamientos)", per, "Deuda c/p + Deuda l/p − Tesorería − Inversiones c/p", [("deuda_cp", per), ("deuda_lp", per), ("caja", per), ("inversiones_cp", per)], dcp + dlp - caja - (inv or 0))
            if arr is not None:
                d("deuda_neta_arr", "Deuda financiera neta (con arrendamientos)", per, "Deuda neta + Pasivos por arrendamiento operativo", [("deuda_cp", per), ("deuda_lp", per), ("caja", per), ("inversiones_cp", per), ("arrendamientos", per)], dcp + dlp + arr - caja - (inv or 0))
        if ac is not None and pc is not None:
            d("fondo_maniobra", "Fondo de maniobra", per, "Activo corriente − Pasivo corriente", [("activo_corriente", per), ("pasivo_corriente", per)], ac - pc)
        if pn and ta:
            d("apalancamiento", "Activo / Patrimonio neto", per, "Total activo / Patrimonio neto", [("total_activo", per), ("patrimonio", per)], ta / pn, "pure")
    # Rentabilidad: sobre medias de apertura y cierre del ejercicio
    for a in (2022, 2023, 2024, 2025):
        bn = _valor(idx, "beneficio_neto", f"FY{a}"); ebit = _valor(idx, "ebit", f"FY{a}")
        bai = _valor(idx, "bai", f"FY{a}"); imp = _valor(idx, "impuestos", f"FY{a}")
        pn1, pn0 = _valor(idx, "patrimonio", f"@{a}-12-31"), _valor(idx, "patrimonio", f"@{a-1}-12-31")
        ta1, ta0 = _valor(idx, "total_activo", f"@{a}-12-31"), _valor(idx, "total_activo", f"@{a-1}-12-31")
        ing = _valor(idx, "ingresos", f"FY{a}")
        if bn is not None and pn1 and pn0:
            d("roe", "ROE", f"FY{a}", "Beneficio neto / Patrimonio neto medio (apertura y cierre)", [("beneficio_neto", f"FY{a}"), ("patrimonio", f"@{a}-12-31"), ("patrimonio", f"@{a-1}-12-31")], bn / ((pn1 + pn0) / 2), "pure")
        if bn is not None and ta1 and ta0:
            d("roa", "ROA", f"FY{a}", "Beneficio neto / Activo total medio", [("beneficio_neto", f"FY{a}"), ("total_activo", f"@{a}-12-31"), ("total_activo", f"@{a-1}-12-31")], bn / ((ta1 + ta0) / 2), "pure")
        if ing and ta1 and ta0:
            d("rotacion_activos", "Rotación de activos", f"FY{a}", "Ingresos / Activo total medio", [("ingresos", f"FY{a}"), ("total_activo", f"@{a}-12-31"), ("total_activo", f"@{a-1}-12-31")], ing / ((ta1 + ta0) / 2), "pure")
        ent = [("deuda_cp", f"@{a}-12-31"), ("deuda_lp", f"@{a}-12-31"), ("caja", f"@{a}-12-31"), ("patrimonio", f"@{a}-12-31"),
               ("deuda_cp", f"@{a-1}-12-31"), ("deuda_lp", f"@{a-1}-12-31"), ("caja", f"@{a-1}-12-31"), ("patrimonio", f"@{a-1}-12-31")]
        vals = [_valor(idx, c, p) for c, p in ent]
        if ebit is not None and bai and imp is not None and None not in vals:
            ci1 = vals[3] + vals[0] + vals[1] - vals[2]
            ci0 = vals[7] + vals[4] + vals[5] - vals[6]
            t = abs(imp) / bai
            d("roic", "ROIC", f"FY{a}", "EBIT × (1 − tipo efectivo) / (Patrimonio + Deuda − Tesorería), medios de apertura y cierre",
              [("ebit", f"FY{a}"), ("impuestos", f"FY{a}"), ("bai", f"FY{a}")] + ent, ebit * (1 - t) / ((ci1 + ci0) / 2), "pure")
    return out


# ---------------------------------------------------------------------------
# Barrido literal: cada hecho XBRL del formulario, buscado en el PDF adjunto
# ---------------------------------------------------------------------------

def _formatos(valor: float, unidad: str) -> list:
    """Cómo puede estar impreso un hecho XBRL en el documento."""
    formas = set()
    v = valor
    neg = v < 0
    v = abs(v)

    def con_comas(x: float, dec: int = 0) -> str:
        return f"{x:,.{dec}f}"
    if unidad in ("USD", "shares"):
        for esc in (1, 1_000, 1_000_000):
            if v % esc == 0 or esc == 1:
                formas.add(con_comas(v / esc))
            else:
                # redondeo a la escala, como haría el redactor («$2.8 billion», «$33 million»)
                formas.add(con_comas(round(v / esc)))
                formas.add(con_comas(v / esc, 1))
        if v >= 1e8:
            formas.add(f"{v / 1e9:.1f} billion"); formas.add(f"{v / 1e9:.0f} billion")
        if v >= 1e6:
            formas.add(f"{v / 1e6:.0f} million"); formas.add(f"{v / 1e6:.1f} million")
    elif unidad == "USD/shares":
        formas.add(f"{v:.2f}"); formas.add(f"{v:.3f}".rstrip("0"))
    elif unidad == "pure":
        formas.add(f"{v * 100:.0f}%"); formas.add(f"{v * 100:.1f}%"); formas.add(f"{v * 100:.2f}%"); formas.add(f"{v:g}")
    else:
        formas.add(f"{v:g}")
    if neg:
        formas |= {f"({f})" for f in list(formas)}
    return sorted(formas, key=len, reverse=True)


def barrido(facts: dict, textos: dict) -> dict:
    resumen = {}
    detalle = []
    for accn, doc in ACCN_ADJUNTOS.items():
        paginas = textos[doc]
        todo = "\n".join(paginas)
        vistos = set()
        n = hallados = 0
        no_hallados = []
        for tax, conceptos in facts.items():
            for concepto, v in conceptos.items():
                for unidad, lst in v["units"].items():
                    for r in lst:
                        if r["accn"] != accn:
                            continue
                        firma = (concepto, unidad, r.get("start"), r["end"], r["val"])
                        if firma in vistos:
                            continue
                        vistos.add(firma)
                        n += 1
                        pagina = None
                        for forma in _formatos(r["val"], unidad):
                            patron = re.compile(r"(?<![\d,.])" + re.escape(forma) + r"(?![\d,])")
                            if patron.search(todo):
                                for i, p in enumerate(paginas, 1):
                                    if patron.search(p):
                                        pagina = i
                                        break
                                break
                        if pagina:
                            hallados += 1
                        else:
                            no_hallados.append(dict(concepto=f"{tax}:{concepto}", unidad=unidad, inicio=r.get("start"), fin=r["end"], valor=r["val"]))
                        detalle.append(dict(doc=doc, concepto=f"{tax}:{concepto}", unidad=unidad, inicio=r.get("start"), fin=r["end"], valor=r["val"], pagina=pagina))
        resumen[doc] = dict(hechos=n, hallados=hallados, no_hallados=len(no_hallados),
                            cobertura=hallados / n if n else None, ejemplos_no_hallados=no_hallados[:40])
    return dict(resumen=resumen, detalle=detalle)


# ---------------------------------------------------------------------------
# Integridad textual: el PDF del analista frente al HTML depositado
# ---------------------------------------------------------------------------

def _tokens(texto: str) -> Counter:
    texto = texto.replace("’", "'").replace("“", '"').replace("”", '"').lower()
    return Counter(re.findall(r"[a-z]{2,}|\d[\d,.]*\d|\d", texto))


def integridad(textos: dict) -> dict:
    salida = {}
    for doc, fichero in FICHERO_SEC.items():
        pdf = _tokens("\n".join(textos[doc]))
        html_ = _tokens((SEC / "texto" / fichero).read_text(encoding="utf-8"))
        comunes = sum((pdf & html_).values())
        num_pdf = Counter({k: v for k, v in pdf.items() if k[0].isdigit()})
        num_html = Counter({k: v for k, v in html_.items() if k[0].isdigit()})
        num_comunes = sum((num_pdf & num_html).values())
        solo_pdf = (pdf - html_)
        salida[doc] = dict(
            tokens_pdf=sum(pdf.values()), tokens_sec=sum(html_.values()),
            fraccion_pdf_en_sec=comunes / sum(pdf.values()),
            numeros_pdf=sum(num_pdf.values()), numeros_pdf_en_sec=num_comunes,
            fraccion_numeros=num_comunes / sum(num_pdf.values()) if num_pdf else None,
            ejemplos_solo_pdf=[k for k, _ in solo_pdf.most_common(25)],
        )
    return salida


# ---------------------------------------------------------------------------

def main() -> None:
    facts = cargar_facts()
    tablas = json.loads((DATOS / "tablas.json").read_text(encoding="utf-8"))
    textos = {d.name: [p.read_text(encoding="utf-8") for p in sorted(d.glob("p*.txt"))] for d in TEXTO.iterdir()}

    filas = matriz(facts, tablas)
    deriv = derivados(filas)
    prev = previsiones(tablas)
    print("Contraste campo × periodo:", len(filas), "filas")
    cuenta = Counter(f["resultado"] for f in filas)
    for k, v in cuenta.items():
        print(f"   {GLIFO[k]} {k:15} {v}")
    print("Discrepancias:")
    for f in filas:
        if f["resultado"] == "discrepante":
            print("   ", f["campo"], f["periodo"]["clave"], f["nota"][:200])
    print("Derivados:", len(deriv), "| Previsiones (Forecast):", len(prev))

    print("\nBarrido literal (hechos XBRL del formulario hallados en su PDF):")
    bar = barrido(facts, textos)
    for doc, r in bar["resumen"].items():
        print(f"   {doc}: {r['hallados']}/{r['hechos']} = {r['cobertura']:.1%}")
    print("\nIntegridad textual (PDF adjunto frente al HTML de la SEC):")
    integ = integridad(textos)
    for doc, r in integ.items():
        print(f"   {doc}: {r['fraccion_pdf_en_sec']:.1%} de los tokens del PDF están en el HTML; "
              f"números {r['numeros_pdf_en_sec']}/{r['numeros_pdf']} = {r['fraccion_numeros']:.1%}")

    (DATOS / "contraste.json").write_text(json.dumps(dict(
        filas=filas, derivados=deriv, previsiones=prev, barrido=bar, integridad=integ,
        resumen=dict(cuenta), glifos=GLIFO), ensure_ascii=False, indent=1, default=str), encoding="utf-8")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
