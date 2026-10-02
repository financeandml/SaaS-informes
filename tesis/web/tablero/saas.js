/* Las páginas del SaaS (expediente, DCF, informe) y la barra de pasos que comparten con el asistente. Solo en español.
   Nada de HTML inyectado: todo lo dinámico se construye con elemento() y textContent. El ticker viaja en ?ticker=.
   Regla de la casa: un estado nunca se distingue solo por el color. Aquí lo dice su palabra —«adjuntado»,
   «falta», «alta», «EDGAR»—, sin símbolos: el rótulo es el portador. */
"use strict";

const D = {
  es: {
    p_expediente: "Expediente", p_dcf: "DCF", p_analista: "Analista", p_informe: "Informe",
    empresa: "Empresa", expediente: "Expediente en orden cronológico", contraste_t: "Contraste de las cifras",
    fichero: "Fichero", tipo: "Tipo", periodo: "Periodo", fecha_doc: "Fecha", certeza: "Certeza",
    destino: "Dónde va en el informe", quitar: "Quitar", siguiente_dcf: "Siguiente: DCF →", siguiente_analista: "Siguiente: analista →",
    anterior_expediente: "← Expediente", anterior_analista: "← Analista", libro: "Modelo DCF del analista",
    opcional: "opcional: sin libro, la sección D sale N/A con su motivo", lectura: "Lo que se ha leído del libro",
    escenario: "Escenario", valor_hoy: "Valor hoy", peso: "Peso", supuesto: "Supuesto", valor: "Valor",
    celda: "Celda", justificacion: "Justificación del analista", emision: "Emisión del informe",
    emitir: "Emitir informe", reemitir: "Volver a emitir", abrir_pdf: "Abrir el PDF", registro_t: "Registro de la emisión",
    vista_t: "Informe emitido", soltar: "Suelta aquí los ficheros o pulsa para elegirlos", formatos: "PDF · XLSX · DOCX — varios a la vez",
    soltar_libro: "Suelta aquí el libro o pulsa para elegirlo",
    necesarios: "Documentos necesarios", documento: "Documento", estado_doc: "Estado", ficheros_adj: "Ficheros adjuntados",
    adjuntar: "Adjuntar", anadir: "Añadir otro", sustituir: "Sustituir", adjuntado: "adjuntado", falta: "falta",
    imprescindible: "imprescindible", recomendado: "recomendado", opcional_doc: "opcional",
    donde_t: "Dónde conseguirlo:", cuantos: "de", falta_bloquea: "sin esto no se puede emitir",
    otros_t: "Otros documentos que no están en la lista", sin_casilla: "fuera de la lista",
    traer: "Traer de la fuente oficial", traer_todo: "Traer de la fuente oficial lo que falte (EDGAR o BME)",
    trayendo: "Pidiendo los documentos a la fuente oficial (EDGAR o BME)…",
    sin_fuente_t: "No hay fuente oficial:", traido_t: "traído de la fuente oficial", registro_traida: "Lo que se ha traído",
    buscando: "Buscando…", sin_resultados: "Ningún emisor de la SEC ni de BME coincide", cargando: "Cargando", listo: "Listo", error: "Error",
    subiendo: "Subiendo y clasificando…", subidos: "documentos en el expediente", rechazados: "sin admitir",
    contraste_en_curso: "Leyendo los documentos y contrastando las cifras…", bloquean: "discrepancias sin decidir",
    confirmado: "confirmadas con el documento", solo_sec: "solo de la SEC", derivado: "derivadas", solo_documento: "solo del documento",
    hueco: "sin dato", no_aplica: "no son partidas de esta empresa", discrepante: "en discrepancia", ejercicios: "Ejercicios", trimestres: "Trimestres",
    si: "sí", no: "no", na: "N/A", paginas: "páginas", hojas: "hojas", recalculado: "copia recalculada con Excel",
    sin_libro: "Aún no hay libro DCF para esta empresa.", faltan_libro: "El libro no trae:",
    emitiendo: "Emitiendo… puede tardar unos minutos", terminado: "Informe emitido", borrador: "Borrador: hay discrepancias sin decidir",
    fallo: "La emisión se detuvo: mira el registro", error_red: "No se pudo hablar con el servidor local.",
    sin_ticker: "Elige primero la empresa en el paso 1.", sin_adjuntos: "Sin documentos no hay informe: vuelve al paso 1.",
    viejo: "El informe que ves es anterior a los últimos documentos que has adjuntado: vuelve a emitir.",
    al_dia: "El informe está al día con lo adjuntado.", nunca: "Aún no has emitido el informe de esta empresa.",
    pend_posicion: "Sin las entradas del analista (paso 3, asistente), el informe sale como borrador con sus apartados pendientes.",
    pend_dcf: "Sin libro DCF (paso 2), los apartados 12 a 20 salen N/A con su motivo.",
    emitido_el: "emitido el", ficheros_usados: "documentos", cifras: "cifras",
    edgar_si: "EDGAR", edgar_no: "no casa con EDGAR",
  },
};
const t = (k) => (D.es[k] !== undefined ? D.es[k] : k);
const PAGINA = document.body.dataset.pagina;
const TICKER = (new URLSearchParams(location.search).get("ticker") || "").toUpperCase();
let ultimo = null;          // el último /api/estado, para repintar los rótulos

function elemento(etiqueta, atributos, hijos) {
  const e = document.createElement(etiqueta);
  Object.entries(atributos || {}).forEach(([k, v]) => { if (v !== null && v !== undefined) e.setAttribute(k, v); });
  (hijos || []).forEach((h) => e.appendChild(typeof h === "string" ? document.createTextNode(h) : h));
  return e;
}
function vaciar(n) { while (n.firstChild) n.removeChild(n.firstChild); return n; }
const con = (ruta) => ruta + (TICKER ? `?ticker=${encodeURIComponent(TICKER)}` : "");
const num = (v, dec) => (v === null || v === undefined ? t("na") : Number(v).toLocaleString("es-ES", { minimumFractionDigits: dec, maximumFractionDigits: dec }));
const pct = (v, dec) => (v === null || v === undefined ? t("na") : num(v * 100, dec) + " %");
const fecha = (iso) => (iso ? iso.split("-").reverse().join("/") : "—");

async function pedir(ruta, opciones) {
  // con plazo: si el servidor local no está (recién arrancado, parado), la página lo dice en vez de quedarse en blanco
  const corte = new AbortController();
  const plazo = setTimeout(() => corte.abort(), 30000);
  let r;
  try {
    r = await fetch(ruta, Object.assign({ headers: { Accept: "application/json" }, signal: corte.signal }, opciones || {}));
  } finally {
    clearTimeout(plazo);
  }
  const d = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(d.error || (d.errores && Object.values(d.errores).join("; ")) || r.statusText);
  return d;
}
const enviarJson = (ruta, datos) => pedir(ruta, { method: "POST", headers: { "Content-Type": "application/json", "X-Formulario": "saas" }, body: JSON.stringify(datos) });
function enviarFicheros(ruta, ficheros) {
  const cuerpo = new FormData();
  Array.from(ficheros).forEach((f) => cuerpo.append("fichero", f, f.name));
  return pedir(ruta, { method: "POST", headers: { "X-Formulario": "saas" }, body: cuerpo });
}

// ---------------------------------------------------------------- pasos y cabecera
const PASOS = [["/", "p_expediente", "inicio"], ["/dcf", "p_dcf", "dcf"], ["/asistente", "p_analista", "asistente"], ["/informe", "p_informe", "informe"]];

function pintarPasos(d) {
  const nav = document.getElementById("pasos");
  if (!nav) return;
  vaciar(nav);
  const hecho = {
    inicio: !!(d && d.adjuntos && d.adjuntos.adjuntos.length),
    dcf: !!(d && d.dcf && d.dcf.existe),
    asistente: !!(d && d.posicion && d.posicion.existe),
    informe: !!(d && d.informe && d.informe.al_dia),
  };
  PASOS.forEach(([ruta, clave, pagina], i) => {
    const clases = [pagina === PAGINA ? "actual" : "", hecho[pagina] ? "hecho" : ""].filter(Boolean).join(" ");
    const a = elemento("a", { href: con(ruta), class: clases },
      [elemento("span", { class: "num" }, [String(i + 1)]), elemento("span", { "data-i18n": clave }, [t(clave)])]);
    if (pagina !== "inicio" && !TICKER) { a.setAttribute("aria-disabled", "true"); a.removeAttribute("href"); }
    nav.appendChild(a);
  });
}

function pintarCabecera(d) {
  const emp = document.getElementById("empresa");
  const cik = document.getElementById("cik");
  if (!emp) return;
  const nombre = d && d.carga && d.carga.nombre;
  emp.textContent = d && d.ticker ? (nombre ? `${d.ticker} · ${nombre}` : d.ticker) : "—";
  // EE. UU.: CIK; España: ISIN. La bolsa, en los dos
  if (cik) cik.textContent = d && d.carga && d.carga.isin ? `ISIN ${d.carga.isin} · ${d.carga.bolsa || ""}`
    : d && d.carga && d.carga.cik ? `CIK ${Number(d.carga.cik)} · ${d.carga.bolsa || ""}` : "";
}

function pintarRotulos() {
  document.querySelectorAll("[data-i18n]").forEach((n) => { n.textContent = t(n.getAttribute("data-i18n")); });
  if (ultimo) pintarEstado(ultimo);
}

// ---------------------------------------------------------------- paso 1 · lista de documentos necesarios
async function quitarFichero(nombre) {
  const mensaje = document.getElementById("mensaje");
  mensaje.textContent = "";
  try { pintarEstado((await enviarJson(con("/api/adjuntos/borrar"), { fichero: nombre })).estado); sondear(); }
  catch (e) { mensaje.className = "error"; mensaje.textContent = e.message; }
}

function lineaFichero(f) {
  const quitar = elemento("button", { type: "button", class: "quitar" }, [t("quitar")]);
  quitar.addEventListener("click", () => quitarFichero(f.fichero));
  // una sola línea: fecha, procedencia y certeza. El motivo entero está en el título, a un palmo del ratón.
  const detalle = [f.periodo_fin ? fecha(f.periodo_fin) : f.fecha ? fecha(f.fecha) : "",
                   f.edgar === true ? t("edgar_si") : f.edgar === false ? t("edgar_no") : "", f.certeza]
    .filter(Boolean).join(" · ");
  return elemento("div", { class: "adj" }, [
    elemento("span", { class: "nombre", title: `${f.fichero} · ${f.motivo}` }, [f.rotulo || f.fichero]),
    elemento("span", { class: `etiqueta ${f.certeza}`, title: f.motivo }, [detalle]),
    quitar,
  ]);
}

async function traerDeLaSec(claves) {
  const p = document.getElementById("traida");
  p.className = "ayuda";
  p.textContent = t("trayendo");
  try {
    await enviarJson(con("/api/traer"), claves ? { documentos: claves } : {});
    sondear();
  } catch (e) { p.className = "ayuda error"; p.textContent = `${t("error")}: ${e.message}`; }
}

function pintarTraida(d) {
  const p = document.getElementById("traida");
  const lista = vaciar(document.getElementById("traida-lineas"));
  const tr = d && d.traida;
  const boton = document.getElementById("traer-todo");
  const faltan = ((d && d.documentos) || []).filter((x) => x.estado === "falta" && x.fuente).length;
  boton.disabled = !faltan || !!(tr && tr.estado === "trayendo");
  if (!tr) { p.textContent = ""; return; }
  p.className = "ayuda" + (tr.estado === "error" ? " error" : tr.estado === "listo" ? " ok" : "");
  p.textContent = tr.estado === "trayendo" ? t("trayendo") : tr.mensaje;
  (tr.lineas || []).forEach((l) => {
    lista.appendChild(elemento("li", { class: l.estado === "error" ? "error" : "" },
      [`${l.clave} · ${l.estado}${l.fichero ? " · " + l.fichero : ""}${l.motivo ? " — " + l.motivo : ""}`]));
  });
}

function botonAdjuntar(doc) {
  const entrada = elemento("input", { type: "file", accept: (doc ? doc.formatos : [".pdf", ".xlsx", ".xlsm", ".docx"]).join(","), class: "oculto" });
  if (!doc || doc.varios) entrada.setAttribute("multiple", "multiple");
  const cuantos = doc && doc.ficheros ? doc.ficheros.length : 0;
  const rotulo = !cuantos ? "adjuntar" : doc.varios ? "anadir" : "sustituir";
  const boton = elemento("button", { type: "button", class: "secundario" }, [t(rotulo)]);
  boton.addEventListener("click", () => entrada.click());
  entrada.addEventListener("change", () => { subirDocumento(doc ? doc.clave : "", entrada.files); entrada.value = ""; });
  return elemento("td", { class: "accion" }, [boton, entrada]);
}

function pintarDocumentos(d) {
  const tabla = document.getElementById("requeridos");
  if (!tabla) return;
  const cuerpo = vaciar(tabla.querySelector("tbody"));
  const docs = (d && d.documentos) || [];
  const puestos = docs.filter((x) => x.estado === "adjuntado").length;
  document.getElementById("cuenta-documentos").textContent = docs.length ? `${puestos} ${t("cuantos")} ${docs.length}` : "";
  docs.forEach((doc) => {
    const puesto = doc.estado === "adjuntado";
    // en pantalla, el nombre y la exigencia; lo demás —dónde entra, qué queda en N/A sin él, dónde conseguirlo—
    // viaja en el título de la fila: es lo que hacía ilegible la lista, no lo que la explicaba
    const porque = [doc.aporta, puesto ? "" : doc.sin_el,
                    puesto ? "" : (doc.fuente ? `${t("donde_t")} ${doc.donde}` : `${t("sin_fuente_t")} ${doc.sin_fuente}`)]
      .filter(Boolean).join(" · ");
    const celdaDoc = elemento("td", { class: "doc", title: porque }, [
      elemento("div", { class: "doc-titulo" }, [doc.titulo]),
      elemento("div", { class: "doc-aporta exigencia" },
        [t(doc.exigencia === "imprescindible" ? "imprescindible" : doc.exigencia === "recomendado" ? "recomendado" : "opcional_doc")]),
    ]);
    const grave = !puesto && doc.exigencia === "imprescindible";
    const marca = elemento("td", { class: "estado" }, [elemento("span", { class: `pildora ${puesto ? "ok" : grave ? "mal" : "medio"}` },
      [t(puesto ? "adjuntado" : "falta")])]);
    const celdaFicheros = elemento("td", { class: "ficheros" }, (doc.ficheros || []).map(lineaFichero));
    if (!doc.ficheros.length) celdaFicheros.appendChild(elemento("span", { class: "apunte" }, ["—"]));
    const acciones = botonAdjuntar(doc);
    if (!puesto && doc.fuente) {
      const traer = elemento("button", { type: "button", class: "secundario traer" }, [t("traer")]);
      traer.addEventListener("click", () => traerDeLaSec([doc.clave]));
      acciones.insertBefore(traer, acciones.firstChild);
    }
    cuerpo.appendChild(elemento("tr", { class: puesto ? "puesto" : grave ? "grave" : "" }, [celdaDoc, marca, celdaFicheros, acciones]));
  });
  pintarTraida(d);
}

function pintarAdjuntos(datos) {
  const tabla = document.getElementById("adjuntos");
  const cuerpo = vaciar(tabla.querySelector("tbody"));
  const filas = (datos && datos.adjuntos) || [];
  tabla.hidden = filas.length === 0;
  document.getElementById("tarjeta-expediente").hidden = filas.length === 0;
  document.getElementById("cuenta-adjuntos").textContent = filas.length ? `${filas.length} ${t("subidos")}` : "";
  filas.forEach((f) => {
    const quitar = elemento("button", { type: "button", class: "quitar" }, [t("quitar")]);
    quitar.addEventListener("click", () => quitarFichero(f.fichero));
    const edgar = f.edgar === null ? "—" : f.edgar ? t("edgar_si") : t("edgar_no");
    cuerpo.appendChild(elemento("tr", {}, [
      elemento("td", { class: "fichero", title: `${f.fichero} · ${f.paginas} ${t("paginas")} · ${f.clave}` }, [f.rotulo || f.fichero]),
      elemento("td", {}, [f.tipo]),
      elemento("td", {}, [fecha(f.periodo_fin)]),
      elemento("td", {}, [fecha(f.fecha)]),
      elemento("td", { class: "edgar", title: f.accession || "" }, [edgar]),
      elemento("td", {}, [elemento("span", { class: `etiqueta ${f.certeza}`, title: f.motivo }, [f.certeza])]),
      elemento("td", { class: "destino" }, [f.destino]),
      elemento("td", {}, [quitar]),
    ]));
  });
  const avisos = vaciar(document.getElementById("avisos"));
  ((datos && datos.avisos) || []).forEach((a) => avisos.appendChild(elemento("li", {}, [`[${a.gravedad}] ${a.texto}`])));
}

function pintarContraste(c) {
  const tarjeta = document.getElementById("tarjeta-contraste");
  const p = document.getElementById("contraste");
  const cifras = vaciar(document.getElementById("cifras-contraste"));
  if (!c || c.estado === "pendiente") { tarjeta.hidden = true; return; }
  tarjeta.hidden = false;
  if (c.estado !== "listo") { p.textContent = c.estado === "error" ? `${t("error")}: ${c.mensaje}` : t("contraste_en_curso"); return; }
  const ajenas = c.no_aplican || {};
  Object.entries(c.resumen || {}).forEach(([k, v]) => {
    // «no aplica» lleva en el título qué partidas son y por qué: son las que esta empresa no tiene en sus cuentas
    const motivo = k === "no_aplica" ? Object.entries(ajenas).map(([campo, por]) => `${campo}: ${por}`).join("\n") : "";
    cifras.appendChild(elemento("div", { title: motivo }, [elemento("dt", {}, [t(k)]), elemento("dd", {}, [String(v)])]));
  });
  const lista = Object.keys(ajenas);
  if (lista.length) {
    cifras.appendChild(elemento("div", { class: "ajenas" },
      [elemento("dt", {}, [t("no_aplica")]), elemento("dd", { class: "apunte" }, [lista.join(" · ")])]));
  }
  p.className = "ayuda" + (c.bloquean ? " error" : "");
  p.textContent = `${t("ejercicios")}: ${(c.ejercicios || []).join(", ")} · ${t("trimestres")}: ${(c.trimestres || []).join(", ")}`
    + (c.bloquean ? ` · ${c.bloquean} ${t("bloquean")}` : "");
  pintarDiscrepancias(tarjeta, c);
}

// Las discrepancias SEC ↔ documento las decide el analista aquí (antes solo con un JSON por línea de comandos, así que
// desde la web ningún informe con una discrepancia podía salir EMITIDO). El sistema no elige: enseña las dos cifras con
// su documento y su página, y guarda la que el analista toma con su motivo, que el informe imprime al pie.
const cifra = (v, unidad) => (v === null || v === undefined ? t("na")
  : unidad === "USD" && Math.abs(v) >= 1e5 ? `${num(v / 1e6, 0)} mln USD` : num(v, Math.abs(v) < 100 ? 2 : 0));
function pintarDiscrepancias(tarjeta, c) {
  let caja = document.getElementById("discrepancias");
  if (!caja) { caja = elemento("div", { id: "discrepancias" }, []); tarjeta.appendChild(caja); }
  vaciar(caja);
  const abiertas = c.discrepancias || [], decididas = c.decididas || [];
  if (!abiertas.length && !decididas.length) return;
  if (abiertas.length) {
    caja.appendChild(elemento("h3", {}, [`Discrepancias por decidir (${abiertas.length}): el informe no se emite mientras quede alguna`]));
  }
  abiertas.forEach((d) => {
    const motivo = elemento("input", { type: "text", placeholder: "Por qué eliges esa cifra (queda como nota al pie)" });
    const aviso = elemento("span", { class: "ayuda" }, []);
    const tomar = async (valor) => {
      aviso.className = "ayuda"; aviso.textContent = "Guardando y volviendo a contrastar…";
      try {
        const r = await enviarJson(con("/api/decisiones"), { campo: d.campo, periodo: d.periodo, valor, motivo: motivo.value });
        pintarEstado(r.estado);
      } catch (e) { aviso.className = "ayuda error"; aviso.textContent = e.message; }
    };
    const botones = [elemento("button", { type: "button", class: "secundario" }, [`Tomar la SEC: ${cifra(d.sec, d.unidad)}`])];
    botones[0].addEventListener("click", () => tomar(d.sec));
    (d.documentos || []).slice(0, 2).forEach((doc) => {
      const b = elemento("button", { type: "button", class: "secundario" }, [`Tomar ${doc.documento} pág. ${doc.pagina}: ${cifra(doc.valor, d.unidad)}`]);
      b.addEventListener("click", () => tomar(doc.valor));
      botones.push(b);
    });
    caja.appendChild(elemento("div", { class: "fila-lista discrepancia" }, [
      elemento("strong", {}, [`≠ ${d.rotulo} · ${d.periodo}`]),
      elemento("div", { class: "ayuda" }, [`SEC ${cifra(d.sec, d.unidad)} · `
        + (d.documentos || []).map((x) => `${x.documento} pág. ${x.pagina} = ${cifra(x.valor, d.unidad)}`).join(" · ") + (d.pista ? ` · ${d.pista}` : "")]),
      motivo, elemento("div", { class: "acciones-fila" }, botones), aviso]));
  });
  if (decididas.length) {
    caja.appendChild(elemento("h3", {}, [`Decididas por el analista (${decididas.length})`]));
    decididas.forEach((d) => {
      const quitar = elemento("button", { type: "button", class: "secundario" }, ["Deshacer"]);
      quitar.addEventListener("click", async () => {
        try { pintarEstado((await enviarJson(con("/api/decisiones"), { campo: d.campo, periodo: d.periodo, valor: null })).estado); }
        catch (e) { quitar.textContent = e.message; }
      });
      caja.appendChild(elemento("div", { class: "fila-lista" }, [
        `✓ ${d.campo} · ${d.periodo}: ${cifra(d.valor)} — ${d.motivo} (${d.analista}, ${fecha(d.fecha)}) `, quitar]));
    });
  }
}

// ---------------------------------------------------------------- paso 2
function pintarDcf(d) {
  const resumen = document.getElementById("resumen");
  const cab = document.getElementById("cabecera-libro");
  const subida = document.getElementById("subida");
  if (!d || !d.existe) { resumen.hidden = true; subida.textContent = t("sin_libro"); return; }
  if (d.error) { resumen.hidden = true; subida.className = "ayuda error"; subida.textContent = `${t("error")}: ${d.error}`; return; }
  subida.className = "ayuda ok";
  subida.textContent = d.fichero || "";
  if (!d.hojas) { resumen.hidden = true; return; }
  resumen.hidden = false;
  cab.textContent = `${d.hojas.length} ${t("hojas")}: ${d.hojas.join(", ")}` + (d.recalculado ? ` · ${t("recalculado")}` : "");
  const cifras = vaciar(document.getElementById("cifras-dcf"));
  const filas = [[t("supuesto") + "s", String(d.supuestos.length)], [t("escenario") + "s", String(d.tabla_escenarios.length)]];
  if (d.valor_razonable !== null && d.valor_razonable !== undefined) filas.push(["Valor razonable (USD)", num(d.valor_razonable, 2)]);
  (d.anclajes_objetivo || []).slice(0, 2).forEach((a) => filas.push([a.rotulo, num(a.valor, 2)]));
  filas.forEach(([k, v]) => cifras.appendChild(elemento("div", {}, [elemento("dt", {}, [k]), elemento("dd", {}, [v])])));
  const esc = vaciar(document.querySelector("#escenarios tbody"));
  d.tabla_escenarios.forEach((x) => esc.appendChild(elemento("tr", {}, [
    elemento("td", {}, [x.nombre]), elemento("td", { class: "num" }, [pct(x.wacc, 2)]), elemento("td", { class: "num" }, [pct(x.g, 2)]),
    elemento("td", { class: "num" }, [num(x.valor_hoy, 2)]), elemento("td", { class: "num" }, [pct(x.peso, 0)])])));
  const sup = vaciar(document.querySelector("#supuestos tbody"));
  d.supuestos.forEach((s) => sup.appendChild(elemento("tr", {}, [
    elemento("td", {}, [s.rotulo]), elemento("td", { class: "num" }, [num(s.valor, Math.abs(s.valor) < 2 ? 4 : 2)]),
    elemento("td", {}, [s.celda]), elemento("td", { class: "destino" }, [s.origen || "—"])])));
  const faltan = vaciar(document.getElementById("faltan"));
  Object.entries(d.faltan || {}).forEach(([k, v]) => faltan.appendChild(elemento("li", {}, [`${k}: ${v}`])));
}

async function subirDcf(ficheros) {
  if (!ficheros.length) return;
  const p = document.getElementById("subida");
  p.className = "ayuda";
  p.textContent = t("subiendo");
  try {
    const d = await enviarFicheros(con("/api/dcf"), [ficheros[0]]);
    pintarDcf(d);
    if (ultimo) { ultimo.dcf = d; pintarPasos(ultimo); }
  } catch (e) { p.className = "ayuda error"; p.textContent = `${t("error")}: ${e.message}`; }
}

// ---------------------------------------------------------------- paso 4
function banda(clase, texto) {
  return elemento("div", { class: `aviso ${clase}` }, [elemento("span", {}, [texto])]);
}

function pintarInforme(d) {
  const em = d.emision;
  const inf = d.informe;
  const emitiendo = em && em.estado === "emitiendo";
  const zona = vaciar(document.getElementById("banda"));
  const mensaje = document.getElementById("mensaje");
  const boton = document.getElementById("emitir");
  const pdf = document.getElementById("pdf");
  const pend = vaciar(document.getElementById("pendientes"));

  if (emitiendo) zona.appendChild(banda("", `${t("emitiendo")} (${em.empezado})`));
  else if (!inf) zona.appendChild(banda("alerta", t("nunca")));
  else if (!inf.al_dia) zona.appendChild(banda("alerta", t("viejo")));
  else zona.appendChild(banda("bueno", `${t("al_dia")} · ${t("emitido_el")} ${inf.emitido}`));
  if (em && em.estado === "error" && !emitiendo) zona.appendChild(banda("malo", t("fallo")));
  else if (em && em.borrador && !emitiendo) zona.appendChild(banda("alerta", t("borrador")));

  if (!d.adjuntos.adjuntos.length) pend.appendChild(elemento("li", {}, [t("sin_adjuntos")]));
  if (!d.posicion.existe) pend.appendChild(elemento("li", {}, [t("pend_posicion")]));
  if (!d.dcf.existe) pend.appendChild(elemento("li", {}, [t("pend_dcf")]));

  boton.disabled = emitiendo || !d.adjuntos.adjuntos.length;
  boton.textContent = inf && inf.al_dia ? t("reemitir") : t("emitir");
  pdf.hidden = !inf;
  if (inf) { pdf.setAttribute("href", inf.pdf); document.getElementById("fichero-informe").textContent = `${inf.fichero} · ${t("emitido_el")} ${inf.emitido}`; }
  document.getElementById("huella").textContent = em && em.orden ? em.orden : "";

  const tarjetaReg = document.getElementById("tarjeta-registro");
  const registro = document.getElementById("registro");
  tarjetaReg.hidden = !(em && em.registro && em.registro.length);
  if (!tarjetaReg.hidden) { registro.textContent = em.registro.join("\n"); registro.scrollTop = registro.scrollHeight; }

  const tarjetaVista = document.getElementById("tarjeta-vista");
  const vista = document.getElementById("vista");
  tarjetaVista.hidden = !(inf && inf.html);
  if (inf && inf.html && vista.getAttribute("src") !== inf.html) vista.setAttribute("src", inf.html);
  mensaje.className = emitiendo ? "" : em && em.estado === "error" ? "error" : inf ? "ok" : "";
  mensaje.textContent = emitiendo ? t("emitiendo") : "";
}

async function lanzarEmision() {
  const mensaje = document.getElementById("mensaje");
  mensaje.className = "";
  mensaje.textContent = t("emitiendo");
  try { await enviarJson(con("/api/emitir"), {}); sondear(); }
  catch (e) { mensaje.className = "error"; mensaje.textContent = e.message; }
}

// ---------------------------------------------------------------- estado común
function pintarEstado(d) {
  ultimo = d;
  pintarCabecera(d);
  pintarPasos(d);
  if (PAGINA === "inicio") {
    const carga = document.getElementById("carga");
    carga.className = "ayuda " + (d.carga.estado === "error" ? "error" : d.carga.estado === "listo" ? "ok" : "");
    carga.textContent = d.carga.estado === "sin empezar" ? "" : `${t(d.carga.estado === "listo" ? "listo" : d.carga.estado === "error" ? "error" : "cargando")}: ${d.carga.mensaje}`;
    document.getElementById("bloque-adjuntos").disabled = d.carga.estado !== "listo";
    pintarDocumentos(d);
    pintarAdjuntos(d.adjuntos);
    pintarContraste(d.contraste);
    document.getElementById("siguiente").setAttribute("href", con("/dcf"));
  } else if (PAGINA === "dcf") {
    pintarDcf(d.dcf);
  } else if (PAGINA === "informe") {
    pintarInforme(d);
  }
}

let sonda = null;
async function sondear() {
  if (!TICKER) return;
  try {
    const d = await pedir(con("/api/estado"));
    pintarEstado(d);
    const sigue = ["sin empezar", "cargando"].includes(d.carga.estado) || (d.contraste && d.contraste.estado === "contrastando")
      || (d.emision && d.emision.estado === "emitiendo") || (d.traida && d.traida.estado === "trayendo");
    clearTimeout(sonda);
    if (sigue) sonda = setTimeout(sondear, 2500);
  } catch (e) {
    const m = document.getElementById("mensaje");
    if (m) { m.className = "error"; m.textContent = t("error_red"); }
  }
}

// ---------------------------------------------------------------- buscador y subida
function buscador() {
  const entrada = document.getElementById("busqueda");
  const lista = document.getElementById("candidatos");
  let temporizador = null;
  entrada.value = TICKER;
  const cerrar = () => { lista.hidden = true; entrada.setAttribute("aria-expanded", "false"); };
  entrada.addEventListener("input", () => {
    clearTimeout(temporizador);
    const q = entrada.value.trim();
    if (!q) { cerrar(); return; }
    temporizador = setTimeout(async () => {
      try {
        const candidatos = await pedir(`/api/tickers?q=${encodeURIComponent(q)}`);
        vaciar(lista);
        if (!candidatos.length) lista.appendChild(elemento("li", { class: "vacio" }, [t("sin_resultados")]));
        candidatos.forEach((c) => {
          const li = elemento("li", { role: "option", tabindex: "0" },
            [elemento("strong", {}, [c.ticker]), elemento("span", {}, [c.nombre]),
              elemento("span", { class: "cik" }, [c.id ? `${c.bolsa ? c.bolsa + " · " : ""}${c.id}` : `CIK ${Number(c.cik)}`])]);
          const elegir = () => { location.href = `/?ticker=${encodeURIComponent(c.ticker)}`; };
          li.addEventListener("click", elegir);
          li.addEventListener("keydown", (ev) => { if (ev.key === "Enter") elegir(); });
          lista.appendChild(li);
        });
        lista.hidden = false;
        entrada.setAttribute("aria-expanded", "true");
      } catch (e) {
        // junto al buscador, donde se está mirando: al pie de la página nadie lo veía (29/09/2026)
        const carga = document.getElementById("carga");
        carga.className = "ayuda error";
        carga.textContent = e.message;
        configuracion();
      }
    }, 250);
  });
  entrada.addEventListener("keydown", (ev) => { if (ev.key === "ArrowDown" && lista.firstChild) { ev.preventDefault(); lista.firstChild.focus(); } if (ev.key === "Escape") cerrar(); });
  document.addEventListener("click", (ev) => { if (!ev.target.closest(".buscador")) cerrar(); });
}

async function subirDocumento(clave, ficheros) {
  if (!ficheros || !ficheros.length) return;
  const p = document.getElementById("subida");
  p.className = "ayuda";
  p.textContent = t("subiendo");
  try {
    const ruta = con("/api/adjuntos") + (TICKER ? "&" : "?") + `documento=${encodeURIComponent(clave || "")}`;
    const d = await enviarFicheros(ruta, ficheros);
    pintarEstado(d.estado);
    p.className = "ayuda" + (d.rechazados.length ? " error" : " ok");
    p.textContent = `${d.estado.adjuntos.adjuntos.length} ${t("subidos")}` + (d.rechazados.length ? ` · ${t("rechazados")}: ${d.rechazados.join("; ")}` : "");
    document.getElementById("ficheros").value = "";
    sondear();
  } catch (e) { p.className = "ayuda error"; p.textContent = `${t("error")}: ${e.message}`; }
}
const subirAdjuntos = (ficheros) => subirDocumento("", ficheros);

function zona(id, entradaId, manejar) {
  const z = document.getElementById(id);
  const entrada = document.getElementById(entradaId);
  ["dragenter", "dragover"].forEach((ev) => z.addEventListener(ev, (e) => { e.preventDefault(); z.classList.add("sobre"); }));
  ["dragleave", "drop"].forEach((ev) => z.addEventListener(ev, (e) => { e.preventDefault(); z.classList.remove("sobre"); }));
  z.addEventListener("drop", (e) => manejar(e.dataTransfer.files));
  entrada.addEventListener("change", () => manejar(entrada.files));
}

// ---------------------------------------------------------------- primera vez: el contacto que exige la SEC
// Sin él la SEC rechaza toda petición y no se puede buscar ninguna empresa. No hay valor por defecto (cada usuario se
// identifica a sí mismo): se pide aquí, se guarda en .env y el buscador funciona sin reiniciar el servidor.
async function configuracion() {
  let c;
  try { c = await pedir("/api/configuracion"); } catch (e) { return; }
  const previo = document.getElementById("tarjeta-configuracion");
  if (c.sec_contacto) { if (previo) previo.remove(); return; }
  if (previo) return;
  const campo = elemento("input", { type: "text", id: "contacto-sec", autocomplete: "name email", placeholder: "Ana Pérez ana@ejemplo.com" });
  const boton = elemento("button", { type: "button", id: "guardar-contacto" }, ["Guardar"]);
  const aviso = elemento("p", { class: "ayuda", id: "aviso-contacto" }, []);
  const tarjeta = elemento("section", { class: "tarjeta", id: "tarjeta-configuracion" }, [
    elemento("h2", {}, [elemento("span", { class: "num" }, ["0"]), " Antes de empezar"]),
    elemento("p", {}, ["La SEC exige que quien consulta EDGAR se identifique con su nombre y su correo. Sin eso no se pueden "
      + "buscar empresas de EE. UU.; las españolas (BME) se buscan sin él. Se guarda solo en este ordenador (fichero .env) "
      + "y solo se envía a la SEC."]),
    elemento("div", { class: "acciones-fila" }, [campo, boton]), aviso]);
  const guardar = async () => {
    aviso.className = "ayuda";
    aviso.textContent = "Guardando…";
    try {
      await enviarJson("/api/configuracion", { contacto: campo.value });
      tarjeta.remove();
      const carga = document.getElementById("carga");
      if (carga) { carga.className = "ayuda ok"; carga.textContent = "Listo: ya puedes buscar la empresa por su ticker o su nombre."; }
      const busqueda = document.getElementById("busqueda");
      if (busqueda) { busqueda.focus(); busqueda.dispatchEvent(new Event("input")); }
    } catch (e) { aviso.className = "ayuda error"; aviso.textContent = e.message; }
  };
  boton.addEventListener("click", guardar);
  campo.addEventListener("keydown", (ev) => { if (ev.key === "Enter") guardar(); });
  const main = document.querySelector("main");
  main.insertBefore(tarjeta, main.firstChild);
  campo.focus();
}

// ---------------------------------------------------------------- arranque
pintarPasos(null);
configuracion();
pintarRotulos();
if (PAGINA === "inicio") {
  buscador();
  zona("zona", "ficheros", subirAdjuntos);
  document.getElementById("traer-todo").addEventListener("click", () => traerDeLaSec(null));
  if (TICKER) enviarJson("/api/preparar", { ticker: TICKER }).then(sondear).catch(() => { document.getElementById("mensaje").textContent = t("error_red"); });
} else if (!TICKER) {
  document.getElementById("mensaje").textContent = t("sin_ticker");
} else if (PAGINA === "dcf") {
  zona("zona-dcf", "fichero", subirDcf);
  document.getElementById("anterior").setAttribute("href", con("/"));
  document.getElementById("siguiente").setAttribute("href", con("/asistente"));
  sondear();
} else if (PAGINA === "informe") {
  document.getElementById("anterior").setAttribute("href", con("/asistente"));
  document.getElementById("emitir").addEventListener("click", lanzarEmision);
  sondear();
}
