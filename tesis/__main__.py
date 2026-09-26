"""El punto de entrada único: `python -m tesis servir | documentos | generar | regresiones | rubrica`.

Manda lo que ya había: `servir` es `tesis.web.saas` y `generar` es `emitir.py`, y a los dos se les pasan sus opciones
tal cual —incluido `--help`—, así que nada de lo que el analista ya escribía cambia de significado. Lo que añade
el spec es `documentos`: el catálogo de lo que hay que adjuntar y qué falta, en el terminal, sin abrir el
navegador ni emitir nada.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Optional

RAIZ = Path(__file__).resolve().parents[1]

ORDENES = ("servir", "documentos", "generar", "regresiones", "rubrica")

_FILA_07 = None   # se compila al usarla: `re` solo hace falta en `regresiones`


def _emitir():
    """`emitir.py` vive en la raíz, no dentro del paquete: se importa por su ruta, no se duplica su lógica."""
    if str(RAIZ) not in sys.path:
        sys.path.insert(0, str(RAIZ))
    import emitir
    return emitir


def _documentos(argv: List[str]) -> int:
    import argparse

    from .datos import documentos as catalogo
    from .web import saas

    ap = argparse.ArgumentParser(prog="python -m tesis documentos",
                                 description="Qué documentos pide el informe de este emisor y cuáles están ya adjuntados.")
    ap.add_argument("ticker")
    args = ap.parse_args(argv)
    ticker = args.ticker.upper()

    clasificados = saas.clasificar(ticker)
    filas = clasificados["adjuntos"]
    print(f"{ticker} · {saas.ADJUNTOS / ticker}")
    for d in catalogo.estado(filas):
        print(f"  [{d['estado']:9}] {d['titulo']}  ({d['exigencia']})")
        for f in d["ficheros"]:
            print(f"        {f['fichero']}  ·  {f['certeza']}" + (f"  ·  EDGAR {f['accession']}" if f["edgar"] else ""))
        if d["estado"] == "falta":
            print(f"        sin él: {d['sin_el']}")
    sueltos = catalogo.sueltos(filas)
    if sueltos:
        print("  fuera del catálogo: " + ", ".join(f["fichero"] for f in sueltos))
    for aviso in clasificados["avisos"]:
        print(f"  aviso ({aviso['gravedad']}): {aviso['texto']}")
    faltan = catalogo.faltan(filas, solo_bloqueantes=True)
    if faltan:
        print("  NO SE PUEDE EMITIR sin: " + ", ".join(d.titulo for d in faltan))
    return 1 if faltan else 0


def _de_la_tabla_07() -> List[tuple]:
    """Las regresiones tal como están escritas en `docs/spec/07`: (id, fase, caso). La tabla no se copia aquí.

    Regla 9 llevada al contador: si el spec y el contador dijeran cada uno su lista, el progreso que enseña este
    comando podría ser verdad sobre una lista que ya no es la del analista.
    """
    import re

    texto = (RAIZ / "docs" / "spec" / "07_regresiones.md").read_text(encoding="utf-8")
    return [(m.group(1), m.group(2).strip(), m.group(3).strip())
            for m in re.finditer(r"^\|\s*(R\d+)\s*\|\s*(F\d)\s*\|\s*([^|]+)\|", texto, re.M)]


class _Recolector:
    """Apunta qué regresión cubre cada prueba y cómo le fue, para que la tabla salga de la ejecución, no de una lista."""

    def __init__(self):
        self.de_nodo, self.estado = {}, {}

    def pytest_collection_modifyitems(self, items):
        for it in items:
            for marca in it.iter_markers("regresion"):
                self.de_nodo.setdefault(it.nodeid, []).extend(marca.args)

    def pytest_runtest_logreport(self, report):
        if report.failed or report.when == "call":
            for rid in self.de_nodo.get(report.nodeid, ()):
                if report.failed or self.estado.get(rid) != "✗":
                    self.estado[rid] = "✗" if report.failed else "✓"


def _regresiones(argv: List[str]) -> int:
    import pytest

    recolector = _Recolector()
    codigo = pytest.main(["-q", "-m", "regresion", *argv], plugins=[recolector])
    filas = _de_la_tabla_07()
    print(f"\nRegresiones · {sum(1 for v in recolector.estado.values() if v == '✓')} de {len(filas)} en verde\n")
    print(f"{'id':4} {'fase':5} {'estado':9} caso")
    for rid, fase, caso in filas:
        print(f"{rid:4} {fase:5} {recolector.estado.get(rid, 'pendiente'):9} {caso}")
    return 0 if codigo == 0 else 1


def _rubrica(argv: List[str]) -> int:
    """La rúbrica institucional (docs/spec/08) resumida; con TICKER, además, la puerta de calidad de su último informe.
    Solo informa: el código de salida es siempre 0 (tramo 5 del plan del 26/09/2026)."""
    import json
    import yaml
    from .rutas import SPEC
    from . import entorno
    criterios = yaml.safe_load((SPEC / "08_rubrica.yaml").read_text(encoding="utf-8"))["criterios"]
    glifo = {"si": "✓", "parcial": "◐", "no": "✕", "por_comprobar": "?", "fuera": "—"}
    cuenta = {k: sum(1 for c in criterios if c["estado"] == k) for k in glifo}
    print(f"Rúbrica institucional · {cuenta['si']} sí · {cuenta['parcial']} parciales · {cuenta['no']} no · "
          f"{cuenta['por_comprobar']} por comprobar · {cuenta['fuera']} fuera de alcance (de {len(criterios)})\n")
    for c in criterios:
        print(f"{c['id']:>3} {glifo.get(c['estado'], '?')} {c['criterio']}  [{c['fase']}]" + (f" · {c['nota']}" if c.get("nota") else ""))
    if argv:
        t = argv[0].upper()
        auditorias = sorted((entorno.carpeta("salida") / t).glob(f"{t}_tesis_*.auditoria.json"))
        if auditorias:
            a = json.loads(auditorias[-1].read_text(encoding="utf-8"))
            print(f"\n{t}, último informe ({a.get('fecha')}): {len(a.get('bloqueos') or [])} bloqueos · {len(a.get('avisos') or [])} avisos · "
                  f"{'EMITIDO' if a.get('emitido') else 'BORRADOR'} · {len(a.get('confirmados_desde_propuesta') or {})} datos confirmados desde una propuesta")
        else:
            print(f"\n{t}: sin informes generados en {entorno.carpeta('salida') / t}")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    orden, resto = (argv[0] if argv else ""), argv[1:]
    if orden == "servir":
        from .web import saas
        return saas.main(resto)
    if orden == "generar":
        return _emitir().main(resto)
    if orden == "documentos":
        return _documentos(resto)
    if orden == "regresiones":
        return _regresiones(resto)
    if orden == "rubrica":
        return _rubrica(resto)
    print(f"uso: python -m tesis {{{'|'.join(ORDENES)}}} …\n\n{__doc__}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
