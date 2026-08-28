class IngestError(Exception):
    """Base for every failure this package raises."""


class ExtractionFailed(IngestError):
    def __init__(self, source_id: str, reason: str):
        super().__init__(f"{source_id}: extraction failed: {reason}")
        self.source_id = source_id
        self.reason = reason


class QaHardGate(IngestError):
    """D37: encoding/extraction-collapse failures hard-gate promotion into source_chunks."""

    def __init__(self, source_id: str, checks):
        detail = ", ".join(c.check_id for c in checks)
        super().__init__(f"{source_id}: QA hard gate failed: {detail}")
        self.source_id = source_id
        self.checks = list(checks)


class UnknownSource(IngestError):
    pass


class UnknownQueueEntry(IngestError):
    """A sourcing-queue operation named an id no row carries. Typed rather than an
    AttributeError on a None fetch, so D24's bounce-budget logic gets a signal it can
    act on instead of a traceback from inside psycopg."""

    def __init__(self, entry_id: int):
        super().__init__(f"no sourcing_queue entry with id {entry_id}")
        self.entry_id = entry_id


class SnapshotMissing(IngestError):
    def __init__(self, source_id: str):
        super().__init__(f"no snapshot stored for source {source_id!r}")
        self.source_id = source_id


class GoldenEntryInvalid(IngestError):
    """A hand-authored golden-set entry (§8.6) has an expectation shape `run_eval` can't
    score: neither key set, only a mistyped one (`expected_chunk` instead of
    `expected_chunks`), or both keys set at once (ambiguous — see `eval._validate`). Typed
    and raised eagerly rather than silently scoring 0.0 or an out-of-range number — for a
    40-60-query set either would read as a plausible bad score instead of an authoring
    mistake."""

    def __init__(self, entry_id, reason):
        super().__init__(f"golden entry {entry_id!r} {reason}")
        self.entry_id = entry_id
        self.reason = reason


class GoldenItemInvalid(IngestError):
    """A committed golden item (Section 6.4) fails the authoring contract: an unknown
    stratum, a verdict its stratum cannot produce, an over-cap quote, an uncurated LLM
    candidate. Raised eagerly rather than scored around — a malformed calibration item
    silently shifts the measured false-accept rate, which is the one number the project
    publishes as an honesty feature."""

    def __init__(self, item_id, reason):
        super().__init__(f"golden item {item_id!r} {reason}")
        self.item_id = item_id
        self.reason = reason
