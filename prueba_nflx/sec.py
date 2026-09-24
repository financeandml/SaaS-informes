"""Paso 2 de la prueba: lo que la SEC tiene depositado de Netflix, tal cual.

Cuatro servicios, los mismos que fija PLANTILLA_TESIS.md §2:

    submissions    quién es el emisor y qué ha depositado, con fecha y acceso
    companyfacts   todos los hechos XBRL (10-K y 10-Q), sin dimensiones
    Archives       el documento concreto: 10-K, DEF 14A, 8-K, Exhibit 21, Form 4
    (frames no hace falta aquí: no se construyen comparables en esta prueba)

Nada se transforma. Se guarda la respuesta íntegra en `datos/sec/` para que
cualquier cifra del informe se pueda seguir hasta el fichero que la SEC sirvió,
y para no volver a pedirla: la SEC limita a 10 peticiones por segundo y exige
identificarse con nombre y correo, que se toman de la configuración del
analista y no se escriben aquí.
"""

from __future__ import annotations

import html
import json
import re
import sys
import time
from pathlib import Path

import requests

AQUI = Path(__file__).resolve().parent
SEC = AQUI / "datos" / "sec"
CIK = 1065280
CIK10 = f"{CIK:010d}"

# La identificación que la SEC exige la declaró el analista en su configuración
# (secrets.toml del proyecto anterior). Se lee de ahí; si no está, se para.
_SECRETOS = Path(r"C:\Users\Sergi\Downloads\Warrants&co\PROYECTOS VERANO\QUANTUM\.streamlit\secrets.toml")


def contacto() -> str:
    m = re.search(r'WC_SEC_CONTACTO\s*=\s*"([^"]+)"', _SECRETOS.read_text(encoding="utf-8"))
    if not m:
        sys.exit("Sin contacto para la SEC: configura WC_SEC_CONTACTO.")
    return m.group(1)


CABECERAS = {"User-Agent": contacto(), "Accept-Encoding": "gzip, deflate"}
_ultima = 0.0


def bajar(url: str, destino: Path, forzar: bool = False) -> bytes | None:
    """Descarga con caché en disco y con el ritmo que pide la SEC."""
    global _ultima
    if destino.exists() and not forzar:
        return destino.read_bytes()
    espera = 0.12 - (time.time() - _ultima)
    if espera > 0:
        time.sleep(espera)
    r = requests.get(url, headers=CABECERAS, timeout=90)
    _ultima = time.time()
    if r.status_code != 200:
        print(f"  {r.status_code} {url}")
        return None
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(r.content)
    print(f"  200 {url} ({len(r.content):,} bytes)")
    return r.content


def a_texto(html_crudo: bytes) -> str:
    """HTML de EDGAR a texto plano conservando los saltos de fila de las tablas.

    No se usa ningún analizador HTML: el objetivo es poder buscar «26,163,437»
    y «Reed Hastings» en el texto, no reconstruir la maqueta.
    """
    s = html_crudo.decode("utf-8", errors="replace")
    s = re.sub(r"(?is)<(script|style|head)[^>]*>.*?</\1>", " ", s)
    s = re.sub(r"(?i)</(td|th)>", " | ", s)
    s = re.sub(r"(?i)</(tr|p|div|br|li|h\d|table)>|<br\s*/?>", "\n", s)
    s = re.sub(r"<[^>]+>", " ", s)
    s = html.unescape(s)
    s = s.replace("\xa0", " ")
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n\s*\n+", "\n", s)
    return s.strip()


def archivo(accession: str, fichero: str) -> str:
    return f"https://www.sec.gov/Archives/edgar/data/{CIK}/{accession.replace('-', '')}/{fichero}"


def indice(accession: str) -> list[dict]:
    """Los ficheros de un depósito, con el tipo que la SEC les asigna."""
    url = archivo(accession, "index.json")
    crudo = bajar(url, SEC / "indices" / f"{accession}.json")
    if not crudo:
        return []
    return json.loads(crudo)["directory"]["item"]


def main() -> None:
    SEC.mkdir(parents=True, exist_ok=True)

    print("submissions")
    sub = json.loads(bajar(f"https://data.sec.gov/submissions/CIK{CIK10}.json", SEC / "submissions.json"))
    print("companyfacts")
    bajar(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{CIK10}.json", SEC / "companyfacts.json")

    rec = sub["filings"]["recent"]
    filas = [dict(form=rec["form"][i], fecha=rec["filingDate"][i], periodo=rec["reportDate"][i],
                  accession=rec["accessionNumber"][i], principal=rec["primaryDocument"][i],
                  descripcion=rec["primaryDocDescription"][i], items=rec["items"][i])
             for i in range(len(rec["form"]))]

    # Los documentos que la plantilla lee en texto. Se toma el ÚLTIMO de cada
    # tipo y, además, todo 8-K desde el cierre del último 10-K: un 8-K posterior
    # a los adjuntos es justo lo que el analista no ha visto.
    pedidos: list[dict] = []
    for tipo in ("10-K", "DEF 14A"):
        pedidos.append(next(f for f in filas if f["form"] == tipo))
    pedidos += [f for f in filas if f["form"] == "10-Q" and f["fecha"] >= "2026-01-01"]
    pedidos += [f for f in filas if f["form"] in ("8-K", "8-K/A") and f["fecha"] >= "2025-10-01"]

    catalogo = []
    for f in pedidos:
        print(f"{f['form']} {f['fecha']} {f['accession']}")
        crudo = bajar(archivo(f["accession"], f["principal"]), SEC / "documentos" / f["accession"] / f["principal"])
        entrada = dict(f, ficheros=[])
        if crudo:
            texto = a_texto(crudo)
            (SEC / "texto" / f"{f['form'].replace('/', '_')}_{f['fecha']}_{f['accession']}.txt").parent.mkdir(parents=True, exist_ok=True)
            (SEC / "texto" / f"{f['form'].replace('/', '_')}_{f['fecha']}_{f['accession']}.txt").write_text(texto, encoding="utf-8")
            entrada["ficheros"].append(f["principal"])
        # Anexos que importan: Exhibit 21 (filiales) del 10-K y el 99.1 de los 8-K de resultados.
        for it in indice(f["accession"]):
            nombre = it["name"]
            if re.search(r"(?i)ex-?21|exhibit21", nombre) or (f["form"].startswith("8-K") and re.search(r"(?i)ex-?99|ex99", nombre)):
                crudo = bajar(archivo(f["accession"], nombre), SEC / "documentos" / f["accession"] / nombre)
                if crudo and nombre.lower().endswith((".htm", ".html")):
                    (SEC / "texto" / f"{f['form'].replace('/', '_')}_{f['fecha']}_{f['accession']}_{nombre}.txt").write_text(a_texto(crudo), encoding="utf-8")
                entrada["ficheros"].append(nombre)
        catalogo.append(entrada)

    # Form 4 de los últimos doce meses, en XML: es lo que alimenta las operaciones
    # de insiders del apartado 6. Se guarda el fichero XML del depósito.
    desde = "2025-09-16"
    forms4 = [f for f in filas if f["form"] == "4" and f["fecha"] >= desde]
    print(f"Form 4 desde {desde}: {len(forms4)}")
    for f in forms4:
        xml = f["principal"].split("/")[-1]
        crudo = bajar(archivo(f["accession"], xml), SEC / "form4" / f"{f['fecha']}_{f['accession']}.xml")
        catalogo.append(dict(f, ficheros=[xml] if crudo else []))

    (SEC / "catalogo.json").write_text(json.dumps(dict(
        emisor=dict(cik=CIK, nombre=sub["name"], tickers=sub["tickers"], bolsas=sub["exchanges"],
                    sic=sub["sic"], sic_descripcion=sub["sicDescription"], estado=sub["stateOfIncorporation"],
                    cierre_fiscal=sub["fiscalYearEnd"], ein=sub["ein"], web=sub.get("website"),
                    direccion=sub["addresses"]["business"], antiguos_nombres=sub.get("formerNames")),
        documentos=catalogo), ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
