// Botón ☀/☾: el sitio arranca en crema y cada persona elige. La elección queda en este navegador.
(() => {
  const CLAVE = "lgc-tema";
  const boton = document.getElementById("boton-tema");
  if (!boton) return;

  function dibujar() {
    const oscuro = document.documentElement.dataset.tema === "oscuro";
    boton.setAttribute("aria-pressed", String(oscuro));
    boton.querySelector(".tema-icono").textContent = oscuro ? "☀" : "☾";
    boton.querySelector(".tema-texto").textContent = oscuro ? "Claro" : "Oscuro";
  }

  boton.addEventListener("click", () => {
    const oscuro = document.documentElement.dataset.tema !== "oscuro";
    if (oscuro) document.documentElement.dataset.tema = "oscuro";
    else delete document.documentElement.dataset.tema;
    try { localStorage.setItem(CLAVE, oscuro ? "oscuro" : "claro"); } catch (_) { /* sin almacenamiento: dura lo que la pestaña */ }
    dibujar();
  });
  dibujar();
})();
