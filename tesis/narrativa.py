"""Apartados 2 y 3: la narrativa que el sistema redacta a partir de los adjuntos.

La regla es la misma que para las cifras: ninguna frase sin cita de página y
ninguna cifra que no sea un hecho contrastado o que no esté escrita en la página
citada. El redactor —un modelo de lenguaje— propone; `verificar` dispone. Lo que
no supera la verificación no se imprime: se retira, se cuenta y queda anotado en
el Anexo I con su motivo. Nunca se corrige en silencio.

Tres piezas, separadas para que la verificación no dependa del redactor:

- `dossier`: lo que el redactor puede leer. Las páginas de los adjuntos que hablan
  de resultados, guía, estrategia, capital y riesgos, cada una con su clave y su
  número, más los hechos contrastados con la clave con que se declaran. Es
  determinista: el mismo expediente produce el mismo dossier.
- `redactar_con_claude`: envía el dossier al modelo (Claude Opus 5, con salida sujeta al
  esquema JSON de `Narrativa`) y devuelve la narrativa. El estilo se fija con un ejemplo
  de una narrativa ya aprobada por el analista (`EJEMPLO_DE_ESTILO`): frases cortas, tono
  de analista, cifra con su fecha, ninguna opinión. Importa el SDK solo al llamarse; sin
  él o sin clave, `SinRedactor`.
- `redactar_verificada`: redacta, verifica y, si hay reparos, devuelve el dossier con los
  reparos al modelo para que corrija (hasta `rondas`); se queda con la ronda con menos
  frases retiradas. Lo que aun así no supere la verificación se retira e imprime en el
  apéndice, como siempre: el modelo propone, `verificar` dispone.
- `verificar`: cita por cita (el documento existe, la página existe, el ancla es
  literal de esa página) y cifra por cifra (un hecho declarado o un número de la
  página citada, con la tolerancia de la última cifra escrita).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .expediente import Adjunto, Expediente, Tipo
from .hechos import Certeza, Hecho, Periodo

__all__ = ["Apoyo", "Frase", "Pilar", "Narrativa", "Reparo", "Verificacion", "SinRedactor",
           "cargar", "guardar", "dossier", "redactar_con_claude", "redactar_verificada", "verificar", "etiqueta"]

MODELO_POR_DEFECTO = "claude-opus-5"
EJEMPLO_DE_ESTILO = Path(__file__).resolve().parents[1] / "narrativas" / "NFLX_2026-09-17.json"   # narrativa aprobada por el analista el 17/09/2026


class SinRedactor(RuntimeError):
    """No hay modelo con el que redactar: falta el SDK o la clave."""


# ---------------------------------------------------------------------------
# Datos
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Apoyo:
    """Una cita: documento del expediente, página y un fragmento literal de esa página."""
    documento: str            # clave del adjunto («CARTA_20260630») o nombre del fichero
    pagina: int               # 1 = primera página
    ancla: str                # ≥ 3 palabras copiadas de la página, tal cual


@dataclass
class Frase:
    texto: str
    apoyos: List[Apoyo]
    cifras: List[str] = field(default_factory=list)   # «campo:periodo», p. ej. «ingresos:2T26»


@dataclass
class Pilar:
    titulo: str
    frases: List[Frase]
    riesgo: Optional[Frase] = None    # el riesgo del Item 1A del 10-K que amenaza el pilar


@dataclass
class Narrativa:
    resumen: List[List[Frase]]        # párrafos del apartado 2
    pilares: List[Pilar]              # apartado 3
    redactor: str                     # quién redactó: modelo y versión, o «analista»
    fecha: date
    bloques: Dict[str, List[List[Frase]]] = field(default_factory=dict)   # otros apartados de texto, por número: «21», «22», «23», «31»


# apartados de texto que el redactor puede rellenar además del 2 y el 3, con lo que el índice pide de cada uno
BLOQUES = {
    "21": "Tamaño de mercado — TAM / SAM / SOM",
    "22": "Análisis competitivo — competidores, cuotas de mercado y comparables",
    "23": "Ventajas competitivas & moat — barreras de entrada y sostenibilidad",
    "31": "Bear case — qué tendría que salir mal para invalidar la tesis",
}


@dataclass(frozen=True)
class Reparo:
    donde: str                        # «resumen §2 frase 3», «pilar 4 riesgo»
    motivo: str
    gravedad: str                     # «grave» retira la frase; «aviso» no
    texto: str = ""


@dataclass
class Verificacion:
    reparos: List[Reparo]
    retiradas: List[str]              # localizadores de las frases retiradas
    documentos: List[str]             # etiquetas de los adjuntos citados, por orden de aparición

    @property
    def graves(self) -> List[Reparo]:
        return [r for r in self.reparos if r.gravedad == "grave"]

    @property
    def certeza(self) -> Certeza:
        # Ninguna frase retirada: lo impreso está íntegramente citado y verificado.
        # Con retiradas, lo impreso sigue verificado pero el texto quedó incompleto.
        if not self.reparos:
            return Certeza.ALTA
        return Certeza.MEDIA if not self.retiradas else Certeza.BAJA


# ---------------------------------------------------------------------------
# Fichero JSON (lo que el analista revisa y lo que el modelo devuelve)
# ---------------------------------------------------------------------------

def _frase_de(d: dict) -> Frase:
    return Frase(texto=str(d["texto"]).strip(),
                 apoyos=[Apoyo(str(a["documento"]), int(a["pagina"]), str(a["ancla"])) for a in d.get("apoyos", [])],
                 cifras=[str(c) for c in d.get("cifras", [])])


def de_dict(d: dict) -> Narrativa:
    return Narrativa(
        resumen=[[_frase_de(f) for f in parrafo] for parrafo in d.get("resumen", [])],
        pilares=[Pilar(titulo=str(p["titulo"]), frases=[_frase_de(f) for f in p.get("frases", [])],
                       riesgo=_frase_de(p["riesgo"]) if p.get("riesgo") else None) for p in d.get("pilares", [])],
        redactor=str(d.get("redactor", "")),
        fecha=date.fromisoformat(d["fecha"]) if d.get("fecha") else date.today(),
        bloques={str(k): [[_frase_de(f) for f in parrafo] for parrafo in v] for k, v in d.get("bloques", {}).items()},
    )


def a_dict(n: Narrativa) -> dict:
    def f(fr: Frase) -> dict:
        return {"texto": fr.texto, "apoyos": [{"documento": a.documento, "pagina": a.pagina, "ancla": a.ancla} for a in fr.apoyos],
                "cifras": list(fr.cifras)}
    return {"redactor": n.redactor, "fecha": n.fecha.isoformat(),
            "resumen": [[f(fr) for fr in parrafo] for parrafo in n.resumen],
            "pilares": [{"titulo": p.titulo, "frases": [f(fr) for fr in p.frases], "riesgo": f(p.riesgo) if p.riesgo else None}
                        for p in n.pilares],
            "bloques": {k: [[f(fr) for fr in parrafo] for parrafo in v] for k, v in n.bloques.items()}}


def cargar(ruta: Path) -> Narrativa:
    return de_dict(json.loads(Path(ruta).read_text(encoding="utf-8")))


def guardar(n: Narrativa, ruta: Path) -> None:
    Path(ruta).write_text(json.dumps(a_dict(n), ensure_ascii=False, indent=1), encoding="utf-8")


# ---------------------------------------------------------------------------
# Etiquetas y localización de documentos
# ---------------------------------------------------------------------------

def _trimestre(fin: Optional[date]) -> str:
    return f"{(fin.month - 1) // 3 + 1}T{fin.year % 100:02d}" if fin else ""


def etiqueta(a: Adjunto) -> str:
    """Cómo se nombra el documento en una cita impresa: corto y reconocible por un analista."""
    if a.tipo is Tipo.K10:
        return f"10-K {a.periodo_fin.year}" if a.periodo_fin else "10-K"
    if a.tipo is Tipo.Q10:
        return f"10-Q {_trimestre(a.periodo_fin)}".strip()
    if a.tipo is Tipo.DEF14A:
        return f"Proxy {a.fecha.year}" if a.fecha else "Proxy"
    if a.tipo is Tipo.CARTA:
        return f"Carta {_trimestre(a.periodo_fin)}".strip()
    if a.tipo is Tipo.NOTA:
        return f"Nota de resultados {_trimestre(a.periodo_fin)}".strip()
    if a.tipo is Tipo.TABLAS:
        return f"Tablas 8-K {_trimestre(a.periodo_fin)}".strip()
    if a.tipo is Tipo.PRESENTACION:
        return f"Presentación {_trimestre(a.periodo_fin)}".strip()
    if a.tipo is Tipo.CALL:
        return f"Call {_trimestre(a.periodo_fin)}".strip()
    if a.tipo is Tipo.FINWEB:
        return f"Cuentas web {_trimestre(a.periodo_fin)}".strip()
    if a.tipo is Tipo.XLSX:
        return f"Hoja {_trimestre(a.periodo_fin)}".strip()
    return a.nombre


def _adjunto(exp: Expediente, documento: str) -> Optional[Adjunto]:
    for a in exp.adjuntos:
        if documento in (a.clave, a.nombre):
            return a
    return None


# ---------------------------------------------------------------------------
# Texto y números
# ---------------------------------------------------------------------------

_COMILLAS = {"’": "'", "‘": "'", "“": '"', "”": '"', "­": "", "￾": ""}


def _normalizar(t: str) -> str:
    for k, v in _COMILLAS.items():
        t = t.replace(k, v)
    return re.sub(r"\s+", " ", t).strip().lower()


# Cifra en convención española dentro de una frase: «12.560», «33,4», «2,8», «13».
# Quedan fuera fechas (30/06/2026), rangos con guion (10-K), etiquetas (2T26, H1'26) y proporciones (10:1).
_NUM_ES = re.compile(r"(?<![\w:'’/\-])(\d{1,3}(?:\.\d{3})+|\d+)(?:,(\d+))?(?![\d\w:'’/\-])")
# Número en una página en inglés: «12,560», «33.4», «2.8», «45,183,036», «$12.6B».
_NUM_EN = re.compile(r"(?<![\w'’])(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d+))?")


def cifras_de(texto: str) -> List[Tuple[float, int]]:
    """Las cifras escritas en una frase, con sus decimales. Los años (1990–2040) no son cifras."""
    salida = []
    for m in _NUM_ES.finditer(texto):
        entero, dec = m.group(1), m.group(2)
        if dec is None and "." not in entero and 1990 <= int(entero) <= 2040:
            continue
        valor = float(entero.replace(".", "") + ("." + dec if dec else ""))
        salida.append((valor, len(dec) if dec else 0))
    return salida


def _numeros_de_pagina(texto: str) -> List[float]:
    return [float(m.group(1).replace(",", "") + ("." + m.group(2) if m.group(2) else "")) for m in _NUM_EN.finditer(texto)]


_ESCALAS = (1.0, 1e-3, 1e-6, 1e-9, 1e3, 1e6, 1e9, 100.0)


def _casa(cifra: float, decimales: int, candidato: float) -> bool:
    """La cifra escrita coincide con el candidato en alguna escala, con la tolerancia de su última cifra."""
    tol = 0.5 * 10 ** (-decimales) + 1e-9
    return any(abs(cifra - candidato * k) <= tol for k in _ESCALAS)


# ---------------------------------------------------------------------------
# Verificación
# ---------------------------------------------------------------------------

def _indice_hechos(hechos: Dict[Tuple[str, Periodo], Hecho]) -> Dict[str, Hecho]:
    return {f"{campo}:{p.clave}": h for (campo, p), h in hechos.items()}


def _verificar_frase(fr: Frase, donde: str, exp: Expediente, indice: Dict[str, Hecho], vistos: List[str]) -> List[Reparo]:
    reparos: List[Reparo] = []
    if not fr.texto.strip():
        return [Reparo(donde, "frase vacía", "grave")]
    if not fr.apoyos:
        reparos.append(Reparo(donde, "sin cita de página", "grave", fr.texto))
    paginas_citadas: List[str] = []
    for a in fr.apoyos:
        adj = _adjunto(exp, a.documento)
        if adj is None:
            reparos.append(Reparo(donde, f"cita un documento que no está en el expediente: {a.documento}", "grave", fr.texto))
            continue
        if not 1 <= a.pagina <= len(adj.paginas):
            reparos.append(Reparo(donde, f"{etiqueta(adj)} no tiene página {a.pagina} (tiene {len(adj.paginas)})", "grave", fr.texto))
            continue
        pagina = adj.paginas[a.pagina - 1]
        if len(a.ancla.split()) < 3:
            reparos.append(Reparo(donde, f"ancla demasiado corta para {etiqueta(adj)} pág. {a.pagina}: «{a.ancla}»", "grave", fr.texto))
        elif _normalizar(a.ancla) not in _normalizar(pagina):
            reparos.append(Reparo(donde, f"el ancla no está en {etiqueta(adj)} pág. {a.pagina}: «{a.ancla}»", "grave", fr.texto))
        else:
            paginas_citadas.append(pagina)
            e = etiqueta(adj)
            if e not in vistos:
                vistos.append(e)
    # cifras: cada una debe ser un hecho declarado o estar escrita en una página citada y verificada
    hechos_declarados: List[Hecho] = []
    for clave in fr.cifras:
        h = indice.get(clave)
        if h is None:
            reparos.append(Reparo(donde, f"declara el hecho {clave}, que el informe no tiene", "grave", fr.texto))
        elif not h.hay_dato:
            reparos.append(Reparo(donde, f"declara el hecho {clave}, que es {h.estado.value} ({h.motivo})", "grave", fr.texto))
        else:
            hechos_declarados.append(h)
    numeros_pagina = [n for p in paginas_citadas for n in _numeros_de_pagina(p)]
    usados = set()
    for cifra, dec in cifras_de(fr.texto):
        por_hecho = next((h for h in hechos_declarados if _casa(cifra, dec, h.valor)), None)
        if por_hecho is not None:
            usados.add(id(por_hecho))
            continue
        if any(_casa(cifra, dec, n) for n in numeros_pagina):
            continue
        reparos.append(Reparo(donde, f"la cifra {cifra:g} no es un hecho declarado ni está en las páginas citadas", "grave", fr.texto))
    for h in hechos_declarados:
        if id(h) not in usados:
            reparos.append(Reparo(donde, f"declara {h.campo}:{h.periodo.clave} pero ninguna cifra de la frase lo usa", "aviso", fr.texto))
    return reparos


def verificar(n: Narrativa, exp: Expediente, hechos: Dict[Tuple[str, Periodo], Hecho]) -> Verificacion:
    """Cita por cita y cifra por cifra. Una frase con un reparo grave se retira; el resto se imprime."""
    indice = _indice_hechos(hechos)
    reparos: List[Reparo] = []
    retiradas: List[str] = []
    vistos: List[str] = []

    def frase(fr: Frase, donde: str) -> None:
        rs = _verificar_frase(fr, donde, exp, indice, vistos)
        reparos.extend(rs)
        if any(r.gravedad == "grave" for r in rs):
            retiradas.append(donde)

    if not n.resumen:
        reparos.append(Reparo("resumen", "sin párrafos", "grave"))
    for i, parrafo in enumerate(n.resumen, 1):
        for j, fr in enumerate(parrafo, 1):
            frase(fr, f"resumen §{i} frase {j}")
    if len(n.pilares) != 5:
        reparos.append(Reparo("pilares", f"el índice pide 5 pilares y hay {len(n.pilares)}", "aviso"))
    for i, p in enumerate(n.pilares, 1):
        if not p.titulo.strip():
            reparos.append(Reparo(f"pilar {i}", "sin título", "grave"))
        for j, fr in enumerate(p.frases, 1):
            frase(fr, f"pilar {i} frase {j}")
        if p.riesgo is None:
            reparos.append(Reparo(f"pilar {i}", "sin riesgo del Item 1A del 10-K", "aviso"))
        else:
            frase(p.riesgo, f"pilar {i} riesgo")
            adjs = [_adjunto(exp, a.documento) for a in p.riesgo.apoyos]
            if not any(a is not None and a.tipo is Tipo.K10 for a in adjs):
                reparos.append(Reparo(f"pilar {i} riesgo", "el riesgo no cita el 10-K", "aviso", p.riesgo.texto))
    for clave, parrafos in n.bloques.items():
        if clave not in BLOQUES:
            reparos.append(Reparo(f"bloque {clave}", "el índice no tiene un apartado de texto con ese número", "aviso"))
        for i, parrafo in enumerate(parrafos, 1):
            for j, fr in enumerate(parrafo, 1):
                frase(fr, f"apartado {clave} §{i} frase {j}")
    return Verificacion(reparos=reparos, retiradas=retiradas, documentos=vistos)


# ---------------------------------------------------------------------------
# Evidencia visual: un recorte por página citada, con las anclas de las frases que la citan
# ---------------------------------------------------------------------------

def evidencias(frases: Sequence[Frase], exp: Expediente, salida: Path, seccion: str) -> list:
    """Recortes de las páginas que citan estas frases, en el orden en que aparecen; uno por (documento, página)."""
    from .recortes import recortar_lineas
    por_pagina: Dict[Tuple[str, int], List[str]] = {}
    orden: List[Tuple[str, int]] = []
    for fr in frases:
        for a in fr.apoyos:
            adj = _adjunto(exp, a.documento)
            if adj is None or adj.tipo is Tipo.XLSX:
                continue
            clave = (adj.clave, a.pagina)
            if clave not in por_pagina:
                orden.append(clave)
            por_pagina.setdefault(clave, []).append(a.ancla)
    salida_recortes = []
    for clave in orden:
        adj = next(a for a in exp.adjuntos if a.clave == clave[0])
        rec = recortar_lineas(adj, clave[1], por_pagina[clave], salida, [f"apartado {seccion}"], sufijo=f"s{seccion}")
        if rec is not None:
            salida_recortes.append(rec)
    return salida_recortes


# ---------------------------------------------------------------------------
# Dossier y redactor
# ---------------------------------------------------------------------------

_PAGINAS_10K = re.compile(r"Item 1\. Business|Item 1A\. Risk Factors|Risks Related to|Results of Operations|Liquidity and Capital Resources|"
                          r"Share Repurchases|Material Cash Requirements|never declared or paid", re.I)
_PAGINAS_10Q = re.compile(r"^Overview|Results of Operations|Liquidity and Capital Resources|Acquisitions|Share Repurchases|Cash Flows", re.I | re.M)
_PAGINAS_PROXY = re.compile(r"Year in Review|Business Highlights", re.I)
_BOILERPLATE = re.compile(r"Forward-Looking Statements|Use of Non-GAAP Measures|All rights reserved\.\s*These materials", re.I)


def _paginas_relevantes(a: Adjunto) -> List[int]:
    n = len(a.paginas)
    if a.tipo in (Tipo.CARTA, Tipo.NOTA, Tipo.TABLAS, Tipo.PRESENTACION):
        return [i for i in range(1, n + 1) if not _BOILERPLATE.search(a.paginas[i - 1][:400]) or i == 1]
    if a.tipo is Tipo.CALL:
        return [i for i in range(1, n + 1) if i >= 4 and not _BOILERPLATE.search(a.paginas[i - 1][:300])]
    if a.tipo is Tipo.K10:
        return [i for i in range(1, n + 1) if _PAGINAS_10K.search(a.paginas[i - 1])]
    if a.tipo is Tipo.Q10:
        return [i for i in range(1, n + 1) if _PAGINAS_10Q.search(a.paginas[i - 1])]
    if a.tipo is Tipo.DEF14A:
        return [i for i in range(1, n + 1) if _PAGINAS_PROXY.search(a.paginas[i - 1])]
    return []


def dossier(exp: Expediente, hechos: Dict[Tuple[str, Periodo], Hecho]) -> str:
    """Lo que lee el redactor: páginas relevantes con su clave y número, y los hechos con su clave."""
    partes: List[str] = []
    ultimo_10q = max(exp.de_tipo(Tipo.Q10), key=lambda a: a.orden, default=None)
    for a in sorted(exp.adjuntos, key=lambda a: a.orden):
        if a.tipo is Tipo.Q10 and a is not ultimo_10q:
            continue
        for p in _paginas_relevantes(a):
            partes.append(f"=== documento {a.clave} ({etiqueta(a)}, {a.nombre}) página {p} ===\n{a.paginas[p - 1].strip()}\n")
    lineas = ["=== hechos contrastados (clave · valor · unidad · contraste) ==="]
    for (campo, p), h in sorted(hechos.items(), key=lambda kv: (kv[0][0], kv[0][1])):
        if h.hay_dato:
            lineas.append(f"{campo}:{p.clave} · {h.valor:,.4f} · {h.unidad} · {h.contraste.value or ('∑' if h.formula else '')}")
    partes.append("\n".join(lineas))
    return "\n".join(partes)


INSTRUCCIONES = """Eres el sistema de redacción de una tesis de inversión de una casa de análisis. Redactas en castellano, para un analista, con el tono de un analista que le explica a otro: frases cortas, una idea por frase, la cifra con su fecha o su periodo, ningún adjetivo que no aporte, ninguna opinión, ninguna recomendación ni precio objetivo. Interpretas: no repites la caja de cifras, dices qué significan y qué dijo la dirección al respecto.
Apartados:
2. «Resumen ejecutivo & contexto de la tesis»: de 3 a 5 párrafos (qué es la empresa y su estrategia declarada; resultados del último trimestre y del último ejercicio; guía y objetivos comunicados; caja, deuda y retribución al accionista).
3. «Investment case — los 5 pilares de la tesis»: exactamente 5 pilares; cada uno con título corto, de 2 a 4 frases y un «riesgo», que es la frase del Item 1A del 10-K que amenaza ese pilar, citada del 10-K.
Y, como «bloques» numerados, los apartados de texto de las secciones E y G: «21» tamaño de mercado (solo lo que los adjuntos cuantifican, con sus palabras), «22» análisis competitivo (competidores y cuotas según los adjuntos; lo que no está se dice que no está), «23» ventajas competitivas y su sostenibilidad, «31» bear case (qué tendría que salir mal, según los propios documentos).
Reglas, sin excepción:
- Solo puedes usar el dossier adjunto. Nada de conocimiento externo, estimaciones ni opiniones.
- Cada frase lleva al menos un apoyo: {"documento": clave del documento tal como aparece en «=== documento … ===», "pagina": número, "ancla": entre 4 y 12 palabras copiadas literalmente de esa página, sin cambiar una letra}.
- Toda cifra escrita en una frase debe ser un hecho contrastado (declara su clave en "cifras", p. ej. "ingresos:2T26") o estar escrita en la página citada. Cifras en convención española: 12.560 M USD; 33,4 %; 2,8.
- Si una frase no puede citarse literalmente, no la escribas.
Devuelve solo el JSON del esquema; nada más."""

ESQUEMA_NARRATIVA = {
    "type": "object",
    "properties": {
        "resumen": {"type": "array", "items": {"type": "array", "items": {"$ref": "#/$defs/frase"}}},
        "pilares": {"type": "array", "items": {
            "type": "object",
            "properties": {"titulo": {"type": "string"}, "frases": {"type": "array", "items": {"$ref": "#/$defs/frase"}}, "riesgo": {"$ref": "#/$defs/frase"}},
            "required": ["titulo", "frases", "riesgo"], "additionalProperties": False}},
        "bloques": {"type": "object",
                    "properties": {k: {"type": "array", "items": {"type": "array", "items": {"$ref": "#/$defs/frase"}}} for k in ("21", "22", "23", "31")},
                    "required": ["21", "22", "23", "31"], "additionalProperties": False},
    },
    "required": ["resumen", "pilares", "bloques"],
    "additionalProperties": False,
    "$defs": {
        "frase": {"type": "object",
                  "properties": {"texto": {"type": "string"},
                                 "apoyos": {"type": "array", "items": {"type": "object", "properties": {"documento": {"type": "string"}, "pagina": {"type": "integer"}, "ancla": {"type": "string"}},
                                                                       "required": ["documento", "pagina", "ancla"], "additionalProperties": False}},
                                 "cifras": {"type": "array", "items": {"type": "string"}}},
                  "required": ["texto", "apoyos", "cifras"], "additionalProperties": False},
    },
}


def ejemplo_de_estilo(ruta: Path = EJEMPLO_DE_ESTILO) -> str:
    """Un extracto de una narrativa aprobada, como muestra de tono y forma (no de datos): el primer párrafo del
    resumen y el primer pilar, con sus apoyos. Sin fichero, cadena vacía."""
    if not Path(ruta).exists():
        return ""
    d = json.loads(Path(ruta).read_text(encoding="utf-8"))
    muestra = {"resumen": d.get("resumen", [])[:1], "pilares": d.get("pilares", [])[:1]}
    return ("\n\nEjemplo de estilo y forma (es de un informe anterior, quizá de la misma empresa en otro periodo: copia el tono, la longitud de las frases y la manera de citar; no copies ni un dato ni una cita, que todo salga del dossier adjunto):\n"
            + json.dumps(muestra, ensure_ascii=False, indent=1))


def _cliente(modelo_sdk):
    import os

    from .entorno import variable
    clave = variable("ANTHROPIC_API_KEY")
    # el SDK no comprueba la autenticación al construir el cliente, sino al firmar la petición (TypeError): se mira aquí
    if False and not (os.environ.get("ANTHROPIC_AUTH_TOKEN") or os.environ.get("ANTHROPIC_BEDROCK_BASE_URL") or os.environ.get("ANTHROPIC_VERTEX_PROJECT_ID")):
        raise SinRedactor("Falta ANTHROPIC_API_KEY (entorno o .env): sin clave no se puede redactar la narrativa. "
                          "Emite sin --redactar (los apartados 2 y 3 salen N/A con motivo) o pasa una narrativa ya redactada con --narrativa.")
    try:
        return modelo_sdk.Anthropic(api_key=clave) if clave else modelo_sdk.Anthropic()
    except Exception as e:  # sin clave ni perfil
        raise SinRedactor(f"No se pudo crear el cliente de Claude (falta ANTHROPIC_API_KEY en el entorno o en .env): {e}") from e


def redactar_con_claude(texto_dossier: str, modelo: str = MODELO_POR_DEFECTO, reparos: Sequence[str] = (), redactor_anterior=None) -> Narrativa:
    """Pide la narrativa al modelo, con salida sujeta al esquema y en streaming (la respuesta es larga).

    `reparos`: los de la ronda anterior, para que el modelo corrija exactamente eso. Exige el SDK
    (`anthropic`) y `ANTHROPIC_API_KEY` (entorno o `.env`); sin ellos, `SinRedactor`.
    """
    try:
        import anthropic  # importación perezosa: la dependencia solo se exige aquí
    except ImportError as e:
        raise SinRedactor("Falta el SDK de Claude (paquete «anthropic»); la narrativa puede venir de un fichero JSON (--narrativa).") from e
    cliente = _cliente(anthropic)
    contenido_usuario = texto_dossier
    if reparos:
        contenido_usuario += ("\n\n=== reparos de la verificación de tu redacción anterior: corrígelos todos ===\n"
                              "Cada reparo dice qué frase falló y por qué (ancla no literal, página equivocada, cifra sin hecho). Vuelve a redactar la narrativa completa; "
                              "en esas frases, o cambias el apoyo por uno literal o retiras la frase.\n" + "\n".join(f"- {r}" for r in reparos))
    try:
        with cliente.messages.stream(model=modelo, max_tokens=64000, system=INSTRUCCIONES + ejemplo_de_estilo(),
                                     messages=[{"role": "user", "content": contenido_usuario}],
                                     output_config={"effort": "high", "format": {"type": "json_schema", "schema": ESQUEMA_NARRATIVA}}) as flujo:
            respuesta = flujo.get_final_message()
    except anthropic.AuthenticationError as e:
        raise SinRedactor(f"La clave de Claude no es válida: {e}") from e
    except anthropic.APIStatusError as e:
        raise SinRedactor(f"Claude devolvió un error {e.status_code}: {e.message}") from e
    except anthropic.APIConnectionError as e:
        raise SinRedactor(f"Sin conexión con Claude: {e}") from e
    except TypeError as e:       # el SDK levanta TypeError cuando no resuelve la autenticación al construir las cabeceras
        raise SinRedactor(f"El SDK de Claude no encuentra con qué autenticarse (ANTHROPIC_API_KEY): {e}") from e
    if respuesta.stop_reason == "refusal":
        raise SinRedactor("El modelo declinó la petición (stop_reason refusal).")
    if respuesta.stop_reason == "max_tokens":
        raise SinRedactor("La respuesta del modelo se cortó por longitud (max_tokens).")
    contenido = "".join(getattr(b, "text", "") for b in respuesta.content if getattr(b, "type", "") == "text")
    inicio, fin = contenido.find("{"), contenido.rfind("}")
    if inicio < 0 or fin < 0:
        raise SinRedactor("El modelo no devolvió JSON.")
    d = json.loads(contenido[inicio:fin + 1])
    d.setdefault("redactor", f"{modelo}")
    d.setdefault("fecha", date.today().isoformat())
    return de_dict(d)


def redactar_verificada(exp: Expediente, hechos: Dict[Tuple[str, Periodo], Hecho], modelo: str = MODELO_POR_DEFECTO, rondas: int = 2,
                        redactar=None) -> Tuple[Narrativa, int]:
    """Redacta y verifica; con reparos, devuelve el dossier con ellos al modelo y repite (hasta `rondas`).

    Devuelve (la narrativa con menos frases retiradas —a igualdad, la más reciente—, rondas usadas).
    `redactar` permite sustituir al modelo en las pruebas.
    """
    redactar = redactar or redactar_con_claude
    texto = dossier(exp, hechos)
    mejor: Optional[Tuple[Narrativa, Verificacion]] = None
    reparos: List[str] = []
    usadas = 0
    for _ in range(max(1, rondas)):
        usadas += 1
        n = redactar(texto, modelo, reparos)
        v = verificar(n, exp, hechos)
        if mejor is None or len(v.retiradas) <= len(mejor[1].retiradas):
            mejor = (n, v)
        if not v.reparos:
            break
        reparos = [f"{r.donde}: {r.motivo}" + (f" — «{r.texto[:120]}»" if r.texto else "") for r in v.reparos]
    return mejor[0], usadas


