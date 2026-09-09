"""§4.4's corpus-currency checks: is the live link still there, and is the edition we
pinned still the current one?

Deliberately separate from `verify/`: nothing in here may reach a verdict, a fact, or the
ledger. A dead link never retroactively unverifies a fact verified against its archived
snapshot (§4.4), so the *only* outputs of this subpackage are a private row and a
`sourcing_queue` entry a human reads."""
