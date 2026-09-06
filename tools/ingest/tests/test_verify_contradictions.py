import pytest
from ruamel.yaml import YAML
from langatlas_ingest.verify.contradictions import (
    citation_participant, dissolves, load_records, mint_verification_record,
)
from langatlas_ingest.verify.verdicts import PairVerdict
from langatlas_validate.ids import contradiction_key

_yaml = YAML(typ="safe")


@pytest.fixture
def ledger_path(tmp_path):
    path = tmp_path / "contradictions.yaml"
    path.write_text("contradictions: []\n")
    return path


def pair(source_id="scott-plp", verdict="supported", locator="p. 12", since_status=None):
    return PairVerdict(fact_id="f-000000000001", source_id=source_id, locator=locator,
                       verdict=verdict, since_status=since_status)


def test_a_contradicted_secondary_citation_mints_a_record(ledger_path):
    pairs = [pair("a-src"), pair("b-src", verdict="contradicted")]
    minted = mint_verification_record(pairs, fact_id="f-000000000001",
                                      has_admissible_alternative=True, path=ledger_path,
                                      today="2026-09-06")
    assert len(minted) == 1
    records = load_records(ledger_path)
    assert records[0]["id"] == minted[0]
    assert records[0]["type"] == "verification"
    assert records[0]["mechanism"] == "verifier"
    assert records[0]["participants"] == sorted(
        ["f-000000000001", citation_participant("b-src", "p. 12")])


def test_a_contradicted_only_citation_mints_nothing(ledger_path):
    # Section 6.5: a contradicted primary/only citation blocks admission and mints
    # nothing. The fact never enters the store, so there is no disagreement to register.
    pairs = [pair("b-src", verdict="contradicted")]
    minted = mint_verification_record(pairs, fact_id="f-000000000001",
                                      has_admissible_alternative=False, path=ledger_path)
    assert minted == []
    assert load_records(ledger_path) == []


def test_partial_verdicts_never_mint(ledger_path):
    # Section 6.5, explicitly: `partial` verdicts never mint records.
    pairs = [pair("a-src"), pair("b-src", verdict="partial")]
    minted = mint_verification_record(pairs, fact_id="f-000000000001",
                                      has_admissible_alternative=True, path=ledger_path)
    assert minted == []


def test_unsupported_verdicts_never_mint(ledger_path):
    pairs = [pair("a-src"), pair("b-src", verdict="unsupported")]
    assert mint_verification_record(pairs, fact_id="f-000000000001",
                                    has_admissible_alternative=True,
                                    path=ledger_path) == []


def test_minting_the_same_conflict_twice_is_idempotent(ledger_path):
    pairs = [pair("a-src"), pair("b-src", verdict="contradicted")]
    first = mint_verification_record(pairs, fact_id="f-000000000001",
                                     has_admissible_alternative=True, path=ledger_path)
    second = mint_verification_record(pairs, fact_id="f-000000000001",
                                      has_admissible_alternative=True, path=ledger_path)
    assert first == second
    assert len(load_records(ledger_path)) == 1


def test_the_minted_id_is_the_content_key(ledger_path):
    pairs = [pair("a-src"), pair("b-src", verdict="contradicted")]
    minted = mint_verification_record(pairs, fact_id="f-000000000001",
                                      has_admissible_alternative=True, path=ledger_path)
    expected = contradiction_key(["f-000000000001",
                                  citation_participant("b-src", "p. 12")])
    assert minted == [expected]


def test_two_contradicted_secondaries_mint_two_records(ledger_path):
    pairs = [pair("a-src"),
             pair("b-src", verdict="contradicted"),
             pair("c-src", verdict="contradicted", locator="p. 99")]
    minted = mint_verification_record(pairs, fact_id="f-000000000001",
                                      has_admissible_alternative=True, path=ledger_path)
    assert len(minted) == 2
    assert len(set(minted)) == 2


def test_a_version_qualified_disagreement_dissolves_at_mint_time(ledger_path):
    # Closure v0: the evidence describes a later version than the claim's `since`, so the
    # two never actually disagreed. Section 6.5 wants that closed at mint time, not shown
    # to a reader as a live dispute.
    pairs = [pair("a-src"),
             pair("b-src", verdict="contradicted", since_status="as-of-supported")]
    minted = mint_verification_record(pairs, fact_id="f-000000000001",
                                      has_admissible_alternative=True, path=ledger_path,
                                      fact_since="3.10", evidence_since="3.12")
    record = load_records(ledger_path)[0]
    assert record["status"] == "dissolved"
    assert record["closure"]["method"] == "since-qualification"
    assert minted


def test_an_unqualifiable_disagreement_stays_open(ledger_path):
    pairs = [pair("a-src"), pair("b-src", verdict="contradicted")]
    mint_verification_record(pairs, fact_id="f-000000000001",
                             has_admissible_alternative=True, path=ledger_path)
    assert load_records(ledger_path)[0]["status"] == "open"


def test_dissolution_is_directional():
    # The evidence bounding from above dissolves the conflict; evidence about an EARLIER
    # version genuinely disagrees with a later `since` and must stay open.
    assert dissolves("3.10", "3.12") is True
    assert dissolves("3.12", "3.10") is False
    assert dissolves("3.10", "3.10") is True
    assert dissolves(None, "3.10") is False
    assert dissolves("3.10", None) is False
    # Unparseable versions are not silently dissolved — a closure the code cannot justify
    # is worse than an open record a human can read.
    assert dissolves("Fortran 77-ish", "3.10") is False


def test_a_closed_record_is_never_deleted_by_a_later_mint(ledger_path):
    pairs = [pair("a-src"), pair("b-src", verdict="contradicted")]
    mint_verification_record(pairs, fact_id="f-000000000001",
                             has_admissible_alternative=True, path=ledger_path)
    other = [pair("a-src"), pair("c-src", verdict="contradicted", locator="p. 99")]
    mint_verification_record(other, fact_id="f-000000000001",
                             has_admissible_alternative=True, path=ledger_path)
    assert len(load_records(ledger_path)) == 2


def test_the_written_ledger_passes_the_validator(ledger_path, tmp_path):
    from langatlas_validate.store import validate_contradictions
    pairs = [pair("a-src"), pair("b-src", verdict="contradicted")]
    mint_verification_record(pairs, fact_id="f-000000000001",
                             has_admissible_alternative=True, path=ledger_path,
                             today="2026-09-06")
    assert validate_contradictions(tmp_path) == []
