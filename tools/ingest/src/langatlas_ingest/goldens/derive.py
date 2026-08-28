from pathlib import Path
from ruamel.yaml import YAML

_yaml = YAML()
_yaml.default_flow_style = False

# Long verbatim quotes make a retrieval query that is really an exact-string lookup, which
# measures the FTS branch and nothing else. Section 8.6 wants three difficulty bands, so
# the derived (easiest) band stays short.
MAX_QUERY_WORDS = 12


def derive_queries(items, *, band: str = "exact-term", limit: int | None = None) -> list[dict]:
    """Derive retrieval golden queries from correct-stratum verifier items.

    Section 6.4 asks for "derived-first": every correct item already pairs a real claim
    with the real chunk that supports it, which is exactly a retrieval query with a known
    answer. Hand-authoring is then reserved for the paraphrase-hard and cross-source
    bands, where no verifier item supplies the query.

    @param items - loaded verifier items; non-`correct` strata are skipped, because their
        claims are deliberately wrong and a wrong claim is not a query with a right answer

    @returns entries in `run_eval`'s committed format
    """
    queries = []
    for item in items:
        if item.stratum != "correct" or not item.evidence_chunk_ids:
            continue
        text = item.citation.quote or item.claim.rendered or item.claim.text
        words = text.split()
        queries.append({"id": f"retrieval-{item.id}", "band": band,
                        "query": " ".join(words[:MAX_QUERY_WORDS]),
                        "expected_chunks": list(item.evidence_chunk_ids)})
        if limit is not None and len(queries) >= limit:
            break
    return queries


def write_queries(queries: list[dict], path: Path, *, theme: str) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as handle:
        handle.write(f"# {theme} retrieval golden queries — derived from the"
                     " correct-stratum verifier items (Section 6.4).\n")
        _yaml.dump({"queries": queries}, handle)
    return path
