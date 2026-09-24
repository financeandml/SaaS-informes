"""El formulario del analista (sección H y portada): una página local que rellena `posiciones/<TICKER>.json`.

    python -m tesis.formulario NFLX [--puerto 8765] [--sin-navegador]

Sirve en 127.0.0.1 una página estática (HTML, CSS y JS en `tesis/tablero/`, sin scripts en
línea, con CSP estricta) que carga el fichero de posición si existe —o la plantilla— y lo
guarda al pulsar «Guardar» tras validarlo con `posicion.validar`: nada se escribe a medias
y un error se devuelve campo a campo. El informe (`emitir.py`) toma ese fichero por defecto.

El servidor no toca nada más del proyecto: solo lee y escribe `posiciones/<TICKER>.json`.
Escucha solo en 127.0.0.1 y rechaza las escrituras que no vengan de su propia página (una web abierta en otra
pestaña puede lanzar un POST a 127.0.0.1 sin preflight con `text/plain`): exige `Content-Type: application/json`,
una cabecera propia y un `Origin`/`Host` locales.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional, Tuple

from . import posicion as posicion_mod

__all__ = ["Servidor", "servir", "main"]

TABLERO = Path(__file__).resolve().parent / "tablero"
RAIZ = Path(__file__).resolve().parents[1]
_TICKER = re.compile(r"^[A-Z0-9.\-]{1,10}$")
CSP = "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self'; form-action 'none'; base-uri 'none'; frame-ancestors 'none'"
_TIPOS = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8", ".js": "text/javascript; charset=utf-8"}


def ruta_posicion(ticker: str, carpeta: Optional[Path] = None) -> Path:
    if not _TICKER.match(ticker):
        raise ValueError(f"ticker no válido: {ticker!r}")
    return (carpeta or RAIZ / "posiciones") / f"{ticker}.json"


def cargar_o_plantilla(ticker: str, carpeta: Optional[Path] = None) -> dict:
    ruta = ruta_posicion(ticker, carpeta)
    if ruta.exists():
        return json.loads(ruta.read_text(encoding="utf-8"))
    return posicion_mod.plantilla()


class _Manejador(BaseHTTPRequestHandler):
    servidor: "Servidor"

    def log_message(self, formato, *args):  # silencio: la consola es del analista
        return

    def _responder(self, codigo: int, cuerpo: bytes, tipo: str) -> None:
        self.send_response(codigo)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(cuerpo)))
        self.send_header("Content-Security-Policy", CSP)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(cuerpo)

    def _json(self, codigo: int, datos: dict) -> None:
        self._responder(codigo, json.dumps(datos, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def do_GET(self) -> None:
        camino = self.path.split("?", 1)[0]
        if camino == "/":
            camino = "/formulario.html"
        if camino == "/api/posicion":
            self._json(200, {"ticker": self.servidor.ticker, "ruta": str(self.servidor.ruta), "existe": self.servidor.ruta.exists(),
                             "posicion": cargar_o_plantilla(self.servidor.ticker, self.servidor.carpeta)})
            return
        nombre = camino.lstrip("/")
        fichero = (TABLERO / nombre).resolve()
        # en Windows, unir una ruta absoluta («C:\…») descarta la base: el fichero resuelto tiene que vivir en la carpeta
        if "/" in nombre or "\\" in nombre or ":" in nombre or ".." in nombre or fichero.parent != TABLERO or fichero.suffix not in _TIPOS or not fichero.is_file():
            self._responder(404, b"no existe", "text/plain; charset=utf-8")
            return
        self._responder(200, fichero.read_bytes(), _TIPOS[fichero.suffix])

    def _es_propia(self) -> bool:
        """Solo la página servida por este mismo servidor puede escribir: tipo JSON, cabecera propia y origen local."""
        tipo = (self.headers.get("Content-Type") or "").split(";", 1)[0].strip().lower()
        if tipo != "application/json" or self.headers.get("X-Formulario") != "posicion":
            return False
        origen = self.headers.get("Origin")
        anfitrion = self.headers.get("Host") or ""
        return origen is None or origen == f"http://{anfitrion}" or origen in (f"http://127.0.0.1:{self.server.server_address[1]}", f"http://localhost:{self.server.server_address[1]}")

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
        if self.path.split("?", 1)[0] != "/api/posicion":
            self._tragar()
            self._responder(404, b"no existe", "text/plain; charset=utf-8")
            return
        if not self._es_propia():
            self._tragar()
            self._json(403, {"errores": {"": "la escritura solo se admite desde la propia página del formulario"}})
            return
        try:
            largo = int(self.headers.get("Content-Length", "0"))
            if largo > 2_000_000:
                raise ValueError("cuerpo demasiado grande")
            datos = json.loads(self.rfile.read(largo).decode("utf-8"))
        except (ValueError, json.JSONDecodeError) as e:
            self._json(400, {"errores": {"": f"JSON no válido: {e}"}})
            return
        errores = posicion_mod.validar(datos)
        if errores:
            self._json(400, {"errores": errores})
            return
        posicion_mod.guardar(datos, self.servidor.ruta)
        faltan = posicion_mod.cargar(self.servidor.ruta).faltan()
        self._json(200, {"guardado": str(self.servidor.ruta), "sin_rellenar": sorted(faltan)})


class Servidor(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, ticker: str, puerto: int = 8765, carpeta: Optional[Path] = None) -> None:
        self.ticker = ticker.upper()
        self.carpeta = carpeta
        self.ruta = ruta_posicion(self.ticker, carpeta)
        manejador = type("Manejador", (_Manejador,), {"servidor": self})
        super().__init__(("127.0.0.1", puerto), manejador)

    @property
    def direccion(self) -> str:
        return f"http://127.0.0.1:{self.server_address[1]}/"


def servir(ticker: str, puerto: int = 8765, carpeta: Optional[Path] = None, en_hilo: bool = False) -> Tuple[Servidor, Optional[threading.Thread]]:
    """Arranca el servidor; con `en_hilo`, en segundo plano (para pruebas) y devuelve el hilo."""
    servidor = Servidor(ticker, puerto, carpeta)
    hilo = None
    if en_hilo:
        hilo = threading.Thread(target=servidor.serve_forever, daemon=True)
        hilo.start()
    return servidor, hilo


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Formulario local del analista: posición, tesis y recomendación (sección H y portada).")
    ap.add_argument("ticker")
    ap.add_argument("--puerto", type=int, default=8765)
    ap.add_argument("--sin-navegador", action="store_true")
    args = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")       # la consola de Windows viene en cp1252 y no imprime «→»
    servidor, _ = servir(args.ticker.upper(), args.puerto)
    print(f"Formulario de {servidor.ticker} en {servidor.direccion} → guarda en {servidor.ruta} (Ctrl+C para parar)", flush=True)
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
