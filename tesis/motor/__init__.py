"""Motor de valoración (05): determinista, en Python puro y con pruebas. Entrada: hechos verificados + entradas del
analista (paso 7); salida: una `Valoracion` con cada cifra intermedia y su fórmula. Se redondea solo al imprimir."""

from .supuestos import Escenario, Parametros, leer
from .proyeccion import Proyeccion, proyectar
from .terminal import Terminal, terminal
from .puente import Puente, puente
from .escenarios import Resultado, Valoracion, valorar

__all__ = ["Escenario", "Parametros", "leer", "Proyeccion", "proyectar", "Terminal", "terminal", "Puente", "puente",
           "Resultado", "Valoracion", "valorar"]
