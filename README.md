# Tesis de inversión — del expediente del analista y la SEC al informe

Una tubería de línea de órdenes: el analista adjunta los documentos de una empresa
(10-K, 10-Q, proxy, carta a accionistas, transcripción, cuentas de la web), su libro
de valoración (Excel) y su fichero de posición; el sistema ordena los documentos
cronológicamente, extrae cada cifra con su página y su rectángulo, la contrasta contra
la SEC y produce el informe con el índice completo A–I (39 apartados, el último de
documentación complementaria): las cuentas de los estados bajo sus cuadros, el resto de
recortes y respuestas literales de las fuentes al final, retratos del equipo directivo
sacados de la proxy, el DCF del analista leído y cuadrado con el dato oficial, los riesgos
del Item 1A literales, las previsiones de la compañía frente a lo publicado leídas de las
cartas depositadas en EDGAR, y una doble comprobación de cada cifra impresa antes de
emitir. El analista rellena su parte (sección H, recomendación, precio objetivo) en un
formulario local. Sin base de datos, sin Docker: eso va después.

```
python -m tesis.saas                                              # el SaaS local en http://127.0.0.1:8770/ (abre el navegador):
                                                                  #   1 ticker + expediente · 2 DCF · 3 analista · 4 informe (HTML y PDF)
python emitir.py NFLX --adjuntos 10k.pdf 10q_1.pdf 10q_2.pdf proxy.pdf carta.pdf call.pdf web.pdf web.xlsx \
       --narrativa narrativas/NFLX_2026-09-17.json --dcf Modelo_DCF_NFLX.xlsx        # posiciones/NFLX.json se toma solo si existe
python emitir.py NFLX --carpeta adjuntos/NFLX --fecha 2026-09-16 --decisiones decisiones_nflx.json --redactar
python -m tesis.formulario NFLX                                    # formulario del analista → posiciones/NFLX.json
python -m unittest discover -s tests -p "prueba_*.py" -t .        # 176 pruebas, ~65 s
```

Antes hace falta `.env` (copiar `.env.ejemplo`): `WC_SEC_CONTACTO` con nombre y correo,
que la SEC exige en el `User-Agent` (solo se envía a EDGAR y solo cuando algo no está ya en
`cache_sec/`, fuera del repo), y `WC_PRECIO_FUENTE=nasdaq` para el precio, la capitalización,
el rango de 52 semanas, el volumen, el margen de seguridad frente a la cotización oficial, la
sección F, los comparables, los múltiplos TTM y la fecha de resultados. Para `--redactar`,
`ANTHROPIC_API_KEY` (entorno o `.env`); el SDK `anthropic` está instalado (18/09/2026).

Fuentes, por este orden y sin otras: documentos oficiales adjuntos, SEC EDGAR, la bolsa
(Nasdaq) y, para completar o contrastar lo que ninguna de las dos publica, Yahoo Finance.

Deja en `salida/`: el PDF, el HTML autocontenido (sin JavaScript, CSP sin scripts), la
carpeta de recortes PNG y `*.contraste.txt`, el cuaderno del generador con cada campo ×
periodo y su resultado.

## La tubería (en `tesis/`)

| Módulo | Qué hace |
|---|---|
| `hechos.py` | `Hecho`: valor · estado (valor / cero / N/A) · capa (H, Hd, S, D) · origen (documento, formulario, página, rectángulo, concepto XBRL) · certeza · fórmula · entradas · glifo de contraste. Un N/A sin motivo o un derivado sin fórmula no se pueden construir. |
| `campos.py` | El catálogo: cada campo del índice con su rótulo, sus conceptos XBRL en orden, sus rótulos de fila, el contexto que exige o excluye, y los derivados con su fórmula. |
| `sec.py` | EDGAR: `company_tickers`, `submissions`, `companyfacts`. Reglas: solo 10-K/10-Q valen; último presentado por periodo con nota de reexpresión; sinónimo por periodo; 4T = FY − 9M como derivado; splits como hecho SEC y reexpresión de lo anterior como derivado con fórmula. |
| `expediente.py` | Clasifica cada adjunto por lo que dice de sí mismo (portada, fecha de periodo, fecha de firma), lo ordena cronológicamente, deduplica por huella y lo cruza con EDGAR (número de acceso o fecha de periodo): avisa si hay un formulario más reciente que no está. |
| `extractor.py` | Texto con coordenadas (carácter a carácter con la API cruda de pdfium), escala de la página, cabeceras de columna repartidas por posición, filas con su cabecera de bloque, y candidatos con rectángulo. Lee también XLSX (referencia por celda) y PDF en configuración regional española. |
| `contraste.py` | Campo × periodo: SEC frente a adjuntos con la tolerancia del documento; ✓ ≠ ◐ ◑ — ∑; pista de split; cero declarado por texto (dividendos); decisiones del analista desde JSON. Una ≠ sin decidir bloquea la emisión. |
| `recortes.py` | La región de la página con las filas confirmadas, ampliada al título del estado, a PNG con huella; pie con fichero, página, formulario y fecha. Además, `recortar_lineas` (la región que contiene unas anclas de texto: la prueba visual de una frase o de una tabla de texto) y `extraer_imagen` (una imagen incrustada, tal cual: los retratos de la proxy). |
| `derivados.py` | Márgenes, EBITDA, deuda neta, FCF, ROE/ROA/ROIC, cobertura, pay-out: con fórmula impresa y N/A si falta una entrada. |
| `ficha.py` · `gobierno.py` · `guidance.py` · `regiones.py` | Texto de los formularios con página: portada del 10-K, empleados, auditor; proxy (accionistas, ejecutivos con retrato y trayectoria literal, consejo con quién no se presenta a la reelección, retribución), Exhibit 21; objetivos de la compañía (carta) y frases de la call; ingresos por región (nota del 10-K/10-Q y hoja regional) con la comprobación suma = total. |
| `riesgos.py` | Apartado 30: los epígrafes del Item 1A del 10-K leídos por su tipografía (negrita, carácter a carácter), literales y con página; familia (regulatorio · financiero · competitivo · ejecución) como inferencia con motivo y certeza; «superado» cuando un 10-Q posterior da por terminada la operación a la que se refieren. |
| `historial.py` · `cartas.py` | Apartado 32: la previsión de la compañía frente a lo publicado, trimestre a trimestre, leída de las cartas a accionistas depositadas en EDGAR (Exhibit 99.1 de cada 8-K de resultados, 9 cartas: la columna «Forecast» de cada una frente a la cifra de la siguiente, con el BPA previo al split dividido por el factor), la serie consenso · publicado · sorpresa de la bolsa, la tabla de la portada de la transcripción, y las frases de la carta sobre su propia previsión; cada «real» cuadrado con la sección C. |
| `dcf.py` · `multiplos.py` | Sección D: el libro Excel del analista leído por rótulos (supuestos, tres escenarios, sensibilidad, reverse, resumen), cada cifra con hoja!celda y si es fórmula o valor tecleado; si el libro llegó guardado sin recalcular, se recalcula una copia con el Excel de la máquina (el original no se toca) y el informe lo dice. `cuadrar` aplica la regla 9 al modelo: cada entrada que afirma ser un hecho frente al dato oficial más reciente; cuando difieren, rige el oficial en lo que el informe calcula y la nota explica la diferencia (la deuda del libro coincide con la «deuda total» del agregador, que incluye arrendamientos). `multiplos.py`: PER, EV/EBITDA, EV/Ventas, P/FCF y PEG sobre los cuatro últimos trimestres de la SEC y la cotización oficial, y ROE/ROA TTM con la definición del 10-K, cada uno cuadrado con lo que publica el agregador. |
| `saas.py` · `tablero/inicio.html`, `dcf.html`, `informe.html`, `saas.js` | El SaaS local en cuatro pasos sobre 127.0.0.1. Buscador de tickers sobre `company_tickers.json`; al elegir uno se cargan emisor y hechos XBRL en segundo plano; los adjuntos van a `adjuntos/<TICKER>/`, se clasifican con `expediente.cargar`, se ordenan por fecha, se cruzan con EDGAR y se contrastan con la SEC; el libro a `dcf/<TICKER>.xlsx`; la posición a `posiciones/`; la emisión lanza `emitir.py -u` como proceso aparte y sirve `salida/<TICKER>/`. Word (.docx) se acepta solo para ordenar el expediente. Sin `ANTHROPIC_API_KEY` no se pide la narrativa: el informe sale igual, con los apartados 2 y 3 en N/A y su motivo. |
| `posicion.py` · `formulario.py` · `tablero/` | Sección H, recomendación y precio objetivo de la portada: el fichero JSON del analista (`posiciones/<TICKER>.json`), que rellena en un formulario local (`python -m tesis.formulario TICKER`: servidor en 127.0.0.1, página sin scripts en línea con CSP estricta, bilingüe, tema claro y oscuro; valida campo a campo y no guarda nada a medias; rechaza escrituras que no vengan de su propia página). Lo que falte sale N/A con motivo. |
| `posicionamiento.py` · `yahoo.py` | Sección F con la API de la bolsa (Nasdaq, decisión del analista): cadena de opciones agregada por vencimiento con put/call ∑, posicionamiento institucional (13F) con la fecha de cada 13F, operaciones de insiders (Form 4) y short interest (FINRA) desde el último split. La volatilidad implícita, que la bolsa no publica, entra por Yahoo Finance como excepción autorizada (`yahoo.py`, cookie + crumb): IV ATM y fuera del dinero por vencimiento, sesgo ∑ y el interés abierto del agregador cuadrado con el de la bolsa. Cada respuesta se guarda entera y se pinta como evidencia (`recortes.volcado_api`). |
| `comparables.py` | Apartado 22, dos clasificaciones oficiales: los valores de la misma industria que la bolsa asigna a la compañía (screener de Nasdaq; Netflix cae en «Consumer Electronics/Video Chains» con Best Buy e iQIYI) y los emisores del mismo código SIC según la SEC (7841, con iQIYI y Cineverse), con capitalización de la bolsa y cuentas anuales de companyfacts → P/Ventas y PER, solo con cuentas en USD. Ninguna de las dos fuentes publica competidores: publican clasificaciones, y el informe lo dice. |
| `mercado_objetivo.py` | Apartado 21: las cifras de mercado que la compañía declara en sus documentos oficiales (hogares e ingresos direccionables, penetración, cuota de visionado, audiencia, suscripciones), literales con página, clasificadas en TAM/SAM/SOM por el sistema con su motivo. |
| `secciones.py` · `agregador.py` · `calendario.py` | Los cuadros de D–I y la evidencia visual de cada apartado (un recorte por página citada, una sola vez por imagen). `agregador.py`: lo que Yahoo Finance publica y ni la SEC ni la bolsa dan como cifra (ROE/ROA TTM, deuda total, EV/EBITDA, PEG, fecha de resultados). `calendario.py`: la próxima presentación de resultados según la bolsa (fecha «esperada» de su proveedor), cuadrada con la del agregador. |
| `precio.py` · `entorno.py` | Cotización del día de emisión desde la bolsa (`nasdaq`), un proveedor licenciado (`polygon`) o, solo como último recurso y rotulado «no oficial», Yahoo. Sin configurar: N/A. De Nasdaq se toman además la ficha del valor (último cruce con hora y estado de la sesión, volumen, rango de 52 semanas, cierre anterior, capitalización publicada, «1 Year Target») y el histórico de cierres, con dos contrastes: el «cierre anterior» de la ficha frente al histórico de la misma bolsa, y el precio que el analista tecleó en su libro frente al cierre oficial de esa fecha. `entorno.py` lee las claves del entorno o de `.env`. |
| `narrativa.py` | Apartados 2, 3, 21–23 y 31. El dossier (páginas relevantes de cada adjunto con su clave y número, más los hechos con su clave) es determinista; el redactor (Claude Opus 5 con salida sujeta al esquema JSON de la narrativa y un extracto de la narrativa aprobada de Netflix como muestra de estilo, o un JSON ya escrito) propone frases con apoyos {documento, página, ancla literal} y claves de hechos; `verificar` retira toda frase cuyo ancla no esté en la página o cuya cifra no sea un hecho contrastado ni esté escrita en la página citada; `redactar_verificada` devuelve los reparos al modelo para que corrija (dos rondas) y se queda con la ronda con menos retiradas. Lo retirado va al apéndice con su motivo. |
| `revision.py` | La doble comprobación antes de emitir: cada celda que viene de un hecho se vuelve a formatear desde el hecho con un formateador propio; cada celda del libro se relee del Excel; cada cuadro se busca en el HTML y sus celdas deben ser exactamente las del cuadro. Un desacuerdo detiene la emisión. |
| `informe.py` · `formato.py` · `graficos.py` · `maqueta/` · `render.py` · `imprimir.py` | El índice completo (A–I, con F penúltima por decisión del analista y numeración por orden de impresión, también la de los cuadros: D, E, G, H, F) como cuadros numerados al pedirlos; cifras en convención española; SVG de matplotlib con **paleta corporativa propia** (marino para la serie principal, ocre para la medida secundaria, escala de un solo tono para los repartos; el granate de la maqueta no entra en los gráficos; una prueba lo afirma) y sin eje doble: la línea va en un panel encima de las barras; HTML por Jinja2 e impresión con el Chromium de Playwright en un proceso aparte, con cabecera y pie por página. La maqueta no deja títulos ni rótulos de cuadro huérfanos al pie de página, imprime el índice en una página a dos columnas, limita a media página los recortes de estados (dos por página) y un cuadro corto no se parte. |

## Resultado sobre el expediente de Netflix (16/09/2026)

203 celdas confirmadas ✓ · 20 derivadas ∑ (4T25 = FY − 9M, cuadran con el XLSX) · 0
discrepantes · 105 solo SEC ◐ (ejercicios 2021–2023, que el 10-K adjunto no cubre) · 16
solo documento ◑ · 36 huecos (fondo de comercio, intangibles, contenido 2021–2023…).
11 recortes de evidencia. Las cuatro discrepancias iniciales (BPA y acciones del 3T25,
10-Q previo al split 10:1 del 14/11/2025) se resuelven como derivados con fórmula porque
el split es un hecho SEC.

Narrativa (17/09/2026): 42 frases —4 párrafos del resumen y 5 pilares con su riesgo del
Item 1A— citando 10-K 2025, 10-Q 2T26, Proxy 2026, Carta 2T26 y Call 2T26; 0 reparos, 0
frases retiradas. Entre lo que dice y un lector apresurado no vería: el beneficio neto
del 1T26 (5.283 M USD) lleva dentro los 2.800 M USD de la indemnización de Warner Bros.
Discovery, y el FCF del 2T26 cayó por los impuestos de esa misma indemnización.

Cosas que la tubería cazó y un lector no habría visto: la DEF 14A redondea el beneficio
neto a millones y ganaba a «último presentado»; «Revenue» bajo «UCAN» no es el ingreso
total; la nota de ingresos por región declara la escala 17 líneas más abajo; en 2023 las
regiones no suman el total porque aún había ingresos por DVD (82.839 miles), y el
informe lo declara.

## Qué hay en cada sección del informe de Netflix (21/09/2026, 53 páginas)

Decisiones de Sergio del 18/09/2026, ya en el informe: los números se imprimen limpios (sin
glifos de contraste, capas ni marcas de derivado: el contraste, la fuente y la fórmula de cada
celda van al pasar el ratón en el HTML y al apéndice de datos complementarios); la página «en
una página» desaparece y sus gráficos pasan a la cabecera de la sección C; el índice enlaza con
cada apartado (también en el PDF); toda la evidencia documental va al apartado final salvo las
cuentas de los estados, que siguen bajo sus cuadros; sweeps y dark pool quedan fuera del índice;
el 37 sigue pendiente.

- **A–C (1–11)**: como antes, más un bloque de evidencia bajo cada apartado: 84 recortes
  de texto de las páginas citadas, 11 recortes de estados, 18 retratos (5 ejecutivos con
  su trayectoria literal y 13 consejeros; Reed Hastings rotulado «no se presenta a la
  reelección» porque lo dice la proxy). La ficha trae la fundación (nota 1, pág. 47 del
  10-K), las acciones de la portada más reciente (10-Q, 4.164 mln a 30/06/2026) y, con
  `WC_PRECIO_FUENTE=nasdaq`, el último precio con su hora y el estado de la sesión, el
  cierre anterior cuadrado con el histórico, la capitalización (∑ precio × acciones, ✓
  frente a la que publica Nasdaq), el rango de 52 semanas y el volumen. Las frases de la
  call del apartado 7 llevan quién las dijo (CFO, co-CEOs) y nunca son preguntas.
- **D (12–20)**: del libro `Modelo_DCF_NFLX_Warrants_Co_2026-09-15.xlsx` (llegó guardado sin
  recalcular: 522 fórmulas sin valor; el informe imprime una copia recalculada con el Excel de la
  máquina y lo dice), cada cifra con su celda. El cuadre con el dato oficial confirma ingresos,
  margen, caja, acciones en circulación y el precio que el analista tecleó (80,32 = cierre del
  14/09/2026), y resuelve las dos diferencias: la deuda del libro (16.655) es la «deuda total» del
  agregador, que incluye arrendamientos, frente a la deuda financiera de la SEC (14.309), y las
  acciones diluidas (4.200 frente a 4.261) son una estimación propia del analista que el libro
  declara; en ambas rige el dato oficial en lo que el informe calcula. El apartado 17 añade los
  múltiplos TTM sobre la SEC y la cotización oficial (PER 22,6x, EV/EBITDA 20,6x ✓ agregador,
  EV/Ventas 6,3x, P/FCF 26,8x, PEG 0,8x sobre el crecimiento anual del BPA; el PEG del agregador,
  1,2x, es otra definición y se imprime al lado). SOTP no aplica y se cita por qué. El apartado 20
  añade el recorrido de cada referencia sobre la cotización oficial y el consenso de la bolsa.
- **E (21–23)** y **G.31**: redactados por el sistema desde los adjuntos con la misma
  verificación que el 2 y el 3 (25 frases más, 0 reparos). **G.30**: 33 epígrafes del
  Item 1A por familia; los dos de WBD, «superados». **G.32**: previsión de la compañía frente
  a lo publicado en los ocho últimos trimestres (40 pares de las cartas de EDGAR: en 3T25 falló
  en todo; en el resto publicó por encima), la serie consenso · publicado de la bolsa, la tabla de
  la transcripción y lo que la compañía dijo de su propia previsión.
- **H (33–36)** y portada: del fichero de posición del analista (formulario); sin él, N/A campo a campo.
- **7 · Fechas clave**: la próxima presentación según la bolsa (20/10/2026, tras el cierre, 3T26,
  «esperada»), cuadrada con la del agregador ✓; la compañía no la anuncia en ningún adjunto.
- **11**: ROE y ROA de los últimos doce meses con la definición del 10-K (beneficio después de
  impuestos / patrimonio medio), frente a los que publica el agregador (ROE ✓ 49,5 %; ROA ≠ 24,5 %
  frente a 16,1 %: definición no publicada). El ROIC no lo publica ninguna fuente.
- **E (21–22)**: cuadro TAM · SAM · SOM con las 8 cifras que la compañía declara (call, proxy, 10-K)
  y cuadro de comparables según la industria que la bolsa asigna (BBY, IQ, CNVS, IZM) con P/Ventas
  y PER ∑ sobre sus cuentas de la SEC (iQIYI en CNY: N/A).
- **F (24–29, cinco apartados: el analista unificó 25 y 26)**: penúltima, con la API de la bolsa:
  cadena de opciones por vencimiento (volumen e interés abierto, put/call), **posicionamiento en
  derivados** (IV ATM y fuera del dinero por vencimiento y sesgo put − call, de Yahoo Finance como
  excepción autorizada; la IV de un vencimiento solo se imprime si el interés abierto del agregador
  cuadra con el de la bolsa dentro del 2 % —fuera de sesión el agregador devuelve la cadena a medio
  cargar y la IV sale N/A con ese motivo—), 13F (91,6 % institucional; mayores tenedores con la
  fecha de su 13F), insiders (74 operaciones en 12 meses, 4 compras) y short interest (2,2 % del
  capital, 3,3 días para cubrir). El apartado 20 añade el consenso de analistas de la bolsa y el
  «1 Year Target» de la ficha, dos cifras de la misma bolsa que se imprimen las dos.
  **I**: 37 pendiente, 38 fuentes, 39 contraste, cuadres entre fuentes, huecos y verificación, y
  el 40 (impreso 39) de documentación complementaria: 97 piezas en 20 apartados.

## Lo que falta, y por qué no está

- **Clave del redactor.** `emitir.py --redactar` está terminado (SDK instalado el 18/09/2026
  por decisión del analista, salida sujeta a esquema, dos rondas con los reparos, guardado en
  `narrativas/` para revisión) pero necesita `ANTHROPIC_API_KEY` en `.env`; sin ella lo dice y
  el informe sale con los apartados de texto pendientes. La narrativa de Netflix aprobada sigue
  entrando por `--narrativa` y es la muestra de estilo del redactor.
- **EDGAR al día.** Sin `WC_SEC_CONTACTO` en `.env` el sistema solo usa `cache_sec/`
  (Netflix: descargado el 16/09/2026); con él, refresca `submissions` y `companyfacts`.
- **Precio fuera de sesión.** Con la sesión cerrada, Nasdaq pone en `primaryData` el último
  cruce extrabursátil y en `secondaryData` el cierre oficial («Closed at … 4:00 PM ET»): el
  informe imprime el cierre y anota el cruce fuera de sesión, que no es el precio.
- **Capturas de pantalla de Nasdaq.** Su web rechaza al Chromium sin cabeza (HTTP/2 reset), así
  que la evidencia de la sección F y de la cotización es la respuesta literal de la API pintada
  con URL, hora y huella, y el cuerpo completo guardado al lado; el pie lo dice.
- **Sección H y recomendación.** El analista aún no ha rellenado `posiciones/NFLX.json`
  (formulario: `python -m tesis.formulario NFLX`); hasta entonces la portada dice «pendiente» y
  la H sale N/A campo a campo.
- **Volatilidad implícita fuera de sesión.** El agregador devuelve la cadena a medio cargar
  (bid, ask e interés abierto a cero) fuera del horario de la bolsa; el informe lo detecta por el
  cuadre del interés abierto y deja la IV en N/A con el motivo. Emitir en horario de mercado la
  rellena.
- **Tablero del analista** (decidir ≠, reconocer ◐, confirmar ◑ y figuras) como web, y
  después cuentas, cola y emisión: `docs/DISEÑO.md`.
- **Empresas fuera de EE. UU.**: sin SEC, el contraste es adjunto contra adjunto.

Las pruebas viven en `tests/`; las que usan el expediente real leen las rutas de
`tests/expediente_nflx.json` y se saltan si faltan. Cada prueba dice en su docstring qué
defecto reintroducido la hace fallar, y los cuatro principales se han visto fallar.
