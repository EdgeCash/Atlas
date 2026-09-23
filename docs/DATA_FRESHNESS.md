# Atlas — Data Freshness

How Atlas knows when each part of itself last succeeded, and how that reaches
a reader.

---

## The problem

A static site fails quietly. The board keeps serving, the cards keep
rendering, and the only symptom of a poller that died on Thursday is a market
number that stopped moving. A build that succeeds against stale inputs is
byte-for-byte indistinguishable from one that succeeded against fresh ones.

Everything here exists to make that difference visible — to an operator
through an exit code, and to a reader through a timestamp.

---

## The store

`data/ops/freshness.json`, written by `atlas/ops/freshness.py`.

```json
{
  "last":    { "poll": { "at": "...", "ok": false, "detail": "provider 503" } },
  "last_ok": { "poll": { "at": "...", "ok": true,  "detail": "market in 3s" } },
  "history": [ ... last 50 runs per event ... ]
}
```

Four events: **heavy**, **poll**, **social**, **build**. Anything else raises
— an unrecognised event name is a typo, not a new event.

### `last` versus `last_ok`

The single most important distinction in this system.

- **`last`** is the most recent run, successful or not. The operator's view.
- **`last_ok`** is the most recent *successful* run. **The reader's view.**

Every page stamp reads `last_ok`. A failed poll is recorded so it shows on the
status page and in the failure-streak check, and is **not allowed to age a
visible timestamp forward**. A reader must never be told information is
current because a refresh was *attempted*.

### Durability

Written through `tempfile.mkstemp` in the same directory and `os.replace`d
into position. A poll killed mid-write cannot leave a truncated JSON file that
every later build has to recover from.

A corrupt file does not stop a build — `load()` logs a warning and returns an
empty state. A site with no timestamps is recoverable; a site that will not
build is not.

---

## How a stamp reaches a page

```
atlas.live run            → freshness.record("poll")
atlas.site.build          → _freshness() reads last_ok
                          → render.freshness_badge(...)
                          → freshness.record("build")
```

`build._freshness()` returns four strings:

| Key | Source | Shown as |
|---|---|---|
| `projection` | `last_ok["heavy"]` | card: *Projection built* |
| `market` | `last_ok["poll"]` | card: *Market updated* |
| `board` | **this build's clock** | board: *Updated* |
| `social` | this build's clock when it is making them, else `last_ok` | social card: *Generated* |

The board and the social cards use this build's clock because **this build is
the publication** — reading the previous record would put them a run behind.
Projections and market numbers describe work done by *other* tasks, so they
read those tasks' records.

---

## How stale is stale

| Thing | Refreshed | Alert limit | Why |
|---|---|---|---|
| Market | hourly, 15 min on game days | **2 hours** | two missed hourly polls, or eight game-day ones |
| Projections | daily 04:00 ET | **24 hours** | they only change when the warehouse does |
| Board | every poll and every heavy run | **3 hours** | a reader looking at a four-hour-old board on a Saturday is looking at the wrong market |
| Social assets | daily 05:00 ET | 48 hours, warn only | a publishing convenience, not information |

Thresholds are generous by design. An alert that fires on one missed poll is
an alert an operator learns to ignore.

---

## What a reader sees

**Board** — one line under the heading:

> **Updated** Sep 22, 2026 10:43 PM ET · Data status

**Card** — two lines at the end of the five-second view, because projections
and market numbers age at different rates:

> **Projection built** Sep 22, 2026 4:00 AM ET  **Market updated** Sep 22, 2026 10:00 PM ET · Data status

**Social card** — in the footer, because it outlives its page:

> Generated Sep 22, 2026 5:00 AM ET

**Status page** — all four, with their ages, the provider state, the tracker
counts and the health checks. `STATUS_PAGE_SPEC.md`.

Every stamp links to `/status.html`. A number a reader cannot investigate is a
number they have to take on trust, which is the thing this product exists not
to ask for.

---

## Honest by construction

Three properties fall out of the design rather than being maintained by
discipline:

**A rebuild cannot fake freshness.** The market stamp comes from the poll's
record. Rebuilding the site a hundred times does not move it.

**A failure is visible before it is reported.** The board's stamp ages in
public. A reader can see the site is stale without reading the status page,
and the status page tells them why.

**The known limitation is on the status page, not only in a caution.** `Books
quoting: 1` is flagged red there with the reason. Putting a product's weakest
number on its own status page is the same discipline as publishing an F card.

---

## Tests

| Test | Property |
|---|---|
| `test_a_failed_run_never_advances_a_visible_timestamp` | the `last`/`last_ok` contract |
| `test_history_keeps_failures_so_an_operator_can_see_them` | failures are recorded, not swallowed |
| `test_an_unknown_event_is_a_typo_not_a_new_event` | the event list is closed |
| `test_a_corrupt_provenance_file_does_not_stop_a_build` | recovery |
| `test_every_public_surface_carries_a_freshness_stamp` | Track 6 |
| `test_a_stamp_names_its_zone` | no bare clock times |
| `scripts/audit_site.py` | the same two checks over all 182 built pages |
