"""Dónde está cada cosa del repositorio, relativo al paquete: la configuración, los specs, las plantillas y la raíz.

No se usa `entorno.RAIZ` para esto: las pruebas la desvían a sus fixtures y la configuración sigue siendo la del
repositorio.
"""

from pathlib import Path

__all__ = ["PAQUETE", "REPO", "CONFIG", "SPEC", "MAQUETA"]

PAQUETE = Path(__file__).resolve().parent            # tesis/
REPO = PAQUETE.parent
CONFIG = REPO / "config"
SPEC = REPO / "docs" / "spec"
MAQUETA = PAQUETE / "plantillas" / "maqueta"
