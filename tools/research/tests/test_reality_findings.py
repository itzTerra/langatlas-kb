"""R5's findings are mechanical, three-valued, and read only the cells (D67)."""
import copy

import pytest

from langatlas_research.reality.findings import compute_findings, refresh
from langatlas_research.reality.record import replace_language, save_record

REF = {"source": "haskell-2010-report", "locator": "§4.1.4",
       "chunk_id": "haskell-2010-report#c00140"}
SCOPE = "No compile-time checking phase exists."


@pytest.fixture
def answered(r5_record, r5_cell, r5_run):
    record = replace_language(r5_record, "python", cells=[
        r5_cell("python", "dynamic-typing", status="admitted"),
        r5_cell("python", "static-typing", answer="absent", status="admitted",
                absence_scope=SCOPE),
        r5_cell("python", "type-inference", mappable=False)], uncovered=[], run=r5_run)
    return replace_language(record, "haskell", cells=[
        r5_cell("haskell", "static-typing", status="admitted"),
        r5_cell("haskell", "dynamic-typing", status="refused"),
        r5_cell("haskell", "type-inference", status="unsourced")],
        uncovered=[{"key": "haskell--type-classes", "language": "haskell",
                    "name": "Type classes", "note": "No item covers them.",
                    "evidence": [dict(REF)]}],
        run={**r5_run, "run_id": "haskell-run"})


def _settled_no(record, r5_cell, r5_run, language):
    """`language` answers both typing members with a verified 'no'."""
    return replace_language(record, language, cells=[
        r5_cell(language, "dynamic-typing", mappable=False),
        r5_cell(language, "static-typing", answer="absent", status="admitted",
                absence_scope=SCOPE)], uncovered=[], run={**r5_run, "run_id": language})


def test_unmappable_cells_are_listed_by_key(answered, r5_spec):
    findings, _ = compute_findings(answered, r5_spec)
    assert findings["unmappable"] == ["python--type-inference"]


def test_a_member_every_language_settles_no_is_uninhabited(r5_record, r5_cell, r5_run,
                                                           r5_spec):
    record = _settled_no(_settled_no(r5_record, r5_cell, r5_run, "python"), r5_cell, r5_run,
                         "haskell")
    findings, _ = compute_findings(record, r5_spec)
    assert findings["uninhabited_values"] == [
        {"dimension": "type-checking-discipline", "value": "dynamic-typing"},
        {"dimension": "type-checking-discipline", "value": "static-typing"}]


def test_an_unknown_cell_never_makes_a_member_uninhabited(answered, r5_spec):
    """haskell--dynamic-typing was refused: we do not know, so nothing is claimed."""
    findings, _ = compute_findings(answered, r5_spec)
    assert findings["uninhabited_values"] == []


def test_a_language_settling_no_on_every_member_is_unfittable(r5_record, r5_cell, r5_run,
                                                              r5_spec):
    findings, _ = compute_findings(_settled_no(r5_record, r5_cell, r5_run, "prolog"), r5_spec)
    assert findings["unfittable"] == ["prolog--type-checking-discipline"]


def test_two_verified_members_of_an_exclusive_dimension_is_a_violation(r5_record, r5_cell,
                                                                       r5_run, r5_spec):
    record = replace_language(r5_record, "python", cells=[
        r5_cell("python", "dynamic-typing", status="admitted"),
        r5_cell("python", "static-typing", answer="partial", status="admitted")],
        uncovered=[], run=r5_run)
    findings, _ = compute_findings(record, r5_spec)
    assert findings["exclusivity_violations"] == [
        {"language": "python", "dimension": "type-checking-discipline",
         "members": ["dynamic-typing", "static-typing"]}]


def test_unverified_answers_inhabit_nothing(r5_record, r5_cell, r5_run, r5_spec):
    record = replace_language(r5_record, "python", cells=[
        r5_cell("python", "dynamic-typing"), r5_cell("python", "static-typing")],
        uncovered=[], run=r5_run)
    findings, _ = compute_findings(record, r5_spec)
    assert findings["exclusivity_violations"] == []


def test_a_multi_dimension_is_never_violated(r5_record, r5_cell, r5_run, r5_spec):
    spec = copy.deepcopy(r5_spec)
    spec["groups"][0]["exclusivity"] = "multi"
    record = replace_language(r5_record, "python", cells=[
        r5_cell("python", "dynamic-typing", status="admitted"),
        r5_cell("python", "static-typing", status="admitted")], uncovered=[], run=r5_run)
    findings, _ = compute_findings(record, spec)
    assert findings["exclusivity_violations"] == []


def test_a_language_the_d50_mask_excluded_is_skipped(r5_record, r5_cell, r5_run, r5_spec):
    record = replace_language(r5_record, "sql", cells=[
        r5_cell("sql", "type-inference", mappable=False)], uncovered=[], run=r5_run)
    findings, _ = compute_findings(record, r5_spec)
    assert findings["unfittable"] == [] and findings["uninhabited_values"] == []


def test_the_summary_counts_every_outcome(answered, r5_spec):
    _, summary = compute_findings(answered, r5_spec)
    assert summary == {"languages": 2, "cells": 6, "mappable": 5, "unmappable": 1,
                       "admitted": 3, "refused": 1, "unsourced": 1, "uncovered": 1}


def test_a_refreshed_record_still_validates(answered, r5_spec, research_repo):
    refreshed = refresh(answered, r5_spec)
    assert refreshed["summary"]["admitted"] == 3
    save_record(refreshed, repo_root=research_repo)
