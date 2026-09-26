/* The reader counter's beacon (counter/worker.js, docs/ANALYTICS_SPEC_FINAL.md).
   Only on pages built with a counter address. It says three things and
   nothing else: this page was viewed (and from which site, by host only);
   this device's first visit today, new or returning; and which card panel
   was opened. No cookie and no identifier: the device keeps the date of its
   last visit in its own storage and never sends it. A browser that asks not
   to be tracked sends nothing. */
(function () {
  "use strict";
  var meta = document.querySelector('meta[name="atlas-counter"]');
  var script = document.currentScript;
  if (!meta || !meta.content || !script || !navigator.sendBeacon) return;
  if (navigator.globalPrivacyControl || navigator.doNotTrack === "1" || window.doNotTrack === "1") return;
  var url = meta.content.replace(/\/+$/, "") + "/hit";

  /* The page from the site root: this file is assets/readers.js, so the root
     is one level up, on github.io's /Atlas/ and a domain's / alike. */
  var base = new URL("..", script.src).pathname;
  var path = location.pathname.indexOf(base) === 0 ? location.pathname.slice(base.length) : "";
  path = (path || "index.html").toLowerCase();

  function send(hit) {
    try {
      navigator.sendBeacon(url, new Blob([JSON.stringify(hit)], { type: "text/plain" }));
    } catch (e) { /* a count missed is fine */ }
  }

  var from = "";
  try { from = document.referrer ? new URL(document.referrer).hostname : ""; } catch (e) { /* none */ }
  send({ e: "view", p: path, r: from });

  try {
    var today = new Date().toLocaleDateString("en-CA");
    var last = window.localStorage.getItem("atlas-last-visit");
    if (last !== today) {
      send({ e: "visit", k: last ? "return" : "new" });
      window.localStorage.setItem("atlas-last-visit", today);
    }
  } catch (e) { /* private mode: no visit count */ }

  Array.prototype.forEach.call(document.querySelectorAll("details[data-panel]"), function (panel) {
    var sent = false;
    panel.addEventListener("toggle", function () {
      if (panel.open && !sent) {
        sent = true;
        send({ e: "panel", p: path, n: panel.dataset.panel });
      }
    });
  });
})();
