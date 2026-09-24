"""Paso 1 de la prueba: qué ha adjuntado el analista, de qué fecha es cada cosa.

El SaaS no puede fiarse del nombre del fichero —tres de los siete adjuntos se
llaman con un UUID— ni de la fecha de creación del PDF, que es la de la
descarga o la de la maquetación. La fecha que importa es la que el propio
documento declara: el periodo que cubre y el día en que se firmó o depositó.
Aquí se leen las dos de la primera página y se clasifica cada adjunto en uno de
los tres apartados que exige la plantilla (anuales · trimestrales · guidance).

Salida: `datos/adjuntos.json` y el texto de cada página en `datos/texto/`.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

import pypdfium2 as pdfium

AQUI = Path(__file__).resolve().parent
CARPETA_ADJUNTOS = Path(r"C:\Users\Sergi\Downloads\Warrants&co")
DATOS = AQUI / "datos"
TEXTO = DATOS / "texto"

# Lo que subió el analista, en el orden en que lo adjuntó. El UUID es el nombre
# con el que EDGAR sirve el PDF; el título interno del PDF trae el número de acceso.
ADJUNTOS = [
    "99482238-46b2-4d0d-b292-40e6781bdf03.pdf",
    "13fce243-80be-4f3a-9033-bf415d3cc71f.pdf",
    "65ef36cc-6598-4deb-a42b-8c59a8e31fd3.pdf",
    "Netflix-2026-Proxy-Statement.pdf",
    "FINAL-Q2-26-Shareholder-Letter.pdf",
    "Netflix-Inc-_Earnings-Call_2026-07-16T00_00_00_English-1.pdf",
    "Q2-26-Website-Financials.pdf",
]

MESES = {m: i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July",
     "August", "September", "October", "November", "December"], 1)}


def _fecha_larga(texto: str) -> str | None:
    """«July 16, 2026» → «2026-07-16». La primera que aparezca."""
    m = re.search(r"(January|February|March|April|May|June|July|August|September|"
                  r"October|November|December)\s+(\d{1,2}),\s+(\d{4})", texto)
    if not m:
        return None
    return f"{int(m.group(3)):04d}-{MESES[m.group(1)]:02d}-{int(m.group(2)):02d}"


def clasificar(p1: str, titulo_pdf: str, texto_total: str) -> dict:
    """Qué documento es, qué periodo cubre y a qué apartado de la plantilla va.

    Todo sale de lo que el documento dice de sí mismo. La certeza no es un
    adorno: un PDF cuya portada no dice qué es se clasifica por pistas más
    débiles y hay que decirlo.
    """
    if "FORM 10-K" in p1:
        m = re.search(r"fiscal year ended\s+(\w+ \d{1,2}, \d{4})", p1)
        return dict(tipo="10-K", apartado="anuales", periodo_fin=_fecha_larga(m.group(1)) if m else None,
                    accession=titulo_pdf or None, certeza="alta",
                    motivo="La portada dice «FORM 10-K» y declara el ejercicio fiscal cerrado.")
    if "FORM 10-Q" in p1:
        m = re.search(r"quarterly period ended\s+(\w+ \d{1,2}, \d{4})", p1)
        return dict(tipo="10-Q", apartado="trimestrales", periodo_fin=_fecha_larga(m.group(1)) if m else None,
                    accession=titulo_pdf or None, certeza="alta",
                    motivo="La portada dice «FORM 10-Q» y declara el trimestre cerrado.")
    if "Proxy" in p1 and "Annual" in p1:
        m = re.search(r"(?:to be held on|will be held on)\s+(\w+ \d{1,2}, \d{4})", texto_total, re.I)
        return dict(tipo="DEF 14A", apartado="anuales", periodo_fin=_fecha_larga(m.group(1)) if m else None,
                    accession=None, certeza="alta",
                    motivo="La portada dice «Proxy Statement and Notice of Annual Meeting». "
                           "Va con las cuentas anuales: accionariado, consejo y retribución.")
    if "Fellow shareholders" in p1:
        # El trimestre que se presenta es el que la carta comenta («Q2 revenue
        # grew…»), no el primero de la tabla, que arranca un año antes.
        m = re.search(r"Q(\d) revenue", p1)
        fecha = _fecha_larga(p1)
        return dict(tipo="Carta a accionistas", apartado="guidance",
                    periodo_fin=None,
                    trimestre=f"Q{m.group(1)} {fecha[:4]}" if (m and fecha) else None,
                    accession=None, certeza="alta",
                    motivo="Empieza «Fellow shareholders» y trae la tabla de resultados y previsión. "
                           "Es el anexo 99.1 del 8-K de resultados: contiene el guidance.")
    if "Earnings Call Transcript" in p1:
        m = re.search(r"FQ(\d) (\d{4}) Earnings Call", p1)
        return dict(tipo="Transcripción de la conferencia de resultados", apartado="guidance",
                    periodo_fin=None, trimestre=f"Q{m.group(1)} {m.group(2)}" if m else None,
                    accession=None, certeza="alta",
                    motivo="La cabecera dice «Earnings Call Transcripts». Guidance verbal de la dirección. "
                           "No está depositado en la SEC: es un documento de un tercero (S&P Global).")
    if "Consolidated Statements of Operations" in p1 and "unaudited" in p1:
        # Sin portada, el periodo es la última columna de la cabecera: una
        # línea de «Month D,» y otra de años, emparejadas por posición.
        lineas = p1.splitlines()
        meses = anyos = None
        for i, l in enumerate(lineas):
            if re.fullmatch(r"(?:(?:January|February|March|April|May|June|July|August|September|"
                            r"October|November|December) \d{1,2}, ?)+", l.strip()) and i + 1 < len(lineas):
                meses = re.findall(r"(\w+ \d{1,2}),", l)
                anyos = re.findall(r"\d{4}", lineas[i + 1])
                break
        fin = _fecha_larga(f"{meses[-1]}, {anyos[-1]}") if meses and anyos and len(meses) == len(anyos) else None
        return dict(tipo="Estados financieros trimestrales (web del emisor)", apartado="trimestrales",
                    periodo_fin=fin, accession=None, certeza="media",
                    motivo="No tiene portada: empieza directamente por la cuenta de resultados trimestral "
                           "«(unaudited)». Coincide con el fichero de financials que Netflix publica en su web de IR.")
    return dict(tipo="desconocido", apartado=None, periodo_fin=None, accession=None, certeza="baja",
                motivo="Ninguna pista reconocible en la primera página.")


def leer(ruta: Path) -> tuple[dict, list[str]]:
    doc = pdfium.PdfDocument(str(ruta))
    paginas = [doc[i].get_textpage().get_text_range() for i in range(len(doc))]
    p1 = paginas[0]
    meta = {k: doc.get_metadata_value(k) for k in ("Title", "CreationDate", "ModDate", "Producer")}
    clase = clasificar(p1, meta.get("Title") or "", "\n".join(paginas[:8]))
    # Fecha declarada por el documento: la primera fecha larga de la portada.
    # En un 10-K/10-Q la de la portada es el cierre del periodo; la de firma va al final.
    fecha_portada = _fecha_larga(p1)
    firma = None
    for t in reversed(paginas):
        m = re.search(r"Dated?:\s*(\w+ \d{1,2}, \d{4})", t)
        if m:
            firma = _fecha_larga(m.group(1))
            break
    huella = hashlib.sha256(ruta.read_bytes()).hexdigest()
    return dict(fichero=ruta.name, tamano=ruta.stat().st_size, sha256=huella, paginas=len(doc),
                metadatos_pdf=meta, fecha_portada=fecha_portada, fecha_firma=firma, **clase), paginas


def main() -> None:
    TEXTO.mkdir(parents=True, exist_ok=True)
    inventario = []
    for nombre in ADJUNTOS:
        ruta = CARPETA_ADJUNTOS / nombre
        ficha, paginas = leer(ruta)
        clave = {"10-K": "10K", "10-Q": "10Q", "DEF 14A": "PROXY", "Carta a accionistas": "CARTA",
                 "Transcripción de la conferencia de resultados": "CALL",
                 "Estados financieros trimestrales (web del emisor)": "FINWEB"}.get(ficha["tipo"], "DOC")
        if ficha.get("periodo_fin"):
            clave += "_" + ficha["periodo_fin"].replace("-", "")
        elif ficha.get("trimestre"):
            clave += "_" + ficha["trimestre"].replace(" ", "_")
        ficha["clave"] = clave
        carpeta = TEXTO / clave
        carpeta.mkdir(parents=True, exist_ok=True)
        for i, t in enumerate(paginas, 1):
            (carpeta / f"p{i:03d}.txt").write_text(t, encoding="utf-8")
        inventario.append(ficha)
        print(f"{clave:16} {ficha['tipo']:48} págs={ficha['paginas']:3} "
              f"periodo={ficha.get('periodo_fin') or ficha.get('trimestre')} "
              f"portada={ficha['fecha_portada']} firma={ficha['fecha_firma']} "
              f"apartado={ficha['apartado']} certeza={ficha['certeza']}")
    (DATOS / "adjuntos.json").write_text(json.dumps(inventario, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
