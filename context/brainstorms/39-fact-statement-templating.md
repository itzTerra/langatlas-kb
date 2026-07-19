# 39 — Fact Statement Templating

> Backlog brainstorm for LangAtlas. Scope (checklist item 39): canonical per-kind claim
> templates (the concrete design behind D23/brainstorm 09's O6, never fully specified);
> template change management (re-render vs re-embed vs re-verify); sampling-parameter
> provenance in fact records (surfaced by brainstorm 13 as an open question, not yet
> resolved). Binding context: D23 (two-part fact identity — anchor + content-keyed
> `f-<12hex>` id over the **canonical claim string**, "canonical claim phrasing as fixed
> per-kind templates over node ids," copyedit-tolerant hashing confirmed so wording fixes
> don't mint a new fact id), brainstorm 09 §O6 (the S-expression-shaped canonical-claim
> grammar for all eight claim kinds, with the explicit design rule "templates render
> *from* claims, claims never derive from renderings"), D16/D38 (ontology blast-radius
> semver + migrations-as-scripts machinery, reused here by analogy), D26 (provider
> abstraction: `RunContext`, cost log, cache keying on `prompt_id@version` — the LLM
> drafting-call provenance layer), D41/brainstorm 32 (the `prompts/<prompt_id>/
> v-<8hex>.md` LLM prompt registry, content-addressed versions, soft regression-fixture
> gate — explicitly scoped to *LLM instruction* prompts, not claim-rendering templates).
> All proposals below are *proposed* until the developer ratifies.

## Problem framing

Brainstorm 09 (O6) already answered *what* the canonical claim looks like — a fixed
per-kind S-expression template over node ids and normalized values, e.g.:

```
instance-exists(fi.rust.pattern-matching, status=present)
edge-polarity(edge.influences.algebraic-data-types.pattern-matching, +)
characteristic(fi.rust.pattern-matching, c-exhaustive, sha256-16=<hash of normalized sentence>)
```

D23 ratified that this canonical string is what gets SHA-256'd into the fact id, and
that hashing is **copyedit-tolerant** (NFC + trim + whitespace-collapse + lowercase +
punctuation-strip on free-text before hashing). What neither brainstorm nailed down —
and what this topic exists to fix — is the actual **rendering layer**: the artifact
that turns `instance-exists(fi.rust.pattern-matching, status=present)` into "Rust
implements pattern matching," where that artifact lives, how it version-changes without
breaking the identity guarantees D23 already promised, and whether the "sampling
parameters" question brainstorm 13 flagged even applies to it.

Three things need concrete design:

1. **The template catalog** — one canonical-claim-kind → English-rendering mapping per
   kind (O6 lists eight: `instance-field`, `instance-exists`, `characteristic`,
   `edge-exists`, `edge-polarity`, `quality-assessment`, `rule-exists`, `syntax-valid`).
   Where do these live, and in what format?
2. **Template change management** — a developer or agent edits a template's English
   wording. Three previously-conflated questions need separating: does the *fact id*
   change (D23 already answers: no, by construction — see below), does the *RAG
   embedding* go stale, and does the *D24 verifier* need to re-check anything.
3. **Sampling-parameter provenance** — is this even the template layer's problem? This
   requires first settling **where in the pipeline claim rendering actually happens**:
   as an LLM call at draft time (in which case sampling parameters are real and belong
   somewhere), or as deterministic code applied to already-decided structured data (in
   which case there is no sampling to have provenance over, and brainstorm 13's question
   resolves to "wrong layer," not "unanswered").

### The load-bearing fact this brainstorm turns on

O6 already states the design rule that resolves most of §2 before any options are
weighed: **"templates render *from* claims, claims never derive from renderings."** The
canonical claim — the hash input, the identity — is the S-expression over node ids and
normalized field values. It is fully determined the moment an agent (or human) commits
`since: "1.0"` or an edge's `polarity: "+"`. Nothing about *how that gets phrased in
English* is part of the claim. This means claim rendering is **pure, deterministic,
template-interpolation code** — a `printf`-shaped function from (kind, node ids,
normalized values) → string — run at build time, exactly like every other derived-fact
computation D23/brainstorm 09 already specifies. It is not, and structurally cannot be,
an LLM call: an LLM call would be sampling *from* a distribution over phrasings for the
same claim, which is precisely the non-determinism O6 built the S-expression layer to
avoid. This one observation answers problem-framing question 3 outright (see §3) and
substantially narrows §2's template-change-management options, because "does the
rendering change the claim" is already a closed question — it never can, by
construction — and the only genuinely open sub-questions are the two *consequences* of
a rendering-text change (RAG staleness, verifier staleness), not the identity question.

## Options with trade-offs

### O1 — Where the template catalog lives

**Option A — inline in build code** (a Python `TEMPLATES: dict[str, Callable]` module
inside the pipeline package). Cheapest to write, but invisible to the D1 "git is the
database, human-readable YAML" ethos this project applies to everything else that
governs claim semantics — a human expert who lands on a fact via the challenge link and
wants to understand *why* it reads the way it does has to go spelunking in application
source rather than reading a config file next to `ontology/schema/`. Also makes template
change-tracking (§2) indistinguishable from an ordinary code commit, losing the
content-hash-versioning discipline every other identity-adjacent artifact in this
project already has (D16 node ids, D23 fact ids, D41 prompt versions).

**Option B — fold into the existing `prompts/<prompt_id>/v-<hash>.md` registry** (D41).
Reuses machinery that already exists, but conflates two artifacts that are different in
kind: prompt-registry entries are **instructions sent to an LLM** to elicit judgment
(drafting, verification, debate) — genuinely non-deterministic, genuinely needing the
sampling-parameter/model provenance brainstorm 13 asks about. Claim-rendering templates
are **pure string interpolation with no model in the loop at all**. Filing them in the
same directory would misleadingly suggest every entry needs the same D26 `RunContext`/
cost-log/cache-key treatment prompts get, when claim templates need none of it (no
tokens, no cost, no cache — see §3). D41's own scope framing already drew this line
implicitly (`PromptRef` as "the only prompt-registry touchpoint," always describing an
LLM call), so folding claim templates in would be the first thing in that registry that
breaks its own stated contract.

**Option C (recommended) — a sibling registry, `ontology/claim-templates/<kind>.yaml`,
one file per O6 claim kind, versioned with the same content-hash pattern D41 already
validated (and D16/D23 validated before it) but as its own artifact family.** This sits
next to `ontology/schema/` and `ontology/taxonomy/` rather than inside `prompts/`,
because a claim-template catalog is closer in kind to the taxonomy/schema layer (it
governs what a claim *means* well enough to phrase it) than to the prompt layer (which
governs what an LLM is *asked to produce*). Reusing the content-hash-versioning pattern
(not a fourth scheme) means template changes get the same mechanical "did this change"
answer D41 already argued for prompts: no discipline to maintain, no silent in-place
edits invalidating downstream assumptions.

Concrete shape per file:

```yaml
# ontology/claim-templates/instance-exists.yaml
kind: instance-exists
claim_pattern: "instance-exists({instance_id}, status={status})"   # O6 grammar — frozen
render:
  present: "{language_name} implements {feature_name}."
  absent: "{language_name} does not implement {feature_name}."
  partial: "{language_name} partially implements {feature_name}."
version: v-3f8a21c0        # content hash of the `render:` block only (see O2)
```

`claim_pattern` is carried in the file for documentation/CI cross-check against O6's
grammar, but it is **not** independently versioned the way `render` is — see O2 for why
the two halves of this file need different change-management treatment.

### O2 — Template change management: splitting the file's two halves

A template file has two blocks with structurally different blast radii, and treating
them identically is the mistake to avoid:

- **`render:`** — the English wording. Editing it changes *how a claim of this kind
  displays*, never *which claim it is*. This is the axis the checklist's "re-render vs
  re-embed vs re-verify" question is actually about.
- **`claim_pattern:`** — the S-expression shape itself. Editing this changes *what
  information the claim kind asserts* — e.g. splitting `instance-exists` into a variant
  that also encodes a version, or adding a new status value. This is a schema-level
  change, not a wording change, and should never be handled by this topic's lightweight
  machinery — it is ontology-schema surgery and belongs to D16/D38's existing
  migration-manifest machinery (a `claim-schema` migration is structurally the same
  shape as an ontology-node migration: blast-radius script, `op` disposition, tombstone
  chain, RFC gate if it crosses a MAJOR-equivalent line). This brainstorm does not
  design a new migration format for `claim_pattern` changes — it names the reuse and
  moves on, exactly as D38 folded topic 28's `edition-superseded` tombstone into the
  existing ledger shape rather than inventing a parallel one.

For `render:` changes specifically (the actual scope of this topic), three axes:

**Re-render.** Always happens, always cheap, never optional. `rendered_text` is a
computed field (per D26's dataset-bundle `facts` table, which already ships
`rendered_text` as a precomputed build column) — it is recomputed on every build from
whatever `render:` block is current at build time. There is no "decide whether to
re-render" question: the moment `ontology/claim-templates/instance-exists.yaml` changes,
the next CI build produces different `rendered_text` for every fact of that kind, for
free, the same way changing `ontology/taxonomy/dimensions.yaml` changes every page that
reads it. **Recommendation: no gate needed here at all** — this is the one axis where
"always happens" is simply correct, not a policy choice.

**Re-embed.** This is where cost actually lives. The fact-RAG index (D7) embeds
`rendered_text` (among other fields) per fact; D35's embedding-cache-reuse check keys
reuse on a per-fact content hash, so a changed `rendered_text` is a legitimate cache
*miss* — correctly so, since the embedding should reflect what the text now says.
The blast radius of a `render:` edit is **every fact of that claim kind, corpus-wide**
— for high-frequency kinds like `instance-exists` (one per feature × language pair,
so already in the thousands once the sweep pipeline runs) this is a real batch-embed
cost, not a rounding error. **Recommendation:** treat a claim-template `render:` commit
exactly like brainstorm 27/D36's commit-triggered pipeline: it is not itself gated, but
it should emit a **blast-radius count** (reusing D38's blast-radius script, generalized
from ontology-node/source scope to also accept `--kind claim-template`, matching the
already-flagged "if topic 29's script ever broadens" interface note in D41 §2.8 — this
is exactly the broadening that note anticipated, and its stated requirement, reusing
`chat_run_id`/`source_id`/`run_id` join keys, is satisfied trivially here since claim
templates don't touch any of those) so the developer sees "this wording edit invalidates
embeddings for ~4,200 facts" *before* the next scheduled re-embed batch runs, rather than
discovering it as an unexplained cache-miss spike. No hard gate — re-embedding is
already a normal, budgeted, cache-driven cost per D26/D35; this just makes the number
visible ahead of time, mirroring how `report.py` (D41) surfaces other costs rather than
blocking on them.

**Re-verify.** This is the axis where the answer is genuinely "no, and here's the
mechanism that guarantees it." The D24 verifier's admissibility gate operates over the
**canonical claim's underlying assertion**, checked against source text via
entailment — for templated (non-free-text) claim kinds, what gets verified is
semantically "does the source support the fact that Rust has status=present for
pattern-matching," not "does the source support the exact English sentence 'Rust
implements pattern matching.'" Since a `render:` edit by construction never changes the
canonical claim (O6's frozen `claim_pattern`, unaffected by `render:` edits), the
underlying assertion the verifier already certified is untouched — **re-verification is
not warranted by a wording change alone**, and D25's event-driven re-verification
triggers (migrations, source-snapshot drift, challenge resolutions, verifier version
bumps, back-dating runs) correctly do not include "claim-template wording changed" as a
trigger; adding it would be D25 gaining a trigger for an event that never changes what's
being verified. The one caveat worth flagging as an open question (§4): for *free-text*
claim kinds (`characteristic`, `syntax-valid`, `rule-exists`'s `message`), the canonical
claim is a hash of the **authored sentence itself**, not a template-generated one — so
this whole O2 analysis is scoped to the five templated kinds (`instance-field`,
`instance-exists`, `edge-exists`, `edge-polarity`, `quality-assessment`'s scaffold text
if any), and doesn't apply to free-text kinds at all, since those have no shared
`render:` file to edit in the first place — an agent/human edits one sentence in one
record, which is already exactly D23's existing copyedit-tolerant-hashing case.

This three-way split — always re-render, blast-radius-surfaced re-embed, never
re-verify (for `render:` edits) — is the complete answer to the checklist's stated
question, and it falls out of O6's original design decision rather than requiring new
machinery: the reason "claims never derive from renderings" was worth stating in
brainstorm 09 is precisely that it makes this whole axis-splitting exercise trivial
instead of requiring a bespoke policy per axis.

### O3 — Sampling-parameter provenance: does it belong to this layer at all?

Brainstorm 13 surfaced this as: "D5 provenance records model + prompt version;
temperature/seed/sampling config arguably belong there too... decide where they live in
the fact provenance schema (touches topic 09)." The checklist folded it into topic 39
under the assumption that claim-statement rendering might be where sampling parameters
matter. §"the load-bearing fact" above already establishes that claim rendering is
**deterministic code with no model call in it whatsoever** — there is no sampling
distribution to have parameters over, because nothing is sampled. So the honest options
are:

**Option A — build a sampling-parameter provenance field into the claim-template
layer anyway**, on the theory that *some* claim kinds might someday be LLM-rendered
(e.g. a hypothetical natural-sounding paraphrase generator). Rejected: this would be
designing provenance for a call type this project has explicitly decided not to make —
O6's whole point was to take rendering *out* of LLM hands so identity stays stable; if a
future paraphrase-quality feature is ever wanted, it is a genuinely new, separately-
scoped capability (probably an LLM-authored `characteristic`-style free-text field with
its own `sources:`/`provenance:`, not a "fancier template"), not a retrofit onto the
deterministic-rendering design this brainstorm is confirming.

**Option B (recommended) — sampling parameters belong entirely to the D26
`RunContext`/D5 provenance layer, at the LLM call site that drafted the underlying
*claim data* (not its rendering), and nowhere else.** The place sampling parameters
actually matter is the **drafting call** — e.g. the sweep agent that decided
`since: "1.0"` or the quality-panel agent that wrote a `characteristic` sentence. That
call already has a `provenance:` block (brainstorm 09 §O4:
`proposer: { agent, model, prompt }`) sitting at record level. Extending it with the
sampling parameters actually used (temperature, seed if the university gateway
exposes one, top_p if non-default) is a small, well-scoped addition to that *existing*
block — not a new concept, not something this topic needs to invent, since D26 already
owns "what a call looked like" and D18 already logs every call's full parameters in the
transcript regardless. The gap brainstorm 13 correctly identified is narrow: the
transcript has the sampling parameters, but the **authored-record `provenance:` block**
(the human-readable summary living in the git-tracked YAML, per O4's "provenance
placement: per-record vs per-field") does not currently mirror them — it currently
stops at `{agent, model, prompt}`. **Recommendation:** add an optional
`sampling: {temperature, top_p, seed}` sub-block to O4's existing `provenance:` shape
(populated for LLM-drafted claims, always `null`/absent for the deterministic
`render:`/claim-template layer, since there is nothing to record there), defaulting to
omitted when the call used the pipeline's own defaults (temperature 0 for
extraction/verification per D26 §2.6) so the common case doesn't bloat every record —
only calls that deviated from defaults, or where the deviation itself might explain a
downstream dispute (a debate challenger arguing a proposer's non-zero-temperature draft
introduced avoidable variance), need the field populated at all.

```yaml
provenance:
  proposer: { agent: lang-sweep/rust, model: claude-sonnet-4-6, prompt: sweep-v3 }
  claim_origin: source-derived
  sampling: { temperature: 0.7 }   # optional; omitted when pipeline defaults were used
  debate_id: null
  chat_run_id: 2026-07-18-sweep-rust-003
```

This closes brainstorm 13's open question with a one-field schema addition to an
existing block, resolves the checklist's apparent premise (that sampling provenance is
part of *this* topic's design) as a category error worth stating explicitly rather than
silently dropping, and keeps the claim-template layer itself entirely free of any
provenance concept beyond its own content-hash version — because it has no model call to
attribute.

## Recommendation

*Proposed* package:

1. **Template catalog (O1c):** `ontology/claim-templates/<kind>.yaml`, one file per O6
   claim kind, each carrying a frozen `claim_pattern` (documentation/CI cross-check
   only) and a `render:` block (the actual English templates, keyed by the relevant
   discriminant — e.g. `status` for `instance-exists`) — a sibling registry to
   `ontology/schema/`/`ontology/taxonomy/`, distinct in kind and location from D41's
   `prompts/` LLM-instruction registry, but reusing D41/D23/D16's already-validated
   content-hash-versioning pattern (`version: v-<8hex>` over the `render:` block).
2. **Change management (O2):** the file's two blocks get different treatment.
   `claim_pattern` changes are ontology-schema-level surgery, routed through D16/D38's
   existing migration machinery (not designed further here). `render:` changes are
   **always re-rendered** (free, automatic, every build), **blast-radius-surfaced
   before re-embedding** (extending D38's blast-radius script to `--kind
   claim-template`, per D41 §2.8's already-anticipated broadening, so the developer
   sees the affected-fact count before a batch re-embed runs — no hard gate, cost
   already governed by D26/D35's existing cache-and-budget machinery), and **never
   trigger re-verification** (the D24 verifier certifies the underlying claim, which a
   wording-only edit never changes, per O6's "claims never derive from renderings"
   design rule — this scope is limited to the five templated claim kinds; free-text
   kinds already have their own copyedit-tolerant-hashing answer from D23).
3. **Sampling-parameter provenance (O3):** not a property of the template-rendering
   layer at all, because that layer makes no model call — it is pure deterministic
   interpolation over already-decided structured data. The actual gap is a small,
   optional `sampling: {temperature, top_p, seed}` sub-block added to brainstorm 09
   §O4's existing per-record `provenance:` schema, populated only for LLM-drafted
   claims that deviated from pipeline sampling defaults, mirroring the low-noise
   omit-when-default convention D26 already uses elsewhere (`cache_hit`,
   `tokens_if_uncached`). This resolves brainstorm 13's open question as a one-field
   schema addition rather than new machinery, and explicitly corrects the checklist's
   framing that conflated it with claim-template design.

## Open questions for the developer

1. **Blast-radius script broadening (O2)** — confirm extending D38's blast-radius
   script to accept `--kind claim-template` (surfacing an affected-fact count on a
   `render:` edit) as the right home for this, over a bespoke smaller script scoped
   only to claim templates? The broadening is cheap given D41 §2.8 already named the
   join-key contract such a broadening would need to honor, and claim templates
   trivially satisfy it (no `chat_run_id`/`source_id`/`run_id` involvement at all).
2. **Batch-embed cadence after a `render:` change** — does a claim-template wording
   edit's blast-radius count get folded into the existing scheduled re-embed cadence
   (whatever topic 25/D22's benchmark work settles on for the fact index specifically,
   still deferred per D27's "fact-index embedding-model decision deferred to
   sweep-pipeline start"), or does it warrant its own on-demand "re-embed now" trigger
   distinct from the routine cadence, given that stale search relevance for
   thousands of facts is a more visible failure mode than most embedding staleness?
3. **`sampling:` field population policy (O3)** — is "populate only when it deviates
   from pipeline defaults" the right sparseness rule, or would the developer prefer
   always populating it explicitly (verbose but literal) for every LLM-drafted claim,
   given that "was this drafted at a nonzero temperature" is exactly the kind of
   detail a future debate-instrumentation script (D30/D41 §2.6's verifier-replay
   counterfactual) might want to correlate against dispute rates?
4. **`quality-assessment` kind's templating scope** — O6 lists
   `quality-assessment(edge.hurts.ownership.learnability, a-2026-07-18-claude-1)` as a
   templated claim kind, but brainstorm 09's worked schema shows each `assessments:`
   entry carrying its own free-text `statement:` (agent-authored prose, not
   template-rendered). Does this kind actually belong in the five "templated" kinds
   this brainstorm's re-embed/re-verify analysis covers, or does it belong with the
   free-text kinds (whose canonical claim already hashes the authored sentence) —
   this brainstorm assumed the latter reading but O6's own claim-pattern example
   suggests the *existence and key* of an assessment is templated while its
   *statement* is free text, i.e. it may need a **split identity** (a templated
   existence-claim plus a free-text statement-claim) rather than fitting cleanly into
   either bucket as currently drafted.

## New brainstorm topics surfaced

No new backlog numbers. Everything this topic touches either resolves fully here (the
template catalog's location/format, the re-render/re-embed/re-verify split, the
sampling-parameter provenance placement) or hands off to machinery a prior topic already
owns and named for exactly this kind of broadening: `claim_pattern`-level schema changes
go through D16/D38's existing migration tooling (no new migration format invented here),
and the blast-radius-count mechanism for `render:` edits extends D38's script along the
broadening path D41 §2.8 already anticipated and scoped a join-key contract for. If the
open question 4 above (the `quality-assessment` split-identity question) turns out to
need real design work rather than a quick schema clarification, it should fold into
whichever future revision of brainstorm 09's schema work handles it, not become its own
numbered topic — it is a boundary-drawing question within an existing schema, not a new
subsystem.

## Sources

No new external sources introduced; all constraints trace to D16, D23, D24, D25, D26,
D38, D41 and their source brainstorms (09, 11, 12, 13, 22, 27–29, 32), and to the input
brief's fixed terminology conventions.
