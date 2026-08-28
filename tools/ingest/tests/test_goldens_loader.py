import pytest
from langatlas_ingest.errors import GoldenItemInvalid
from langatlas_ingest.goldens.loader import (
    load_controversy_cases, load_verifier_items, validate_controversy_cases,
    validate_items, validate_set,
)

ITEM = """
version: 1
items:
  - id: v-typing-0001
    stratum: correct
    expected_verdict: supported
    claim:
      kind: instance-exists
      text: 'instance-exists(i-haskell-lazy-evaluation, status=present)'
      status: present
    citation:
      source: vanroy-haridi-2003
      locator: '§4.5'
    evidence_chunk_ids: ['vanroy-haridi-2003#c01234']
"""


def write(tmp_path, text, name="items-test.yaml"):
    (tmp_path / name).write_text(text)
    return tmp_path


def test_a_well_formed_item_loads(tmp_path):
    items = load_verifier_items(write(tmp_path, ITEM))
    assert len(items) == 1
    assert items[0].claim.fact_id.startswith("f-")
    assert items[0].evidence_chunk_ids == ("vanroy-haridi-2003#c01234",)


def test_the_held_out_directory_is_excluded_by_default(tmp_path):
    write(tmp_path, ITEM)
    held = tmp_path / "held-out"
    held.mkdir()
    (held / "items-audit.yaml").write_text(ITEM.replace("v-typing-0001", "v-audit-0001"))
    assert [i.id for i in load_verifier_items(tmp_path)] == ["v-typing-0001"]
    both = load_verifier_items(tmp_path, include_held_out=True)
    assert sorted(i.id for i in both) == ["v-audit-0001", "v-typing-0001"]
    assert [i for i in both if i.id == "v-audit-0001"][0].held_out is True


def test_an_uncurated_llm_candidate_is_rejected_not_warned(tmp_path):
    text = ITEM + "    curated: false\n    authored_by: llm-candidate\n"
    with pytest.raises(GoldenItemInvalid, match="uncurated"):
        load_verifier_items(write(tmp_path, text))


def test_a_verdict_its_stratum_cannot_produce_is_an_error():
    from langatlas_ingest.goldens.items import Citation, Claim, VerifierItem
    bad = VerifierItem(id="v-x-0001", stratum="correct", expected_verdict="unsupported",
                       claim=Claim(kind="instance-exists", text="instance-exists(i-x, status=present)"),
                       citation=Citation(source="ctm", locator="p. 1"))
    errors = validate_items([bad], sources_dir=None)
    assert any("stratum 'correct'" in e for e in errors)


def test_an_over_cap_quote_is_an_error():
    from langatlas_ingest.goldens.items import Citation, Claim, VerifierItem
    bad = VerifierItem(id="v-x-0002", stratum="correct", expected_verdict="supported",
                       claim=Claim(kind="instance-exists", text="instance-exists(i-x, status=present)"),
                       citation=Citation(source="ctm", locator="p. 1",
                                         quote=" ".join(["word"] * 51)))
    assert any("quote" in e and "50" in e for e in validate_items([bad], sources_dir=None))


def test_a_quote_stratum_must_expect_its_annotation():
    from langatlas_ingest.goldens.items import Citation, Claim, VerifierItem
    bad = VerifierItem(id="v-x-0003", stratum="quote-found-elsewhere",
                       expected_verdict="supported",
                       claim=Claim(kind="instance-exists", text="instance-exists(i-x, status=present)"),
                       citation=Citation(source="ctm", locator="p. 1", quote="a quote"))
    assert any("quote-found-elsewhere" in e for e in validate_items([bad], sources_dir=None))


def test_an_absent_claim_without_its_absence_argument_is_an_error():
    from langatlas_ingest.goldens.items import Citation, Claim, VerifierItem
    bad = VerifierItem(id="v-x-0004", stratum="correct", expected_verdict="supported",
                       claim=Claim(kind="instance-exists",
                                   text="instance-exists(i-x, status=absent)", status="absent"),
                       citation=Citation(source="ctm", locator="p. 1"))
    errors = validate_items([bad], sources_dir=None)
    assert any("absence_scope" in e for e in errors)
    assert any("feature_aliases" in e for e in errors)


def test_a_malformed_locator_needs_the_explicit_flag():
    from langatlas_ingest.goldens.items import Citation, Claim, VerifierItem
    claim = Claim(kind="instance-exists", text="instance-exists(i-x, status=present)")
    bad = VerifierItem(id="v-x-0005", stratum="fabricated-locator",
                       expected_verdict="locator-not-found", claim=claim,
                       citation=Citation(source="ctm", locator="page twelve"))
    assert any("locator" in e for e in validate_items([bad], sources_dir=None))
    ok = VerifierItem(id="v-x-0006", stratum="fabricated-locator",
                      expected_verdict="locator-not-found", claim=claim,
                      citation=Citation(source="ctm", locator="page twelve"),
                      shape_invalid=True)
    assert validate_items([ok], sources_dir=None) == []


def test_duplicate_ids_are_an_error():
    from langatlas_ingest.goldens.items import Citation, Claim, VerifierItem
    claim = Claim(kind="instance-exists", text="instance-exists(i-x, status=present)")
    twin = [VerifierItem(id="v-dup", stratum="correct", expected_verdict="supported",
                         claim=claim, citation=Citation(source="ctm", locator="p. 1"))] * 2
    assert any("duplicate" in e for e in validate_items(twin, sources_dir=None))


def test_set_invariants_catch_an_under_sized_unbalanced_set():
    from langatlas_ingest.goldens.items import Citation, Claim, VerifierItem
    claim = Claim(kind="instance-exists", text="instance-exists(i-x, status=present)")
    thin = [VerifierItem(id=f"v-{n:04d}", stratum="correct", expected_verdict="supported",
                         claim=claim, citation=Citation(source="ctm", locator="p. 1"))
            for n in range(10)]
    errors = validate_set(thin, held_out=[])
    assert any("200" in e for e in errors)              # size floor
    assert any("stratum" in e for e in errors)          # missing strata
    assert any("held-out" in e for e in errors)         # audit slice missing


def test_a_controversy_case_may_not_smuggle_human_challenge_inputs(tmp_path):
    (tmp_path / "cases-test.yaml").write_text("""
version: 1
cases:
  - id: c-bootstrap-0001
    expected_level: 2
    inputs:
      verdicts: [{fact: f-abc, verdict: partial, field: since}]
      github_activity: {open_issues: 3}
""")
    cases = load_controversy_cases(tmp_path)
    errors = validate_controversy_cases(cases)
    assert any("github_activity" in e for e in errors)
