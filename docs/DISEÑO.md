# SaaS de informes bursátiles — Diseño y plan (v0)

Fecha: 2026-09-16 · Estado: **borrador para decidir**, sin código.

Este documento fija arquitectura, stack, modelo de datos, principios y hoja de ruta.
No importa, copia ni adapta nada de QUANTUM: el saber del dominio se reaprovecha, el
código no. El tipo de informe concreto llegará después; todo lo que sigue es
independiente de él y está pensado para acogerlo como **una plantilla más**.

---

## 1. Qué es el producto

Un servicio web donde un cliente (una organización con uno o varios usuarios):

1. elige una **plantilla** de informe bursátil y unos **parámetros** (ticker, fecha,
   escenario…);
2. pide una **emisión**, que un proceso en segundo plano genera —trae datos de
   proveedores, construye los hechos, maqueta y produce PDF y HTML—;
3. descarga, comparte o programa que se repita (diario, semanal, tras resultados…);
4. puede hacer todo lo anterior también **por API**, con clave propia, para integrarlo
   en su flujo (CRM, intranet, correo automático).

Lo que lo distingue no es la maqueta sino la **trazabilidad**: cada cifra del informe
viaja con su fuente, su fecha de observación y su estado (hay dato · es cero · no hay
dato), y cada emisión es reproducible porque congela los datos con los que se hizo.

---

## 2. Requisitos que has fijado y cómo se traducen

| Lo que pediste | Decisión de diseño |
|---|---|
| Compatible para moverlo a web después | **API primero.** La web es *un* cliente de la API, no la aplicación. Mañana una SPA, una app móvil o un cliente Excel consumen lo mismo sin tocar el servidor. |
| Seguro | Aislamiento por organización en la base de datos (RLS), sesiones revocables en servidor, contraseñas Argon2, CSP estricta, CSRF, SQL parametrizado por construcción, auditoría de toda acción. |
| Fiable | Generación en cola con reintentos y estado explícito; emisiones inmutables y reproducibles; un solo almacén de estado (Postgres) en v0 para tener menos piezas que puedan fallar. |
| Todo tipo de integraciones | OpenAPI generado automáticamente, claves API por organización con permisos, webhooks al terminar una emisión, exportación PDF/HTML/JSON. |
| Que funcione bien y rápido | Backend asíncrono; datos de proveedores cacheados con caducidad; render HTML→PDF sin navegador; nada de JavaScript pesado en el cliente. |
| De cero, sin lo ya creado | Repo nuevo, paquete nuevo, sin dependencias hacia QUANTUM. |

---

## 3. Stack recomendado y por qué

**Lenguaje: Python 3.12.** Es donde tienes velocidad, y el ecosistema de datos
financieros y de render vive ahí.

**Backend: FastAPI.** Asíncrono, validación por tipos (Pydantic), y **OpenAPI gratis**,
que es lo que convierte «integraciones» en algo real desde el primer día.

**Base de datos: PostgreSQL.** Único almacén de estado en v0: datos, usuarios,
sesiones, cola de trabajos, caché de proveedores y auditoría. Menos infraestructura
que Redis + Postgres y suficiente hasta muy lejos. Con **Row-Level Security** el
aislamiento entre organizaciones lo garantiza la base de datos, no la disciplina del
programador.

**Cola de trabajos: tabla en Postgres con `FOR UPDATE SKIP LOCKED`.** Sin Celery, sin
Redis, sin dependencia extra. Un worker (o varios) toma trabajos, los marca, reintenta
con espera creciente. Cuando el volumen lo pida, se sustituye por Redis/arq sin tocar
el resto, porque la cola está detrás de una interfaz.

**Front web: HTML servido por el servidor (Jinja2) + JavaScript vanilla en módulos.**
Cumple CSP estricta (sin scripts en línea, sin CDN, sin `innerHTML`), pesa poco, no hay
build step. La interfaz habla con la misma API que usarán los clientes externos.

**Render de informes: HTML + CSS → PDF con WeasyPrint.** **Una sola plantilla** produce
la vista web y el PDF; no hay dos maquetas que puedan discrepar. Gráficos con
matplotlib exportados a SVG e incrustados: el mismo SVG en pantalla y en papel.

**Proveedores de datos: capa de adaptadores.** Cada proveedor implementa la misma
interfaz y devuelve **hechos**, no números: valor, estado, fuente, URL, fecha
observada, fecha obtenida. La caché vive en Postgres con caducidad por campo.

**Despliegue: Docker Compose (api, worker, postgres, caddy).** Caddy da TLS automático.
Un VPS basta para v0; después, Postgres gestionado y varios workers. **Desarrollo
también en Docker**: WeasyPrint necesita librerías de sistema (Pango/Cairo) que en
Windows son un dolor; con Docker el entorno de desarrollo es idéntico al de producción.

### Alternativas descartadas y motivo

- **Streamlit multiusuario.** No tiene autenticación propia, ni tenancy, ni cola; no es
  un SaaS, es un panel.
- **Next.js / TypeScript.** Ecosistema SaaS excelente, pero cambio de lenguaje, build
  step y muchas más dependencias. La ventaja «se mueve a web» ya la da API-primero.
- **Playwright/Chromium para PDF.** Más fiel al navegador, pero pesa cientos de MB por
  worker y tarda segundos por informe. WeasyPrint hace paginación CSS bien; si una
  plantilla lo desborda, se puede introducir Chromium solo para esa plantilla.
- **Celery + Redis.** Correcto pero sobredimensionado para v0; dos servicios más que
  vigilar.

---

## 4. Arquitectura

```
                 ┌──────────────┐        ┌──────────────┐
  navegador ───▶ │ api (FastAPI)│ ◀───── │ cliente API  │  (CRM, script, Excel…)
                 │ HTML + JSON  │        └──────────────┘
                 └──────┬───────┘
                        │ escribe trabajo
                        ▼
                 ┌──────────────┐  toma trabajo    ┌──────────────┐
                 │  PostgreSQL  │ ◀──────────────▶ │  worker      │
                 │  datos, cola,│                  │  proveedores │
                 │  caché, RLS  │                  │  hechos      │
                 └──────────────┘                  │  render→PDF  │
                        ▲                          └──────┬───────┘
                        │ metadatos de la emisión         │ fichero
                        └─────────────────────────────────┤
                                                   ┌──────▼───────┐
                                                   │  almacén     │ disco en v0,
                                                   │  (interfaz)  │ S3/R2 después
                                                   └──────────────┘
```

**Flujo de una emisión**

1. El usuario (o la API) crea una emisión → fila `emision` en estado `en_cola` + fila
   en la cola. Respuesta inmediata con el `id`.
2. El worker toma el trabajo, pasa a `generando`.
3. Para cada dato que la plantilla declara necesitar, pide a los proveedores; lo que
   hay en caché y no ha caducado no se vuelve a pedir.
4. Construye el **modelo de hechos** del informe con lo que trae la SEC.
4b. **Contraste automático** (PLANTILLA_TESIS.md §5): el worker busca cada hecho SEC
   en los adjuntos del analista —ya extraídos al subirlos— y clasifica cada campo ×
   periodo como confirmado, discrepante, solo SEC o solo documento. Lo que no está en
   ninguno es un **hueco** (§6). Si hay discrepancias, huecos o hechos por reconocer,
   la emisión pasa a `pendiente_analista` y el analista los resuelve en un tablero;
   cada decisión queda registrada y se imprime como nota. El sistema nunca elige el
   valor «que cuadra» ni rellena nada por su cuenta.
4c. **Recortes**: para cada tabla confirmada, el worker recorta la región del adjunto
   donde la encontró; para las figuras ilustrativas propone páginas y el analista
   confirma (PLANTILLA_TESIS.md §7).
5. Renderiza la plantilla a HTML; el HTML a PDF. Calcula el hash del contenido.
6. Guarda PDF y HTML en el almacén, congela los hechos usados en `emision.hechos`
   (JSON), pasa a `emitida`. Si algo falla, `fallida` con el error, y reintento según
   política.
7. Notifica: la web se actualiza (sondeo ligero), y si hay webhook configurado, se
   llama con firma HMAC.

**Reproducibilidad.** Una emisión guarda sus hechos congelados. Re-renderizar la misma
emisión con la misma plantilla produce el mismo hash; si cambia la plantilla, la
re-emisión es una emisión nueva con número siguiente. Nunca se sobreescribe.

---

## 5. El modelo de hechos (núcleo del producto)

Toda cifra que llega a una plantilla es un `Hecho`, nunca un número suelto:

```
Hecho
  valor        número | texto | None
  estado       'valor' | 'cero' | 'na'      ← los tres estados, explícitos
  fuente       identificador del proveedor
  url          dónde se puede comprobar
  observado_en fecha a la que se refiere el dato (cierre, trimestre…)
  obtenido_en  cuándo lo pedimos
  motivo       por qué es N/A, o por qué se ha clasificado así
  certeza      solo en inferencias: 'alta' | 'media' | 'baja'
  origen       'sec' | 'documento' | 'analista' | 'derivado'   ← la capa (PLANTILLA_TESIS.md §1)
  adjunto_id   solo en 'documento': el fichero aportado por el analista
  pagina       solo en 'documento': dónde está la cifra en ese fichero
  formula      solo en derivados: la operación, tal como se imprime en el informe
  entradas     solo en derivados: ids de los hechos que usa
```

Las cuatro capas —hecho publicado por la SEC, hecho aportado por el analista desde un
documento adjunto, supuesto del analista, derivado— se rotulan distinto en el informe
y nunca se mezclan en una misma celda sin decirlo. Que un derivado guarde
sus entradas es lo que permite afirmar por máquina que dos cifras que expresan el mismo
hecho son el mismo objeto.

Reglas que el código hace cumplir, no que se recomiendan:

- La plantilla **no acepta números crudos**: el filtro de formato exige un `Hecho`. Un
  `N/A` se rotula `N/A` con su motivo en nota; un cero se rotula `0` (no `—`).
- **Un hecho, una fuente.** Un total y sus partes salen del mismo cálculo; el rótulo
  de un gráfico y su titular salen del mismo hecho. Hay pruebas que afirman la
  concordancia, porque en pantalla el desacuerdo no se ve.
- **Inferencia ≠ hecho.** Toda clasificación derivada (sector, régimen, señal) lleva
  `certeza` y `motivo`, y la plantilla los muestra.
- **Prohibido inventar.** Ningún proveedor «de relleno», ningún valor por defecto,
  ninguna media para tapar huecos. `Math.random()` y equivalentes, prohibidos en
  interfaz.

---

## 6. Modelo de datos (Postgres)

Todas las tablas con `organizacion_id` tienen política RLS: una conexión solo ve las
filas de la organización fijada en la sesión (`SET app.organizacion_id`).

```
organizacion   id, nombre, slug, creada_en, plan
usuario        id, correo (único), hash_contrasena (Argon2), nombre, verificado_en, creado_en
pertenencia    usuario_id, organizacion_id, rol ('propietario'|'editor'|'lector')
sesion         id (aleatorio, solo hash en BD), usuario_id, organizacion_id,
               creada_en, caduca_en, revocada_en, agente, ip
clave_api      id, organizacion_id, prefijo (visible), hash, permisos[], caduca_en, revocada_en
plantilla      id, organizacion_id (NULL = global), clave, version, nombre,
               esquema_parametros (JSON Schema), datos_requeridos[], activa
informe        id, organizacion_id, plantilla_id, parametros (JSON), supuestos (JSON),
               textos (JSON), nombre, creado_por, creado_en
adjunto        id, informe_id, apartado ('cuentas_anuales'|'trimestrales'|'guidance'),
               nombre, hash, tamano, tipo_mime, ruta_almacen, periodo,
               incluido_en (adjunto_id, solo guidance), pagina, subido_por, subido_en
emision        id, informe_id, numero,
               estado ('en_cola'|'generando'|'pendiente_analista'|'emitida'|'fallida'),
               iniciada_en, terminada_en, hash_contenido, ruta_pdf, ruta_html,
               hechos (JSON congelado), adjuntos (ids congelados), error, intentos
candidato      id, adjunto_id, pagina, rectangulo, texto, valor, etiqueta_cercana,
               periodo_inferido, escala, certeza          (lo extraído; es inferencia)
hueco          id, emision_id, campo, periodo, apartado, motivo_sec, apartado_sugerido,
               estado ('pendiente'|'cubierto'|'declarado_na'), hecho_id,
               motivo_analista, resuelto_por, resuelto_en
contraste      id, emision_id, campo, periodo, hecho_sec_id, candidato_id,
               resultado ('confirmado'|'discrepante'|'solo_sec'|'solo_documento'),
               decision, motivo, decidido_por, decidido_en
recorte        id, emision_id, adjunto_id, pagina, rectangulo, ruta_png, hash,
               uso ('evidencia'|'figura'), apartado, pie, alt, confirmado_por
programacion   id, informe_id, cron, zona_horaria, proxima_en, activa, creada_por
webhook        id, organizacion_id, url, secreto (hash), eventos[], activo
dato_cache     proveedor, entidad, campo, observado_en → valor, estado, url,
               obtenido_en, caduca_en          (sin organizacion_id: es compartida)
trabajo        id, tipo, carga (JSON), estado, intentos, siguiente_en, bloqueado_por,
               creado_en                        (la cola)
auditoria      id, organizacion_id, usuario_id | clave_api_id, accion, objeto_tipo,
               objeto_id, detalle (JSON), en
```

Notas:

- `sesion` en servidor, no en cookie firmada: se puede **revocar** una sesión concreta
  («cerrar en todos los dispositivos»), y no hay secreto de firma que rotar.
- `clave_api` se enseña una vez; se guarda solo el hash. El `prefijo` permite
  identificarla en la lista sin revelarla.
- `plantilla.datos_requeridos` es la lista de campos que el worker debe pedir a los
  proveedores. Así el worker es genérico y la plantilla es declarativa.
- `dato_cache` es compartida entre organizaciones a propósito: el cierre de NVDA del
  15/09 es el mismo para todos. Lo que **no** se comparte es qué informes lo usan.

---

## 7. Seguridad (lista de compromiso, no de intención)

- **Tenancy:** RLS en Postgres + `organizacion_id` obligatorio en toda consulta de
  tablas de cliente. Prueba automática: un usuario de A no puede leer, listar ni
  adivinar ids de B.
- **Autenticación:** contraseña con Argon2id; sesión en cookie `HttpOnly`, `Secure`,
  `SameSite=Lax`; caducidad deslizante; verificación de correo antes de emitir.
  2FA (TOTP) en fase posterior. OAuth (Google/Microsoft) cuando haya demanda.
- **Autorización:** tres roles por organización; toda ruta declara el rol mínimo.
- **CSRF:** token por sesión en formularios; la API con clave no lo necesita (no usa
  cookie).
- **CSP estricta:** `default-src 'self'`; sin `unsafe-inline`, sin CDN, sin `eval`.
  Contenido dinámico con `createElement` y `textContent`; nada de `innerHTML`.
- **SQL:** siempre a través del ORM o con parámetros; nunca concatenación.
- **Secretos:** en variables de entorno; nunca en el repo. `.env.ejemplo` sí.
- **Límite de peticiones:** por IP en login/registro, por clave en la API.
- **Auditoría:** toda acción de escritura deja fila en `auditoria`.
- **Ficheros:** el almacén sirve por rutas firmadas con caducidad, nunca por ruta
  directa. Los adjuntos que sube el analista se comprueban por contenido (no por
  extensión), tienen tamaño máximo, nunca se ejecutan ni se renderizan en servidor, y
  su subida queda en `auditoria`.
- **Dependencias:** lista corta, fijada por versión, revisada con `pip-audit`.

---

## 8. Estructura del repositorio

```
SAAS-INFORMES/
  CLAUDE.md                 reglas del proyecto (heredará las duras de W&C)
  docs/
    DISEÑO.md               este documento
    DECISIONES/             una nota por decisión de arquitectura (ADR)
  compose.yaml              api, worker, postgres, caddy
  Dockerfile
  pyproject.toml
  .env.ejemplo
  aplicacion/
    __init__.py
    configuracion.py        lectura tipada de variables de entorno
    principal.py            arranque FastAPI, middlewares, CSP
    bd/                     motor, sesión, migraciones (Alembic), RLS
    modelos/                tablas (SQLAlchemy 2)
    esquemas/               entrada/salida de la API (Pydantic)
    api/                    rutas JSON: cuentas, informes, emisiones, claves, webhooks
    web/                    rutas HTML, plantillas Jinja2, estáticos (css, js)
    hechos/                 Hecho, formato, reglas de concordancia
    proveedores/            interfaz + un adaptador por proveedor + caché
    plantillas_informe/     una carpeta por plantilla: html, css, datos_requeridos
    render/                 HTML→PDF, gráficos SVG, hash
    cola/                   tabla-cola, worker, reintentos
    almacen/                interfaz + disco + (S3 después)
    seguridad/              contraseñas, sesiones, claves API, CSRF, límites
    auditoria.py
  worker.py                 punto de entrada del worker
  tests/
    unidad/                 hechos, formato, proveedores con respuestas grabadas
    integracion/            BD real en Docker, RLS, cola
    render/                 HTML de referencia (golden) por plantilla
    concordancia/           total = suma de partes, rótulo = titular, etc.
```

---

## 9. Pruebas: qué se afirma y cómo

- **Proveedores:** nunca contra la red en pruebas; respuestas grabadas en ficheros.
  Se afirma que un campo ausente sale como `na` con motivo, y que un cero sale como
  `cero`, no como `na`.
- **Hechos y formato:** el filtro de plantilla rechaza números crudos (prueba que
  falla si alguien lo relaja).
- **Concordancia:** por plantilla, una prueba por cada par «dos cosas que expresan el
  mismo hecho».
- **Render:** HTML de referencia por plantilla con datos fijos; el PDF se afirma por
  número de páginas y por texto extraído, no por bytes.
- **Tenancy:** prueba de integración que intenta cruzar organizaciones por todas las
  rutas.
- **Cola:** dos workers en paralelo no toman el mismo trabajo; un fallo reintenta con
  espera creciente y acaba en `fallida` con error legible.
- **Regla de la casa:** una prueba nueva no vale hasta haberla visto fallar.

---

## 10. Dependencias propuestas (pendientes de tu aprobación)

| Paquete | Para qué | Por qué esta y no otra |
|---|---|---|
| fastapi + uvicorn | API y web | asíncrono, OpenAPI automático |
| pydantic-settings | configuración desde entorno | tipada, falla al arrancar si falta algo |
| sqlalchemy 2 + alembic + psycopg 3 | BD y migraciones | estándar, parametrizado por construcción |
| jinja2 | plantillas HTML (web e informes) | una plantilla, dos salidas |
| weasyprint | HTML→PDF | paginación CSS sin navegador |
| matplotlib | gráficos a SVG | determinista, sin JS |
| argon2-cffi | hash de contraseñas | recomendación actual OWASP |
| httpx | llamadas a proveedores | asíncrono, timeouts sanos |
| **pypdfium2** | leer texto de PDF con posiciones y renderizar páginas a imagen (recortes) | licencia Apache/BSD, sin dependencias de sistema; la alternativa habitual (PyMuPDF) es AGPL, inviable para un SaaS sin licencia comercial |
| **pdfplumber** | localizar tablas y celdas en PDF | MIT; se apoya en pdfminer.six; es lo que da filas y columnas, no solo texto |
| **openpyxl** | leer adjuntos `.xlsx` | MIT; estándar |
| pytest, ruff, pip-audit | desarrollo | pruebas, estilo, auditoría de dependencias |

Las tres en negrita son nuevas respecto a la lista anterior y las pide el contraste
automático (PLANTILLA_TESIS.md §5). Fuera por ahora: OCR (tesseract), que es dependencia
de sistema y solo hace falta para PDF escaneados.

Deliberadamente **fuera** en v0: Redis, Celery, cualquier framework de front, cualquier
SDK de pagos, cualquier librería de sesiones (van en BD). Se añaden cuando una fase
los pida y con justificación.

---

## 11. Hoja de ruta

Cada fase tiene un «hecho cuando» comprobable. Las fases 0–2 no necesitan cuentas de
usuario: se puede tener un informe real saliendo antes de tener registro.

| Fase | Qué | Hecho cuando |
|---|---|---|
| 0 · Cimientos | repo, `CLAUDE.md`, `compose.yaml`, configuración tipada, BD con migración inicial, pytest y ruff pasando en Docker | `docker compose up` levanta api + postgres y `/salud` responde |
| 1 · Hechos y SEC | `Hecho` con capas, interfaz de proveedor, sub-adaptadores `identidad` y `hechos_xbrl` (ticker → CIK → companyfacts), reglas de reexpresión y sinónimos, caché con caducidad, pruebas de tres estados | un script pide la cuenta de resultados de 3 ejercicios de un ticker y muestra concepto, formulario, fecha y estado de cada cifra; un concepto no presentado sale `N/A` con motivo |
| 1b · Extractor y contraste | extracción de candidatos de PDF/XLSX (texto con posiciones, escala, tablas), contraste campo × periodo contra los hechos SEC, recortes de evidencia; sub-adaptadores `segmentos` y `documentos` | con un 10-K real y su PDF adjunto: cada cifra de la cuenta de resultados sale confirmada con página y recorte; se ha visto fallar la prueba al alterar una cifra del PDF (discrepante) y al borrar una fila (solo SEC) |
| 2 · Plantilla «Tesis de inversión» A–C | apartados 1–11 de `PLANTILLA_TESIS.md`: HTML+CSS, gráficos SVG, glifos de contraste, recortes bajo cada tabla, textos y decisiones del analista por fichero JSON (aún sin web), pruebas de concordancia y golden | un PDF real, con hash, desde la línea de comandos; la caja de cifras del apartado 2 y las tablas de la sección C son los mismos objetos y hay prueba que lo afirma; una emisión con una discrepancia sin decidir **no** produce PDF |
| 3 · Cuentas y tenancy | organizaciones, usuarios, sesiones, roles, RLS, auditoría, CSRF, CSP | la prueba de cruce de organizaciones pasa; login/registro funcionan en el navegador |
| 4 · Cola, emisiones y tablero | tabla-cola, worker, estados, reintentos, almacén, descarga firmada, **tres apartados de adjuntos, tablero de contraste y huecos, propuesta y confirmación de figuras** | desde la web subes los tres ficheros, pides una emisión, decides una discrepancia viendo el recorte, confirmas una figura y descargas el PDF |
| 5 · API y claves | claves API, OpenAPI publicada, webhooks firmados | un `curl` con clave crea una emisión y recibe el webhook al terminar |
| 6 · Programación | cron por informe, zona horaria, correo de aviso | un informe diario sale solo a la hora dicha |
| 7 · Operación | Caddy con TLS, copias de BD, logs estructurados, métricas básicas, alertas | desplegado en un VPS con dominio y copia nocturna verificada |
| 8 · Monetización | planes, límites por plan, pasarela de pago | **decisión pendiente** (ver §12) |

---

## 12. Decisiones que necesito de ti antes de la fase 0

1. ~~El tipo de informe~~ **Decidido (2026-09-16):** tesis de inversión / inicio de
   cobertura. Estructura en `PLANTILLA_TESIS.md`.
2. ~~Proveedores de datos y licencias~~ **Decidido (2026-09-16):** solo SEC/EDGAR
   (dominio público) para empresas de EE. UU.; lo que falte lo aporta el analista
   desde tres adjuntos obligatorios. Empresas fuera de EE. UU.: más adelante.
   **Cotización, decidido (2026-09-16, tarde):** fuente oficial siempre —la bolsa
   de cotización o un proveedor licenciado de datos de bolsa—, y del día de emisión;
   Yahoo solo en último extremo y rotulado «no oficial». Implementado en
   `tesis/precio.py` (`WC_PRECIO_FUENTE`); sin configurar, N/A.
   **Orden de construcción, decidido (2026-09-16, tarde):** primero la tubería de
   línea de órdenes (`tesis/`, `emitir.py`) hasta tener el PDF con las secciones A–C
   y los recortes; cuentas, cola y web después. La fase 0 de §11 pasa a ser esa.
3. **Idiomas de la interfaz y del informe.** ¿ES/EN por diccionario como en W&C, o solo
   ES en v0?
4. **Marca.** Nombre del producto y si va bajo Warrants & Co.
5. **Hospedaje y presupuesto.** VPS propio (~5–20 €/mes) frente a plataforma gestionada
   (más caro, menos operación).
6. **Monetización.** ¿Suscripción por organización, por emisión, o uso interno sin
   cobro al principio? Cambia el modelo de `plan` y si la fase 8 existe.
7. ~~Narrativa generada~~ **Decidido (2026-09-16, tarde):** los apartados 2 (resumen
   ejecutivo) y 3 (cinco pilares) los redacta el sistema a partir de los adjuntos, con
   cita de fichero y página en cada frase, cada cifra verificada contra los hechos
   contrastados, y el bloque rotulado «redactado por el sistema a partir de…» con su
   certeza. **Hecho (2026-09-17):** `tesis/narrativa.py` separa el redactor de la
   verificación. La narrativa es un JSON (frase → apoyos {documento, página, ancla
   literal} + claves de hechos); `verificar` retira toda frase cuyo ancla no esté en la
   página citada o cuya cifra no sea un hecho contrastado ni esté escrita en esa página,
   y lo anota en el Anexo I. El redactor con el SDK de Claude (`redactar_con_claude`,
   `--redactar`) importa el paquete solo al llamarse: **el paquete `anthropic` sigue sin
   instalarse hasta que Sergi lo apruebe**; mientras, la narrativa se redacta en la sesión
   de Claude Code sobre el mismo dossier y entra por `--narrativa` (Netflix:
   `narrativas/NFLX_2026-09-17.json`, 42 frases, 0 reparos).
8. **Índice completo A–I (decidido 2026-09-17).** El informe lleva los 39 apartados del
   índice del analista. Reglas fijadas por Sergi: **nada de estimaciones ni cifras
   autónomas**, todo unido a un documento oficial adjunto, actualizado y contrastado, y
   **con imágenes** que lo corroboren (recortes de las páginas citadas bajo cada apartado;
   retratos del equipo directivo desde la proxy). **D (12–20)** se rellena solo desde el
   libro Excel del DCF que adjunta el analista (`--dcf`, `tesis/dcf.py`, lectura por
   rótulos; sus entradas se cuadran con la sección C). **E (21–23)** y **G (30–32)** salen
   de los adjuntos (narrativa verificada, Item 1A por tipografía, consenso de la portada
   de la transcripción). **H (33–36)** la rellena el analista en `posiciones/<TICKER>.json`
   (plantilla `posiciones/plantilla.json`; será formulario del tablero). **F (24–29)** pasa
   a ser **penúltima** y queda **pendiente** de la API de datos que Sergi adjuntará; **I.37**
   pendiente, I.38 fuentes, I.39 el antiguo Anexo I. Los apartados se numeran por orden de
   impresión (F: 31–36; G: 24–26; H: 27–30).
   Los derivados que el índice pide y ningún formulario publica (EBITDA, ROE, ROIC, ROA,
   márgenes) se mantienen: se calculan solo de hechos contrastados, con la fórmula
   impresa y el glifo ∑. Si Sergi los considera «estimación», se retiran; se le pregunta.
9. **Cotización desde la bolsa (decidido 2026-09-17).** Sergi pidió conectar la API de Nasdaq
   como fuente del precio y de lo que faltaba por él. `WC_PRECIO_FUENTE=nasdaq` en `.env`
   (`tesis/entorno.py` lee el entorno o `.env` para todas las claves). `tesis/precio.py`
   toma de la ficha del valor el último cruce con fecha y hora, el estado de la sesión, el
   volumen, el rango de 52 semanas, el cierre anterior, la capitalización publicada y el «1
   Year Target», y del histórico de la bolsa los cierres oficiales. Tres reglas: (a) con la
   sesión abierta el precio se rotula «último precio … sesión abierta (hh:mm ET)», nunca
   «cierre»; (b) regla 9 sobre la propia fuente: el «cierre anterior» de la ficha se cuadra
   con el histórico y, si discrepan, sale N/A con el ≠; (c) la capitalización del informe es
   ∑ precio × acciones de la portada más reciente (10-Q), y se contrasta con la publicada
   por Nasdaq (tolerancia 0,5 %). El precio que el analista tecleó en su libro se cuadra
   con el cierre oficial de la fecha que él mismo escribió (Netflix: 80,32 del 14/09/2026 ✓).
   El «1 Year Target» de Nasdaq entra en el cuadro del apartado 20 como fila Hd de certeza
   media (Nasdaq no dice cuántos analistas ni de qué fecha). Mismo día, tres arreglos
   cazados con pruebas: fundación en la nota 1 de las cuentas (pág. 47, no en el Item 1);
   la fila de la proxy sin porcentaje (Willems) ya no arrastra la del grupo y las acciones
   se imprimen enteras (151.211 salía como «0»); las frases de la call se atribuyen por
   orador (página «Call Participants») y se descartan preguntas y presentaciones del
   moderador.
10. **Sección F interina desde la bolsa (17/09/2026, «adelante» de Sergi).** Sin API de derivados
   todavía, la web de Nasdaq publica cadena de opciones (volumen e interés abierto por strike y
   vencimiento; sin IV), 13F, Form 4 y short interest (FINRA), y la página de analistas con el
   consenso de precio objetivo (recuento y rango). `tesis/posicionamiento.py` los lee y el
   informe los imprime como Hd de certeza media, con put/call y % del capital como ∑ con fórmula
   y la serie de short interest desde el último split que la SEC registra. La sección F pasa de
   «pendiente» a «parcial» en el índice; 25 (sweeps, dark pool) y 26 (IV) siguen N/A con motivo.
   Evidencia: la web de Nasdaq no se deja capturar por Chromium sin cabeza (ERR_HTTP2 /
   CONNECTION_RESET), así que cada petición se guarda entera (`api_nasdaq_*.json`) y se pinta
   como imagen con URL, hora local y sha256 (`recortes.volcado_api`); el pie dice que no es una
   captura de pantalla. Hallazgo: Nasdaq publica dos consensos distintos (ficha «1 Year Target»
   94,50; página de analistas 95,82) y el informe los imprime con ≠.
11. **Decisiones de Sergio del 17/09/2026 (segunda tanda).** (a) 25 y 26 del índice se unifican en
   «Posicionamiento en derivados — IV, Open Interest (Put/Call ratio), volumen y sesgo implícito»;
   la API es Nasdaq y, para la IV que la bolsa no publica, **Yahoo Finance excepcionalmente y de
   forma provisional** (`tesis/yahoo.py`, cookie + crumb; interés abierto cuadrado con la bolsa por
   vencimiento; todo rotulado como agregador no oficial). El índice queda en 38 apartados
   (F: 31–35; I: 36–38). (b) `WC_SEC_CONTACTO` = «Sergio sergiodesantiago2004@gmail.com» en
   `.env`, con la instrucción de usarlo lo menos posible: solo en el User-Agent de EDGAR y solo
   cuando algo no está en `cache_sec/`; nunca a Nasdaq ni a Yahoo. (c) 22: comparables = la
   industria que la bolsa asigna (screener de Nasdaq) con cuentas de companyfacts y múltiplos ∑;
   Nasdaq no tiene endpoint de «peers». (d) 27–29 del índice (13F, insiders, short) con Nasdaq,
   Yahoo solo como suplente si Nasdaq falla (no ha hecho falta). (e) Se mantienen los ∑. (f) 21:
   cifras declaradas por la compañía en sus documentos oficiales, clasificadas TAM/SAM/SOM con
   motivo. (g) 37 sigue pendiente. Trampa cazada el mismo día: fuera de sesión Nasdaq pone el
   cruce extrabursátil en `primaryData` y el cierre oficial en `secondaryData`.
12. **Paleta y maqueta (18/09/2026, pedido de Sergio).** Los gráficos dejan el granate y pasan a una
   paleta corporativa propia definida una sola vez en `tesis/graficos.py` (`PALETA`: marino `#1c3760`
   para la serie principal, ocre `#b07d1e` para la medida secundaria —ΔE OKLab ≥ 30 entre ambos con
   protan y deutan— y `ESCALA`, un solo tono de oscuro a claro, ordenada por tamaño, para los
   repartos); la plantilla conserva su granate. El gráfico de barras con línea ya no comparte eje: la
   línea va en un panel superior con el mismo eje de periodos y cada punto con su cifra, y hay
   leyenda para las dos series. La maqueta: títulos y rótulos de cuadro con `break-after: avoid`, el
   índice en una página a dos columnas, la sección C en un solo flujo, 19–20 tras el reverse DCF,
   recortes de estados a media página (dos por página), cuadros de texto con la primera columna a
   ≥ 30 mm y cabeceras partibles, un cuadro de ≤ 10 filas nunca se parte, y los cuadros se numeran
   por orden de impresión (E antes que G). **Fallo de regla 9 cazado por el camino:** el recorte de
   evidencia se guardaba en un fichero por (adjunto, página, apartado), así que cuatro citas de la
   misma página producían cuatro recortes que se pisaban y tres huellas impresas ya no eran las de
   la imagen; ahora una página citada varias veces en un apartado da un solo recorte con todas sus
   anclas, y una prueba compara cada huella impresa con el fichero incrustado.
13. **Decisiones de Sergio del 18/09/2026 (tercera tanda), ejecutadas el 18–21/09.** (a) Números
   limpios: fuera de la página los glifos ✓ ≠ ∑, las capas H/Hd/S/D y «elaboración propia»; el
   contraste, la fuente y la fórmula viajan en el `title` de cada celda y las notas de cuadre en el
   apéndice 39 («Cuadres entre fuentes»). (b) Desaparece «X en una página»; sus gráficos abren la
   sección C. (c) Índice enlazado (anclas `#ap-N` y `#parte-X`; el PDF conserva los enlaces). (d) Toda
   la evidencia documental al apartado final «Documentación complementaria» (40 en el índice, 39
   impreso), una imagen por huella, salvo las cuentas de los estados, que siguen bajo sus cuadros.
   (e) Fuentes: SEC, Nasdaq y, para completar o contrastar, Yahoo Finance (`agregador.py`); nada
   más. (f) Fecha de resultados (`calendario.py`): la bolsa la publica como «esperada»; se imprime
   así y cuadrada con el agregador. (g) ROE/ROA: los formularios no los publican como cifra; el 10-K
   define el ROE para su plan de incentivos y esa definición se aplica en TTM (`multiplos.py`),
   frente al agregador. (h) El cuadre del DCF resuelve solo: rige el dato oficial y la nota
   explica (la deuda del libro = «deuda total» del agregador con arrendamientos). (i) EV/EBITDA y
   PEG con fórmula sobre las últimas cifras de la SEC; PEG del agregador al lado como otra
   definición. (j) 22: segunda clasificación oficial por SIC de la SEC (búsqueda de EDGAR por SIC ×
   `company_tickers`); nada de listas propias. (k) Sweeps y dark pool fuera del índice para siempre.
   (l) 32: las cartas anteriores desde EDGAR (`cartas.py`: Ex. 99.1 de cada 8-K, columna «Forecast»
   frente a la carta siguiente, BPA previo al split dividido por el factor) y la serie de la bolsa.
   (m) Formulario local del analista (`formulario.py` + `tablero/`): CSP estricta, sin innerHTML,
   bilingüe, validación campo a campo, escritura atómica, rechazo de escrituras ajenas. (n) 37 se
   mantiene. (o) Doble comprobación (`revision.py`): cada cifra impresa releída por otro camino
   (hecho → formateador propio; libro → openpyxl; cuadro → HTML); un desacuerdo detiene la emisión.
   (p) SDK `anthropic` instalado (aprobado con «termínalo»); redactor con esquema JSON, muestra de
   estilo de la narrativa aprobada y bucle de dos rondas con los reparos.
   Trampas cazadas: el libro renombrado a `Modelo_DCF_NFLX_Warrants_Co_2026-09-15.xlsx` llegó sin
   valores calculados (522 fórmulas) → se recalcula una copia con el Excel de la máquina vía COM
   (guion `.ps1`, porque una ruta con «&» no sobrevive a `-Command`) y el informe lo dice; fuera de
   sesión Yahoo devuelve la cadena de opciones a medio cargar (bid/ask/OI a cero, IV de relleno) →
   la IV solo se imprime si el OI cuadra con la bolsa; la consola de Windows (cp1252) no imprime
   «→» → `sys.stdout.reconfigure`; un POST `text/plain` desde otra web llega a 127.0.0.1 sin
   preflight → cabecera propia + `Content-Type` + `Origin`.
   Revisión adversaria (21–22/09/2026, dos revisores y tres relectores de cifras independientes):
   (q) la escala de una cifra del libro la decide el formato numérico de su celda («0.0%», «0.00\x»),
   no una heurística por rótulo (un WACC 0,105 bajo el rótulo «Pesimista» salía «0»); la doble
   comprobación aplica la misma regla por su cuenta. (r) Cada cifra de la sección D cita su propia
   celda (antes las diez columnas de un año citaban la primera). (s) La copia recalculada del libro
   se reutiliza si está completa y coincide con el original: releer no la reescribe y la huella
   impresa sigue siendo la del fichero. (t) Cartas: cada celda va con su columna (una celda «—» ya
   no desplaza la fila), «$(12)» es negativo, todas las cifras por acción se llevan a la base
   actual (3T24: 0,51 → 0,54, no 5,10 → 5,40), el split repetido por la SEC cuenta una vez y una
   previsión nula no inventa un desvío. (u) Cierres anteriores al primer ejercicio y al primer
   trimestre en `instantes`: ROE/ROA/ROIC 2021 ya se calculan (38,0 / 12,2 / 24,5 %). (v) 13F: las
   cifras del proveedor («$273,821») en la convención del documento, el literal al pasar el ratón.
   (w) Formulario: una ruta absoluta de Windows sin «/» ni «..» salía de `tablero/` → resolve() +
   carpeta; un criterio vacío con evidencia ya no se guarda. (x) Comparables: el último anual es el
   cierre más reciente entre conceptos y sin cierres iguales no hay PER; múltiplos: sin inversiones
   contrastadas no hay EV, sin BPA positivo no hay PER, 29 de febrero seguro; historial: negativos
   entre paréntesis; `_segmento_unico` solo acepta «one|a single»; la cabecera de F solo afirma
   el cuadre de la IV cuando la IV se imprime.
   (y) 22/09/2026 · SaaS local (`saas.py`, decisión del analista): cuatro pasos sobre un servidor de la
   biblioteca estándar; el buscador de tickers ordena ticker exacto · prefijo alfabético · nombre que empieza ·
   nombre que contiene; multipart con `email.parser`; la emisión es `emitir.py` como subproceso con `-u`
   (el registro se lee línea a línea); el informe se sirve enmarcado (`frame-src 'self'`) con su propia CSP
   porque el documento impreso lleva estilos en línea. Word: texto con zip+XML, tipo reconocido en el motivo,
   `DESCONOCIDO` para la tubería (sin coordenadas no hay evidencia). Tres simulaciones NFLX de punta a punta
   (API, reemisión, botón del paso 4) con 0 desacuerdos; MSFT sin adjuntos y ZZZZQ (sin CIK) rechazados con motivo.
   (z) 22/09/2026 · el primer expediente ajeno a Netflix (Oracle: nota de prensa, diapositivas y tablas del anexo
   99.1) dejó cuatro cosas: (1) sin `ANTHROPIC_API_KEY` el SDK no falla al crear el cliente sino al firmar la
   petición, con `TypeError`, que nadie capturaba: la emisión moría sin PDF. Ahora la clave se comprueba antes, el
   `TypeError` también se traduce a `SinRedactor` y el SaaS no pide la redacción si no hay con qué (2 y 3 salen N/A
   con su motivo). (2) Un código de salida 1 puede ser «borrador con discrepancias» —con PDF— o un proceso que
   reventó —sin él—: manda el fichero, no el código. (3) Tres tipos de documento nuevos, porque no toda compañía
   escribe cartas al estilo de Netflix: nota de resultados, sus tablas y la presentación; el cierre del periodo solo
   se toma si el documento lo declara («Q1» de un ejercicio no natural no dice cuál es). (4) Las conciliaciones
   GAAP → non-GAAP y los desgloses de otra partida (retribución en acciones por línea de gasto, información
   geográfica) tienen las filas del estado de resultados y cifras que no son las suyas: se descartan como fuente.
   Con esto Oracle pasa de 11 discrepancias que bloqueaban a 0 y de 1 cifra confirmada a 14. Y un POST rechazado
   tiene que leer su cuerpo antes de responder: cerrar con datos sin leer corta la conexión y el cliente no ve el 403
   (salía como prueba intermitente en `formulario` y en `saas`).
   (aa) 22/09/2026 · segunda vuelta del expediente de Oracle, con el analista delante. Lo que no funcionaba:
   (1) el detector de columnas exigía que la línea de años no llevara nada más, y Oracle imprime «(in millions,
   except per share data) 2026 2025»: se descartaban el balance, la cuenta de resultados y el flujo de caja
   enteros —de 139 páginas del 10-K se leían 5—. Ahora el rótulo de unidades puede ir a la izquierda del primer
   año, y a la derecha solo años y meses; una fila con importes nunca es cabecera. De 14 cifras confirmadas por
   los documentos se pasa a 74, y Netflix no se mueve (214).
   (2) El balance de un grupo con minoritarios trae dos filas de patrimonio; la genérica incluye los minoritarios
   y no es el concepto de la SEC. El campo declara ahora sus filas de más específica a más genérica y, dentro de
   una página, gana la específica: una sola fuente por hecho, sin discrepancias inventadas por nosotros.
   (3) El paso 4 enseñaba el último PDF aunque fuera anterior a los documentos recién adjuntados. El estado del
   ticker se reconstruye del disco (`informe_en_disco`) y dice si el informe está al día; si no lo está, se avisa
   y el botón pasa a ser «Emitir informe».
   (4) La carga del emisor se arranca con cerrojo (`arrancar_carga`): la página pregunta cada dos segundos y
   antes cada respuesta «sin empezar» lanzaba otro hilo contra la SEC; y el sondeo paraba justo en ese estado,
   así que la página se quedaba en blanco. Las peticiones llevan plazo: sin servidor, la página lo dice y ofrece
   reintentar en vez de quedarse colgada.
   (5) Maqueta: las cuatro páginas comparten la paleta del informe (marino y ocre), tarjetas, barra de pasos con
   su estado, tablas con etiquetas de certeza y avisos con glifo. El formulario del analista dice, campo a campo,
   dónde se imprime lo que escribe, trae la fecha puesta, enseña el valor del libro DCF al lado del precio
   objetivo y, al guardar, lista exactamente qué quedará N/A.
   (6) pypdfium2 no es seguro entre hilos: abrir dos empresas seguidas hacía que las dos cargas se pisaran y
   devolvieran «Data format error» con los ficheros intactos; la lectura de documentos va ahora de una en una.
   (7) El libro del analista puede tener otra maqueta (hojas «01 Summary», «08 Sensitivity»): las hojas se buscan
   también en inglés y una fila solo es un escenario si sus dos primeras cifras pueden ser un WACC y un
   crecimiento; si no, se anota en `faltan` en vez de imprimir un WACC de siete cifras.
   (8) Riesgos: la cabecera de familia puede no decir «Risks Related to» («Business and Operational Risks»), y el
   último renglón del epígrafe puede compartir línea con el cuerpo y dejar de contar como negrita; la frase se
   completa con el texto literal de su misma página. Oracle pasa de 1 epígrafe a 23.

---

## 13. Principios heredados (irán al `CLAUDE.md` nuevo)

   (bb) 23/09/2026 · el paso 1 deja de ser un montón de ficheros: `tesis/documentos.py` es el catálogo de los
   diez documentos que el informe sabe usar —clave, exigencia, formatos, en qué apartados entra y qué queda en
   N/A sin él— y de ahí salen, a la vez, la lista con un botón por documento, el destino que se imprime en la
   tabla del expediente y el aviso de lo que falta (regla 9: una sola fuente para «dónde va esto»). La casilla
   en la que el analista adjunta se guarda en `adjuntos/<TICKER>/declarado.json` y es una declaración suya,
   no una lectura: si el documento dice ser otra cosa, manda el documento y se avisa; si no dice nada y es un
   PDF, se usa la declaración diciéndolo (regla 3). Sin 10-K no se deja emitir; que falte un 10-Q avisa, pero
   no cierra la puerta.
   Tres fallos que rompían el trabajo del analista, los tres en la misma sesión:
   (1) el cuadro del precio objetivo imprimía cada fila del libro como importe, y la doble comprobación la
   relee en USD por acción salvo que el formato de la celda diga otra cosa: un «peso» o un «upside» guardados
   en porcentaje salían «0,00» frente a «0,00 %» y la emisión se detenía con el libro intacto. Ahora las dos
   lecturas usan la misma regla y hay prueba que lo afirma. Además, el recorrido sobre la cotización solo se
   calcula sobre precios: dividir un porcentaje entre la cotización daba una cifra sin significado.
   (2) `formulario.js` amplía el diccionario con `Object.assign` después de que `saas.js` haya pintado la
   página, y nadie repintaba: el formulario del analista se abría enseñando «titulo», «portada», «pista_tamano»
   —los nombres de las claves— hasta que se cambiaba de idioma y se volvía.
   (3) el tamaño de mercado apuntaba como huecos de la compañía siete conceptos del vocabulario de Netflix
   («hogares direccionables», «cuota de visionado de televisión»): si el término no aparece en ningún adjunto,
   la compañía no mide así su mercado y no es un hueco suyo; si aparece sin cifra, entonces sí.

---

   (cc) 23/09/2026 · lo que falta se trae, los números se auditan y la página no arrastra memoria.
   (1) `tesis/fuentes.py`: cada casilla del catálogo declara su fuente oficial (10-K, 10-Q, DEF 14A y los
   anexos 99 del 8-K de resultados) o el motivo de no tenerla —la transcripción es de un tercero, las cuentas
   maquetadas viven en la web del emisor—. Lo que se trae se baja en su HTML depositado y se imprime a PDF con
   el mismo Chromium del informe, porque sin coordenadas no hay cifra con evidencia ni recorte. El HTML se
   imprime con CSP `default-src 'none'`: el documento no sale a la red por su cuenta, a la SEC solo se le
   habla desde `sec.py`, identificados. En `origen.json` queda de qué depósito salió cada fichero, y de ahí
   le pone el expediente su formulario, su número de acceso y sus fechas: un documento traído no depende de
   adivinar su portada. Un solo 8-K sirve a la nota, las tablas, la carta y la presentación.
   (2) `tesis/auditor.py`: el único sitio donde vive la aritmética entre cifras. Comprueba las identidades
   contables periodo a periodo (activo = pasivo + patrimonio, BAI − impuestos = neto, beneficio = BPA ×
   acciones, EBITDA, FCF, deuda bruta), **despeja** el término que falte cuando la identidad es exacta —sale
   marcado como derivado, con su fórmula y sus entradas— y **declara** lo que no puede saber. Nunca cuadra a
   la fuerza ni pisa un dato publicado. En Oracle: 19 identidades cuadran, 5 despejadas, 1 contradicción
   real (el BPA no se multiplica por las acciones: hay dividendo preferente de por medio) y 31 sin datos.
   El veredicto va al registro y a `<base>.auditoria.txt`. Su aritmética se afirma contra la de `derivados`
   con una prueba: dos implementaciones del mismo hecho tienen que dar lo mismo (regla 9).
   (3) Una empresa cada vez: `saas.estado` suelta lo de la anterior al abrir otra —el expediente son los
   textos de todos sus PDF— y solo respeta una emisión en marcha. Todo se reconstruye del disco al volver.
   (4) Dos huecos de datos que la auditoría sacó a la luz en Oracle: su balance no imprime el total del pasivo
   —pone las dos mitades— y la SEC no lo tiene tampoco, así que se añade el campo «pasivo no corriente» y el
   total se despeja de sus dos mitades oficiales; y su deuda a largo plazo viajaba en «LongTermDebt», que
   Oracle solo usa en la nota de valor razonable con un único hecho a cero, en vez de «LongTermNotesPayable»,
   que es la cifra del balance. De 19 identidades que cuadraban se pasa a 34 y de 5 despejadas a 15.
   (5) pdfium dejaba abiertos todos los PDF leídos mientras viviera el proceso: en Windows el analista no
   podía quitar ni sustituir un documento que el servidor ya hubiera leído. Ahora se cierran.

---

Nunca inventar datos · tres estados siempre · inferencia con certeza y motivo · nada de
`innerHTML` · CSP estricta · SQL parametrizado · un hecho, una fuente · código en
español · interfaz por diccionario · color nunca único portador de información ·
cambios mínimos · una prueba nueva no vale hasta haberla visto fallar.
