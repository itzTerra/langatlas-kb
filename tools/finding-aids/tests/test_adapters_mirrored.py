import json

import pytest

from langatlas_finding_aids.adapters.hyperpolyglot import query_hyperpolyglot
from langatlas_finding_aids.adapters.pldb import query_pldb
from langatlas_finding_aids.config import FindingAidsConfig
from langatlas_finding_aids.mirror import MirrorMissing

RUST = """id rust
name Rust
appeared 2010
tags pl
type pl
paradigms functional imperative
fileExtensions rs
influencedBy cpp ocaml haskell
description Rust is a multi-paradigm systems language with an ownership type system.
"""
HASKELL = """id haskell
name Haskell
appeared 1990
tags pl
type pl
paradigms functional lazy
fileExtensions hs lhs
description Haskell is a purely functional language with lazy evaluation.
"""


@pytest.fixture
def config():
    return FindingAidsConfig.load()


@pytest.fixture
def pldb_mirror(tmp_path, config):
    concepts = tmp_path / "pldb" / "repo" / "concepts"
    concepts.mkdir(parents=True)
    (concepts / "rust.scroll").write_text(RUST)
    (concepts / "haskell.scroll").write_text(HASKELL)
    (tmp_path / "pldb" / "manifest.json").write_text(json.dumps(
        {"source": "pldb", "version": "abc1234", "refreshed_at": "2026-09-08T00:00:00Z",
         "item_count": 2, "items": {}}))
    return tmp_path


@pytest.fixture
def hp_mirror(tmp_path):
    pages = tmp_path / "hyperpolyglot" / "pages"
    pages.mkdir(parents=True)
    (pages / "functional.html").write_text(
        "<html><h1>Functional</h1><table><tr><td>pattern matching</td>"
        "<td>case x of</td></tr></table></html>")
    (tmp_path / "hyperpolyglot" / "manifest.json").write_text(json.dumps(
        {"source": "hyperpolyglot", "version": "ff00", "refreshed_at":
         "2026-09-08T00:00:00Z", "item_count": 1, "items": {}}))
    return tmp_path


def test_pldb_matches_on_name_and_returns_the_configured_fields(pldb_mirror, config):
    results = query_pldb("rust", config=config, root=pldb_mirror)
    assert [r.item_id for r in results] == ["rust"]
    assert results[0].fields["appeared"] == "2010"
    assert results[0].fields["fileExtensions"] == "rs"


def test_pldb_matches_on_description_text_too(pldb_mirror, config):
    assert {r.item_id for r in query_pldb("lazy evaluation", config=config,
                                          root=pldb_mirror)} == {"haskell"}


def test_pldb_results_carry_the_mirror_version(pldb_mirror, config):
    assert query_pldb("rust", config=config, root=pldb_mirror)[0].mirror_version \
        == "abc1234"


def test_pldb_results_are_non_citable_envelopes(pldb_mirror, config):
    assert all(r.non_citable for r in query_pldb("rust", config=config,
                                                 root=pldb_mirror))


def test_pldb_honours_the_limit(pldb_mirror, config):
    assert len(query_pldb("", config=config, root=pldb_mirror, limit=1)) == 1


def test_pldb_without_a_mirror_raises_rather_than_fetching(tmp_path, config):
    with pytest.raises(MirrorMissing):
        query_pldb("rust", config=config, root=tmp_path)


def test_hyperpolyglot_returns_the_matching_page_with_text_stripped(hp_mirror, config):
    results = query_hyperpolyglot("pattern matching", config=config, root=hp_mirror)
    assert [r.item_id for r in results] == ["functional"]
    assert "<td>" not in results[0].fields["text"]
    assert "pattern matching" in results[0].fields["text"]


def test_hyperpolyglot_without_a_mirror_raises(tmp_path, config):
    with pytest.raises(MirrorMissing):
        query_hyperpolyglot("anything", config=config, root=tmp_path)
