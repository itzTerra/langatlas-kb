# Contributing to LangAtlas

## Automated (agent-runner) commits

Commits authored by the `langatlas-bot[bot]` GitHub App identity are **DCO-exempt by
design**: installing the App on this repository is itself the developer's one-time act of
contribution and sign-off for everything the pipeline subsequently produces under that
identity (D36/D14). No per-commit `Signed-off-by:` trailer is expected or required on
bot-authored commits.

## Human contributions

Every human-submitted commit (via PR) must carry a `Signed-off-by:` trailer per the
Developer Certificate of Origin (DCO), asserting you have the right to submit the change
under this project's licenses (code: MIT; corpus: CC BY-SA 4.0). Add it with
`git commit -s`.

Human contribution lanes and the fact-challenge process are documented in full once Stage 6
lands (D32); this file will grow those sections then.

## Sourcing

**Finding aids are not sources.** PLDB, Wikidata, Hyperpolyglot and Wikipedia tell the
pipeline what to look for; they never back a claim. If a fact's only support is a finding
aid, it does not enter the store — go find the tier-A/B source the lead was pointing at.
