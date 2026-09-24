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
        separador = "&" if "?" in url else "?"
        cuerpo = self._texto(f"{url}{separador}crumb={urllib.parse.quote(self.crumb())}")
        self.crudos[url] = (cuerpo, datetime.now())
        return json.loads(cuerpo)


_CLIENTE: Optional[Cliente] = None


def cliente() -> Cliente:
    global _CLIENTE
    if _CLIENTE is None:
        _CLIENTE = Cliente()
    return _CLIENTE
