"""Assembly is the half of the assessor that has to be right whatever any model says: it is
where §6.4's exclusions are enforced, and it runs with no provider at all."""
import pytest

from langatlas_ingest.verify.verdicts import PairVerdict
from langatlas_research.controversy.assemble import (
    assemble_inputs, contradiction_projection, fact_field, source_strength,
)


class _Ledger:
    def __init__(self, rows):
        self._rows = rows

    def latest_for(self, fact_id):
        return [r for r in self._rows if r.fact_id == fact_id]


def _tier(source_id, tier, **csl):
    return type("S", (), {"id": source_id, "tier": tier, "grounding": "",
                          "locator_kinds": (), "csl": csl})()


FACT = {"fact_id": "f-aaaaaaaaaaaa",
        "claim": "node-definition(structural-typing, sha256-16=0123456789abcdef)",
        "record_path": "features/structural-typing.yaml",
        "sources": [{"source": "pierce-tapl-2002", "locator": "p. 251"},
                    {"source": "scott-plp", "locator": "§7.2.4"}]}

SOURCES = {"pierce-tapl-2002": _tier("pierce-tapl-2002", "A", publisher="MIT Press",
                                     author=[{"family": "Pierce", "given": "B"}]),
           "scott-plp": _tier("scott-plp", "A", publisher="Morgan Kaufmann",
                              author=[{"family": "Scott", "given": "M"}])}


def test_fact_field_reads_the_claim_kind():
    assert fact_field(FACT["claim"]) == "base"
    assert fact_field("characteristic(fi.rust.pattern-matching, c-exhaustive, sha256-16=ab)") \
        == "characteristic"
    assert fact_field("quality-assessment(edge.affects-quality.x.y, a-1)") == "quality-assessment"


def test_verdict_rows_carry_field_and_tier_and_a_stable_citation_index():
    ledger = _Ledger([
        PairVerdict(fact_id="f-aaaaaaaaaaaa", source_id="scott-plp", locator="§7.2.4",
                    verdict="contradicted"),
        PairVerdict(fact_id="f-aaaaaaaaaaaa", source_id="pierce-tapl-2002", locator="p. 251",
                    verdict="supported")])
    inputs = assemble_inputs(FACT, record={}, ledger=ledger, source_facts=SOURCES,
                             contradictions=[], debates={})
    assert sorted(inputs.verdicts, key=lambda v: v["citation"]) == [
        {"fact": "f-aaaaaaaaaaaa", "citation": 1, "verdict": "supported",
         "field": "base", "tier": "A"},
        {"fact": "f-aaaaaaaaaaaa", "citation": 2, "verdict": "contradicted",
         "field": "base", "tier": "A"}]


def test_a_since_status_adds_its_own_row_without_replacing_base():
    ledger = _Ledger([PairVerdict(fact_id="f-aaaaaaaaaaaa", source_id="pierce-tapl-2002",
                                  locator="p. 251", verdict="partial",
                                  since_status="as-of-supported")])
    inputs = assemble_inputs(FACT, record={}, ledger=ledger, source_facts=SOURCES,
                             contradictions=[], debates={})
    assert {(v["field"], v["verdict"]) for v in inputs.verdicts} == {
        ("base", "partial"), ("since", "partial")}


def test_source_strength_counts_supporting_citations_by_tier():
    pairs = [PairVerdict(fact_id="f-1", source_id="pierce-tapl-2002", locator="p. 251",
                         verdict="supported"),
             PairVerdict(fact_id="f-1", source_id="scott-plp", locator="§7.2.4",
                         verdict="supported")]
    assert source_strength(pairs, SOURCES) == {"tier_a": 2, "tier_b": 0,
                                               "independent_corroborations": 2}


def test_a_contradicted_citation_does_not_corroborate():
    pairs = [PairVerdict(fact_id="f-1", source_id="pierce-tapl-2002", locator="p. 251",
                         verdict="supported"),
             PairVerdict(fact_id="f-1", source_id="scott-plp", locator="§7.2.4",
                         verdict="contradicted")]
    assert source_strength(pairs, SOURCES) == {"tier_a": 1, "tier_b": 0,
                                               "independent_corroborations": 0}


def test_contradiction_projection_drops_everything_human_derived():
    record = {"id": "ctr-0123456789ab", "type": "verification", "status": "open",
              "participants": ["f-aaaaaaaaaaaa", "citation:scott-plp:§7.2.4"],
              "mechanism": "reconciler", "detail": "the two books disagree",
              "chat_run_id": "2026-09-16-r4-debate-01",
              "closure": {"method": "human-adjudication", "detail": "confirmed open"}}
    assert contradiction_projection(record) == {
        "id": "ctr-0123456789ab", "type": "verification", "status": "open", "participants": 2}


def test_contradiction_projection_maps_confirmed_open_down_to_open():
    """Finding 5: `status: confirmed-open` is set only via human-challenge resolution
    (`mechanism: challenge-resolution`, `closure.method: human-adjudication`) — the same
    human-derived signal `closure` is dropped for, just carried on `status` instead. The
    assessor must see an ordinary open contradiction, never a hint that a human specifically
    re-confirmed it."""
    record = {"id": "ctr-0123456789ab", "type": "verification", "status": "confirmed-open",
              "participants": ["f-aaaaaaaaaaaa"], "mechanism": "challenge-resolution",
              "closure": {"method": "human-adjudication", "detail": "confirmed open"}}
    assert contradiction_projection(record) == {
        "id": "ctr-0123456789ab", "type": "verification", "status": "open", "participants": 1}


def test_only_contradictions_naming_this_fact_are_included():
    mine = {"id": "ctr-111111111111", "type": "verification", "status": "open",
            "participants": ["citation:scott-plp:§7.2.4", "f-aaaaaaaaaaaa"]}
    theirs = {"id": "ctr-222222222222", "type": "verification", "status": "open",
              "participants": ["f-999999999999", "f-888888888888"]}
    inputs = assemble_inputs(FACT, record={}, ledger=_Ledger([]), source_facts=SOURCES,
                             contradictions=[mine, theirs], debates={})
    assert [c["id"] for c in inputs.contradiction_records] == ["ctr-111111111111"]


def test_the_records_debate_is_projected_through_3c_not_read_raw():
    debate = {"id": "d-01-typing-003", "cycle": 1, "theme": "typing",
              "target": {"list": "nodes", "key": "structural-typing"},
              "opened": "2026-09-16", "runs": {"debate": "r"}, "triggers": [],
              "personas": {"challenger_a": "the type theorist"}, "pre_challenge": {},
              "messages": [{"seq": 1, "role": "proposer", "persona": "p", "text": "t"}],
              "resolution": {"outcome": "escalated", "disposition": "escalate",
                             "standing_dissent": True, "rounds": 4,
                             "upheld_challenges": [], "rationale": "no convergence"}}
    inputs = assemble_inputs(FACT, record={"provenance": {"debate_id": "d-01-typing-003"}},
                             ledger=_Ledger([]), source_facts=SOURCES, contradictions=[],
                             debates={"d-01-typing-003": debate})
    assert inputs.debates == ({"id": "d-01-typing-003", "outcome": "escalated",
                              "standing_dissent": True, "rounds": 4},)


def test_a_dangling_debate_id_is_ignored_rather_than_raising():
    """A record can outlive a debate record the developer deleted. The assessor degrades to
    "no debate signal" — it never takes the nightly batch down with it."""
    inputs = assemble_inputs(FACT, record={"provenance": {"debate_id": "d-01-typing-404"}},
                             ledger=_Ledger([]), source_facts=SOURCES, contradictions=[],
                             debates={})
    assert inputs.debates == ()


def test_assembly_never_produces_a_forbidden_key():
    inputs = assemble_inputs(FACT, record={"provenance": {"debate_id": None},
                                           "notes": "agent prose"},
                             ledger=_Ledger([]), source_facts=SOURCES, contradictions=[],
                             debates={})
    assert set(inputs.as_dict()) == {"debates", "contradiction_records", "verdicts",
                                     "source_strength", "assessment_spread"}
