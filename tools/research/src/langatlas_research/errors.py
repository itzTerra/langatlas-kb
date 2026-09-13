class ResearchError(Exception):
    """Base for every failure this package raises deliberately."""


class SignOffMissing(ResearchError):
    """D27's hard checkpoint: this cycle has no developer sign-off at all."""


class SignOffStale(ResearchError):
    """The theme was edited after it was signed off, so the sign-off no longer
    describes what would run. The gate re-opens rather than silently passing."""


class UnsourcedNode(ResearchError):
    """D4/§6.1: a node with no (source, locator) evidence is not mintable."""


class DegenerateRule(ResearchError):
    """D64: a 1-antecedent Rule belongs in the matching edge type instead."""


class InvalidDraft(ResearchError):
    """The rendered record failed schema or normalization validation."""


class InvalidTransition(ResearchError):
    """Cycle status moves forward through the fixed ladder, never backward."""


class UnknownTheme(ResearchError):
    """A cycle names a theme that `research/themes.yaml` does not define."""


class RaceExhausted(ResearchError):
    """A shared-file mint (taxonomy.py) kept losing its race against a competing writer
    on every retry `land_drafts` was given — the file never stopped looking stale long
    enough for `land_record` to even attempt a commit. Never silence this as a
    `(minted, None)` result: a lost race is data loss if nobody is told about it."""


class PoolMissing(ResearchError):
    """The tagging job or the surveyor ran before `survey pool` froze a candidate pool."""


class PoolStale(ResearchError):
    """The frozen pool was built against a different theme digest than the one now
    signed off — the pool answers a question the developer no longer asked."""


class TaggerOutputInvalid(ResearchError):
    """A tagger response named no chunk from its own batch — nothing is salvageable."""


class SurveyOutputInvalid(ResearchError):
    """A Claude role returned no structured output, or output its schema rejects."""


class EvidenceUnresolvable(ResearchError):
    """A candidate cites a chunk id that `source_chunks` does not hold."""


class AmendmentRefused(ResearchError):
    """A theme amendment would orphan a cycle (slug removal) or is malformed."""


class R3Incomplete(ResearchError):
    """`survey finalize` found open work: an unscouted gap or a stale digest."""
