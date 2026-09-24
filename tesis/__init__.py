"""Tesis de inversión: de los adjuntos del analista y de la SEC al informe.

Una tubería de línea de órdenes, sin web ni base de datos: cada módulo hace una
cosa y deja un fichero que el siguiente lee. El orden es el del flujo:

    expediente  →  qué ha adjuntado el analista, clasificado y en orden cronológico
    sec         →  lo que la SEC tiene depositado del emisor (hechos XBRL, formularios)
    extractor   →  cada número de cada adjunto, con su rótulo, periodo, página y rectángulo
    contraste   →  campo × periodo: SEC frente a adjunto, con glifo y sin elegir por su cuenta
    recortes    →  la región exacta de la página de la que salió cada tabla, a PNG
    informe     →  las once secciones como hechos, y el HTML/PDF con la retícula de casa

Lo que atraviesa toda la tubería es `hechos.Hecho`: ninguna cifra viaja suelta.
"""
