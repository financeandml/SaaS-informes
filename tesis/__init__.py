"""Tesis de inversión de Warrants & Co.: de la SEC, Nasdaq, el Tesoro y las entradas del analista al informe de 39
apartados, sin IA en tiempo de ejecución.

Subpaquetes, en el orden del flujo:

    fuentes       →  fuentes oficiales: EDGAR, Nasdaq, Tesoro y Yahoo (solo VI); descarga, caché y lectura en bruto
    datos         →  el Hecho, el catálogo de campos y lo que se lee de los documentos del expediente
    verificacion  →  contraste con la SEC, auditoría de identidades y doble comprobación de lo impreso
    entradas      →  lo del analista: esquema 04, carga, comprobaciones por paso, asistente y propuestas (06 §1)
    motor         →  la valoración (05): supuestos, WACC, proyección, puente, escenarios, sensibilidad, múltiplos, sector
    plantillas    →  el informe como datos: índice, partes A–I, frases, cuadros, gráficos y la maqueta
    qa            →  la puerta de calidad (06 §3) y el linter de los textos del analista (06 §2)
    render        →  HTML autocontenido y PDF paginado con Chromium (06 §4)
    web           →  el SaaS local y sus páginas
    heredado      →  el camino anterior al asistente, aparte hasta que F9 lo retire

Transversales: `entorno` (configuración y carpetas de datos), `rutas` (dónde está cada cosa del repositorio),
`umbrales` (`config/umbrales.yaml`), `formato` (cifras y fechas es-ES; la celda que se imprime) y `rotulos`
(traducciones y fallos de red en español). Lo que atraviesa toda la tubería es `datos.hechos.Hecho`: ninguna cifra
viaja suelta.
"""
