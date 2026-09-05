from langatlas_ingest.eval import run_eval  # noqa: F401 — contract reference
from langatlas_ingest.goldens.derive import derive_queries, write_queries
from langatlas_ingest.goldens.items import Citation, Claim, VerifierItem


def item(item_id, stratum, quote=None, chunks=("ctm#c00001",)):
    return VerifierItem(
        id=item_id, stratum=stratum, expected_verdict="supported",
        claim=Claim(kind="instance-exists",
                    text="instance-exists(i-oz-lazy-evaluation, status=present)",
                    rendered="Oz supports lazy evaluation."),
        citation=Citation(source="ctm", locator="p. 1", quote=quote),
        evidence_chunk_ids=chunks)


def test_only_correct_stratum_items_are_derived_from():
    items = [item("a", "correct", quote="lazy evaluation defers a computation"),
             item("b", "contradicted", quote="something wrong")]
    assert [q["id"] for q in derive_queries(items)] == ["retrieval-a"]


def test_a_derived_query_carries_the_evidence_chunk_as_its_expectation():
    query = derive_queries([item("a", "correct",
                                 quote="lazy evaluation defers a computation")])[0]
    assert query["expected_chunks"] == ["ctm#c00001"]
    assert "expected_sources" not in query      # run_eval rejects entries setting both


def test_an_item_without_a_quote_derives_its_query_from_the_rendered_claim():
    query = derive_queries([item("a", "correct")])[0]
    assert query["query"] == "Oz supports lazy evaluation."


def test_an_item_with_no_evidence_chunks_is_skipped():
    assert derive_queries([item("a", "correct", chunks=())]) == []


def test_written_queries_load_through_run_evals_own_reader(tmp_path):
    from langatlas_ingest.eval import load_entries, _validate
    path = write_queries(derive_queries([item("a", "correct")]),
                         tmp_path / "queries-typing.yaml", theme="typing")
    entries = load_entries(path.parent)
    assert len(entries) == 1
    _validate(entries[0])       # raises GoldenEntryInvalid if the shape is wrong
