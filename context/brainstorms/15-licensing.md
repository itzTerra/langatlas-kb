# 15 — Legal & Licensing Statement

> Round-2 brainstorm output. Owner asked for a plain-language explanation of the copyright and
> licensing problems Hermes will face, EU/Czech framing first (Czech university context), US fair
> use second. **One caveat, stated once: this is research by a language model, not legal advice.
> It is a map of where the problems are, written so a non-lawyer can make sane defaults; the
> "consult a lawyer if X" list at the end marks the few places where a real lawyer earns their fee.**

## Problem framing

Hermes touches other people's copyrighted material in five distinct ways, and each has a
different risk profile:

1. **Quoting** — short verbatim excerpts from books (Van Roy & Haridi), papers (Jordan et al.),
   and docs, displayed publicly on the site inside citation popovers (D3, D10).
2. **Snapshotting** — the verification pipeline fetches and stores source text/PDFs so the
   verifier can check claims (D4). Private storage vs public repo is the whole question.
3. **Referencing proprietary data** — TIOBE and similar indexes ("Language statistics" in the
   brief).
4. **Ingesting open datasets** — PLDB, Wikidata, Hyperpolyglot, official language docs, each
   under a different license, some with strings attached (share-alike).
5. **Licensing our own output** — the corpus license (D12 left CC BY-SA 4.0 tentative, pending
   this brainstorm) and the contribution mechanics (DCO/CLA).

The good news up front: Hermes is structurally on the safe side of copyright. Its product is
**facts** (Rust has affine types; call-by-need exists in Haskell) expressed in **our own
sentences**, with short attributed quotes as evidence. Facts are not copyrightable anywhere;
short attributed quotation for scholarly purposes is an explicit statutory exception in Czech/EU
law; and the one thing that would be clearly infringing — republishing whole chapters, full PDFs,
or wholesale copies of other databases — is something D1 already forbids for unrelated
engineering reasons ("never commit page snapshots"). The job of this document is to turn that
accidental safety into deliberate policy.

## The landscape in plain language

### Copyright protects expression, not facts

Copyright covers the *particular wording, structure, and creative choices* of a work — never the
facts, ideas, or methods inside it. "Van Roy & Haridi define active objects as X" is a fact you
may state freely in your own words forever, with or without permission (attribution is scholarly
honesty and, for quotes, a legal requirement — but *stating a fact* needs no license). What you
may not do freely is reproduce their *sentences* at length, because the sentences are the
protected expression. This fact/expression line is the single most important idea in this
document: almost everything Hermes wants to do lives on the safe "facts" side.

### There is no "fair use" in Czech law — there is a closed list of exceptions, and quotation is on it

US fair use is a flexible four-factor balancing test. EU/Czech law works differently: the Czech
Copyright Act (No. 121/2000 Coll., implementing the EU InfoSoc Directive) contains a **closed
list of specific exceptions**, and if your use fits one, you're fine; if it fits none, you need
permission — there is no general "but it was fair" argument. The relevant exception is
**§ 31 — the quotation right (citace)**. In plain terms it permits, without permission:

- using **excerpts of published works** (or small works in their entirety) **in your own work**,
- to a **justified extent** — no fixed word count; the excerpt must be no longer than the purpose
  (evidence, criticism, review, scientific/technical treatment) requires,
- with **mandatory attribution**: author, title, and source must always be stated unless
  impossible, and
- consistent with **fair practice** (the three-step test: the use must not conflict with normal
  exploitation of the work or unreasonably harm the author).

Every EU member state has an equivalent, because quotation is the one exception the InfoSoc
Directive effectively mandates. Two practical consequences for Hermes:

1. **The quote must sit inside our own work.** A page of Hermes prose containing a two-sentence
   attributed quote as evidence = classic quotation. A page that is *mostly* quoted material with
   thin connective tissue = not quotation, just copying. Hermes' fact-card design (one original
   sentence per fact, optional short verbatim quote in a popover, D3) is almost the textbook
   example of what § 31 was written for.
2. **Attribution is not optional in the EU** the way it can be argued in US fair use. Hermes'
   citation system makes every quote attributed by construction — this requirement is satisfied
   for free.

US fair use, for completeness: short quotation with attribution for a transformative,
non-substitutive scholarly purpose is about the strongest fair-use position that exists. If the
use passes the (stricter, list-based) Czech test, it passes the US test with room to spare. The
site serves globally, so it is good that we clear the tighter bar.

### Private copies for analysis are a separately blessed activity (text and data mining)

The pipeline needs to fetch sources and keep snapshots so the verifier can check quotes and
claims (D4). Storing a full copyrighted PDF *privately* for machine analysis is a different act
from *publishing* it, and EU law now covers it explicitly: the **DSM Directive (EU) 2019/790,
Articles 3–4** (transposed into Czech law by amendment No. 429/2022 Coll.) creates a **text and
data mining exception** — reproductions of lawfully accessible works for automated analysis are
permitted, and copies may be retained as long as needed (for research purposes, retained for
verification). Article 4 (general TDM) is subject to a machine-readable opt-out by the
rightsholder (e.g. robots.txt / ToS reservations), which the fetcher should respect anyway per
the politeness rules in 08 §5. So: **private pipeline snapshots of lawfully accessed sources are
fine; publishing those snapshots is a completely different and mostly not-fine act.**

### Databases get an extra EU-only right: the sui generis database right

US-centric advice says "facts are free, so scrape away." The EU has an extra layer: the
**Database Directive 96/9/EC** gives the *maker* of a database — someone who substantially
invested in **obtaining, verifying, or presenting** its contents — a 15-year **sui generis
right** against **extraction or re-utilisation of a substantial part** of that database, *even
though the individual facts are uncopyrightable*. Czech law implements this in §§ 88–94 of the
Copyright Act. Two directions matter:

- **Inbound:** bulk-copying a substantial part of someone else's curated database (e.g.
  mirroring PLDB's tables, scraping all of TIOBE's history, ingesting Hyperpolyglot wholesale)
  can infringe *their* database right even if every individual cell is a mere fact. Taking
  *individual facts* (insubstantial parts), or using their data as a **lead to the primary
  source** which you then cite, does not.
- **Outbound:** Hermes itself — a database built with substantial investment in obtaining and
  verifying contents — **will qualify for its own sui generis right**, which is exactly why the
  corpus license choice must be one that handles database rights explicitly (CC 4.0 licenses
  do; CC 3.0 and plain "public domain" statements often don't — see below).

### Code snippets are (usually) copyrightable, but tiny ones usually aren't protectable

Software is a literary work under both EU and US law, and that includes example snippets in
documentation. But copyright requires creative expression: a three-line snippet showing *the
only reasonable way* to write a `match` expression has little or no protectable expression
(merger doctrine / "dictated by function"). The practical rule: **short syntax demonstrations
written by us are always safe; verbatim copies of distinctive multi-line examples from docs
inherit the docs' license.** Since SyntaxExamples are a first-class entity (D2), the clean
policy is: agents write **original minimal examples** demonstrating the feature, and treat the
official docs as the *source cited for correctness*, not the text copied.

## Risks & resolutions

### R1. Quoting Van Roy & Haridi, Jordan et al., and other books/papers publicly

**Risk (low, if policy is followed):** overlong or aggregated quotation. One two-sentence quote
per fact is unambiguously fine under § 31. The failure mode is *accumulation*: if the "active
objects" feature page ends up displaying two paragraphs of CTM verbatim across ten fact
popovers, the page as a whole starts to look like a substitute for reading the book — that
breaks both the "justified extent" limb and the three-step test.

**Resolution:**
- Hard policy in the schema/CI: a `quote` field is **capped (suggest ~50 words / ~300 chars)**;
  CI warns when a single rendered page aggregates more than a few hundred words of verbatim
  quotation from one source.
- Quotes are always attributed (already guaranteed by D3's citation machinery) and always
  embedded in Hermes' own explanatory text (already guaranteed by the fact-card design).
- Note the brief itself already contains verbatim CTM sentences (input-brief.md §1); they are
  fine in a private planning doc and fine on the site *at popover length with attribution*.
- The CTM PDF is freely distributed by Van Roy himself at his university page — good for a
  primary-URL link, but that does **not** grant republication rights; link, never mirror.

### R2. Source snapshots: private pipeline storage vs public repo

**Risk:** committing fetched text extracts or PDFs to the **public** repo = republication, no
exception covers it. This is the one place a hobby project can generate a real DMCA/EU takedown.

**Resolution (mostly already decided — make the legal rationale explicit):**
- D1 already says "never commit page snapshots or binaries." Restate it as a *legal* rule in
  CONTRIBUTING/README of the KB repo: **full source texts, extracts beyond quote length, and
  PDFs never enter any public repo or public bucket.**
- Private snapshot store (local disk / private bucket, content-hash keyed, per 08 §5) is
  covered by the TDM exception for lawfully accessed sources; keep the fetcher polite and
  respect robots.txt / opt-outs (this converts a legal gray zone into the blessed path).
- Link-rot protection is **delegated to the Internet Archive** (SavePageNow on mint, D3) —
  archive.org carries the republication risk, Hermes just links. This is the standard,
  Wikipedia-endorsed pattern.
- Paywalled papers (ISO standards, some Jordan et al.-adjacent literature): the developer may
  read them via university access, quote briefly, and cite with DOI + locator — but the PDF
  never leaves the private store, and university license terms typically forbid even private
  redistribution to third parties (including, arguably, cloud-hosted LLM APIs — see R8/open
  question).

### R3. TIOBE and proprietary indexes — what "link, don't ingest" means

TIOBE's stated permission is that the index may be reproduced/referenced **if www.tiobe.com is
cited as the source**, but its data is proprietary and methodology-limited (tier D per D3), and
the safe reading of "link, don't ingest" is:

- **Do:** state the fact "language X ranked #N on TIOBE in 2026-07" with a link (a single data
  point = insubstantial part, plus their attribution condition is met); link to their page for
  "current stats."
- **Don't:** scrape or store their historical time series, re-plot their charts from bulk data,
  or make TIOBE numbers a load-bearing dataset. Bulk reproduction is exactly the "substantial
  part re-utilisation" the sui generis right forbids, and their business is selling that data.
- Same posture for any stats provider without an explicit open license (RedMonk, IEEE Spectrum,
  Stack Overflow survey — the SO survey data is actually ODbL, which is open but share-alike;
  if ever ingested it becomes an R5 problem, so link it too).
- TIOBE stats are deferred anyway (D11) — the only rule needed *now* is that nobody builds an
  ingester for a proprietary index.

### R4. Upstream open datasets — the license inventory

| Source | License | What it means for Hermes |
|---|---|---|
| **PLDB** | Public domain (site states its data/code are public domain) | Free to use for anything. Caveat: "public domain" declarations by non-US parties can be legally wobbly in the EU (moral rights, database right can't always be waived by mere statement) — treat as CC0-equivalent, keep attribution anyway (D3 requires provenance regardless; costs nothing, removes all doubt). Corroboration-only per D3. |
| **Wikidata** | CC0 1.0 | Genuinely free, database rights explicitly waived. Ideal skeleton source (IDs, `sameAs` links per D10). No obligations. |
| **Hyperpolyglot** | **CC BY-SA 3.0** | The dangerous one. Attribution required, and **share-alike: any "adaptation" incorporating its content must be licensed CC BY-SA**. Copying its comparison-table *content* (its curated cell text, its example snippets) into the corpus would contaminate those parts with an SA obligation (and BY-SA **3.0** has messy one-way upgrade compatibility to 4.0). **Resolution: use Hyperpolyglot only as a *finding aid* — a pointer to check a feature against the primary source — and as corroborating citation (D3 already restricts it to corroboration-only). Never copy its cells or its example code.** Facts independently restated from primary sources carry no SA taint (facts aren't copyrightable; independent expression is ours). |
| **Python docs** | PSF License 2.0; **code examples in docs since 3.8.6 are dual PSF-2.0 / 0BSD** | Very permissive. 0BSD on doc snippets means Python example code can be reused without even attribution — though Hermes policy is original examples anyway. Citing/quoting docs: unproblematic. |
| **Rust docs (Reference, Book, std docs)** | MIT OR Apache-2.0 (Rust Foundation policy: open licenses incl. CC-BY/CC0 for media) | Permissive; quoting and even copying examples is fine with license notice. Original examples still preferred for consistency. |
| **ISO C++ / other ISO/ECMA specs** | **Proprietary, paywalled (ISO); ECMA specs free but copyrighted** | Never mirror or excerpt at length. Cite by clause number (locator `[dcl.init]`-style), quote a sentence under § 31 if needed. Practical tip: cite the **freely available working drafts** (eel.is/c++draft, open-std.org papers) which the C++ community itself treats as the referenceable text. |
| **Wikipedia/wikis** | CC BY-SA 4.0 | Same SA logic as Hyperpolyglot: use as finding aid + corroboration, restate facts independently, don't copy prose. |
| **Official docs, general rule** | Varies per language | Add a `custom.license` field on source records for doc-type sources; agents minting a docs source record the license when discoverable. Quoting under § 31 is always available regardless of license; *copying examples* is what needs the license check. |

### R5. The corpus license: CC BY-SA 4.0 vs CC BY 4.0 vs ODbL

What is actually being licensed? Three layers, worth keeping distinct:

1. **The facts themselves** — not copyrightable by anyone; no license can add or remove that.
2. **Hermes' expression** — the fact sentences, feature descriptions, original examples,
   explanatory prose. Normal copyright, ours (and contributors').
3. **The database as a whole** — EU sui generis right, ours (the "substantial investment in
   obtaining and verifying" is literally the verification pipeline).

The license choice governs layers 2–3. The candidates:

- **CC BY 4.0** — attribution only. Maximum reuse: anyone (including commercial LLM vendors,
  competitors, PLDB) can ingest the corpus with a credit line. Explicitly licenses sui generis
  database rights (CC 4.0 series does; 3.0 didn't reliably). Simplest downstream story.
- **CC BY-SA 4.0** (current tentative, D12) — attribution + share-alike: anyone building an
  *adapted work* on the corpus must release it under BY-SA. What SA obliges downstream users to
  do, concretely: a site that republishes/extends Hermes data must license its adapted database
  BY-SA; a company embedding the corpus into a proprietary product must keep the corpus-derived
  part BY-SA (in practice many will simply not use it). What SA does **not** do: it does not
  stop anyone from *reading facts out* of Hermes and restating them (facts are free — SA can't
  reach layer 1), so SA's protective power over a *fact* corpus is weaker than it looks. Note
  also: **because Hermes ingests no CC BY-SA content (R4 policy: finding-aid only), there is no
  inbound SA obligation forcing this choice** — it is a genuinely free choice. One-way door
  warning: relicensing BY-SA → BY later requires consent of every contributor; BY → BY-SA is
  equally hard in the other direction, so the choice is sticky either way once outside
  contributions arrive.
- **ODbL 1.1** (OpenStreetMap's license) — database-specific share-alike; legally the most
  precise fit for an EU database, but heavier: longer, less understood, worse tooling/ecosystem,
  and it complicates mixing with CC content. Overkill for a solo project whose community lives
  on GitHub, not in GIS.

**Recommendation: CC BY-SA 4.0, confirmed** — it matches the owner's tentative pick, matches
the Wikipedia-adjacent norms of the contributor community Hermes courts, covers EU database
rights properly, and its main cost (deterring proprietary bulk reuse) is arguably the intended
effect. If the owner's priority flips to "maximize reuse including by AI/commercial systems,"
CC BY 4.0 is the right answer and equally defensible; ODbL is not worth its friction here.
Either way, add a plain-English `LICENSE` note in the KB repo explaining the three layers above
(one paragraph), because contributors will ask.

### R6. Code = MIT (decided); DCO for contributions

- Code repos: MIT, decided (D12). No issue; MIT-licensed code may freely link/serve BY-SA data
  (license of the pipeline and license of the corpus are independent).
- **Contributions: use the DCO (Developer Certificate of Origin — `Signed-off-by` line), not a
  CLA.** A CLA (contributor license agreement) is a signed contract assigning/licensing rights
  to the project — legal overhead, contribution friction, and pointless without a legal entity
  to receive the rights. The DCO is a one-line self-certification ("I have the right to submit
  this under the project license") used by the Linux kernel and most of GitHub; enforceable
  enough, zero friction, solo-dev sized. Add: DCO paragraph in CONTRIBUTING.md + optionally the
  `dco` GitHub app/Action to check sign-offs. Challenge-issue text (D9) needs nothing — issue
  comments are ideas/facts, not copyrightable contributions worth papering.

### R7. Syntax examples

Policy (from "code snippets" section above): **agents write original minimal examples; official
docs are cited for correctness, not copied.** Where an example is genuinely canonical and tiny
(`print("hello")`), copying is harmless — no protectable expression. Where a doc example is
distinctive and multi-line, either rewrite it or (for permissively licensed docs like
Python/Rust) copy with license attribution in the source record. CI nicety: SyntaxExample gets
an `origin: original | adapted-from:<source-id>` field so provenance is auditable.

### R8. Quiet extra risks worth naming

- **Sending copyrighted source text to LLM APIs** (university API, Anthropic) for
  verification/entailment is a reproduction; for lawfully accessed open-web sources the TDM
  exception plausibly covers it, but for **university-licensed paywalled content** the
  publisher's license terms (not copyright law) may forbid it. Cheap mitigation: verification
  over paywalled sources uses only the short quote + surrounding paragraph, not full texts.
- **Moral rights (EU):** authors retain the right against distortion. Quoting accurately and
  not misattributing — which the verification gate enforces anyway — satisfies this.
- **Trademark, not copyright:** language names/logos (Python, Rust, Java) are trademarks;
  nominative use ("facts about Java") is fine, implying endorsement or reusing logos is not.
  Use plain text names or clearly-licensed logo packs; don't put language logos on the site
  without checking each trademark policy (several, like Rust's, have explicit policies).

## Recommendation

**Do this now (cheap, before code):**
1. Ratify **corpus = CC BY-SA 4.0** (or consciously flip to CC BY 4.0 — R5 gives the criterion);
   code = MIT (done). Put `LICENSE` files + the three-layer plain-English note in both repos.
2. Add **DCO** (`Signed-off-by` + CONTRIBUTING paragraph + check Action) to both repos.
3. Write the **quotation policy into schema + CI**: quote field ≤ ~50 words, always attributed
   (already structural), per-page aggregate quote warning.
4. Write the **"no source content in public repos"** rule into CONTRIBUTING as a legal rule, not
   just an engineering one; private snapshot store only.
5. Adopt the **Hyperpolyglot/Wikipedia rule**: CC BY-SA sources are finding aids + corroborating
   citations only; their prose/cells/examples are never copied. (One sentence in the agent
   pipeline prompt/policy doc.)
6. Adopt the **original-examples rule** for SyntaxExamples + `origin` field.
7. Fetcher: respect robots.txt and TDM opt-outs (already planned as politeness — now also the
   legal path).

**Decide later (when the feature arrives):**
- TIOBE/stats display details (deferred module) — revisit R3 then; default is link-only.
- Whether to record `custom.license` on all doc sources from day one or backfill (suggest: field
  exists in schema now, populated opportunistically).
- Stack Overflow survey / ODbL datasets, if ever wanted — separate assessment then.
- Logo/trademark usage on the site — decide at website-design time; default is text names.

**Genuinely consult a lawyer if:**
- Hermes ever wants to **host source snapshots publicly** (e.g. its own archive of docs pages)
  — don't do this without advice; the Internet Archive delegation makes it unnecessary.
- A **rightsholder complains** (takedown notice, email from a publisher) — respond via counsel
  or at minimum the university's legal office, not by arguing copyright theory in an issue
  thread. Immediate safe action: unpublish the contested quote (facts can stay; they were never
  theirs).
- The project **incorporates or takes money** (sponsorship, selling API access to the corpus) —
  commercial exploitation changes the fair-practice calculus and makes license hygiene
  contractual, not just reputational.
- You want to **bulk-ingest any proprietary or SA-licensed database** as a load-bearing source
  (i.e., someone proposes breaking the R3/R4 rules for good reasons).

## Open questions for the owner

1. **BY-SA vs BY, final:** the deciding question is one sentence — *do you want someone who
   republishes an extended version of the Hermes corpus to be forced to share their extensions
   openly (BY-SA), or do you prefer maximum uptake including by closed systems (BY)?* D12's
   tentative BY-SA is the community-protective default; confirm or flip.
2. **Quote cap value:** is ~50 words per quote / ~300 words aggregate-per-page-per-source an
   acceptable CI rule of thumb? (Any figure is a policy choice, not a legal line — Czech law has
   no word count; the cap just keeps every page comfortably inside "justified extent.")
3. **University API terms** (repeats 08 open question 6, now with legal teeth): do the
   university model API's terms say anything about sending third-party copyrighted text through
   it, and does your university library license forbid feeding paywalled PDFs to it? If unknown,
   the R8 mitigation (short excerpts only) should be the default.
4. **Logos:** text-only language names on the site (zero risk), or do you want logos enough to
   check ~20 trademark policies?

## New brainstorm topics surfaced

- **Attribution rendering spec** — how BY/BY-SA attribution, source licenses, and the corpus
  license notice concretely appear on site pages and in MCP responses (ties into D10 citations;
  small, but SA attribution has format requirements).
- **Takedown/complaint runbook** — a half-page "what to do if a rightsholder emails" note
  (unpublish quote, keep fact, respond within N days), so a future panicked evening has a
  checklist.
- **Trademark policy sweep** — if logos are wanted (open question 4), a one-off audit of the
  top languages' trademark/logo policies.
- **Dataset export design** — if the corpus is BY-SA, publishing clean machine-readable dumps
  (with embedded attribution metadata) is the honest way to make SA reuse practical; overlaps
  brainstorm on build artifacts.

---

*Key references checked (2026-07):* Czech Copyright Act No. 121/2000 Coll. § 31 (quotation) and
§§ 88–94 (database right) — [WIPO Lex consolidated text](https://wipolex-res.wipo.int/edocs/lexdocs/laws/en/cz/cz043en.html),
[copyrightexceptions.eu on § 31](https://www.copyrightexceptions.eu/implementations/cz/info53d/);
DSM Directive (EU) 2019/790 Arts. 3–4 (TDM); Database Directive 96/9/EC;
[TIOBE index page (attribution condition)](https://www.tiobe.com/tiobe-index/);
[Python docs license (PSF-2.0, examples dual 0BSD)](https://docs.python.org/3/license.html);
[Rust licenses (MIT/Apache-2.0)](https://rust-lang.org/policies/licenses/) and
[Rust Foundation IP policy](https://rustfoundation.org/policy/intellectual-property-policy/);
[Hyperpolyglot (CC BY-SA)](https://hyperpolyglot.org/);
[CC BY-SA 4.0 legal code (incl. sui generis DB rights)](https://creativecommons.org/licenses/by-sa/4.0/legalcode.en).
