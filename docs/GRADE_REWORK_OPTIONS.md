# Atlas Grade — Rework Options

**Status: research. Nothing in this document is implemented.** The site still
computes the approved rubric from `ATLAS_CARD_SPEC.md` §5, unchanged.

The refinement brief asks for three options, their distributions on the real
slate, and a recommendation. Measuring them turned up something that changes
what the question is, so that comes first.

---

## 1. The finding: the grade is already the disagreement band, wearing a letter

The rubric has four components. On a real slate, three of them are constants.

| Component | Weight | Varies per card? |
|---|---|---|
| Data completeness | 15 | **No.** 1.000 on all 58 cards. |
| Calibration | 40 | **No.** A property of the band, not the card. |
| Signal stability | 20 | **No.** Also a property of the band. |
| Market agreement | 25 | Yes — but only within a band. |

Calibration and stability are both looked up from the disagreement band, so
they take exactly seven values. Completeness is a flat 15-point offset.
The only per-card term is agreement, and it is bounded by how wide its own
band is.

The consequence is that the score is a **step function of the band**. Applying
the rubric to all 5,071 gradeable games in the seven-season research sample:

| Band | Games | Score range | Gap to the band above |
|---|---|---|---|
| 0–1 | 773 | 85.9 – 88.0 | — |
| 1–2 | 782 | 85.6 – 87.6 | −1.7 (overlaps) |
| 2–4 | 1,280 | 80.1 – 84.3 | 1.3 |
| 4–6 | 908 | 71.5 – 75.7 | 4.4 |
| 6–8 | 598 | 65.3 – 69.4 | 2.1 |
| 8–10 | 326 | 56.4 – 60.6 | 4.7 |
| 10+ | 404 | 31.3 – 35.4 | 21.0 |

Seven disjoint clusters, each 2–4 points wide, separated by gaps of 1.3 to 21
points. No card can move from one cluster into another by being a better or
worse card; only by landing in a different band.

**So none of the three options is a curve. Each is a map from seven bands to
six letters.** The exception is Option A, which is the only scheme that can cut
*inside* a cluster — and that turns out to be its defect rather than its
feature.

Today's letter boundaries (90/80/70/60/50) map those seven clusters onto four
letters: A+ is above every cluster, D falls in the void between 8–10 and 10+.

---

## 2. Current state, measured

The approved rubric on the 58-card slate of 26 September:

| Grade | Cards | Share |
|---|---|---|
| A+ | 0 | 0% |
| A | 39 | 67% |
| B | 11 | 19% |
| C | 7 | 12% |
| D | 0 | 0% |
| F | 1 | 2% |

Scores 33.0 – 87.6, median 82.0. `PRODUCT_VISION.md` names this exact failure:
*"Grades cluster: if 80% of cards grade B, the grade is decoration."*

Two letters are unreachable, not unlucky. A+ needs 90 and the ceiling is 88.0,
because signal stability tops out at 6 of 7 seasons. D needs 50–60 and only the
8–10 band lands there — 6% of games.

---

## 3. Option A — Percentile grading

*A+ top 5%, A next 15%, B next 30%, C next 30%, D next 15%, F bottom 5%.*

The reference distribution has to come from somewhere, and the two candidates
behave differently enough that they are really two options.

### A1 — anchored to the week's own slate

| Grade | Cards | Share |
|---|---|---|
| A+ | 3 | 5% |
| A | 9 | 16% |
| B | 17 | 29% |
| C | 17 | 29% |
| D | 9 | 16% |
| F | 3 | 5% |

A textbook distribution, by construction. It has two defects and both are
fatal.

**It cuts inside clusters.** The B/C boundary lands at 82.0, which is the
middle of the 2–4 band. FAU at UL Monroe (2.1 points from the market) grades B;
UMass at Sacramento State (3.2 points) grades C. Both cards sit in the same
band, carry the same calibration evidence and the same seven-season record. The
letter that separates them is measuring a 1.1-point difference in disagreement
and calling it a grade difference. A reader comparing the two cards would
conclude something about them that is not true.

**It makes the letter mean a different thing every week.** Georgia Tech at
Stanford grades F on this slate at 6–8 points of disagreement — a band that
delivered 52.7% out of sample. Central Michigan at Miami also grades F at 11.2
points, in a band that delivered 49.5%. The scheme spends its bottom 5% on
whatever is worst this Saturday, whether or not it is bad. A week of tight
lines produces three unearned Fs; a week of blowout mismatches produces three
unearned A+s.

That second property is the one that kills it for this product. The grade is
screenshotted and compared. A letter that only means "relative to the other 57
games this Saturday" cannot survive being seen next to last week's.

### A2 — anchored to the seven-season history

Cut points from the historical score distribution: A+ ≥ 87.5, A ≥ 86.5,
B ≥ 81.2, C ≥ 67.4, D ≥ 32.8.

| Grade | Cards | Share |
|---|---|---|
| A+ | 5 | 9% |
| A | 12 | 21% |
| B | 18 | 31% |
| C | 19 | 33% |
| D | 4 | 7% |
| F | 0 | 0% |

Week-independent, which fixes the second defect. It does not fix the first, and
it adds a new one: because 8% of history sits in the 10+ cluster at ~33, the
bottom-5% cut falls *inside* that cluster. Central Michigan at Miami — 11.2
points from the market, the single worst card on the board — grades **D**, and
the F is empty. The scheme splits a tie group and produces the opposite of the
intended ordering at the exact point where the grade matters most.

**Verdict on A: reject.** Both anchorings slice clusters that the evidence says
are not separable; the slate anchoring additionally destroys week-to-week
comparability.

---

## 4. Option B — Absolute calibration thresholds

*The letter is a function of the measured calibration gap of the card's band.*

Thresholds on |claimed − realised|: ≤2pt A+, ≤5pt A, ≤9pt B, ≤14pt C, ≤20pt D,
else F.

| Band | Gap | Letter |
|---|---|---|
| 0–1 | −0.5 | A+ |
| 1–2 | −1.5 | A+ |
| 2–4 | −5.1 | B |
| 4–6 | −9.0 | B |
| 6–8 | −13.3 | C |
| 8–10 | −14.9 | D |
| 10+ | −27.8 | F |

| Grade | Cards | Share |
|---|---|---|
| A+ | 22 | 38% |
| A | 0 | 0% |
| B | 28 | 48% |
| C | 7 | 12% |
| D | 0 | 0% |
| F | 1 | 2% |

This is the honest option. Every letter means a fixed, published, measured
thing; the same card grades the same in week 2 and week 12; no two cards with
identical evidence get different letters.

It has one real problem and it is a bad one: **the alphabet has holes wherever
no band's gap happens to land**. A and D are empty here — not because no card
deserves them but because the gap steps from −1.5 to −5.1 and from −14.9 to
−27.8. Adding an eighth season moves the gaps and the holes move with them; a
product where the set of achievable letters changes when a season is added is
hard to explain and harder to trust.

It also fails the brief's own test. 38% at A+ and 86% at B-or-better is the
same clustering the sprint set out to fix, renamed.

**Verdict on B: right principle, wrong mechanism.** The principle — absolute,
published thresholds — is what the product needs. Deriving them from where the
gaps happen to fall is not.

---

## 5. Option C — Hybrid (recommended)

Three changes, in order of how much each one buys.

### C1 — Keep the rubric. Re-cut the letters between the clusters.

The score is a step function with known gaps. Put the boundaries in the gaps:

| Letter | Score floor | Bands it captures |
|---|---|---|
| A+ | 85 | 0–1, 1–2 |
| A | 79 | 2–4 |
| B | 70 | 4–6 |
| C | 60 | 6–8, 8–10 |
| D | 45 | *(empty at present)* |
| F | 0 | 10+ |

No boundary falls inside a cluster, so two cards with the same evidence can
never take different letters. Across the seven-season history:

| Grade | Share of 5,071 games |
|---|---|
| A+ | 31% |
| A | 25% |
| B | 18% |
| C | 13% |
| D | 5% |
| F | 8% |

On the 58-card slate: A+ 22, A 17, B 11, C 7, F 1.

This is strictly better than today — six letters reachable instead of four,
nothing arbitrary — and it is a three-line change to `LETTERS`. It does **not**
solve the clustering: 38% still land at A+, because 38% of cards genuinely sit
within 2 points of the market. That is a fact about an 0.89-weight
market-anchored model, not a fact about the rubric.

### C2 — Give the rubric a component that actually varies per card

This is the part that needs the research, and the research is done.

For the grade to distinguish two cards inside a band, something in the rubric
has to differ between them. Three candidates were tested against the
seven-season sample, in every case asking: *does this axis change the realised
calibration gap, and does it do so consistently season by season?*

| Candidate axis | Mean within-band gap spread | Stable across seasons? |
|---|---|---|
| Week of season (1–4 vs later) | 0.078 | **Yes — 6 of 7 seasons** |
| Total moved ≥1.5 since open | 0.090 | **Yes — 5 of 6 seasons** |
| Books quoting | 0.012 | No — and constant at 1 today |

Both surviving axes are worth about 2–3 points of calibration gap, against 27
points across the bands. Small, but they are the only things measured so far
that move card-to-card *within* a week, and both hold up under the same
season-by-season stability test the rubric already applies to its bands.

Proposed: the calibration component reads an **adjusted** gap —
`band.gap + δ_early + δ_moved`, with δ_early = −0.028 for weeks 1–4 and
δ_moved = −0.022 when the total has moved 1.5 or more since it opened. Both
adjustments worsen the gap, which lowers the grade, which is the direction the
evidence points. Both are recomputed from the warehouse at build time exactly
as `calibration_bands()` is, so neither can drift from the research.

With C1's boundaries and C2's adjustment, the slate becomes:

| Grade | Cards | Share |
|---|---|---|
| A+ | 0 | 0% |
| A | 26 | 45% |
| B | 14 | 24% |
| C | 17 | 29% |
| D | 0 | 0% |
| F | 1 | 2% |

The letters now interleave across bands — the 2–4 band spans A and B, the 4–6
band spans B and C — which is the first time in any option that the grade
distinguishes two cards the market treats the same way. The boundaries in the
table above would need re-cutting once for the new score range (29.8–84.4); the
principle of cutting between clusters is unchanged.

### C3 — Say the quiet part on the research page

After C1 and C2, 45% of this slate still grades A. That is the honest answer,
and the research page should carry it: *most cards are reliable, because most
cards sit near the market; the letter exists to find the minority that do not.*

A product that manufactures a bell curve out of a distribution that is not one
is lying about its own evidence, which is the single thing Atlas cannot afford.

---

## 6. Recommendation

**Adopt Option C, in the order C1 → C3 → C2.**

- **C1 now.** Re-cutting the letter boundaries into the gaps between clusters
  is small, safe, strictly an improvement, and needs only the decision that
  "A+" should mean "0–2 points from the market" rather than "unreachable".
- **C3 with it.** One paragraph on the research page, because C1 alone will
  produce a board that is 38% A+ and that will read as generous unless the
  reason is published beside it.
- **C2 after.** It is a change to what a grade measures, which is a bigger
  decision than a change to where the boundaries sit, and the two effects it
  adds are small. It should ship on its own so its effect is visible.

**Reject Option A** in both anchorings. **Reject Option B's mechanism**, adopt
its principle — C1 *is* absolute thresholds, derived from where the score
distribution is empty rather than from where the calibration gaps happen to
fall.

### What this does not fix

Data completeness is 15 points of every grade and is 1.000 on every card.
Either it should encode something that varies — the number of games behind each
team's profile is the obvious candidate — or its weight belongs elsewhere.
That is a fourth option and it is not researched here.

Market depth is the same story from the other direction: `books quoting` is 1
on all 58 cards because the live tracker captures one provider. The axis failed
the test above partly because the historical sample has almost no variation in
it. A second provider would be a tracker change, and it would give the rubric a
genuine per-card input.

---

## 7. How to reproduce every number here

```bash
python -m atlas.warehouse.build --include-scheduled
python -m atlas.site.build            # current distribution, in the build log
```

The band table, the historical score distribution and the two stability tests
come from `atlas.site.grade.calibration_bands` and
`atlas.research.market_aware` under the same walk-forward protocol as every
earlier phase — out of sample, point-in-time, no season used to grade itself.
