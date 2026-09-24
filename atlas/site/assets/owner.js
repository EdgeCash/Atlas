/* The owner page: decrypts this week's lineups in the browser.
 *
 * The page carries only ciphertext (AES-256-GCM under a PBKDF2-SHA256 key,
 * see atlas/dfs/owner.py). The passphrase is typed here, the key is derived
 * here, and the plaintext exists only in this tab's memory. Nothing is
 * stored and nothing is sent anywhere.
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

  function open(passphrase) {
    var enc = new TextEncoder();
    return crypto.subtle.importKey("raw", enc.encode(passphrase.trim()), "PBKDF2", false, ["deriveKey"])
      .then(function (base) {
        return crypto.subtle.deriveKey(
          { name: "PBKDF2", salt: bytes(box.salt), iterations: box.iterations, hash: "SHA-256" },
          base, { name: "AES-GCM", length: 256 }, false, ["decrypt"]);
      })
      .then(function (key) {
        return crypto.subtle.decrypt({ name: "AES-GCM", iv: bytes(box.iv) }, key, bytes(box.ct));
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

  function money(n) { return "$" + Number(n).toLocaleString("en-US"); }
  function pts(n) { return n === null || n === undefined || isNaN(n) ? "–" : Number(n).toFixed(1); }

  function table(head, rows) {
    var wrap = el("div", { "class": "table-scroll" });
    var t = el("table", { "class": "rows owner-table" });
    var tr = el("tr");
    head.forEach(function (h) { tr.appendChild(el("th", null, h)); });
    var thead = el("thead"); thead.appendChild(tr); t.appendChild(thead);
    var tbody = el("tbody");
    rows.forEach(function (r) {
      var row = el("tr");
      r.forEach(function (c) { row.appendChild(el("td", null, c)); });
      tbody.appendChild(row);
    });
    t.appendChild(tbody);
    wrap.appendChild(t);
    return wrap;
  }

  function download(slate) {
    var blob = new Blob([slate.upload_csv], { type: "text/csv" });
    var name = "atlas-dk-" + (slate.sport || "nfl") + "-" + slate.draft_group_id + "-" +
      (slate.game_type || "Classic").toLowerCase() + ".csv";
    var a = el("a", { href: URL.createObjectURL(blob), download: name });
    document.body.appendChild(a);
    a.click();
    a.remove();
  }

  function slateName(s) {
    var kind = s.game_type || "Classic";
    var sport = s.sport === "cfb" ? "College" : "NFL";
    return sport + " " + kind + (s.label && s.label !== kind ? " · " + s.label : "") + " · " + eastern(s.starts_at);
  }

  function lineupCards(slate, holder) {
    holder.textContent = "";
    if (!slate.lineups.length) {
      holder.appendChild(el("p", { "class": "note" }, "No lineup fits this slate's pool."));
      return;
    }
    slate.lineups.forEach(function (lu, i) {
      var card = el("div", { "class": "card card-pad top-gap" });
      var cost = lu.salary === null || lu.salary === undefined ? "" : " · " + money(lu.salary);
      card.appendChild(el("h3", null, "Lineup " + (i + 1) + " · " + pts(lu.projection) + " projected" + cost));
      card.appendChild(table(["Slot", "Player", "Team", "Salary", "Proj", "Range"],
        lu.slots.map(function (s) {
          return [s.slot, s.name, s.team, s.salary === null || s.salary === undefined || isNaN(s.salary) ? "–" : money(s.salary),
                  pts(s.projection), pts(s.low) + "–" + pts(s.high)];
        })));
      holder.appendChild(card);
    });
  }

  function poolCard(title, players) {
    var pool = el("div", { "class": "card card-pad top-gap" });
    pool.appendChild(el("h3", null, title));
    var pick = el("select", { "aria-label": "Position" });
    var seen = {};
    players.forEach(function (p) { seen[p.position] = true; });
    ["All", "QB", "RB", "WR", "TE", "K", "DST"].filter(function (p) { return p === "All" || seen[p]; })
      .forEach(function (p) { pick.appendChild(el("option", { value: p }, p)); });
    pool.appendChild(pick);
    var rowsHolder = el("div");
    pool.appendChild(rowsHolder);
    function fill() {
      rowsHolder.textContent = "";
      var rows = players.filter(function (p) { return pick.value === "All" || p.position === pick.value; })
        .slice(0, 80)
        .map(function (p) {
          return [p.name + (p.status ? " (" + p.status + ")" : ""), p.position, p.team, money(p.salary),
                  pts(p.projection), pts(p.low) + "–" + pts(p.high),
                  p.p_play === null || p.p_play === undefined ? "–" : Math.round(p.p_play * 100) + "%"];
        });
      rowsHolder.appendChild(table(["Player", "Pos", "Team", "Salary", "Proj", "Range", "Plays"], rows));
    }
    pick.addEventListener("change", fill);
    fill();
    return pool;
  }

  function render(data) {
    out.textContent = "";
    var slates = data.slates || [];
    var head = el("div", { "class": "card card-pad" });
    head.appendChild(el("h2", null, slates.length + " slates this week"));
    head.appendChild(el("p", { "class": "note" }, "Built " + eastern(data.built_at)));
    var choose = el("select", { "aria-label": "Slate", "class": "owner-slate" });
    slates.forEach(function (s, i) { choose.appendChild(el("option", { value: String(i) }, slateName(s))); });
    var main = slates.findIndex(function (s) {
      return s.game_type === "Classic" && s.label === "Main" && (s.sport || "nfl") === "nfl";
    });
    if (main >= 0) choose.value = String(main);
    head.appendChild(choose);
    var actions = el("div", { "class": "lede-actions" });
    var dl = el("button", { type: "button", "class": "button" }, "Download this slate's DraftKings upload file");
    dl.addEventListener("click", function () { download(slates[Number(choose.value)]); });
    var close = el("button", { type: "button", "class": "button ghost" }, "Close");
    close.addEventListener("click", function () { out.textContent = ""; form.hidden = false; status.textContent = ""; });
    actions.appendChild(dl);
    actions.appendChild(close);
    head.appendChild(actions);
    out.appendChild(head);
    var holder = el("div");
    out.appendChild(holder);
    choose.addEventListener("change", function () { lineupCards(slates[Number(choose.value)], holder); });
    if (slates.length) lineupCards(slates[Number(choose.value)], holder);

    out.appendChild(poolCard("Every player, by projection", data.players || []));
    if (data.college_players) out.appendChild(poolCard("College: every player, by projection", data.college_players));
  }

  form.addEventListener("submit", function (ev) {
    ev.preventDefault();
    var input = document.getElementById("owner-pass");
    status.textContent = "Opening…";
    open(input.value).then(function (data) {
      input.value = "";
      form.hidden = true;
      status.textContent = "";
      try {
        render(data);
      } catch (e) {
        // Opened, but not shown: say so rather than blame the passphrase.
        form.hidden = false;
        status.textContent = "The lineups opened but could not be shown (" + e.name + ").";
        if (window.console) console.error(e);
      }
    }, function () {
      status.textContent = "That passphrase does not open this week's lineups.";
    });
  });
})();
