import random
from pathlib import Path
from pydantic import BaseModel, Field
from ruamel.yaml import YAML
from langatlas_ingest.config import IngestConfig
from langatlas_ingest.goldens.items import STRATUM_VERDICTS
from langatlas_ingest.store import SourceChunksStore
from langatlas_pipeline.prompts import load_prompt

_yaml = YAML()
_yaml.default_flow_style = False

# How much evidence one generation call sees. Small on purpose: a wide window makes the
# model summarise the source instead of reading one passage closely, and the obscure-locus
# targeting Section 6.4 asks for depends on a narrow view.
CHUNKS_PER_CALL = 3

STRATUM_DEFINITIONS = {
    "correct": "a claim the evidence fully supports, stated plainly",
    "overstated-claim": "a claim whose core is supported but which generalises beyond"
                        " what the evidence says (scope, universality, or strength)",
    "fabricated-locator": "a supportable claim cited to a locator that points nowhere in"
                          " this source",
    "wrong-since-off-by-one": "a correct claim whose `since` version is one release off",
    "wrong-since-off-by-major": "a correct claim whose `since` version is a major version off",
    "contradicted": "a claim the evidence directly contradicts",
    "right-claim-wrong-source": "a claim that is true in general but that this evidence"
                                " does not carry",
    "category-error": "a claim that asks the wrong kind of question of this evidence",
    "fabricated-combination": "a feature-instance pairing that does not exist",
    "quote-mismatch": "a claim whose quote does not appear in this source",
    "quote-found-elsewhere": "a claim whose quote is real but sits elsewhere in the source",
    "ocr-noisy": "a correct claim whose quote carries plausible extraction noise",
    "paraphrase-heavy-correct": "a correct claim sharing almost no vocabulary with the"
                                " evidence",
}


class Candidate(BaseModel):
    stratum: str
    claim_kind: str
    claim_text: str
    rendered: str = ""
    expected_verdict: str
    locator: str
    quote: str | None = None
    expected_annotations: list[str] = Field(default_factory=list)
    rationale: str = ""
    since: str | None = None
    expected_since_status: str | None = None


class CandidateBatch(BaseModel):
    candidates: list[Candidate]


def _sample_chunks(conn, source_id: str, *, topic: str | None, ctx,
                   config: IngestConfig):
    if topic:
        from langatlas_ingest.search import SourceSearch

        hits = SourceSearch(conn, ctx, config=config).search(
            topic, k=CHUNKS_PER_CALL, source_ids=[source_id])
        return [hit.chunk for hit in hits]
    chunks = SourceChunksStore(conn).by_source(source_id)
    # Deterministic sampling would draw the same passages every batch; a seeded shuffle
    # keeps the run reproducible from its transcript while still moving through the book.
    rng = random.Random(f"{source_id}:{len(chunks)}")
    return rng.sample(chunks, min(CHUNKS_PER_CALL, len(chunks)))


def generate_candidates(ctx, conn, *, source_id: str, stratum: str, count: int,
                        topic: str | None = None, config: IngestConfig | None = None,
                        chunks=None) -> list[dict]:
    """Draft `count` candidate golden items for one stratum, grounded in real chunks.

    Volume only: every returned candidate carries `curated: false`, and the loader
    refuses to read an uncurated item, so nothing here can reach the committed set
    without a human having read it (Section 6.4).

    @param ctx - a `RunContext`; chunk text passes through its D31 door before it reaches
        the model, and the call is logged (D18)
    @param chunks - explicit chunks, bypassing sampling (tests, and hand-picked passages)

    @pre `stratum` is one of the 13 strata

    @returns candidate dicts in the committed YAML's own shape
    """
    config = config or IngestConfig.load()
    chunks = chunks if chunks is not None else _sample_chunks(
        conn, source_id, topic=topic, ctx=ctx, config=config)
    if not chunks:
        return []
    by_locator = {chunk.locator: chunk for chunk in chunks}
    evidence = "\n\n".join(
        ctx.tool_result(tool="golden-candidate", text=f"[{chunk.locator}] {chunk.text}",
                        source_id=source_id)
        for chunk in chunks)

    prompt = load_prompt("golden-candidate")
    messages = prompt.render(
        stratum=stratum, stratum_definition=STRATUM_DEFINITIONS[stratum],
        expected_verdicts=", ".join(sorted(STRATUM_VERDICTS[stratum])),
        count=str(count), source_id=source_id, evidence=evidence)
    result = ctx.complete(config.golden_candidate_model, messages, prompt=prompt,
                          schema=CandidateBatch)

    drafted = []
    for index, candidate in enumerate(result.parsed.candidates, start=1):
        matched = by_locator.get(candidate.locator)
        drafted.append({
            "id": f"v-{source_id}-{stratum}-{index:04d}",
            "stratum": candidate.stratum or stratum,
            "expected_verdict": candidate.expected_verdict,
            "claim": {"kind": candidate.claim_kind, "text": candidate.claim_text,
                      "rendered": candidate.rendered, "since": candidate.since,
                      "expected_since_status": candidate.expected_since_status},
            "citation": {"source": source_id, "locator": candidate.locator,
                         "quote": candidate.quote},
            # A fabricated locator matches no real chunk, so it grounds in nothing — the
            # empty list is the honest record, not a lookup failure to paper over.
            "evidence_chunk_ids": [matched.chunk_id] if matched else [],
            "expected_annotations": list(candidate.expected_annotations),
            "authored_by": "llm-candidate",
            "curated": False,
            "notes": candidate.rationale,
        })
    return drafted


def write_candidate_file(candidates: list[dict], path: Path) -> Path:
    """Write drafts to a review file. Never writes into a committed set directory
    directly — curation is a separate, deliberate move of the item."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as handle:
        handle.write("# Generated candidates — NOT a committed golden set.\n"
                     "# Read each item, fix it, then set `curated: true` and move it into\n"
                     "# tests/golden/verifier/. The loader refuses uncurated items.\n")
        _yaml.dump({"version": 1, "items": candidates}, handle)
    return path
