"""The fan-out and its two renderings (D53 §O1c).

`search_finding_aids` is one function with two call sites, matching §7.6's mediation
split: a completion-channel runner calls it and injects `render_for_prompt`'s string; a
Claude-channel session calls the SDK tool in `tools.py`, which calls this. There is no
third path, and neither path can reach an adapter without a `ctx`."""
from langatlas_finding_aids.adapters.hyperpolyglot import query_hyperpolyglot
from langatlas_finding_aids.adapters.pldb import query_pldb
from langatlas_finding_aids.adapters.wikidata import query_wikidata
from langatlas_finding_aids.adapters.wikipedia import query_wikipedia
from langatlas_finding_aids.channel import FindingAidChannel
from langatlas_finding_aids.config import FindingAidsConfig, UnknownFindingAidSource
from langatlas_finding_aids.results import NON_CITABLE_CAVEAT, candidate_source_for

# The mirrored adapters read files and take no channel; the live ones take it first. Kept
# as data rather than four `if` branches so adding a fifth aid is one row.
_ADAPTERS = {
    "pldb": ("mirror", lambda **kw: query_pldb(kw["query"], config=kw["config"],
                                               root=kw["root"], limit=kw["limit"])),
    "hyperpolyglot": ("mirror",
                      lambda **kw: query_hyperpolyglot(kw["query"], config=kw["config"],
                                                       root=kw["root"],
                                                       limit=kw["limit"])),
    "wikidata": ("live", lambda **kw: query_wikidata(kw["channel"], kw["query"],
                                                     config=kw["config"],
                                                     limit=kw["limit"])),
    "wikipedia": ("live", lambda **kw: query_wikipedia(kw["channel"], kw["query"],
                                                       config=kw["config"],
                                                       limit=kw["limit"])),
}


def search_finding_aids(ctx, query: str, *, sources=None, limit: int = 10,
                        config: FindingAidsConfig | None = None, channel=None,
                        root=None) -> list:
    """Leads from every requested finding aid.

    @param sources - defaults to every source enabled in `config/finding-aids.yaml`
    @returns results in the requested sources' order. An adapter that raises (a missing
        mirror, a Wikidata outage) contributes nothing and is logged: this tool is never
        load-bearing for correctness, so degrading to fewer leads always beats raising
        inside an agent's tool loop.
    """
    config = config or FindingAidsConfig.load()
    requested = tuple(sources or config.sources)
    unknown = set(requested) - set(_ADAPTERS)
    if unknown:
        raise UnknownFindingAidSource(sorted(unknown))
    channel = channel or FindingAidChannel(ctx, config=config)
    results = []
    for source in requested:
        _, call = _ADAPTERS[source]
        try:
            results.extend(call(query=query, config=config, root=root, limit=limit,
                                channel=channel))
        except Exception as exc:
            ctx.writer.append(role="assistant",
                              content=f"finding aid {source} returned nothing: {exc!r}",
                              flags=["finding-aid-degraded"])
    return results


def _block(result) -> str:
    fields = "\n".join(f"  {key}: {value}" for key, value in sorted(
        result.fields.items()))
    version = f" @{result.mirror_version}" if result.mirror_version else " (live)"
    return (f"[{result.source}{version}] {result.label} — {result.url}\n"
            f"  candidate_source: {candidate_source_for(result)}\n{fields}")


def render_for_prompt(ctx, results, *, channel=None) -> str:
    """§7.6: the completion channel gets no tool loop, so the runner injects this string.

    The caveat leads, before any content — an agent that stops reading early must still
    have read the rule. Every result block then goes through the D31 door individually, so
    a hostile string inside a scraped table is scanned, logged, and delimited rather than
    concatenated into our own framing."""
    if not results:
        return ""
    channel = channel or FindingAidChannel(ctx)
    blocks = [channel.deliver(_block(result),
                              source_id=f"finding-aid:{result.source}")
              for result in results]
    return "\n\n".join([NON_CITABLE_CAVEAT, *blocks])
