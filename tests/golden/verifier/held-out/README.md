<!-- tests/golden/verifier/held-out/README.md -->
# Held-out audit slice (§6.4)

10–15 items **authored entirely by the developer, with no LLM in the loop**, kept out of
every tuning signal. `load_verifier_items()` excludes this directory unless a caller
passes `include_held_out=True`, and `golden-score` requires the explicit
`--include-held-out` flag.

Run it **once**, at the end of 2D's calibration, as an audit. If it is consulted while
tuning prompts or models, it has stopped being a held-out slice and a fresh one must be
authored.
