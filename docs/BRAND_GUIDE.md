# Atlas Sports Intelligence — Brand Guide

---

## Name and tagline

**Atlas Sports Intelligence**

> Research. Analytics. Context.

Three nouns, no verb, no promise. The tagline is deliberately not a benefit
claim: everything in this category promises an outcome, and Atlas promises a
category of work.

In running text the product is **Atlas**. "Atlas Sports Intelligence" appears
in the wordmark, the footer and legal contexts. Never "ASI".

---

## Voice

Atlas writes like a research desk publishing to professionals: plain,
specific, unhurried, and willing to say when something is weak.

**Four rules.**

1. **Give the number, then its provenance.** "Utah's offence is 95th
   percentile on opponent-adjusted EPA" — not "Utah's offence has been
   excellent".
2. **State uncertainty in the same breath as the claim.** "51.9% against a
   49.5% baseline, on 214 games — not statistically distinguishable."
3. **Never be urgent.** No countdowns, no "before the line moves", no
   scarcity. The reader is not being hurried toward anything.
4. **Grade yourself down in public.** When the model is unreliable the card
   says so at the top, in the same typeface as everything else.

### Tone calibration

| Instead of | Atlas writes |
|---|---|
| "Atlas LOVES the under here" | "Atlas projects 52.3 against a market of 53.5" |
| "Massive edge on this total" | "An 11.2-point difference — the band where this model has been least reliable" |
| "Our model is 63-41 this season" | "Claimed 57% accuracy, realised 51.9%, across 1,262 games" |
| "Sharp money is on the under" | "The total opened 54.5 and is now 53.5" |
| "Trust the process" | "Here is the seven-season record" |

---

## Language rules

Atlas may never use these words **except** when describing a betting market
descriptively — "the moneyline", "the spread market", "books quoting this
game":

<!-- lang-lint: quoting -->
> bet · wager · lock · best bet · play · hammer · smash · unit

Also forbidden anywhere in the product surface: **pick**, **selection**,
**edge** as a noun meaning opportunity, **ROI**, **bankroll**, **Kelly**,
**stake**, **parlay**, **sweat**, **cash**, **fade**, **tail**.
<!-- lang-lint: end -->

### Permitted verbs for what Atlas does

**projects · reads · measures · grades · moved · sits · agrees · disagrees**

That list is short on purpose. If a sentence cannot be written with one of
those verbs, it is probably a recommendation wearing a disguise.

### Enforcement

This is not a style preference, it is a product constraint, and it is checked
rather than trusted. `tests/test_product_language.py` tokenises every file in
`docs/` and `design/` and fails on a forbidden word outside an allowed
descriptive context. The same discipline already governs the live tracker,
where `tests/test_live.py::test_the_tracker_never_computes_a_stake` scans
`atlas/live/` for money vocabulary.

A word gets added to the allow-list only with the sentence that justifies it
sitting beside it in the test.

A passage that **quotes** the vocabulary rather than using it — the list above,
the anti-pattern tables, the "never called" column — is wrapped in a visible
marker so the exemption is auditable in review rather than implicit:

```
<!-- lang-lint: quoting -->
...the passage that names the forbidden words...
<!-- lang-lint: end -->
```

The check is a tripwire, not a proof: a sentence that both states a
prohibition and breaks it would pass. It exists to catch the drift that
actually happens — a driver label, a marketing line, a phrase copied from a
competitor — not an adversary.

---

## The one thing Atlas will not do

Publish a side. Not as a "lean", not as an arrow, not as a highlighted row,
not "for entertainment".

A card that names a side becomes a selection the moment a reader screenshots it,
and everything else on the page then reads as justification. The entire
credibility of the grade depends on Atlas never having done this once.

---

## Wordmark

Set in the UI sans at 680 weight, −0.02em tracking. **Atlas** in ink,
**Sports Intelligence** in the muted tone at 500 weight.

```
Atlas Sports Intelligence
^^^^^ ink/680      muted/500
```

No icon in v1. An abstract mark would say nothing the wordmark does not, and
a globe-and-shoulders logo would be a pun the product has to live with
forever. Favicon is the letterform **A** on the off-white surface.

Clear space: the cap height of "A" on all sides. Never on a photograph, never
over a team colour, never in a team colour.

---

## Colour

The palette is specified in full in [`UI_SYSTEM.md`](UI_SYSTEM.md). Three
brand-level rules:

**Bright by default.** Off-white surfaces, slate ink. Dark mode exists so an
OS setting does not produce a glaring page at night; it is a restrained
restatement, never the designed default, and never used in marketing.

**Team colour is chrome, never data.** A team accent may tint a header rule or
a logo chip. It may never encode a value — two cards have to be comparable,
and team colours are not a scale. When two teams' accents are within 8 ΔE, the
away accent falls back to slate.

**Data colour is fixed and validated.** One blue, one red, one neutral,
validated for colour-vision deficiency against the product surface. Never
neon. Never a gradient standing in for a value.

---

## Typography

System sans throughout — `ui-sans-serif, system-ui, -apple-system, Segoe UI,
Inter`. It loads instantly, renders natively on every platform and looks like
software rather than like marketing.

**Every number in the product uses tabular figures.** A column of prices that
jitters as digits change is the fastest way to look amateur.

No display face, no serif, no italic except for genuine emphasis in prose.

---

## Social

One high-quality card graphic per post. Templates and approved copy shapes
are in `design/social-card.html`.

<!-- lang-lint: quoting -->
**Never post:** a side, a record of wins and losses, units, a countdown, a
screenshot of a bet slip, or another account's pick with commentary.
<!-- lang-lint: end -->

**Post:** a disagreement and what drives it; a line that moved and which way
Atlas reads it; the reliability record. Each with a link to the full card,
because the point of the post is the card.

The most on-brand post Atlas can make is a card it has graded **F**, with the
reason. Nobody else in the category will ever publish that, and it says more
about the product than any A-grade card could.

---

## Naming inside the product

<!-- lang-lint: quoting -->
| Concept | Name | Never called |
|---|---|---|
| The per-game page | **matchup card** | "the pick", "the play" |
| Model minus market | **difference** | "edge", "value" |
| A–F rating | **grade** | "confidence rating", "star rating" |
| The model's number | **projection** | "prediction", "our number" |
| Historical accuracy | **reliability record** | "track record", "results" |
| Line movement | **market intelligence** | "steam", "sharp action" |
<!-- lang-lint: end -->
