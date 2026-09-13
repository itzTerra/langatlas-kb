# D24 verifier calibration

The measured false-accept and false-reject rates of the verification gate
(context/spec.md §6.2), against the committed golden set (§6.4). **Published on purpose**:
a gate whose error rates are private is a gate no reader can weigh.

## Result

| Metric | Measured | Target |
|---|---|---|
| False accept | 3.73% | ≤2% |
| False reject | 7.06% | ≤10% |
| Exact-verdict accuracy | 84.47% | — |
| Absence false accept (D49) | 0.00% | ≤2% |
| Contamination gauge (obscure vs mainstream) | gauge 92.59% vs mainstream 81.82% (gap -10.8%) | narrow gap |

No held-out audit slice: abandoned by developer ruling (2026-09-09).

**Thresholds not fully met** (false accept over target) — accepted as the calibration
record by developer decision rather than pursued further. See "What was changed" below
for what brought this from a 45.88% false-reject baseline down to here, and "Known
limitation" for why the false-accept rate is treated as measured-and-accepted rather than
chased further.

## Configuration measured

- Golden set: 219 items over 13 strata; no held-out slice (abandoned 2026-09-09)
- Primary / escalation / second opinion: `deepseek` / `deepseek-thinking` / `mini`
- Second-opinion rate: 0.10; mandatory second vote: false
- Prompts: `verify-entailment@v-9beb8a9b` (v4), `verify-absence@v-7c781704`,
  `verify-quote-adjudication@v-29674aab`
- Canaries: the 5 in `tests/golden/verifier/canaries.yaml`

## Per-stratum reading

- **overstated-claim**: 2 false accepts, the K1 laundering pattern this stage exists to
  catch — the model marked a `qualifier` supported at a broader scope than the evidence
  actually backs (e.g. an unconditional claim where the passage only supports a narrower,
  conditioned case). v4's prompt revision fixed the two overstated-claim items it was
  built against; these are two *different* items failing the same way, suggesting the
  underlying comprehension gap is only partially closed rather than a residual wiring bug.
- **wrong-since-off-by-one**: 2 false accepts, new to this run (not present in the
  immediately preceding rerun) — see "Known limitation."
- **category-error**: 1 false accept (`v-scheme-core-0002`), present in every calibration
  run since the first — a `quality-assessment` claim the model reads as supported because
  the source states a real efficiency effect, when the golden item's intent is that a
  descriptive efficiency note is not the same as an explicit quality judgment. A prompt gap
  specific to the `quality-assessment` claim kind, not touched by this round's fixes.
- **correct / ocr-noisy / paraphrase-heavy-correct**: the remaining 6 false rejects are a mix
  of a known page-break/running-header extraction artifact splitting one quote mid-sentence
  (`v-ada-core-0001`, chunk `sebesta-copl#c01035`) and residual model misreads on individual
  items — no further single fixable bug identified.

## What was changed to reach here

Starting point (first real calibration run, before this round's fixes): false accept
1.49%, **false reject 45.88%**. Four bugs found and fixed, each confirmed against the real
gateway before being committed, each with a regression test reproducing the exact failure:

1. **Evidence not rerouted on `quote-found-elsewhere`** (`verify/pipeline.py`) — stage 3 kept
   judging the wrong-locator text instead of the chunk the fast path actually located.
   Fixed that stratum's false-reject rate from 9/12 to 0/12.
2. **`unsupported` never escalated** (`verify/tiering.py`) — a primary-model misread of
   quote-confirmed evidence had no rescue path. Now escalates when the fast path
   independently confirmed the quote (a clean match, an adjudicated OCR-noise call, or a
   located elsewhere-match) and the verdict still comes back `unsupported`.
3. **Quote ratio too strict for real OCR noise** (`verify/quotes.py`) — pure token-level
   comparison gave a corrupted token zero credit no matter how character-similar it was,
   terminal-rejecting the whole `ocr-noisy` stratum before the LLM adjudicator ever ran.
   Now blends in a character-level read of the same window.
4. **`EntailmentOut.assertions` had a permissive default** (`verify/entailment.py`) — 50 of
   276 real responses across one run omitted `assertions` entirely; the default let that
   validate as "zero assertions" and silently fold to `unsupported`, without ever
   triggering the repair-turn retry that exists for exactly this. This was the single
   largest contributor, concentrated on `status: absent` claims (12 of them). Also fixed a
   related robustness gap: a cache entry that no longer validates against a tightened
   schema is now treated as a miss, not a crash.

Two `verify-entailment` prompt versions (v3, v4) closed most of the remaining gap: v3
added guidance to read the whole passage before concluding `not-supported` (the claim's
subject is often inside a list, a comparison, or a glossary definition rather than the
sentence's grammatical subject); v4 added back explicit scope/qualifier scrutiny after v3's
generosity introduced two new overstated-claim false accepts.

## Known limitation: run-to-run variance

Five consecutive reruns during this round, differing only in code/prompt fixes applied
between them, showed the specific failing item *ids* changing between otherwise-identical
runs (e.g. the two overstated-claim items v4 was built and verified against are not the
ones failing in the final run — different items fail the same way instead). The model is
not fully deterministic at temperature 0 on this gateway. The measured rates above should
be read as one draw from a noisy process with false accept sitting near its 2% ceiling
(observed range across reruns: roughly 1.5%–3.7%) rather than a single precise number.
Section 6.2 names the mandatory-`mini`-second-vote hardening
(`verification.mandatory_second_opinion` in `config/ingest.yaml`) as the next lever for a
false-accept rate prompt work has not fully closed; not applied this round by developer
decision.

## Re-running

`langatlas-sources golden-score --json benchmarks/d24-verifier/calibration.json`

Rerun on **any** verifier prompt or model change (§6.2). The machine-readable
`calibration.json` is what the D35 bundle manifest and the site's published error rates
read; keep it in step with this file.
