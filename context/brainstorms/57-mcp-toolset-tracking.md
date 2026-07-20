# 57 — MCP Tool-Set Extension Tracking

> Backlog brainstorm for LangAtlas. Scope (checklist item 57): a standing consolidation of every
> proposed addition to D8's original five-tool read-only public MCP set, and every tool
> deliberately kept off that public MCP, so future brainstorms append a row here instead of
> re-deriving D8's public/pipeline-only boundary from scratch. Binding context: D8 (provider
> connectivity — the original tool set, read-only amendment), D15 (full-source RAG —
> `search_sources`/`get_source_section`, pipeline-only), D18 (chat logging — the proposed v2
> `search_debate_history`, pipeline-only), D35 (dataset bundle contract — the MCP caution
> contract every public tool response must carry), D38 (ontology change tooling — tombstone-chain
> response-shape extensions to existing public tools), D41 (absence & unknown semantics — the
> `no-record` envelope extension to existing public tools), D45 (contradiction-register lifecycle
> — `list_contradictions`/`get_contradiction`, ratified as a public-set addition), D53
> (finding-aid tooling — `search_finding_aids`, pipeline-only). This is explicitly a
> **consolidation task, not new design**: nothing below invents mechanism the source brainstorms
> didn't already propose. Per the project's decision-hygiene convention, tool statuses below
> reflect exactly what decisions.md already records as ratified/proposed — this file adds no new
> ratifications of its own.

## Problem framing

D8 drew one clean boundary at the project's first pass: a read-only, five-tool stdio MCP server
(`search_knowledge`, `get_fact`, `get_feature`, `get_neighbors`, `get_source`) for Claude Code and
MCP-speaking local models, serving verified, citable fact content only. Every brainstorm since that
has needed a new agent-facing tool has had to re-derive, from context, whether its tool belongs on
that public surface or not — and three brainstorms in a row (15, 37, 45) independently arrived at
the same underlying test ("does this tool return content an agent could mistake for a citable,
verified fact?") without ever writing the test down in one place. Brainstorm 37 named the problem
explicitly in its own "New brainstorm topics surfaced" section: worth a standing note "rather than
letting each brainstorm that needs a new tool re-derive D8's boundary from scratch." This document
is that standing note.

Two things make this worth a dedicated (if lightweight) file rather than a decisions.md footnote:

1. **The list is already inconsistent across documents.** Brainstorm 37's own text still describes
   `list_contradictions`/`get_contradiction` as "proposed, not fully specified" — accurate at the
   time it was written, but D45's ratification (recorded later in the same batch) confirmed they
   ship now, as part of topic 37's implementation, not deferred to "whichever future pass
   concretizes D8's extension list." A reader skimming brainstorm 37 alone would get the status
   wrong. A single source of truth for *current* status avoids this drift.
2. **The public/pipeline-only line is not obvious from a tool's name alone.** `search_sources` and
   `search_knowledge` sound similar; one is pipeline-only raw evidence, the other is the public
   verified-fact index. Writing the boundary logic down once, with worked examples, is cheaper than
   four brainstorms each re-explaining why their new tool falls on one side or the other.

## The boundary logic (consolidated from D8, D15, D29, D45, D53)

A tool belongs on the **public** MCP if and only if every object it can return is either:

- an **admitted, verified fact** carrying D35's mandatory `caution` block (status/confidence/
  verification/dispute/note), or
- **read-only KB structure** (feature/instance/edge/source records, graph neighbors) that is
  itself build-derived and citable by construction.

A tool is **pipeline-only** (never registered on the public MCP) if any of its possible outputs are:

- **raw, pre-verification evidence** — full-source RAG chunks that feed drafting but have not
  themselves cleared the D24 verification gate (D15's rationale: these are inputs to facts, not
  facts);
- **structurally non-citable by policy**, regardless of verification state — finding-aid results
  (D29: PLDB/Wikidata/Hyperpolyglot/Wikipedia are corroboration/leads only, never sole backing) and
  agent chat transcripts (D4: "agent-generated text is never itself citable");
- content whose exposure would let an external MCP-speaking agent construct a claim that *looks*
  sourced but isn't — the load-bearing risk (K1, citation laundering) that D4/D15/D29/D53 each cite
  as their reason for keeping the tool off the public surface.

This is the same test D15, D37/D45, and D45/D53 each applied independently; writing it down once is
this document's main substantive contribution.

## Table 1 — Public read-only MCP tool set

| Tool | Origin | Status | Notes |
|---|---|---|---|
| `search_knowledge` | D8 | Ratified, original v0 set | Hybrid search over the fact index; relevance stays the primary sort key (D35) — confidence/controversy are per-result annotations, never a re-ranking signal |
| `get_fact` | D8 | Ratified, original v0 set | Extended by D35 (mandatory `caution` block on every response), D38 (dead-id tombstone-chain resolution, inlines successor content), D45 (on a `dispute: contradicted` fact, inlines the conflicting participant fact(s) in full, each with its own `caution` block), D41 (the `no-record` envelope for `not-yet-swept`/`not-yet-onboarded`/`deferred`/`not-applicable` states) |
| `get_feature` | D8 | Ratified, original v0 set | Same D38/D41 response-shape extensions as `get_fact`; on a split's old node id, returns the hub page's real content directly (not the dead-reference envelope) per D38's ratification |
| `get_neighbors` | D8 | Ratified, original v0 set | Same D38/D41 extensions; never synthesizes an absence conclusion from a missing hit (D41) |
| `get_source` | D8 | Ratified, original v0 set | Auto-walks multi-hop edition-supersession chains transparently (D38) |
| `list_contradictions(status?, type?)` | Brainstorm 37, ratified by D45 | **Ratified — ships as part of topic 37's implementation**, not deferred | Returns open (and optionally closed) contradiction records with participant fact ids |
| `get_contradiction(ctr_id)` | Brainstorm 37, ratified by D45 | **Ratified — ships as part of topic 37's implementation**, not deferred | Returns the full record with both participants inlined, mirroring `get_fact`'s inlining shape |

**Response-shape extensions to existing tools (not new tools, listed for completeness):** D35's
`caution` block (universal), D38's tombstone-chain resolution object, D41's `no-record` envelope
(extended by D50 with a `not-applicable` reason), D45's contradicted-fact inlining. None of these
add a tool name to the table above; they modify what the existing five (now seven) can return.

**Deployment-mode note:** D35 proposes an optional "MCP lite mode" (SQLite-direct, no Postgres,
`retrieval_mode: lexical-fallback` flagged) as a documented future accessibility option — explicitly
**not built in v0** per the developer's ratification. This is a serving-mode variant of the existing
tool set, not a tool-set addition, so it isn't a table row.

## Table 2 — Tools deliberately kept off the public MCP (pipeline/research-only)

| Tool | Origin | Status | Why it's pipeline-only |
|---|---|---|---|
| `search_sources` | D15 (brainstorm 21) | Ratified | Returns full-source RAG chunks — pre-verification evidence with locators, feeding drafting and the D24 verifier; not itself a verified fact |
| `get_source_section` | D15 (brainstorm 21) | Ratified | Same rationale as `search_sources` — small-to-big chunk expansion over raw source text |
| `search_finding_aids` | D53 (brainstorm 45) | Ratified | Structurally non-citable by D29 policy (PLDB/Wikidata/Hyperpolyglot/Wikipedia are leads, never sole backing); enforced via a typed `FindingAidResult` envelope the fact schema has no slot for. Available to every agent session type per D53's ratification (not scoped only to R3/D5) |
| `search_debate_history` | D18 (brainstorm 24) | **Proposed, not yet built** — named as a "v2" item in D18, no implementation decision recorded since | Chat transcripts are agent-generated text, never itself citable (D4); a `chat_chunks` pgvector index is the proposed backing store, with a mandatory NON-CITABLE banner on results |

**Why these stay off the public surface, consolidated:** D8's original read-only amendment already
drew "the write path is the agent pipeline only"; these four tools extend that same separation one
step further — they expose pipeline-internal *inputs* (raw source text, non-authoritative
third-party leads, chat transcripts) that a public MCP consumer (an external Claude Code session, a
non-project agent) could otherwise mistake for, or launder into, a verified fact. Keeping them
pipeline-only is what lets the public tool set make a hard guarantee (every returned object is
either an admitted fact or citable KB structure) without a disclaimer-by-tool exception list.

## Recommendation

1. **This file is the single source of truth for current MCP tool-set status.** When decisions.md
   records a ratification or amendment touching a tool listed here (as D45 did for
   `list_contradictions`/`get_contradiction`, correcting brainstorm 37's own "proposed, not fully
   specified" language), update the relevant table row's Status column in the same pass — don't
   leave the status only inside the originating brainstorm file, which is not re-read as part of
   normal workflow (per the existing convention already governing brainstorm-checklist.md and
   open-questions.md updates).
2. **Any future brainstorm that proposes a new agent-facing tool should append one row to the
   appropriate table here, not re-derive the boundary test.** Concretely: state which table the
   tool belongs in using the boundary logic above, add the row with `Status: proposed`, and note
   which brainstorm/topic number owns the full design. When the developer ratifies (or the
   proposal lands as part of a broader topic's implementation, as D45 did), flip the status in
   place — mirroring exactly how this file's own two ratified-but-still-tabled rows
   (`search_debate_history`, and previously `list_contradictions`/`get_contradiction` before D45)
   are meant to be maintained.
3. **No new tooling or process infrastructure is proposed for this maintenance** — it is a manual
   markdown-editing discipline, the same weight as the brainstorm-checklist.md upkeep CLAUDE.md
   already documents, not a validator-enforced check. Given the tool count (seven public, three
   pipeline-only, one still-proposed) and the low rate of new-tool proposals historically (roughly
   one every several brainstorm batches), a manual convention is proportionate; revisit only if the
   list grows enough that manual upkeep starts silently drifting the way brainstorm 37's own text
   already has once.

## Open questions for the developer

1. **`search_debate_history` design timing** — is v2's `search_debate_history` (D18) worth a
   dedicated brainstorm now that D15/D45/D53 have each worked through a very similar
   non-citability-enforcement pattern (typed envelope, tool-description caveat, D31 data-not-
   instructions treatment), or does it stay parked until the transcripts repo (D18) has enough
   real volume to make the design concrete rather than speculative?
2. **Maintenance ownership going forward** — is a manual per-brainstorm-append convention
   (recommendation 2 above) sufficient, or would the developer prefer this file's tables regenerated
   mechanically from decisions.md at some point (e.g. a small script grepping tool names out of
   ratified decisions), given the project's general preference for structural drift-prevention over
   procedural discipline (D46 and D48 both made exactly this trade-off for other artifacts)?

## New brainstorm topics surfaced

None. This is a consolidation pass; the survey did not turn up a design gap needing its own future
brainstorm beyond the already-flagged, already-tracked `search_debate_history` design (open question
1 above, which stays a note on this file rather than a new backlog line — it was already implicit
in D18's own "v2" framing, not a new discovery of this pass).
