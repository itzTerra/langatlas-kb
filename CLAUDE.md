# LangAtlas

Single source of context for this project (formerly working-titled "Hermes" — that name is
retired everywhere except historical brainstorm documents; D17). This file replaces the
original Notion page; the complete Notion content is preserved (restructured, nothing lost) in
[context/input-brief.md](context/input-brief.md).

## What LangAtlas is

A **sourced knowledge base mapping many programming languages onto a structured model of
programming-language concepts**, built incrementally by developer-managed AI agents and
correctable by human experts, with three surfaces:

1. **Knowledge base** — features of programming languages, their per-language realizations with
   syntax previews, quality impacts, and a typed graph of relationships (requires / enables /
   influences ± / conflicts-with / alternative-to / improves- and hurts-quality). Every
   user-facing fact links to a structured source record.
2. **Agent-facing RAG** — the same knowledge exposed to AI agents (Claude Code via MCP, other
   providers via a thin API) so agents can argue about the topic and grow the corpus with new
   sourced facts — a self-backing net of information.
3. **Public website** — SEO-focused, for human eyes (not an AI information source), clean
   typography-first design ("opposite of Amazon"), with a per-fact citation and an easy
   "challenge this fact" path for human experts who know better than the agents.

Later modules (explicitly deferred): a PC-part-picker-style **Language Builder** + public library
of built languages, and a **Language Selector** recommending a workforce-popular language per
domain. Explicitly unrealistic/out of scope: auto language standards, auto compilers, automatic
language-to-language translators.

### Terminology (fixed vocabulary — use consistently)

- **concept** — any idea or principle, often (not necessarily) grounded in theory
- **feature** — a realisation of a concept within a family of related systems (here: programming
  languages)
- **feature instance** — a realisation of a feature in a specific system (a particular language)
- **characteristic** — an observable property of a system or feature instance

## Developer constraints (bind every design choice)

Solo developer; proof-of-concept MVP. Resources: Claude Code Pro (session/usage limits), no GPU
for local inference, a fairly slow university-hosted model API. Every user-facing fact needs a
source with a structured, modern bibliographic identity. The RAG system must connect to Claude
Code and ideally other/local providers. Facts must be trivially challengeable by human experts.
Favor boring, solo-maintainable technology.

## Architecture direction (ratified 2026-07-18 — details in context/decisions.md)

**LangAtlas is a build pipeline, not an online application.** The canonical store is a public git
repo of human-readable YAML files (facts, features, instances, edges, rules, and
CSL-JSON-vocabulary source records); the knowledge-base repo and the website repo are separate.
Postgres (+ pgvector/FTS, via docker compose), the read-only stdio MCP server, and the fully
static Astro site are all one-way derived build artifacts. **Agents commit facts directly — no
PR gate**: admissibility comes from the automated source-verification gate, controversial facts
are auto-flagged, and every agent chat is logged (facts optionally link to the chat that
produced them). Human experts correct the record via prefilled GitHub issues; git history is
the public audit trail. Agent-generated text is never itself citable. Claude does judgment
work; the university API does volume (it also hosts embedding/reranker models); neither crosses
into the other's lane. English-only; code MIT, corpus CC BY-SA 4.0 (final).

**Scoping: no artificial MVP slice.** A heavy frontloaded research phase — broad-knowledge
agents + internet sources designing the generic language-feature landscape — comes first,
completely separate from the per-language sweep pipeline, which is retained for onboarding new
languages later. Personal hobby project: no deadline, full Claude Pro + reasonable academic API
budget, no shortcuts that damage the long-term product.

Round-2 decisions (D13–D22 in decisions.md, ratified): CI via a validated dataset bundle
published as release assets — the site never reads raw KB files (repos: `langatlas-kb`,
`langatlas-site`, `langatlas-transcripts`); a second full-text **source-corpus RAG index**
(books/specs, locator-carrying chunks, initial corpus in `~/Downloads/hermes-research/` + specs
of the initial languages — tentatively TIOBE top 10, topic 34) feeding both the research phase
and the verifier; ontology versioning with immutable node ids vs renameable slugs,
blast-radius semver, migrations-as-scripts (ontology MAJORs are the one human-gated
exception); DCO for contributions; all agent chats captured to a public transcripts repo with
fact→chat links; positioning wedge = typed concept graph first, per-fact sourcing second (D19);
fact granularity = per-instance records with derived per-field fact IDs (D20); controversy as
an agent-assessed ordinal score with GitHub-challenge activity kept separate (D21).

## Context directory map

| File | Contents |
|---|---|
| [context/input-brief.md](context/input-brief.md) | Complete original Notion content + developer constraints — the requirements source of truth |
| [context/decisions.md](context/decisions.md) | Ratified decisions D1–D22 + top risks, with pointers to full analyses |
| [context/open-questions.md](context/open-questions.md) | Remaining open questions and developer actions |
| [context/brainstorm-checklist.md](context/brainstorm-checklist.md) | Living list of brainstorm topics: rounds 1–2 done, backlog 09–34 pending |
| [context/brainstorms/](context/brainstorms/) | Full brainstorm deep-dives, rounds 1 (01–08) and 2 (10, 15, 21–24); historical — they predate the rename and still say "Hermes" |

Workflow for these docs: answered questions move from open-questions.md into decisions.md with
their answer; new big topics go onto the checklist backlog and get their own brainstorm file;
this file stays the stable entry point.

**After every brainstorm run** (one or more topics dispatched to a subagent), before reporting
back to the user: reflect each brainstorm's recommendation into
[context/decisions.md](context/decisions.md) as a *proposed* decision (per the decision-hygiene
convention below — not ratified until the developer says so), and file its open questions in
[context/open-questions.md](context/open-questions.md). Any non-obvious ratification made in the
same turn (the developer accepting a recommendation without a full separate review pass) also
gets recorded in decisions.md as ratified, so the developer always has a decisions.md/
open-questions.md diff to review after a brainstorm run, not just the raw brainstorm file.
File open questions **one numbered list item per discrete question**, not grouped/summarized
into a single bullet per brainstorm and not left as plain unnumbered bullets — matches the
`## Developer actions` convention already in open-questions.md and lets the developer refer to
or check off each question by number.

## Conventions for all project .md files

- **Citations**: author-year in prose — e.g. Jordan et al. (2015); Van Roy & Haridi (2003) —
  with full references (URL/DOI included) in a Sources section at file bottom when a file
  introduces new sources. The website will render numeric citations from CSL records; that is a
  build concern, not a docs concern.
- **Cross-references**: relative markdown links to files; brainstorms referenced by number
  ("see brainstorm 04").
- **Decision hygiene**: proposals are marked *proposed* until the developer ratifies; ratified
  decisions are binding and edited in place with a dated note if changed.
- **People terminology**: never "owner" — use **developer** (the person operating the pipeline
  and making project decisions) or **contributor** (anyone participating); the project is
  designed for multiple people.
- Checkbox plans use `[ ]`/`[x]`; check items off immediately when completed.

## Sources (from the original Notion page)

- Jordan, H., et al. (2015). Feature model of programming languages — PDF attached on the
  original Notion page (`feature-model.pdf`); quoted excerpts preserved in the input brief.
- Van Roy, P., & Haridi, S. (2003). *Concepts, Techniques, and Models of Computer Programming.*
  MIT Press. https://webperso.info.ucl.ac.be/~pvr/VanRoyHaridi2003-book.pdf
- Sammet, J. (1981 lineage, via Jordan et al.): "the simple presence of features is not a good
  indication of the worth of a language." https://onlinelibrary.wiley.com/doi/10.1002/spe.4380110102
- PLDB — http://pldb.info/ · Hyperpolyglot — https://hyperpolyglot.org/ ·
  Wikidata programming language entity — https://www.wikidata.org/wiki/Q2005 ·
  Language influence network — https://programminglanguages.info/influence-network/
- AI language comparisons — https://lang-compare.zander.wtf/ · https://programming-languages.com/
- DSL generators — https://spoofax.dev/ · https://eclipse.dev/Xtext/
