import pytest

from langatlas_research.draft.evidence import EvidenceItem, as_drafts, bind_evidence
from langatlas_research.errors import EvidenceUnresolvable


def test_a_chunk_id_becomes_a_machine_produced_citation(fake_lookup):
    entries, warnings = bind_evidence([EvidenceItem(chunk_id="scott-plp#c00310")],
                                      lookup=fake_lookup, what="static-typing")
    assert entries == [{"source": "scott-plp", "locator": "§7.2",
                        "chunk_id": "scott-plp#c00310"}]
    assert warnings == []


def test_a_verbatim_quote_from_the_cited_chunk_is_kept(fake_lookup):
    entries, warnings = bind_evidence(
        [EvidenceItem(chunk_id="scott-plp#c00310",
                      quote="Static typing checks types before the program runs.")],
        lookup=fake_lookup, what="static-typing")
    assert entries[0]["quote"] == "Static typing checks types before the program runs."
    assert warnings == []


def test_a_quote_that_is_not_in_its_chunk_is_dropped_but_the_citation_survives(fake_lookup):
    entries, warnings = bind_evidence(
        [EvidenceItem(chunk_id="scott-plp#c00310", quote="Static typing is always better.")],
        lookup=fake_lookup, what="static-typing")
    assert "quote" not in entries[0] and entries[0]["source"] == "scott-plp"
    assert any("not verbatim" in w for w in warnings)


def test_an_over_cap_quote_is_dropped(fake_lookup):
    long_quote = " ".join(["word"] * 51)
    entries, warnings = bind_evidence(
        [EvidenceItem(chunk_id="scott-plp#c00310", quote=long_quote)],
        lookup=fake_lookup, what="static-typing")
    assert "quote" not in entries[0]
    assert any("50 words" in w for w in warnings)


def test_whitespace_differences_do_not_break_a_genuine_quote(fake_lookup):
    entries, _ = bind_evidence(
        [EvidenceItem(chunk_id="scott-plp#c00310",
                      quote="Static  typing\nchecks types before the program runs.")],
        lookup=fake_lookup, what="x")
    assert entries[0]["quote"].startswith("Static")


def test_duplicate_chunk_ids_collapse(fake_lookup):
    entries, _ = bind_evidence([EvidenceItem(chunk_id="scott-plp#c00310"),
                                EvidenceItem(chunk_id="scott-plp#c00310")],
                               lookup=fake_lookup, what="x")
    assert len(entries) == 1


def test_an_unresolvable_chunk_id_is_a_typed_failure(fake_lookup):
    with pytest.raises(EvidenceUnresolvable):
        bind_evidence([EvidenceItem(chunk_id="made-up#c99999")], lookup=fake_lookup,
                      what="static-typing")


def test_a_partly_unresolvable_list_keeps_what_resolved_and_warns(fake_lookup):
    entries, warnings = bind_evidence(
        [EvidenceItem(chunk_id="scott-plp#c00310"), EvidenceItem(chunk_id="made-up#c1")],
        lookup=fake_lookup, what="static-typing")
    assert len(entries) == 1
    assert any("made-up#c1" in w for w in warnings)


def test_plan_entries_convert_to_3as_evidence_tuples():
    drafts = as_drafts([{"source": "s", "locator": "§1", "chunk_id": "s#c1"},
                        {"source": "t", "locator": "§2", "quote": "q", "chunk_id": "t#c2"}])
    assert [(e.source, e.locator, e.quote) for e in drafts] == [("s", "§1", None),
                                                                ("t", "§2", "q")]
