# 36 — Golden-Set Authoring Methodology

> Backlog brainstorm for LangAtlas. Scope (checklist item 36): perturbation taxonomy including
> an overstated-claim stratum, contamination hygiene, hand-labeled controversy cases, retrieval
> golden queries, joining the topic-16 eval harness, and whether a public benchmark is worth
> committing to. Derives from brainstorms 11, 12, 25. Binding context: D6 (Claude never does
> volume, university API never has the last word), D24 (verifier golden set, ~200–300
> stratified items, FA ≤2%/FR ≤10%), D25 (controversy assessor golden set, ~50 hand-labeled
> cases, four controversy levels after the level-4→3 fold), D27 (embedding-benchmark golden
> queries, 40–60 items in three difficulty bands, developer co-authors during R1 QA skims), D30
> (topic-16 regression harness: record/replay fixtures under `tests/fixtures/providers/`,
> human-diff review, explicit deferral of any scored golden set to this topic), D41 (shared
> `replay_verdict` library function). All proposals below are *proposed* until the developer
> ratifies.

## Problem framing

Four separate documents have already promised a "golden set" without anyone designing them as
one coherent authoring practice:

1. **The D24 verifier calibration set** (~200–300 items) — exists to measure the claim↔source
   entailment gate's false-accept/false-reject rates, the load-bearing K1 defense (brainstorm
   11 §2.8) since there is no human merge gate (D1).
2. **The D25 controversy-assessor golden set** (~50 items) — regression-tests the ordinal
   controversy rubric (brainstorm 12 §5.2), and is also the calibration instrument for Claude's
   escalation role on level-3 assignments.
3. **The D27 embedding-benchmark golden queries** (40–60 items, three difficulty bands) —
   measures retrieval quality (Recall@5, nDCG@10, Recall@50, MRR) for the `source_chunks` index
   that both the research phase and the D24 verifier depend on.
4. **A possible scored debate-outcome golden set** (brainstorm 16 §2.3 Option B, ~30–50 items)
   — explicitly deferred by D30 to *this* topic ("Option B, if ever built, is topic 36's job")
   once phase-1 sweep-debate volume exists.

Each was designed in isolation with its own item count, its own authoring cadence, and its own
implicit assumption about who writes the "correct" label. Left unaddressed, this is exactly the
kind of solo-scope-collapse risk (S1) the project elsewhere guards against: four ad-hoc
mini-projects instead of one methodology reused four times. The checklist line names five
concrete sub-problems this brainstorm must resolve, plus the meta-question of whether any of
this should become a public artifact. A sixth, implicit sub-problem sits underneath all of
them: **who actually writes the wrong answers**, given the solo developer has finite QA-skim
time (D27 open question 3) and the project's only "judgment-tier" labeler is Claude, which
(D6) is not supposed to do volume work and (per this topic's own contamination concern) is not
a neutral labeler for claims it may have memorized independent of any retrieved evidence.

A structural point worth stating up front, because it shapes every option below: **these four
golden sets are not one artifact with four views — they test three different failure surfaces**
(does retrieval find the right text; does the verifier correctly judge whether found text
supports a claim; does the controversy rubric correctly rank disagreement) that happen to share
authoring infrastructure and a developer-labeling bottleneck. The methodology this topic
designs is the *shared plumbing* — perturbation techniques, contamination defenses, fixture
storage, re-run triggers — not a single merged dataset.

## Options with trade-offs

### O1 — Perturbation taxonomy for the verifier golden set

D24 already commits to "deliberate wrongs authored by inverting/perturbing verified real
claims" and names several strata informally (brainstorm 11 §2.8: overstated, fabricated/
misplaced locators, wrong `since`, contradicted, right-claim-wrong-source, paraphrase-heavy
correct, OCR-noisy). This section makes the taxonomy exhaustive and concrete, and answers the
checklist's specific callout: why does "overstated" need to be its own stratum rather than
folding into "flatly false"?

**Proposed taxonomy** (each row: what's wrong, which stage of the D24 filter ladder should
catch it, and the correct verdict a well-calibrated verifier should emit):

| Stratum | Construction | Should be caught at | Correct verdict |
|---|---|---|---|
| **Correct (positive)** | real verified claim, real citation | passes cleanly | `supported` |
| **Overstated claim** | real quote, real locator, claim adds an assertion the quote doesn't make (stronger scope, stronger causality, an unstated "always"/"only") | stage 3 entailment, decomposition step | `partial` or `unsupported` (never `supported`) |
| **Fabricated locator** | claim + citation where the locator points at unrelated or nonexistent text | stage 1 resolution | `locator-not-found` |
| **Wrong `since` (off-by-one)** | correct feature/claim, `since` value one point-release earlier/later than the source supports | stage 3, `since` sub-check | `partial` with `since_check: unsupported` |
| **Wrong `since` (off-by-major)** | same, but a whole major version off — tests whether the verifier notices large drift as readily as small | stage 3 | `partial`/`unsupported` |
| **Contradicted** | claim asserts the opposite of what the source says | stage 3 | `contradicted` |
| **Right-claim-wrong-source** | a true claim paired with a real but irrelevant citation (topically adjacent, doesn't actually discuss the claim) | stage 3, on-topic-but-not-entailing | `unsupported` |
| **Category error** | claim about the wrong kind of node (e.g. a syntax-layer claim cited against a semantics-layer passage that discusses a same-named but distinct concept) | stage 3 | `unsupported` |
| **Fabricated feature-instance combination** | claim asserts language L has feature F in combination with F′ when the source only supports F alone (or supports F′ for a different language) | stage 3 | `unsupported`/`contradicted` |
| **Quote-mismatch (fabricated quote)** | claim carries a `quote:` field whose text isn't in the located chunk at all | stage 2 fuzzy match | `unsupported` (quote-mismatch annotation) |
| **Quote-found-elsewhere** | quote is real but sits at a different locator than claimed (tests the rescue-as-hint-only rule, brainstorm 11 §2.3) | stage 2/3 | bounce with hint, not a silent pass |
| **OCR-noisy quote (false-reject probe)** | a genuinely correct claim whose quote has realistic extraction artifacts (ligature/hyphenation noise, from real ingestion QA failures per topic 28) | stage 2 fuzzy match, LLM adjudication band | `supported` (tests the false-reject side, not FA) |
| **Paraphrase-heavy correct (false-reject probe)** | correct claim phrased with heavy paraphrase relative to the source's wording, no verbatim quote at all (D3's "quotes optional" case) | stage 3, entailment-from-locator-alone | `supported` |

**Why overstated claims are a distinct stratum, not a variant of "flatly false":** a flatly
false claim (contradicted, fabricated locator, category error) fails on a *surface* signal —
the retrieved text is off-topic, absent, or says the opposite, which a verifier can catch
without deep reading comprehension. An overstated claim is, by construction, topically on
point: real source, real quote, real locator, and the located text genuinely discusses the
subject. What fails is a *narrower* comprehension task — does the text support the claim's
*exact scope*, not just its topic. This is precisely the K1 laundering pattern brainstorm 11
names as "the single most important stratum" and the reason the D24 filter ladder's design
principle is "a matched quote never waives entailment" (brainstorm 11 §2.4). Practically: a
verifier that never sees overstated-claim examples in its golden set can pass calibration while
having learned nothing except "is there a matching string nearby" — exactly the failure mode
the whole decomposition-based entailment design (claim → atomic assertions → per-assertion
grounding) exists to prevent. The six-verdict vocabulary's `partial` category is *specifically*
what an overstated claim should produce (some atomic assertions supported, the overreaching one
not), so a golden set without this stratum can never actually exercise `partial`'s correct
usage — it would only ever see `supported` or wholesale failure, and the calibration numbers
(FA ≤2%/FR ≤10%) would be measuring a task the real corpus doesn't pose. This is why D24
already flagged reporting the overstated-claim stratum's FA rate *separately*, expecting it to
be the worst-performing stratum — it is the load-bearing one.

**Construction method (proposed):** perturb real, already-verified claims rather than author
wrong claims from scratch — cheaper, and it guarantees perturbations are drawn from the actual
claim-text distribution the pipeline produces (D24's existing recommendation). Two sourcing
lanes:

- **LLM-generated candidates, volume lane.** A university-API model (not the verifier model
  itself — decorrelation matters here too, mirroring the verifier's own cross-family drift
  design in brainstorm 11 §2.6) is given a verified claim + its citation and a stratum
  assignment, and asked to produce the perturbed version plus a one-line note on what was
  changed. Cheap, scales to volume, and because the *target stratum* is specified up front
  (not left to the model to invent), coverage across strata is controllable.
- **Developer-curated selection, quality lane.** The developer selects and lightly edits a
  stratified sample from the LLM-generated candidates during the R1 corpus QA skims (already
  committed as golden-set co-authoring time per D27's ratified developer amendment), rejecting
  candidates that are ambiguous, too easy, or accidentally still true. This is the same
  "developer co-authors during QA skims" mechanism D27 already established for retrieval golden
  queries — reusing it for verifier perturbations avoids opening a second labeling channel.

Target composition, adapting D24's proposed split: **40% correct-stratum items** (split
roughly evenly between plain-correct, OCR-noisy, and paraphrase-heavy, since these calibrate
the false-reject side) and **60% wrong-stratum items**, with the overstated-claim and wrong-
`since` strata over-weighted relative to the others (they are both the hardest to catch and the
most common real-world failure shapes) — proposed at roughly double the per-stratum share of
the remaining wrong strata.

### O2 — Contamination hygiene

The checklist frames this precisely: a Claude-family model plausibly authored or interacted
with training corpora containing PLDB/Wikipedia/spec text, and Claude also sits inside this
pipeline as thinker/challenger/moderator/ontologist. Does that let golden-set claims (and their
"correct" verdicts) leak into what a grading model already "knows," independent of the
retrieved evidence it's supposed to be judging?

Two contamination vectors need to be distinguished, because they have different exposure and
different fixes:

**Vector 1 — the verifier itself is contaminated.** D6 already forecloses most of this risk by
policy: Claude is explicitly excluded from the verification loop (brainstorm 11 §2.6, "Claude
is deliberately not in the verification loop except as an occasional manual spot-check
instrument"). The verifier is `deepseek`/`glm`/`mini` — university-hosted models with their own
independent (and to LangAtlas, opaque) training corpora. This doesn't eliminate contamination
risk, it just relocates it: any general-purpose LLM trained on a large web crawl has *plausibly*
seen PLDB, Wikipedia, and popular language specs too. A verifier that "knows" Rust has pattern
matching can rubber-stamp a claim about Rust pattern matching without actually reading the
provided chunk — the exact failure the context-blindness design (brainstorm 11 §2.7) partially
addresses but does not fully solve, because context-blindness only prevents the verifier from
seeing *proposer* context; it cannot prevent the verifier from having *pretrained* general
knowledge about popular languages.

**Vector 2 — the golden-set labels themselves are contaminated.** If an LLM (Claude or the
university API) both generates a perturbed claim *and* is later asked to confirm the perturbed
claim's correct verdict, and it does so from prior knowledge rather than from actually reading
the evidence text, the golden set's "ground truth" is not independently established — it's
recycled model output validating itself. This is a distinct risk from Vector 1: it corrupts the
benchmark, not the production verifier.

**Options for defense, given the actual budget/tooling constraint (Claude Code Pro + a
university API, no dedicated red-teaming infra, no ability to inspect any model's training
data):**

| Defense | Mechanism | Cost | Coverage |
|---|---|---|---|
| **Structural context-blindness (already adopted, D24)** | verifier prompt is built from a field whitelist; no free text, no proposer identity | free (already built) | defends Vector 1 partially — stops proposer-bias leakage, does nothing against pretrained general knowledge of famous facts |
| **Counterfactual construction (recommended, primary)** | perturb toward claims that are *plausible-sounding but specifically false in a way no model could have memorized* — invented version numbers, invented (but stylistically consistent) feature-name variants, altered locator page numbers, swapped-language attribution among two real similar languages — rather than perturbing toward "famous known facts stated wrong" | free, authoring-time only | defends both vectors: a model cannot rubber-stamp from memory a claim about "Rust 1.31 introduced non-lexical lifetimes" when the correct answer per the actual cited chunk is 1.36, because there is no famous canonical fact to fall back on — the model is forced to read |
| **Obscure-locus targeting** | prefer perturbing claims anchored to specific page/section/version numbers and less-famous corners of the corpus (a mid-chapter qualifier, not a textbook's headline claim) over broad, widely-known facts | free, authoring-time discipline | reduces Vector 1 exposure; a specific `pp. 412` claim about a niche feature is far less likely to be in any model's memorized "common knowledge" than "Python is dynamically typed" |
| **Cross-family sampling as a contamination canary (extends D24 §2.6/2.8)** | the existing 10%-sample cross-family check (`mini` vs `deepseek`) already flags disagreement; treat a *rising* agreement rate on wrong-stratum items specifically as a contamination signal worth investigating (two decorrelated model families agreeing with each other on a wrong answer more often than chance is weak evidence both are pattern-matching to the same memorized fact rather than reading) | free (reuses D24 machinery, one added report column) | detection only, not prevention; cheap because it rides infrastructure that exists anyway |
| **Held-out slice never shown to any authoring model** | reserve a small subset of golden items authored purely by the developer, with no LLM involved in generating *or* confirming the wrong answer, used only for periodic manual audits, never fed back into any prompt | developer time only — the scarce resource | strongest guarantee, but not scalable past a handful of items |
| **Dedicated adversarial red-team pass** | a separate agent role tasked specifically with trying to fool the verifier | real engineering + prompt-design effort | rejected as disproportionate — this is the kind of infra a red-teaming-staffed org builds, not a solo-dev proof-of-concept; D31's equivalent reasoning for the prompt-injection surface ("bounded severity, non-trivial likelihood, light-touch controls... no reader/actor split needed") applies here too |

**Recommendation:** counterfactual construction as the primary, always-on defense (it is free
and structural — it changes *what* gets authored, not how it's checked), layered with obscure-
locus targeting as an authoring habit, the existing cross-family sample repurposed as a passive
drift/contamination gauge (no new mechanism, just a new interpretation of an existing number),
and a small (~10–15 item) fully-developer-authored held-out slice reserved for occasional manual
spot-audits — proportionate to the "occasional calibration check" pattern D24/brainstorm 16 §2.1
Option C already established for other spot-check needs in this project. A dedicated
adversarial red-team role is explicitly rejected as disproportionate to project scale, matching
D31's risk-tolerance precedent on the adjacent prompt-injection question.

### O3 — Hand-labeled controversy cases

D25 (topic 12) already proposes ~50 hand-labeled cases regression-testing the controversy
rubric, and names two candidate example domains: constructed pipeline-side disagreement
(non-convergent debates, partial verification verdicts) and genuine field disputes (gradual-
typing efficacy, checked-exceptions debate, GC-vs-ownership learnability). The controversy
scale itself was subsequently amended by the developer to **four levels, not five** — level 4
(`unsettled-in-the-field`) folded into level 3 (`disputed`) — so this section's job is narrower
than brainstorm 12 originally scoped it: cases now only need to span 0–3, with the folded level
3 covering both "the pipeline couldn't settle it" and "the field hasn't settled it" sub-cases
without needing a separate rubric tiebreaker between them.

**Selection strategy — real disputed facts vs constructed:**

- **Constructed cases (bootstrap lane).** Synthetic structured inputs — hand-built debate
  records, verification-verdict sets, and assessment spreads matching the assessor's exact
  input schema (brainstorm 12 §5.2: debate outcome, contradiction-register state, per-source
  verdicts, source-strength context, assessment spread) — can be authored **before any real
  corpus or ontology content exists**, since they don't depend on the research phase having
  produced anything. This is the only lane available at project start, and it's the cheapest:
  the developer (or a Claude session under developer review) writes 15–20 small structured-
  input fixtures spanning levels 0–2 cleanly plus a handful of level-3-boundary cases, each
  paired with the level the developer believes is correct and a one-line rationale.
- **Real cases, opportunistic lane.** Once the research phase's R3/R4 schema-dispute debates
  and (later) phase-1 sweep fact-debates start producing genuine escalations, D25's own
  ratified escalation rule already routes every level-3 assignment to Claude for review. A
  Claude-reviewed escalation *is* a hand-labeled case in all but name — the developer's marginal
  cost to turn it into a golden-set fixture is spot-checking Claude's escalation call (cheap,
  review not authorship) and archiving the structured inputs + outcome. This lane is
  self-supplying once real pipeline volume exists and requires no dedicated authoring sessions.
- **Real cases, curated lane (for genuine field disputes specifically).** The brainstorm-12
  examples (gradual typing, checked exceptions, GC-vs-ownership) need the source corpus to
  actually contain opposing tier-A/B material before they can become real fixtures — this can't
  happen before R1/R3 ingest the relevant literature. Flag these as a standing "if the corpus
  ever contains this, mint it as a golden case" note rather than a task with a deadline.

**How many, and who labels:** confirm D25's ~50-case target as the ceiling, but recommend
reaching it through the bootstrap + opportunistic lanes rather than a dedicated authoring
sprint — realistically ~15–20 constructed cases at project start (a few hours of developer time,
one sitting), then the opportunistic lane adding real cases roughly at the rate escalations
occur (bounded by pipeline volume, not developer bandwidth) until ~50 is reached. This keeps
the labeling burden realistic for a solo developer: the expensive part (reading a real debate
and forming a judgment) is work the developer would be doing anyway under D25's Claude-
escalation-review process; golden-set curation just archives that work rather than discarding
it.

**Keeping cases in sync as ontology/schema evolves (topic 29 tie-in):** each golden case is
tagged with the `ontology_version` and controversy-rubric `prompt_version` (D41's prompt
registry) it was authored against, mirroring how facts themselves carry provenance. A schema
change to the assessor's structured-input shape (e.g. a new signal source added to §5.2's input
list) is exactly the kind of change topic 40's validator/normalizer CLI should catch as a
golden-set staleness check — a case whose fixture doesn't validate against the current input
schema is flagged, not silently skipped. This does **not** require topic 29's migration-manifest
machinery itself (golden-set fixtures are test data, not canonical corpus content, so they sit
outside D16's blast-radius/migration scope entirely) — it only needs the much lighter "does this
fixture still parse against the current schema" check, which is a natural extension of topic
40's existing validator-CLI scope rather than a new mechanism.

### O4 — Retrieval golden queries

D27 (via brainstorm 25 §O4) already designed the concrete shape: 40–60 queries in three
difficulty bands (exact-term, paraphrase/concept, cross-source), scored on Recall@5/nDCG@10/
Recall@50/MRR, authored during R1 QA skims with the developer co-authoring per the ratified
amendment. This topic's job is narrower: **is this the same authoring effort as the verifier
perturbation taxonomy, or a separate one?**

They test different failure surfaces (retrieval: can the index find the right chunk at all;
verification: given a chunk, does it support the claim) and need different artifact shapes
(query → expected chunk/section IDs, vs. claim + citation → expected verdict) — so they cannot
simply be merged into one dataset. But they should not be authored from scratch twice, either:
**every correct-stratum verifier golden item already is a `(claim text, locator)` pair whose
citation, by construction, must be findable by the retrieval stack** — that's what "correctly
verified" means. This gives a cheap derivation path:

- **Derived-first:** for each correct-stratum verifier golden item, its claim text (or a
  natural paraphrase of it) becomes a retrieval query, and its cited locator's chunk(s) become
  the expected result. This alone can supply a meaningful fraction of the exact-term and
  paraphrase bands at essentially zero extra authoring cost — the two golden sets share a
  bootstrap corpus.
- **Hand-authored supplement:** the derived queries systematically under-represent two things
  the D27 difficulty bands specifically want: (a) genuinely hard paraphrase queries that don't
  read like a restated claim (real users/agents phrase questions, not claim-shaped assertions),
  and (b) cross-source queries expecting a *multi-source* hit set, which no single verifier
  claim (bound to one citation) can express. These remain a dedicated, smaller hand-authoring
  task for the developer during R1 QA skims — but a smaller one than designing all 40–60 queries
  from nothing, since the derived set already covers the easier bands.

**Recommendation:** treat retrieval golden queries as *derived-first, hand-supplemented* from
the verifier golden set's own correct-stratum citations, with the developer's R1 QA-skim time
spent specifically on the paraphrase and cross-source bands the derivation can't produce. This
is the concrete answer to "same authoring effort or separate": **one shared bootstrap corpus,
two distinct scored artifacts, with the smaller of the two authoring tasks (retrieval queries)
partially subsidized by the larger one (verifier perturbations) that has to exist regardless.**

### O5 — Joining the topic-16 eval/regression harness, concretely

D30 (topic 16) built a specific, narrower thing: **record/replay fixtures** under
`tests/fixtures/providers/`, with a lighter-weight `regression/` subfolder using human-diff
review rather than CI pass/fail — deliberately *not* a scored golden set, because at the time
no debate volume existed to author one from (brainstorm 16 §2.3 Option A vs B). D30 explicitly
named this topic (36) as the owner of any eventual scored debate-outcome golden set (Option B),
once phase-1 sweep-debate volume makes it authorable.

"Joins the topic-16 eval harness" therefore does **not** mean the golden sets designed here
become CI-blocking the way topic-16's core regression fixtures are (they aren't — topic 16's
own fixtures are explicitly non-blocking, human-diff-reviewed). It means three concrete points
of shared infrastructure:

1. **Shared storage convention.** Golden-set fixtures (verifier, controversy, retrieval, and —
   once authored — the deferred debate-outcome set) live in a sibling directory,
   `tests/golden/` (`verifier/`, `controversy/`, `retrieval/`, `debates/`), parallel to
   `tests/fixtures/providers/regression/` — distinguishing *scored, pytest-run, threshold-gated*
   golden sets from topic-16's *diff-and-review* regression fixtures, while keeping both under
   one `tests/` root so a contributor finds all eval material in one place.
2. **Shared tooling.** The verifier golden set literally reuses D41's `replay_verdict` library
   function (already designed to be shared between topic 16's counterfactual instrumentation and
   topic 32's bulk verifier-drift reporting) — golden-set scoring is a third consumer of the same
   function, not a fourth reimplementation. Re-run triggers follow the same convention D26/D41
   already established elsewhere: any `prompt_version` or resolved-model-id change triggers a
   re-run (mandatory/scored for the golden sets here, soft/log-only for topic-16's regression
   fixtures per D41's existing rule).
3. **The deferred debate-outcome set's eventual home.** When phase-1 sweep-debate volume
   materializes and D30's Option B becomes buildable, it lands in `tests/golden/debates/` under
   this topic's methodology (perturbation-style construction from real accepted vs. rejected
   debate outcomes, the same contamination-hygiene discipline from O2, the same developer-
   labeling-burden constraints from O3) — closing the loop D30 explicitly left open, rather than
   becoming a fifth ad-hoc mini-project.

### O6 — Public benchmark: commit now, or stretch goal?

The checklist line calls this "possible," not decided. Two considerations pull in opposite
directions.

**The case for building toward it now:** LangAtlas already commits to publishing measured
verifier error rates as a site-visible honesty feature (D24, ratified — "the pipeline's measured
error rates will be published"). A citable, versioned public golden set (in the spirit of TRUE
(Honovich et al. 2022), SummaC (Laban et al. 2022), FActScore (Min et al. 2023), and MiniCheck
(Tang et al. 2024) — all cited in brainstorm 11's Sources as the methodological lineage this
project's verifier design already follows) would let outside readers independently reproduce
those published numbers rather than trust them on faith, which is squarely in the spirit of
D19's positioning wedge (typed graph + per-fact sourcing) and D40's "narrower on purpose,
independently checkable" launch framing.

**The case against building toward it now:**

- **It works against O2's contamination hygiene.** A published golden set is exactly the kind
  of artifact that gets scraped into the next generation of models' training data — the
  well-documented public-benchmark contamination problem (Sainz et al. 2023; Oren et al. 2023).
  Publishing the golden set the verifier is calibrated against risks silently invalidating
  future re-calibration runs the moment a newer university-API model has memorized the answer
  key, which is precisely Vector 2 from O2 turned into a standing, unavoidable liability instead
  of an authoring-time discipline.
- **The set isn't credible as a benchmark yet.** At D24's proposed scale (~200–300 verifier
  items, ~50 controversy items, 40–60 retrieval queries) and before any real pipeline output
  exists to validate the labels against, this is a calibration instrument, not a community
  benchmark — publishing it prematurely as "the LangAtlas benchmark" invites exactly the kind of
  scrutiny a solo-developer proof-of-concept isn't resourced to defend.
- **No deadline pressure, per CLAUDE.md's developer constraints** (D11: "no deadline... no
  shortcuts that damage the long-term product") — there is no launch-timing reason to decide
  this now rather than once the underlying golden sets have matured through real pipeline use.
- **The lower-cost version of the positioning benefit already ships.** D24's commitment to
  publish *measured error rates* (a number and a methodology description) delivers most of the
  "independently checkable" positioning value without requiring the underlying test items
  themselves to be public and therefore exposed to contamination.

**Recommendation: stretch goal, not a near-term commitment.** If pursued later (once the golden
sets are mature — plausibly post-1.0, once real pipeline volume has validated the labels
against production behavior), the standard academic-benchmark contamination mitigation applies
directly: a **public sample slice** (enough items to demonstrate methodology and let readers
sanity-check the published error rates) **plus a private held-out slice** that is never
published and is swapped in periodically for the actual calibration runs — mirroring how MMLU/
ARC-style benchmarks and O2's own held-out-slice recommendation already work. Licensing, if it
happens, follows the `langatlas-transcripts` CC0 1.0 precedent (D42) rather than the corpus's
CC BY-SA 4.0 — a golden set is evaluation tooling, not corpus content, and CC0 maximizes its
reuse value as a citable artifact the same way D42 reasoned for transcripts.

## Recommendation

*Proposed* — the developer ratifies:

1. **One shared perturbation taxonomy (O1)** — 13 named strata (table above) reused across the
   D24 verifier golden set's authoring, with the **overstated-claim stratum treated as
   first-class and reported separately** per D24's existing calibration-target design, since it
   is the only stratum that actually exercises the `partial` verdict's intended meaning and the
   K1 laundering defense. Construction: LLM-generated candidates (volume, decorrelated from the
   verifier model) curated by the developer during R1 QA skims (quality), target composition
   ~40% correct / 60% wrong-stratum with overstated-claim and wrong-`since` over-weighted.
2. **Contamination defense (O2)** is primarily structural, not procedural: perturb toward
   **counterfactual, specifically-invented wrongness** (invented version numbers, swapped
   similar-language attribution, altered page/section loci) rather than "famous facts stated
   wrong," supplemented by obscure-locus targeting, the existing D24 cross-family sample
   repurposed as a passive contamination gauge, and a small (~10–15 item) fully-developer-
   authored held-out slice for occasional manual audits. No dedicated red-teaming role — rejected
   as disproportionate, matching D31's precedent.
3. **Hand-labeled controversy cases (O3)**: keep D25's ~50-case target, reached via a bootstrap
   lane (~15–20 synthetic structured-input cases authored at project start, before any real
   corpus exists) plus an opportunistic lane (D25's own Claude-escalation-review process already
   produces real hand-labeled cases as a byproduct — archive them rather than re-author). Genuine
   field-dispute cases (gradual typing, checked exceptions, etc.) get minted opportunistically
   once the corpus contains the relevant opposing tier-A/B literature, not on a schedule. Cases
   carry `ontology_version`/`prompt_version` tags and are staleness-checked (not migration-
   gated) by topic 40's validator.
4. **Retrieval golden queries (O4)**: derived-first from the verifier golden set's own
   correct-stratum `(claim, locator)` pairs — a shared bootstrap corpus, not a duplicated
   authoring effort — supplemented by a smaller, dedicated hand-authoring pass (developer, during
   R1 QA skims per D27) specifically for the paraphrase and cross-source difficulty bands the
   derivation can't produce.
5. **Topic-16 join (O5)**: shared `tests/golden/` directory (`verifier/`, `controversy/`,
   `retrieval/`, `debates/`) parallel to topic-16's `tests/fixtures/providers/regression/`,
   distinguished by being scored/threshold-gated rather than diff-reviewed; the verifier golden
   set reuses D41's `replay_verdict` function as a third consumer; the deferred debate-outcome
   golden set (D30's Option B) becomes this topic's responsibility once phase-1 debate volume
   exists, landing in `tests/golden/debates/` under the same methodology.
6. **Public benchmark (O6)**: stretch goal, not a near-term commitment. Ship D24's already-
   ratified "publish measured error rates" instead, now. If a public benchmark is pursued later,
   use a public-sample-slice + private-held-out-slice split (contamination mitigation) and CC0
   1.0 licensing (matching the `langatlas-transcripts` precedent, D42) — but design that split
   only when the underlying golden sets are mature enough to be worth publishing.

## Open questions for the developer

1. **Perturbation authoring split**: is LLM-generated-candidates + developer-curated-selection
   (O1) the right division, or does the developer want a fully manual authoring pass for the
   overstated-claim stratum specifically, given it's the single most load-bearing one?
2. **Contamination defense sufficiency**: is counterfactual construction (invented plausible-
   sounding wrongness) an acceptable *primary* defense given the no-red-teaming-infra
   constraint, or does the developer want the held-out-slice audit lane sized larger than the
   proposed ~10–15 items?
3. **Controversy golden-set count and sourcing**: confirm the ~50-case target from D25 stands,
   reached via the bootstrap + opportunistic hybrid (O3) rather than a dedicated authoring
   sprint — or does the developer want a firmer near-term floor (e.g. all ~50 authored before
   the research phase's R3/R4 debates start) rather than letting the count grow opportunistically
   at pipeline-volume pace?
4. **Retrieval golden query derivation**: confirm deriving a majority of the exact-term/
   paraphrase bands from the verifier golden set's own citations (O4), with dedicated
   hand-authoring reserved for paraphrase-hard and cross-source queries only — or does the
   developer want the full 40–60 queries hand-authored independently as D27 originally
   described, treating the derivation as a bonus rather than the primary source?
5. **Fixture directory placement**: confirm `tests/golden/` (parallel to topic-16's
   `tests/fixtures/providers/regression/`) as proposed, or does the developer prefer golden
   sets nested inside the existing `tests/fixtures/` tree instead of a sibling directory?
6. **Public benchmark posture**: confirm stretch-goal/not-now (O6), or does the developer want
   the public-sample/private-holdout split scoped in more detail now, even without committing to
   publish, so the golden sets are authored with that eventual split already in mind (e.g.
   tagging each item `public-eligible: true/false` from day one rather than retrofitting later)?
7. **Golden-set staleness enforcement**: should topic 40's validator hard-fail CI when a golden
   fixture no longer parses against the current schema (matching the project's general
   fail-closed posture), or is a soft/log-only flag sufficient, mirroring D41's soft-gate stance
   on topic-16's regression-fixture staleness checks?

## New brainstorm topics surfaced

- **Eval-contamination monitoring for a future public benchmark** — if O6's stretch goal is ever
  greenlit, detecting when public golden-set items have leaked into a newer model generation's
  training data (the practical version of the Sainz/Oren contamination-detection literature)
  needs its own design; not worth designing before the benchmark itself is greenlit, but flagged
  here so it isn't lost if that day comes.
- **Counterfactual claim construction as a reusable technique beyond golden sets** — O2's
  "perturb toward specifically-invented wrongness rather than famous facts stated wrong" is a
  generically useful pattern; worth a pointer in case it turns out useful for other adversarial-
  robustness needs the project surfaces later (e.g. testing the prompt-injection defenses from
  topic 17 with counterfactual injected instructions rather than only known-pattern ones) — small
  enough to fold into whichever topic picks that up rather than standing alone now.

## Sources

- Sainz, O., Campos, J. A., García-Ferrero, I., Etxaniz, J., de Lacalle, O. L., & Agirre, E.
  (2023). NLP Evaluation in Trouble: On the Need to Measure LLM Data Contamination for Each
  Benchmark. *EMNLP 2023 Findings*. https://aclanthology.org/2023.findings-emnlp.722/ — the
  general case that public benchmark test sets get absorbed into subsequent model training
  data, motivating O6's public-sample/private-holdout split.
- Oren, Y., Meister, N., Chatterji, N., Ladhak, F., & Hashimoto, T. B. (2023). Proving Test Set
  Contamination in Black Box Language Models. *arXiv:2310.17623*.
  https://arxiv.org/abs/2310.17623 — concrete detection methodology for whether a model has
  memorized a specific benchmark's test items, referenced as the shape of monitoring a future
  public benchmark would need.
- (TRUE, SummaC, FActScore, MiniCheck — the entailment-evaluation methodological lineage behind
  the D24 verifier design — are already cited in full in
  [brainstorms/11-verification-pipeline.md](11-verification-pipeline.md)'s Sources section; not
  duplicated here.)
