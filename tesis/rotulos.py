"""Rótulos en español para miembros XBRL, países y jurisdicciones (`config/traducciones.yaml`, 02 › Lenguaje).

Devuelve siempre (texto, traducido): lo que no se sabe traducir sale tal cual y marcado, para que la puerta de
calidad lo pida al analista en vez de imprimir inglés sin avisar.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Dict, Mapping, Optional, Tuple

__all__ = ["miembro", "jurisdiccion", "es_acronimo", "cargo"]

_RUTA = Path(__file__).resolve().parent.parent / "config" / "traducciones.yaml"


@lru_cache(maxsize=1)
def _datos() -> dict:
    import yaml
    return yaml.safe_load(_RUTA.read_text(encoding="utf-8"))


def es_acronimo(texto: str) -> bool:
    """QCT, QTL, EMEA, UCAN, IoT: sigla corta con al menos dos mayúsculas."""
    return bool(re.fullmatch(r"[A-Z][A-Za-z0-9&]{1,5}", texto)) and sum(c.isupper() for c in texto) >= 2


def _palabras(nombre: str) -> str:
    """«UnitedStatesAndCanada» → «United States And Canada»; respeta las siglas («IoTDevices» → «IoT Devices»)."""
    trozos = re.findall(r"[A-Z]{2,}(?=[A-Z][a-z]|$|\d)|[A-Z][a-z]+|[a-z]+|[A-Z]|\d+", nombre)
    frase = " ".join(trozos)
    return re.sub(r"\bI o T\b", "IoT", frase)


def _glosario(texto: str) -> Optional[str]:
    clave = " ".join(re.sub(r"[^a-z0-9 ]", " ", texto.lower()).split())
    return _datos()["glosario"].get(clave)


def miembro(qname: str, propios: Optional[Mapping[str, str]] = None,
            etiqueta_en: Optional[str] = None) -> Tuple[str, bool]:
    """El rótulo en español de un miembro («qcom:QctMember», «country:CN», «srt:AmericasMember»).

    Orden: el del analista; el de la taxonomía estándar; el rótulo del propio depósito (`etiqueta_en`, del linkbase de
    etiquetas: «QCT», «Handsets») si es una sigla o está en el glosario; el nombre del miembro partido en palabras.
    """
    if propios and qname in propios:
        return propios[qname], True
    d = _datos()
    if qname in d["miembros"]:
        return d["miembros"][qname], True
    prefijo, _, local = qname.partition(":")
    if prefijo == "country":
        return d["paises"].get(local, local), local in d["paises"]
    if prefijo == "stpr":
        return local, True
    nombre = local[:-6] if local.endswith("Member") else local
    candidatos = []
    if etiqueta_en:
        candidatos.append(etiqueta_en)
        sigla = re.match(r"^([A-Z][A-Za-z0-9&]{1,5})\s*\(", etiqueta_en)
        if sigla:
            candidatos.append(sigla.group(1))
    candidatos += [nombre, _palabras(nombre)]
    for c in candidatos:
        if es_acronimo(c):
            return c, True
        traducido = _glosario(c)
        if traducido:
            return traducido, True
    return (etiqueta_en or _palabras(nombre)), False


def jurisdiccion(texto: str) -> Tuple[str, bool]:
    """«Cayman Islands» → «Islas Caimán». Un estado de EE. UU. que se escribe igual se deja; lo desconocido, marcado."""
    limpio = " ".join(texto.replace("\xa0", " ").split()).strip(" .,;")
    d = _datos()["jurisdicciones"]
    if limpio in d:
        return d[limpio], True
    for ingles, espanol in d.items():
        if limpio.lower() == ingles.lower():
            return espanol, True
    return limpio, bool(re.fullmatch(r"[A-Z][a-z]+(?: [A-Z][a-z]+)?", limpio))


_INGLES = {"and", "of", "the", "for", "officer", "president", "vice", "chief", "executive", "senior", "former", "head"}


@lru_cache(maxsize=1)
def _patron_cargos():
    pares = sorted(_datos()["cargos"], key=lambda p: -len(p[0]))
    tabla = {ingles.lower(): espanol for ingles, espanol in pares}
    patron = re.compile(r"(?<![A-Za-z])(" + "|".join(re.escape(i) for i, _ in pares) + r")(?![A-Za-z])", re.I)
    return patron, tabla


_FEMENINO = {"director": "directora", "presidente": "presidenta", "vicepresidente": "vicepresidenta", "consejero": "consejera",
             "secretario": "secretaria", "tesorero": "tesorera", "interventor": "interventora", "fundador": "fundadora",
             "antiguo": "antigua", "jurídico": "jurídica", "financiero": "financiera", "ejecutivo": "ejecutiva",
             "delegado": "delegada", "designado": "designada", "interino": "interina"}


def cargo(texto: str, femenino: bool = False) -> Tuple[str, bool]:
    """«Executive Vice President, Chief Financial Officer and Chief Operating Officer» →
    «Vicepresidente ejecutivo, director financiero (CFO) y director de operaciones (COO)». Una sola pasada (lo ya
    traducido no se vuelve a traducir). (texto, completo): completo es False si queda inglés de cargo, para que el
    analista lo revise; los nombres propios (divisiones, productos) se quedan como están."""
    patron, tabla = _patron_cargos()
    salida = patron.sub(lambda m: tabla[m.group(1).lower()], " ".join(texto.split()))
    salida = re.sub(r"\band\b", "y", salida)
    salida = re.sub(r"\bof\b", "de", salida)
    restos = {w.lower() for w in re.findall(r"[A-Za-z]+", salida)} & _INGLES
    if femenino:
        salida = re.sub(r"\b(" + "|".join(_FEMENINO) + r")\b", lambda m: _FEMENINO[m.group(1)], salida)
    salida = salida[:1].upper() + salida[1:]
    return salida, not restos


SIN_TRADUCIR_BOLSA: set = set()        # rótulos de la bolsa sin traducción: aviso de la puerta de calidad (sin inglés en el cuerpo)


def bolsa(texto: str) -> str:
    """Un rótulo literal de la web de Nasdaq en español (`config/traducciones.yaml` › bolsa); los compuestos
    «Officer · Director» se traducen por partes. Sin traducción, el literal y queda anotado."""
    import re
    tabla = {k.lower(): v for k, v in (_datos().get("bolsa") or {}).items()}
    partes = [p.strip() for p in re.split(r"\s*[,/]\s*", str(texto or "")) if p.strip()]
    salida = []
    for p in partes or [str(texto or "")]:
        t = tabla.get(p.lower())
        if t is None:
            SIN_TRADUCIR_BOLSA.add(p)
        salida.append(t or p)
    return ", ".join(salida)


FALLOS: list = []                      # el detalle técnico de cada consulta fallida: a auditoria.json, nunca al cuerpo (regla 5)


def fallo(e: BaseException) -> str:
    """Por qué falló una consulta, dicho para el lector: sin URL, sin traza y sin el nombre de la excepción (el
    detalle queda en `FALLOS` para la auditoría de la emisión)."""
    FALLOS.append(f"{type(e).__name__}: {e}")
    causa = e.__cause__
    codigo = getattr(e, "code", None) or getattr(causa, "code", None)
    texto = f"{e} {getattr(e, 'reason', '')} {causa or ''}"
    if codigo == 429:
        return "la fuente limitó las consultas por exceso de peticiones"
    if isinstance(codigo, int):
        return f"la fuente devolvió el error {codigo}"
    if "sin respuesta guardada" in texto:
        return "sin conexión y sin copia guardada de la respuesta"
    if "timed out" in texto or isinstance(e, TimeoutError) or isinstance(causa, TimeoutError):
        return "la consulta superó el tiempo de espera"
    if isinstance(e, (ValueError, KeyError, TypeError, IndexError)):
        return "la respuesta no tiene el formato esperado"
    return "no hubo conexión con la fuente"
