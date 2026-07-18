# 23 — Product naming & domain

> Round-2 brainstorm. "Hermes" is a working title only: it collides with the luxury brand
> (aggressive trademark enforcement), a famous messaging library (Facebook's Hermes JS engine!),
> and dozens of dev tools. The JS-engine collision alone makes it unusable for a programming
> product — SEO for "hermes programming" is permanently owned by Meta.

## Problem framing

What the name must carry:

- **Product**: a sourced, citation-backed knowledge base of programming-language
  features/concepts as a typed graph; later a PC-part-picker-style language builder.
- **Audience**: programmers + PL enthusiasts/academics. The name can afford to be a
  linguistics/PL-theory in-joke — that audience *rewards* it — but must not be unpronounceable
  or unspellable.
- **SEO reality (D10, P2)**: traffic will come from long-tail pages (`/features/pattern-matching/`,
  `/features/gc-vs-ownership/`), not from people searching the brand. So the brand name does
  **not** need to be descriptive; it needs to be *unclaimed* so that once someone hears it,
  searching it finds us. A generic descriptive name ("Language Feature Database") can never be
  owned in search. **Brandable name + descriptive tagline** is the right split.
- **Tests applied to every candidate**: (a) spelling-over-the-phone, (b) obvious existing
  product/repo/major-site collision in the programming space, (c) does it survive the later
  builder module, (d) does it read well in a URL (`<name>.dev/features/pattern-matching/`).

**Honesty note on availability**: everything below is a *search-based sanity check* (does a
significant product/repo/site already occupy the name). Definitive domain availability needs a
registrar lookup (e.g. porkbun/namecheap search) by the owner — several ".dev/.io" domains may
be parked even where no product exists.

## Candidates

### Full brainstorm list (15)

| # | Name | Strategy | One-line rationale |
|---|------|----------|--------------------|
| 1 | **Isogloss** | evocative (linguistics/cartography) | the exact linguistics term for a boundary line of a language feature on a map — the product literally draws feature boundaries across languages |
| 2 | **LangAtlas** | evocative + descriptive | "WALS for programming languages" — WALS (World Atlas of Language Structures) is the revered natural-language precedent for exactly this product |
| 3 | **Morpheme** | evocative (linguistics) | smallest unit of meaning; features are the morphemes languages are built from |
| 4 | **Panini** | classical (Pāṇini, first formal grammarian) | the person who invented formal grammar description; deep PL-theory credibility |
| 5 | **Glossa** | classical Greek "tongue/language" | clean, pronounceable, language-flavored |
| 6 | **Clade** | evocative (biology/taxonomy) | languages as clades sharing derived features |
| 7 | **Featura** | coined | feature + Latin ending; says "features" instantly |
| 8 | **Ontolang** | coined/portmanteau | ontology + language; describes the typed graph precisely but sounds like infrastructure |
| 9 | **Codon** | evocative (genome/DNA) | genetic unit of code — perfect metaphor, but **hard collision**: Codon is a well-known Python compiler (exaloop/codon) |
| 10 | **Linnaea** | classical (Linnaeus, taxonomy) | the taxonomist's flower; "Linnaean taxonomy of languages" |
| 11 | **Glossopoeia** | classical (Tolkien's term for language-construction) | uncannily perfect for the builder module; fails the phone-spelling test badly |
| 12 | **Periodic** / "The Periodic Table of Programming Languages" | evocative | strong mental model, but "periodic table of X" is a meme format, and single word "Periodic" is unownable |
| 13 | **Quipu** | classical (Inca knotted-cord knowledge records) | knowledge encoded in a typed structure of threads and knots ≈ typed graph |
| 14 | **Strata** | evocative | the three feature layers (syntax/semantic/design) as strata; too generic, many collisions |
| 15 | **Rosetta / Babel / Lingua / Polyglot** | classical | listed only to reject: all four are hard-taken in the programming space (Rosetta Code, Babel compiler, many Linguas, glot.io/polyglot everything) |

### Shortlist (6) — with availability sanity checks

#### 1. Isogloss — the favorite

- **Rationale**: an isogloss is the geographic boundary of a linguistic feature — dialectology's
  core mapping tool. This product is exactly that for programming languages: which languages
  fall inside the "pattern matching" line, which outside. The metaphor covers the knowledge
  base (feature maps), the graph (boundaries and overlaps), and even comparisons
  (`/features/gc-vs-ownership/` is two isoglosses crossing). PL academics and linguistics-adjacent
  programmers will get it immediately; everyone else gets a distinctive, real-word brand.
- **Phone test**: good-with-one-beat — "isogloss, I-S-O-G-L-O-S-S, like 'iso' + 'gloss'". Two
  familiar morphemes, no ambiguous letters. Pronounceable on first sight.
- **Availability sanity check (search-based)**: near-clean in the dev space. Only collisions
  found: a small ISO-639 lookup CLI ([thunderpoot/isogloss](https://github.com/thunderpoot/isogloss)),
  a tiny localization npm bundle ([chrisnewtn/isogloss](https://github.com/chrisnewtn/isogloss)),
  a small consultancy at [isogloss.com](https://www.isogloss.com/), and a linguistics journal
  named *Isogloss*. No product of significance in programming. `isogloss.dev` returned no
  product in search — plausibly free, **registrar check required**. SEO: the generic-term
  search results (Wikipedia dialectology) are low-competition and thematically *helpful*.
- **URL IA**: `isogloss.dev/features/pattern-matching/` reads beautifully — the brand is the map,
  the paths are the territory.

#### 2. LangAtlas (or "Language Atlas")

- **Rationale**: the strongest *precedent* play. WALS — the World Atlas of Language Structures
  ([wals.info](https://wals.info/)) — is the canonical academic database of natural-language
  features, and this product is its programming-language sibling. "Atlas" says curated,
  map-like, browsable reference; "Lang" scopes it. Semi-descriptive, so it needs less tagline
  support than a pure brandable.
- **Phone test**: excellent — two dictionary words, zero spelling risk.
- **Availability sanity check**: no product named "LangAtlas" found; "Atlas" alone is hopeless
  (MongoDB Atlas, dozens more) but the compound looks open. `langatlas.dev` unverified —
  registrar check required. Risk: compound "Lang*" names read slightly generic/startup-y, and
  LangChain's "Lang*" family (LangGraph, LangSmith) has polluted the prefix — some people will
  guess it's an LLM tool.
- **URL IA**: `langatlas.dev/languages/rust/` is self-explanatory; `/features/` works fine.

#### 3. Panini

- **Rationale**: Pāṇini wrote the Aṣṭādhyāyī (~4th c. BCE), the first generative grammar —
  Backus–Naur form is routinely called "Panini–Backus form". No name carries more
  formal-language-theory credibility. Honors the descriptive, rule-based nature of the KB.
- **Phone test**: trivially spellable — but that's the problem: everyone hears the sandwich
  first. Charming or embarrassing depending on taste.
- **Availability sanity check**: crowded at the repo level but no major product: a Rust parser
  framework ([pczarn/panini](https://github.com/pczarn/panini)), Foundation's static-site
  flat-file generator ([foundation/panini](https://github.com/foundation/panini)), a Ruby CFG
  toy, a Sanskrit-NLP project. Plus the Panini sticker-album company (real trademark) and
  infinite sandwich SEO. You would never own the SERP for "panini". Domains: `panini.dev`
  almost certainly unavailable/premium; would need `paninilang.dev` or similar — which weakens it.
- **URL IA**: fine, but the sandwich noise leaks into every share ("check out panini.dev" — "the
  recipe site?").

#### 4. Morpheme

- **Rationale**: the smallest meaning-carrying unit — features are the morphemes of programming
  languages, and the builder composes morphemes into a language. Great two-way fit (KB +
  builder). Real linguistics word, distinctive in dev conversation.
- **Phone test**: good — "morpheme, M-O-R-P-H-E-M-E"; slight risk of "morphine" mishearing.
- **Availability sanity check**: moderately crowded: a Flutter CLI on
  [pub.dev](https://pub.dev/packages/morpheme) with the `morpheme.dev` docs domain likely
  attached, NaturalMotion's Morpheme game-animation engine (legacy but famous),
  [morpheme.design](https://www.morpheme.design/), an INRIA research team. No giant, but the
  Flutter CLI probably holds `morpheme.dev`. Would need `.io`/`.app` or a modifier.
- **URL IA**: fine; `/features/` under "morpheme" is conceptually neat (features *are* the
  morphemes).

#### 5. Glossa

- **Rationale**: Greek for "tongue/language"; short, warm, classical, easy.
- **Phone test**: excellent — G-L-O-S-S-A.
- **Availability sanity check**: worse than it looks. Γλώσσα is the pseudo-language taught in
  Greek high schools, with many interpreters/editors on GitHub
  ([example](https://github.com/markoutso/glo)) and a VS Code extension — a genuine
  *programming-language* namespace collision. *Glossa* is also a major open-access linguistics
  journal. In exactly our audience (PL + linguistics), the name is spoken for. Drop.

#### 6. Featura (representative coined/descriptive option)

- **Rationale**: if the owner wants the name itself to say "features", a coined
  feature-derivative is the honest option; instantly communicates the domain, zero metaphor
  required.
- **Phone test**: okay but not great — people will type "featura/feature-a/featura?"; the
  -a ending gets mangled.
- **Availability sanity check**: not searched exhaustively; short "feat*" names are a minefield
  of parked domains and small SaaS (feature-flag products own this semantic space: Featurevisor,
  FeatureHub, Flagsmith...). The feature-flag association is actively misleading for us. Keep
  only as a fallback pattern, not a recommendation.

### SEO: brandable vs descriptive

Brandable wins here, decisively: (1) the site's organic entry points are the long-tail feature
pages, which carry their own descriptive keywords in the URL and title regardless of brand;
(2) a descriptive name ("language feature database") competes with PLDB's whole category and
can never be exclusively owned; (3) a distinctive brand makes citations, HN posts, and academic
mentions unambiguous ("as catalogued on Isogloss"). The cost is that every page `<title>` and
the homepage H1 must carry the descriptive tagline until the brand is known.

**Tagline pattern**: `<Name> — <what> of <scope>, <trust-differentiator>`. Concretely:

- "Isogloss — a sourced map of programming-language features."
- "Isogloss — where programming-language features begin and end. Every fact cited."
- Page-title template: `Pattern matching — <Name>` (feature pages) /
  `<Name>: the cited atlas of programming-language features` (home).

The trust-differentiator ("every fact cited", "sourced") is the actual positioning vs
PLDB/hyperpolyglot (open question A2) and belongs in the tagline, whatever the name.

## Recommendation

**Top 3:**

1. **Isogloss** — *the favorite.* Precise metaphor that deepens the more you know PL/linguistics,
   near-empty competitive namespace in dev, passes the phone test, ages perfectly into the
   builder ("draw your own isogloss"). Register `isogloss.dev` (+ `.io` defensively) if the
   registrar check confirms.
2. **LangAtlas** — the safe, semi-descriptive runner-up with the WALS pedigree; choose it if
   Isogloss feels too erudite or its domains turn out taken. Slight LangChain-prefix taint.
3. **Morpheme** — best pure metaphor for the *builder* future; ranked third only because the
   Flutter CLI likely holds `morpheme.dev` and the namespace is moderately occupied.

Rejected with reasons on record: Panini (sandwich SERP + trademarked sticker company + crowded
repos), Glossa (Greek school language + linguistics journal), Codon (existing compiler), Clade
(heavily claimed across industries), Rosetta/Babel/Lingua/Polyglot (hard-taken), Glossopoeia
(unspellable), Periodic (unownable meme format).

## Open questions for the owner

1. Run registrar lookups: `isogloss.dev`, `isogloss.io`, `isogloss.org`, `langatlas.dev`,
   `morpheme.io`. Search can only prove occupancy, never availability.
2. Comfort check: is "Isogloss" too academic for the mainstream-programmer half of the audience?
   (Mitigation: the tagline does the explaining; the word is self-teaching after one glance at
   the homepage.)
3. GitHub org name should match the chosen name (D1: public split repos) — check org
   availability at the same time as domains (`github.com/isogloss` etc.).
4. Trademark sanity: the *Isogloss* linguistics journal is non-commercial and non-software; a
   cheap TM screening search is still prudent before printing the name everywhere.
5. Does the owner want the repo/product rename now, or keep "hermes" as internal codename until
   the site ships? (Recommendation: rename repos before they go public — public history under a
   dead name is churn.)

## New brainstorm topics surfaced

- **26 Brand identity & typography**: logo/wordmark (an isogloss line motif is an obvious,
  ownable visual), accent color (D10 allows exactly one), OG-image template for feature pages.
- **27 Launch positioning & announcement**: HN/lobste.rs post framing, the A2 positioning
  statement vs PLDB/hyperpolyglot, and how the name + tagline carry it.
- Minor: naming conventions *inside* the product (do we call nodes "features" publicly or adopt
  the isogloss/map vocabulary in UI copy? Recommendation: plain "features" in IA, map metaphor
  only in brand copy — URLs stay boring and searchable).
