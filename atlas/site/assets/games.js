/* Following games, and My scoreboard. Loaded on every page.

   What a reader follows lives in this browser only (localStorage): Atlas has
   no accounts and never sees the list. Each page carries its games as JSON
   (#atlas-games); following one stores that record, so the scoreboard can
   show it after its card has left the site. The record is who, when and
   where the card is - never Atlas's numbers. On the scoreboard page, scores
   come straight from ESPN's public scoreboard, which allows cross-site reads.

   Nothing here animates, counts down or flashes: the scoreboard refreshes
   its numbers quietly - every minute while a followed game is on or about to
   start, every ten minutes otherwise - and stops while the tab is hidden. */
(function () {
  "use strict";

  var KEY = "atlas-following";
  var KEEP_DAYS = 4;
  var DAY = 864e5;
  var MINUTE = 6e4;

  function slice(list) { return Array.prototype.slice.call(list); }

  function read() {
    try {
      var value = JSON.parse(window.localStorage.getItem(KEY) || "{}");
      return value && typeof value === "object" ? value : {};
    } catch (e) { return {}; }
  }

  function write(map) {
    try { window.localStorage.setItem(KEY, JSON.stringify(map)); } catch (e) { /* private mode: this visit only */ }
  }

  function pageGames() {
    var node = document.getElementById("atlas-games");
    if (!node) return {};
    try { return JSON.parse(node.textContent) || {}; } catch (e) { return {}; }
  }

  var games = pageGames();
  var following = read();

  /* Forget games long over, and refresh a followed game's details from this
     page's newer numbers where the page has it. */
  (function tidy() {
    var now = Date.now();
    var changed = false;
    Object.keys(following).forEach(function (id) {
      var kickoff = Date.parse((following[id] || {}).kickoff);
      if (!following[id] || (!isNaN(kickoff) && now - kickoff > KEEP_DAYS * DAY)) {
        delete following[id];
        changed = true;
      } else if (games[id]) {
        following[id] = games[id];
        changed = true;
      }
    });
    if (changed) write(following);
  })();

  /* ---------------------------------------------------------------- follow */

  var buttons = slice(document.querySelectorAll("[data-follow]"));
  var renderBoard = function () {};

  function paint() {
    buttons.forEach(function (button) {
      var on = Boolean(following[button.dataset.follow]);
      button.setAttribute("aria-pressed", String(on));
      var icon = button.querySelector(".follow-icon");
      var text = button.querySelector(".follow-text");
      if (icon) icon.textContent = on ? "★" : "☆";
      if (text) text.textContent = on ? "Following" : "Follow";
      button.title = on ? "On My scoreboard - tap to remove" : "Add to My scoreboard";
    });
  }

  buttons.forEach(function (button) {
    button.hidden = false;
    button.addEventListener("click", function (event) {
      event.preventDefault();
      event.stopPropagation();
      var id = button.dataset.follow;
      following = read();
      if (following[id]) delete following[id];
      else if (games[id]) following[id] = games[id];
      write(following);
      paint();
      renderBoard();
    });
  });
  paint();

  /* ------------------------------------------------------------ scoreboard */

  var board = document.getElementById("scoreboard");
  if (!board) return;
  var empty = document.getElementById("scores-empty");
  var status = document.getElementById("scores-status");

  var SCOREBOARD = {
    ncaaf: "https://site.api.espn.com/apis/site/v2/sports/football/college-football/scoreboard?groups=80&limit=300&dates=",
    nfl: "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard?limit=100&dates="
  };
  var SPORT = { ncaaf: "College football", nfl: "NFL" };
  var scores = {};
  var timer = null;

  function element(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
  }

  function state(id) { return (scores[id] || {}).state || "pre"; }

  function statusText(id) {
    var game = following[id];
    var score = scores[id];
    if (score && score.state === "in") return "In progress · " + score.detail;
    if (score && score.state === "post") return score.detail || "Final";
    if (!score && Date.parse(game.kickoff) < Date.now()) return "Score not available yet";
    return game.when;
  }

  function teamRow(side, score, won, showScore) {
    var row = element("div", "score-team" + (won ? " won" : ""));
    if (side.logo) {
      var img = element("img", "crest small");
      img.src = side.logo;
      img.alt = "";
      img.width = 30;
      img.height = 30;
      row.appendChild(img);
    }
    row.appendChild(element("span", "score-name", side.short || side.abbr));
    row.appendChild(element("span", "score-pts", showScore ? score : ""));
    return row;
  }

  function gameCard(id) {
    var game = following[id];
    var score = scores[id] || {};
    var live = score.state === "in";
    var over = score.state === "post";
    var card = element("article", "card card-pad score-card" + (live ? " is-live" : over ? " is-final" : ""));

    var top = element("div", "score-top");
    top.appendChild(element("span", "score-status", statusText(id)));
    top.appendChild(element("span", "score-sport", SPORT[game.sport] || ""));
    card.appendChild(top);

    var shown = live || over;
    card.appendChild(teamRow(game.away, score.away, over && score.awayWin, shown));
    card.appendChild(teamRow(game.home, score.home, over && score.homeWin, shown));

    var actions = element("div", "score-actions");
    /* A card leaves the site at kickoff, so its link is offered until then. */
    if (Date.parse(game.kickoff) > Date.now() && game.path) {
      var link = element("a", "details-chip", "Details →");
      link.href = game.path;
      actions.appendChild(link);
    }
    var remove = element("button", "follow compact-text", "Remove");
    remove.type = "button";
    remove.setAttribute("aria-label", "Remove " + game.title + " from My scoreboard");
    remove.addEventListener("click", function () {
      following = read();
      delete following[id];
      write(following);
      renderBoard();
    });
    actions.appendChild(remove);
    card.appendChild(actions);
    return card;
  }

  var ORDER = { "in": 0, pre: 1, post: 2 };

  renderBoard = function () {
    var ids = Object.keys(following);
    board.textContent = "";
    if (empty) empty.hidden = ids.length > 0;
    if (!ids.length) {
      if (status) status.textContent = "";
      return;
    }
    ids.sort(function (a, b) {
      var sa = state(a);
      var sb = state(b);
      if (ORDER[sa] !== ORDER[sb]) return ORDER[sa] - ORDER[sb];
      var ka = Date.parse(following[a].kickoff);
      var kb = Date.parse(following[b].kickoff);
      return sa === "post" ? kb - ka : ka - kb;        // latest final first
    });
    ids.forEach(function (id) { board.appendChild(gameCard(id)); });
  };

  function clock(date) {
    try {
      return date.toLocaleTimeString("en-US", { timeZone: "America/New_York", hour: "numeric", minute: "2-digit" }) + " ET";
    } catch (e) { return date.toLocaleTimeString(); }
  }

  function nextDelay() {
    var now = Date.now();
    var busy = Object.keys(following).some(function (id) {
      var s = state(id);
      var kickoff = Date.parse(following[id].kickoff);
      return s === "in" || (s === "pre" && kickoff - now < 20 * MINUTE && now - kickoff < 6 * 60 * MINUTE);
    });
    return busy ? MINUTE : 10 * MINUTE;
  }

  function schedule() {
    window.clearTimeout(timer);
    if (!document.hidden && Object.keys(following).length) timer = window.setTimeout(refresh, nextDelay());
  }

  function refresh() {
    var ids = Object.keys(following);
    if (!ids.length) { renderBoard(); return; }
    var wanted = {};
    ids.forEach(function (id) {
      var game = following[id];
      if (SCOREBOARD[game.sport] && game.date) wanted[game.sport + "|" + game.date] = true;
    });
    var keys = Object.keys(wanted);
    var left = keys.length;
    var failed = 0;
    if (!left) { renderBoard(); return; }
    keys.forEach(function (key) {
      var parts = key.split("|");
      window.fetch(SCOREBOARD[parts[0]] + parts[1])
        .then(function (response) {
          if (!response.ok) throw new Error(String(response.status));
          return response.json();
        })
        .then(function (data) {
          (data.events || []).forEach(function (event) {
            if (!following[event.id]) return;
            var competition = (event.competitions || [])[0];
            if (!competition) return;
            var type = ((competition.status || event.status || {}).type) || {};
            var score = { state: type.state, detail: type.shortDetail || type.detail || "" };
            (competition.competitors || []).forEach(function (team) {
              score[team.homeAway] = team.score;
              score[team.homeAway + "Win"] = Boolean(team.winner);
            });
            scores[event.id] = score;
          });
        })
        .catch(function () { failed += 1; })
        .then(function () {
          left -= 1;
          if (left) return;
          if (status) {
            status.textContent = failed === keys.length
              ? "Scores are not available right now. Atlas will try again shortly."
              : "Scores updated " + clock(new Date());
          }
          renderBoard();
          schedule();
        });
    });
  }

  document.addEventListener("visibilitychange", function () {
    if (document.hidden) window.clearTimeout(timer);
    else refresh();
  });

  renderBoard();
  refresh();
})();
