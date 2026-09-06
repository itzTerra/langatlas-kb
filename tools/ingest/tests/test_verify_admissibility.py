import pytest
from langatlas_ingest.verify.admissibility import FactOutcome, decide_fact
from langatlas_ingest.verify.sources import SourceFacts
from langatlas_ingest.verify.verdicts import PairVerdict

SF = {
    "a-src": SourceFacts("a-src", "A", "formal-spec", (),
                         {"author": [{"family": "Pierce"}], "publisher": "MIT Press"}),
    "b-src": SourceFacts("b-src", "B", "third-party-reference", (),
                         {"author": [{"family": "Scott"}], "publisher": "Morgan Kaufmann"}),
    "c-src": SourceFacts("c-src", "C", "third-party-reference", (),
                         {"author": [{"family": "Wiki"}], "publisher": "Wikimedia"}),
}


def pair(source_id, verdict="supported", locator="p. 1", since_status=None):
    return PairVerdict(fact_id="f-000000000001", source_id=source_id, locator=locator,
                       verdict=verdict, since_status=since_status)


class FakeQueue:
    def __init__(self, existing=()):
        self.filed = []
        self.bounced = []
        self.existing = list(existing)

    def file(self, *, kind, source_id, reason, detail=""):
        self.filed.append((kind, source_id, reason, detail))
        return len(self.filed)

    def open_entries(self, *, kind=None):
        return list(self.existing)

    def bounce(self, entry_id):
        self.bounced.append(entry_id)
        return len(self.bounced)


def test_one_supported_tier_a_citation_admits():
    got = decide_fact("f-000000000001", [pair("a-src")], SF)
    assert isinstance(got, FactOutcome)
    assert got.admissible is True
    assert got.verification == "verified"


def test_tier_c_alone_never_admits():
    # C/D corroborate only (Section 6.2's admissibility rule).
    got = decide_fact("f-000000000001", [pair("c-src")], SF)
    assert got.admissible is False
    assert got.verification == "failed"


def test_confidence_comes_from_the_lookup_not_from_the_caller():
    got = decide_fact("f-000000000001", [pair("a-src"), pair("b-src")], SF)
    assert got.confidence == "high"


def test_a_failed_fact_carries_no_confidence():
    assert decide_fact("f-000000000001", [pair("c-src")], SF).confidence is None


def test_a_partial_only_fact_bounces_for_claim_narrowing():
    queue = FakeQueue()
    got = decide_fact("f-000000000001", [pair("a-src", verdict="partial")], SF,
                      queue=queue)
    assert got.admissible is False
    assert got.bounced is True
    assert "narrow" in got.bounce_reason
    assert queue.filed and queue.filed[0][0] == "pending-source"


def test_an_unsupported_fact_bounces_with_a_rationale():
    queue = FakeQueue()
    got = decide_fact("f-000000000001", [pair("a-src", verdict="unsupported")], SF,
                      queue=queue)
    assert got.admissible is False
    assert got.bounced is True
    assert got.bounce_reason


def test_the_bounce_budget_is_exhausted_after_two():
    queue = FakeQueue(existing=[{"id": 7, "source_id": "a-src", "bounce_count": 2}])
    got = decide_fact("f-000000000001", [pair("a-src", verdict="partial")], SF,
                      queue=queue, bounce_budget=2)
    assert got.bounced is False
    assert got.exhausted is True
    assert queue.bounced == []


def test_an_existing_queue_entry_is_bounced_rather_than_refiled():
    queue = FakeQueue(existing=[{"id": 7, "source_id": "a-src", "bounce_count": 0}])
    decide_fact("f-000000000001", [pair("a-src", verdict="partial")], SF, queue=queue)
    assert queue.bounced == [7]
    assert queue.filed == []


def test_an_admitted_fact_never_bounces():
    queue = FakeQueue()
    got = decide_fact("f-000000000001", [pair("a-src"), pair("b-src", verdict="partial")],
                      SF, queue=queue)
    assert got.admissible is True
    assert got.bounced is False
    assert queue.filed == []


def test_a_contradicted_secondary_mints_while_the_fact_still_admits(tmp_path):
    path = tmp_path / "contradictions.yaml"
    path.write_text("contradictions: []\n")
    pairs = [pair("a-src"), pair("b-src", verdict="contradicted")]
    got = decide_fact("f-000000000001", pairs, SF, contradictions_path=path)
    assert got.admissible is True
    assert got.verification == "verified"
    assert len(got.contradiction_ids) == 1


def test_a_contradicted_only_citation_blocks_and_mints_nothing(tmp_path):
    path = tmp_path / "contradictions.yaml"
    path.write_text("contradictions: []\n")
    got = decide_fact("f-000000000001", [pair("a-src", verdict="contradicted")], SF,
                      contradictions_path=path)
    assert got.admissible is False
    assert got.contradiction_ids == ()


def test_an_as_of_since_admits_but_lands_partially_verified():
    got = decide_fact("f-000000000001", [pair("a-src", since_status="as-of-supported")],
                      SF, has_since=True)
    assert got.admissible is True
    assert got.verification == "partially-verified"
    assert got.confidence == "low"


def test_an_absent_fact_on_one_source_is_capped_at_medium():
    got = decide_fact("f-000000000001", [pair("a-src")], SF, absent=True)
    assert got.confidence == "medium"


def test_no_pairs_at_all_is_unverified_and_does_not_bounce():
    queue = FakeQueue()
    got = decide_fact("f-000000000001", [], SF, queue=queue)
    assert got.verification == "unverified"
    assert got.bounced is False
    assert queue.filed == []
