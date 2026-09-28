"""Congela lo que leyeron las cuatro emisiones de la auditoría del 27/09/2026 (A0): `python tests/grabar_auditoria.py`.

Emite AAPL, NFLX, ORCL y QCOM sin red, con las mismas entradas y adjuntos, contra una caché vacía que se va llenando con
la respuesta guardada de cada URL que la emisión pide —de `cache_sec/` y `cache_bolsa/`, y solo las del 27/09/2026 o
anteriores—. Lo que queda en `tests/fixtures/auditoria/` es exactamente lo que el informe necesitó: ni una respuesta más
(el repositorio no carga 20 MB de caché) ni una menos (la prueba no puede ir a la red a medias).

No es una prueba: se ejecuta a mano una vez. Las pruebas (`prueba_auditoria_27_09.py`) solo leen lo congelado.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

DESTINO = RAIZ / "tests" / "fixtures" / "auditoria"
DIA = date(2026, 9, 27)
TICKERS = ("AAPL", "NFLX", "ORCL", "QCOM")


def main(entradas: Path) -> int:
    from tesis import entorno
    from tesis.fuentes import precio, sec
    vivo_sec, vivo_bolsa = RAIZ / "cache_sec", RAIZ / "cache_bolsa"
    sec_dest, bolsa_dest = DESTINO / "cache_sec", DESTINO / "cache_bolsa"
    sec_dest.mkdir(parents=True, exist_ok=True)
    bolsa_dest.mkdir(parents=True, exist_ok=True)

    ruta_sec_original = sec._ruta_cache

    def ruta_sec(url: str) -> Path:
        destino = sec_dest / ruta_sec_original(url).name
        vivo = vivo_sec / destino.name
        if not destino.exists() and vivo.exists():
            shutil.copy2(vivo, destino)
        return destino

    ruta_bolsa_original = precio._ruta_bolsa

    def ruta_bolsa(url: str, dia: date):
        _, ruta = ruta_bolsa_original(url, dia)
        prefijo = ruta.name.rsplit("__", 1)[0]
        for vivo in vivo_bolsa.glob(prefijo + "__*.json.gz"):
            if date.fromisoformat(vivo.name.rsplit("__", 1)[1][:10]) <= DIA and not (bolsa_dest / vivo.name).exists():
                shutil.copy2(vivo, bolsa_dest / vivo.name)
        return bolsa_dest, bolsa_dest / ruta.name

    sec._ruta_cache, precio._ruta_bolsa = ruta_sec, ruta_bolsa
    precio.SOLO_CACHE = True
    os.environ["WC_SEC_CONTACTO"] = ""                     # sin identificación, la SEC no se consulta: nada sale a la red
    import emitir
    codigos = {}
    for t in TICKERS:
        (DESTINO / t).mkdir(exist_ok=True)
        shutil.copy2(entradas / t / "entradas.json", DESTINO / t / "entradas.json")
        with tempfile.TemporaryDirectory() as tmp:
            codigos[t] = emitir.main([t, "--carpeta", str(entorno.carpeta("adjuntos") / t), "--entradas", str(DESTINO / t / "entradas.json"),
                                      "--fecha", DIA.isoformat(), "--salida", tmp])
    print(json.dumps(codigos))
    return 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1])))
