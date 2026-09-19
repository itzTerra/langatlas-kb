import pytest
from pydantic import ValidationError

from langatlas_research.draft.findings import (
    FindingOut, STRUCTURE_ELEMENTS, friction_entry,
)
from langatlas_research.draft.plan import build_plan_record
from langatlas_research.schema import validate_research_record


def test_a_friction_finding_must_name_its_area_and_element():
    with pytest.raises(ValidationError):
        FindingOut(kind="structure-friction", detail="no slot for refinement")
    with pytest.raises(ValidationError):
        FindingOut(kind="structure-friction", detail="d", area="ontology")


def test_only_a_friction_finding_may_carry_area_or_element():
    with pytest.raises(ValidationError):
        FindingOut(kind="rule-candidate", detail="d", area="ontology")


def test_an_element_outside_the_closed_vocabulary_is_refused():
    with pytest.raises(ValidationError):
        FindingOut(kind="structure-friction", detail="d", area="ontology", element="vibes")


def test_as_entry_drops_unset_fields_so_old_finding_kinds_keep_their_shape():
    old = FindingOut(kind="rule-candidate", detail="d", keys=["a"])
    assert old.as_entry() == {"kind": "rule-candidate", "detail": "d", "keys": ["a"]}


def test_friction_entry_builds_a_valid_finding_dict():
    entry = friction_entry("d", keys=["a"], element="realizes")
    assert entry == {"kind": "structure-friction", "detail": "d", "keys": ["a"],
                     "area": "ontology", "element": "realizes"}
    assert "realizes" in STRUCTURE_ELEMENTS


def test_the_plan_schema_accepts_friction_and_requires_its_classification(
        research_repo, signed_cycle):
    plan = build_plan_record(cycle=signed_cycle, ontologist_run_id="r",
                             generated_at="2026-09-20T10:00:00Z")
    plan["findings"] = [friction_entry("d", keys=["a"], element="realizes")]
    assert validate_research_record(plan, "draft", repo_root=research_repo) == []
    plan["findings"] = [{"kind": "structure-friction", "detail": "d", "keys": []}]
    assert validate_research_record(plan, "draft", repo_root=research_repo) != []
