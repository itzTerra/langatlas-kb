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
