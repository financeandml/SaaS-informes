"""El SaaS local en cuatro pasos: expediente → DCF → analista → informe.

    python -m tesis servir [--puerto 8770] [--sin-navegador]      (o python -m tesis.web.saas)

Sirve en 127.0.0.1 cuatro páginas estáticas (`tesis/web/tablero/`, CSP estricta, sin scripts en línea) y una API:

  1. `/`            el analista busca el ticker (lista desplegable sobre `company_tickers.json` de la SEC); al elegirlo se
                    cargan en segundo plano el emisor, sus depósitos y los hechos XBRL. Después adjunta los ficheros
                    (PDF, XLSX, Word) a `adjuntos/<TICKER>/`; cada uno se clasifica con `expediente.cargar`, se ordena
                    cronológicamente, se contrasta con la SEC (`contraste.contrastar`) y se dice en qué apartados se usa.
  2. `/dcf`         el libro Excel del analista, a `dcf/<TICKER>.xlsx`, leído con `dcf.cargar` (copia recalculada si hace falta).
  3. `/asistente`   las entradas del analista en 9 pasos (`entradas/asistente.py`), a `<datos>/entradas/<TICKER>/<fecha>/entradas.json`.
  4. `/informe`     lanza `emitir.py` como proceso aparte (registro en `salida/<TICKER>/emision.log`) y muestra el HTML y el PDF.

El servidor solo escribe en `adjuntos/`, `dcf/`, `entradas/` y `salida/` (`posiciones/` solo se lee, para migrarla). Escucha
solo en 127.0.0.1 y rechaza las escrituras que no vengan de sus propias páginas (cabecera propia + origen local).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import threading
import webbrowser
from datetime import date, datetime
from email.parser import BytesParser
from email.policy import default as POLITICA_HTTP
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Tuple
from urllib.parse import parse_qs, unquote, urlparse

from ..datos import documentos as catalogo, expediente
from .. import entorno
from ..fuentes import edgar, sec
from ..rutas import REPO

TABLERO = Path(__file__).resolve().parent / "tablero"
_TICKER = re.compile(r"^[A-Z0-9.\-]{1,10}$")
CSP = ("default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self'; form-action 'none'; "
       "base-uri 'none'; frame-ancestors 'none'")
_TIPOS = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8", ".js": "text/javascript; charset=utf-8"}

__all__ = ["Servidor", "servir", "main"]

RAIZ = REPO
ADJUNTOS, SALIDA = entorno.carpeta("adjuntos"), entorno.carpeta("salida")   # pesan cientos de megas: fuera del repositorio
DCF = RAIZ / "dcf"
ADMITIDOS = {".pdf", ".xlsx", ".xlsm", ".docx"}
LIBROS = {".xlsx", ".xlsm"}
MAXIMO_CUERPO = 400_000_000
CSP_SAAS = CSP + "; frame-src 'self'"          # el paso 4 enmarca el informe emitido, servido por este mismo servidor
PAGINAS = {"/": "inicio.html", "/dcf": "dcf.html", "/informe": "informe.html", "/asistente": "asistente.html"}
_NOMBRE = re.compile(r"[^A-Za-z0-9._\- ]+")

DECLARADO = "declarado.json"       # en la carpeta del ticker: fichero → casilla en la que lo adjuntó el analista

_ESTADO: Dict[str, dict] = {}
_CERROJO = threading.Lock()
# pypdfium2 no es seguro entre hilos: dos tickers clasificándose a la vez corrompen la lectura («Data format error»).
# El SaaS es local y de un solo analista, así que la lectura de documentos se hace de uno en uno.
_CERROJO_PDF = threading.Lock()


def _nuevo() -> dict:
    return {"carga": {"estado": "sin empezar", "mensaje": ""}, "adjuntos": None, "contraste": None, "dcf": None,
            "emision": None, "traida": None}


def _emitiendo(e: dict) -> bool:
    em = e.get("emision")
    return em is not None and em["proceso"].poll() is None


def estado(ticker: str) -> dict:
    """El estado en memoria del ticker, y solo del ticker: una empresa cada vez.

    Al abrir otra empresa se suelta lo de la anterior —su expediente son los textos de todos sus PDF en memoria— y el
    análisis nuevo empieza de cero. Nada se pierde: todo lo que importa está en disco (`adjuntos/`, `dcf/`,
    `posiciones/`, `salida/`) y se reconstruye al volver. Lo único que no se suelta es una emisión en marcha, que
    tiene un proceso vivo detrás y su registro que enseñar.
    """
    with _CERROJO:
        if ticker not in _ESTADO:
            for otro in [t for t, e in _ESTADO.items() if not _emitiendo(e)]:
                del _ESTADO[otro]
        return _ESTADO.setdefault(ticker, _nuevo())


def _json_listo(v):
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    if isinstance(v, Path):
        return str(v)
    if hasattr(v, "value"):
        return v.value
    return str(v)


# ---------------------------------------------------------------- carga del emisor, clasificación y contraste

def arrancar_carga(ticker: str) -> dict:
    """Marca el ticker como «cargando» y lanza el hilo, si no lo está ya. Devuelve el estado de carga resultante.

    El cerrojo es el que evita el tropel: la página pregunta por el estado cada dos segundos y, sin él, cada respuesta
    «sin empezar» arrancaría otro hilo pidiendo lo mismo a la SEC.
    """
    e = estado(ticker)
    with _CERROJO:
        if e["carga"]["estado"] == "cargando":
            return e["carga"]
        e["carga"] = {"estado": "cargando", "mensaje": "emisor, depósitos y hechos XBRL de la SEC"}
    threading.Thread(target=preparar, args=(ticker,), daemon=True).start()
    return e["carga"]


def preparar(ticker: str) -> None:
    """Hilo: emisor y hechos XBRL de la SEC; después, lo que ya hubiera en disco (adjuntos, libro) se clasifica y se resume."""
    e = estado(ticker)
    from ..fuentes import emisores
    bme = emisores.es_bme(ticker)
    e["carga"] = {"estado": "cargando", "mensaje": "emisor y documentos de BME" if bme else "emisor, depósitos y hechos XBRL de la SEC"}
    try:
        emisor = emisores.emisor(ticker)
        if emisor is None:
            e["carga"] = {"estado": "error", "mensaje": f"{ticker} no está ni en la SEC ni en BME"}
            return
        if emisor.mercado == "bme":
            # sin XBRL: las cifras salen de las cuentas en PDF y se contrastan documento contra documento
            e["emisor"], e["facts"] = emisor, (None, None)
            e["carga"] = {"estado": "listo", "mensaje": f"{emisor.nombre} · ISIN {emisor.isin} · {emisor.bolsa} · cifras en {emisor.moneda}, "
                                                        "de las cuentas anuales y semestrales que publica el emisor en BME",
                          "nombre": emisor.nombre, "cik": "", "isin": emisor.isin, "bolsa": emisor.bolsa, "mercado": "bme"}
        else:
            facts, obtenido = sec.companyfacts(emisor.cik)
            e["emisor"], e["facts"] = emisor, (facts, obtenido)
            conceptos = len((facts.get("facts") or {}).get("us-gaap") or {})
            e["carga"] = {"estado": "listo", "mensaje": f"{emisor.nombre} · CIK {int(emisor.cik)} · {emisor.bolsa} · {len(emisor.depositos)} depósitos recientes · "
                                                        f"{conceptos} conceptos XBRL (companyfacts del {obtenido:%d/%m/%Y})",
                          "nombre": emisor.nombre, "cik": emisor.cik, "bolsa": emisor.bolsa, "mercado": "sec"}
        e["adjuntos"] = clasificar(ticker)
        if e["adjuntos"]["adjuntos"]:
            contrastar(ticker)
        if (DCF / f"{ticker}.xlsx").exists():
            e["dcf"] = resumen_dcf(ticker)
    except Exception as ex:  # el fallo se enseña en pantalla, no se cae el servidor
        e["carga"] = {"estado": "error", "mensaje": f"{ex.__class__.__name__}: {ex}"}


def _rutas(ticker: str) -> List[Path]:
    carpeta = ADJUNTOS / ticker
    return sorted(p for p in carpeta.iterdir() if p.suffix.lower() in ADMITIDOS) if carpeta.exists() else []


def _rotulo(a) -> str:
    """Cómo se ve el adjunto en la lista: lo que es y de cuándo («10-K 31/05/2026»), no el nombre del fichero; EDGAR sirve
    muchos PDF con un UUID por nombre y «0723dfa7-….pdf» no dice qué documento es (fallo [68])."""
    cuando = a.periodo_fin or a.fecha
    return f"{a.tipo.value} {cuando:%d/%m/%Y}" if cuando else a.tipo.value


def clasificar(ticker: str) -> dict:
    """Los adjuntos del ticker clasificados por `expediente.cargar`, en orden cronológico, con su destino en el informe."""
    rutas = _rutas(ticker)
    e = estado(ticker)
    if not rutas:
        return {"adjuntos": [], "avisos": []}
    emisor = e.get("emisor")
    with _CERROJO_PDF:
        exp = expediente.cargar(ticker, rutas, emisor.depositos if emisor is not None else None)
    e["expediente"] = exp
    declarado = expediente.declaraciones(ADJUNTOS / ticker)
    filas = []
    for a in exp.adjuntos:
        orden = a.fecha or a.periodo_fin
        filas.append({"fichero": a.ruta.name, "rotulo": _rotulo(a), "clave": a.clave, "tipo": a.tipo.value, "periodo_fin": a.periodo_fin, "fecha": a.fecha,
                      "orden": orden.isoformat() if orden else "", "certeza": a.certeza.value, "motivo": a.motivo, "edgar": a.verificado_en_edgar,
                      "accession": a.accession, "paginas": len(a.paginas), "destino": catalogo.destino(a.tipo),
                      "tambien": [t.value for t in a.tambien],
                      "declarado": declarado.get(a.ruta.name, "")})
    filas.sort(key=lambda f: (f["orden"] == "", f["orden"], f["fichero"]))
    return {"adjuntos": filas, "avisos": [{"gravedad": av.gravedad, "texto": av.texto} for av in exp.avisos]}


def declarar(ticker: str, fichero: str, clave: str) -> None:
    """Deja escrito en qué casilla adjuntó el analista este fichero (o la borra). Vive con los adjuntos: si el
    servidor se reinicia, la lista de documentos sigue sabiendo qué puso el analista en cada sitio."""
    carpeta = ADJUNTOS / ticker
    ruta = carpeta / DECLARADO
    datos = expediente.declaraciones(carpeta)
    if clave:
        datos[fichero] = clave
    else:
        datos.pop(fichero, None)
    carpeta.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")


def imprescindibles(ticker: str, filas: List[dict]) -> list:
    """Los documentos sin los que la emisión no puede empezar, del catálogo del mercado del emisor (un emisor de BME no
    tiene 10-K: lo suyo son las cuentas anuales)."""
    from ..fuentes.emisores import es_bme
    return catalogo.faltan(filas, solo_bloqueantes=True, mercado="bme" if es_bme(ticker) else "sec") if filas else []


def arrancar_traida(ticker: str, claves: List[str]) -> dict:
    """Marca la traída en marcha y lanza el hilo que baja de EDGAR lo que falte. Una sola a la vez por ticker."""
    e = estado(ticker)
    with _CERROJO:
        if e.get("traida") and e["traida"]["estado"] == "trayendo":
            return e["traida"]
        from ..fuentes.emisores import es_bme
        fuente = "la bolsa (BME)" if es_bme(ticker) else "EDGAR"
        e["traida"] = {"estado": "trayendo", "mensaje": f"pidiendo a {fuente} los documentos que faltan", "lineas": []}
    threading.Thread(target=traer, args=(ticker, claves), daemon=True).start()
    return e["traida"]


def traer(ticker: str, claves: List[str]) -> None:
    """Hilo: trae de EDGAR los documentos pedidos, los deja en la carpeta del analista y vuelve a clasificar.

    Lo traído no entra por una puerta distinta: es un PDF más en `adjuntos/<TICKER>/`, se clasifica por su portada y
    se cruza con EDGAR como cualquier otro. Lo que no tiene fuente oficial no se trae, y su aviso sigue en pie.
    """
    from ..fuentes import edgar
    e = estado(ticker)
    emisor = e.get("emisor")
    if emisor is None:
        e["traida"] = {"estado": "error", "mensaje": "primero hay que cargar el emisor (paso 1)", "lineas": []}
        return
    filas = (e["adjuntos"] or {}).get("adjuntos") or []
    mercado = getattr(emisor, "mercado", "sec")
    ya_estan = [d["clave"] for d in catalogo.estado(filas, mercado) if d["estado"] == "adjuntado"]
    try:
        if mercado == "bme":
            from ..fuentes import bme
            traidos = bme.traer(emisor, ADJUNTOS / ticker)      # la bolsa sirve el expediente entero de una vez
        else:
            traidos = edgar.traer(emisor, claves, ADJUNTOS / ticker, ya_estan)
            # con los documentos nuevos, los hechos XBRL de hoy: la emisión avisa si los de la caché se quedan viejos [9]
            try:
                e["facts"] = sec.companyfacts(emisor.cik, refrescar=True)
            except (RuntimeError, sec.SinContacto):
                pass
    except Exception as ex:
        e["traida"] = {"estado": "error", "mensaje": f"{ex.__class__.__name__}: {ex}", "lineas": []}
        return
    for t in traidos:
        if t.estado == "traído" and t.fichero:
            declarar(ticker, t.fichero, t.clave if t.clave in catalogo.POR_CLAVE else "")
    e["adjuntos"] = clasificar(ticker)
    cuenta = sum(1 for t in traidos if t.estado == "traído")
    fuente = "BME" if mercado == "bme" else "EDGAR"
    e["traida"] = {"estado": "listo", "lineas": [t.como_json() for t in traidos],
                   "mensaje": f"{cuenta} documentos traídos de {fuente}" if cuenta else f"no había nada nuevo que traer de {fuente}"}
    contrastar(ticker)


def ruta_decisiones(ticker: str) -> Path:
    """Las decisiones del analista sobre las discrepancias SEC ↔ documento: junto a sus entradas, y las lee la emisión."""
    return entorno.carpeta("entradas") / ticker / "decisiones.json"


def leer_decisiones(ticker: str) -> List[dict]:
    ruta = ruta_decisiones(ticker)
    try:
        return json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else []
    except ValueError:
        return []


def decidir(ticker: str, campo: str, periodo: str, valor: Optional[float], motivo: str) -> Optional[str]:
    """Guarda (o quita, con `valor` None) la decisión del analista sobre una discrepancia. None si fue bien; el motivo
    si no. Nunca decide el sistema: solo registra la cifra que el analista elige y por qué (03, «El sistema no las toma
    nunca por él»)."""
    decisiones = [d for d in leer_decisiones(ticker) if (d.get("campo"), d.get("periodo")) != (campo, periodo)]
    if valor is not None:
        motivo = " ".join(str(motivo or "").split())
        if len(motivo) < 5:
            return "Escribe en una frase por qué eliges esa cifra: queda como nota al pie en el informe."
        ruta_ent = _entradas_analista(ticker)
        analista = ""
        if ruta_ent is not None:
            try:
                analista = str((json.loads(ruta_ent.read_text(encoding="utf-8")).get("meta") or {}).get("analista") or "")
            except ValueError:
                pass
        decisiones.append({"campo": campo, "periodo": periodo, "valor": float(valor), "motivo": motivo,
                           "analista": analista or "analista", "fecha": date.today().isoformat()})
    ruta = ruta_decisiones(ticker)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(decisiones, ensure_ascii=False, indent=1), encoding="utf-8")
    return None


def _discrepancias(tab) -> List[dict]:
    """Cada discrepancia abierta con lo que el analista necesita para decidir: la cifra de la SEC y la de cada
    documento con su página."""
    salida = []
    for r in tab.bloquea:
        docs = [{"documento": c.documento, "pagina": c.pagina, "valor": c.valor} for c in (r.candidatos or [])[:4]]
        salida.append({"campo": r.campo.clave, "rotulo": r.campo.rotulo, "periodo": r.periodo.clave,
                       "sec": r.sec.valor if r.sec is not None and r.sec.hay_dato else None, "documentos": docs,
                       "unidad": r.campo.unidad, "pista": r.nota or ""})
    return salida


def contrastar(ticker: str) -> None:
    """El contraste campo × periodo del expediente con los hechos XBRL (el mismo que hace emitir.py), resumido, con las
    decisiones del analista ya aplicadas y las discrepancias que quedan abiertas."""
    e = estado(ticker)
    exp, facts = e.get("expediente"), e.get("facts")
    if exp is None or facts is None:
        e["contraste"] = {"estado": "pendiente", "mensaje": "hacen falta el emisor cargado y al menos un adjunto"}
        return
    e["contraste"] = {"estado": "contrastando", "mensaje": "extracción con coordenadas y contraste campo × periodo con la SEC"}
    try:
        from ..verificacion import contraste
        periodos = contraste.periodos_del_informe(exp, facts=facts[0])
        with _CERROJO_PDF:
            tab = contraste.contrastar(exp, facts[0], facts[1], periodos, ruta_decisiones(ticker))
        e["contraste"] = {"estado": "listo", "resumen": {str(k): v for k, v in tab.resumen.items()}, "bloquean": len(tab.bloquea), "no_aplican": dict(tab.no_aplican),
                          "ejercicios": [p.clave for p in periodos["anuales"]], "trimestres": [p.clave for p in periodos["trimestres"]],
                          "discrepancias": _discrepancias(tab), "decididas": leer_decisiones(ticker),
                          "mensaje": " · ".join(f"{k} {v}" for k, v in tab.resumen.items())}
    except ValueError as ex:      # sin 10-K no hay ejercicio base: se dice, no se inventa
        e["contraste"] = {"estado": "pendiente", "mensaje": str(ex)}
    except Exception as ex:
        e["contraste"] = {"estado": "error", "mensaje": f"{ex.__class__.__name__}: {ex}"}


def resumen_dcf(ticker: str) -> dict:
    ruta = DCF / f"{ticker}.xlsx"
    if not ruta.exists():
        return {"existe": False}
    from ..heredado import dcf
    try:
        m = dcf.cargar(ruta, DCF / f"{ticker}.recalculado.xlsx")
    except Exception as ex:
        return {"existe": True, "fichero": ruta.name, "error": f"{ex.__class__.__name__}: {ex}"}
    return {"existe": True, "fichero": ruta.name, "hojas": m.hojas, "titulo": m.titulo, "recalculado": bool(m.recalculado),
            "supuestos": [{"rotulo": s.rotulo, "valor": s.valor, "origen": s.origen, "celda": s.celda.cita} for s in m.supuestos],
            "escenarios": [{"nombre": x.nombre, "hoja": x.hoja, "wacc": x.wacc, "g": x.g, "peso": x.peso, "anios": len(x.anios), "filas": len(x.filas)} for x in m.escenarios],
            "tabla_escenarios": [{"nombre": t["nombre"], "wacc": t["wacc"], "g": t["g"], "valor_hoy": t["valor_hoy"], "peso": t["peso"]} for t in m.tabla_escenarios],
            "multiplos": [{"rotulo": x.rotulo, "actual": x.actual, "objetivo": x.objetivo, "valor_accion": x.valor_accion} for x in m.multiplos],
            "anclajes_objetivo": [{"rotulo": t, "valor": v} for t, v, _ in m.anclajes_objetivo],
            "valor_razonable": m.valor_razonable.get("hoy") if m.valor_razonable else None, "faltan": dict(m.faltan)}


# ---------------------------------------------------------------- emisión

def _entradas_analista(ticker: str) -> Optional[Path]:
    """Las últimas entradas guardadas por el asistente (una carpeta por fecha de informe)."""
    from ..entradas import asistente
    ultimas = asistente.fechas(ticker)
    return asistente.ruta(ticker, date.fromisoformat(ultimas[-1])) if ultimas else None


def entradas(ticker: str) -> List[Path]:
    """Todo lo que alimenta al informe: adjuntos, libro y entradas del analista."""
    fuentes = (_rutas(ticker) + [DCF / f"{ticker}.xlsx"] + [x for x in [_entradas_analista(ticker)] if x is not None]
               + [ruta_decisiones(ticker)])
    return [p for p in fuentes if p.exists()]


_CONTACTO = re.compile(r"^\S.*\s[^@\s]+@[^@\s]+\.[^@\s]+$")


def configuracion() -> dict:
    """Lo que la página necesita saber para no fallar en silencio: si hay contacto para la SEC (sin él no se puede buscar
    ninguna empresa), de dónde salen los precios y dónde están los datos."""
    contacto = entorno.variable("WC_SEC_CONTACTO")
    return {"sec_contacto": bool(contacto and "@" in contacto), "precio": entorno.variable("WC_PRECIO_FUENTE"),
            "datos": str(ADJUNTOS.parent)}


def guardar_contacto(contacto: str) -> Optional[str]:
    """Guarda en `.env` el contacto que la SEC exige en cada petición («Nombre correo@dominio»). None si fue bien; el
    motivo si no. Solo se envía a data.sec.gov y www.sec.gov (`fuentes.sec.contacto`)."""
    contacto = " ".join(contacto.split())
    if not _CONTACTO.match(contacto):
        return "Escribe tu nombre y tu correo, separados por un espacio: «Ana Pérez ana@ejemplo.com»."
    entorno.guardar("WC_SEC_CONTACTO", contacto)
    return None


_HUELLAS: Dict[Tuple[str, int, int], str] = {}


def _clave(p: Path) -> str:
    """«adjuntos/QCOM/x.pdf», «dcf/QCOM.xlsx», «entradas/QCOM/2026-09-27/entradas.json»: relativa a la carpeta de datos o
    al repositorio, nunca con el nombre de la carpeta en la que se clonó (la misma en cualquier copia)."""
    for raiz in (ADJUNTOS.parent, DCF.parent, entorno.carpeta("entradas").parent):
        try:
            return p.resolve().relative_to(raiz.resolve()).as_posix()
        except ValueError:
            continue
    return p.name


def huellas(ticker: str) -> Dict[str, str]:
    """La huella (sha256) de todo lo que alimenta al informe, por su clave. Se recalcula solo si el fichero cambia."""
    import hashlib
    salida = {}
    for p in entradas(ticker):
        st = p.stat()
        k = (str(p), st.st_mtime_ns, st.st_size)
        if k not in _HUELLAS:
            _HUELLAS[k] = hashlib.sha256(p.read_bytes()).hexdigest()
        salida[_clave(p)] = _HUELLAS[k]
    return salida


def escribir_emision(ticker: str, base: Path, generado: Optional[datetime] = None) -> Path:
    """`<informe>.emision.json`: cuándo se emitió y con qué entradas (sus huellas). Git no conserva la fecha de los
    ficheros —al clonar, todos llevan la hora del clonado—, así que «emitido» y «al día» no pueden salir de ella."""
    ruta = base.with_suffix(".emision.json")
    ruta.write_text(json.dumps({"generado": (generado or datetime.now()).isoformat(timespec="seconds"), "entradas": huellas(ticker)},
                               ensure_ascii=False, indent=1), encoding="utf-8")
    return ruta


def _fecha_del_nombre(pdf: Path) -> str:
    return pdf.stem.split("_tesis_")[-1]


def informe_en_disco(ticker: str) -> Optional[dict]:
    """El último informe emitido para el ticker y si está al día con lo que hay adjuntado ahora mismo.

    Se mira el disco y no la memoria: el analista vuelve al día siguiente, o reinicia el servidor, y su informe sigue ahí.
    «Al día» = las entradas de ahora son las mismas (misma huella) con las que se emitió; si adjunta, cambia o quita un
    documento después, el informe que ve es viejo y hay que decírselo en vez de dejar que lo tome por suyo. El último es
    el de fecha más reciente en su nombre, y la hora de emisión la que se guardó al emitir: las fechas de los ficheros no
    sobreviven a un `git clone`. Sin `.emision.json` (informes anteriores), las fechas de los ficheros, como antes.
    """
    salida = SALIDA / ticker
    pdfs = sorted(salida.glob(f"{ticker}_tesis_*.pdf"), key=lambda p: (_fecha_del_nombre(p), p.stat().st_mtime)) if salida.is_dir() else []
    if not pdfs:
        return None
    pdf = pdfs[-1]
    html = pdf.with_suffix(".html")
    try:
        meta = json.loads(pdf.with_suffix(".emision.json").read_text(encoding="utf-8"))
        emitido, al_dia = datetime.fromisoformat(meta["generado"]), meta["entradas"] == huellas(ticker)
    except (OSError, ValueError, KeyError, TypeError):
        emitido = datetime.fromtimestamp(pdf.stat().st_mtime)
        al_dia = pdf.stat().st_mtime >= max((p.stat().st_mtime for p in entradas(ticker)), default=0)
    return {"pdf": f"/informes/{ticker}/{pdf.name}", "html": f"/informes/{ticker}/{html.name}" if html.exists() else None,
            "fichero": pdf.name, "emitido": emitido.strftime("%d/%m/%Y %H:%M"), "al_dia": al_dia}


def emitir(ticker: str) -> dict:
    e = estado(ticker)
    em = e.get("emision")
    if em is not None and em["proceso"].poll() is None:
        return estado_emision(ticker)
    salida = SALIDA / ticker
    salida.mkdir(parents=True, exist_ok=True)
    # -u: el registro se ve línea a línea mientras corre
    orden = [sys.executable, "-u", "emitir.py", ticker, "--carpeta", str(ADJUNTOS / ticker), "--salida", str(salida)]
    if (DCF / f"{ticker}.xlsx").exists():
        orden += ["--dcf", str(DCF / f"{ticker}.xlsx")]
    if ruta_decisiones(ticker).exists():   # las discrepancias que el analista decidió en la página del expediente
        orden += ["--decisiones", str(ruta_decisiones(ticker))]
    ruta_entradas = _entradas_analista(ticker)
    if ruta_entradas is not None:          # la fecha del informe es la de las entradas guardadas, no la del día en que se pulsa
        orden += ["--fecha", ruta_entradas.parent.name, "--entradas", str(ruta_entradas)]
    registro = salida / "emision.log"
    fh = registro.open("w", encoding="utf-8")
    proceso = subprocess.Popen(orden, cwd=str(RAIZ), stdout=fh, stderr=subprocess.STDOUT,
                               env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"})
    e["emision"] = {"proceso": proceso, "registro": registro, "empezado": datetime.now(), "orden": orden, "fichero": fh}
    return estado_emision(ticker)


def estado_emision(ticker: str) -> Optional[dict]:
    e = estado(ticker)
    em = e.get("emision")
    if em is None:
        return None
    codigo = em["proceso"].poll()
    if codigo is not None and not em["fichero"].closed:
        em["fichero"].close()
    try:
        lineas = em["registro"].read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        lineas = []
    salida = SALIDA / ticker
    pdfs = [p for p in salida.glob(f"{ticker}_tesis_*.pdf") if p.stat().st_mtime >= em["empezado"].timestamp() - 1]
    pdfs.sort(key=lambda p: p.stat().st_mtime)
    pdf = pdfs[-1] if pdfs and codigo is not None else None
    estado_actual = "emitiendo" if codigo is None else ("terminado" if pdf is not None else "error")
    return {"estado": estado_actual, "codigo": codigo,
            "empezado": em["empezado"].strftime("%d/%m/%Y %H:%M:%S"), "registro": lineas[-80:], "orden": " ".join(Path(x).name if os.sep in x else x for x in em["orden"] if x != "-u"),
            "pdf": f"/informes/{ticker}/{pdf.name}" if pdf else None, "html": f"/informes/{ticker}/{pdf.with_suffix('.html').name}" if pdf and pdf.with_suffix(".html").exists() else None,
            "borrador": codigo == 2 and pdf is not None}     # emitir.py: 0 emitido · 2 borrador · 1 error


def resumen_ticker(ticker: str) -> dict:
    """Lo que las cuatro páginas necesitan saber del ticker, venga de la memoria o del disco."""
    e = estado(ticker)
    if e["carga"]["estado"] == "sin empezar" and (_rutas(ticker) or (SALIDA / ticker).is_dir()):
        arrancar_carga(ticker)      # el servidor se reinició, pero el trabajo del analista sigue en el disco: se retoma solo
    if e["dcf"] is None and (DCF / f"{ticker}.xlsx").exists():
        e["dcf"] = resumen_dcf(ticker)
    ruta_ent = _entradas_analista(ticker)
    adj = e["adjuntos"] or {"adjuntos": [], "avisos": []}
    if not adj["adjuntos"] and _rutas(ticker) and e["carga"]["estado"] == "listo":
        adj = e["adjuntos"] = clasificar(ticker)
    filas = adj["adjuntos"]
    from ..fuentes import emisores
    mercado = "bme" if emisores.es_bme(ticker) else "sec"
    if mercado == "bme":
        documentos = [dict(d, fuente=True, sin_fuente="") for d in catalogo.estado(filas, "bme")]
    else:
        documentos = [dict(d, fuente=edgar.hay_fuente(d["clave"]), sin_fuente=edgar.FUENTES[d["clave"]].sin_fuente
                           if d["clave"] in edgar.FUENTES else "") for d in catalogo.estado(filas)]
    return {"ticker": ticker, "mercado": mercado, "carga": e["carga"], "adjuntos": adj, "contraste": e["contraste"],
            "documentos": documentos,
            "sueltos": catalogo.sueltos(filas), "traida": e.get("traida"),
            "faltan_imprescindibles": [d.clave for d in catalogo.faltan(filas, mercado=mercado)],
            "dcf": e["dcf"] or {"existe": False},
            "posicion": {"existe": ruta_ent is not None, "fichero": ruta_ent.name if ruta_ent else "",
                         "fecha": ruta_ent.parent.name if ruta_ent else ""},
            "informe": informe_en_disco(ticker), "emision": estado_emision(ticker)}


# ---------------------------------------------------------------- HTTP

def _partes_multipart(tipo: str, cuerpo: bytes) -> Iterator[Tuple[str, bytes]]:
    """(nombre de fichero, bytes) de cada parte con fichero de un multipart/form-data, con la biblioteca estándar."""
    mensaje = BytesParser(policy=POLITICA_HTTP).parsebytes(b"Content-Type: " + tipo.encode("latin-1") + b"\r\n\r\n" + cuerpo)
    for parte in mensaje.iter_parts():
        nombre = parte.get_filename()
        if nombre:
            yield nombre, parte.get_payload(decode=True) or b""


def _nombre_seguro(nombre: str) -> str:
    base = _NOMBRE.sub("_", Path(nombre.replace("\\", "/")).name).strip(" .")
    return base[:120] or "fichero"


def _fecha(qs: Dict[str, List[str]]):
    """La fecha del informe de la consulta («2026-09-23»); hoy si no viene; None si no es una fecha."""
    from datetime import date
    texto = (qs.get("fecha") or [""])[0].strip()
    try:
        return date.fromisoformat(texto) if texto else date.today()
    except ValueError:
        return None


class _Manejador(BaseHTTPRequestHandler):
    def log_message(self, formato, *args):  # silencio: la consola es del analista
        return

    def _responder(self, codigo: int, cuerpo: bytes, tipo: str, extra: Optional[Dict[str, str]] = None) -> None:
        self.send_response(codigo)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(cuerpo)))
        self.send_header("Content-Security-Policy", extra.pop("Content-Security-Policy") if extra and "Content-Security-Policy" in extra else CSP_SAAS)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(cuerpo)

    def _json(self, codigo: int, datos) -> None:
        self._responder(codigo, json.dumps(datos, ensure_ascii=False, default=_json_listo).encode("utf-8"), "application/json; charset=utf-8")

    def _ticker(self, qs: Dict[str, List[str]]) -> Optional[str]:
        t = (qs.get("ticker") or [""])[0].strip().upper()
        return t if _TICKER.match(t) else None

    def _es_propia(self, tipos: Tuple[str, ...]) -> bool:
        tipo = (self.headers.get("Content-Type") or "").split(";", 1)[0].strip().lower()
        if tipo not in tipos or self.headers.get("X-Formulario") != "saas":
            return False
        origen, anfitrion, puerto = self.headers.get("Origin"), self.headers.get("Host") or "", self.server.server_address[1]
        return origen is None or origen == f"http://{anfitrion}" or origen in (f"http://127.0.0.1:{puerto}", f"http://localhost:{puerto}")

    def _cuerpo(self) -> bytes:
        largo = int(self.headers.get("Content-Length", "0"))
        if largo > MAXIMO_CUERPO:
            raise ValueError("cuerpo demasiado grande")
        return self.rfile.read(largo)

    # -- GET
    def do_GET(self) -> None:
        u = urlparse(self.path)
        camino, qs = u.path, parse_qs(u.query)
        if camino in PAGINAS:
            self._fichero(TABLERO / PAGINAS[camino])
            return
        if camino.startswith("/informes/"):
            self._informe(camino)
            return
        if camino == "/api/configuracion":
            self._json(200, configuracion())
            return
        if camino == "/api/tickers":
            q = (qs.get("q") or [""])[0]
            try:
                # los dos mercados: EE. UU. (SEC, si hay contacto) y España (BME, sin identificación)
                from ..fuentes import emisores
                self._json(200, [{"ticker": c["clave"], "nombre": c["nombre"], "mercado": c["mercado"], "id": c["id"],
                                  "cik": c.get("cik", ""), "bolsa": c.get("bolsa", "")} for c in emisores.buscar(q)])
            except Exception as ex:
                self._json(502, {"error": f"no se pudo buscar el emisor: {ex}"})
            return
        if camino == "/api/estado":
            t = self._ticker(qs)
            if t is None:
                self._json(400, {"error": "ticker no válido"})
                return
            self._json(200, resumen_ticker(t))
            return
        if camino == "/api/asistente":
            t, fecha = self._ticker(qs), _fecha(qs)
            if t is None or fecha is None:
                self._json(400, {"error": "ticker o fecha no válidos"})
                return
            from ..entradas import asistente, proponer
            datos, notas = asistente.cargar(t, fecha)
            faltas, avisos = asistente.validar(t, fecha, datos)
            self._json(200, {"ticker": t, "fecha": fecha.isoformat(), "fechas": asistente.fechas(t), "esquema": asistente.esquema(),
                             "entradas": datos, "notas": notas, "faltas": faltas, "avisos": avisos,
                             "propuestas": asistente.propuestas(t, fecha),
                             "propuestas_campos": proponer.como_json(proponer.proponer(t, fecha, datos))})
            return
        nombre = camino.lstrip("/")
        fichero = (TABLERO / nombre).resolve()
        if "/" in nombre or "\\" in nombre or ":" in nombre or ".." in nombre or fichero.parent != TABLERO or fichero.suffix not in _TIPOS or not fichero.is_file():
            self._responder(404, b"no existe", "text/plain; charset=utf-8")
            return
        self._fichero(fichero)

    def _fichero(self, ruta: Path) -> None:
        self._responder(200, ruta.read_bytes(), _TIPOS.get(ruta.suffix, "application/octet-stream"))

    def _informe(self, camino: str) -> None:
        """Lo emitido para un ticker (`salida/<TICKER>/…`): HTML autocontenido, PDF, registro. Nada fuera de esa carpeta."""
        trozos = [unquote(x) for x in camino.split("/")[2:]]
        if len(trozos) < 2 or not _TICKER.match(trozos[0]) or any(".." in x or not x for x in trozos):
            self._responder(404, b"no existe", "text/plain; charset=utf-8")
            return
        carpeta = (SALIDA / trozos[0]).resolve()
        ruta = carpeta.joinpath(*trozos[1:]).resolve()
        if carpeta not in ruta.parents or not ruta.is_file():
            self._responder(404, b"no existe", "text/plain; charset=utf-8")
            return
        tipos = {".html": "text/html; charset=utf-8", ".pdf": "application/pdf", ".png": "image/png", ".json": "application/json; charset=utf-8",
                 ".txt": "text/plain; charset=utf-8", ".log": "text/plain; charset=utf-8", ".svg": "image/svg+xml"}
        # el informe lleva sus propios estilos en línea (documento impreso): su CSP es la del documento, no la del tablero
        extra = {"Content-Security-Policy": "default-src 'none'; img-src data: 'self'; style-src 'unsafe-inline'; font-src 'self' data:"} if ruta.suffix == ".html" else None
        self._responder(200, ruta.read_bytes(), tipos.get(ruta.suffix, "application/octet-stream"), extra)

    # -- POST
    def _tragar(self) -> None:
        """Lee y descarta el cuerpo de una petición que se va a rechazar: si se responde y se cierra con datos sin
        leer en el socket, el cliente ve la conexión cortada en vez del 403 y no puede enseñar el motivo."""
        try:
            restante = int(self.headers.get("Content-Length", "0") or 0)
        except ValueError:
            return
        while restante > 0:
            trozo = self.rfile.read(min(65536, restante))
            if not trozo:
                return
            restante -= len(trozo)

    def do_POST(self) -> None:
        u = urlparse(self.path)
        camino, qs = u.path, parse_qs(u.query)
        t = self._ticker(qs)
        try:
            if camino == "/api/configuracion":
                if not self._es_propia(("application/json",)):
                    self._tragar(); self._json(403, {"error": "solo desde la propia página"}); return
                datos = json.loads(self._cuerpo().decode("utf-8") or "{}")
                error = guardar_contacto(str(datos.get("contacto") or ""))
                self._json(400 if error else 200, {"error": error} if error else configuracion())
                return
            if camino == "/api/preparar":
                if not self._es_propia(("application/json",)):
                    self._tragar(); self._json(403, {"error": "solo desde la propia página"}); return
                datos = json.loads(self._cuerpo().decode("utf-8") or "{}")
                t = str(datos.get("ticker") or "").strip().upper()
                if not _TICKER.match(t):
                    self._tragar(); self._json(400, {"error": "ticker no válido"}); return
                self._json(200, {"ticker": t, "carga": arrancar_carga(t)})
                return
            if t is None:
                self._tragar(); self._json(400, {"error": "ticker no válido"}); return
            if camino == "/api/adjuntos":
                if not self._es_propia(("multipart/form-data",)):
                    self._tragar(); self._json(403, {"error": "solo desde la propia página"}); return
                clave = (qs.get("documento") or [""])[0].strip().upper()
                doc = catalogo.POR_CLAVE.get(clave)
                if clave and doc is None:
                    self._tragar(); self._json(400, {"error": f"«{clave}» no es ninguno de los documentos de la lista"}); return
                admitidos = set(doc.formatos) if doc else ADMITIDOS
                carpeta = ADJUNTOS / t
                carpeta.mkdir(parents=True, exist_ok=True)
                guardados, rechazados = [], []
                for nombre, datos in _partes_multipart(self.headers.get("Content-Type", ""), self._cuerpo()):
                    seguro = _nombre_seguro(nombre)
                    if not datos:
                        rechazados.append(f"{nombre}: el fichero llegó vacío"); continue
                    if Path(seguro).suffix.lower() not in admitidos:
                        rechazados.append(f"{nombre}: {doc.titulo if doc else 'el expediente'} admite {', '.join(sorted(admitidos))}"); continue
                    (carpeta / seguro).write_bytes(datos)
                    declarar(t, seguro, clave)
                    guardados.append(seguro)
                e = estado(t)
                e["adjuntos"] = clasificar(t)
                threading.Thread(target=contrastar, args=(t,), daemon=True).start()
                self._json(200, {"guardados": guardados, "rechazados": rechazados, "estado": resumen_ticker(t)})
                return
            if camino == "/api/adjuntos/borrar":
                if not self._es_propia(("application/json",)):
                    self._tragar(); self._json(403, {"error": "solo desde la propia página"}); return
                nombre = _nombre_seguro(str(json.loads(self._cuerpo().decode("utf-8")).get("fichero") or ""))
                ruta = ADJUNTOS / t / nombre
                if ruta.is_file():
                    ruta.unlink()
                declarar(t, nombre, "")
                e = estado(t)
                e["adjuntos"] = clasificar(t)
                threading.Thread(target=contrastar, args=(t,), daemon=True).start()
                self._json(200, {"estado": resumen_ticker(t)})
                return
            if camino == "/api/decisiones":
                if not self._es_propia(("application/json",)):
                    self._tragar(); self._json(403, {"error": "solo desde la propia página"}); return
                datos = json.loads(self._cuerpo().decode("utf-8") or "{}")
                valor = datos.get("valor")
                error = decidir(t, str(datos.get("campo") or ""), str(datos.get("periodo") or ""),
                                None if valor is None else float(valor), str(datos.get("motivo") or ""))
                if error:
                    self._json(400, {"error": error}); return
                contrastar(t)                     # en el acto: la tarjeta se repinta con la discrepancia ya decidida
                self._json(200, {"estado": resumen_ticker(t)})
                return
            if camino == "/api/traer":
                if not self._es_propia(("application/json",)):
                    self._tragar(); self._json(403, {"error": "solo desde la propia página"}); return
                datos = json.loads(self._cuerpo().decode("utf-8") or "{}")
                filas = (estado(t)["adjuntos"] or {}).get("adjuntos") or []
                from ..fuentes import emisores as _emisores
                mercado = "bme" if _emisores.es_bme(t) else "sec"
                pedidas = datos.get("documentos") or [d["clave"] for d in catalogo.estado(filas, mercado) if d["estado"] == "falta"]
                if mercado == "bme" and not pedidas:
                    pedidas = ["CCAA"]                    # la bolsa sirve el expediente entero: se refresca igual
                claves = [c for c in pedidas if c in catalogo.POR_CLAVE]
                if not claves:
                    self._json(200, {"traida": {"estado": "listo", "mensaje": "no falta ningún documento de la lista", "lineas": []}}); return
                self._json(200, {"traida": arrancar_traida(t, claves)})
                return
            if camino == "/api/dcf":
                if not self._es_propia(("multipart/form-data",)):
                    self._tragar(); self._json(403, {"error": "solo desde la propia página"}); return
                DCF.mkdir(parents=True, exist_ok=True)
                for nombre, datos in _partes_multipart(self.headers.get("Content-Type", ""), self._cuerpo()):
                    if Path(nombre).suffix.lower() not in LIBROS or not datos:
                        self._tragar(); self._json(400, {"error": f"{nombre}: el DCF tiene que ser un libro Excel (.xlsx)"}); return
                    (DCF / f"{t}.xlsx").write_bytes(datos)
                    copia = DCF / f"{t}.recalculado.xlsx"
                    if copia.exists():
                        copia.unlink()           # el libro ha cambiado: la copia recalculada anterior ya no vale
                    break
                e = estado(t)
                e["dcf"] = resumen_dcf(t)
                self._json(200, e["dcf"])
                return
            if camino == "/api/asistente":
                if not self._es_propia(("application/json",)):
                    self._tragar(); self._json(403, {"error": "solo desde la propia página del asistente"}); return
                fecha = _fecha(qs)
                if fecha is None:
                    self._tragar(); self._json(400, {"error": "fecha no válida"}); return
                from ..entradas import asistente
                datos = json.loads(self._cuerpo().decode("utf-8") or "{}").get("entradas")
                if not isinstance(datos, dict):
                    self._json(400, {"error": "faltan las entradas"}); return
                datos.setdefault("meta", {})["fecha_informe"] = fecha.isoformat()
                guardado = asistente.guardar(t, fecha, datos)
                faltas, avisos = asistente.validar(t, fecha, datos)
                self._json(200, {"guardado": guardado.name, "carpeta": f"entradas/{t}/{fecha.isoformat()}", "faltas": faltas, "avisos": avisos})
                return
            if camino == "/api/emitir":
                if not self._es_propia(("application/json",)):
                    self._tragar(); self._json(403, {"error": "solo desde la propia página"}); return
                if not _rutas(t):
                    self._tragar(); self._json(400, {"error": "sin adjuntos: el informe necesita al menos el 10-K"}); return
                filas = (estado(t)["adjuntos"] or {}).get("adjuntos") or []
                faltan = imprescindibles(t, filas)
                if faltan:
                    self._tragar()
                    self._json(400, {"error": "falta " + " y ".join(f"«{d.titulo}»" for d in faltan)
                                              + ": " + " ".join(d.sin_el for d in faltan)})
                    return
                self._json(200, emitir(t))
                return
            self._tragar()
            self._responder(404, b"no existe", "text/plain; charset=utf-8")
        except (ValueError, json.JSONDecodeError) as ex:
            self._json(400, {"error": f"petición no válida: {ex}"})


class Servidor(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, puerto: int = 8770) -> None:
        super().__init__(("127.0.0.1", puerto), _Manejador)

    @property
    def direccion(self) -> str:
        return f"http://127.0.0.1:{self.server_address[1]}/"


def servir(puerto: int = 8770, en_hilo: bool = False) -> Tuple[Servidor, Optional[threading.Thread]]:
    servidor = Servidor(puerto)
    hilo = None
    if en_hilo:
        hilo = threading.Thread(target=servidor.serve_forever, daemon=True)
        hilo.start()
    return servidor, hilo


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Warrants & Co. · SaaS local de informes: expediente → DCF → analista → informe.")
    ap.add_argument("--puerto", type=int, default=8770)
    ap.add_argument("--sin-navegador", action="store_true")
    args = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    servidor, _ = servir(args.puerto)
    print(f"Warrants & Co. · informes en {servidor.direccion} (Ctrl+C para parar)", flush=True)
    if not args.sin_navegador:
        webbrowser.open(servidor.direccion)
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        servidor.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
