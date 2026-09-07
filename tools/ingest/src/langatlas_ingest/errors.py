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


class UnknownSearchMode(IngestError):
    """§8.6's retrieval variant axis is a closed set. Typed and raised at construction
    rather than producing an empty result set, because a silently-wrong mode in a
    benchmark arm would be recorded as a real measurement."""

    def __init__(self, mode: str):
        from langatlas_ingest.search import SEARCH_MODES

        super().__init__(f"unknown search mode {mode!r}; expected one of"
                         f" {', '.join(SEARCH_MODES)}")
        self.mode = mode


class BenchCorpusMismatch(IngestError):
    """The benchmark corpus rebuilt at production's chunk size does not reproduce
    production's chunk ids. Fatal rather than a warning: the golden set cites production
    ids, so every arm scored against a divergent corpus reports a uniform zero that reads
    as a model failure instead of a corpus failure."""

    def __init__(self, differences: list[str]):
        super().__init__("benchmark corpus does not match production:\n  "
                         + "\n  ".join(differences))
        self.differences = list(differences)


class BenchCorpusChunkSizeMismatch(IngestError):
    """`run_arm` was asked to score an arm against a bench corpus chunked at a
    different size than the arm itself declares. A live run once let exactly this
    happen through the CLI (fixed there with a `--chunk-target`/`--chunk-max` guard),
    but `run_arm` is the primary-matrix path too, and scoring a chunk-size mismatch
    reports a uniform garbage number that reads as a model finding rather than a setup
    mistake. Raised eagerly, before any embedding work starts, rather than left for a
    human to notice in a table of implausible numbers."""

    def __init__(self, arm_id: str, *, declared: tuple[int, int], recorded: tuple[int, int]):
        super().__init__(
            f"arm {arm_id!r} declares chunk size {declared[0]}/{declared[1]} but the"
            f" bench corpus was built at {recorded[0]}/{recorded[1]} — rebuild it at the"
            " arm's chunk size (bench-build --chunk-target/--chunk-max) before scoring"
            " this arm")
        self.arm_id = arm_id
        self.declared = declared
        self.recorded = recorded


class IncompleteMatrix(IngestError):
    """§8.6's decision rules were asked to conclude from a matrix with a hole in it.
    Raised rather than deciding on what is present: a rule comparing an arm against an
    absent one would silently become a different rule, and the verdict it produced would
    be indistinguishable from a real one."""

    def __init__(self, missing: list[str]):
        super().__init__("cannot decide with arms missing:\n  " + "\n  ".join(missing))
        self.missing = list(missing)


class CanaryPassed(IngestError):
    """Section 6.2's per-batch canary answered `supported` to a known-bad item.

    Raised — not logged — because the correct response is to stop the batch. A verifier
    that admits a fabricated locator has stopped reading, and every verdict it produces
    for the rest of the night is worthless in the one direction the project cannot
    tolerate (a false accept poisons a public, RAG-recycled corpus)."""

    def __init__(self, item_ids):
        super().__init__("verification canaries passed (they must not): "
                         + ", ".join(item_ids))
        self.item_ids = list(item_ids)


class NoVerifierRegistered(IngestError):
    """`golden-score` was asked to score a verifier that does not exist yet. Typed so the
    CLI can say "2D has not shipped the verifier" instead of reporting a 0% error rate
    over zero items, which would read as a passing calibration."""

    def __init__(self, key: str):
        super().__init__(f"no verifier registered: set `goldens.{key}` in"
                         " config/ingest.yaml or pass an explicit dotted path")
        self.key = key
