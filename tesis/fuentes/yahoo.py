"""Yahoo Finance como excepción: solo para lo que la bolsa no publica (la volatilidad implícita).

Decisión del analista (17/09/2026): la API de datos es Nasdaq; Yahoo Finance entra
«excepcionalmente y de forma provisional» cuando un dato no se puede obtener de la bolsa.
Es un agregador sin licencia declarada, así que todo lo que venga de aquí se rotula
«Yahoo Finance (agregador, no oficial; excepción autorizada por el analista)» con
certeza media, y donde la bolsa publique el mismo hecho (interés abierto por
vencimiento) se contrasta contra ella.

Yahoo exige una cookie y un «crumb» para sus API de datos: se piden una vez por
sesión y se reutilizan. No se envía ningún dato del analista en las peticiones.
"""

from __future__ import annotations

import http.cookiejar
import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from typing import Dict, Optional, Tuple

__all__ = ["FUENTE", "Cliente", "cliente"]

FUENTE = "Yahoo Finance (agregador, no oficial; excepción autorizada por el analista)"
_CABECERAS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128.0 Safari/537.36",
              "Accept": "*/*", "Accept-Language": "en-US,en;q=0.9"}


class Cliente:
    def __init__(self) -> None:
        self._jar = http.cookiejar.CookieJar()
        self._abrir = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self._jar))
        self._crumb: Optional[str] = None
        self.crudos: Dict[str, Tuple[str, datetime]] = {}     # url → (cuerpo literal, hora): la evidencia

    def _texto(self, url: str) -> str:
        r = self._abrir.open(urllib.request.Request(url, headers=_CABECERAS), timeout=30)
        return r.read().decode("utf-8")

    def crumb(self) -> str:
        if self._crumb is None:
            try:
                self._texto("https://fc.yahoo.com")          # solo para recibir la cookie; responde 404 a propósito
            except urllib.error.HTTPError:
                pass
            self._crumb = self._texto("https://query2.finance.yahoo.com/v1/test/getcrumb").strip()
        return self._crumb

    def json(self, url: str) -> dict:
        """Con la misma caché por URL y día que la bolsa (`precio.CACHE_BOLSA`, `precio.SOLO_CACHE`): la respuesta queda
        guardada entera, con su hora y su huella, y las pruebas no salen a la red. El crumb no forma parte de la clave."""
        import gzip
        import hashlib
        from datetime import date
        from . import precio
        carpeta, ruta = precio._ruta_bolsa(url, date.today())
        if not ruta.exists() and precio.SOLO_CACHE:
            previas = sorted(carpeta.glob(ruta.name.rsplit("__", 1)[0] + "__*.json.gz"))
            if not previas:
                raise urllib.error.URLError(f"sin respuesta guardada de {url}")
            ruta = previas[-1]
        if ruta.exists():
            with gzip.open(ruta, "rt", encoding="utf-8") as f:
                sobre = json.load(f)
            self.crudos[url] = (sobre["cuerpo"], datetime.fromisoformat(sobre["obtenido"]))
            return json.loads(sobre["cuerpo"])
        separador = "&" if "?" in url else "?"
        cuerpo = self._texto(f"{url}{separador}crumb={urllib.parse.quote(self.crumb())}")
        ahora = datetime.now()
        self.crudos[url] = (cuerpo, ahora)
        try:
            carpeta.mkdir(parents=True, exist_ok=True)
            with gzip.open(ruta, "wt", encoding="utf-8") as f:
                json.dump({"url": url, "obtenido": ahora.isoformat(timespec="seconds"),
                           "sha256": hashlib.sha256(cuerpo.encode("utf-8")).hexdigest(), "cuerpo": cuerpo}, f, ensure_ascii=False)
        except OSError:
            pass
        return json.loads(cuerpo)


_CLIENTE: Optional[Cliente] = None


def cliente() -> Cliente:
    global _CLIENTE
    if _CLIENTE is None:
        _CLIENTE = Cliente()
    return _CLIENTE
