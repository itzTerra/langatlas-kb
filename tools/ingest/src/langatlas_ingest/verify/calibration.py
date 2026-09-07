from langatlas_ingest.config import IngestConfig
from langatlas_ingest.goldens.score import VerdictOutcome
from langatlas_ingest.verify.inputs import CitationInput, ClaimInput
from langatlas_ingest.verify.pipeline import VerifyDeps, verify_pair


class GoldenVerifier:
    """The adapter between 2B's `Verifier` protocol and 2D's pipeline.

    2B deliberately specified the protocol as a bare `(item) -> VerdictOutcome` callable
    with no construction and no configuration, so the harness could ship before any
    verifier existed. That leaves this class holding the session: the connection, the
    `RunContext` and the injected collaborators are opened once and reused across the
    whole 200-300-item run rather than per item.

    An item's `stratum`, `expected_verdict`, `notes`, and its own id are never read — the
    verifier must see exactly what a real pair would.
    """

    def __init__(self, *, config: IngestConfig | None = None, deps=None, conn=None,
                 ctx=None):
        self.config = config
        self.deps = deps
        self.conn = conn
        self.ctx = ctx
        self._owns_session = False

    def _ensure_session(self) -> None:
        """Lazily open the connection/RunContext/deps this instance will reuse.

        @pre no-op when `deps` was already injected (tests, or a caller building its own
            session) — only the module-level `verify_golden_item` singleton ever opens
            one for real.
        """
        if self.deps is not None:
            return
        from langatlas_ingest.db import connect
        from langatlas_pipeline.providers.core import RunContext

        self.config = self.config or IngestConfig.load()
        self.conn = self.conn or connect(self.config.dsn)
        self.ctx = self.ctx or RunContext.start(kind="verification", slug="golden-score")
        self.deps = VerifyDeps.build(self.conn, self.ctx, config=self.config)
        self._owns_session = True

    def __call__(self, item) -> VerdictOutcome:
        """Score one golden item through the real D24 pipeline.

        @param item - a `goldens.items.VerifierItem`
        @returns the `VerdictOutcome` `goldens.score.score_verifier` expects
        """
        self._ensure_session()
        claim = ClaimInput(fact_id=item.claim.fact_id, claim=item.claim.text,
                           since=item.claim.since, status=item.claim.status,
                           absence_scope=item.claim.absence_scope,
                           feature_aliases=item.claim.feature_aliases)
        citation = CitationInput(item.citation.source, item.citation.locator,
                                 item.citation.quote)
        verdict = verify_pair(self.ctx, self.conn, claim=claim, citation=citation,
                              config=self.config, deps=self.deps)
        return VerdictOutcome(verdict=verdict.verdict, annotations=verdict.annotations,
                              per_assertion=tuple(a.as_dict()
                                                  for a in verdict.per_assertion),
                              model=verdict.model)

    def close(self) -> None:
        """Release the session this instance opened, if any.

        @pre no-op for an injected session — closing collaborators this instance never
            opened would break the caller that still owns them.
        """
        if not self._owns_session:
            return
        if self.ctx is not None:
            self.ctx.close()
        if self.conn is not None:
            self.conn.close()
        self.deps = self.ctx = self.conn = None
        self._owns_session = False


# The callable `config/ingest.yaml`'s `goldens.verifier_entry_point` names. A module-level
# instance rather than a function, so one `golden-score` run opens one session.
verify_golden_item = GoldenVerifier()


def reset_session() -> None:
    """Drop the process-wide session. Tests only."""
    verify_golden_item.close()
