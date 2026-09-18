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
    """Every evidence chunk id an R4 role named for one entry failed to resolve, so the entry
    has no source at all — unmintable per D4/§6.1."""


class AmendmentRefused(ResearchError):
    """A theme amendment would orphan a cycle (slug removal) or is malformed."""


class R3Incomplete(ResearchError):
    """`survey finalize` found open work: an unscouted gap or a stale digest."""


class DraftMissing(ResearchError):
    """R4 ran before `draft atomize` wrote a carve plan for this cycle."""


class DraftOutputInvalid(ResearchError):
    """An R4 Claude role returned output its schema or this package's binding rejects."""


class UndebatedCarve(ResearchError):
    """A contested carve reached the mint step without a debate or a developer waiver.
    D5's rule is that contested carves are debated, not that debates are optional."""


class NotAdmissible(ResearchError):
    """Minting was attempted on an entry the D24 gate did not admit. The gate is the
    admissibility authority (D1/D4); there is no override."""


class DebateIncomplete(ResearchError):
    """A debate ran out of messages, or the moderator returned no resolution — the record
    is kept, and nothing it touched is mintable until the developer re-runs it."""


class R4Incomplete(ResearchError):
    """`draft finalize` found open work: an undebated contested carve, an unverified
    entry, or an entry the gate refused."""


class ControversyInputRefused(ResearchError):
    """§6.4's allow-list: the assessor sees exactly `debates`, `contradiction_records`,
    `verdicts`, `source_strength` and `assessment_spread`. Everything human-challenge-derived
    — GitHub activity, challenge counts, and (2026-07-20) a contradiction record's
    `closure_attempt.outcome` — is refused here rather than filtered later, because a filter
    that is ever forgotten silently calibrates the assessor against a fiction."""


class AssessorOutputInvalid(ResearchError):
    """The assessor returned a level outside 0-3, or output its schema rejects. There is no
    repair turn: the fact keeps whatever level it already had and the run says so."""


class R5NotReady(ResearchError):
    """R5 was started on a cycle that has not finished R4, has no features to check, or already
    holds classifier runs that starting over would silently discard."""


class RealityCheckMissing(ResearchError):
    """An R5 step ran before `reality compile` opened the cycle's reality check."""


class RealityOutputInvalid(ResearchError):
    """The reality checker returned output its schema or this package's shape rules reject, or a
    reality-check file failed its own schema. There is no repair turn: the transcript is logged
    (D18), and the developer reads it and re-runs the language."""


class R5Incomplete(ResearchError):
    """`reality finalize` found open work: an unclassified language, or a cell that never
    reached the gate."""
