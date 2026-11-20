// Het thema opent alle details bij afdrukken. Bewaar de selectie van de lezer.
window.addEventListener("beforeprint", () => {
  for (const detail of document.querySelectorAll("article details:not([open])")) {
    detail.classList.add("ingeklapt-bij-afdrukken");
  }
}, { capture: true });

window.addEventListener("afterprint", () => {
  for (const detail of document.querySelectorAll(".ingeklapt-bij-afdrukken")) {
    detail.classList.remove("ingeklapt-bij-afdrukken");
  }
});
