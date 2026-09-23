# Atlas — Timestamp Standard

One format, one zone, one rule. Implemented in `atlas/site/html.py::stamp`.

---

## The format

```
Sep 22, 2026 7:05 PM ET
```

`%b %-d, %Y` then `%-I:%M %p` then the literal `ET`. No leading zeros, no
seconds, no twenty-four-hour clock, no ISO strings on a page.

```python
from atlas.site.html import stamp
stamp(datetime(2026, 9, 22, 23, 5, tzinfo=UTC))   # "Sep 22, 2026 7:05 PM ET"
```

---

## The zone

**Everything a reader sees is Eastern. Everything Atlas stores is UTC.**

Storage in UTC because it is unambiguous and never skips or repeats an hour.
Display in Eastern because every schedule in this product is about American
football: a Saturday slate starts in the morning Eastern and ends after
midnight Eastern, and expressing that in UTC produces a window that drifts
twice a year when the clocks change.

The zone is always named. A clock time with no zone is a number a reader has
to guess about, and `scripts/audit_site.py` fails the build on one.

Daylight saving is handled by `zoneinfo`, not by an offset:

| Stored | Displayed |
|---|---|
| `2026-01-05 17:00 UTC` | `Jan 5, 2026 12:00 PM ET` (EST, −5) |
| `2026-07-05 17:00 UTC` | `Jul 5, 2026 1:00 PM ET` (EDT, −4) |

---

## The rule

> **A timestamp is the time of the last *successful* refresh of that thing.
> Never the time the page was built. Never the browser's clock.**

This is the whole reason `atlas/ops/freshness.py` distinguishes `last` from
`last_ok`. A failed poll is recorded so an operator can see it, and is
deliberately **not allowed to age a visible timestamp forward** — a reader
must never be told information is current because a refresh was *attempted*.

The consequence is visible and intended: a board rebuilt at 7:05 PM against a
market captured at 6:00 PM says **6:00 PM** for the market. That looks like a
bug for about five seconds and then looks like the only honest answer.

---

## What each surface stamps

| Surface | Label | Source |
|---|---|---|
| Board | `Updated` | this build's clock — this build *is* the publication |
| Matchup card | `Projection built` | last successful **heavy** refresh |
| Matchup card | `Market updated` | last successful **poll** |
| Social card | `Generated` | the build that rasterised it |
| Status page | all four, with ages | the freshness store |

Projections and market numbers age at different rates — the heavy refresh runs
daily, the poll hourly — so the card carries two stamps rather than one. A
single "updated" on a card would have to be the older of the two to be honest,
and would then understate how current the market is.

**A social card's stamp is not optional.** It outlives its page by months in
somebody's timeline, and a screenshot with no date is a claim about a game
that may already have been played.

---

## Where the format is enforced

- `atlas/site/html.py::stamp` is the only implementation. Nothing else
  formats a user-visible time.
- `tests/test_ops_schedule.py::test_the_stamp_format_is_the_one_in_the_specification`
  pins the exact string.
- `test_every_stamp_is_eastern_whatever_the_stored_zone` pins both sides of
  the daylight-saving boundary.
- `tests/test_site.py::test_a_stamp_names_its_zone` scans a rendered card for
  any clock time without `ET`.
- `scripts/audit_site.py` runs the same scan over all 182 built pages.

---

## What is not stamped, and why

**Kickoff times** use `day_and_clock` and `clock`, not `stamp` — they are
future events, not refreshes, and a date is already on the card.

**Research figures** carry no timestamp. They are computed from seven finished
seasons and change only when a season is added; a stamp would imply a
freshness they do not have and do not need.

**The 404 page** stamps nothing. It describes no data.
