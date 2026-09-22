# Atlas Sports Intelligence — UI System

The reference implementation is [`design/atlas.css`](../design/atlas.css) and
the wireframes in `design/`. This document is the contract those files
implement.

---

## Principles

**Bright, not dark.** The category is black backgrounds and neon. Atlas is
off-white and slate. This is the single most visible decision in the product.

**Mobile-first, genuinely.** The card is designed at 390px and expands. Every
layout rule in this system is written as a single column that gains columns,
never as a desktop grid that collapses.

**Density with air.** Bloomberg's information density, Apple's spacing. A
section is a card with 16px of padding and real whitespace between sections —
not a dense table pretending to be a dashboard.

**Numbers are the design.** Tabular figures everywhere, −0.03em tracking on
large values, and nothing decorative competing with them.

---

## Tokens

### Surfaces

| Token | Light | Dark | Use |
|---|---|---|---|
| `--bg` | `#fbfaf8` | `#14161a` | page |
| `--surface` | `#ffffff` | `#1b1e23` | cards |
| `--surface-sunk` | `#f4f3f0` | `#22262c` | wells, disclosures, meter tracks |
| `--border` | `#e6e4df` | `#2b3037` | hairlines |
| `--border-strong` | `#d4d1ca` | `#3a4049` | table heads, inputs |

### Ink

| Token | Light | Dark | Use |
|---|---|---|---|
| `--ink` | `#14181f` | `#f4f5f7` | primary text, values |
| `--ink-2` | `#3d4652` | `#c6ccd4` | body, row labels |
| `--ink-3` | `#6b7480` | `#9aa2ad` | notes, captions, section heads |
| `--ink-4` | `#949ba5` | `#737b86` | axis labels only |

Slate, not black. `#14181f` at 16px on `#fbfaf8` clears 15:1.

### Data

| Token | Light | Dark | Means |
|---|---|---|---|
| `--data-pos` | `#2a78d6` | `#3987e5` | Atlas, above the reference, home advantage |
| `--data-neg` | `#e34948` | `#e66767` | below the reference, away advantage |
| `--data-neutral` | `#9aa1aa` | `#7b838d` | the market — a reference, not a series |
| `--data-grid` | `#e9e7e2` | `#272b31` | gridlines |

Validated with the dataviz validator against both surfaces: lightness band,
chroma floor, CVD separation and contrast all pass; worst adjacent CVD ΔE
21.6, normal-vision ΔE 32.3.

The market is drawn in the neutral because it is a **reference**, like a
baseline or a gridline, not a competing series. That keeps every chart to one
coloured series, which is why no chart in this product needs a legend box.

### Status

Reserved. Never reused as a series colour, always shipped with an icon and a
label so state is never carried by colour alone.

| Token | Hex | Use |
|---|---|---|
| `--good` | `#0ca30c` | grade A/A+ |
| `--warning` | `#fab219` | grade C |
| `--serious` | `#ec835a` | grade D |
| `--critical` | `#d03b3b` | grade F, breached checks |

Grade B uses `--data-pos`, not a status colour: B is "fine", and a status
green for "fine" pushes A toward meaninglessness.

### Team accent

`--team-home` and `--team-away`, set per card. **Chrome only.**

Rules:
1. Never encodes a value. Ever.
2. Never used for text.
3. Appears in exactly two places: the 3px header rule and the 26px logo chip.
4. If the two teams' accents are within **8 ΔE** (OKLab ×100), the away accent
   falls back to `--ink-3`. Iowa State cardinal and Utah crimson are 4.1 apart,
   which is why the Iowa State card shows one red and one slate.
5. If an accent fails 3:1 against `--surface`, it is darkened to its nearest
   passing step rather than being used at low contrast.

---

## Type scale

| Role | Size | Weight | Tracking |
|---|---|---|---|
| Page title | 26 / 22 mobile | 700 | −0.025em |
| Stat value | 24 / 21 mobile | 680 | −0.03em |
| Card title (`h3`) | 15 | 640 | −0.01em |
| Body | 16 | 400 | — |
| Table / rows | 14 / 13 mobile | 400 | — |
| Section head (`h2`) | 11.5 | 640 | +0.09em, uppercase |
| Label | 10.5 | 620 | +0.07em, uppercase |
| Note | 12.5 | 400 | — |

Line height 1.5 for prose, 1.2 for values. Section heads are small uppercase
slate — they organise without shouting, which is what lets the numbers be the
loudest thing on the page.

---

## Layout

- Max width **1080px**. Gutter 16px mobile, 24px ≥720px.
- Sections are `.card` on `--surface` with 1px `--border`, 14px radius and a
  two-layer shadow that reads as paper rather than as elevation.
- `.grid-2` is one column, two at ≥720px.
- `.grid-3` is three columns, **two** at ≤460px — three 21px values do not fit
  on a 390px phone without wrapping.
- Vertical rhythm: 12px inside a section, 28px between sections.

### Breakpoints

| Width | Behaviour |
|---|---|
| ≤460px | 2-up stats, 13px tables, 21px values, 22px title |
| 461–719px | single column, full type scale |
| ≥720px | 2-up sections, 24px gutter |
| ≥1080px | centred, fixed max width |

No breakpoint above 1080. A wider viewport gets more margin, not more columns:
the card is a reading experience.

---

## Components

| Component | Class | Notes |
|---|---|---|
| Sticky nav | `.nav` | translucent, blurred, 1px bottom rule |
| Game header | `.game-head` | team accent rule, three-column team/at/team |
| Stat tile | `.stat` | label / value / note, tabular |
| Data rows | `.rows` | first column left, all others right, nowrap |
| Moneyline pair | `.ml` | own block — two prices never share a table cell |
| Grade badge | `.grade` | 74px, 2px ring in the status colour, score beneath |
| Component meter | `.meter-row` | 150px label, track, 50px value |
| Driver | `.driver` | name, magnitude, sentence, centred diverging bar |
| Disclosure | `.disclosure` | sunk well for anything that qualifies a number |
| Game row | `.game-row` | full-width link, grade pill right |
| Filter chip | `.filter` | `aria-pressed` carries state |
| Badge | `.badge` | icon + word, never colour alone |

### Meters

`.meter-track` must be `display: block`. An inline `<span>` ignores height and
overflow and the bar silently renders as a hairline — a real defect caught in
review, noted here so it is not reintroduced.

---

## Charts

Charts follow the dataviz method. Product-specific decisions:

**One series, no legend.** Every chart in the card has a single coloured
series against a neutral reference, directly labelled at the end of the line.
The only two-series chart is the calibration plot, where both series are
directly labelled — "claimed" and "realised" — and no legend box appears.

**Diverging where sign matters.** Driver bars are centred on zero: blue right,
red left, a 1px centre rule, and the two team names as the scale. A driver is
an advantage to one side, which is polarity, not magnitude.

**Never a dual axis.** Two measures of different scale become two charts.

**Every chart has a table.** The card's reliability section carries the same
figures in `.rows` beside the plot, which is the accessible view and also the
one people screenshot.

**Marks:** 2px lines, ≥8px markers, 4px rounded bar ends anchored to the
baseline, 2px surface ring on overlapping marks, recessive gridlines.

---

## Accessibility

- Body text ≥ 4.5:1; all data colours ≥ 3:1 against their surface.
- State never by colour alone: grades carry a letter, badges carry a glyph and
  a word, movement carries a sign as well as a hue.
- Every chart has `role="img"` and an `aria-label` that states the finding,
  not the geometry: *"the gap widens as disagreement grows"*, not *"a line
  chart of two series"*.
- Hit targets ≥ 44px. `.game-row` is a full-width link.
- Focus is visible and never removed.
- The layout survives 200% zoom at 390px because it is one column.

---

## Anti-patterns

Checked on every screen before it ships.

<!-- lang-lint: quoting -->
| Never | Why |
|---|---|
| Black background | the category's default; Atlas's most visible differentiator is not being it |
| Neon accents | reads as a betting product |
| Team colour encoding a value | two cards stop being comparable |
| A dual-axis chart | the most common serious chart error |
| A number on every point | the eye needs two or three, not twenty |
| Red/green for up/down | collides with the reserved status palette and fails CVD |
| A countdown or urgency cue | Atlas is never hurrying anyone |
| A highlighted "lean" row | that is a selection with extra steps |
| Decimal drift (`47.83333`) | three decimals, tabular, everywhere |
<!-- lang-lint: end -->
