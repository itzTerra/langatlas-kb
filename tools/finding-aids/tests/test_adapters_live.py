import pytest

from langatlas_finding_aids.adapters.wikidata import load_template, query_wikidata
from langatlas_finding_aids.adapters.wikipedia import query_wikipedia
from langatlas_finding_aids.config import FindingAidsConfig


class _Channel:
    def __init__(self, payload):
        self.payload, self.calls = payload, []

    def get_json(self, source, url, *, params=None, query_shape, version=None):
        self.calls.append({"source": source, "url": url, "params": params,
                           "query_shape": query_shape, "version": version})
        return self.payload


SPARQL_PAYLOAD = {"results": {"bindings": [
    {"item": {"value": "http://www.wikidata.org/entity/Q575"},
     "itemLabel": {"value": "Rust"},
     "inception": {"value": "2010-07-07T00:00:00Z"},
     "paradigmLabel": {"value": "multi-paradigm programming language"},
     "extension": {"value": "rs"}}]}}

SUMMARY_PAYLOAD = {"title": "Rust (programming language)",
                   "extract": "Rust is a general-purpose programming language.",
                   "content_urls": {"desktop": {"page":
                                                "https://en.wikipedia.org/wiki/Rust"}}}


@pytest.fixture
def config():
    return FindingAidsConfig.load()


def test_the_sparql_template_is_scoped_not_free_text():
    """D53 §O2: a fixed, versioned query template — never a free-text search that could
    return anything at all."""
    template = load_template()
    assert "Q9143" in template          # instance/subclass of programming language
    assert "{label}" in template        # the one interpolated slot
    assert "SERVICE wikibase:label" in template


def test_wikidata_binds_the_query_into_the_template_and_passes_the_version(config):
    channel = _Channel(SPARQL_PAYLOAD)
    query_wikidata(channel, "Rust", config=config)
    call = channel.calls[0]
    assert call["source"] == "wikidata"
    assert "Rust" in call["params"]["query"]
    assert call["params"]["format"] == "json"
    assert call["version"] == str(config.wikidata["template_version"])


def test_wikidata_normalizes_bindings_into_envelopes(config):
    results = query_wikidata(_Channel(SPARQL_PAYLOAD), "Rust", config=config)
    assert [r.item_id for r in results] == ["Q575"]
    assert results[0].label == "Rust"
    assert results[0].fields["inception"].startswith("2010")
    assert results[0].url == "https://www.wikidata.org/wiki/Q575"
    assert results[0].non_citable is True
    assert results[0].mirror_version is None    # live source, no mirror


def test_a_quote_in_the_query_cannot_break_out_of_the_template(config):
    """A label is interpolated into a SPARQL string literal. An unescaped quote would be
    a query-injection bug, and the input here comes from an agent."""
    channel = _Channel({"results": {"bindings": []}})
    query_wikidata(channel, 'Ru"st', config=config)
    assert '"Ru\\"st"' in channel.calls[0]["params"]["query"]


def test_a_carriage_return_in_the_query_cannot_break_out_of_the_template(config):
    """SPARQL's STRING_LITERAL2 grammar forbids a raw CR inside a double-quoted string
    literal the same way it forbids a raw LF; an unescaped CR is the same class of
    string-literal-breakout risk the newline handling exists to prevent."""
    channel = _Channel({"results": {"bindings": []}})
    query_wikidata(channel, "Ru\rst", config=config)
    assert "\r" not in channel.calls[0]["params"]["query"]


def test_wikipedia_summary_is_normalized(config):
    results = query_wikipedia(_Channel(SUMMARY_PAYLOAD),
                              "Rust (programming language)", config=config)
    assert results[0].source == "wikipedia"
    assert results[0].fields["extract"].startswith("Rust is")
    assert results[0].url.endswith("/wiki/Rust")


def test_wikipedia_titles_are_url_encoded(config):
    channel = _Channel(SUMMARY_PAYLOAD)
    query_wikipedia(channel, "Rust (programming language)", config=config)
    assert "Rust%20(programming%20language)" in channel.calls[0]["url"] \
        or "Rust_(programming_language)" in channel.calls[0]["url"]


def test_an_empty_result_set_is_an_empty_list_not_an_error(config):
    assert query_wikidata(_Channel({"results": {"bindings": []}}), "x",
                          config=config) == []
