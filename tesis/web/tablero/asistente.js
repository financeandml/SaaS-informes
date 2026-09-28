/* Asistente del analista: 9 pasos generados desde docs/spec/04_entradas.yaml (lo sirve /api/asistente).
   Guarda en <datos>/entradas/<TICKER>/<fecha>/entradas.json, que es lo que lee el informe. Solo en español.
   Nada de HTML inyectado: el(), textContent y nodos. */
"use strict";

const qs = new URLSearchParams(location.search);
const TICKER = (qs.get("ticker") || "").toUpperCase();
let FECHA = qs.get("fecha") || "";
let ESQUEMA = [], DATOS = {}, FALTAS = {}, PROPUESTAS = [], PROPUESTAS_CAMPOS = {}, PASO = Number(qs.get("paso") || 1);

const PALABRAS = {
  tamano: "tamaño", anio: "año", anios: "años", senal: "señal", descripcion: "descripción", fundacion: "fundación", asignacion: "asignación",
  direccion: "dirección", recomendacion: "recomendación", justificacion: "justificación", invalidacion: "invalidación", revision: "revisión",
  valoracion: "valoración", metodo: "método", metrica: "métrica", titulo: "título", vision: "visión", linea: "línea", ejecucion: "ejecución",
  multiplo: "múltiplo", multiplos: "múltiplos", explicito: "explícito", sintetico: "sintético", regresion: "regresión", dilucion: "dilución",
  catalizador: "catalizador", kpi: "KPI", kpis: "KPI", sbc: "SBC", erp: "ERP", ronic: "RONIC", kd: "coste de la deuda", g: "g",
  pct: "%", porque: "por qué", por: "por", que: "qué", compania: "compañía", ultimo: "último", ultimos: "últimos", pais: "país",
  segmentos_ok: "segmentos confirmados", track_record: "trayectoria", texto_es: "texto en español", riesgo_1a: "epígrafe del Item 1A",
  riesgo_es: "riesgo en español", driver: "supuesto", top: "cinco riesgos", guia_manual: "guía manual", si: "sí", cumplido: "¿cumplido?",
  drawdown_tolerado: "drawdown tolerado (%)", tamano_pct: "tamaño (% de la cartera)", precio_entrada: "precio de entrada (USD)",
  fecha_entrada: "fecha de entrada", fechas_revision: "fechas de revisión (AAAA-MM-DD)", salida: "criterios de salida",
  nombre_presentacion: "nombre en el informe", fecha_informe: "fecha del informe", fecha_valoracion: "fecha de valoración",
  horizonte_meses: "horizonte (meses)", beta_desapalancada: "beta desapalancada", tipo_marginal: "tipo impositivo marginal (%)",
  wacc_ajuste_pp: "ajuste del WACC (p. p.)", declarado_compania: "declarado por la compañía", top_down: "de arriba abajo",
  bottom_up: "de abajo arriba", se_amplia: "se amplía", se_estrecha: "se estrecha", inicio_cobertura: "inicio de cobertura",
  actualizacion: "actualización", ultimos_12_meses: "últimos 12 meses", ultimo_ejercicio: "último ejercicio",
  fuera_de_deuda: "fuera de la deuda", coste_de_caja: "coste de caja", rendimiento_bonos: "rendimiento de los bonos",
  rating_sintetico: "rating sintético", value_driver: "value driver", multiplo_salida: "múltiplo de salida",
  no_recurrente_en_caja: "no recurrente en caja", excluir_de_base: "excluir de la base", efectos_de_red: "efectos de red",
  costes_de_cambio: "costes de cambio", ventaja_de_costes: "ventaja de costes", escala_eficiente: "escala eficiente",
  umbral_invalidacion: "umbral de invalidación", usar_en_multiplos: "usar en los múltiplos", durabilidad_anios: "durabilidad (años)",
  recomendacion_justificacion: "justificación de la recomendación",
};

function el(etiqueta, atributos, hijos) {
  const e = document.createElement(etiqueta);
  Object.entries(atributos || {}).forEach(([k, v]) => { if (v !== null && v !== undefined && v !== false) e.setAttribute(k, v === true ? "" : v); });
  (hijos || []).forEach((h) => e.appendChild(typeof h === "string" ? document.createTextNode(h) : h));
  return e;
}
function vaciar(n) { while (n.firstChild) n.removeChild(n.firstChild); return n; }
function rotulo(id) {
  const ultimo = String(id).split(".").pop();
  if (PALABRAS[ultimo]) return PALABRAS[ultimo].charAt(0).toUpperCase() + PALABRAS[ultimo].slice(1);
  const t = ultimo.split("_").map((w) => PALABRAS[w] || w).join(" ");
  return t.charAt(0).toUpperCase() + t.slice(1);
}
function legible(falta) {                                  // «pos.asunciones[2].texto: …» → «Asunciones 2 · texto: …»
  const i = falta.indexOf(":");
  if (i < 0) return falta;
  const id = falta.slice(0, i), m = id.match(/^([\w.]+?)(?:\[(\d+|[^\]]+)\])?(?:\.(\w+))?$/);
  if (!m) return falta;
  return `${rotulo(m[1])}${m[2] ? ` ${m[2]}` : ""}${m[3] ? ` · ${rotulo(m[3]).toLowerCase()}` : ""}${falta.slice(i)}`;
}
function valorEnum(v) { return PALABRAS[v] || String(v).replace(/_/g, " "); }
function obtener(obj, ruta) { return ruta.split(".").reduce((o, k) => (o && typeof o === "object" ? o[k] : undefined), obj); }
function fijar(obj, ruta, valor) {
  const p = ruta.split(".");
  let o = obj;
  p.slice(0, -1).forEach((k) => { if (!o[k] || typeof o[k] !== "object" || Array.isArray(o[k])) o[k] = {}; o = o[k]; });
  if (valor === undefined || valor === "" || (Array.isArray(valor) && !valor.length)) delete o[p[p.length - 1]]; else o[p[p.length - 1]] = valor;
}
function palabras(t) { return (String(t || "").match(/[\p{L}\p{N}_]+/gu) || []).length; }
const esProsa = (c) => c.tipo === "texto" && c.palabras;

function pista(c) {
  return [c.ayuda, c.nota, c.prop ? `propuesta: ${c.prop}` : "", c.val ? `validación: ${c.val}` : "", c.palabras ? `${c.palabras} palabras` : "",
          c.rango ? `rango ${c.rango}` : ""].filter(Boolean).join(" · ");
}

// ---- editores por tipo: cada uno devuelve un nodo y llama a cambio(valor) con el valor ya en su forma del JSON
function editorTexto(c, valor, cambio, envuelto) {
  const actual = envuelto ? (valor && typeof valor === "object" ? valor.texto || "" : valor || "") : (valor || "");
  const campo = c.palabras ? el("textarea", { rows: 4 }) : el("input", { type: "text" });
  campo.value = actual;
  const nodos = [campo];
  if (c.palabras) {
    const [bajo, alto] = String(c.palabras).split("-").map(Number);
    const cuenta = el("div", { class: "contador" });
    const pintar = () => { const n = palabras(campo.value); cuenta.textContent = `${n} palabras (${bajo}–${alto})`; cuenta.classList.toggle("fuera", n < bajo || n > alto); };
    campo.addEventListener("input", pintar); pintar(); nodos.push(cuenta);
  }
  campo.addEventListener("change", () => cambio(campo.value.trim() ? (envuelto ? { texto: campo.value.trim() } : campo.value.trim()) : undefined));
  return el("div", {}, nodos);
}
function editorNumero(c, valor, cambio) {
  const campo = el("input", { type: "number", step: "any" });
  campo.value = valor === undefined || valor === null ? "" : valor;
  campo.addEventListener("change", () => cambio(campo.value === "" ? undefined : Number(campo.value)));
  return campo;
}
function editorFecha(c, valor, cambio) {
  const campo = el("input", { type: "date" }); campo.value = valor || "";
  campo.addEventListener("change", () => cambio(campo.value || undefined));
  return campo;
}
function editorEnum(c, valor, cambio) {
  if (!Array.isArray(c.valores)) return editorTexto(c, valor, cambio, false);
  const s = el("select", {}, [el("option", { value: "" }, ["— elige —"]), ...c.valores.map((v) => el("option", { value: String(v) }, [valorEnum(v)]))]);
  s.value = valor === undefined ? "" : String(valor);
  s.addEventListener("change", () => cambio(s.value || undefined));
  return s;
}
function editorBool(c, valor, cambio) {
  const b = el("input", { type: "checkbox" }); b.checked = valor === true;
  b.addEventListener("change", () => cambio(b.checked));
  return el("label", {}, [b, " sí"]);
}
function editorSerie(c, valor, cambio) {
  const v = valor && typeof valor === "object" && !Array.isArray(valor) ? { ...valor } : (typeof valor === "number" ? { 1: valor, N: valor } : {});
  return el("div", { class: "serie" }, ["1", "2", "3", "5", "N"].map((k) => {
    const campo = el("input", { type: "number", step: "any" }); campo.value = v[k] === undefined ? "" : v[k];
    campo.addEventListener("change", () => { if (campo.value === "") delete v[k]; else v[k] = Number(campo.value); cambio(Object.keys(v).length ? { ...v } : undefined); });
    return el("label", {}, [`año ${k}`, campo]);
  }));
}
const CITA = [{ id: "doc", tipo: "texto" }, { id: "pag", tipo: "texto" }, { id: "texto", tipo: "texto", palabras: "1-400" }, { id: "texto_es", tipo: "texto", palabras: "1-400" }];
function editorLista(c, valor, cambio, campos) {
  const lista = Array.isArray(valor) ? valor.map((x) => (x && typeof x === "object" ? { ...x } : x)) : [];
  const caja = el("div");
  const pintar = () => {
    vaciar(caja);
    if (!campos) {                                         // lista de textos: uno por línea
      const t = el("textarea", { rows: 4 }); t.value = lista.join("\n");
      t.addEventListener("change", () => cambio(t.value.split("\n").map((x) => x.trim()).filter(Boolean)));
      caja.appendChild(el("span", { class: "pista" }, ["uno por línea"])); caja.appendChild(t); return;
    }
    lista.forEach((fila, k) => {
      const quitar = el("button", { type: "button", class: "secundario" }, ["Quitar"]);
      quitar.addEventListener("click", () => { lista.splice(k, 1); cambio(lista.slice()); pintar(); });
      const bloque = el("div", { class: "fila-lista" }, [el("div", { class: "cabecera-fila" }, [`${k + 1}`, quitar])]);
      campos.forEach((sub) => bloque.appendChild(campoNodo(sub, fila[sub.id], (v) => { if (v === undefined) delete fila[sub.id]; else fila[sub.id] = v; cambio(lista.slice()); }, true)));
      caja.appendChild(bloque);
    });
    const mas = el("button", { type: "button", class: "secundario" }, ["+ Añadir"]);
    mas.addEventListener("click", () => { lista.push({}); pintar(); });
    caja.appendChild(mas);
  };
  pintar();
  return caja;
}
function editorEscenarios(c) {
  return el("div", {}, (c.escenarios || []).map((nombre) => el("fieldset", { class: "escenario" }, [
    el("legend", {}, [`Escenario ${nombre}`]),
    ...(c.campos || []).map((sub) => campoNodo({ ...sub, id: sub.id }, obtener(DATOS, `esc.${nombre}.${sub.id}`),
      (v) => fijar(DATOS, `esc.${nombre}.${sub.id}`, v), true)),
  ])));
}
// ---- paso 9: párrafos de plantilla (06 §1). El sistema propone; el analista acepta o edita frase a frase (la cita no se
// edita) y lo validado se guarda con la huella de la propuesta: si los datos cambian, la huella es otra y se vuelve a pedir.
function estadoParrafo(p, guardado) {
  if (!guardado || !Array.isArray(guardado.frases) || !guardado.frases.length) return "sin validar";
  if (guardado.propuesta !== p.huella) return "cambió desde que lo validó: vuelva a aceptarlo o editarlo";
  return guardado.editado ? "editado" : "aceptado";
}
function editorParrafos() {
  const caja = el("div", { class: "parrafos" });
  if (!PROPUESTAS.length) {
    caja.appendChild(el("div", { class: "pista" }, ["Aún no hay propuestas para esta fecha: genere el informe (borrador) en la página del informe y vuelva aquí."]));
    return caja;
  }
  PROPUESTAS.forEach((p) => {
    const bloque = el("div", { class: "fila-lista", "data-parrafo": p.id });
    const pintarUno = (editando) => {
      vaciar(bloque);
      const guardado = obtener(DATOS, `revision.parrafos.${p.id}`);
      const vigente = guardado && guardado.propuesta === p.huella && Array.isArray(guardado.frases) && guardado.frases.length === p.frases.length;
      const textos = p.frases.map((f, k) => (vigente ? String(guardado.frases[k][0]) : f[0]));
      bloque.appendChild(el("div", { class: "cabecera-fila" }, [p.titulo, el("span", { class: "estado-parrafo" }, [estadoParrafo(p, guardado)])]));
      const campos = [];
      bloque.appendChild(el("ol", {}, p.frases.map((f, k) => {
        if (!editando) return el("li", {}, [`${textos[k]} `, el("span", { class: "pista" }, [`[${f[1]}]`])]);
        const t = el("textarea", { rows: 2 }); t.value = textos[k]; campos.push(t);
        return el("li", {}, [t, el("span", { class: "pista" }, [`[${f[1]}]`])]);
      })));
      const fijarParrafo = (frases) => fijar(DATOS, `revision.parrafos.${p.id}`,
        { propuesta: p.huella, frases, editado: frases.some((x, k) => x[0] !== p.frases[k][0]) });
      const botones = editando
        ? [["Dar por buena la edición", "", () => { fijarParrafo(p.frases.map((f, k) => [campos[k].value.trim(), f[1]])); pintarUno(false); }],
           ["Cancelar", "secundario", () => pintarUno(false)]]
        : [["Aceptar la propuesta", "", () => { fijarParrafo(p.frases.map((f) => [f[0], f[1]])); pintarUno(false); }],
           ["Editar", "secundario", () => pintarUno(true)]];
      bloque.appendChild(el("div", { class: "botones-parrafo" }, botones.map(([texto, clase, accion]) => {
        const b = el("button", { type: "button", class: clase || null }, [texto]);
        b.addEventListener("click", accion);
        return b;
      })));
      (FALTAS[9] || []).filter((x) => x.startsWith(`revision.parrafos.${p.id}`)).forEach((x) => bloque.appendChild(el("div", { class: "falta" }, [legible(x)])));
    };
    pintarUno(false);
    caja.appendChild(bloque);
  });
  // F10: aceptar de una vez los párrafos que siguen sin validar (lo ya aceptado o editado con la huella vigente no se toca)
  const sinValidar = PROPUESTAS.filter((p) => estadoParrafo(p, obtener(DATOS, `revision.parrafos.${p.id}`)) !== "aceptado"
    && estadoParrafo(p, obtener(DATOS, `revision.parrafos.${p.id}`)) !== "editado");
  if (sinValidar.length > 1) {
    const todos = el("button", { type: "button", id: "aceptar-todos", class: "secundario" }, [`Aceptar las ${sinValidar.length} propuestas sin validar`]);
    todos.addEventListener("click", () => {
      sinValidar.forEach((p) => fijar(DATOS, `revision.parrafos.${p.id}`, { propuesta: p.huella, frases: p.frases.map((f) => [f[0], f[1]]), editado: false }));
      pintar();
    });
    caja.insertBefore(todos, caja.firstChild);
  }
  caja.appendChild(el("div", { class: "pista" }, ["Lo aceptado o editado se guarda con «Guardar» y queda congelado en las entradas."]));
  return caja;
}
function editor(c, valor, cambio, anidado) {
  switch (c.tipo) {
    case "texto": return editorTexto(c, valor, cambio, !anidado && esProsa(c));
    case "numero": case "pct": return editorNumero(c, valor, cambio);
    case "fecha": return editorFecha(c, valor, cambio);
    case "enum": return editorEnum(c, valor, cambio);
    case "bool": return editorBool(c, valor, cambio);
    case "serie": return editorSerie(c, valor, cambio);
    case "evidencia": return editorLista(c, valor, cambio, CITA);
    case "lista": return editorLista(c, valor, cambio, c.campos);
    case "escenarios": return editorEscenarios(c);
    case "parrafos": return editorParrafos();
    case "solo_lectura": return el("div", { class: "pista" }, ["Lo calcula el sistema al generar el informe."]);
    case "accion": {
      const a = el("a", { href: `/informe?ticker=${encodeURIComponent(TICKER)}`, class: "boton" }, ["Ir a la emisión del informe →"]);
      return a;
    }
    default: return editorTexto(c, valor, cambio, false);
  }
}
// ---- F10: lo que propone el sistema. No es una entrada hasta que el analista lo confirma: al confirmar, el valor y su
// origen (fuente, motivo, huella) se escriben en DATOS y «Guardar» los guarda. Si luego lo cambia, pasa a ser suyo.
function vacio(v) { return v === undefined || v === null || v === "" || (Array.isArray(v) && !v.length); }
function confirmar(id, p) {
  fijar(DATOS, id, p.valor);
  if (!DATOS._origen || typeof DATOS._origen !== "object") DATOS._origen = {};
  DATOS._origen[id] = { tipo: "propuesta", fuente: p.fuente, motivo: p.motivo, huella: p.huella, valor: p.valor };
}
function nodoPropuesta(c, valor) {
  const p = PROPUESTAS_CAMPOS[c.id];
  const origen = DATOS._origen && DATOS._origen[c.id];
  if (!vacio(valor) && origen && origen.tipo === "propuesta") {
    return el("div", { class: "propuesta confirmada" }, [`✓ Confirmado desde la propuesta del sistema · ${origen.fuente}`]);
  }
  if (!p) return null;
  if (p.sin !== undefined) return vacio(valor) ? el("div", { class: "propuesta sin" }, [`○ Sin propuesta del sistema: ${p.sin}`]) : null;
  if (!vacio(valor)) return null;
  const uno = (x) => (x && typeof x === "object" ? (x.kpi || x.evento || x.texto || Object.values(x)[0] || "") : typeof x === "string" ? valorEnum(x) : String(x));
  const mostrado = Array.isArray(p.valor) ? p.valor.map(uno).join(" · ") : typeof p.valor === "boolean" ? (p.valor ? "sí" : "no") : uno(p.valor);
  const b = el("button", { type: "button", class: "secundario" }, ["Confirmar"]);
  b.addEventListener("click", () => { confirmar(c.id, p); pintar(); });
  return el("div", { class: "propuesta", "data-propuesta": c.id, title: p.motivo }, [
    el("span", { class: "marca" }, ["◇ Propuesto: "]), el("strong", {}, [mostrado]), ` · ${p.fuente} `, b,
  ]);
}
function campoNodo(c, valor, cambio, anidado) {
  const faltas = (FALTAS[PASO] || []).filter((f) => !anidado && f.split(":")[0].split("[")[0] === c.id);
  const propuesta = anidado ? null : nodoPropuesta(c, valor);
  return el("div", { class: "campo" }, [
    el("span", { class: "rotulo" }, [rotulo(c.id)]),
    ...(pista(c) ? [el("span", { class: "pista" }, [pista(c)])] : []),
    ...(propuesta ? [propuesta] : []),
    editor(c, valor, cambio, anidado),
    ...faltas.map((f) => el("div", { class: "falta" }, [legible(f)])),
  ]);
}
function botonBloque(p) {
  // solo lo que `config/propuestas.yaml` deja confirmar en bloque, y solo si el campo está vacío
  const pendientes = p.campos.filter((c) => PROPUESTAS_CAMPOS[c.id] && PROPUESTAS_CAMPOS[c.id].bloque && vacio(obtener(DATOS, c.id)));
  if (!pendientes.length) return null;
  const b = el("button", { type: "button", id: "confirmar-bloque", class: "secundario" }, [`Confirmar las propuestas de este paso (${pendientes.length})`]);
  b.addEventListener("click", () => { pendientes.forEach((c) => confirmar(c.id, PROPUESTAS_CAMPOS[c.id])); pintar(); });
  return b;
}

// ---- pintar
function pintarPasos() {
  const nav = vaciar(document.getElementById("pasos-asistente"));
  ESQUEMA.forEach((p) => {
    const n = (FALTAS[p.numero] || []).length;
    const b = el("button", { type: "button", class: p.numero === PASO ? "actual" : "" }, [p.paso, el("span", { class: n ? "cuenta" : "cuenta cero" }, [n ? ` (${n})` : " ✓"])]);
    b.addEventListener("click", () => { PASO = p.numero; pintar(); });
    nav.appendChild(b);
  });
}
function pintar() {
  pintarPasos();
  const p = ESQUEMA.find((x) => x.numero === PASO) || ESQUEMA[0];
  document.getElementById("titulo-paso").textContent = `Paso ${p.paso}`;
  const campos = vaciar(document.getElementById("campos"));
  const bloque = botonBloque(p);
  if (bloque) campos.appendChild(bloque);
  p.campos.forEach((c) => campos.appendChild(campoNodo(c, obtener(DATOS, c.id), (v) => fijar(DATOS, c.id, v), false)));
  const lista = vaciar(document.getElementById("faltas"));
  (FALTAS[PASO] || []).forEach((f) => lista.appendChild(el("li", {}, [legible(f)])));
  if (!(FALTAS[PASO] || []).length) lista.appendChild(el("li", { class: "ok" }, ["Nada: el paso está completo."]));
}
function avisar(notas) {
  const lista = vaciar(document.getElementById("notas"));
  notas.forEach((n) => lista.appendChild(el("li", {}, [n])));
  document.getElementById("avisos-tarjeta").hidden = !notas.length;
}

async function cargar() {
  if (!TICKER) { document.getElementById("titulo-paso").textContent = "Falta el ticker: /asistente?ticker=QCOM"; return; }
  const r = await fetch(`/api/asistente?ticker=${encodeURIComponent(TICKER)}${FECHA ? `&fecha=${encodeURIComponent(FECHA)}` : ""}`);
  const d = await r.json();
  if (!r.ok) { document.getElementById("titulo-paso").textContent = d.error || "No se pudo cargar"; return; }
  ESQUEMA = d.esquema; DATOS = d.entradas || {}; FALTAS = d.faltas || {}; PROPUESTAS = d.propuestas || []; FECHA = d.fecha;
  PROPUESTAS_CAMPOS = d.propuestas_campos || {};
  document.getElementById("empresa").textContent = `Asistente del analista · ${TICKER}`;
  document.getElementById("a-expediente").setAttribute("href", `/?ticker=${encodeURIComponent(TICKER)}`);
  document.getElementById("a-informe").setAttribute("href", `/informe?ticker=${encodeURIComponent(TICKER)}`);
  document.getElementById("fecha-informe").textContent = `informe del ${FECHA.split("-").reverse().join("/")}`;
  avisar([...(d.notas || []), ...(d.avisos || [])]);
  pintar();
}
async function guardar(ev) {
  ev.preventDefault();
  const estado = document.getElementById("estado-guardado");
  estado.textContent = "Guardando…";
  const r = await fetch(`/api/asistente?ticker=${encodeURIComponent(TICKER)}&fecha=${encodeURIComponent(FECHA)}`, {
    method: "POST", headers: { "Content-Type": "application/json", "X-Formulario": "saas" }, body: JSON.stringify({ entradas: DATOS }),
  });
  const d = await r.json();
  if (!r.ok) { estado.textContent = d.error || "No se ha guardado"; return; }
  FALTAS = d.faltas || {};
  estado.textContent = `Guardado en ${d.carpeta}/${d.guardado}`;
  avisar(d.avisos || []);
  pintar();
}
document.getElementById("asistente").addEventListener("submit", guardar);
document.getElementById("anterior").addEventListener("click", () => { PASO = Math.max(1, PASO - 1); pintar(); });
document.getElementById("siguiente").addEventListener("click", () => { PASO = Math.min(ESQUEMA.length, PASO + 1); pintar(); });
cargar();
