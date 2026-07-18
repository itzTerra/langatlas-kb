# 34 — Initial Language Selection

> Backlog brainstorm for LangAtlas. Scope: analyze the TIOBE top 10 as the tentative initial
> language set (D15 amendment), and propose the final initial list + phased onboarding order.
> Feeds the research phase (topic 25) and the D15 source-corpus ingestion list. Binding context:
> `context/decisions.md` (esp. D10 Shiki highlighting, D11 research phase, D14 licensing, D15
> source corpus), `context/input-brief.md` (feature model layers/dimensions), brainstorms 01, 06,
> 21. All proposals here are *proposed* until the developer ratifies.

## Problem framing

D15 tentatively sets the initially supported languages to "the top 10 of the TIOBE index" and
defers the real selection analysis here. The initial set does three jobs at once:

1. **Feature-landscape coverage (primary).** The D11 research phase designs the *generic*
   feature landscape — layers, dimensions, features — and per D19 the typed concept graph is
   the positioning wedge. An ontology designed only against imperative/OOP languages will bake
   in blind spots (K2 ontology-instability risk): dimensions like evaluation strategy, effects,
   macros, and half the concurrency-model vocabulary have no interesting values in the TIOBE
   top 10 alone. The set must contain the languages whose features *stress* the model, not just
   the popular ones.
2. **D15 corpus ingestion list.** Each language contributes its official spec/reference
   chapters to the private source-corpus index. That requires a spec that (a) exists in decent
   quality, (b) can lawfully enter the private pipeline (per D14 the EU TDM exceptions bless
   private snapshot/index ingestion regardless of license, and the university API carries no
   ToS restriction — so license mainly governs *acquisition* and later *quotation*, not
   indexing), and (c) has locator-friendly structure (numbered clauses/anchors, per 21 §2.3).
3. **Audience relevance.** The public site targets "does X have Y"-class queries (06 §C); the
   workforce-popular languages are where the search volume is. TIOBE is the ratified
   *popularity* proxy — but per D14 rule 7, TIOBE data itself enters only as single attributed
   data points, never bulk.

The tension: jobs 2–3 pull toward popular languages; job 1 pulls toward paradigm diversity.

**The actual TIOBE top 10 (July 2026):** Python, C, C++, Java, C#, JavaScript, Visual Basic,
SQL, R, Rust — with Rust entering the top 10 for the first time (TIOBE 2026; TechRepublic
2026). Notable for planning: **Go (#13) and Swift (#15) are *not* in the top 10**, while
Visual Basic (#7) and SQL (#8) are.

Paradigm audit of that ten against the brief's layer-3 dimensions:

- **Paradigm:** imperative/OOP ×8, R is the only functional-leaning member (lazy promise
  evaluation of arguments, first-class functions, copy-on-modify), SQL the only declarative
  one. **No pure/lazy functional, no ML-family, no logic, no Lisp, no array language.**
- **Evaluation strategy:** everything is strict except R's argument promises. Lazy (call-by-need)
  is unrepresented by its canonical carrier.
- **Memory management:** tracing GC ×7, manual (C/C++), ownership (Rust). **ARC unrepresented**
  (Swift is the industrial carrier); regions likewise (Rust lifetimes partially; Cyclone/Vale
  are research-tier).
- **Concurrency model:** threads + async/await are saturated; Go's CSP/goroutines, the actor
  model (Erlang/Elixir/Akka), STM (Haskell/Clojure), and dataflow concurrency (Oz — already
  sourced via Van Roy & Haridi 2003 in the D15 corpus) are absent.
- **Typing:** static-nominal and dynamic are covered; **structural** (Go interfaces, OCaml
  objects, TypeScript), **gradual** (TypeScript, Python-with-mypy partially), **dependent /
  linear / affine** (Idris/Agda/ATS; Rust approximates affine) are thin or absent.
- **Effects / purity:** no pure language, no algebraic-effects carrier (Haskell monadic
  effects; OCaml 5 effect handlers — the brief lists effect handlers explicitly).
- **Modules:** files/namespaces/packages are saturated; **functors** (OCaml/SML) absent;
  traits/mixins partially via Rust/Scala/Ruby.
- **Macros:** textual (C preprocessor) and AST/hygienic-ish (Rust `macro_rules!`) present;
  full hygienic homoiconic macros (Scheme/Racket/Clojure/Elixir) absent.
- **Polymorphism:** subtyping + parametric covered; **type classes** (ad-hoc done right —
  Haskell) and row polymorphism absent.
- **Dispatch:** single dispatch everywhere; multiple dispatch (Julia, CLOS) absent; R's S4
  actually provides a multiple-dispatch data point inside the top 10.

So the TIOBE ten covers the mainstream plateau densely and the rest of the landscape almost
not at all — as expected for a popularity index. Two members are also *qualitatively*
awkward: **SQL** is a domain-specific declarative query language for which most layer-2/3
dimensions (memory management, concurrency model, parameter passing, module systems…) are
inapplicable or apply only to vendor procedural dialects, and its spec (ISO/IEC 9075) is
paywalled with no freely published drafts; **Visual Basic** is a frozen, C#-equivalent
language on the same runtime (Microsoft stopped evolving the language beyond stability) whose
unique feature contribution is nearly nil.

### Per-candidate assessment (spec, license, Shiki, unique contribution, cost)

Shiki note first: the current `tm-grammars` bundle redistributed by Shiki carries 260
grammars, including every language named in this document — `python`, `c`, `cpp`, `java`,
`csharp`, `javascript`, `vb`, `sql`, `r`, `rust`, `haskell`, `ocaml`, `prolog`, `erlang`,
`elixir`, `go`, `swift`, `scheme`, `racket`, `clojure`, `apl`, `julia`, `smalltalk`,
`typescript`, `matlab`, `ada`, `fortran-free-form` (Shiki 2026). **Syntax highlighting is not
a constraint on this selection.** (D10's Shiki-gap concern only bites for research-tier
languages like Oz, BQN, or K — none proposed for onboarding.)

Cost model used below: **ingestion cost** = spec acquisition + extraction + the 0.5–2 h QA
per book-class source (D15), scaling with page count and PDF vs HTML; **sweep cost** = size
of the feature surface the per-language sweep (D5) must cover, scaling with language size and
with how implementation-oriented (vs reader-oriented) the spec prose is.

| Language | Primary spec/reference | License / access | Ingestion | Sweep | Unique contribution to the landscape |
|---|---|---|---|---|---|
| Python | The Python Language Reference | PSF-2.0; free HTML, anchor-rich (PSF 2026) | Low | Medium | Duck typing, descriptors/metaclasses (first-class classes, metaclass — brief layer 2), generators/coroutines, GIL-removal-era threading, gradual typing via annotations |
| C | ISO/IEC 9899:2024; free working draft N3220 (open-std) | ISO copyright; draft publicly posted, private TDM per D14 | Low–Med (PDF) | Medium | Baseline procedural language; manual memory; textual macros (preprocessor); UB as a concept |
| C++ | ISO/IEC 14882; free final working draft N4950 (open-std) | ISO copyright; draft publicly posted (ISO C++ 2023) | **High** (~2000 pp PDF) | **High** (largest feature surface of any candidate) | Templates (compile-time metaprogramming), RAII, multiple inheritance, value/reference semantics spectrum, overloading/ad-hoc polymorphism |
| Java | Java Language Specification (SE 25) | Free to read; restrictive Oracle spec license — no redistribution; private indexing OK per D14 TDM, quotes under the ~50-word cap (Oracle 2026) | Medium (~800 pp, clean HTML) | Medium–High | Canonical class-based nominal OOP, checked exceptions (the *only* carrier in any proposed set), JMM as a memory-model exemplar, virtual threads |
| C# | ECMA-334 (6th ed., free PDF); working drafts on Microsoft Learn (CC BY 4.0) | Ecma free download; Microsoft docs CC BY 4.0 (Ecma 2026; Microsoft 2026) | Medium | Medium–High | Properties/events, LINQ (embedded query comprehension), async/await (origin), reified generics, `dynamic` gradual escape hatch |
| JavaScript | ECMA-262 (2026 ed.) | Ecma permissive copyright — "may be copied … without restriction" (Ecma 2026a) | Medium (huge, but HTML with numbered clauses — ideal locators per 21 §2.3) | High (spec is written for implementers; fact-mining leans on it being algorithmic, not descriptive — MDN is CC BY-SA and per D14 rule 5 a finding aid/corroboration only) | Prototype-based OOP (only carrier), event-loop concurrency, closures-in-the-mainstream, gradual-typing ecosystem context (TS) |
| Visual Basic | VB Language Specification (VB 11, frozen) on Microsoft Learn | CC BY 4.0 (Microsoft 2026) | Low | Low | Almost none beyond C# (same CLR, same semantics; `On Error`, XML literals, `Module`) — its value is SEO/completeness, not landscape |
| SQL | ISO/IEC 9075 | **Paywalled, no free drafts** (ISO 2023); vendor docs (PostgreSQL, BSD-ish) document dialects, not the standard | Medium + purchase | Awkward — most dimensions inapplicable | Declarative/relational paradigm, 3-valued logic; but it stresses the ontology as a DSL, not as a general-purpose language |
| R | R Language Definition (CRAN manual) | Free; permissive verbatim-and-modified copying notice (R Core Team 2026) | Low | Medium | Lazy argument promises, copy-on-modify value semantics, S3/S4 — including **multiple dispatch**, first-class environments, computing-on-the-language metaprogramming |
| Rust | The Rust Reference + Ferrocene Language Specification | MIT OR Apache-2.0, free (Rust Project 2026) | Low–Med | High (large surface) | Ownership/borrowing (affine-flavored typing), traits, hygienic-ish declarative + procedural macros, fearless-concurrency story, `unsafe` boundary |

Gap-filling candidates (not in the top 10):

| Language | Spec/reference | License | Unique contribution |
|---|---|---|---|
| **Haskell** | Haskell 2010 Language Report + GHC User's Guide | Report: permissive community license (copy/distribute freely; SPDX `HaskellReport`) (Marlow 2010); GHC guide BSD | Lazy evaluation (call-by-need) canonical carrier, purity, monadic effects/IO, type classes (ad-hoc polymorphism done principled), ADTs + exhaustive pattern matching origin-adjacent, STM, GADTs/type-level extensions |
| **OCaml** | The OCaml Manual (incl. language spec chapters) | **CC BY-SA 4.0** since 5.x (INRIA 2026) | ML module system with **functors**, eager typed FP, structural object system + row-flavored typing, **effect handlers** (OCaml 5 — the brief's "effects: algebraic" dimension in an industrial language), multicore runtime |
| **Prolog** | ISO/IEC 13211-1 (**paywalled**); complements: Deransart et al. (1996) via university access; SWI-Prolog reference manual (BSD-2-Clause distribution) | ISO paywalled — D15's university-acquisition path; SWI docs free | The **logic paradigm**: unification, backtracking, resolution, homoiconicity (clauses as terms), constraint extensions — the brief's paradigm triad (functional/OOP/logic) is unfillable without it |
| **Erlang** | Erlang/OTP Reference Manual + System Documentation | Apache 2.0 (Ericsson 2026) | **Actor model** / share-nothing green processes, supervision trees ("let it crash"), hot code loading, per-process GC — the concurrency-model dimension's most distinct value |
| **Go** | The Go Programming Language Specification | CC BY 4.0; code samples BSD (Go Project 2026) | **CSP** (goroutines + channels), **structural interfaces**, defer, minimal-feature design philosophy (a useful *negative* data point: features absent on purpose), TIOBE #13 so audience-relevant anyway |
| **Swift** | The Swift Programming Language (TSPL) + Swift book repo | Apache 2.0 (Apple 2026) | **ARC** (the missing memory-management value), protocols with default implementations + retroactive conformance, value-type-first design, typed `throws`, structured concurrency with actors |
| Scheme (R7RS) | R7RS-small report | Freely distributed report | Hygienic macros, first-class continuations (`call/cc`), TCO-guaranteed, homoiconicity |
| TypeScript | No current normative spec (old spec archived); Handbook (docs) | Docs freely licensed; **no spec is a real sourcing problem** | Gradual + structural typing at industrial scale, conditional/mapped types |
| APL (array family) | ISO 8485 (dated/withdrawn-era); Dyalog documentation (proprietary, freely downloadable) | Weak spec situation | Array-oriented paradigm, rank polymorphism, tacit programming |
| Elixir | Elixir docs (Apache 2.0) | Free | Hygienic macros on the BEAM, protocols; semantics largely = Erlang's |

One more corpus note: **Oz** is already fully sourced — Van Roy & Haridi (2003) is in the D15
initial corpus — so dataflow concurrency, active objects, and the kernel-language method can
back *concept/feature-level* facts during the research phase without onboarding Oz as a KB
language (no sweep, no instances). Same applies to Coq/Rocq via Software Foundations for
dependent-type concepts.

## Options with trade-offs

### Option A — TIOBE top 10 verbatim

Take the D15 tentative list literally: Python, C, C++, Java, C#, JavaScript, Visual Basic,
SQL, R, Rust.

- Pros: zero selection argument to defend ("we cover the TIOBE top 10" is self-explanatory
  positioning); maximal aggregate search volume; every spec except SQL's is freely obtainable.
- Cons: catastrophic for job 1 — the research phase would design the ontology against eight
  imperative/OOP languages, one statistical language, and one DSL. Lazy evaluation, logic
  programming, functors, actors, CSP, ARC, effect handlers, type classes would all enter the
  landscape purely from book knowledge with no language instances to validate against —
  exactly the K2 blind-spot scenario the frontloaded research phase exists to avoid. Pays SQL's
  paywall + ontology-mismatch cost and VB's near-zero-contribution cost.

### Option B — TIOBE top 10 + paradigm completers (union, ~14–16)

Keep all ten, add Haskell, OCaml, Prolog, Erlang, Go, Swift.

- Pros: both jobs fully served; no "why did you drop a top-10 language" conversation.
- Cons: 16 languages is the largest sweep and ingestion bill on the table; SQL still stresses
  the ontology and still has no free spec; VB still contributes ~nothing while consuming a
  sweep. The marginal cost is spent on the two weakest members.

### Option C — curated set: TIOBE core minus poor fits, plus paradigm completers (~14) — *proposed*

Drop **SQL** (deferred, not rejected: revisit once the ontology has a story for
non-general-purpose languages) and demote **Visual Basic** to a cheap last-phase add. Keep the
other eight; add the six gap-fillers.

- Pros: every remaining language earns its place on at least one job; the paradigm audit's
  gaps all close (lazy/pure FP → Haskell; ML modules + effect handlers → OCaml; logic →
  Prolog; actors → Erlang; CSP + structural typing → Go; ARC → Swift); total stays within the
  task's ~10–14 envelope for the core set; the two D15 paywall problems (SQL) and dead-weight
  sweeps (VB early) disappear from the critical path.
- Cons: "TIOBE top 10" stops being literally true — positioning copy must say "the most
  popular languages plus the languages that define the feature landscape" (arguably a
  *better* story for D19's typed-graph wedge); SQL has real search volume that is forgone for
  now; two languages (Prolog partially, Java) have restrictive spec licenses — both are
  handled by the D14 TDM position, but Prolog additionally needs an acquisition step
  (university purchase/access for ISO 13211-1 or Deransart et al. 1996) before its tier-A
  backing exists.

### Option D — minimal diverse set (~8), popularity be damned

Python, C, Java, JavaScript, Rust, Haskell, Prolog, Erlang.

- Pros: cheapest path to a landscape-validating ontology.
- Cons: violates the D11 no-artificial-slice posture in spirit — C++/C#/R/Go/Swift/OCaml would
  need onboarding almost immediately anyway; forfeits the popularity positioning entirely.

### Onboarding-order logic (applies to whichever set is ratified)

Order is driven by what the **research phase** needs early, not by rank: the ontology should
meet its hardest counterexamples first (K2), and the D15 ingestion of each spec must precede
that language's sweep. Two orderings considered:

1. **Popularity order** — simple, SEO-aligned; but the ontology meets Haskell/Prolog last,
   guaranteeing late MAJOR-class ontology churn (D16) after thousands of facts exist. Rejected.
2. **Diversity-first phases** (*proposed*) — each phase is a maximally-spread slice, so every
   paradigm the model must express is instantiated before mass fact production begins, and the
   most expensive ingestions (C++, ECMA-262) land after the pipeline is proven on cheap,
   well-structured specs.

## Recommendation

*Proposed* (developer ratifies; this amends the "tentatively TIOBE top 10" clause of D15):

**Initial language set = 14 core languages** — the July 2026 TIOBE top 10 minus SQL and
Visual Basic, plus Haskell, OCaml, Prolog, Erlang, Go, Swift — onboarded in four phases, with
VB as an optional fifth-phase add:

- **Phase 1 — ontology stress set (6): Python, C, Java, Rust, Haskell, Prolog.**
  One dynamic multi-paradigm language, one procedural/manual-memory baseline, one canonical
  nominal-OOP/GC language, one ownership/trait language, one lazy pure functional language,
  one logic language. Every layer-3 dimension in the brief has ≥2 distinct values instantiated
  inside this phase. All six have free, well-structured references except Prolog (acquisition
  action below). Cheap-to-ingest specs (PSF reference, N3220, JLS HTML, Rust Reference,
  Haskell Report) let the D15 ingestion pipeline mature before the monsters arrive.
- **Phase 2 — mainstream weight (4): C++, C#, JavaScript, R.**
  The remaining TIOBE-top-10 members: highest sweep+ingestion cost (C++ N4950, ECMA-262) and
  highest fact volume, now running against a phase-1-hardened ontology.
- **Phase 3 — landscape completers (4): OCaml, Erlang, Go, Swift.**
  Functors + effect handlers, actors, CSP + structural interfaces, ARC + protocol-oriented
  design. All four have free permissively-licensed references (CC BY-SA 4.0, Apache 2.0,
  CC BY 4.0, Apache 2.0) — trivial ingestion.
- **Phase 4 — cheap completeness (optional): Visual Basic** (CC BY 4.0 spec, near-zero novel
  facts, restores literal "TIOBE top 10 covered" for positioning).
- **Deferred, revisit post-1.0:** SQL (pending an ontology position on domain-specific
  languages + spec acquisition), TypeScript (no normative spec), Scheme/Racket (continuations
  + hygienic macros — first candidate if a phase-3 gap analysis shows the macro/control
  dimensions underinstantiated), APL-family and Julia (array orientation, multiple dispatch —
  R partially covers both), Elixir (Erlang covers the semantics; Elixir adds macros).

**D15 ingestion-list consequence** (specs/references entering the private source corpus, in
phase order): Python Language Reference (PSF-2.0); C N3220 draft; JLS SE 25 (private TDM only,
no redistribution); Rust Reference + Ferrocene FLS (MIT/Apache-2.0); Haskell 2010 Report;
ISO/IEC 13211-1 and/or Deransart et al. 1996 via university access + SWI-Prolog manual as the
free complement; then N4950, ECMA-334 + Microsoft C# draft standard (CC BY 4.0), ECMA-262,
R Language Definition; then OCaml Manual (CC BY-SA 4.0), Erlang/OTP docs (Apache 2.0), Go
spec (CC BY 4.0), TSPL (Apache 2.0). Per D14 nothing here constrains the private index; the
license column governs quotation (all fine under the ~50-word cap) and rules out only
bulk-copying — the already-forbidden act.

**Shiki**: all 14 (+VB) have bundled grammars in the current `tm-grammars` set — no D10 risk.

**Positioning line** (for topic 31): "the most-used languages of the TIOBE top 10, plus the
languages that define the rest of the feature landscape" — the curated deviation from raw
TIOBE is itself an argument for the typed-graph wedge (D19).

## Open questions for the developer

1. **Ratify the SQL deferral and VB demotion?** If literal "TIOBE top 10" coverage matters
   for positioning/SEO more than argued here, Option B (union, 16 languages) is the fallback —
   the added cost is one paywalled ISO purchase plus two low-value sweeps.
2. **Prolog tier-A backing:** purchase/obtain ISO/IEC 13211-1 through university access, rely
   on Deransart et al. (1996) as the standard's book form, or accept the SWI-Prolog reference
   manual (tier B, implementation-defined) as primary until the ISO text is acquired? Blocks
   phase 1, so this is the earliest developer action in this file.
3. **Erlang vs Elixir** (or both) as the BEAM/actor representative — Erlang is primary-source
   cleanest; Elixir adds hygienic macros and more current mindshare.
4. **Oz and Coq/Rocq status:** confirm they remain *concept-source-only* (facts from CTM /
   Software Foundations at feature level, no language pages, no sweeps) — or should Oz get
   language pages given CTM's centrality to the corpus?
5. **Spec edition pinning:** which edition per language is *the* pinned corpus version (e.g.
   C23/N3220 vs C17; JLS SE 25 vs SE 21 LTS; ECMA-262 2026 vs the living TC39 draft;
   Haskell 2010 + which GHC guide version)? Interacts with `since` semantics (D2) and the
   corpus-freshness topic from brainstorm 21.
6. **Phase-3/4 trigger:** are later phases gated on completing the earlier ones' sweeps, or
   may they interleave once the ontology stabilizes (e.g. `1.0.0` per D16)?

## New brainstorm topics surfaced

- **Domain-specific languages in the ontology** — whether/how the feature model accommodates
  non-general-purpose languages (SQL-class query languages, shells, config languages): a
  `language_kind` field, dimension applicability masks, or explicit out-of-scope. Blocks any
  future SQL onboarding; touches D2/D16.
- **Spec-vs-implementation provenance** — several onboarded languages are defined by an
  implementation, not a standard (Python/CPython, R/GNU R, Rust pre-FLS, TypeScript): how
  facts distinguish "the spec says" from "the reference implementation does", and which tier
  each gets. Extends D3's tier system; feeds the verifier (D4).
- **Coverage-gap analytics for language selection** — after phase 2, compute which
  features/dimension values still have <2 instances and let that drive phase-3+ ordering and
  future additions (Scheme, Julia, APL) — a data-driven successor to this document's manual
  audit.
- **Spec edition pinning & re-ingestion cadence** — concretizes brainstorm 21's
  "corpus freshness policy" for the 14 pinned specs above (annual ECMA-262 editions, rolling
  JLS releases, living Rust Reference).

## Sources

- TIOBE (2026). *TIOBE Index for July 2026.* https://www.tiobe.com/tiobe-index/
- TechRepublic (2026). *TIOBE Index July 2026: Rust Enters Top 10 as Index Turns 25.*
  https://www.techrepublic.com/article/news-tiobe-july-2026-rust-enters-top-10/
- PSF (2026). *History and License — Python documentation* (PSF-2.0; examples dual PSF-2.0 /
  0BSD). https://docs.python.org/3/license.html
- ISO/IEC (2024, via WG14). *N3220 working draft — ISO/IEC 9899:2024.*
  https://www.open-std.org/jtc1/sc22/wg14/www/docs/n3220.pdf
- ISO C++ (2023, via WG21). *N4950 — Working Draft, Standard for Programming Language C++.*
  https://www.open-std.org/jtc1/sc22/wg21/docs/papers/2023/n4950.pdf
- Oracle (2026). *Java Language Specification* + spec license (limited grant, no
  redistribution). https://docs.oracle.com/javase/specs/ ·
  https://www.oracle.com/downloads/licenses/javase8speclicense.html
- Ecma International (2026). *ECMA-334 — C# language specification* (free download).
  https://ecma-international.org/publications-and-standards/standards/ecma-334/
- Ecma International (2026a). *ECMA-262 — ECMAScript language specification* (permissive
  copy/derivative notice).
  https://ecma-international.org/publications-and-standards/standards/ecma-262/
- Microsoft (2026). *C# / Visual Basic language documentation and draft standards on
  Microsoft Learn* (docs CC BY 4.0 per dotnet/docs LICENSE).
  https://github.com/dotnet/docs/blob/main/LICENSE ·
  https://learn.microsoft.com/en-us/dotnet/visual-basic/reference/language-specification/
- ISO (2023). *ISO/IEC 9075 — Database language SQL* (paywalled).
  https://www.iso.org/standard/76583.html
- R Core Team (2026). *R Language Definition* (permissive verbatim/modified copying notice).
  https://cran.r-project.org/doc/manuals/r-release/R-lang.html ·
  https://cran.r-project.org/manuals.html
- Rust Project (2026). *Licenses* (Reference and spec MIT OR Apache-2.0).
  https://rust-lang.org/policies/licenses/ · https://github.com/rust-lang/spec
- Marlow, S. (ed.) (2010). *Haskell 2010 Language Report* (community license; SPDX
  `HaskellReport`). https://www.haskell.org/onlinereport/haskell2010/ ·
  https://spdx.org/licenses/HaskellReport.html
- INRIA (2026). *The OCaml Manual* (documentation CC BY-SA 4.0).
  https://ocaml.org/docs/license.html · https://ocaml.org/manual/
- Deransart, P., Ed-Dbali, A., & Cervoni, L. (1996). *Prolog: The Standard — Reference
  Manual.* Springer. https://doi.org/10.1007/978-3-642-61411-8 (ISO/IEC 13211-1 companion;
  university access)
- Ericsson (2026). *Erlang/OTP documentation* (Apache 2.0).
  https://github.com/erlang/otp/blob/master/LICENSE.txt · https://www.erlang.org/doc/
- Go Project (2026). *The Go Programming Language Specification*; site content CC BY 4.0.
  https://go.dev/ref/spec · https://go.dev/copyright
- Apple / Swift.org (2026). *The Swift Programming Language* book, Apache 2.0 with Runtime
  Library Exception. https://github.com/swiftlang/swift-book ·
  https://www.swift.org/legal/license.html
- Shiki (2026). *Bundled languages / tm-grammars* (260 grammars; per-language IDs verified
  against the current `tm-grammars` package). https://shiki.style/languages ·
  https://github.com/shikijs/textmate-grammars-themes
- Van Roy, P., & Haridi, S. (2003). *Concepts, Techniques, and Models of Computer
  Programming.* MIT Press. https://webperso.info.ucl.ac.be/~pvr/VanRoyHaridi2003-book.pdf
