/* Homepage filtering. Plain DOM over already-rendered rows: the page is
   complete before this file loads, and it works without it. */
(function () {
  "use strict";
  var q = document.getElementById("q");
  var conf = document.getElementById("conf");
  var count = document.getElementById("count");
  var buttons = Array.prototype.slice.call(document.querySelectorAll(".filter"));
  var rows = Array.prototype.slice.call(document.querySelectorAll(".game-row"));
  if (!rows.length) return;

  var grade = "";
  var ORDER = { "A+": 6, A: 5, B: 4, C: 3, D: 2, F: 1 };

  function matchesGrade(value) {
    if (!grade) return true;
    if (grade === "low") return value === "low";
    if (value === "low") return ORDER[grade] <= 2;
    return (ORDER[value] || 0) >= (ORDER[grade] || 0);
  }

  function apply() {
    var text = (q.value || "").trim().toLowerCase();
    var conference = conf.value;
    var shown = 0;
    rows.forEach(function (row) {
      var ok =
        (!text || row.dataset.search.indexOf(text) !== -1) &&
        (!conference || (row.dataset.conf || "").indexOf(conference) !== -1) &&
        matchesGrade(row.dataset.grade);
      row.hidden = !ok;
      if (ok) shown++;
    });
    document.querySelectorAll(".game-list").forEach(function (list) {
      var section = list.closest(".section");
      if (section) {
        section.hidden = !list.querySelector(".game-row:not([hidden])");
      }
    });
    /* Silent when nothing is filtered. "58 games" under a heading that
       already says "58 cards" is a line of chrome above the first card. */
    var filtered = shown !== rows.length;
    count.textContent = filtered ? shown + " of " + rows.length + " games" : "";
    count.hidden = !filtered;
  }

  q.addEventListener("input", apply);
  conf.addEventListener("change", apply);
  buttons.forEach(function (button) {
    button.addEventListener("click", function () {
      grade = button.dataset.grade;
      buttons.forEach(function (other) {
        other.setAttribute("aria-pressed", String(other === button));
      });
      apply();
    });
  });
  apply();
})();
