"""Fuentes oficiales: lo que se descarga, se guarda en caché y se lee tal cual lo publica cada fuente (CLAUDE.md, regla 6).

- `sec`: SEC EDGAR (company_tickers, submissions, companyfacts; depósitos, hechos XBRL, calendario fiscal, portada del 10-K).
- `edgar`: trae al expediente los documentos que el analista no adjunta (10-K, 10-Q, proxy, Ex. 99.1…), impresos a PDF.
- `precio`: Nasdaq (cierre oficial, sesiones, cotización del día y consenso).
- `calendario`: Nasdaq (próxima presentación de resultados, dividendos y sorpresas frente al consenso).
- `posicionamiento`: Nasdaq (cadena de opciones, 13F, directivos y cortos) y la VI de Yahoo, excepción marcada.
- `tesoro`: Tesoro de EE. UU. (curva par diaria: el 10 años del WACC).
- `yahoo`: Yahoo Finance, solo para la volatilidad implícita.
"""
