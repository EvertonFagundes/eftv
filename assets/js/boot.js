/* EFTV - inicialização da grade.
   Arquivo separado (em vez de <script> inline) para a página poder usar uma
   Content-Security-Policy que só permite scripts do próprio site. */
(function () {
  if (typeof window.CanaisRenderTudo === "function") {
    window.CanaisRenderTudo();
  } else if (typeof window.CanaisRenderGrade === "function") {
    window.CanaisRenderGrade();
  }
})();
