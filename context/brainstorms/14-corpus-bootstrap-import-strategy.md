# 14 — Corpus Bootstrap & Import Strategy

> Backlog brainstorm for LangAtlas. Scope: whether to seed the initial knowledge base from PLDB
> (public domain) and/or Wikidata (CC0) versus pure agent generation, and how a fact's origin
> (imported / agent-derived / human-authored) gets marked in the schema. From brainstorm 08.
> Binding context: `context/decisions.md` D1 (no PR gate, admissibility = verification, not
> review), D3/D14 (community sources are corroboration only, never sole backing; TIOBE-class
> indexes are single attributed data points, never bulk ingestion), D4/D24 (source-first workflow,
> index-only verifier evidence, `pending-source` for un-ingested citations), D11/D27 (frontloaded
> research phase, no artificial MVP slice), D19 (typed concept graph + per-fact sourcing as the
> positioning wedge vs PLDB/hyperpolyglot), D20/D23 (fact schema, provenance blocks), D28
> (14-language initial set). All proposals here are *proposed* until the developer ratifies.

## Problem framing

Two public datasets are structurally tempting bootstrap material: **PLDB** (Programming Language
DataBase, ~135k facts on ~5,000 languages, dedicated to the public domain, PDDL-compatible;
Roussey 2026) and **Wikidata**'s programming-language entities (structured statements CC0-licensed;
Wikimedia Foundation 2026). Both are license-compatible with CC BY-SA 4.0 output — public domain
and CC0 content can be relicensed into a share-alike corpus with no obligation flowing back. The
naive move is: pull PLDB's per-language fact rows and Wikidata's `P`-statements (paradigm, typing
discipline, influenced-by, first-appeared) into LangAtlas as a fast skeleton, saving agent-hours
on the frontloaded research phase (D27) and the per-language sweep (D5).

But license compatibility is not the same as *admissibility*. D4's source-first rule is stricter
than copyright law: a fact may not exist in the canonical store without `source_id` + `locator`
resolving to a structured bibliographic record that the D24 verifier can check entailment
against. A PLDB CSV row or a Wikidata statement is not, itself, that kind of source — it is
someone else's *already-asserted conclusion*, with no page/section locator into primary
literature. D3 anticipated exactly this and pre-ratified the answer for *citation*: "community
sources (PLDB, hyperpolyglot, wikis) are corroboration only — never the sole backing for a fact."
The open question this brainstorm actually has to resolve is narrower than "can we import PLDB"
— it is: **does bulk-importing PLDB/Wikidata *rows as facts* violate D3's corroboration-only rule
even under a license that permits the copy, and if a bounded form is useful, what does it look
like and how is its provenance marked so it never gets confused with a verified, primary-sourced
fact?**

A second, independent question the checklist scope raises: regardless of the import verdict, the
schema needs a place to say "this fact came from bulk import" vs "an agent derived and sourced
this from a primary source" vs "a human expert supplied/corrected this via a challenge." Whether
that is a new field or falls out of existing D23/D24/D25 provenance machinery needs a concrete
answer, not just a principle.

## Options with trade-offs

### Option A — Full bulk import as seed facts (rejected)

Pull PLDB rows and Wikidata statements directly into `languages/<id>/instances/*.yaml` as
`present`/`absent` records with `source: pldb` / `source: wikidata`, then let the D5 sweep
overwrite them later.

- Pros: fastest possible skeleton — thousands of instance records in an afternoon; immediately
  gives the site *something* to render for all 14+ D28 languages, which flatters early SEO
  crawl coverage.
- Cons: directly contradicts D3 ("never the sole backing for a fact") — every imported row would
  be exactly that until the sweep gets around to re-deriving it, and per D11 there is no deadline
  forcing an early sweep, so stale, sole-sourced import rows could sit in the "verified-looking"
  corpus indefinitely. It also undermines D19's stated wedge: LangAtlas's entire differentiation
  argument against PLDB is *per-fact primary sourcing* — an early corpus that is silently
  PLDB-in-a-trenchcoat is the single fastest way to forfeit that positioning before the site
  launches (risk P1 in brainstorm 08's register). Practically, PLDB's schema (informal free-text
  cells, no fixed feature ontology) does not map cleanly onto LangAtlas's typed
  concept/feature/dimension graph (D2) — a naive field-to-field import would need its own
  reconciliation layer that is arguably *more* work than sourcing the fact directly, and every
  imported row would still need a D24 verification pass before it could leave `unverified` status,
  so the "savings" evaporate at the gate.

### Option B — No bulk import; pure agent generation from day one

Reject PLDB/Wikidata as a data source entirely (beyond the D3-sanctioned corroboration-only
citation role they already have); every fact enters exclusively through the D11 research phase
and the D5 sweep, sourced against primary literature (specs, textbooks) from the start.

- Pros: zero ambiguity about provenance — everything in the canonical store followed the same
  source-first path, so there is no need for an "imported" status axis at all, and no risk of
  D19's wedge getting diluted. Simplest to reason about and to explain publicly.
- Cons: forfeits a genuinely useful *navigational* signal PLDB/Wikidata could offer for free —
  neither dataset is being proposed as fact content, but both are large, structured indexes an
  agent could use to check "did I forget a feature/language that's obviously relevant" during
  D27's R3 divergent survey or a per-language sweep, the same finding-aid role D14 rule 5 already
  grants Hyperpolyglot and Wikipedia. Ruling out *any* use, not just bulk-import-as-facts, is
  stricter than the situation requires.

### Option C — Hybrid: import as gated, low-confidence stub facts, subject to the same admissibility gate — *proposed*

Do not import PLDB/Wikidata rows as facts at all. Instead, treat both datasets purely as
**candidate/coverage input** to the pipeline, never as fact content, and mark that role explicitly
in the schema so it can never be mistaken for a sourced claim:

1. **Coverage & candidate-generation use only.** During D27's R0–R3 (ontology research) and the
   D5 per-language sweep, an agent may query PLDB/Wikidata to build a checklist of
   language↔feature pairs worth checking ("PLDB says Rust has macros — does our sweep have a
   sourced fact for that yet?") — exactly the finding-aid role D14 already ratified for
   Hyperpolyglot/Wikipedia, extended by analogy to PLDB and Wikidata since both meet or exceed
   that bar on license terms (public domain / CC0 vs CC BY-SA). This produces a `pending-source`
   work-queue entry (already a first-class D24 concept) or a sweep-questionnaire cell, never a
   canonical record.
2. **No stub records, no new "imported" fact status.** Because D4's admissibility gate already
   requires ≥1 tier-A/B `supported` citation for *any* fact to leave `unverified`, and D3 already
   forbids community sources as sole backing, there is no daylight in the existing rules for an
   "imported-but-unverified" fact to occupy — it would either need its own citation (in which case
   it is not an import, it is a normally-sourced fact that happened to be candidate-generated by
   PLDB) or it would sit permanently below the admissibility bar, which is just a `pending-source`
   entry with extra steps.
3. **Provenance marking falls out of existing machinery, with one small addition.** D23's
   `provenance.claim_origin: source-derived | prior` and `provenance.proposer.agent` already
   distinguish *how* a fact came to be asserted; D9 already gives human-challenge corrections a
   distinct path (a GitHub issue → re-argued fact, same verification gate, so a corrected fact is
   provenance-identical to an agent-derived one plus a `chat_run_id`/issue link). The one gap is
   *candidate-generation source*, which is not currently recorded anywhere and arguably should be,
   purely for pipeline analytics (which candidate-generation channel produces facts that survive
   verification vs get rejected) — **add an optional `provenance.candidate_source:
   pldb | wikidata | hyperpolyglot | internal-survey | sweep-questionnaire | challenge` enum**,
   recorded at proposal time, never rendered on the public site (it answers "what suggested we
   look here", not "what backs this claim" — that's still `sources:`). This is additive to D23's
   schema, not a new status axis, and does not touch the D25 verification/freshness/dispute model
   at all.
4. **License compatibility is a non-issue for this scoped use.** Because nothing from
   PLDB/Wikidata is ever copied into a canonical record's citable content, CC BY-SA 4.0
   compatibility is moot for the pipeline-input role — the license question only mattered under
   Option A. Attribution is not owed for uncopied candidate-generation queries.

- Pros: captures the one real efficiency PLDB/Wikidata offer (coverage checklisting, catching
  agent blind spots) without touching D3's corroboration-only rule or D19's wedge; requires almost
  no new schema (one optional enum field, non-public); keeps the admissibility gate as the single
  source of truth for what's canonical, so there is never a second-class "imported" tier of fact
  sitting in the corpus.
- Cons: does not save agent-hours on the actual bottleneck — sourcing and verifying claims against
  primary literature — since that step still has to run per fact regardless of where the candidate
  came from; some hand-wringing risk that "candidate-generation from PLDB" quietly becomes
  "paraphrasing PLDB's own characterization of a feature" if agents aren't instructed carefully
  (mitigated by the same D14 rule-5 instruction already governing Hyperpolyskip/Wikipedia use: read
  for orientation, always re-derive and re-cite from primary sources).

## Recommendation

*Proposed*: **Option C.** No bulk import of PLDB or Wikidata as fact content, ever — Option A is
rejected outright as incompatible with D3 and actively damaging to D19's positioning wedge, and
would not even save the work it promises once the D24 gate is accounted for. PLDB and Wikidata
join Hyperpolyglot and Wikipedia (D14 rule 5) as **finding aids only**: usable by research-phase
and sweep agents to generate coverage checklists and candidate language↔feature pairs, never
copied into a record's `sources:` or claim text. This needs zero new fact-status machinery — D3,
D4, and the existing D23 provenance block already forbid the thing Option A proposed and already
support the thing Option C proposes. The one concrete schema addition: an optional, non-public
`provenance.candidate_source` enum for pipeline analytics, extending D23's provenance block rather
than creating a parallel identity concept. "Imported vs agent-derived vs human-authored" resolves
to: **there is no imported tier** — every canonical fact is agent-derived-and-verified or
human-corrected-and-reverified (D9); the only thing that varies is which non-authoritative signal
prompted an agent to go look, which is exactly what `candidate_source` records.

On the practical-value question: seeding does **not** save real agent-hours or cost under this
project's constraints. The scarce resource per CLAUDE.md is not "knowing which language/feature
pairs might be worth a fact" — a broad-knowledge agent with internet access (D27's R3) already
generates that list for free from its own priors plus the D15 source corpus. The scarce resource
is *verified sourcing*, which the D24 gate demands per fact regardless of origin, and a bulk
import buys nothing there — it would just relocate the same verification cost from "the sweep"
column to "the import-reconciliation" column while adding schema-mapping overhead PLDB's informal
structure doesn't avoid. Treating import as a false economy (per the developer constraints in
CLAUDE.md: Claude Pro limits and a slow university API make the verifier, not the drafting step,
the actual bottleneck) is the correct call.

## Open questions for the developer

1. **Ratify Option C's scope** — finding-aid-only use of PLDB/Wikidata, no bulk import, no new
   fact-status tier? This is a direct extension of D14 rule 5 by analogy; flag if PLDB/Wikidata
   should be treated more restrictively (e.g. barred entirely) or more permissively than
   Hyperpolyglot/Wikipedia given their different license terms (public domain/CC0 vs CC BY-SA).
2. **Is `provenance.candidate_source` worth adding now**, or should it wait until brainstorm 32
   (pipeline observability) designs the fuller analytics story — is a one-field addition to D23's
   schema in scope for this brainstorm, or should this document just *recommend* it there instead
   of specifying it here?
3. **Wikidata `sameAs` cross-linking** (already implicitly assumed by D10's JSON-LD plan —
   `ComputerLanguage` + Wikidata `sameAs`) is a *different*, already-decided use of Wikidata (an
   outbound identifier link on the site, not a fact-content import) — should this document say so
   explicitly to prevent future confusion between "Wikidata as SEO/structured-data cross-link"
   (already D10) and "Wikidata as fact source" (rejected here)?
4. **PLDB's `keywords`/`extensions`/file-metadata fields** (not feature/paradigm claims, just
   identifying metadata: file extensions, first-appeared year as a single data point) — does the
   developer want an explicit carve-out allowing *pure identification metadata* (not feature
   claims) to be pulled from PLDB/Wikidata as single attributed data points, mirroring D14 rule 7's
   treatment of TIOBE? This would be a much smaller, clearly bounded exception if wanted.

## New brainstorm topics surfaced

- **Finding-aid tooling for the research phase** — a concrete `search_finding_aids` or checklist
  generator that queries PLDB/Wikidata/Hyperpolyglot/Wikipedia during D27's R3 survey and the D5
  sweep, distinct from the D15/21 primary-source RAG tools (which are citable); scopes how
  "finding aid" moves from a policy statement (D14 rule 5, this document) into an actual pipeline
  component.
- **Pipeline-input provenance analytics** — whether `candidate_source` (and similar
  non-public-but-useful proposal metadata) belongs in a broader "why did the pipeline look here"
  telemetry model, feeding backlog topic 32 (pipeline observability & prompt registry).

## Sources

- Roussey, B. (PLDB contributors) (2026). *PLDB: a Programming Language DataBase — About /
  Readme* (public domain; PDDL-compatible; attribution appreciated, not required).
  https://pldb.io/pages/about.html · https://pldb.io/readme.html ·
  https://github.com/breck7/pldb
- Wikimedia Foundation (2026). *Wikidata:Licensing* (structured data in main/property/lexeme
  namespaces under CC0; text elsewhere under CC BY-SA 4.0).
  https://www.wikidata.org/wiki/Wikidata:Licensing
