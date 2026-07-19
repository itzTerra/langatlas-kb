# 28 — Locator Normalization & Ingestion QA

> Backlog brainstorm for LangAtlas. Topic: getting source material *into* the system cleanly and
> keeping it trustworthy over time — six bundled sub-problems: (1) confirming/refining the one
> canonical locator grammar shared by chunks, facts, and the verifier; (2) an extraction-quality
> harness for newly ingested sources; (3) a corpus freshness policy (edition pinning +
> re-ingestion cadence) for the topic-34 language-spec list; (4) a scheduled link-checker for
> URL-locator sources; (5) a `pending-source` acquisition queue for claims citing un-ingested or
> inaccessible sources; (6) the corpus/mirror-integrity distinction — a textually clean but
> subtly wrong or persuasively biased copy of a real source, a third problem distinct from both
> extraction QA and prompt injection. Binding context: D15/brainstorm 21 (`source_chunks` —
> structure-aware chunks with breadcrumb prefixes and page/§/anchor locators + `parent_section_id`,
> initial corpus = the developer's collection + topic-34 language specs, extracted text lives
> outside git in the private snapshot store); D23/brainstorm 09 §O5 (the locator grammar this
> brainstorm confirms rather than reinvents — `pp. N–M` \| `§N(.N)*` \| `#<fragment>` /
> `<path>#<fragment>` \| `<commit-sha7>:<path>#LN-LM` \| `t=HH:MM:SS`, CI-regex-validated,
> machine-produced at chunk time and copied verbatim into fact records, joined on
> `(source_id, locator)` by range/section overlap rather than string equality); D24/brainstorm 11
> (index-only verifier evidence — reads exclusively from `source_chunks`, never live-fetches at
> verdict time; the six-verdict vocabulary including `source-unavailable`/`locator-not-found`; the
> `pending-source` state with a 14-day age alarm and a 2-bounce-per-claim budget, both already
> ratified); D25/brainstorm 12 (the `freshness` axis, snapshot-drift as an existing re-verification
> trigger — "a fact whose live source has since changed stays verified against the archived
> snapshot while queued for refresh" — and the 18-month backstop sweep, a *different, slower* axis
> than this topic's link-checking); D28 (topic-34's 15-language curated set, spec edition pinned to
> "the latest available edition... re-pinning as new editions ship" — the trigger mechanism for
> that re-pinning is this topic's job); D31/brainstorm 17 (fetched content is data-not-instructions,
> enforced once in the `RunContext` wrapper — and brainstorm 17 §5 explicitly flagged the
> corpus/mirror-integrity distinction as this topic's follow-up, not its own); D3 (source tiers
> A–D, Wayback archival on mint, dedup on mint); D29 (PLDB/Wikidata/Hyperpolyglot as finding aids
> only, never fact content — relevant background for §2.6, not itself in scope here); D18 (all
> mechanical/LLM work here still logs through the shared wrapper where an LLM call is actually
> made). Flagged as an **R0 prerequisite** by brainstorm 25 alongside topic 09 — this design has
> to land before or alongside the research phase's infrastructure-preflight subphase, not after.
>
> **What 11, 12, 21, and 25 already assumed here, so this brainstorm complements rather than
> re-derives it:** 21 already fixed the ingestion pipeline shape (Docling-class PDF extraction,
> trafilatura for HTML, structure-aware 400–800-token chunks, `qwen3-embedding-4b`) and *named*
> all six of this topic's sub-problems in its own §5 as follow-up work — this brainstorm is where
> those follow-ups actually get designed, not a rehash of 21's ingestion architecture. 09 already
> fixed the locator grammar's *shape* (§O5 above) — this brainstorm's job on that front is edge
> cases and validation tooling, not a new grammar. 11 already fixed the verifier's *behavior* when
> a locator doesn't resolve or a source isn't ingested (the verdict vocabulary, the `pending-source`
> state, its SLA numbers) — this brainstorm designs the *queue mechanics* feeding that state, not
> the verdict semantics themselves. 12 already fixed the *staleness model* in the abstract (three
> orthogonal axes, event-driven re-verification, snapshot-drift as a named trigger) — this
> brainstorm supplies the concrete detector (the link-checker) that fires that trigger for
> URL-locator sources, plus a sibling trigger (edition supersession) for the topic-34 spec corpus.
> All proposals below are *proposed* until the developer ratifies.

## 1. Problem framing

Six sub-problems, all sharing one property: they are the mechanical, unglamorous work of keeping
the boundary between "the outside world" and "the canonical store" honest, over *time* — not at
the moment of first ingestion, which 21 already designed, but across the corpus's whole
subsequent life as specs get new editions, URLs rot, and a rushed ingestion run silently drops a
chapter. A locator that resolves to garbage, an "official spec" that's actually a stale mirror, a
claim parked forever because nobody remembered its source needed acquiring — each of these quietly
reintroduces exactly the citation-laundering risk (K1) that D4/D24's verifier exists to close,
just one layer upstream of where the verifier looks. If the verifier trusts `source_chunks`
completely (D24's index-only design, by deliberate choice — the verifier never live-fetches), then
everything this brainstorm designs is what makes that trust deserved.

Scale check (carried from 21/25): ~30 sources at R1, growing to the topic-34 15-language spec set
plus general PL-design texts over the research phase, tens of thousands of chunks. Every
mechanism below has to be cheap enough to run unattended and often — none of this should need
Claude-grade judgment (D6: Claude never does volume); most of it should not need an LLM call at
all.

## 2. Options with trade-offs

### 2.1 Locator grammar — confirming the shape, closing the edge cases

The grammar itself is not up for redesign — brainstorm 09 §O5 already fixed it, CI-regex-validated
per `custom.locator_kinds` on the source record, joined by range/section overlap rather than
string equality. This brainstorm confirms it verbatim and resolves the three edge cases the task
brief calls out by name, none of which 09 had reason to address at schema-design time.

**Edge case A — sources with no stable pagination (wiki pages, docs sites that reflow).**

- **Option A1 — treat as unlocatable, forbid citing them for anything beyond corroboration.**
  Simple, but throws away real content (many docs sites, e.g. MDN-class references, are
  legitimate tier-B sources) for a formatting inconvenience.
- **Option A2 (recommended) — pin to the archived snapshot, not the live page.** D3 already
  archives web sources via Wayback SavePageNow on mint with a preferred version-pinned permalink.
  The locator (`#<fragment>` or `<path>#<fragment>`, per the existing grammar) resolves against
  *that* archived, content-hashed copy — the one already sitting in `source_chunks` — never
  against whatever the live page currently says. "No stable pagination" stops being a locator
  problem the moment the thing being located is a frozen snapshot instead of a moving target; it
  becomes purely a link-checking problem (§2.4), cleanly separated from grammar validity.
  **Recommendation: A2** — no grammar change needed, just the discipline (already implicit in
  D15/21, made explicit here) that a URL-kind locator always resolves against the ingested
  snapshot, and the live URL is tracked separately purely for the link-checker's own use.

**Edge case B — multi-locator claims (a fact backed by two passages).**

The `sources:` list already supports multiple entries (D23 §O7), each independently carrying its
own `source_id` + `locator` + optional `quote`. Two entries citing the *same* source at two
different locators, or two different sources, are both already representable without a schema
change.

- **Option B1 — keep pure OR semantics** (D24's existing admissibility rule: ≥1 `supported`
  tier-A/B citation is sufficient; extra entries are corroboration, not joint-necessity).
- **Option B2 — add an `all_required: true` flag** for the rare claim that only makes sense as the
  conjunction of two passages (e.g. a `since` claim needing both an intro paragraph and a
  changelog entry to be jointly supportable). Adds a schema field and a verifier-logic branch for
  a case that's genuinely rare.
  **Recommendation: B1 as the default, with B2 held in reserve but not built now.** D24's
  admissibility rule was calibrated (golden-set target FA ≤2%/FR ≤10%) against OR semantics; a
  conjunctive mode is a verifier-behavior change that should wait for a concrete claim that
  actually needs it, rather than being spec'd speculatively here. Multi-entry `sources:` lists
  already do everything this brainstorm needs today.

**Edge case C — locator well-formedness: syntax vs. resolution.**

The CI regex (D23 §O5) only checks that a locator string is *shaped* like `pp. N–M` or `§N.N.N` —
it cannot know whether page 492 of `vanroy-haridi-2003` actually exists, or whether `#match-guards`
is a real anchor on the cited page. That deeper check already exists, but only at verification
time (D24's stage-2 "locator resolution" filter-ladder step, producing `locator-not-found` on
failure) — which means a garbage locator survives all the way to a verifier batch before anyone
notices, wasting a verification cycle on something CI could have caught for free at commit time.

- **Option C1 — leave resolution-checking solely in the D24 verifier.** No new work, but every
  malformed locator costs a full verifier round-trip (and, worse, sits admissible-looking in a
  human-authored file until that batch runs).
- **Option C2 (recommended) — one shared `validate-locator` routine, reused in three places**:
  the agent-runner's pre-commit gate (D27/D13's existing offline-validator pattern), full CI, and
  the D24 verifier's own stage-2 step. It does exactly what stage-2 already does (regex shape →
  lookup against `source_chunks`/the source's manifest → range/section-existence check), just
  invoked earlier and more often. This is not new logic, it is *deduplicating* logic that would
  otherwise be written three times (matching topic 40's already-stated purpose: "the one offline
  tool shared by CI and the agent runner's pre-commit gate"). A malformed or non-existent locator
  is now caught the moment an agent commits, before it ever reaches a verifier batch.
  **Recommendation: C2.** Zero new design, pure implementation consolidation — but worth stating
  explicitly here because otherwise nothing forces the pre-commit/CI/verifier three call sites to
  actually share one implementation instead of drifting into three slightly different regexes.

### 2.2 Extraction-quality harness

The task brief asks for concrete detectors, not just "have some QA." 21 already flagged this as a
follow-up (its ingestion pipeline can silently poison the corpus with a bad extractor run); this
brainstorm supplies the actual check list and, more importantly, decides which checks are a hard
gate versus a soft flag.

**Garbled-text detectors** (run per chunk, at ingestion, before embedding):

- **Encoding/mojibake detection** — round-trip the extracted text through a UTF-8 re-encode and
  flag chunks containing the classic mojibake byte sequences (`Ã©`, `â€™`, replacement-character
  runs) or an anomalously high ratio of non-printable/control characters.
- **OCR-artifact heuristics** (for scanned or poorly-embedded-font PDFs) — flag chunks with a low
  ratio of dictionary-recognizable tokens (a cheap English wordlist membership check, not an LLM
  call), broken ligature splits (`ﬁ`/`ﬂ` mis-decoded as stray glyphs), or hyphenation artifacts
  from line-wrap reflow (`program-\nming` not correctly rejoined).
- **Extraction-collapse heuristics** — chunks with near-zero whitespace (word-boundary loss, a
  classic PDF-to-text failure mode) or repeated garbage-glyph runs (a font-embedding failure
  showing up as the same wrong character hundreds of times).
- **Length-distribution outliers** — chunks far outside the target 400–800-token band (21 §2.4);
  a cluster of near-empty chunks or one absurdly oversized chunk usually means the section-aware
  chunker fell over on that part of the document's structure, not that the content is genuinely
  that short or long.

**Outline coverage** (run once per source, after chunking, before the source is marked citable):

- Extract the document's own structural table of contents — a PDF's embedded bookmarks/outline
  where present, or a spec/docs site's own heading hierarchy (`<h1>`–`<h3>`, or numbered-clause
  headers) where not — and diff it against the *set of `section_path` values the chunker actually
  produced*. A top-level section present in the source outline but absent from any chunk's
  `section_path` is exactly the "silently dropped chapter" failure mode named in the task brief —
  flag it by name (e.g. "outline says Ch. 9 'Concurrency', no chunk carries that breadcrumb").
- This check does **not** need an external ground truth — the document's own outline (when it has
  one) is free, already-machine-readable, and directly comparable to the chunker's output. For
  outline-less sources (a docs page with no heading structure at all), the check degrades to a
  no-op with a logged caveat rather than a false alarm.

**Gate design — which checks block, which flag:**

- **Hard gate (source not promoted to citable in `source_chunks` until it passes):** encoding
  failures and extraction-collapse — these are unambiguous, cheap to detect, and a source that
  fails them is not usably ingested at all, full stop. Re-running with a different extractor
  (Docling vs. marker vs. PyMuPDF4LLM, per 21 §2.3's tool list) or re-scanning is the fix, not a
  judgment call.
- **Soft flag (source is ingested and marked citable, but a QA report is attached for the
  developer's existing per-source skim):** outline-coverage gaps, OCR-heuristic hits below a
  severity threshold, and length-distribution outliers. These need a human glance to distinguish
  "the chunker missed a chapter" from "that chapter genuinely doesn't exist in this edition" or
  "this book has no real chapter structure to diff against" — exactly the kind of judgment call
  D1 already reserves for humans elsewhere, applied here to source fidelity rather than fact
  content. This rides the same "~0.5–2 h QA per book" budget 21 already allocated — the harness's
  job is to make that hour productive (a short, pre-triaged report) rather than an unguided
  re-skim of the whole extracted text.

**Recommendation:** build the harness as a step in the existing ingestion CLI (21 §2.3), hard-gate
on encoding/extraction-collapse failures, soft-flag everything else into a per-source QA report
consumed during the developer's existing manual skim step — no new infrastructure, no new human
workflow, just a structured checklist replacing an unguided read-through.

### 2.3 Corpus freshness policy — edition pinning & re-ingestion cadence (topic-34 spec list)

D28 already ratified *what* to pin ("pick the latest available edition... re-pinning as new
editions ship") without designing *how re-pinning gets triggered*. That's this sub-problem.

**Recording the pin.** Each spec source's registry record (D3 CSL-YAML, `custom` key) carries
`custom.edition` (the pinned edition/version string, e.g. `"SE 25"`, `"N3220"`, `"2010 + GHC
2026.1 user guide"` per D28's own examples) and a new `custom.edition_check_url` — a canonical
page the publishing body itself maintains that states the current edition (a TC39 finished-
proposals page, an ISO/IEC catalog entry, the JLS index page, a language's own releases page).
Not every source will have one (an out-of-print book has no "check for a new edition" page) —
the field is optional, and its absence just means this source never triggers automatically.

**Detecting a new edition — three options:**

- **Option A — recurring full re-extraction of every spec source**, diffed wholesale against the
  previous ingest. Simple, but expensive (a full Docling/trafilatura pass per source, every
  cycle) for a signal that's usually "nothing changed."
- **Option B (recommended) — a lightweight, separate "edition check" job**, distinct from full
  re-ingestion: for every source with `custom.edition_check_url`, fetch just that page (a plain
  HTTP GET, no LLM call, no chunking) and compare the edition string it reports against the
  recorded `custom.edition`. A mismatch opens a queue entry ("possible new edition available for
  `ecma-262-2025`: check page now says 2027 edition") — it does **not** auto-trigger re-ingestion.
  Cadence: **quarterly**, cheap enough to run far more often than the 18-month D25 backstop sweep
  (which is a different, slower, LLM-driven axis re-verifying facts against their *existing*
  snapshot — this check is about whether a *new* snapshot should exist at all) and frequent enough
  that a new spec edition doesn't sit undetected for a year.
- **Option C — no automated check; developer manually revisits the topic-34 list periodically.**
  Zero engineering cost, but "periodically" reliably means "whenever the developer happens to
  think of it" — a silent staleness risk for exactly the corpus D28 spent real effort curating.
  **Rejected** as the sole mechanism, though it remains the actual triage step once Option B's
  job opens a queue entry.

**When a new edition IS adopted (this is a migration, not an edit):** existing locators (page/
section numbers) may no longer mean the same thing in the new edition, so this cannot be an
in-place overwrite of the old source record.

1. Ingest the new edition as a **new, separately versioned `source_id`** (e.g. `ecma-262-2025` →
   `ecma-262-2027`), never overwriting the old one — the old record stays in the registry
   (never deleted) because facts already verified against it remain historically accurate
   citations of *that* edition.
2. Tag the superseded source `custom.superseded_by: ecma-262-2027` — a source-registry-level
   tombstone, one layer above D16/D23's existing fact-level `tombstones.yaml`, following the same
   append-only pattern rather than inventing a new one.
3. Facts citing the superseded source get flagged via D25's existing `freshness: stale` machinery,
   with a new named trigger reason — **`edition-superseded`**, a sibling of the already-designed
   `snapshot-drift` trigger (§2.4 below) — feeding the same event-driven re-verification queue
   (D25 O4c) rather than a bespoke mechanism.
4. Re-verification against the new edition is **not automatic** — D16's migration-manifest
   machinery already owns "how a fact's evidence gets remapped after a structural change," and a
   spec edition bump is exactly the kind of blast-radius event that machinery exists for. This
   brainstorm's job stops at correctly triggering that pipeline, not re-designing it.

**Recommendation:** quarterly lightweight edition-check job (Option B) opening a triage queue
entry, never auto-reingesting; a new edition adoption ingests as a new versioned source_id with
the old one tombstoned via `superseded_by`, driving a new `edition-superseded` freshness-staleness
trigger that rides D25's existing re-verification queue.

### 2.4 Scheduled link-checker

Scoped explicitly to **URL-locator sources only** — book/paper `pp.`/`§` locators are pinned to
the private snapshot store and immune to link rot by construction (D15); repo `commit+lines`
locators are git-content-addressed and immune by construction (a commit sha either exists or
doesn't, and if it exists its content never changes). Only the `#<fragment>` / `<path>#<fragment>`
kinds — web pages, docs sites — are exposed to the outside world changing out from under a
citation.

**Design:** a monthly cron-style job (cheap: plain HTTP, no LLM cost, fits alongside D25's other
scheduled housekeeping) walking every source with a live `url` field, checking three independent
things per source, because "the link still works" and "the link still says what we cited" are
different failure modes:

1. **Resolution** — does the URL still return 2xx (or 3xx to a working final target) on a HEAD/GET
   with retry? Failure → `link_status: dead`.
2. **Anchor presence** — for sources cited at a `#fragment`, does a fresh (cheap, non-chunking)
   fetch-and-parse still contain that anchor? Failure with the URL itself alive → `link_status:
   anchor-drift` (the page moved/reorganized, the URL still resolves but the cited spot doesn't).
3. **Content drift** — does the freshly fetched page's content hash still match the hash recorded
   at ingestion (the same hash D3 already computes for dedup/archival)? A mismatch with the URL
   and anchor both still resolving is exactly D25's already-designed **`snapshot-drift`** trigger
   ("the topic-28 link-checker/freshness pass detects that a source's live content no longer
   matches its snapshot hash" — D25 §O4c already names this brainstorm as the source of that
   signal) — this brainstorm's job is simply to be the concrete thing that fires it.

**On failure — what happens to facts, concretely:**

- **Dead link:** flag the source `link_status: dead` in the private build-side ledger (never
  written back into authored YAML, mirroring D23's "verifier verdict lives in a build-side ledger"
  precedent for the same reason — this is pipeline state, not authored content); facts citing it
  get `freshness: stale` with reason `source-link-dead`. Per D25's already-ratified
  snapshot-drift policy, **the fact stays verified against the archived Wayback/local snapshot**
  — a dead live link never retroactively unverifies anything, it only queues the citation for a
  possible future replacement (e.g. the developer re-locating the same content at a new URL).
- **Anchor drift:** same staleness flagging, reason `anchor-drift`, plus a queue entry suggesting
  the locator itself needs manual repair (find where the cited content moved to on the still-live
  page) — a locator-repair job, not a content-verification one.
- **Content drift:** feeds directly into D25's existing snapshot-drift re-verification trigger —
  the fact gets queued for re-verification against the *new* content; if the new content still
  supports the claim, nothing visibly changes; if not, the verdict flips through the normal D24
  gate. No new mechanism needed here beyond correctly detecting the drift and enqueuing it.

**Recommendation:** monthly job, three independent checks (resolution / anchor / content-hash) per
URL-locator source, writing to the same private ledger pattern as the verifier's own build-side
state, feeding two of D25's existing triggers (`snapshot-drift` for content changes) plus one new
sibling reason code each for dead links and anchor drift — no new re-verification *machinery*,
just the concrete detector D25 was already designed to be fed by.

### 2.5 Source-acquisition queue (`pending-source`)

D24 already ratified the *existence* and SLA of `pending-source` (14-day age alarm, 2-bounce
budget per claim) as a verifier verdict-adjacent state. What's missing is the queue's own
mechanics: how a claim gets there, how it's triaged, and how it un-parks — the actual thing the
task brief is asking this brainstorm to design.

**Entry conditions** — a claim parks in `pending-source` when an agent drafts it citing:

- a `source_id` not yet present in `source_chunks` at all (source registered but never ingested),
  or
- a locator on a source that's only *partially* ingested (rare, but possible if ingestion was
  interrupted or scoped to a subset of a large reference), or
- a genuinely new bibliographic reference the agent proposes minting but that isn't accessible yet
  (paywalled paper, out-of-print book) — the source *record* can still be minted per D3/D4's
  "registry changes are logged, not human-gated" rule (a stub entry, tier assigned provisionally),
  even though the *content* behind it isn't ingested yet.

**Queue entry shape** (private, build-side — not authored YAML, same reasoning as verifier
verdicts): `claim` (the record#field-path anchor + draft content), `source_id` (or a bibliographic
stub if not yet minted), `reason` (`not-ingested | partially-ingested | paywalled |
access-pending | acquisition-failed`), `opened_at`, `bounce_count` (against D24's 2-bounce budget),
derived `age_days` (against the 14-day alarm).

**Acquisition paths** (mirroring D15's own acquisition posture, applied at the level of "what does
the developer actually do when this queue has an entry"):

1. **Already-owned corpus gap** — the source is something the developer has or can freely obtain;
   route straight into the next R1-style ingestion batch. Cheapest, most common path for the
   topic-34 spec set specifically (D28's phase-gated onboarding means most gaps here are "haven't
   gotten to it yet," not "can't get it").
2. **Paywalled academic paper** — per D14/D15's already-ratified stance, the agent requests it, the
   developer fetches via university access, the PDF lands in the private snapshot store and
   ingestion proceeds normally. No new policy needed — this brainstorm just wires the *queue* that
   makes such requests visible and trackable rather than ad hoc.
3. **Genuinely inaccessible** (out of print with no digital copy, developer declines to acquire
   for cost/relevance reasons) — the claim stays parked **indefinitely, visibly**, in the queue.
   Per K1's framing, it is never silently dropped and never quietly promoted around the gate —
   an unresolved `pending-source` entry is the honest state, not a failure to be hidden.

**Resolution mechanic:** once a cited source becomes ingested (or the specific missing locator
resolves), the parked claim automatically re-enters the verifier's stage-1 filter ladder on the
next scheduled batch — no manual re-trigger required beyond the acquisition itself. This is
already implied by D24/21's design ("parked claims auto-resume on the next batch"); this
brainstorm's contribution is making that resumption a mechanical scan of the queue (`source_id`
now present in `source_chunks`? → re-file for verification) rather than something depending on
anyone remembering which claims were waiting on which source.

**Recommendation:** a single private `sourcing_queue` log recording all of the above, typed by
`reason`, checked automatically each verifier batch for now-resolvable entries, surfaced to the
developer sorted by `age_days` (the 14-day alarm) — see §5 for why this queue's *reporting surface*
belongs with topic 32 rather than being designed as a standalone dashboard here.

### 2.6 The corpus/mirror-integrity distinction

Brainstorm 17 §5 named this explicitly as unfinished business belonging here: three genuinely
different problems that superficially look similar (all involve "a source that's wrong somehow")
but require entirely different mitigations, and conflating them wastes effort building the wrong
defense against each.

1. **Extraction QA (§2.2, this brainstorm)** — the source is legitimate and factually correct, but
   the *pipeline's own extraction step* corrupted it (OCR noise, dropped sections, encoding
   mangling). Detectable purely from the extracted text's own internal properties — no need to
   compare against anything external. Already designed above.
2. **Prompt injection (D31/brainstorm 17)** — a fetched page (legitimate or attacker-controlled)
   contains adversarial instruction-like text aimed at manipulating the *agent reading it* into
   doing something other than faithfully reporting content. Mitigated structurally (data-not-
   instructions delimiting, D31) — not a content-correctness question at all.
3. **Mirror/copy integrity (new here)** — the text is clean, well-formatted, passes every check in
   (1) and every scan in (2), and *is still wrong*: an unofficial mirror with a stealth edit, a
   translated/annotated copy that silently misrepresents a passage, a superseded draft
   masquerading as the final spec. Both other detectors assume the text is faithfully what it
   claims to be; this is exactly the case where that assumption fails, at the *acquisition* step
   rather than the extraction or reading step — a different point in the pipeline than either (1)
   or (2) touches.

**Design for (3), scoped to what a solo project can actually sustain:**

- **Prefer canonical/official sources at acquisition time, tracked as a field.** A new
  `custom.canonical_source: true | false` on every source record — deliberately *not* folded into
  D3's existing `tier` field, because tier measures evidentiary strength (peer-review/spec status)
  while this measures copy-fidelity risk; a tier-A spec fetched from a sketchy third-party mirror
  is still tier-A-*worthy content* but should carry `canonical_source: false` until re-acquired
  from the real thing. Sources fetched directly from the publishing body's own domain (ecma-
  international.org, iso.org, an official language `github.com/<org>` releases page, a DOI
  resolver) get `true` by construction; anything else defaults `false`. For the bulk of the
  topic-34 spec corpus this is nearly free — official specs are, almost without exception,
  directly fetchable from their own publishing body, so the ingestion CLI simply preferring the
  canonical URL when one exists engineers most of this risk away at the source rather than
  detecting it after the fact.
- **Checksum/diff against a known-good copy, where one independently exists.** Only applicable
  when a canonical copy *is* obtainable — in which case the ingestion CLI should simply fetch from
  it directly rather than accepting a mirror at all, making this bullet mostly redundant with the
  one above for the common case. It has no purchase on the genuinely hard case (an out-of-print
  book scan, a translated copy) — there is no independent known-good copy to diff against by
  definition, so this mitigation cannot close that gap and shouldn't be oversold as if it could.
- **A mandatory, human-authored `custom.acquisition_note` for every non-canonical source.** Short
  free text stating where the copy came from and why it's believed faithful (e.g. "purchased
  directly from Cambridge University Press" / "PDF via the university library's own subscription
  portal, not a public mirror"). CI enforces the field's *presence* whenever
  `canonical_source: false` — it cannot mechanically verify the note is *true*, only that a human
  made and recorded the judgment call. That is the honest ceiling here, not a gap to be
  apologized for: D1/D14 already reserve exactly this kind of judgment call for humans elsewhere
  (source-tier assignment, quote-cap enforcement), and copy-provenance trust is the same shape of
  problem — mechanically checkable *that* a judgment was made, not mechanically checkable that the
  judgment was *correct*.
- **Explicitly not building a dedicated detector for this risk.** No stylometric/bias classifier,
  no automated cross-source contradiction-mining pass built specifically for mirror integrity —
  that capability already exists, structurally, one layer downstream: D24's entailment verifier
  plus D25's multi-source corroboration requirement (confidence rises with count of independent
  corroborating sources) already catch a subtly-wrong copy the instant a second, independently-
  acquired source disagrees with it on a claim, and D25's controversy scoring is exactly the
  signal that surfaces persistent disagreement once it does. Building a parallel detector here
  would duplicate machinery the verification pipeline already provides for free once ≥2 sources
  exist on a topic. **The genuine residual risk is the single-sourced claim** — early in the
  corpus, or for a niche language/feature with only one available reference, there is no second
  source to catch a stealth error against. That residual is real and not solved by anything in
  this brainstorm; it's named as an open question (§4) rather than papered over.

**Recommendation:** `canonical_source` flag + preference for official URLs at ingestion (engineers
away most of the risk for the topic-34 spec corpus specifically) + mandatory `acquisition_note` for
the non-canonical remainder (documents the human judgment call, the honest ceiling for a solo
project) + explicit reliance on the existing multi-source verification/corroboration machinery as
the structural backstop, rather than building a redundant bespoke detector.

## 3. Recommendation (*proposed*)

1. **Locator grammar (§2.1):** confirm brainstorm 09 §O5's grammar verbatim, no changes. Pin
   URL-kind locators to the archived snapshot, never the live page (live-page freshness is the
   link-checker's job, §2.4, kept cleanly separate from locator validity). Keep OR-semantics as
   the default for multi-entry `sources:` lists; hold a conjunctive `all_required` mode in
   reserve, unbuilt until a concrete claim needs it. Build one shared `validate-locator` routine
   (regex shape + `source_chunks` resolution check) reused by the pre-commit gate, CI, and the
   D24 verifier's own stage-2 step — one implementation, not three independently drifting ones.
2. **Extraction-quality harness (§2.2):** garbled-text detectors (encoding/mojibake, OCR
   heuristics, extraction-collapse, length-distribution outliers) plus an outline-coverage diff
   (chunker's `section_path` set vs. the source's own table of contents/heading structure) run in
   the ingestion CLI. Encoding/extraction-collapse failures **hard-gate** a source from
   `source_chunks` promotion; outline-coverage gaps and softer heuristic hits produce a structured
   per-source QA report consumed during the existing developer skim step (21's ~0.5–2 h/book
   budget) — no new human workflow, a pre-triaged one.
3. **Corpus freshness / edition pinning (§2.3):** `custom.edition` + optional
   `custom.edition_check_url` on spec source records; a quarterly lightweight edition-check job
   (plain page fetch, no re-ingestion) opens a triage queue entry on mismatch, never
   auto-reingests. Adopting a new edition ingests it as a new versioned `source_id`, tombstones the
   old one via `custom.superseded_by` (a source-registry-level sibling of D16/D23's fact-level
   tombstones), and fires a new `edition-superseded` freshness-staleness trigger riding D25's
   existing event-driven re-verification queue.
4. **Scheduled link-checker (§2.4):** monthly job over URL-locator sources only (book/repo locators
   are immune by construction), checking resolution, anchor presence, and content-hash drift as
   three independent signals. Content drift feeds D25's already-designed `snapshot-drift` trigger
   directly; dead links and anchor drift get their own sibling reason codes. Per D25's ratified
   policy, a dead live link never retroactively unverifies a fact already verified against its
   archived snapshot — it only queues the citation for possible future repair.
5. **Source-acquisition queue (§2.5):** a single private `sourcing_queue` log, entries typed by
   `reason` (`not-ingested | partially-ingested | paywalled | access-pending |
   acquisition-failed`), tracking `bounce_count` against D24's existing 2-bounce budget and
   `age_days` against its existing 14-day alarm. Automatic re-filing into the verifier's stage-1
   queue the moment a cited source becomes ingested — no manual re-trigger. Genuinely inaccessible
   sources stay visibly parked indefinitely, never silently dropped.
6. **Corpus/mirror-integrity distinction (§2.6):** a new `custom.canonical_source` flag (orthogonal
   to D3's evidentiary `tier`), preference for official publishing-body URLs at ingestion time
   (closes most of the risk for the topic-34 spec corpus specifically, nearly for free), a
   mandatory `custom.acquisition_note` for every non-canonical source (CI-enforced presence, not
   truth — the honest ceiling for a solo project), and explicit reliance on the existing D24/D25
   multi-source verification and corroboration machinery as the structural backstop rather than a
   bespoke detector. The genuine residual risk (a single-sourced claim with no second source to
   catch a stealth error) is named, not solved, here.
7. **Shared infrastructure note:** the `sourcing_queue` (item 5), the link-checker's private ledger
   (item 4), and the edition-check triage queue (item 3) should all be one combined "sourcing work
   queue" the developer looks at in one place, typed by reason code, rather than three
   independently half-built systems that each need their own dashboard — see §5 for where its
   reporting surface belongs.

## 4. Open questions for the developer

1. **Edition-check cadence** — is quarterly the right frequency for the lightweight edition-check
   job (§2.3), or should it track something else (e.g. tied to each language's own typical release
   cadence, which varies wildly — C moves on a ~5-year ISO cycle, JavaScript/TC39 stages proposals
   continuously)?
2. **`canonical_source: false` retroactive audit** — should the R1 initial-corpus ingestion
   (developer's existing `~/Downloads/hermes-research/` collection plus early topic-34 specs)
   get a one-time retroactive pass to backfill `canonical_source`/`acquisition_note` before the
   flag becomes load-bearing for later sources, or is it acceptable for the flag to only bind
   going forward from whenever this design ships?
3. **Single-sourced-claim residual risk (§2.6)** — is a lower confidence ceiling on single-sourced
   claims (distinct from D25's existing tier×corroboration-count confidence model, which already
   penalizes lack of corroboration generally) worth adding specifically for the mirror-integrity
   case, or does D25's existing mechanism already cover it adequately without a special case?
4. **Link-checker false-positive tolerance** — sites that intermittently 5xx or rate-limit
   scrapers could flag a perfectly healthy source as `link_status: dead` on a bad day; is a single
   retry (per §2.4's design) sufficient, or does the developer want a "confirm dead across N
   consecutive monthly runs before flagging" dampener, given that a wrongly-flagged dead link
   costs only a staleness badge (not a content change) per D25's non-retroactive-unverify policy?
5. **Outline-coverage check scope** — for sources with genuinely no machine-readable outline (a
   docs page with flat, unheaded prose), the check silently no-ops (§2.2). Is that acceptable, or
   does the developer want such sources flagged as "outline-coverage: not applicable" explicitly
   in the QA report, so a source that *should* have structure (a mis-extracted spec that lost its
   headings entirely) isn't indistinguishable from one that genuinely never had any?

## 5. New brainstorm topics surfaced

- **Unified sourcing work queue / reporting surface** — the combined view (§3 item 7) spanning
  `pending-source`, link-checker findings, and edition-check triage entries. This is a reporting/
  observability surface compiled from logs the pipeline already produces, matching topic 32's
  existing scope exactly ("cost-per-accepted-fact / verifier-failure / debate-outcome reporting
  compiled from transcripts + cost logs... whether `provenance.candidate_source` belongs in a
  broader 'why did the pipeline look here' telemetry model") — **fold into topic 32**, not a new
  number.
- **Edition-supersession as a migration trigger type** — wiring the new `edition-superseded`
  freshness-staleness reason (§2.3) into D16's migration-manifest disposition machinery is exactly
  topic 29's stated scope ("migration-manifest disposition DSL... tombstone/supersession rendering
  on site + MCP") one level up (source-registry tombstones rather than fact/ontology-node
  tombstones, but the same disposition-DSL shape) — **fold into topic 29**, not a new number.
- **`validate-locator` as a shared CLI routine** — the single implementation reused by pre-commit,
  CI, and the verifier's stage-2 step (§2.1) is squarely topic 40's stated purpose ("the one
  offline tool shared by CI and the agent runner's pre-commit gate") — **fold into topic 40**, not
  a new number.
- **Link-checker job scheduling** — the monthly cron-style job itself (§2.4) is one more scheduled
  background job alongside D25's 18-month backstop sweep and the edition-check job; its actual
  scheduling/checkpointing mechanics belong with topic 35 ("run orchestrator & checkpointing...
  halt/resume signaling for unattended overnight runs") rather than being designed as a standalone
  cron here — **fold into topic 35**, not a new number.
- No genuinely new, undesigned topic emerged that isn't better placed inside an existing backlog
  number — this brainstorm's six sub-problems were already fully enumerated by the checklist entry
  itself, and the four items above are refinements that belong inside topics already on the
  backlog rather than net-new ones.
