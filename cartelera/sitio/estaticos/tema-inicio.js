// El tema elegido se aplica antes de dibujar la página, para que no parpadee. Va en un archivo aparte (y no en
// línea en el HTML) para que la política de contenido pueda prohibir todo script en línea.
try { if (localStorage.getItem("lgc-tema") === "oscuro") document.documentElement.dataset.tema = "oscuro"; } catch (_) { /* sin almacenamiento: tema claro */ }
