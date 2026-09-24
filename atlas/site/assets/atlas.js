/* Board filtering and the Tiles/List switch, both sports. Plain DOM over
   already-rendered games: the page is complete before this file loads, and
   it works without it. Every game appears as a row and as a tile (one of the
   two is shown); both carry the same data-* attributes, so one filter pass
   covers both views. The conference filter is optional - the NFL board has
   none. */
(function () {
  "use strict";
  var root = document.documentElement;
  var q = document.getElementById("q");
  var conf = document.getElementById("conf");
  var count = document.getElementById("count");
  var buttons = Array.prototype.slice.call(document.querySelectorAll(".filter"));
  var views = Array.prototype.slice.call(document.querySelectorAll(".view-btn"));
  var items = Array.prototype.slice.call(document.querySelectorAll("[data-game]"));
  if (!items.length) return;

  /* Tiles or list. With no saved choice the stylesheet decides by width
     (tiles from 760px, the list below); the switch records a choice. */
  var WIDE = "(min-width: 760px)";
  function currentView() {
    return root.dataset.view || (window.matchMedia(WIDE).matches ? "tiles" : "list");
  }
  function markView() {
    var view = currentView();
    views.forEach(function (button) {
      button.setAttribute("aria-pressed", String(button.dataset.view === view));
    });
  }
  views.forEach(function (button) {
    button.addEventListener("click", function () {
      root.dataset.view = button.dataset.view;
      try { window.localStorage.setItem("atlas-view", button.dataset.view); } catch (e) { /* private mode */ }
      markView();
    });
  });
  if (window.matchMedia) {
    var media = window.matchMedia(WIDE);
    if (media.addEventListener) media.addEventListener("change", markView);
  }
  markView();

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
    var conference = conf ? conf.value : "";
    var all = {};
    var shown = {};
    items.forEach(function (item) {
      var ok =
        (!text || item.dataset.search.indexOf(text) !== -1) &&
        (!conference || (item.dataset.conf || "").indexOf(conference) !== -1) &&
        matchesGrade(item.dataset.grade);
      item.hidden = !ok;
      all[item.dataset.game] = true;
      if (ok) shown[item.dataset.game] = true;
    });
    document.querySelectorAll(".section").forEach(function (section) {
      if (section.querySelector("[data-game]")) {
        section.hidden = !section.querySelector("[data-game]:not([hidden])");
      }
    });
    /* Games, not rows or tiles: a game listed under "Next kickoffs" and
       under its grade is one game. Silent when nothing is filtered. */
    var total = Object.keys(all).length;
    var visible = Object.keys(shown).length;
    var filtered = visible !== total;
    count.textContent = filtered ? visible + " of " + total + " games" : "";
    count.hidden = !filtered;
  }

  q.addEventListener("input", apply);
  if (conf) conf.addEventListener("change", apply);
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
