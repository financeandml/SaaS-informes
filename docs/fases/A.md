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

## Estado (30/09/2026)
- A0, A1 y A4 ☑ (antes del 29/09).
- A5 ☑ motor (+ F12, `docs/fases/F12.md`): saldo anterior del ejercicio en ROE/ROA [13, 43]; ROIC con la definición del
  glosario [14]; CAGR de cinco intervalos [15, 44]; FCFF desde el balance del puente [16]; SBC según la decisión 1, con
  «dilución» implementada (05 §3) [17, 75]; cierres de 52/53 semanas [18, 60]; BPA del 4T sin dividendo preferente [19, 53];
  «otros ingresos» que cuadran [20]; dos ejes geográficos sin sumar [21]; ratios con base negativa N/A [22]; aviso de
  partidas no recurrentes en el TTM (`datos/no_recurrentes.py`, `config/no_recurrentes.yaml`) [23].
  Contador: `pytest -m auditoria` 34 de 78 sin marca (44 abiertos). Informe de control QCOM: cambian 11–18, 20, 23, 25,
  28 y 36 (ROIC, SBC, periodo parcial, CAGR).
- A2 ☑ (02/10): escala por fila cuando la cabecera exceptúa las acciones [3]; cada tabla de una página con su cabecera
  de columnas y la línea de un estado con concepto propio de la compañía (XBRL del depósito) como otro alcance del
  us-gaap [4]; lo leído en un documento anterior a un split, reexpresado antes de contrastar [5]; guía y real en la base
  de acciones de hoy [49]. AAPL pasa de 79 a 9 bloqueos. Contador: 38 de 78 sin marca (40 abiertos). Informe de control
  QCOM: sin cambios de cifras (solo la hora de consulta en 31 y 33–35).
- A3 ☑ salvo [56] (02/10): política de dividendo en tres estados (`calendario.politica_dividendo`: bolsa → SEC → cero
  declarado del 10-K → sin dato) [6, 52]; DPA vigente = último pago × pagos en doce meses [24]; cero declarado también
  en los trimestres que cubre un 10-Q [48]; `RepaymentsOfOtherLongTermDebt` en la amortización de deuda [59]; el motivo
  de la bolsa cuando no cubre el valor, en español [67]. Y, de A7, la lista de comprobación cuenta los bloqueos de la
  puerta ya calculada [29]. Bloqueos: AAPL 6, NFLX 3, ORCL 13, QCOM 4. Contador: 45 de 78 sin marca (33 abiertos).
  Informe de control QCOM: 10 (amortización de deuda), V_h −0,06 USD por el DPA vigente (12–15, 20, 25, 28) y 38.
- [56] abierto: el interés en corto de FINRA (decisión 2) necesita su API, que la red de la sesión del 02/10 no
  alcanza (`api.finra.org` denegado por el proxy); sin una respuesta real que congelar no se escribe el cliente a ciegas.
- A6 ☑ (02/10; 25, 27, 28, 70, 71 y 74 ya estaban): presentaciones y transcripciones de resultados del emisor citables
  por su trimestre [10]; epígrafes del Item 1A en negrita dentro de un párrafo redondo (ORCL: 1 → 34) [26, 57];
  llamadas a nota «(3)(4)» en la Summary Compensation Table (AAPL 2025) [46]; el texto alternativo «LOGO» de las imágenes
  de la proxy fuera de cargos y fichas [50]; rótulo legible de los adjuntos en la web [68]. Y, de A7, el recuento de QCOM
  [61]. Contador: 52 de 78 sin marca (26 abiertos). Informe de control QCOM: sin cambios de cifras.
- A8 ☑ (03/10): folio impreso en un pie con separadores («Apple Inc. | 2025 Form 10-K | 8») [11]; los doce meses de
  rentabilidad y múltiplos con el trimestre fiscal («2T FY26»), también en las identidades que no cuadran [12]; marcas que
  empiezan en minúscula («iPhone») y el código M del Form 4 como «Ejercicio o conversión de derivados» (RSU) [47].
- A7 ☑ salvo lo de A9–A11 (03/10): identidades contables que no cuadran listadas en el apartado 39, sin bloquear [30];
  catalizadores «AAAA-Tn» fechados al cierre de su trimestre natural [31]; SOTP sin casilla del analista no se le
  atribuye [32]; propuesta confirmada sin «propuesta» [33]; columna «Actual» de los KPI desde su hecho
  (`checklist.kpi_hechos`) [34]; SOM por defecto sin texto técnico [35]; un grupo del escenario no es un disparador [36];
  frase de retribución sin dividendos para quien no los paga [37]; RONIC en el cuadro de escenarios [38]; hoja «Reverse
  DCF» con fórmulas y los tres valores terminales en cada escenario [39]; SOTP (`motor/sotp.py`, apartado 19) [40];
  `emitir.py` 0 emitido · 2 borrador · 1 error [41]; rúbrica coherente con el SOTP [76]. Contador: 68 de 78 sin marca
  (10 abiertos: 9, 51, 55, 56, 62, 63, 64, 65, 73, 74).
- Siguiente: A9 (mercado secundario: 9, 51, 55, 62), A11 (avisos de las entradas: 63, 64, 65, 73) y [74] gobierno manual.

