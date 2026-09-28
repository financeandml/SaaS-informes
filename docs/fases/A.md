# A · Corrección de la auditoría del 27/09/2026 (78 fallos)
Origen: emisión de prueba de AAPL, NFLX, ORCL y QCOM con entradas de analista senior (27/09/2026) y auditoría palabra por
palabra y número por número por agentes que no intervinieron. Lista numerada [1–78] en la conversación del 28/09/2026; cada
número tiene su prueba en `tests/prueba_auditoria_27_09.py` (marca `auditoria`), que empieza en rojo (xfail estricto).
Protocolo: el de siempre (`00_protocolo.md`); cada parte se cierra con resumen breve y se sigue salvo decisión.

## Decisiones del analista (28/09/2026)
1. SBC con «coste de caja»: el margen EBIT GAAP ya la incluye; el FCFF no la resta y la fila queda informativa. Con
   «dilución», se suma al EBIT y crecen las acciones. La spec 05 §3 lo dirá así.
2. FINRA entra en `config/fuentes.yaml` como fuente oficial (organismo autorregulador) del interés en corto fuera de Nasdaq.
3. Valores negociables a largo plazo en el puente: propuesta automática del sistema, confirmada por el analista.
4. `emitir.py`: 0 emitido · 2 borrador con bloqueos · 1 error.
5. SOTP: se implementa (`motor/sotp.py`).
6. ERP de referencia: delegada; Damodaran, implied ERP a 01/09/2026 = 4,14 %, comprobada el 28/09/2026 (`config/erp.yaml`).
7. F12 se cierra dentro de la Parte 5.

## Partes (orden de ejecución)
| Orden | Parte | Fallos | Depende de |
|---|---|---|---|
| 1 | A0 · Banco de pruebas: fixtures congelados de las cuatro emisiones y una prueba por fallo | 78 | — |
| 2 | A1 · Precio, sesión y volumen desde el histórico oficial | 1, 2, 42, 66, 9 (mercado) | A0 |
| 3 | A4 · Deuda (papel comercial, valores a largo plazo), acciones y dilución: una definición | 7, 8, 45, 54, 58, 69 | A0 |
| 4 | A5 · Motor: saldos de rentabilidad, ROIC, CAGR, trimestre de caja, SBC, cierres 52/53, preferentes, otros ingresos, geografías, ratios, no recurrentes (+ F12) | 13–24, 43, 44, 53, 60, 75 | A1, A4 |
| 5 | A2 · Extracción y contraste: escala por fila, columna por fecha, split, alcance de intangibles | 3, 4, 5, 49 | A0 |
| 6 | A3 · Tres estados: fuentes que no cubren, dividendos, ceros publicados, FINRA | 6, 24, 48, 52, 56, 59, 67 | A2 |
| 7 | A6 · Reconocimiento documental: proxy, Exhibit 21, Item 1A, fundación, guía en texto, llamadas y presentaciones citables, gobierno manual | 10, 25–28, 46, 50, 57, 68, 70, 71, 74 | A2 |
| 8 | A8 · Periodos fiscales y folios impresos | 11, 12, 47 | A2, A6 |
| 9 | A7 · Puerta de calidad, recuentos, KPI, SOM, párrafo factual, supuestos visibles, Excel, SOTP, código de salida | 29–41, 61 | A3–A6 |
| 10 | A9 · Mercado secundario: caché EDGAR, consenso, 13G/13F, Form 4 | 9, 51, 55, 62 | A1 |
| 11 | A10 · Texto y formato | 37–41 (bajos), 47, 51 | A7 |
| 12 | A11 · Avisos sobre las entradas (tramo 5: avisan, no bloquean) | 63, 64, 65, 73 | A6, A7 |
| 13 | A12 · Cierre: ERP, rúbrica, reemisión y auditoría nueva | 72, 76, 77 | todas |

Aceptación final: `pytest -m auditoria` 78 de 78; los cuatro informes sin bloqueos del programa; una auditoría nueva no
reproduce ninguno; batería completa y regresiones en verde.
