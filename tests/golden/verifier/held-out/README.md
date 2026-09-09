<!-- tests/golden/verifier/held-out/README.md -->
# Held-out audit slice (§6.4) — ABANDONED (2026-09-09)

D44 originally called for 10–15 items authored entirely by the developer, with no LLM in
the loop, kept out of every tuning signal and run once at the end of 2D's calibration as
an audit. The developer ruled to abandon hand-authoring this slice; `SET_INVARIANTS` in
`goldens/loader.py` now requires exactly 0 held-out items, and this directory stays empty
permanently. `load_verifier_items(include_held_out=True)` and `golden-score
--include-held-out` still work, but have nothing to load.
