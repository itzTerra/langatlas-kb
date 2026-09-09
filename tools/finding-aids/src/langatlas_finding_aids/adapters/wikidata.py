"""Wikidata, queried live through the fifth channel (D53 §O2).

Live, because Wikidata publishes a real endpoint; scoped, because a free-text SPARQL hole
in an agent-callable tool is both a correctness and a courtesy problem. The template is a
file so a query change is reviewable as a diff, and versioned so a changed query cannot be
answered from a cache filled by the old one."""
from pathlib import Path

from langatlas_finding_aids.config import FindingAidsConfig
from langatlas_finding_aids.results import FindingAidResult, utc_now

SPARQL_TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "queries"
_ENTITY_URL = "https://www.wikidata.org/wiki/{item_id}"
_FIELDS = ("inception", "paradigmLabel", "extension", "influencedByLabel")


def load_template(config: FindingAidsConfig | None = None) -> str:
    config = config or FindingAidsConfig.load()
    return (SPARQL_TEMPLATE_DIR / config.wikidata["template"]).read_text()


def _escape(label: str) -> str:
    """SPARQL string-literal escaping. The label reaches us from an agent, so this is the
    boundary between 'a search term' and 'a query'.

    `STRING_LITERAL2` forbids a raw CR the same way it forbids a raw LF, so both are
    neutralized here alongside the backslash/quote escaping."""
    return (label.replace("\\", "\\\\").replace('"', '\\"')
                 .replace("\r", " ").replace("\n", " "))


def query_wikidata(channel, query: str, *, config: FindingAidsConfig | None = None,
                   limit: int = 10) -> list[FindingAidResult]:
    config = config or FindingAidsConfig.load()
    sparql = load_template(config).replace("{label}", _escape(query))
    payload = channel.get_json(
        "wikidata", config.wikidata["endpoint"],
        params={"query": sparql, "format": "json"}, query_shape="language-facts",
        version=str(config.wikidata["template_version"]))
    results: list[FindingAidResult] = []
    for binding in payload.get("results", {}).get("bindings", [])[:limit]:
        item_id = binding["item"]["value"].rsplit("/", 1)[-1]
        results.append(FindingAidResult(
            source="wikidata", item_id=item_id,
            label=binding.get("itemLabel", {}).get("value", item_id),
            fields={name: binding[name]["value"] for name in _FIELDS if name in binding},
            url=_ENTITY_URL.format(item_id=item_id), retrieved_at=utc_now()))
    return results
