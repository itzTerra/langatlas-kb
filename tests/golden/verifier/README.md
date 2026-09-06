<!-- tests/golden/verifier/README.md -->
# Verifier golden set (D44 / §6.4)

~200–300 stratified `(claim, citation)` items with the verdict a correctly-calibrated D24
verifier must return. Scored by `langatlas-sources golden-score`, which reports
**false-accept and false-reject rates separately** against the §6.2 targets
(**FA ≤2% / FR ≤10%**). Distinct from `tests/fixtures/providers/regression/`, which is
D48's diff-reviewed pass/fail family. **This harness is never a CI blocker on its own**
(§8.6) — only the shape check (`golden-validate`) runs in CI.

## The 13 strata

| Stratum | What it perturbs | Expected verdict |
|---|---|---|
| `correct` | nothing | `supported` |
| `overstated-claim` | claim generalises beyond what the cited text says | `partial` |
| `fabricated-locator` | locator points nowhere in the source | `locator-not-found` |
| `wrong-since-off-by-one` | `since` off by one release | `contradicted` if the text states a conflicting version, else `partial` |
| `wrong-since-off-by-major` | `since` off by a major version | same split — error size does not change the fold |
| `contradicted` | source states the opposite | `contradicted` |
| `right-claim-wrong-source` | true claim, source that does not carry it | `unsupported`/`contradicted` |
| `category-error` | claim asks the wrong kind of question of the text | `unsupported` |
| `fabricated-combination` | feature-instance pairing that does not exist | `unsupported`/`contradicted` |
| `quote-mismatch` | quote is not in the source | `unsupported` (`contradicted` if the source also opposes the claim) |
| `quote-found-elsewhere` | quote is real but not at the locator | `supported`/`partial` |
| `ocr-noisy` | correct claim, quote carries extraction noise | `supported` |
| `paraphrase-heavy-correct` | correct claim, no lexical overlap with the source | `supported` |

`source-unavailable` is in the verdict vocabulary but no stratum produces it: it is the
un-ingested-citation path, exercised by 2D's own unit tests rather than by calibration
items, because it never reaches the entailment stage.

## Authoring contract

- One file per batch: `items-<theme>.yaml`.
- Locators and `evidence_chunk_ids` are **copied from real `source_chunks` rows** — never
  hand-typed — except in `fabricated-locator`, where fabricating them is the point.
- Quotes obey D14's 50-word cap.
- LLM-generated candidates arrive with `curated: false`; the loader **refuses** to load
  them. Flipping it to `true` is the developer's act of curation.
- Contamination defense is structural: perturb toward specifically-invented wrongness
  (invented version numbers, swapped similar-language attribution, altered loci), not
  famous-facts-stated-wrong. Mark obscure-locus items `contamination_gauge: true`; they
  are scored on their own line, and a wide gap against the mainstream items is the
  contamination signal.
- Staleness enforcement is soft: `golden-staleness` logs, never fails.

Run `langatlas-sources golden-validate --resolve --complete` before declaring the set done.
`--resolve` only checks that ids exist, not that their content still matches the claim —
after a chunking change, re-derive by content (see `PENDING-REPAIR.md` for the D22 rework
in progress) rather than trusting a clean `--resolve` run alone.
