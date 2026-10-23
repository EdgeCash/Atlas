/* The owner page: decrypts the sealed sections in the browser.
 *
 * The page carries only ciphertext (AES-256-GCM under a PBKDF2-SHA256 key,
 * see atlas/owner/crypto.py and atlas/owner/page.py): one box, under one
 * passphrase. The passphrase is typed here, the key is derived here, and the
 * plaintext exists only in this tab's memory. Nothing is stored and nothing
 * is sent anywhere. Opened, the page is a row of tabs; each section names
 * the one it belongs in. The script holds the tabs' names, nothing else.
 */
(function () {
  "use strict";

  var boxEl = document.getElementById("owner-box");
  var form = document.getElementById("owner-form");
  if (!boxEl || !form) return;
  var record = JSON.parse(boxEl.textContent || "{}");
  var box = record.box;
  var status = document.getElementById("owner-status");
  var out = document.getElementById("owner-out");
  var gate = form.parentNode;          // the passphrase card: out of the way while the page is open

  if (!box) { form.hidden = true; return; }
  if (!(window.crypto && window.crypto.subtle)) {
    status.textContent = "This browser cannot decrypt the page (no WebCrypto).";
    form.hidden = true;
    return;
  }

  function bytes(b64) {
    var s = atob(b64), a = new Uint8Array(s.length);
    for (var i = 0; i < s.length; i++) a[i] = s.charCodeAt(i);
    return a;
  }

  function open(passphrase, sealed) {
    var enc = new TextEncoder();
    return crypto.subtle.importKey("raw", enc.encode(passphrase.trim()), "PBKDF2", false, ["deriveKey"])
      .then(function (base) {
        return crypto.subtle.deriveKey(
          { name: "PBKDF2", salt: bytes(sealed.salt), iterations: sealed.iterations, hash: "SHA-256" },
          base, { name: "AES-GCM", length: 256 }, false, ["decrypt"]);
      })
      .then(function (key) {
        return crypto.subtle.decrypt({ name: "AES-GCM", iv: bytes(sealed.iv) }, key, bytes(sealed.ct));
      })
      .then(function (plain) { return JSON.parse(new TextDecoder().decode(plain)); });
  }

  function el(tag, attrs, text) {
    var e = document.createElement(tag);
    if (attrs) for (var k in attrs) e.setAttribute(k, attrs[k]);
    if (text !== undefined && text !== null) e.textContent = String(text);
    return e;
  }

  function eastern(iso) {
    if (!iso) return "";
    var d = new Date(iso);
    return new Intl.DateTimeFormat("en-US", {
      timeZone: "America/New_York", weekday: "short", month: "short", day: "numeric",
      hour: "numeric", minute: "2-digit"
    }).format(d) + " ET";
  }

  function table(head, rows, stack) {
    var wrap = el("div", { "class": "table-scroll" });
    // A stacked table becomes one small card a row on a phone; each cell carries its column's name for it.
    var t = el("table", { "class": "rows owner-table" + (stack ? " owner-stack" : "") });
    var tr = el("tr");
    head.forEach(function (h) { tr.appendChild(el("th", null, h)); });
    var thead = el("thead"); thead.appendChild(tr); t.appendChild(thead);
    var tbody = el("tbody");
    rows.forEach(function (r) {
      var row = el("tr");
      r.forEach(function (c, i) {
        var td = el("td", { "data-col": head[i] || "" });
        // A cell is a string, or a main value with its second lines beneath.
        if (Array.isArray(c)) {
          td.appendChild(el("b", null, c[0]));
          c.slice(1).forEach(function (line) {
            if (line) td.appendChild(el("span", { "class": "owner-sub" }, line));
          });
        } else {
          td.textContent = c === null || c === undefined ? "" : String(c);
        }
        row.appendChild(td);
      });
      tbody.appendChild(row);
    });
    t.appendChild(tbody);
    wrap.appendChild(t);
    return wrap;
  }

  var TABS = ["Polymarket", "Record", "More"];

  function tabOf(sec) { return sec.tab || "More"; }

  function slug(name) { return name.toLowerCase().replace(/[^a-z]+/g, "-"); }

  function shell(data) {
    var head = el("div", { "class": "card card-pad owner-head" });
    head.appendChild(el("p", { "class": "note" }, data && data.built_at ? "Built " + eastern(data.built_at) : ""));
    var close = el("button", { type: "button", "class": "button ghost" }, "Close");
    close.addEventListener("click", function () {
      out.textContent = ""; form.hidden = false; status.textContent = ""; gate.style.display = "";
      if (history.replaceState) history.replaceState(null, "", location.pathname + location.search);
    });
    head.appendChild(close);
    out.appendChild(head);
    var bar = el("div", { "class": "owner-tabs", role: "tablist", "aria-label": "Owner sections" });
    var panels = {};
    var buttons = {};
    var names = [];
    function select(name) {
      names.forEach(function (n) {
        var on = n === name;
        buttons[n].setAttribute("aria-selected", on ? "true" : "false");
        buttons[n].setAttribute("tabindex", on ? "0" : "-1");
        panels[n].hidden = !on;
      });
    }
    function add(name) {
      if (panels[name]) return;
      var id = "owner-tab-" + slug(name);
      var b = el("button", { type: "button", "class": "owner-tab", role: "tab", id: id + "-tab",
                             "aria-controls": id, "aria-selected": "false", tabindex: "-1" }, name);
      var p = el("div", { "class": "owner-panel", role: "tabpanel", id: id, "aria-labelledby": id + "-tab" });
      p.hidden = true;
      b.addEventListener("click", function () { select(name); });
      bar.appendChild(b);
      panels[name] = p;
      buttons[name] = b;
      names.push(name);
    }
    // Tabs in their fixed order, then any a section named that the script does not know.
    TABS.forEach(add);
    (data.sections || []).forEach(function (sec) { add(tabOf(sec)); });
    out.appendChild(bar);
    names.forEach(function (n) { out.appendChild(panels[n]); });
    return {
      panel: function (name) { add(name); return panels[name]; },
      finish: function () {
        // Empty tabs go; the first with something in it opens.
        var kept = names.filter(function (n) {
          if (panels[n].childNodes.length) return true;
          bar.removeChild(buttons[n]); out.removeChild(panels[n]); return false;
        });
        names = kept;
        if (kept.length) select(kept[0]);
      }
    };
  }

  function sectionCard(sec) {
    var card = el("div", { "class": "card card-pad top-gap" });
    card.appendChild(el("h3", null, sec.title || ""));
    (sec.tables || []).forEach(function (t) {
      // A long reference table can arrive folded, its title the thing to open.
      if (t.fold) {
        var fold = el("details", { "class": "owner-fold top-gap" });
        fold.appendChild(el("summary", null, t.title || ""));
        fold.appendChild(table(t.head || [], t.rows || [], t.stack));
        card.appendChild(fold);
        return;
      }
      if (t.title) card.appendChild(el("h4", { "class": "top-gap" }, t.title));
      card.appendChild(table(t.head || [], t.rows || [], t.stack));
    });
    // The explanations after the numbers, folded: read once, not scrolled past every visit.
    if ((sec.notes || []).length) {
      var more = el("details", { "class": "owner-notes top-gap" });
      more.appendChild(el("summary", null, "How this works"));
      sec.notes.forEach(function (n) { more.appendChild(el("p", { "class": "note" }, n)); });
      card.appendChild(more);
    }
    return card;
  }

  function render(data) {
    var page = shell(data);
    (data.sections || []).forEach(function (sec) { page.panel(tabOf(sec)).appendChild(sectionCard(sec)); });
    page.finish();
  }

  form.addEventListener("submit", function (ev) {
    ev.preventDefault();
    var input = document.getElementById("owner-pass");
    status.textContent = "Opening…";
    open(input.value, box).then(function (data) {
      input.value = "";
      form.hidden = true;
      status.textContent = "";
      gate.style.display = "none";
      out.textContent = "";
      render(data);
    }).catch(function () {
      status.textContent = "That passphrase did not open the page.";
    });
  });
})();
