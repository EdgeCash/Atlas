/* The DFS page's position filter: shows one position's rows, or all.
 * It only hides and shows rows the page already has; it adds no numbers. */
(function () {
  "use strict";
  var buttons = document.querySelectorAll(".dfs-chip");
  if (!buttons.length) return;
  function show(pos) {
    buttons.forEach(function (b) { b.setAttribute("aria-pressed", String(b.dataset.filter === pos)); });
    document.querySelectorAll(".dfs-table tbody tr").forEach(function (tr) {
      tr.hidden = pos !== "All" && tr.dataset.pos !== pos;
    });
  }
  buttons.forEach(function (b) { b.addEventListener("click", function () { show(b.dataset.filter); }); });
})();
