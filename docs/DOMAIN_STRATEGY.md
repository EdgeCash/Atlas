# Atlas — Domain Strategy

Brand risk, availability, conflicts. **Nothing here was checked against a
registrar** — this container has no lookup access and the study is deliberately
not guessing at live WHOIS. Every probability below is an estimate from the
name's shape and history, and each is marked with how it could be confirmed in
a minute at a registrar.

---

## The structural finding

**`.football` is the correct TLD for this product, not a fallback.**

The scope is fixed and documented: NCAAF now, NFL staged behind calibration,
and `ATLAS_FEATURE_ROADMAP.md` lists *"other sports"* under **Never**. A
`.football` domain covers the entire declared universe exactly, reads
unambiguously in a social post, and is already wired through the build as
`SITE_URL = "https://atlas.football"` — in every canonical tag, the sitemap,
the Open Graph URLs and both social templates.

It also releases the study from the constraint that otherwise decides naming:
`.com` availability. `atlas.com` is unobtainable at any realistic price;
`atlas.football` is not. That is why single dictionary words were candidates at
all.

**The cost.** A category TLD reads newer and less institutional than `.com`,
and some people will type `.com` regardless. Both are acceptable for a product
whose acquisition is social rather than typed — and unacceptable the day the
product adds a third sport, which is the first flip condition in
`FINAL_5_BRANDS.md`.

---

## Atlas — the recommended brand

| | |
|---|---|
| **Primary** | `atlas.football` — **in the code today** |
| **Brand risk** | **moderate–high**, and structural rather than legal |
| **`.com` availability** | ~0%. Long-registered, six figures if it trades at all. |
| **`.football` availability** | high — the TLD is thinly registered |

### Conflicts, ranked by how much they matter here

1. **Club Atlas** — Liga MX football club, founded 1916. **The sharpest
   conflict in the study**, because it is in the sports category and on a
   `.football` domain. Mitigated by sport, language and geography: soccer,
   Spanish, Mexico. Nobody looking for American college football cards lands
   on a Guadalajara club by accident.
2. **Atlassian** — the largest tech "Atlas" and the most likely to have
   defensive filings. Different class, different product, no consumer overlap.
3. **MongoDB Atlas** — a product name, not a company. Crowds developer search;
   irrelevant to a sports audience.
4. **Atlas Obscura** — travel media. Adjacent *register* (premium editorial),
   unrelated category. The nearest thing to a tonal collision.
5. **Atlas Air, Atlas Copco, Atlas Van Lines** — industrial. Noise.

### Consequences

**Search.** "Atlas" alone is unwinnable. "Atlas sports intelligence" is
winnable, and "atlas college football" probably is. This is why the wordmark
lockup is **Atlas Sports Intelligence** and not bare Atlas — the qualifier is
doing search work as well as clarity work.

**Social.** `@atlasfootball` or `@atlas_football` — plain "atlas" is certainly
taken on every platform. Handle availability should be checked **before** the
domain, because a good domain with no matching handle is the worse outcome for
a product whose distribution is social.

### To register

| Priority | Domain | Why |
|---|---|---|
| **1** | `atlas.football` | the canonical; already in the build |
| 2 | `atlasfootball.com` | typo insurance and the `.com` reflex |
| 3 | `atlassportsintelligence.com` | the full lockup; email and legal |
| 4 | `atlas.fo`  / short redirects | optional |

Do **not** buy defensively across `.net`, `.org`, `.io`, `.co`. That is a
five-figure habit protecting against a risk that does not exist for a product
with no transactional surface.

---

## Lodestar — the runner-up

| | |
|---|---|
| **Primary** | `lodestar.football` |
| **Brand risk** | **low** |
| **`.com` availability** | ~5%. A real word; almost certainly registered, possibly parked and buyable in the low thousands. |
| **`.football` availability** | very high |

**Conflicts.** Lodestar Capital and similar fund names; a UK software
consultancy; scattered small use. **Nothing in sports, nothing consumer-facing,
nothing at scale.** This is the entire reason it is the runner-up.

If the flip conditions in `FINAL_5_BRANDS.md` fire, `lodestar.com` is worth a
broker approach — a single word with no dominant holder is the kind of domain
that trades.

---

## The other finalists

| Name | `.com` | `.football` | Risk | Note |
|---|---|---|---|---|
| **Brier** | ~15% | very high | **lowest in the study** | a surname and a place name; almost no commercial holder. The most *available* name is also the least *legible*. |
| **Almanac** | ~2% | high | moderate | many almanacs; Baseball Almanac is directly adjacent |
| **Calibre** | ~2% | high | moderate | Calibre the e-book manager is well known to exactly the technical audience; and the `Calibre`/`Caliber` split fragments the brand across markets |

---

## The two owned domains

Scored as if unowned, as instructed. Both lose.

### EdgeEquation.com

**Owned, and unusable.** `BRAND_GUIDE.md` forbids **"edge" as a noun meaning
opportunity** anywhere on the product surface, and the naming table says model
minus market is called *the difference* and **never** "edge". The company would
be unable to write its own name on a page obeying its own rules.

Beyond the prohibition: "edge" is the most gambling-coded word in the category
after "bet", it fails the agency test, and it reads as a quant fund.

**Recommendation: retain, park, never use.** A short `.com` has residual value
and costs about a tenner a year. It is not a brand.

### ForgeSportsAnalytics.com

**Owned, and weak.** Passes both gates and loses on every other axis: 23
characters, three words, un-social, and "Sports Analytics" as a suffix is a
2015 name that dates the company on day one. "Forge" also means *to
counterfeit* — for a product whose entire claim is verifiability, "a forgery"
is an unfortunate second reading.

**Recommendation: retain, park, never use.**

**Owning a domain is not an argument for a name.** Both were scored blind and
both lost to candidates with no domain at all — which is exactly the outcome
the brief asked the study to be capable of producing.

---

## Before launch, in this order

1. **Trademark search**, classes 9 and 41, for Atlas in sports information.
   The one item that could overturn the YES. A lawyer's job.
2. **Social handles** on X, Threads and Instagram. Check before the domain — a
   good domain with no handle is the worse half.
3. **Register** `atlas.football`, `atlasfootball.com`,
   `atlassportsintelligence.com`.
4. **Email** — `beta@atlas.football` is already referenced in the footer and
   in `BETA_FEEDBACK_LOOP.md`.
5. **Park** the two owned domains. Do not redirect them to the product; a
   redirect from `EdgeEquation.com` would attach the forbidden word to the
   brand in exactly the search results the product is trying to stay out of.

---

## Risk summary

| | Atlas | Lodestar | Brier |
|---|---|---|---|
| Legal risk | **moderate** — unsearched | low | **very low** |
| Search risk | **high** — bare term unwinnable | low | very low |
| Category collision | **Club Atlas** | none | none |
| Domain cost | low (`.football`) | low | low |
| Comprehension | **immediate** | immediate | **requires explanation** |
| Voice fit | **already built** | good | good |

Atlas carries the most risk of the three and is still the recommendation,
because every risk it carries is on an axis the product has already chosen not
to compete on, and the one axis it wins outright — a name that can be the
subject of *"marks its own card down"* — is the axis the whole product is
built on.
