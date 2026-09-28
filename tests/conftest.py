"""La batería no puede cambiar sus propios datos de prueba.

`tests/fixtures/` es la verdad congelada contra la que se comparan las pruebas: si una ejecución escribe ahí (una
descarga de EDGAR que se guarda en la caché de fixtures, una respuesta de la bolsa del día), el siguiente verde ya no
es el mismo verde. Pasó el 26/09/2026: validar las entradas de JPM descargó su 10-K y lo dejó en `cache_sec/`. Al
acabar, se compara el contenido de la carpeta con el del principio y la batería falla nombrando lo que cambió.

Lo mismo con los ficheros sueltos de la raíz del repositorio (A0, fallo [78] de la auditoría del 27/09/2026): un script
auxiliar dejó allí un `textos.pkl`. Las carpetas de caché de la raíz (`cache_sec/`, `cache_bolsa/`) no cuentan: crecen
por diseño.
"""

from pathlib import Path

_FIXTURES = Path(__file__).resolve().parent / "fixtures"
_RAIZ = Path(__file__).resolve().parents[1]


def _foto() -> dict:
    return {str(p.relative_to(_FIXTURES)): (p.stat().st_size, p.stat().st_mtime_ns)
            for p in _FIXTURES.rglob("*") if p.is_file()} if _FIXTURES.exists() else {}


def _foto_raiz() -> set:
    return {p.name for p in _RAIZ.iterdir() if p.is_file()}


def pytest_sessionstart(session):
    session.config._fixtures_antes = _foto()
    session.config._raiz_antes = _foto_raiz()


def pytest_sessionfinish(session, exitstatus):
    antes = getattr(session.config, "_fixtures_antes", None)
    if antes is None:
        return
    despues = _foto()
    cambios = sorted(set(despues) - set(antes)) + sorted(k for k in antes if k in despues and antes[k] != despues[k]) \
        + sorted(set(antes) - set(despues))
    if cambios:
        print("\n\nLa batería ha modificado tests/fixtures/ (no puede):\n  " + "\n  ".join(cambios[:20]))
        session.exitstatus = 1
    sueltos = sorted(_foto_raiz() - getattr(session.config, "_raiz_antes", _foto_raiz()))
    if sueltos:
        print("\n\nLa batería ha dejado ficheros en la raíz del repositorio (no puede):\n  " + "\n  ".join(sueltos))
        session.exitstatus = 1
