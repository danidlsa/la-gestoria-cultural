// "¿Qué es La Gestoría?": en el celular las preguntas arrancan cerradas, para no scrollear tanto.
// Si se llega con un enlace a una sección (por ejemplo, "Privacidad" desde el pie), esa se abre.
(() => {
  const preguntas = [...document.querySelectorAll("details.pregunta")];
  if (window.matchMedia("(max-width: 860px)").matches) for (const pregunta of preguntas) pregunta.open = false;

  function abrirLaDelEnlace() {
    const destino = location.hash && document.getElementById(location.hash.slice(1));
    const pregunta = destino?.closest("details.pregunta");
    if (pregunta) {
      pregunta.open = true;
      pregunta.scrollIntoView({ block: "start" });
    }
  }
  abrirLaDelEnlace();
  window.addEventListener("hashchange", abrirLaDelEnlace);
})();
