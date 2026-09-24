/* Paso 3: la posición y la tesis del analista → posiciones/<TICKER>.json.
   Se apoya en saas.js (elemento, t, D, TICKER, pedir, pintarEstado) y añade lo suyo: el contexto que ya sabe el
   sistema (valor del libro, recomendación guardada), lo que falta por rellenar y el guardado con errores campo a campo.
   Nada de HTML inyectado: elemento() y textContent. */
"use strict";

Object.assign(D.es, {
  titulo: "Posición y tesis del analista", portada: "Recomendación y posición", analista: "Analista", fecha: "Fecha del informe",
  recomendacion: "Recomendación", sin_decidir: "— sin decidir —", comprar: "Comprar", mantener: "Mantener", vender: "Vender",
  precio_objetivo: "Precio objetivo (USD)", precio_entrada: "Precio de entrada (USD)", fecha_entrada: "Fecha de entrada",
  tamano: "Tamaño de la posición", horizonte: "Horizonte", tesis: "Tesis de inversión consolidada", argumento: "Argumento",
  asunciones: "Asunciones clave", horizonte_tesis: "Horizonte de la tesis", checklist: "Checklist de entrada",
  criterio: "Criterio", cumplido: "¿Cumplido?", evidencia: "Evidencia", anadir: "+ Añadir criterio", riesgo: "Gestión del riesgo",
  invalidacion: "Qué invalidaría la tesis", tamano_posicion: "Tamaño de posición y por qué", volatilidad: "Volatilidad que asumes",
  seguimiento: "Seguimiento post-entrada", kpis: "KPIs que vas a vigilar", fechas_revision: "Fechas de revisión",
  criterios_salida: "Criterios de salida", guardar: "Guardar", guardado_ya: "Guardado", quitar: "Quitar",
  sin_evaluar: "sin evaluar", si: "sí", no: "no", guardando: "Guardando…", siguiente_informe: "Siguiente: informe →",
  anterior_dcf: "← DCF", sin_rellenar: "sin rellenar", error_guardar: "No se ha guardado: corrige los campos marcados.",
  fichero_nuevo: "aún no hay fichero; se creará al guardar", fichero_existe: "guardado en",
  pista_tamano: "texto libre: «2 % de la cartera»", pista_horizonte: "«12–18 meses»", pista_lineas: "una por línea",
  pista_fechas: "AAAA-MM-DD, una por línea", pista_argumento: "por qué esta empresa y por qué ahora; se imprime literal",
  contexto_libro: "Valor razonable del libro DCF", contexto_objetivo: "Precio objetivo del libro", contexto_escenarios: "escenarios",
  sin_guardar: "Tienes cambios sin guardar.", reintentar: "Reintentar", falta_por_rellenar: "Queda por rellenar, y saldrá N/A en el informe:",
});
Object.assign(D.en, {
  titulo: "Analyst position and thesis", portada: "Recommendation and position", analista: "Analyst", fecha: "Report date",
  recomendacion: "Recommendation", sin_decidir: "— undecided —", comprar: "Buy", mantener: "Hold", vender: "Sell",
  precio_objetivo: "Target price (USD)", precio_entrada: "Entry price (USD)", fecha_entrada: "Entry date",
  tamano: "Position size", horizonte: "Horizon", tesis: "Consolidated investment thesis", argumento: "Argument",
  asunciones: "Key assumptions", horizonte_tesis: "Thesis horizon", checklist: "Entry checklist",
  criterio: "Criterion", cumplido: "Met?", evidencia: "Evidence", anadir: "+ Add criterion", riesgo: "Risk management",
  invalidacion: "What would invalidate the thesis", tamano_posicion: "Position size and why", volatilidad: "Volatility you accept",
  seguimiento: "Post-entry follow-up", kpis: "KPIs you will watch", fechas_revision: "Review dates",
  criterios_salida: "Exit criteria", guardar: "Save", guardado_ya: "Saved", quitar: "Remove",
  sin_evaluar: "not assessed", si: "yes", no: "no", guardando: "Saving…", siguiente_informe: "Next: report →",
  anterior_dcf: "← DCF", sin_rellenar: "left empty", error_guardar: "Not saved: fix the marked fields.",
  fichero_nuevo: "no file yet; it will be created on save", fichero_existe: "saved in",
  pista_tamano: "free text: «2% of the portfolio»", pista_horizonte: "«12–18 months»", pista_lineas: "one per line",
  pista_fechas: "YYYY-MM-DD, one per line", pista_argumento: "why this company and why now; printed verbatim",
  contexto_libro: "Fair value from the DCF workbook", contexto_objetivo: "Target price in the workbook", contexto_escenarios: "scenarios",
  sin_guardar: "You have unsaved changes.", reintentar: "Retry", falta_por_rellenar: "Still empty, and it will be N/A in the report:",
});

const API = con("/api/posicion");
let sucio = false;
let ultimoGuardado = null;

function marcarSucio() { sucio = true; document.getElementById("mensaje").textContent = ""; }

function filaCriterio(c) {
  const criterio = elemento("input", { type: "text", name: "criterio", value: c.criterio || "", autocomplete: "off" });
  const evidencia = elemento("input", { type: "text", name: "evidencia", value: c.evidencia || "", autocomplete: "off" });
  const cumplido = elemento("select", { name: "cumplido" }, [
    elemento("option", { value: "" }, [t("sin_evaluar")]),
    elemento("option", { value: "true" }, [t("si")]),
    elemento("option", { value: "false" }, [t("no")]),
  ]);
  cumplido.value = c.cumplido === true ? "true" : c.cumplido === false ? "false" : "";
  const quitar = elemento("button", { type: "button", class: "quitar" }, [t("quitar")]);
  const fila = elemento("tr", {}, [elemento("td", {}, [criterio]), elemento("td", {}, [cumplido]), elemento("td", {}, [evidencia]), elemento("td", {}, [quitar])]);
  quitar.addEventListener("click", () => { fila.remove(); marcarSucio(); });
  [criterio, evidencia, cumplido].forEach((e) => e.addEventListener("input", marcarSucio));
  return fila;
}

function pintar(p) {
  const v = (ruta) => ruta.split(".").reduce((o, k) => (o === null || o === undefined ? o : o[k]), p);
  document.querySelectorAll("[name]").forEach((campo) => {
    if (!campo.name.includes(".") && !["analista", "fecha"].includes(campo.name)) return;
    const valor = v(campo.name);
    if (Array.isArray(valor)) campo.value = valor.join("\n");
    else campo.value = valor === null || valor === undefined ? "" : String(valor);
  });
  const cuerpo = vaciar(document.getElementById("checklist"));
  const filas = (p.checklist || []).length ? p.checklist : [{}];
  filas.forEach((c) => cuerpo.appendChild(filaCriterio(c)));
  if (!document.querySelector("[name='fecha']").value) document.querySelector("[name='fecha']").value = new Date().toISOString().slice(0, 10);
}

function leer() {
  const d = { analista: "", fecha: "", posicion: {}, tesis: {}, checklist: [], riesgo: {}, seguimiento: {} };
  const lineas = (s) => s.split("\n").map((x) => x.trim()).filter(Boolean);
  const numero = (s) => (s.trim() === "" ? null : Number(s));
  document.querySelectorAll("#formulario [name]").forEach((campo) => {
    const n = campo.name;
    if (!n.includes(".")) { if (n in d) d[n] = campo.value.trim(); return; }
    const [grupo, clave] = n.split(".");
    if (!d[grupo]) return;
    if (campo.tagName === "TEXTAREA") d[grupo][clave] = lineas(campo.value);
    else if (campo.type === "number") d[grupo][clave] = numero(campo.value);
    else d[grupo][clave] = campo.value.trim();
  });
  d.tesis.argumento = (document.querySelector("[name='tesis.argumento']").value || "").trim();
  document.querySelectorAll("#checklist tr").forEach((fila) => {
    const criterio = fila.querySelector("[name='criterio']").value.trim();
    const evidencia = fila.querySelector("[name='evidencia']").value.trim();
    const cumplido = fila.querySelector("[name='cumplido']").value;
    if (criterio || evidencia) d.checklist.push({ criterio, evidencia, cumplido: cumplido === "" ? null : cumplido === "true" });
  });
  return d;
}

function mostrarErrores(errores) {
  document.querySelectorAll(".invalido").forEach((e) => e.classList.remove("invalido"));
  const lista = vaciar(document.getElementById("pendientes"));
  Object.entries(errores || {}).forEach(([campo, motivo]) => {
    const e = document.querySelector(`[name='${campo}']`);
    if (e) e.classList.add("invalido");
    lista.appendChild(elemento("li", {}, [`${campo}: ${motivo}`]));
  });
}

function pintarPendientes(sinRellenar) {
  const lista = vaciar(document.getElementById("pendientes"));
  if (!sinRellenar || !sinRellenar.length) return;
  lista.appendChild(elemento("li", {}, [t("falta_por_rellenar")]));
  sinRellenar.forEach((x) => lista.appendChild(elemento("li", {}, [x])));
}

function pintarContexto(d) {
  const zona = vaciar(document.getElementById("contexto"));
  const est = document.getElementById("estado-fichero");
  est.textContent = d.posicion.existe ? `${t("fichero_existe")} ${d.posicion.fichero}` : t("fichero_nuevo");
  const dcf = d.dcf || {};
  const cifras = [];
  if (dcf.valor_razonable !== null && dcf.valor_razonable !== undefined) cifras.push([t("contexto_libro"), num(dcf.valor_razonable, 2) + " USD"]);
  (dcf.anclajes_objetivo || []).slice(0, 2).forEach((a) => cifras.push([a.rotulo, num(a.valor, 2) + " USD"]));
  if ((dcf.tabla_escenarios || []).length) cifras.push([t("contexto_escenarios"), String(dcf.tabla_escenarios.length)]);
  if (!cifras.length) return;
  const dl = elemento("dl", { class: "cifras" }, []);
  cifras.forEach(([k, v]) => dl.appendChild(elemento("div", {}, [elemento("dt", {}, [k]), elemento("dd", {}, [v])])));
  zona.appendChild(dl);
  const pista = document.getElementById("pista-objetivo");
  if (pista && dcf.valor_razonable) pista.textContent = `${t("contexto_libro")}: ${num(dcf.valor_razonable, 2)} USD`;
}

async function cargar() {
  const [p, d] = await Promise.all([pedir(API), pedir(con("/api/estado"))]);
  document.title = `${d.ticker} · ${t("titulo")} — Warrants & Co.`;
  pintarEstado(d);
  pintarContexto(d);
  pintar(p.posicion || {});
  pintarPendientes(d.posicion.sin_rellenar);
  sucio = false;
}

async function guardar(ev) {
  if (ev) ev.preventDefault();
  const mensaje = document.getElementById("mensaje");
  mensaje.className = "";
  mensaje.textContent = t("guardando");
  const r = await pedir(API, { method: "POST", headers: { "Content-Type": "application/json", "X-Formulario": "posicion" }, body: JSON.stringify(leer()) })
    .catch((e) => ({ _error: e.message }));
  if (r._error) {
    mensaje.className = "error";
    mensaje.textContent = t("error_guardar") + " " + r._error;
    return false;
  }
  mostrarErrores({});
  pintarPendientes(r.sin_rellenar);
  mensaje.className = "ok";
  mensaje.textContent = `${t("guardado_ya")}: ${r.fichero}` + (r.sin_rellenar.length ? ` · ${r.sin_rellenar.length} ${t("sin_rellenar")}` : "");
  sucio = false;
  ultimoGuardado = r;
  if (r.estado) { pintarEstado(r.estado); pintarContexto(r.estado); }
  return true;
}

document.getElementById("formulario").addEventListener("submit", guardar);
document.getElementById("formulario").addEventListener("input", marcarSucio);
document.getElementById("anadir-criterio").addEventListener("click", () => { document.getElementById("checklist").appendChild(filaCriterio({})); marcarSucio(); });
document.getElementById("anterior").setAttribute("href", con("/dcf"));
document.getElementById("siguiente-informe").setAttribute("href", con("/informe"));
document.getElementById("siguiente-informe").addEventListener("click", async (ev) => {
  if (!sucio) return;                       // nada que guardar: se sigue
  ev.preventDefault();
  if (await guardar()) location.href = con("/informe");
});
document.getElementById("idioma").addEventListener("click", () => {
  document.querySelectorAll("#checklist tr").forEach((fila) => {
    const s = fila.querySelector("[name='cumplido']");
    const opciones = ["sin_evaluar", "si", "no"];
    Array.from(s.options).forEach((o, i) => { o.textContent = t(opciones[i]); });
    fila.querySelector(".quitar").textContent = t("quitar");
  });
  if (ultimo) { pintarContexto(ultimo); pintarPendientes(ultimo.posicion.sin_rellenar); }
});
window.addEventListener("beforeunload", (ev) => { if (sucio) { ev.preventDefault(); ev.returnValue = ""; } });
function avisarSinServidor(e) {
  const m = document.getElementById("mensaje");
  m.className = "error";
  m.textContent = `${t("error_red")} ${e && e.message ? e.message : ""}`;
  const reintentar = elemento("button", { type: "button", class: "secundario" }, [t("reintentar")]);
  reintentar.addEventListener("click", () => cargar().then(() => reintentar.remove()).catch(avisarSinServidor));
  m.parentNode.insertBefore(reintentar, m);
}
// El diccionario de esta página se añade a D después de que saas.js ya haya pintado los rótulos, así que hay que
// repintarlos: sin esto, al entrar se ve el nombre de cada clave —«titulo», «portada», «pista_tamano»— y el
// formulario solo se leía después de cambiar de idioma y volver.
repintarIdioma();
cargar().catch(avisarSinServidor);
