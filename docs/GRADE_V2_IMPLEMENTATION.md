# Atlas Grade V2 — Implementation

**Implemented.** `atlas/site/grade.py` is V2; V1 is gone. The research behind
it is `GRADE_STRATEGY_V2.md`, and `GRADE_REWORK_OPTIONS.md` is the sprint
before that which established why V1 could not be salvaged by relabelling.

---

## What changed, in one paragraph

V1 looked calibration up in a seven-row table of disagreement bands, which made
the score a step function: seven clusters, four reachable letters, 67% of a real
slate at A. The bands were an artifact of the research report's own buckets, not
a property of the data. V2 fits the curve those buckets were summarising, so the
score is continuous, every letter is reachable, and a card's letter depends on
that card alone.

---

## The rubric

```python
WEIGHTS = {"calibration": 45, "agreement": 25, "conditions": 15, "completeness": 15}
LETTERS = ((96, "A+"), (90, "A"), (79, "B"), (66, "C"), (51, "D"), (0, "F"))
```

| Component | Weight | Reads |
|---|---|---|
| Calibration | 45 | `1 − |gap| / 0.35`, where `gap` is the fitted curve plus the condition penalties |
| Market agreement | 25 | `1 − d / 12`, unchanged from V1 |
| Card conditions | 15 | season maturity and how settled the market is |
| Data completeness | 15 | unchanged from V1 |

**Signal stability is gone.** It measured "in how many of seven seasons did this
band beat 50%", which is a property of a band, and there are no bands any more.
Its 20 points went to calibration (+5) and to the new conditions component (15).

### The curve

```python
@dataclass(frozen=True)
class Curve:
    a: float; p: float; games: int; r: float; seasons: int
    def gap(self, disagreement: float) -> float:
        return -self.a * max(abs(disagreement), 0.05) ** self.p
```

`calibration_curve()` fits it from the warehouse on every build. It slices the
walk-forward results at half a point, keeps slices with at least 40 games, and
does a least-squares fit in log space on the slices where the model undershot
its claim. Slices where the model happened to beat its claim carry no
information about the decay and are left out rather than clamped.

The current fit, printed in the build log:

```
calibration curve: gap(d) = -0.0133 * d^1.139  (r=0.88, n=5006)
```

**Refitted, never transcribed.** The coefficient moves by about 2.5× across
seasons; a hard-coded constant would silently drift away from the research the
card cites. This is the same discipline `calibration_bands()` already followed.

### Conditions

```python
EARLY_SEASON_WEEKS   = 4      EARLY_SEASON_PENALTY = -0.028
UNSETTLED_MOVE       = 1.5    UNSETTLED_PENALTY    = -0.022
```

Both were measured in the previous sprint and both held season by season: weeks
1–4 calibrate worse in 6 of 7 seasons, a total that has moved 1.5 points or more
since it opened calibrates worse in 5 of 6. They apply twice — as a penalty on
the expected gap, and as the `conditions` component — because they describe both
how reliable the card is and what kind of card it is.

They are small: two to three points of calibration gap against twenty-seven
across the range. They are also the only inputs that separate two cards the
market treats the same way, which is what makes 53 of 58 cards score distinctly.

---

## Results

### Seven seasons, 5,006 graded games

| Letter | Share |
|---|---|
| A+ | 6% |
| A | 14% |
| B | 31% |
| C | 25% |
| D | 15% |
| F | 10% |

### The 58-card slate of 26 September

| Letter | V1 | V2 |
|---|---|---|
| A+ | 0 | 0 |
| A | 39 | 7 |
| B | 11 | 23 |
| C | 7 | 17 |
| D | 0 | 10 |
| F | 1 | 1 |

Distinct scores: **53 of 58**, against 6 under V1. The board's summary line went
from "39 graded A or better · 1 marked down" to "7 graded A or better ·
11 marked down".

---

## The brief's four requirements

| Requirement | How it is met |
|---|---|
| **Absolute thresholds** | `LETTERS` is a module constant. Nothing about a card's letter reads any other card. |
| **Stable week to week** | The thresholds do not move. The fitted curve moves only when a season is added, and then it moves for every card at once. |
| **Reach every letter** | `test_every_letter_is_reachable` sweeps disagreements from 0 to 20 points and asserts all six letters come out. |
| **No slate-relative grading** | `test_the_thresholds_are_absolute_and_never_slate_relative`. There is no code path from one card's grade to another's. |

One nuance on stability worth stating because it is new behaviour: **a card's
letter can now change as the market moves.** Under V1 a card had to cross a band
boundary to change letters; under V2 every tick of the total moves the score.
This is honest — a card whose market has moved three points really is a
different card — but it means a screenshot is a snapshot, and the card says
when it was generated.

---

## Rule 4: the grade teaches itself

Every grade carries a three-line lesson, computed from its own numbers:

```
Historically unreliable.
A very large disagreement of 11.2 points.
Across seven seasons, cards this far from the market claimed 77% accuracy
and delivered 50%. Atlas marks its own card down.
```

```
Historically reliable.
Atlas and the market are closely aligned, 0.4 points apart.
Across seven seasons, cards this close to the market claimed 51% accuracy
and delivered 51%.
```

The three lines are always the same three things: **what the letter says, what
Atlas did, and the record behind it.** A letter is a symbol, and a symbol a
reader has to be taught somewhere else is a symbol they skip — so every card
teaches it again.

The panel below adds the arithmetic:

> Atlas sits **11.2 points** from the market. The calibration curve, fitted to
> seven seasons out of sample, expects cards at that distance to fall **24.6%**
> short of what they claim — which is where the calibration component above
> comes from.

and then the conditions in words: *"It is week 4. Team profiles are still shrunk
toward last season, and early-season cards have calibrated worse in six of seven
seasons."*

### The A+ caveat

A+ does not say "high confidence" and stop. It says:

> Agreement is where this model is most reliable, and where it is adding least —
> a top grade means trust the number, not that this is the card to read first.

This is the finding from `GRADE_STRATEGY_V2.md` §5, and it is on the card
because leaving it off would let the grade be read as a ranking of what to look
at. Cards where Atlas and the market agree to within a point realise 50.8%
against a 51.3% claim — a coin flip, p = 0.69. **An A+ card is one where Atlas
has contributed nothing.** A test pins that the top of the scale says so.

---

## Tests

| Test | Property |
|---|---|
| `test_the_rubric_weights_sum_to_one_hundred` | arithmetic |
| `test_a_larger_disagreement_can_never_raise_a_grade` | the product's central claim |
| `test_a_steeper_calibration_curve_can_never_raise_a_grade` | replaces V1's band-gap monotonicity |
| `test_early_season_and_an_unsettled_market_can_never_raise_a_grade` | both adjustments point down |
| `test_the_letter_boundaries_match_the_specification` | the six thresholds |
| `test_the_thresholds_are_absolute_and_never_slate_relative` | the brief's requirement |
| `test_every_letter_is_reachable` | the brief's requirement |
| `test_the_grade_teaches_itself_in_three_plain_lines` | Rule 4 |
| `test_the_top_of_the_scale_says_atlas_is_adding_least` | the A+ caveat |
| `test_missing_inputs_cost_the_completeness_component` | 15 points, proportional |
| `test_a_worked_example_from_the_specification` | the F card, pinned at 44.5 |

The tests hold a fixed `Curve` and vary the card, because the real curve is
refitted every build and these are assertions about the rubric's shape rather
than about this week's numbers.

---

## Migration notes

- `grading.compute()` now requires a `curve` keyword and takes an optional
  `conditions`. `data.build_cards` passes both.
- `Grade.stability` became `Grade.conditions`; `Grade` also gained `lesson`,
  `disagreement`, `expected_gap` and `condition_notes`.
- `calibration_bands()` and `Band` are **kept**, unchanged. V2 does not grade
  from them, but the reliability record on the card and the research page still
  report by band — a table of seven rows is how a reader checks a curve — and
  the lesson's third line quotes the band's claimed-versus-realised record.
- Build time is unchanged at about 7 seconds; the curve fit shares its
  walk-forward frame with the band table.

---

## What V2 does not fix

**Data completeness is still 1.000 on every card**, so 15 of the 100 points are
a constant offset. The obvious variable candidate is how many games sit behind
each team's profile.

**Market depth still carries no information.** `books quoting` is 1 on all 58
cards because the live tracker captures one provider, and the historical sample
has almost no variation in it either — which is why that axis failed the
stability test. A second provider is a tracker change and it would give the
rubric a genuine per-card input.

**The curve is fitted on the total market only.** Spreads are anchored at weight
1.00, so there is no independent Atlas spread number to calibrate.
