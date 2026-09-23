# Atlas — Launch Day Plan

The sequence, the checks, and how to undo it.

---

## Before the day

Four things, none of them product work.

1. **Answer the jurisdiction question.** Atlas publishes no selections and
   takes no money, so it is not a gambling service — but it describes betting
   markets, and jurisdictions differ on what that requires. It is legal, it is
   the only genuine blocker, and it should be settled before a public URL
   exists rather than after.
2. **Write the privacy note.** Half a page. Atlas logs less than almost any
   site on the internet, and that is worth saying rather than leaving implied.
   `ANALYTICS_SPEC_FINAL.md` has the content.
3. **Stand up hosting.** `DEPLOYMENT_GUIDE.md`. DNS, HTTPS, the schedule
   installed, `/var/log/atlas` writable, and the off-machine backup line.
4. **Create the accounts.** `beta@atlas.football`, and the handles on X,
   Threads and Instagram with the bio from `FINAL_CONTENT_COPY.md`.

---

## T−1 day

```bash
git pull
make launch-check          # audit → SEO → 299 tests → lint. Must be green.
make ops-heavy             # a real build from real sources
make ops-health            # must exit 0
make ops-status            # eyeball the freshness and provider rows
make ops-backup            # and copy it off the machine
```

Then by hand, because no test can:

- [ ] Open the board, a card, a team page and `/status.html` on a **real
      phone**, not a viewport emulator.
- [ ] Paste a card URL into X and into iMessage; confirm the unfurl shows the
      right title, description and image.
- [ ] Load `/404.html` and a path that does not exist; confirm the web server
      serves the former for the latter.
- [ ] Click **feedback** and confirm the mail client opens with the subject
      filled in.
- [ ] Confirm the board's timestamp is inside the last hour.

---

## Launch morning

**04:00 ET** — the heavy refresh runs on its own schedule. Do not trigger it
by hand; watching the scheduled build run unattended *is* the last test.

**07:00 ET** — verify:

```bash
make ops-health && make ops-status
```

Board stamped within the hour, market within the hour, projections from 04:00,
social from 05:00. If any of those is wrong, stop and fix before publishing a
link. A launch with a stale timestamp is worse than a launch a day late,
because the timestamp is the promise.

**09:00 ET** — publish.

1. **The landing page is the link**, not the board. `LAUNCH_PLAN.md`: a
   first-time visitor needs the thirty seconds before the 58 cards.
2. **One social post: the marked-down card, with the reason.** Not an
   announcement thread. The product explains itself better than a thread
   would, and leading with a card Atlas graded F is the entire positioning in
   one image.
3. Nothing else. No countdown, no "we're live!!" — `BRAND_GUIDE.md` rule 3
   applies to launch day too.

---

## The first 24 hours

| When | Do |
|---|---|
| Hourly | `make ops-health`. It exits non-zero when anything is stale. |
| Once | `make ops-analytics` after a few hours — mostly to confirm the log parses |
| Continuously | read `beta@atlas.football` |
| **Do not** | change anything in response to the first day's traffic |

That last row matters. Day-one traffic is a launch post, not an audience. The
numbers that mean something are in `POST_LAUNCH_METRICS.md` and they need a
season.

### What "going wrong" looks like

| Symptom | Severity | Action |
|---|---|---|
| A page names a side, or a forbidden word appears | **stop and roll back** | the audit missed a category; fix, add the check, redeploy |
| A card shows a wrong number | high | fix the input, `make ops-heavy`, redeploy |
| The board's timestamp stops moving | high | `make ops-health`, check `poll.log` |
| A page 404s that should not | medium | check the deploy's `--delete` |
| Slow under load | low | it is a static site; check the host, not Atlas |
| Someone screenshots a card as a pick | **not a failure** | it is what the grade and the disclaimer are for |

---

## Rollback

Atlas is a static site built from a git checkout. A rollback is a checkout and
a rebuild — there is no migration to reverse and no state to unwind.

### Rolling back the site — about two minutes

```bash
cd /srv/atlas
git log --oneline -5
git checkout <last-good-sha>
make site
rsync -a --delete site/ /var/www/atlas/
```

The build is deterministic — two consecutive builds produce 351 of 352
byte-identical files — so the rebuilt site is the site that was there before,
not an approximation of it.

### Rolling back the data

**The tracking store is append-only and must not be rolled back.** Signals are
opinions published at a moment; removing one because a later build was wrong
would corrupt the only record Atlas cannot rebuild. If the store is genuinely
damaged:

```bash
python -c "from pathlib import Path; from atlas.ops import backup; \
           b = backup.latest(); print(backup.verify(b)); \
           backup.restore(b, Path('/tmp/restored'))"
```

`restore` refuses to write over the live store on purpose. Compare, then move
it deliberately, by hand.

### Stopping everything

```bash
crontab -r          # the site keeps serving; it simply stops refreshing
```

Timestamps then age in public and `/status.html` turns **Degraded** on its
own. That is the designed behaviour: a reader can see Atlas has stopped
without being told.

### Taking it down

Point the web server at a holding page. Do not delete `site/` — it is a build
artefact and deleting it destroys the thing a rollback would have served.

---

## Definition of done

Launch is complete when all of these are true for a week:

- [ ] `make ops-health` exits 0 on every hourly run
- [ ] The board's timestamp is never older than three hours
- [ ] Backups run daily, verify clean, and land off the machine
- [ ] The access log parses and the marked-down share is a real number
- [ ] No severity-1 feedback
- [ ] The scheduled tasks have run unattended through one full game weekend —
      **Saturday's fifteen-minute cadence is the real test**, and nothing
      before launch exercises it under load

Then, and only then, the roadmap resumes: a second market provider, and the
public reliability record.

---

## The one-line version

> Settle the legal question, stand up hosting, let the 04:00 build run by
> itself, check the timestamps, post the F card, and change nothing for a
> week.
