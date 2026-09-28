"""Dónde está cada cosa del repositorio, relativo al paquete: la configuración, los specs, las plantillas y la raíz.

No se usa `entorno.RAIZ` para esto: las pruebas la desvían a sus fixtures y la configuración sigue siendo la del
repositorio.
"""

from pathlib import Path

__all__ = ["PAQUETE", "REPO", "CONFIG", "SPEC", "MAQUETA", "leer_yaml"]

PAQUETE = Path(__file__).resolve().parent            # tesis/
REPO = PAQUETE.parent
CONFIG = REPO / "config"
SPEC = REPO / "docs" / "spec"
MAQUETA = PAQUETE / "plantillas" / "maqueta"


_YAML: dict = {}


def leer_yaml(ruta: Path) -> dict:
    """Un YAML de configuración, leído una vez mientras no cambie en disco (se invalida por la fecha de modificación).

    El motor consulta los valores de partida y los paquetes muchas veces por informe: releer y analizar el YAML en cada
    consulta duplicaba el tiempo de la batería. Devuelve una copia, para que quien la modifique no cambie la de todos."""
    import copy
    import yaml
    ruta = Path(ruta)
    clave = (str(ruta), ruta.stat().st_mtime_ns)
    if clave not in _YAML:
        _YAML[clave] = yaml.safe_load(ruta.read_text(encoding="utf-8")) or {}
    return copy.deepcopy(_YAML[clave])
