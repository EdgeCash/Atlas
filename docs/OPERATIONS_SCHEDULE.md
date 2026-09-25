# Atlas — Operations Schedule

Three scheduled tasks, all Eastern. `atlas/ops/schedule.py` is the
implementation; this is what it does and why.

```bash
make ops-crontab        # print the schedule, ready to install
make ops-heavy          # 04:00 ET daily
make ops-poll           # every 15 minutes; the task decides whether to act
make ops-social         # 05:00 ET daily
make ops-health         # hourly; non-zero exit when stale
```

---

## The schedule

```cron
CRON_TZ=America/New_York

0 4 * * *    make ops-heavy    # warehouse, model, market, every page
0 5 * * *    make ops-social   # the featured card assets
*/15 * * * * make ops-poll     # market only; skips non-poll minutes
30 * * * *   make ops-health   # the check
```

**`CRON_TZ` is not optional.** Without it a 4 AM build becomes a 3 AM build in
November and the schedule silently moves an hour twice a season. A test pins
its presence.

---

## Track 1 — the heavy refresh · 04:00 ET daily

Rebuilds everything, in this order:

| Step | Command | Why here |
|---|---|---|
| 1 | `atlas.warehouse.build --include-scheduled` | the warehouse feeds everything |
| 2 | `atlas.live refresh --no-rebuild` | the model reads the warehouse |
| 3 | `atlas.live run` | capture the market before publishing |
| — | record `heavy` and `poll` | **stamps are written before the pages** |
| 4 | `atlas.site.build` | board, 58 cards, 116 team pages, social, status |

Two orderings matter and both are deliberate.

**The market is captured before the pages are written**, or the board would
advertise a market number older than the one already in the tracker.

**The stamps are recorded before the site is built**, because the site *reads*
them. A build that ran after a fresh capture must show the fresh time, not the
previous run's. Getting this backwards puts every timestamp on the site one
run behind, which is the kind of bug nobody notices for a month.

**04:00** because every West Coast game has finished and the day's scores have
settled, and because the board should be current before anybody is awake to
read it.

Runtime: about 7 seconds for the site, plus the warehouse rebuild. Use
`--skip-warehouse` to re-run the rest without it.

---

## Track 2 — the light poller · hourly

Market only. No warehouse, no model, no social assets.

| Step | Command |
|---|---|
| 1 | `atlas.live run` — capture the current market |
| — | record `poll` |
| 2 | `atlas.site.build --no-social` — republish with the new numbers |

**The projections on a card do not change.** Only the market numbers, the
difference, the grade (which moves with the market under V2), and the board's
stamp. The card keeps the heavy refresh's `Projection built` time, which is
the honest answer.

**Social assets are skipped.** Rasterising twelve PNGs every fifteen minutes
on a Saturday is the most expensive thing in the whole schedule, and nothing
about them has changed.

Runtime: about 10 seconds.

---

## Track 3 — game-day mode · every 15 minutes

| Window | Days | Hours ET |
|---|---|---|
| NCAAF Saturday | Saturday | 08:00 → midnight |
| NFL Sunday | Sunday | 07:00 → 20:00 |

Inside a window the poller runs every 15 minutes. Outside, hourly.

### One crontab line, two cadences

The cron entry fires every fifteen minutes always, and `poll()` decides
whether this minute is a poll minute:

```python
schedule.should_poll(now)   # minute % poll_interval_minutes(now) == 0
```

Off a game day, fourteen of every fifteen invocations log one line and exit,
costing **no provider request**. On a game day all four fire.

This is deliberately in the code rather than in two crontab lines. Two
schedules would eventually disagree with each other — one updated, one not —
and the disagreement would be invisible. One schedule that the task owns can
be tested, and it is: eight parametrised cases pin the window boundaries,
including the one past midnight that does *not* count as Saturday.

### API budget

| | Requests per week |
|---|---|
| Hourly poller, 5 ordinary days | 120 |
| Game-day Saturday, 16 hours × 4 | 64 |
| Game-day Sunday, 13 hours × 4 | 52 |
| Heavy refresh | 7 |
| **Total** | **~243** |

One ESPN scoreboard request each, unauthenticated, against a public endpoint —
comfortably inside anything that could be called a rate limit. The skip logic
is what keeps it there: without it the same crontab would make 672.

---

## Track 4 — social automation · 05:00 ET daily

An hour after the heavy refresh, so the assets are made from the cards that
refresh just published rather than from yesterday's.

Twelve files: six cards chosen as a spread across the grade range, each as
1200×675 and 1080×1080, SVG and PNG at 2×. The spread is what guarantees a
**marked-down card is always available** without anybody making one specially.

The build records the `social` stamp itself, because only the build knows how
many files it actually produced.

---

## Track 5 — health checks · hourly at :30

```bash
make ops-health     # exit 0 healthy, exit 1 blocking failure
```

| Check | Limit | Blocking |
|---|---|---|
| Last successful poll | 2 hours | **yes** |
| Last successful heavy refresh | 24 hours | **yes** |
| Board timestamp | 3 hours | **yes** |
| Social assets | 48 hours | no |
| Poll failure streak | 3 consecutive | no |
| Heavy failure streak | 3 consecutive | no |

Thresholds are generous on purpose. Two hours is two missed hourly polls or
eight missed game-day polls; an alert that fires on a single miss is an alert
an operator learns to ignore, and an ignored alert is worse than none.

Wire it to anything that reads an exit code — `||` into a mail command, a
systemd `OnFailure=`, a monitoring agent. Atlas ships the check, not the
alerting.

---

## Retune · by hand, after a model change

Not on the schedule. **Actions → retune → Run workflow** (`.github/workflows/retune.yml`)
re-runs the model walk-forwards on the full warehouse: `ncaaf` (benchmarks,
prior, state, total), `nfl` (benchmarks, state, total), or `both`.

* It restores the heavy run's warehouse cache and never saves it, so it
  cannot change what production builds from. The college half refuses to run
  without `CFBD_API_KEY`: the prior is fitted on CFBD features, and a retune
  without them would tune a model production does not run.
* It proposes, it does not publish. `reports/` goes to a branch
  `retune/<run number>` and to an artifact, and a pull request is opened
  where the repository lets Actions open one (Settings → Actions → General →
  "Allow GitHub Actions to create and approve pull requests"); otherwise the
  run prints the compare link.
* It dispatches CI on its branch itself. A push or pull request made with the
  workflow's own token starts no other workflow, so without that the pull
  request would have no checks at all.
* The saved choices it writes (`reports/*_state_choices.json`) are what the
  live projectors read, so merging that pull request moves live numbers from
  the next heavy run.

## Failure behaviour

**Every task is safe to run twice.** The warehouse rebuild is idempotent, the
tracker appends only on change, and the site build writes into a fresh
directory.

**A failed task records the failure and exits non-zero without advancing any
timestamp a reader can see.** That is the entire point of `last` versus
`last_ok` in the freshness store. Concretely:

| Failure | What a reader sees |
|---|---|
| Poll fails | the board keeps yesterday's market stamp and goes stale visibly |
| Heavy fails | projections keep the previous day's stamp |
| Site build fails | the previous build stays served; nothing is half-written |
| Provider is down | the poll fails, the streak check fires after three |

**Nothing retries automatically.** The next scheduled run is the retry, and it
is at most fifteen minutes away. A task that retries inside its own window can
hammer a provider that is already struggling.

---

## Installing

```bash
make ops-crontab --root /srv/atlas | crontab -
mkdir -p /var/log/atlas
```

Requirements: Python, the repository, and write access to `data/` and `site/`.
No database, no daemon, no queue. The freshness store is a single JSON file
written atomically through a temporary file in the same directory, so a poll
killed mid-write cannot leave a truncated file behind.
