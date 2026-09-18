"""FeatureInstance rendering (D65): existence cited through `since` or, for an absence, at status
level — and the shapes a status cannot carry."""
import pytest
from ruamel.yaml import YAML

from langatlas_research.drafts import (
    Characteristic, Evidence, InstanceDraft, InstanceNote, Proposer, SyntaxExample,
)
from langatlas_research.errors import InvalidDraft, UnsourcedNode
from langatlas_research.mint import render_draft
from langatlas_validate.normalize import normalize_record
from langatlas_validate.schema import validate_record

yaml = YAML(typ="safe")
PROPOSER = Proposer(agent="r5-reality-checker", model="claude", prompt_version="v-test")
REF = (Evidence(source="python-langref-3", locator="§3.1"),)
CITED = [{"source": "python-langref-3", "locator": "§3.1"}]


def _draft(**over) -> InstanceDraft:
    base = dict(language="python", feature="dynamic-typing", status="present", evidence=REF,
                proposer=PROPOSER, chat_run_id="2026-09-20-r5-classify-01-typing-python-01",
                since="3.14")
    return InstanceDraft(**(base | over))


def test_a_present_instance_is_cited_through_its_since():
    minted = render_draft(_draft())
    assert minted.path == "languages/python/instances/dynamic-typing.yaml"
    assert minted.kind == "feature-instance"
    assert minted.node_ids == ("fi.python.dynamic-typing",)
    data = yaml.load(minted.text)
    assert data["since"] == {"value": "3.14", "sources": CITED}
    assert "sources" not in data
    assert validate_record(data, "feature-instance") == []
    assert normalize_record(minted.text, "feature-instance") == minted.text


def test_an_absent_instance_cites_at_status_level_and_scope_comes_first():
    minted = render_draft(_draft(status="absent", since=None,
                                 absence_scope="The reference lists every checking phase."))
    data = yaml.load(minted.text)
    assert data["sources"] == CITED and "since" not in data
    assert minted.text.index("absence_scope:") < minted.text.index("sources:")
    assert validate_record(data, "feature-instance") == []


def test_provenance_names_the_classifier_run_and_the_sweep_questionnaire():
    provenance = yaml.load(render_draft(_draft()).text)["provenance"]
    assert provenance["candidate_source"] == "sweep-questionnaire"
    assert provenance["chat_run_id"] == "2026-09-20-r5-classify-01-typing-python-01"
    assert provenance["proposer"]["agent"] == "r5-reality-checker"


def test_every_field_of_a_partial_instance_round_trips():
    data = yaml.load(render_draft(_draft(
        status="partial",
        notes=(InstanceNote(key="n-annotations-only", type="limitation",
                            text="Annotations are not enforced.", evidence=REF),),
        characteristics=(Characteristic(key="c-runtime-checks",
                                        text="Type errors surface at run time.", evidence=REF),),
        syntax=(SyntaxExample(key="rebinding", title="Rebinding a name to another type",
                              code="x = 1\nx = 'one'\n", evidence=REF),))).text)
    assert data["notes"][0]["type"] == "limitation"
    assert data["characteristics"][0]["key"] == "c-runtime-checks"
    assert data["syntax"][0]["origin"] == "original"
    assert validate_record(data, "feature-instance") == []


def test_a_present_or_partial_instance_without_a_since_is_refused():
    for status in ("present", "partial"):
        with pytest.raises(InvalidDraft, match="since is required"):
            render_draft(_draft(status=status, since=None))


def test_an_instance_with_no_citation_is_unmintable():
    with pytest.raises(UnsourcedNode, match="#exists"):
        render_draft(_draft(evidence=()))


def test_an_absent_instance_needs_its_scope_and_describes_nothing_present():
    with pytest.raises(InvalidDraft, match="absence_scope"):
        render_draft(_draft(status="absent", since=None))
    with pytest.raises(InvalidDraft, match="describes nothing present"):
        render_draft(_draft(status="absent", absence_scope="The reference lists every form."))


def test_a_scope_on_a_present_instance_is_refused():
    with pytest.raises(InvalidDraft, match="absent instance only"):
        render_draft(_draft(absence_scope="stray"))


def test_typed_notes_belong_to_partial_only():
    note = InstanceNote(key="n-x", type="extra", text="Extra.", evidence=REF)
    with pytest.raises(InvalidDraft, match="partial instance only"):
        render_draft(_draft(notes=(note,)))


def test_entry_keys_are_checked_before_the_schema_sees_them():
    with pytest.raises(InvalidDraft, match="c-"):
        render_draft(_draft(characteristics=(Characteristic(key="runtime", text="t",
                                                            evidence=REF),)))
    with pytest.raises(InvalidDraft, match="syntax key"):
        render_draft(_draft(syntax=(SyntaxExample(key="Not A Slug", title="t", code="x",
                                                  evidence=REF),)))
