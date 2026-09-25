"""Traer de la fuente oficial los documentos que el analista no ha adjuntado.

De EDGAR sale el documento tal como se depositó: el 10-K, los 10-Q del ejercicio en curso, la proxy y los anexos 99
del 8-K de resultados. Se bajan en su HTML original y se imprimen a PDF con el mismo Chromium que imprime el informe,
porque la tubería lee cifras con sus coordenadas —página, recorte, evidencia— y eso solo lo da un PDF.

Tres cosas que este módulo no hace, a propósito:

* **No decide qué es cada documento.** El PDF impreso entra en el expediente como cualquier otro y se clasifica por lo
  que diga su portada (regla 3). Lo único que se le añade es el número de acceso de EDGAR como título del PDF, que es
  precisamente lo que `expediente` usa para casarlo con su depósito: el documento dice de dónde viene.
* **No inventa una fuente donde no la hay.** La transcripción de la call es de un tercero y las cuentas maquetadas del
  emisor están en su web: ni una ni otra se depositan. Eso se dice con su motivo y el aviso de que falta sigue en pie.
* **No vuelve a pedir lo que ya está.** Lo que el analista haya adjuntado no se descarga, y a la SEC se le piden tan
  pocas peticiones como sea posible: un 8-K sirve a la vez para la nota, las tablas, la carta y la presentación.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence

from .. import render
from . import sec

__all__ = ["Fuente", "Traido", "FUENTES", "traer", "hay_fuente"]

_EPIGRAFE_RESULTADOS = "2.02"        # «Results of Operations and Financial Condition»


@dataclass(frozen=True)
class Fuente:
    """De dónde sale oficialmente un documento del catálogo, o por qué no hay de dónde."""
    clave: str
    formulario: str = ""              # formulario de EDGAR que se descarga entero
    cuantos: int = 1                  # cuántos de los últimos (los 10-Q del ejercicio en curso son varios)
    del_8k: bool = False              # es un anexo 99 del 8-K de resultados
    sin_fuente: str = ""              # por qué no hay fuente oficial que traer


FUENTES: Dict[str, Fuente] = {
    "10K": Fuente("10K", formulario="10-K"),
    "10Q": Fuente("10Q", formulario="10-Q", cuantos=3),
    "PROXY": Fuente("PROXY", formulario="DEF 14A"),
    "NOTA": Fuente("NOTA", del_8k=True),
    "TABLAS": Fuente("TABLAS", del_8k=True),
    "CARTA": Fuente("CARTA", del_8k=True),
    "SLIDES": Fuente("SLIDES", del_8k=True),
    "CALL": Fuente("CALL", sin_fuente="la transcripción de la call la publica un tercero (S&P Global, Motley Fool, la web del emisor): "
                                      "no se deposita en la SEC y no hay de dónde traerla."),
    "FINWEB": Fuente("FINWEB", sin_fuente="las cuentas maquetadas por el emisor viven en su web de relación con inversores: "
                                          "no se depositan, y las mismas cifras ya están en el 10-Q y en el anexo 99.1."),
    "XLSX": Fuente("XLSX", sin_fuente="la hoja de cálculo de cuentas la publica el emisor en su web: no se deposita. "
                                      "Las cifras de la SEC ya entran por los hechos XBRL."),
}


@dataclass
class Traido:
    """Qué pasó con un documento que se intentó traer. Nunca se resume en un «ok»: cada uno con su motivo."""
    clave: str
    estado: str                       # «traído» | «ya estaba» | «sin fuente» | «no publicado» | «error»
    fichero: str = ""
    url: str = ""
    accession: str = ""
    formulario: str = ""
    presentado: Optional[date] = None
    motivo: str = ""

    def como_json(self) -> dict:
        return {"clave": self.clave, "estado": self.estado, "fichero": self.fichero, "url": self.url,
                "accession": self.accession, "formulario": self.formulario,
                "presentado": self.presentado.isoformat() if self.presentado else "", "motivo": self.motivo}


def hay_fuente(clave: str) -> bool:
    f = FUENTES.get(clave)
    return bool(f and not f.sin_fuente)


# ---------------------------------------------------------------- impresión del documento depositado

def _para_imprimir(html: str, accession: str) -> str:
    """El HTML depositado, preparado para imprimirlo sin salir a la red y declarando de qué depósito viene.

    El título pasa a ser el número de acceso porque es lo que `expediente.clasificar` lee para casar el documento con
    su depósito de EDGAR: así el PDF impreso aquí se verifica igual que el que se descarga a mano.
    La CSP corta cualquier petición del documento a la red: la SEC solo se consulta desde `fuentes/sec.py`, identificados.
    """
    meta = ('<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'; '
            'img-src data:; font-src data:">')
    titulo = f"<title>{accession}</title>"
    m = re.search(r"<head[^>]*>", html, re.I)
    if m:
        html = html[:m.end()] + meta + titulo + html[m.end():]
        return re.sub(r"<title>(?!" + re.escape(accession) + r")[^<]*</title>", "", html, count=1)
    return "<html><head>" + meta + titulo + "</head>" + html


def _nombre(formulario: str, deposito, sufijo: str = "") -> str:
    """Nombre del fichero que se deja en la carpeta del analista: forma, periodo y número de acceso, todo a la vista."""
    cuando = deposito.periodo or deposito.presentado
    partes = ["SEC", formulario.replace("/", "-").replace(" ", "-"), cuando.isoformat() if cuando else "", sufijo, deposito.accession]
    return "_".join(p for p in partes if p) + ".pdf"


def _imprimir_deposito(deposito, url: str, nombre: str, carpeta: Path, descargar: Callable, imprimir: Callable) -> Traido:
    salida = carpeta / nombre
    if salida.exists():
        return Traido(clave="", estado="ya estaba", fichero=nombre, url=url, accession=deposito.accession,
                      formulario=deposito.formulario, presentado=deposito.presentado,
                      motivo="ya se había traído antes: no se vuelve a pedir a la SEC.")
    html, _ = descargar(url)
    fuente = carpeta / ".sec"
    fuente.mkdir(parents=True, exist_ok=True)
    imprimir(_para_imprimir(html, deposito.accession), salida, fuente / (nombre[:-4] + ".html"))
    return Traido(clave="", estado="traído", fichero=nombre, url=url, accession=deposito.accession,
                  formulario=deposito.formulario, presentado=deposito.presentado,
                  motivo=f"impreso del documento depositado el {deposito.presentado:%d/%m/%Y} en EDGAR.")


# ---------------------------------------------------------------- los trabajos

def _de_formulario(emisor, clave: str, formulario: str, cuantos: int, carpeta: Path,
                   descargar: Callable, imprimir: Callable) -> List[Traido]:
    depositos = [d for d in emisor.depositos if d.formulario == formulario and d.documento.lower().endswith((".htm", ".html"))]
    depositos.sort(key=lambda d: d.presentado, reverse=True)
    if not depositos:
        return [Traido(clave=clave, estado="no publicado",
                       motivo=f"EDGAR no tiene ningún {formulario} reciente de este emisor entre sus últimos depósitos.")]
    salida = []
    for d in depositos[:cuantos]:
        try:
            t = _imprimir_deposito(d, d.url, _nombre(formulario, d), carpeta, descargar, imprimir)
            t.clave = clave
        except Exception as ex:      # un documento que no se puede traer se dice; los demás siguen
            t = Traido(clave=clave, estado="error", url=d.url, accession=d.accession, formulario=formulario,
                       presentado=d.presentado, motivo=f"{ex.__class__.__name__}: {ex}")
        salida.append(t)
    return salida


def _anexos_del_8k(emisor, claves: Sequence[str], carpeta: Path, descargar: Callable, imprimir: Callable,
                   indice: Callable) -> List[Traido]:
    """Los anexos 99 del último 8-K de resultados (epígrafe 2.02). Uno solo sirve a la nota, las tablas, la carta y
    la presentación: qué es cada anexo lo dirá su portada, no nosotros."""
    pedidos = ", ".join(claves)
    ochok = sorted([d for d in emisor.depositos if d.formulario == "8-K" and _EPIGRAFE_RESULTADOS in (d.epigrafes or "")],
                   key=lambda d: d.presentado, reverse=True)
    if not ochok:
        return [Traido(clave=pedidos, estado="no publicado",
                       motivo="EDGAR no tiene ningún 8-K con el epígrafe 2.02 (resultados) entre los últimos depósitos.")]
    d = ochok[0]
    carpeta_edgar = f"https://www.sec.gov/Archives/edgar/data/{int(d.cik)}/{d.accession.replace('-', '')}"
    try:
        idx, _ = indice(f"{carpeta_edgar}/index.json")
        nombres = [it["name"] for it in idx["directory"]["item"]
                   if sec.es_anexo_99(it["name"])]
    except Exception as ex:
        return [Traido(clave=pedidos, estado="error", accession=d.accession, formulario="8-K", presentado=d.presentado,
                       motivo=f"EDGAR no sirvió el índice del 8-K: {ex}")]
    if not nombres:
        return [Traido(clave=pedidos, estado="no publicado", accession=d.accession, formulario="8-K", presentado=d.presentado,
                       motivo=f"el 8-K de resultados del {d.presentado:%d/%m/%Y} no lleva ningún anexo 99.")]
    salida = []
    for i, nombre in enumerate(sorted(nombres), 1):
        try:
            t = _imprimir_deposito(d, f"{carpeta_edgar}/{nombre}", _nombre("8-K", d, f"ex99-{i}"), carpeta, descargar, imprimir)
            t.clave = pedidos
            t.motivo += " Qué es (nota, tablas, carta o presentación) lo decide su portada al clasificarlo."
        except Exception as ex:
            t = Traido(clave=pedidos, estado="error", url=f"{carpeta_edgar}/{nombre}", accession=d.accession,
                       formulario="8-K", presentado=d.presentado, motivo=f"{ex.__class__.__name__}: {ex}")
        salida.append(t)
    return salida


def anotar_origen(carpeta: Path, traidos: Sequence[Traido], depositos: Dict[str, object]) -> None:
    """Deja escrito en `origen.json` de qué depósito salió cada fichero traído.

    Es lo que hace que un documento traído no dependa de adivinar su portada: el expediente le pone el formulario,
    el número de acceso y las fechas que EDGAR publica de ese depósito (`expediente.origenes`).
    """
    import json
    ruta = Path(carpeta) / "origen.json"
    datos = {}
    if ruta.is_file():
        try:
            datos = json.loads(ruta.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            datos = {}
    for t in traidos:
        if t.estado not in ("traído", "ya estaba") or not t.fichero:
            continue
        d = depositos.get(t.accession)
        datos[t.fichero] = {"url": t.url, "accession": t.accession, "formulario": t.formulario,
                            "presentado": t.presentado.isoformat() if t.presentado else "",
                            "periodo": getattr(d, "periodo", None).isoformat() if getattr(d, "periodo", None) else ""}
    ruta.write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")


def traer(emisor, claves: Sequence[str], carpeta: Path, ya_estan: Sequence[str] = (),
          descargar: Callable = sec.descargar_texto, imprimir: Callable = render.a_pdf,
          indice: Callable = sec._descargar) -> List[Traido]:
    """Trae de EDGAR los documentos pedidos que falten. Devuelve qué pasó con cada uno, uno por uno."""
    carpeta = Path(carpeta)
    carpeta.mkdir(parents=True, exist_ok=True)
    salida: List[Traido] = []
    del_8k = []
    for clave in claves:
        f = FUENTES.get(clave)
        if f is None:
            salida.append(Traido(clave=clave, estado="sin fuente", motivo="no es ninguno de los documentos de la lista."))
        elif clave in ya_estan:
            salida.append(Traido(clave=clave, estado="ya estaba", motivo="ya lo has adjuntado: no se pide a la SEC."))
        elif f.sin_fuente:
            salida.append(Traido(clave=clave, estado="sin fuente", motivo=f.sin_fuente))
        elif f.del_8k:
            del_8k.append(clave)
        else:
            salida += _de_formulario(emisor, clave, f.formulario, f.cuantos, carpeta, descargar, imprimir)
    if del_8k:
        salida += _anexos_del_8k(emisor, del_8k, carpeta, descargar, imprimir, indice)
    anotar_origen(carpeta, salida, {d.accession: d for d in emisor.depositos})
    return salida
