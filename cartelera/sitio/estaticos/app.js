// La Gestoría Cultural: filtros, carriles por día, mapa y "Planeá tu mes".
// Los datos vienen precalculados desde Python; acá solo se filtra y se dibuja.
(function () {
  "use strict";

  const datos = JSON.parse(document.getElementById("datos").textContent);
  const deposito = document.getElementById("eventos"); // tarjetas generadas en Python, siempre ocultas
  const tarjetas = new Map(Array.from(deposito.children).map((li) => [li.dataset.id, li]));

  // --- Utilidades --------------------------------------------------------------------------------
  // Crea un elemento con atributos e hijos; el texto va siempre como texto, nunca como HTML.
  function el(etiqueta, atributos = {}, ...hijos) {
    const nodo = document.createElement(etiqueta);
    for (const [clave, valor] of Object.entries(atributos)) {
      if (clave === "class") nodo.className = valor;
      else if (clave.startsWith("data-")) nodo.dataset[clave.slice(5).replace(/-(.)/g, (_, c) => c.toUpperCase())] = valor;
      else nodo.setAttribute(clave, valor);
    }
    nodo.append(...hijos.filter((h) => h !== null && h !== undefined && h !== false));
    return nodo;
  }

  // Un flyer que no carga (la fuente lo borró o cambió) se saca y queda el fondo con el tipo de evento.
  // El evento "error" de una imagen no burbujea: se escucha en la fase de captura.
  document.addEventListener("error", (e) => {
    if (e.target instanceof HTMLImageElement && e.target.closest(".flyer")) e.target.remove();
  }, true);

  // La dirección pública del sitio (la "canonical" de la página), para los mensajes que se comparten.
  const URL_SITIO = document.querySelector('link[rel="canonical"]')?.href || `${location.origin}${location.pathname}`;
  const plano = (texto) => (texto || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
  const plural = (n, palabra) => `${n} ${palabra}${n === 1 ? "" : "s"}`;
  const mayuscula = (texto) => texto.charAt(0).toUpperCase() + texto.slice(1);

  // --- Fechas en hora de Montevideo --------------------------------------------------------------
  const ZONA = "America/Montevideo";
  const hoy = new Intl.DateTimeFormat("en-CA", { timeZone: ZONA }).format(new Date()); // "AAAA-MM-DD"
  const DIAS = ["dom", "lun", "mar", "mié", "jue", "vie", "sáb"];
  const DIAS_LARGOS = ["Domingo", "Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado"];
  const MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
    "septiembre", "octubre", "noviembre", "diciembre"];

  // Aritmética de días sobre fechas "AAAA-MM-DD", sin depender de la zona horaria del navegador.
  const aFecha = (dia) => new Date(dia + "T12:00:00Z");
  const sumarDias = (dia, n) => new Date(aFecha(dia).getTime() + n * 86400000).toISOString().slice(0, 10);
  const diaSemana = (dia) => aFecha(dia).getUTCDay(); // 0 = domingo
  const rango = (desde, cantidad) => Array.from({ length: cantidad }, (_, i) => sumarDias(desde, i));
  const sumarMeses = (mes, n) => {
    const [anio, numero] = mes.split("-").map(Number);
    return new Date(Date.UTC(anio, numero - 1 + n, 1)).toISOString().slice(0, 7);
  };
  const nombreMes = (mes) => {
    const [anio, numero] = mes.split("-").map(Number);
    return `${MESES[numero - 1]} ${anio}`;
  };

  function textoFuncion([inicio, sinHora]) {
    const dia = inicio.slice(0, 10);
    const [, mes, numero] = dia.split("-").map(Number);
    const fecha = `${DIAS[diaSemana(dia)]} ${numero} ${MESES[mes - 1].slice(0, 3)}`;
    return sinHora ? fecha : `${fecha} · ${inicio.slice(11, 16)}`;
  }

  function tituloDia(dia) {
    const [, mes, numero] = dia.split("-").map(Number);
    return `${DIAS_LARGOS[diaSemana(dia)]} ${numero} de ${MESES[mes - 1]}`;
  }

  // --- Eventos -----------------------------------------------------------------------------------
  // La cartelera se arma unas veces por día, así que al abrir la página se sacan las funciones que ya
  // empezaron (las de hoy con hora anterior a ahora) y los días sin hora que ya pasaron. Un evento que se
  // queda sin funciones no se muestra; los que nunca tuvieron (alguna muestra) quedan como están.
  const ahoraAlAbrir = Date.now();
  const sigueVigente = ([inicio, sinHora]) => (sinHora ? inicio.slice(0, 10) >= hoy : Date.parse(inicio) > ahoraAlAbrir);
  const eventos = datos.eventos
    .map((e) => ({ ...e, funciones: e.funciones.filter(sigueVigente), teniaFunciones: e.funciones.length > 0 }))
    .filter((e) => e.funciones.length || !e.teniaFunciones)
    .map((e) => ({
      ...e,
      dias: e.funciones.map(([inicio]) => inicio.slice(0, 10)),
      textoPlano: plano(e.texto),
      tarjeta: tarjetas.get(e.id),
    }));
  const porId = new Map(eventos.map((e) => [e.id, e]));
  // El orden de los rubros dentro de cada día de la Agenda; los que no están en la lista van después, juntos.
  const RUBROS_PRIMERO = ["musica", "tour", "teatro", "humor", "danza"];
  const ordenRubro = (evento) => {
    const lugar = RUBROS_PRIMERO.indexOf(evento.categoria);
    return lugar === -1 ? RUBROS_PRIMERO.length : lugar;
  };
  const nombreLugar = (evento) => datos.lugares[evento.lugar]?.nombre || "";

  // --- Mi plan: funciones elegidas, guardadas en este navegador ---------------------------------
  const CLAVE_PLAN = "lgc-plan";
  // "entradas": la persona marcó que ya las tiene (confirmado); si no, es algo que le tienta (tentativo).
  const plan = new Map(); // "id|inicio" -> { id, inicio, sinHora, entradas }
  const clavePlan = (id, inicio) => `${id}|${inicio}`;
  try {
    for (const [id, inicio, sinHora, entradas] of JSON.parse(localStorage.getItem(CLAVE_PLAN) || "[]")) {
      // Se descarta lo que ya no está en la cartelera (función pasada o evento que se cayó).
      if (porId.get(id)?.funciones.some(([i]) => i === inicio)) {
        plan.set(clavePlan(id, inicio), { id, inicio, sinHora, entradas: Boolean(entradas) });
      }
    }
  } catch (_) { /* sin almacenamiento disponible: el plan dura lo que la pestaña */ }

  function guardarPlan() {
    try {
      localStorage.setItem(CLAVE_PLAN, JSON.stringify([...plan.values()].map((p) => [p.id, p.inicio, p.sinHora, p.entradas ? 1 : 0])));
    } catch (_) { /* idem */ }
  }

  function alternarPlan(id, inicio) {
    const clave = clavePlan(id, inicio);
    if (plan.has(clave)) plan.delete(clave);
    else plan.set(clave, { id, inicio, sinHora: porId.get(id).funciones.find(([i]) => i === inicio)?.[1] || false, entradas: false });
    guardarPlan();
  }

  // Un cartelito que aparece un momento arriba de un botón, para explicar qué hizo ("Tengo entradas").
  let globito = null;
  let esperaGlobito = null;
  function mostrarGlobito(boton, texto) {
    if (!globito) {
      globito = el("div", { class: "globito", role: "status" });
      document.body.appendChild(globito);
    }
    globito.textContent = texto;
    globito.classList.remove("visible");
    const r = boton.getBoundingClientRect();
    const ancho = globito.offsetWidth;
    const izquierda = Math.min(Math.max(8, r.left + r.width / 2 - ancho / 2), document.documentElement.clientWidth - ancho - 8);
    globito.style.left = `${izquierda + window.scrollX}px`;
    globito.style.top = `${r.top + window.scrollY - globito.offsetHeight - 10}px`;
    globito.style.setProperty("--flecha", `${r.left + r.width / 2 - izquierda}px`);
    requestAnimationFrame(() => globito.classList.add("visible"));
    clearTimeout(esperaGlobito);
    esperaGlobito = setTimeout(() => globito.classList.remove("visible"), 1800);
  }

  // El botón 🎟️ de las listas del plan: marca (o desmarca) que ya tenés entradas para esa función.
  function botonEntradas(p, evento) {
    return el("button", {
      type: "button", class: `entradas${p.entradas ? " con-entradas" : ""}`, "data-entradas": clavePlan(p.id, p.inicio),
      "aria-pressed": String(Boolean(p.entradas)), "aria-label": `Ya tengo entradas para ${evento.titulo}`,
      title: p.entradas ? "Ya tenés entradas (tocá para desmarcar)" : "Marcá si ya tenés entradas",
    }, el("span", { "aria-hidden": "true" }, "🎟️"));
  }

  const elegidasOrdenadas = () => [...plan.values()].sort((a, b) => a.inicio.localeCompare(b.inicio));

  // --- Estado de los filtros --------------------------------------------------------------------
  const FILTROS_INICIALES = {
    periodo: "todo", dia: null, categoria: "", etiqueta: "", sub: "",
    presupuesto: "", programa: "", sala: "", ciclo: "", texto: "", excluir: [],
  };
  let estado = { seccion: "agenda", mes: hoy.slice(0, 7), planMes: hoy.slice(0, 7), ...FILTROS_INICIALES };

  // Etiquetas que cruzan rubros: se filtran y se excluyen como un tipo más.
  const NOMBRE_ETIQUETA = { festival: "Festivales", museo: "Museos" };

  // Lo excluido ("nada de infantil") queda guardado en este navegador, como el plan.
  const CLAVE_EXCLUIR = "lgc-excluir";
  try {
    const guardado = JSON.parse(localStorage.getItem(CLAVE_EXCLUIR) || "[]");
    estado.excluir = guardado.filter((c) => c in NOMBRE_ETIQUETA || c in datos.categorias);
  } catch (_) { /* sin almacenamiento disponible: la exclusión dura lo que la pestaña */ }

  function guardarExcluir() {
    try { localStorage.setItem(CLAVE_EXCLUIR, JSON.stringify(estado.excluir)); } catch (_) { /* idem */ }
  }

  // Bienvenida de la primera visita: se muestra hasta que se cierra.
  const CLAVE_BIENVENIDA = "lgc-bienvenida";
  let bienvenidaVista = false;
  try { bienvenidaVista = localStorage.getItem(CLAVE_BIENVENIDA) === "vista"; } catch (_) { /* sin almacenamiento: se muestra cada vez */ }

  function cerrarBienvenida() {
    bienvenidaVista = true;
    document.getElementById("bienvenida").hidden = true;
    try { localStorage.setItem(CLAVE_BIENVENIDA, "vista"); } catch (_) { /* idem */ }
    document.getElementById("resultados").focus({ preventScroll: true });
  }

  function diasDelPeriodo() {
    if (estado.periodo === "dia") return [estado.dia];
    if (estado.periodo === "hoy") return [hoy];
    if (estado.periodo === "manana") return [sumarDias(hoy, 1)];
    if (estado.periodo === "semana") return rango(hoy, 7);
    if (estado.periodo === "finde") {
      const semana = diaSemana(hoy);
      const desde = semana === 0 || semana >= 5 ? 0 : 5 - semana; // desde el viernes (o hoy, si ya es finde)
      const hasta = semana === 0 ? 0 : 7 - semana; // hasta el domingo
      return rango(sumarDias(hoy, desde), hasta - desde + 1);
    }
    return null; // "todo"
  }

  function coincide(evento, { ignorarFecha = false } = {}) {
    const s = estado.seccion;
    if (s === "gratis" && evento.presupuesto !== "gratis") return false;
    if (s === "promos" && !evento.promos.length) return false;
    if (s === "festivales" && !evento.etiquetas.includes("festival")) return false;
    // Lo excluido no aparece, salvo en su propia pestaña (en Festivales se ven los festivales aunque estén excluidos).
    if (estado.excluir.includes(evento.categoria)) return false;
    for (const etiqueta of evento.etiquetas) {
      if (estado.excluir.includes(etiqueta) && !(etiqueta === "festival" && s === "festivales")) return false;
    }
    if (estado.categoria && evento.categoria !== estado.categoria) return false;
    if (estado.etiqueta && !evento.etiquetas.includes(estado.etiqueta)) return false;
    if (estado.sub === "otros" && evento.sub) return false;
    if (estado.sub && estado.sub !== "otros" && evento.sub !== estado.sub) return false;
    if (estado.presupuesto && s !== "gratis" && evento.presupuesto !== estado.presupuesto) return false;
    if (estado.programa && !evento.promos.includes(estado.programa)) return false;
    if (estado.sala && evento.lugar !== estado.sala) return false;
    if (estado.ciclo && evento.ciclo !== estado.ciclo) return false;
    if (estado.texto && !evento.textoPlano.includes(plano(estado.texto))) return false;
    if (s === "plan") return evento.dias.some((d) => d.startsWith(estado.planMes));
    if (!ignorarFecha) {
      const dias = diasDelPeriodo();
      if (dias && !evento.dias.some((d) => dias.includes(d))) return false;
    }
    return true;
  }

  // --- Filtros activos: chips que se borran de a uno -------------------------------------------
  const NOMBRE_PERIODO = { hoy: "Hoy", manana: "Mañana", finde: "Este finde", semana: "Próximos 7 días", todo: "Todas las fechas" };
  const NOMBRE_PRECIO = Object.fromEntries(
    Array.from(document.querySelectorAll("#presupuestos button")).map((b) => [b.dataset.presupuesto, b.firstChild.textContent.trim()]),
  );

  function filtrosActivos() {
    const activos = [];
    if (estado.periodo !== "todo" && estado.seccion !== "plan") {
      activos.push(["periodo", estado.periodo === "dia" ? textoFuncion([estado.dia, true]) : NOMBRE_PERIODO[estado.periodo]]);
    }
    if (estado.categoria) activos.push(["categoria", datos.categorias[estado.categoria]]);
    if (estado.etiqueta) activos.push(["etiqueta", NOMBRE_ETIQUETA[estado.etiqueta] || estado.etiqueta]);
    if (estado.sub) {
      const otros = datos.subcategoriasOtros[estado.categoria] || "Otros";
      activos.push(["sub", estado.sub === "otros" ? otros : (datos.subcategorias[estado.categoria] || {})[estado.sub]]);
    }
    if (estado.presupuesto && estado.seccion !== "gratis") activos.push(["presupuesto", NOMBRE_PRECIO[estado.presupuesto]]);
    if (estado.programa) activos.push(["programa", estado.programa]);
    if (estado.sala) activos.push(["sala", datos.lugares[estado.sala]?.nombre || "Sala"]);
    if (estado.ciclo) {
      const nombre = datos.ciclos[estado.ciclo];
      activos.push(["ciclo", /^ciclo/i.test(nombre) ? nombre : `Ciclo: ${nombre}`]);
    }
    if (estado.texto.trim()) activos.push(["texto", `“${estado.texto.trim()}”`]);
    for (const clave of estado.excluir) {
      activos.push([`excluir:${clave}`, `Sin ${(NOMBRE_ETIQUETA[clave] || datos.categorias[clave]).toLowerCase()}`]);
    }
    return activos;
  }

  function dibujarActivos() {
    const activos = filtrosActivos();
    const chips = activos.map(([clave, texto]) => el("button", {
      type: "button", class: "chip-activo", "data-borrar": clave, "aria-label": `Quitar filtro: ${texto}`,
    }, el("span", {}, texto), el("span", { "aria-hidden": "true" }, "×")));
    if (activos.length > 1) chips.push(el("button", { type: "button", class: "borrar-todo", "data-borrar": "todo" }, "Borrar todo"));
    document.getElementById("activos").replaceChildren(...chips);
    document.querySelector(".filtros-titulo .borrar-todo").hidden = activos.length === 0;
    for (const cuenta of document.querySelectorAll(".cuenta-filtros")) {
      cuenta.hidden = activos.length === 0;
      cuenta.textContent = activos.length;
    }
  }

  function borrar(clave) {
    if (clave === "todo") return { ...FILTROS_INICIALES };
    if (clave === "periodo") return { periodo: "todo", dia: null };
    if (clave === "categoria") return { categoria: "", sub: "" };
    if (clave.startsWith("excluir:")) return { excluir: estado.excluir.filter((c) => c !== clave.slice(8)) };
    return { [clave]: FILTROS_INICIALES[clave] };
  }

  // --- Carriles: un carril por día, que se desliza de costado -----------------------------------
  // Así la página se recorre día por día y no evento por evento. Las temporadas y muestras largas
  // van una sola vez, en el carril "En cartel", para no repetirse todos los días.
  const DIAS_POR_TANDA = 6;
  let carrilesPendientes = [];
  let observador = null;

  function marcarBotonPlan(boton, id, inicio) {
    const enPlan = plan.has(clavePlan(id, inicio));
    boton.dataset.agregarFuncion = clavePlan(id, inicio);
    boton.textContent = enPlan ? "✓ En mi plan" : "＋ Mi plan";
    boton.classList.toggle("en-plan", enPlan);
    // Para lectores de pantalla: el botón dice de qué evento es y si ya está en el plan.
    boton.setAttribute("aria-pressed", String(enPlan));
    boton.setAttribute("aria-label", `Mi plan: ${porId.get(id)?.titulo || ""}, ${textoFuncion([inicio, false])}`);
    boton.title = enPlan ? "Quitar de mi plan" : `Agregar la función del ${textoFuncion([inicio, false])} a mi plan`;
  }

  // "Invitá a alguien": comparte una función con el menú del celular (WhatsApp, Telegram, mail…) o, si el
  // navegador no lo tiene, abre WhatsApp con el mensaje armado.
  function marcarCompartir(boton, evento, inicio) {
    if (!boton) return;
    boton.dataset.compartir = clavePlan(evento.id, inicio);
    boton.setAttribute("aria-label", `Invitá a alguien a ${evento.titulo}`);
  }

  async function compartir(id, inicio) {
    const evento = porId.get(id);
    const sinHora = evento.funciones.find(([i]) => i === inicio)?.[1] ?? false;
    const texto = [
      `¿Vamos? ${evento.titulo}`,
      `📅 ${mayuscula(textoFuncion([inicio, sinHora]))}`,
      `📍 ${[nombreLugar(evento), evento.precioTexto].filter(Boolean).join(" · ")}`,
      `🎟️ ${evento.url}`,
      "",
      `Lo vi en La Gestoría Cultural: ${URL_SITIO}`,
    ].join("\n");
    if (navigator.share) {
      try {
        await navigator.share({ title: evento.titulo, text: texto });
        return;
      } catch (error) {
        if (error.name === "AbortError") return; // la persona cerró el menú
      }
    }
    window.open(`https://wa.me/?text=${encodeURIComponent(texto)}`, "_blank", "noopener");
  }

  // Copia de la tarjeta de un evento, mostrando una función en particular.
  function tarjetaPara(evento, [inicio, sinHora]) {
    const copia = evento.tarjeta.cloneNode(true);
    const hora = copia.querySelector(".proxima");
    if (!hora) { // una exposición: muestra su período, igual en todos los días
      marcarBotonPlan(copia.querySelector(".agregar-plan"), evento.id, inicio);
      marcarCompartir(copia.querySelector(".compartir"), evento, inicio);
      return copia;
    }
    hora.textContent = textoFuncion([inicio, sinHora]);
    hora.dateTime = inicio;
    const otras = evento.funciones.length - 1;
    const mas = copia.querySelector(".mas");
    if (mas) mas.textContent = otras ? `+${plural(otras, "función").replace("funcións", "funciones")}` : "";
    marcarBotonPlan(copia.querySelector(".agregar-plan"), evento.id, inicio);
    marcarCompartir(copia.querySelector(".compartir"), evento, inicio);
    return copia;
  }

  // En el celular cada día es una lista (no un carril de costado) y muestra los primeros; el resto, con "Ver los…".
  const VISIBLES_EN_LISTA = 5;

  // Cada día se puede plegar tocando su título (por ejemplo, para saltear hoy y ver los próximos días).
  const carrilesPlegados = new Set();

  function carril(titulo, detalle, elementos, clase = "", clave = titulo) {
    const plegado = carrilesPlegados.has(clave);
    const idPista = `carril-${clave.replace(/[^\w-]/g, "")}`;
    const pista = el("ul", { class: "carril-pista", id: idPista }, ...elementos);
    const recortado = elementos.length > VISIBLES_EN_LISTA;
    const verTodos = recortado
      ? el("button", { type: "button", class: "ver-todos", "data-ver-todos": "" }, `Ver los ${elementos.length} eventos`)
      : null;
    return el("section", { class: `carril ${clase} ${recortado ? "recortado" : ""} ${plegado ? "plegado" : ""}`.replace(/\s+/g, " ").trim() },
      el("header", { class: "carril-cabezal" },
        el("h2", {}, el("button", {
          type: "button", class: "carril-plegar", "data-plegar-carril": clave, "aria-expanded": String(!plegado), "aria-controls": idPista,
        }, el("span", { class: "chevron", "aria-hidden": "true" }, "▾"), titulo, detalle ? el("small", {}, detalle) : null)),
        el("div", { class: "carril-flechas" },
          el("button", { type: "button", class: "cal-flecha", "data-desplazar": "-1", "aria-label": "Anteriores" }, "‹"),
          el("button", { type: "button", class: "cal-flecha", "data-desplazar": "1", "aria-label": "Siguientes" }, "›"))),
      pista, verTodos);
  }

  function nombreCarril(dia) {
    if (dia === hoy) return `Hoy · ${tituloDia(dia).toLowerCase()}`;
    if (dia === sumarDias(hoy, 1)) return `Mañana · ${tituloDia(dia).toLowerCase()}`;
    return tituloDia(dia);
  }

  function dibujarCarriles() {
    const contenedor = document.getElementById("carriles");
    const visibles = eventos.filter((e) => coincide(e));
    const dias = diasDelPeriodo();
    const enRango = (dia) => dia >= hoy && (!dias || dias.includes(dia));

    const enCartel = visibles.filter((e) => e.enCartel);
    const porDia = new Map();
    for (const evento of visibles) {
      if (evento.enCartel) continue;
      const vistos = new Set();
      for (const funcion of evento.funciones) {
        const dia = funcion[0].slice(0, 10);
        if (!enRango(dia) || vistos.has(dia)) continue;
        vistos.add(dia);
        if (!porDia.has(dia)) porDia.set(dia, []);
        porDia.get(dia).push([evento, funcion]);
      }
    }

    const secciones = [];
    for (const dia of [...porDia.keys()].sort()) {
      // Primero lo que tiene hora; al final lo que no tiene (exposiciones, actividades de todo el día). Entre lo
      // que tiene hora, primero los rubros que más invitan a salir (si no, de mañana arranca siempre con cine),
      // y dentro de cada uno, por hora.
      const items = porDia.get(dia).sort((a, b) => (a[1][1] - b[1][1])
        || (ordenRubro(a[0]) - ordenRubro(b[0]))
        || a[1][0].localeCompare(b[1][0]));
      secciones.push(() => carril(nombreCarril(dia), plural(items.length, "evento"),
        items.map(([e, f]) => tarjetaPara(e, f)), diaSemana(dia) % 6 === 0 ? "carril-finde" : "", dia));
    }
    // Lo que se repite durante semanas (temporadas, exposiciones, talleres) va al final, con su título:
    // no tapa lo que pasa cada día, pero tampoco se esconde.
    if (enCartel.length) {
      const items = enCartel.map((e) => [e, e.funciones.find(([i]) => enRango(i.slice(0, 10))) || e.funciones[0]])
        .sort((a, b) => a[1][0].localeCompare(b[1][0]));
      secciones.push(() => carril("Con muchas fechas · en exhibición", "obras, exposiciones, talleres y visitas que se repiten durante semanas",
        items.map(([e, f]) => tarjetaPara(e, f)), "carril-cartel", "en-cartel"));
    }

    // Se dibujan de a tandas a medida que se baja, para no armar cientos de tarjetas de una.
    observador?.disconnect();
    contenedor.replaceChildren();
    carrilesPendientes = secciones;
    const centinela = el("div", { class: "centinela", "aria-hidden": "true" });
    const tanda = () => {
      for (const armar of carrilesPendientes.splice(0, DIAS_POR_TANDA)) contenedor.insertBefore(armar(), centinela);
      if (!carrilesPendientes.length) observador?.disconnect();
    };
    contenedor.appendChild(centinela);
    tanda();
    if (carrilesPendientes.length && "IntersectionObserver" in window) {
      observador = new IntersectionObserver((entradas) => {
        if (entradas.some((e) => e.isIntersecting)) tanda();
      }, { rootMargin: "800px" });
      observador.observe(centinela);
    } else {
      while (carrilesPendientes.length) tanda();
    }

    const cantidad = visibles.length;
    document.getElementById("resumen").replaceChildren(el("strong", {}, String(cantidad)),
      ` evento${cantidad === 1 ? "" : "s"} · ${estado.periodo === "dia" ? textoFuncion([estado.dia, true]) : NOMBRE_PERIODO[estado.periodo].toLowerCase()}`,
      porDia.size > 1 ? ` · ${porDia.size} días` : "");
    document.getElementById("vacio").hidden = cantidad > 0;
  }

  // --- Calendario chico del costado (elige un día en la agenda) ---------------------------------
  function dibujarCalendario() {
    const [anio, mes] = estado.mes.split("-").map(Number);
    document.getElementById("cal-mes").textContent = nombreMes(estado.mes);
    const primero = `${estado.mes}-01`;
    const diasEnMes = new Date(Date.UTC(anio, mes, 0)).getUTCDate();

    const conteo = new Map();
    for (const evento of eventos) {
      if (!coincide(evento, { ignorarFecha: true })) continue;
      for (const dia of new Set(evento.dias)) conteo.set(dia, (conteo.get(dia) || 0) + 1);
    }
    const maximo = Math.max(1, ...rango(primero, diasEnMes).map((d) => conteo.get(d) || 0));
    const periodo = diasDelPeriodo();

    const celdas = [];
    for (let i = 0; i < (diaSemana(primero) + 6) % 7; i++) celdas.push(el("span", { class: "cal-dia fuera" }));
    for (const dia of rango(primero, diasEnMes)) {
      const cantidad = conteo.get(dia) || 0;
      // Hasta 0.62 de cobalto: más oscuro, el número deja de leerse con contraste suficiente.
      const intensidad = 0.12 + 0.5 * cantidad / maximo;
      const boton = el("button", {
        type: "button", "data-dia": dia, "aria-label": `${textoFuncion([dia, true])}: ${plural(cantidad, "evento")}`,
        class: ["cal-dia", dia === hoy && "hoy", dia < hoy && "pasado", !cantidad && "sin-eventos",
          estado.periodo === "dia" && estado.dia === dia && "elegido",
          periodo && estado.periodo !== "dia" && periodo.includes(dia) && "en-periodo"].filter(Boolean).join(" "),
      }, String(Number(dia.slice(8))), el("small", {}, cantidad ? String(cantidad) : ""));
      boton.style.setProperty("--intensidad", intensidad.toFixed(2));
      boton.disabled = dia < hoy;
      celdas.push(boton);
    }
    document.getElementById("cal-grilla").replaceChildren(...celdas);
  }

  // --- Mapa -------------------------------------------------------------------------------------
  let mapa = null;
  let capaMarcadores = null;
  // Los colores de la paleta, uno por tipo de lugar (ver TIPOS_DE_LUGAR en generar.py).
  const COLORES_LUGAR = { grande: "#3256A8", sala: "#F06C4F", museo: "#E4A94A", otro: "#F4E9D5" };
  const COLOR_BORDE = "#18264A";

  function cargarLeaflet() {
    if (window.L) return Promise.resolve();
    // Con su hash (integrity): si el archivo del CDN cambiara, el navegador no lo usa.
    document.head.appendChild(el("link", {
      rel: "stylesheet", href: "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css", crossorigin: "anonymous",
      integrity: "sha512-h9FcoyWjHcOcmEVkxOfTLnmZFWIH0iZhZT1H2TbOq55xssQGEJHEaIm+PgoUaZbRvQTNTluNOEfb1ZRy6D3BOw==",
    }));
    return new Promise((resolver, rechazar) => {
      const script = el("script", {
        src: "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js", crossorigin: "anonymous",
        integrity: "sha512-puJW3E/qXDqYp9IfhAI54BJEaWIfloJ7JWs7OeD5i6ruC9JZL1gERT1wjtwXFlh7CjE7ZJ+/vcRZRkIYIb6p4g==",
      });
      script.onload = resolver;
      script.onerror = rechazar;
      document.head.appendChild(script);
    });
  }

  // La rueda del mouse hace zoom solo después de tocar el mapa (si no, al bajar por la página el mapa la
  // atraparía). El pellizco del touchpad llega como rueda con Ctrl y hace zoom siempre; en el celular,
  // el pellizco con dos dedos lo maneja Leaflet.
  function activarZoomConRueda(contenedor) {
    let activa = false;
    let esperaPista = null;
    const pista = el("div", { class: "mapa-pista", "aria-hidden": "true" }, "Tocá el mapa para hacer zoom con la rueda, o pellizcá");
    contenedor.appendChild(pista);
    contenedor.addEventListener("wheel", (e) => {
      if (e.ctrlKey || activa) return;
      e.stopPropagation(); // Leaflet no se entera y la página baja como siempre
      pista.classList.add("visible");
      clearTimeout(esperaPista);
      esperaPista = setTimeout(() => pista.classList.remove("visible"), 1500);
    }, { capture: true });
    contenedor.addEventListener("pointerdown", () => { activa = true; pista.classList.remove("visible"); });
    contenedor.addEventListener("mouseleave", () => { activa = false; });
  }

  // En el celular, como en Google Maps: un dedo mueve la página (el mapa no la atrapa) y dos dedos mueven
  // y acercan el mapa. Sobre el mapa el pellizco siempre es del mapa, así que no agranda la página entera.
  // Si se arrastra con un dedo, aparece la pista.
  const TACTIL = window.matchMedia("(pointer: coarse)").matches;

  function activarDosDedos(contenedor) {
    let esperaPista = null;
    const pista = el("div", { class: "mapa-pista", "aria-hidden": "true" }, "Usá dos dedos para mover y acercar el mapa");
    contenedor.appendChild(pista);
    contenedor.addEventListener("touchmove", (e) => {
      if (e.touches.length !== 1) {
        pista.classList.remove("visible");
        return;
      }
      pista.classList.add("visible");
      clearTimeout(esperaPista);
      esperaPista = setTimeout(() => pista.classList.remove("visible"), 1200);
    }, { passive: true });
  }

  // Un botón para volver a ver todos los puntos, después de haber acercado o movido el mapa.
  let limitesDelMapa = null;
  function agregarBotonVerTodo() {
    const Control = L.Control.extend({
      options: { position: "topleft" },
      onAdd() {
        const caja = el("div", { class: "leaflet-bar ver-todo" });
        const boton = el("button", { type: "button", title: "Volver a ver todo el mapa", "aria-label": "Volver a ver todo el mapa" }, "⤢");
        boton.addEventListener("click", (e) => {
          e.stopPropagation();
          if (limitesDelMapa) mapa.fitBounds(limitesDelMapa, { padding: [30, 30], maxZoom: 15 });
        });
        L.DomEvent.disableClickPropagation(caja);
        caja.appendChild(boton);
        return caja;
      },
    });
    mapa.addControl(new Control());
  }

  async function dibujarMapa() {
    await cargarLeaflet();
    if (!mapa) {
      const contenedor = document.getElementById("mapa");
      mapa = L.map(contenedor, { wheelPxPerZoomLevel: 90, dragging: !TACTIL }).setView([-34.895, -56.17], 12);
      if (TACTIL) activarDosDedos(contenedor);
      else activarZoomConRueda(contenedor);
      agregarBotonVerTodo();
      // Tiles de OpenStreetMap: gratis y sin API key (con atribución). El color se ajusta por CSS.
      L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
        maxZoom: 19,
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
      }).addTo(mapa);
      capaMarcadores = L.layerGroup().addTo(mapa);
    }
    mapa.invalidateSize();
    capaMarcadores.clearLayers();

    const porLugar = new Map();
    for (const evento of eventos) {
      if (coincide(evento)) porLugar.set(evento.lugar, (porLugar.get(evento.lugar) || 0) + 1);
    }
    const puntos = [];
    for (const [lugarId, cantidad] of porLugar) {
      const lugar = datos.lugares[lugarId];
      if (!lugar || lugar.lat == null) continue;
      const boton = el("button", { type: "button", class: "ver-sala" }, "Ver sus eventos");
      boton.addEventListener("click", () => cambiar({ sala: lugarId, seccion: "agenda" }));
      const tipo = lugar.tipo || "otro";
      const punto = L.circleMarker([lugar.lat, lugar.lon], {
        radius: 7 + Math.min(14, Math.sqrt(cantidad) * 3),
        className: `punto tipo-${tipo}`, color: COLOR_BORDE, weight: 2, fillColor: COLORES_LUGAR[tipo], fillOpacity: 0.9,
      }).bindPopup(el("div", {}, el("strong", {}, lugar.nombre), el("br"), el("span", { class: "tipo-popup" }, datos.tiposDeLugar[tipo]), el("br"), plural(cantidad, "evento"), el("br"), boton))
        .bindTooltip(`${lugar.nombre} · ${plural(cantidad, "evento")}`, { direction: "top", offset: [0, -8] })
        .addTo(capaMarcadores);
      // Al pasar el mouse, el punto crece (por CSS) y queda adelante de los vecinos.
      punto.on("mouseover", () => punto.bringToFront());
      puntos.push([lugar.lat, lugar.lon]);
    }
    limitesDelMapa = puntos.length ? puntos : null;
    if (puntos.length) mapa.fitBounds(puntos, { padding: [30, 30], maxZoom: 15 });
  }

  // --- Planeá tu mes: un calendario que se va llenando con lo que elegís -----------------------
  function opcionesDelMes() {
    // { dia: Map(id -> [funciones]) } con lo que cumple los filtros en el mes del plan.
    // Solo lo que todavía no empezó: los días pasados no, y de hoy, las funciones con hora que ya arrancaron tampoco.
    const porDia = new Map();
    const ahora = Date.now();
    for (const evento of eventos) {
      if (!coincide(evento)) continue;
      for (const funcion of evento.funciones) {
        const dia = funcion[0].slice(0, 10);
        if (!dia.startsWith(estado.planMes) || dia < hoy) continue;
        if (dia === hoy && !funcion[1] && Date.parse(funcion[0]) < ahora) continue;
        if (!porDia.has(dia)) porDia.set(dia, new Map());
        const delDia = porDia.get(dia);
        if (!delDia.has(evento.id)) delDia.set(evento.id, []);
        delDia.get(evento.id).push(funcion);
      }
    }
    return porDia;
  }

  function dibujarCalendarioPlan(opciones) {
    const [anio, mes] = estado.planMes.split("-").map(Number);
    document.getElementById("pc-titulo").textContent = mayuscula(nombreMes(estado.planMes));
    document.querySelector("[data-plan-mes='-1']").disabled = estado.planMes <= hoy.slice(0, 7);
    const primero = `${estado.planMes}-01`;
    const elegidasPorDia = new Map();
    for (const p of elegidasOrdenadas()) {
      const dia = p.inicio.slice(0, 10);
      if (!elegidasPorDia.has(dia)) elegidasPorDia.set(dia, []);
      elegidasPorDia.get(dia).push(p);
    }

    const celdas = [];
    for (let i = 0; i < (diaSemana(primero) + 6) % 7; i++) celdas.push(el("div", { class: "pc-dia fuera" }));
    for (const dia of rango(primero, new Date(Date.UTC(anio, mes, 0)).getUTCDate())) {
      const elegidas = elegidasPorDia.get(dia) || [];
      const cantidad = opciones.get(dia)?.size || 0;
      const pasado = dia < hoy;
      celdas.push(el("div", {
        class: ["pc-dia", pasado && "pasado", dia === hoy && "hoy", elegidas.length && "con-plan",
          diaSemana(dia) % 6 === 0 && "finde"].filter(Boolean).join(" "),
      },
      elegidas.length
        ? el("button", {
          type: "button", class: "pc-numero", "data-ver-plan-dia": dia,
          "aria-label": `${tituloDia(dia)}: ${plural(elegidas.length, "evento")} en tu plan. Ver o quitar`,
        }, String(Number(dia.slice(8))))
        : el("span", { class: "pc-numero" }, String(Number(dia.slice(8)))),
      ...elegidas.map((p) => {
        const evento = porId.get(p.id);
        return el("span", { class: `pc-elegida cat-${evento.categoria}${p.entradas ? " con-entradas" : ""}` },
          p.entradas ? el("span", { class: "pc-ticket", "aria-label": "con entradas" }, "🎟️ ") : null,
          el("b", {}, p.sinHora ? "" : p.inicio.slice(11, 16)), ` ${evento.titulo}`,
          el("button", { type: "button", class: "pc-quitar", "data-quitar": clavePlan(p.id, p.inicio), "aria-label": `Quitar ${evento.titulo}` }, "×"));
      }),
      !pasado && cantidad
        ? el("button", { type: "button", class: "pc-opciones", "data-ver-dia": dia, "aria-label": `Ver ${cantidad} opciones del ${tituloDia(dia)}` },
          `${elegidas.length ? "+ " : ""}${cantidad}`, el("span", { class: "pc-palabra" }, " opciones"))
        : null));
    }
    document.getElementById("pc-grilla").replaceChildren(...celdas);
    document.getElementById("pc-ayuda").hidden = !elegidasPorDia.size;
    cantidadOpciones = new Map([...opciones].map(([dia, ids]) => [dia, ids.size]));
    dibujarDetallePlan();
  }

  // El día del plan que se está mirando (al tocarlo en el calendario), y cuántas opciones hay por día.
  let diaDetalle = null;
  let cantidadOpciones = new Map();

  function dibujarDetallePlan() {
    const panel = document.getElementById("pc-detalle");
    const elegidas = diaDetalle ? elegidasOrdenadas().filter((p) => p.inicio.startsWith(diaDetalle)) : [];
    if (!elegidas.length) {
      diaDetalle = null;
      panel.hidden = true;
      return;
    }
    panel.hidden = false;
    panel.replaceChildren(
      el("div", { class: "pc-detalle-cabezal" },
        el("h3", {}, `Tu plan del ${tituloDia(diaDetalle).toLowerCase()}`),
        el("button", { type: "button", class: "quitar", "data-cerrar-detalle": "", "aria-label": "Cerrar" }, "×")),
      el("ul", {}, ...elegidas.map((p) => {
        const evento = porId.get(p.id);
        return el("li", {},
          el("span", { class: "pc-detalle-hora" }, p.sinHora ? "Todo el día" : p.inicio.slice(11, 16)),
          el("span", { class: "mi-plan-evento" },
            el("a", { href: evento.url, target: "_blank", rel: "noopener" }, evento.titulo),
            el("small", {}, nombreLugar(evento))),
          botonEntradas(p, evento),
          el("button", { type: "button", class: "quitar-texto", "data-quitar": clavePlan(p.id, p.inicio), "aria-label": `Quitar ${evento.titulo} de mi plan` }, "Quitar"));
      })),
      cantidadOpciones.get(diaDetalle)
        ? el("button", { type: "button", class: "boton-secundario", "data-ver-dia": diaDetalle }, `Ver las ${cantidadOpciones.get(diaDetalle)} opciones de ese día`)
        : null);
  }

  // Las opciones de un día, en la lista de abajo del calendario: se abre y la página baja hasta ahí.
  function irAlDia(dia) {
    const seccion = document.getElementById(`dia-${dia}`);
    if (!seccion) return;
    seccion.open = true;
    abiertosPlan.add(dia);
    seccion.scrollIntoView({ behavior: suave(), block: "start" });
  }

  function abrirDetallePlan(dia) {
    diaDetalle = dia;
    dibujarDetallePlan();
    const panel = document.getElementById("pc-detalle");
    panel.scrollIntoView({ behavior: suave(), block: "nearest" });
    panel.querySelector("h3").setAttribute("tabindex", "-1");
    panel.querySelector("h3").focus({ preventScroll: true });
  }

  // Google Calendar no importa varios eventos por enlace: con uno solo se abre directo; con más, la lista
  // del plan, donde cada función tiene su enlace.
  function abrirEnGoogle() {
    const elegidas = elegidasOrdenadas();
    if (elegidas.length === 1) {
      window.open(enlaceGoogle(porId.get(elegidas[0].id), elegidas[0]), "_blank", "noopener");
      return;
    }
    const lista = document.getElementById("mi-plan-detalle");
    lista.open = true;
    lista.scrollIntoView({ behavior: suave(), block: "start" });
    lista.querySelector("a.google")?.focus({ preventScroll: true });
  }

  function dibujarMiPlan() {
    const elegidas = elegidasOrdenadas();
    document.getElementById("cuenta-plan").textContent = elegidas.length;
    document.getElementById("mi-plan-vacio").hidden = elegidas.length > 0;
    document.getElementById("mi-plan-acciones").hidden = elegidas.length === 0;
    document.getElementById("mi-plan-detalle").hidden = elegidas.length === 0;
    // Con el plan vacío el calendario va compacto, y crece cuando se suma algo.
    document.querySelector(".plan-cal").classList.toggle("compacto", elegidas.length === 0);
    document.querySelector("[data-vaciar-plan]").hidden = elegidas.length === 0;
    document.getElementById("compartir-whatsapp").href = `https://wa.me/?text=${encodeURIComponent(textoPlan())}`;
    document.getElementById("mi-plan-lista").replaceChildren(...elegidas.map((p) => {
      const evento = porId.get(p.id);
      return el("li", {},
        el("time", { datetime: p.inicio }, textoFuncion([p.inicio, p.sinHora])),
        el("span", { class: "mi-plan-evento" },
          el("a", { href: evento.url, target: "_blank", rel: "noopener" }, evento.titulo),
          el("small", {}, nombreLugar(evento))),
        el("a", { class: "google", href: enlaceGoogle(evento, p), target: "_blank", rel: "noopener" }, "Google Calendar ↗"),
        botonEntradas(p, evento),
        el("button", { type: "button", class: "quitar-texto", "data-quitar": clavePlan(p.id, p.inicio), "aria-label": `Quitar ${evento.titulo} de mi plan` }, "Quitar"));
    }));
  }

  // Desplegables de la lista del plan; recuerdan si estaban abiertos entre un redibujo y otro.
  const abiertosPlan = new Set();
  function desplegable(clave, clase, resumen, ...contenido) {
    const detalles = el("details", { class: clase }, el("summary", {}, ...resumen), ...contenido);
    detalles.open = abiertosPlan.has(clave);
    detalles.addEventListener("toggle", () => {
      if (detalles.open) abiertosPlan.add(clave);
      else abiertosPlan.delete(clave);
    });
    return detalles;
  }

  function dibujarPlan() {
    dibujarMiPlan();
    const opciones = opcionesDelMes();
    dibujarCalendarioPlan(opciones);
    // Debajo del calendario, lo que hay para elegir. Cada día es un desplegable y, adentro, cada tipo de
    // evento otro; las filas van por hora. Lo abierto queda abierto al sumar o quitar algo del plan.
    const dias = [...opciones.keys()].sort();
    const secciones = dias.map((dia) => {
      const porTipo = new Map();
      const filas = [...opciones.get(dia)]
        .sort((a, b) => a[1][0][0].localeCompare(b[1][0][0]))
        .map(([id, funciones]) => {
        const evento = porId.get(id);
        const elegido = funciones.some(([inicio]) => plan.has(clavePlan(id, inicio)));
        const fila = el("li", { class: `plan-fila cat-${evento.categoria}${elegido ? " elegida" : ""}` },
          el("div", { class: "plan-horarios" }, ...funciones.map(([inicio, sinHora]) => {
            const enPlan = plan.has(clavePlan(id, inicio));
            return el("button", {
              type: "button", class: `horario${enPlan ? " en-plan" : ""}`, "data-plan": clavePlan(id, inicio),
              "aria-pressed": String(enPlan), title: enPlan ? "Quitar de mi plan" : "Agregar a mi plan",
            }, `${enPlan ? "✓" : "＋"} ${sinHora ? "Todo el día" : inicio.slice(11, 16)}`);
          })),
          el("div", { class: "plan-info" },
            el("a", { href: evento.url, target: "_blank", rel: "noopener" }, evento.titulo),
            el("small", {}, [nombreLugar(evento), evento.precioTexto].filter(Boolean).join(" · "))));
        if (!porTipo.has(evento.categoria)) porTipo.set(evento.categoria, []);
        porTipo.get(evento.categoria).push(fila);
        return fila;
      });
      const grupos = [...porTipo.entries()]
        .sort((a, b) => b[1].length - a[1].length)
        .map(([categoria, filasTipo]) => desplegable(`${dia}|${categoria}`, "plan-tipo",
          [el("span", {}, datos.categorias[categoria] || categoria), el("small", {}, String(filasTipo.length))],
          el("ul", {}, ...filasTipo)));
      const enPlan = [...opciones.get(dia)].filter(([id, funciones]) => funciones.some(([i]) => plan.has(clavePlan(id, i)))).length;
      const seccion = desplegable(dia, "plan-dia",
        [el("span", { class: "plan-dia-titulo" }, tituloDia(dia)),
          el("small", {}, `${plural(filas.length, "opción")}`.replace("opcións", "opciones") + (enPlan ? ` · ${enPlan} en tu plan` : ""))],
        ...grupos,
        el("button", { type: "button", class: "volver-calendario", "data-volver-calendario": "" }, "↑ Ver mi mes"));
      seccion.id = `dia-${dia}`;
      return seccion;
    });
    document.getElementById("plan-dias").replaceChildren(
      ...(secciones.length ? secciones : [el("p", { class: "vacio" }, "No hay eventos en este mes con estos filtros.")]));

    const cantidadEventos = new Set(dias.flatMap((d) => [...opciones.get(d).keys()])).size;
    document.getElementById("resumen").replaceChildren(el("strong", {}, String(cantidadEventos)),
      ` eventos para elegir en ${nombreMes(estado.planMes)} · ${plural(plan.size, "función")} en tu plan`.replace("funcións", "funciones"));
  }

  // --- Exportar: archivo .ics y enlaces a Google Calendar ---------------------------------------
  const DURACION_MS = 2 * 60 * 60 * 1000; // las fuentes no informan cuándo termina: 2 horas estimadas
  const utcIcs = (fecha) => fecha.toISOString().replace(/[-:]/g, "").replace(/\.\d{3}/, ""); // 20261114T233000Z
  const diaIcs = (dia) => dia.replace(/-/g, ""); // 20261114

  // Fin real si la fuente lo informa (el Sodre, por ejemplo); si no, una duración estimada.
  const finInformado = (p) => porId.get(p.id)?.funciones.find(([i]) => i === p.inicio)?.[2] || null;

  function horarios(p) {
    if (p.sinHora) {
      const dia = p.inicio.slice(0, 10);
      return { todoElDia: true, inicio: diaIcs(dia), fin: diaIcs(sumarDias(dia, 1)) };
    }
    const inicio = new Date(p.inicio);
    const fin = finInformado(p) ? new Date(finInformado(p)) : new Date(inicio.getTime() + DURACION_MS);
    return { todoElDia: false, inicio: utcIcs(inicio), fin: utcIcs(fin) };
  }

  function lugarCompleto(evento) {
    const lugar = datos.lugares[evento.lugar] || {};
    return [lugar.nombre, lugar.direccion, "Montevideo"].filter(Boolean).join(", ");
  }

  const detalle = (evento, p) => `Entradas e información: ${evento.url}\n${p && finInformado(p) ? "" : "Duración estimada. "}Agregado desde La Gestoría Cultural.`;

  // En el calendario, el nombre dice si ya tenés entradas: "EMI (confirmado)" o "EMI (tentativo)".
  const tituloCalendario = (evento, p) => `${evento.titulo} (${p.entradas ? "confirmado" : "tentativo"})`;

  function enlaceGoogle(evento, p) {
    const h = horarios(p);
    const parametros = new URLSearchParams({
      action: "TEMPLATE", text: tituloCalendario(evento, p), dates: `${h.inicio}/${h.fin}`,
      details: detalle(evento, p), location: lugarCompleto(evento), ctz: ZONA,
    });
    return `https://calendar.google.com/calendar/render?${parametros}`;
  }

  // Texto según RFC 5545: se escapan \ ; , y saltos de línea, y las líneas largas se pliegan a 75 bytes.
  const escaparIcs = (texto) => texto.replace(/\\/g, "\\\\").replace(/;/g, "\\;").replace(/,/g, "\\,").replace(/\r?\n/g, "\\n");
  function plegar(linea) {
    const codificador = new TextEncoder();
    const partes = [];
    let actual = "";
    let bytes = 0;
    for (const caracter of linea) {
      const tamano = codificador.encode(caracter).length;
      if (bytes + tamano > 75) {
        partes.push(actual);
        actual = " ";
        bytes = 1;
      }
      actual += caracter;
      bytes += tamano;
    }
    partes.push(actual);
    return partes.join("\r\n");
  }

  function generarIcs() {
    const sello = utcIcs(new Date());
    const lineas = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//La Gestoria Cultural//Planea tu mes//ES",
      "CALSCALE:GREGORIAN", "METHOD:PUBLISH", "X-WR-CALNAME:Mi plan cultural"];
    for (const p of elegidasOrdenadas()) {
      const evento = porId.get(p.id);
      const h = horarios(p);
      lineas.push(
        "BEGIN:VEVENT",
        `UID:${p.id}-${h.inicio}@lagestoriacultural`,
        `DTSTAMP:${sello}`,
        h.todoElDia ? `DTSTART;VALUE=DATE:${h.inicio}` : `DTSTART:${h.inicio}`,
        h.todoElDia ? `DTEND;VALUE=DATE:${h.fin}` : `DTEND:${h.fin}`,
        `SUMMARY:${escaparIcs(tituloCalendario(evento, p))}`,
        `LOCATION:${escaparIcs(lugarCompleto(evento))}`,
        `DESCRIPTION:${escaparIcs(detalle(evento, p))}`,
        `URL:${evento.url}`,
        // Los calendarios distinguen lo tentativo de lo confirmado (con entradas).
        `STATUS:${p.entradas ? "CONFIRMED" : "TENTATIVE"}`,
        "END:VEVENT",
      );
    }
    lineas.push("END:VCALENDAR");
    return lineas.map(plegar).join("\r\n") + "\r\n";
  }

  function descargarIcs() {
    const enlace = el("a", {
      href: URL.createObjectURL(new Blob([generarIcs()], { type: "text/calendar;charset=utf-8" })),
      download: "mi-plan-cultural.ics",
    });
    document.body.appendChild(enlace);
    enlace.click();
    enlace.remove();
    setTimeout(() => URL.revokeObjectURL(enlace.href), 1000);
  }
  window.__generarIcs = generarIcs; // para pruebas

  // --- Exportar sin calendario digital: texto para WhatsApp y versión para imprimir ------------
  function textoPlan() {
    const elegidas = elegidasOrdenadas();
    const meses = [...new Set(elegidas.map((p) => p.inicio.slice(0, 7)))];
    const lineas = [`🎭 *Mi plan cultural*${meses.length === 1 ? ` · ${nombreMes(meses[0])}` : ""}`];
    for (const p of elegidas) {
      const evento = porId.get(p.id);
      lineas.push(
        "",
        `📅 *${mayuscula(textoFuncion([p.inicio, p.sinHora]))}*`,
        evento.titulo,
        `📍 ${[nombreLugar(evento), evento.precioTexto].filter(Boolean).join(" · ")}`,
        `🎟️ ${evento.url}`,
      );
    }
    lineas.push("", `Armado en La Gestoría Cultural: ${URL_SITIO}`);
    return lineas.join("\n");
  }

  async function copiarTexto() {
    const texto = textoPlan();
    try {
      await navigator.clipboard.writeText(texto);
    } catch (_) {
      // Navegadores sin permiso de portapapeles: se copia desde un campo de texto temporal.
      const campo = el("textarea", { readonly: "", class: "copia-oculta" });
      campo.value = texto;
      document.body.appendChild(campo);
      campo.select();
      document.execCommand("copy");
      campo.remove();
    }
    const aviso = document.getElementById("aviso-copiado");
    aviso.hidden = false;
    setTimeout(() => { aviso.hidden = true; }, 2000);
  }

  function armarImprimible() {
    const porMes = new Map();
    for (const p of elegidasOrdenadas()) {
      const mes = p.inicio.slice(0, 7);
      if (!porMes.has(mes)) porMes.set(mes, []);
      porMes.get(mes).push(p);
    }
    const hojas = [...porMes].map(([mes, elegidas]) => {
      const [anio, numeroMes] = mes.split("-").map(Number);
      const primero = `${mes}-01`;
      const porDia = new Map();
      for (const p of elegidas) {
        const dia = p.inicio.slice(0, 10);
        if (!porDia.has(dia)) porDia.set(dia, []);
        porDia.get(dia).push(p);
      }
      const celdas = [];
      for (let i = 0; i < (diaSemana(primero) + 6) % 7; i++) celdas.push(el("div", { class: "imp-dia imp-fuera" }));
      for (const dia of rango(primero, new Date(Date.UTC(anio, numeroMes, 0)).getUTCDate())) {
        celdas.push(el("div", { class: `imp-dia${porDia.has(dia) ? " imp-con-plan" : ""}` },
          el("span", { class: "imp-numero" }, String(Number(dia.slice(8)))),
          ...(porDia.get(dia) || []).map((p) => {
            const evento = porId.get(p.id);
            return el("p", { class: "imp-evento" },
              el("strong", {}, `${p.entradas ? "🎟️ " : ""}${p.sinHora ? "" : `${p.inicio.slice(11, 16)} `}`), evento.titulo,
              el("small", {}, nombreLugar(evento)));
          })));
      }
      const detalleMes = elegidas.map((p) => {
        const evento = porId.get(p.id);
        const lugar = datos.lugares[evento.lugar] || {};
        return el("li", {},
          el("span", { class: "imp-cuando" }, mayuscula(textoFuncion([p.inicio, p.sinHora])) + (p.entradas ? " · 🎟️ con entradas" : "")),
          el("span", {}, el("strong", {}, evento.titulo), ` · ${[lugar.nombre, lugar.direccion].filter(Boolean).join(", ")}`,
            evento.precioTexto ? ` · ${evento.precioTexto}` : ""));
      });
      return el("section", { class: "imp-hoja" },
        el("header", { class: "imp-cabezal" },
          el("h1", {}, `Mi plan cultural · ${mayuscula(nombreMes(mes))}`),
          el("span", {}, "La Gestoría Cultural")),
        el("div", { class: "imp-semana" }, ...["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"].map((d) => el("span", {}, d))),
        el("div", { class: "imp-grilla" }, ...celdas),
        el("ol", { class: "imp-detalle" }, ...detalleMes));
    });
    document.getElementById("imprimible").replaceChildren(...hojas);
  }

  function imprimir() {
    armarImprimible();
    document.body.classList.add("imprimiendo");
    window.addEventListener("afterprint", () => document.body.classList.remove("imprimiendo"), { once: true });
    window.print();
  }
  window.__armarImprimible = armarImprimible; // para pruebas

  // --- Texto de presentación de cada sección ----------------------------------------------------
  const INTROS = {
    gratis: ["Gratis", "Todo lo que no cuesta un peso. Algunas actividades piden inscripción previa: revisá la fuente."],
    promos: ["Promos", "Eventos con 2x1 o descuentos para socios de clubes, bancos y programas de beneficios, según lo que marca cada ticketera."],
    festivales: ["Festivales", "Festivales, fiestas grandes y noches de tres bandas o más."],
    especiales: ["Especiales", "Las jornadas grandes del año, del Día del Patrimonio a las Llamadas. Cuando sale el programa, sus actividades aparecen en cada tarjeta."],
    mapa: ["Mapa", "Dónde pasa lo que estás buscando. Tocá una sala para ver sus eventos."],
    plan: ["Planeá tu mes", "Armá tu propia agenda cultural de Montevideo: tocá un día, sumá lo que te guste y llevalo a tu calendario."],
  };

  function dibujarIntro() {
    const intro = document.getElementById("intro");
    const texto = INTROS[estado.seccion];
    intro.hidden = !texto;
    if (!texto) return;
    intro.replaceChildren(el("h2", {}, texto[0]), el("p", {}, texto[1]));
  }

  // --- Controles --------------------------------------------------------------------------------
  function marcarActivo(grupo, atributo, valor) {
    for (const boton of document.querySelectorAll(`#${grupo} button:not(.ver-mas)`)) {
      const activo = (boton.dataset[atributo] ?? null) === valor;
      boton.classList.toggle("activo", activo);
      boton.setAttribute("aria-pressed", String(activo));
    }
  }

  // Quien pidió menos movimiento en su sistema no ve desplazamientos animados.
  const menosMovimiento = window.matchMedia("(prefers-reduced-motion: reduce)");
  const suave = () => (menosMovimiento.matches ? "auto" : "smooth");

  function dibujarSubrubros() {
    const contenedor = document.getElementById("subrubros");
    const opciones = datos.subcategorias[estado.categoria];
    contenedor.hidden = !opciones;
    if (!opciones) return;
    const nombre = datos.categorias[estado.categoria];
    const otros = datos.subcategoriasOtros[estado.categoria] || "Otros";
    const botones = [["", `Todo ${nombre.toLowerCase()}`], ...Object.entries(opciones), ["otros", otros]];
    const nota = datos.subcategoriasExperimentales.includes(estado.categoria)
      ? el("p", { class: "nota-experimental" }, "✦ Experimental: el género se deduce solo y a veces le erra.")
      : null;
    contenedor.replaceChildren(...botones.map(([clave, texto]) => el("button", {
      type: "button", "data-sub": clave, class: estado.sub === clave ? "activo" : "", "aria-pressed": String(estado.sub === clave),
    }, texto)), ...(nota ? [nota] : []));
  }

  // "Más" (barra de abajo del celular): despliega Gratis, Promos, Festivales, Especiales y "¿Qué es?".
  const pestanas = document.getElementById("pestanas");
  const SECCIONES_EN_MAS = ["gratis", "promos", "festivales", "especiales"];
  function alternarMas(abrir = !pestanas.classList.contains("mas-abierto")) {
    pestanas.classList.toggle("mas-abierto", abrir);
    document.querySelector(".boton-mas").setAttribute("aria-expanded", String(abrir));
  }
  document.addEventListener("click", (e) => {
    if (pestanas.classList.contains("mas-abierto") && !pestanas.contains(e.target)) alternarMas(false);
  });

  function dibujarControles() {
    document.querySelector(".boton-mas").classList.toggle("activa", SECCIONES_EN_MAS.includes(estado.seccion));
    for (const boton of document.querySelectorAll(".secciones button[data-seccion]")) {
      const activa = boton.dataset.seccion === estado.seccion;
      boton.classList.toggle("activa", activa);
      boton.setAttribute("aria-pressed", String(activa));
    }
    for (const boton of document.querySelectorAll(".atajos button")) {
      boton.classList.toggle("activo", boton.dataset.periodo === estado.periodo);
      boton.setAttribute("aria-pressed", String(boton.dataset.periodo === estado.periodo));
    }
    for (const boton of document.querySelectorAll("#rubros button:not(.ver-mas)")) {
      const activo = estado.etiqueta ? boton.dataset.etiqueta === estado.etiqueta
        : boton.dataset.categoria === estado.categoria && !boton.dataset.etiqueta;
      boton.classList.toggle("activo", activo);
      boton.setAttribute("aria-pressed", String(activo));
    }
    for (const boton of document.querySelectorAll("#excluidos button")) {
      const excluido = estado.excluir.includes(boton.dataset.excluir);
      boton.classList.toggle("excluido", excluido);
      boton.setAttribute("aria-pressed", String(excluido));
    }
    const cuentaExcluir = document.getElementById("cuenta-excluir");
    cuentaExcluir.hidden = !estado.excluir.length;
    cuentaExcluir.textContent = estado.excluir.length;
    marcarActivo("presupuestos", "presupuesto", estado.seccion === "gratis" ? "gratis" : estado.presupuesto);
    marcarActivo("programas", "programa", estado.programa);
    document.getElementById("campo-promos").hidden = estado.seccion !== "promos";
    document.getElementById("sala").value = estado.sala;
    document.getElementById("buscar").value = estado.texto;
    dibujarSubrubros();
  }

  function dibujarContenido() {
    const s = estado.seccion;
    if (s === "plan") dibujarPlan();
    else {
      dibujarMiPlan();
      if (s === "mapa") {
        dibujarMapa().catch(() => { document.getElementById("mapa").textContent = "No se pudo cargar el mapa."; });
      } else if (s !== "especiales") {
        dibujarCarriles();
      }
    }
  }

  function dibujar() {
    const enMapa = estado.seccion === "mapa";
    const enPlan = estado.seccion === "plan";
    const enEspeciales = estado.seccion === "especiales";
    dibujarControles();
    dibujarIntro();
    dibujarActivos();
    // En el plan, el mes se elige en el calendario grande; el chico del costado sobra.
    document.getElementById("campo-fecha").hidden = enPlan;
    if (!enPlan) dibujarCalendario();
    document.getElementById("bienvenida").hidden = bienvenidaVista || estado.seccion !== "agenda";
    document.getElementById("mapa").hidden = !enMapa;
    document.getElementById("mapa-leyenda").hidden = !enMapa;
    document.getElementById("plan").hidden = !enPlan;
    // La pestaña "Especiales" puede estar apagada (sin su sección en la página).
    const seccionEspeciales = document.getElementById("especiales");
    if (seccionEspeciales) seccionEspeciales.hidden = !enEspeciales;
    // Los especiales tienen sus propias fechas: los filtros no se aplican y el panel se esconde.
    document.querySelector(".principal").classList.toggle("sin-filtros", enEspeciales);
    // En el plan, el mes se elige en su calendario: los atajos de fecha (Hoy, Mañana…) no aplican.
    document.querySelector(".principal").classList.toggle("en-plan", enPlan);
    document.getElementById("carriles").hidden = enMapa || enPlan || enEspeciales;
    document.getElementById("vacio").hidden = true;
    dibujarContenido();
    // El botón del pie del panel dice cuántos eventos quedan con estos filtros.
    const cantidad = document.querySelector("#resumen strong")?.textContent;
    document.querySelector(".ver-eventos").textContent = cantidad ? `Ver ${cantidad} eventos` : "Ver los eventos";
  }

  // --- Panel de filtros del celular: se abre desde la izquierda, como un diálogo -------------------
  const panelFiltros = document.getElementById("filtros");
  const velo = document.getElementById("velo");
  const botonFiltros = document.querySelector("[data-abrir-filtros]");
  const fondo = () => [document.querySelector(".cabezal"), document.getElementById("resultados"), document.querySelector(".pie-pagina")];

  function abrirFiltros() {
    panelFiltros.classList.add("abierto");
    panelFiltros.setAttribute("role", "dialog");
    panelFiltros.setAttribute("aria-modal", "true");
    velo.hidden = false;
    document.body.classList.add("filtros-abiertos");
    // Lo de atrás queda inerte: ni el teclado ni el lector de pantalla salen del panel.
    for (const parte of fondo()) parte?.setAttribute("inert", "");
    botonFiltros.setAttribute("aria-expanded", "true");
    panelFiltros.querySelector(".cerrar-filtros").focus();
  }

  function cerrarFiltros(devolverFoco = true) {
    if (!panelFiltros.classList.contains("abierto")) return;
    panelFiltros.classList.remove("abierto");
    panelFiltros.removeAttribute("role");
    panelFiltros.removeAttribute("aria-modal");
    velo.hidden = true;
    document.body.classList.remove("filtros-abiertos");
    for (const parte of fondo()) parte?.removeAttribute("inert");
    botonFiltros.setAttribute("aria-expanded", "false");
    if (devolverFoco) botonFiltros.focus();
  }

  velo.addEventListener("click", () => cerrarFiltros());
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    if (pestanas.classList.contains("mas-abierto")) {
      alternarMas(false);
      document.querySelector(".boton-mas").focus();
    } else cerrarFiltros();
  });

  function cambiar(cambios) {
    estado = { ...estado, ...cambios };
    if ("excluir" in cambios) guardarExcluir();
    dibujar();
  }

  // Delegación de clics: cada botón dice qué cambia con sus data-atributos.
  document.addEventListener("click", (evento) => {
    const boton = evento.target.closest("button");
    if (!boton || boton.disabled) return;
    const d = boton.dataset;
    if ("cerrarBienvenida" in d) cerrarBienvenida();
    else if (d.plegarCarril) {
      const seccion = boton.closest(".carril");
      const plegado = seccion.classList.toggle("plegado");
      if (plegado) carrilesPlegados.add(d.plegarCarril);
      else carrilesPlegados.delete(d.plegarCarril);
      boton.setAttribute("aria-expanded", String(!plegado));
    } else if (d.compartir) {
      const [id, inicio] = d.compartir.split("|");
      compartir(id, inicio);
    } else if ("verTodos" in d) {
      boton.closest(".carril").classList.remove("recortado");
      boton.remove();
    } else if ("masSecciones" in d) {
      alternarMas();
    } else if ("verMas" in d) {
      // "Más tipos" / "Más programas": muestra u oculta los botones plegados.
      const lista = boton.parentElement;
      const abierta = lista.classList.toggle("abierta");
      boton.setAttribute("aria-expanded", String(abierta));
      boton.textContent = abierta ? "Menos" : boton.dataset.textoMas;
    } else if ("abrirFiltros" in d) abrirFiltros();
    else if ("cerrarFiltros" in d) cerrarFiltros();
    else if (d.borrar) cambiar(borrar(d.borrar));
    else if (d.excluir) {
      const ya = estado.excluir.includes(d.excluir);
      cambiar({ excluir: ya ? estado.excluir.filter((c) => c !== d.excluir) : [...estado.excluir, d.excluir] });
    }
    else if (d.desplazar) {
      const pista = boton.closest(".carril").querySelector(".carril-pista");
      pista.scrollBy({ left: Number(d.desplazar) * pista.clientWidth * 0.9, behavior: suave() });
    } else if (d.agregarFuncion) {
      const [id, inicio] = d.agregarFuncion.split("|");
      alternarPlan(id, inicio);
      for (const otro of document.querySelectorAll(`[data-agregar-funcion="${CSS.escape(d.agregarFuncion)}"]`)) marcarBotonPlan(otro, id, inicio);
      dibujarMiPlan();
    } else if (d.plan) {
      const [id, inicio] = d.plan.split("|");
      alternarPlan(id, inicio);
      dibujarPlan();
    } else if (d.verPlanDia) {
      abrirDetallePlan(d.verPlanDia);
    } else if ("cerrarDetalle" in d) {
      diaDetalle = null;
      dibujarDetallePlan();
    } else if (d.entradas) {
      const elegida = plan.get(d.entradas);
      if (elegida) {
        elegida.entradas = !elegida.entradas;
        guardarPlan();
        const enDetalle = Boolean(boton.closest("#pc-detalle"));
        dibujarContenido();
        // Al redibujar se pierde el foco: vuelve al mismo botón, para seguir con el teclado.
        const nuevo = document.querySelector(`${enDetalle ? "#pc-detalle" : "#mi-plan-lista"} [data-entradas="${CSS.escape(d.entradas)}"]`);
        nuevo?.focus();
        if (nuevo) mostrarGlobito(nuevo, elegida.entradas ? "🎟️ Tengo entradas" : "Sin entradas todavía");
      }
    } else if (d.quitar) {
      plan.delete(d.quitar);
      guardarPlan();
      dibujarContenido();
    } else if ("vaciarPlan" in d) {
      if (window.confirm("¿Vaciar todo tu plan?")) {
        plan.clear();
        guardarPlan();
        dibujarContenido();
      }
    } else if (d.verDia) irAlDia(d.verDia); else if ("volverCalendario" in d) {
      document.querySelector(".plan-cal").scrollIntoView({ behavior: suave(), block: "start" });
    } else if (d.planMes) cambiar({ planMes: sumarMeses(estado.planMes, Number(d.planMes)) });
    else if (d.exportar === "ics") descargarIcs();
    else if (d.exportar === "google") abrirEnGoogle();
    else if (d.exportar === "imprimir") imprimir();
    else if (d.exportar === "copiar") copiarTexto();
    else if (d.seccion) {
      alternarMas(false);
      const cambios = { seccion: d.seccion };
      if (d.seccion !== "promos") cambios.programa = "";
      cambiar(cambios);
    } else if (d.periodo) cambiar({ periodo: d.periodo, dia: null });
    else if (d.dia) {
      const mismo = estado.periodo === "dia" && estado.dia === d.dia;
      cambiar(mismo ? { periodo: "todo", dia: null } : { periodo: "dia", dia: d.dia });
    } else if (d.mes) cambiar({ mes: sumarMeses(estado.mes, Number(d.mes)) });
    else if ("categoria" in d) cambiar({ categoria: d.categoria, etiqueta: "", sub: "" });
    else if (d.etiqueta) cambiar({ etiqueta: estado.etiqueta === d.etiqueta ? "" : d.etiqueta, categoria: "", sub: "" });
    else if ("sub" in d) cambiar({ sub: d.sub });
    else if ("presupuesto" in d) {
      const salirDeGratis = estado.seccion === "gratis" && d.presupuesto !== "gratis";
      cambiar({ presupuesto: d.presupuesto, seccion: salirDeGratis ? "agenda" : estado.seccion });
    } else if ("programa" in d) cambiar({ programa: d.programa });
    else if (d.sala) cambiar({ sala: d.sala, seccion: estado.seccion === "mapa" ? "agenda" : estado.seccion });
    // El ciclo de una tarjeta filtra la agenda por ese ciclo (con todas sus fechas).
    else if (d.ciclo) cambiar({ ciclo: d.ciclo, periodo: "todo", dia: null, seccion: ["mapa", "plan"].includes(estado.seccion) ? "agenda" : estado.seccion });
  });
  document.getElementById("sala").addEventListener("change", (e) => cambiar({ sala: e.target.value }));
  // En la compu, el número del día abre lo elegido y "N opciones" lleva a las opciones. En el celular los botones
  // quedan chicos: toda la celda es un solo toque. Con algo elegido abre "Tu plan del día" (que también lleva a
  // las opciones); sin nada elegido, va directo a las opciones.
  document.getElementById("pc-grilla").addEventListener("click", (e) => {
    const celda = e.target.closest(".pc-dia");
    if (!celda || celda.classList.contains("pasado") || celda.classList.contains("fuera")) return;
    const conPlan = celda.querySelector("[data-ver-plan-dia]");
    if (angosta.matches || !e.target.closest("button")) {
      if (conPlan) abrirDetallePlan(conPlan.dataset.verPlanDia);
      else if (celda.querySelector("[data-ver-dia]")) irAlDia(celda.querySelector("[data-ver-dia]").dataset.verDia);
      else return;
      e.stopPropagation(); // ya se resolvió acá: que no lo tome también el manejador general
    }
  });

  // La búsqueda redibuja al dejar de tipear, para no rearmar los carriles con cada letra.
  let esperaBusqueda = null;
  document.getElementById("buscar").addEventListener("input", (e) => {
    estado.texto = e.target.value;
    clearTimeout(esperaBusqueda);
    esperaBusqueda = setTimeout(() => {
      dibujarActivos();
      if (estado.seccion !== "plan") dibujarCalendario();
      dibujarContenido();
    }, 200);
  });

  // En el celular, calendario y filtros arrancan plegados; en pantallas grandes, siempre abiertos.
  const angosta = window.matchMedia("(max-width: 860px)");
  const ajustarPlegables = () => {
    // Los filtros van siempre desplegados: en el celular viven en el panel lateral, que ya se abre y se cierra.
    for (const plegable of document.querySelectorAll(".plegable")) plegable.open = true;
    if (!angosta.matches) cerrarFiltros(false);
  };
  angosta.addEventListener("change", ajustarPlegables);
  ajustarPlegables();

  dibujar();
})();
