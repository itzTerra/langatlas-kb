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
