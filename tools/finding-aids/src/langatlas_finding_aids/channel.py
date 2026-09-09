"""D53's fifth `RunContext` channel.

Not an attribute on `RunContext` (plan decision 5): D53 ratified the wrapper's placement
inside `tools/finding-aids/`, and `langatlas_pipeline` cannot import a package that
imports it. It is a channel by *policy* — cache, throttle, budget, transcript, D31 door —
which is what "rides RunContext as a fifth channel" actually means; the shape mirrors
`EmbeddingClient(ctx)` exactly, `ctx` first."""
from langatlas_pipeline.cache import finding_aid_cache_key
from langatlas_pipeline.providers.throttle import Throttle

from langatlas_finding_aids.config import FindingAidsConfig

# Every finding-aid read is logged under one tool name, because an agent (and a reader of
# the transcript) sees one tool: `search_finding_aids`. Which adapter answered is in the
# event's `tool_args`.
TOOL_LOG_NAME = "search_finding_aids"


class FindingAidChannel:
    """One polite, cached, logged HTTP path for the two live adapters — and the D31 door
    for every adapter, mirrored or live."""

    def __init__(self, ctx, *, config: FindingAidsConfig | None = None, client=None,
                 throttle=None):
        self.ctx = ctx
        self.config = config or FindingAidsConfig.load()
        self._client = client
        self._throttles: dict[str, Throttle] = {}
        self._throttle_override = throttle
        self.network_calls = 0
        self.cached_calls = 0

    # ---- plumbing ---------------------------------------------------------------

    def _http(self):
        if self._client is None:
            import httpx

            self._client = httpx.Client(timeout=60, follow_redirects=True)
        return self._client

    def _throttle(self, source: str) -> Throttle:
        if self._throttle_override is not None:
            return self._throttle_override
        if source not in self._throttles:
            self._throttles[source] = Throttle(
                min_interval=self.config.min_interval(source))
        return self._throttles[source]

    def _fetch(self, source: str, url: str, *, params: dict | None, query_shape: str,
               version: str | None, as_json: bool):
        key = finding_aid_cache_key(source=source, query_shape=query_shape,
                                    params=dict(params or {}), version=version)
        cache = getattr(self.ctx, "cache", None)
        cached = cache.get(key) if cache is not None else None
        if cached is not None:
            self.cached_calls += 1
            self._log(source, url, query_shape, cache_hit=True)
            return cached["payload"]

        # Budget is checked *before* the call (D26/D43), so an exceeded cap leaves the
        # in-flight item re-attemptable rather than half-fetched.
        self.ctx.check_budget(calls=1)
        headers = {"user-agent": self.config.user_agent,
                   "accept": "application/json" if as_json else "text/html"}
        response = self._throttle(source).run(
            lambda: self._http().get(url, params=params, headers=headers))
        response.raise_for_status()
        payload = response.json() if as_json else response.text
        self.ctx.note_usage(calls=1)
        self.network_calls += 1
        if cache is not None:
            cache.put(key, {"payload": payload})
        self._log(source, url, query_shape, cache_hit=False)
        return payload

    def _log(self, source: str, url: str, query_shape: str, *, cache_hit: bool) -> None:
        """The *call* is logged here; the *content* is logged by `deliver()` through the
        D31 door, which is the only path that ever hands one of these bytes to a model."""
        self.ctx.writer.append(role="tool", content=f"{source} {query_shape} {url}",
                               tool_name=f"finding-aid:{source}",
                               tool_args={"source": source, "query_shape": query_shape,
                                          "url": url},
                               cache_hit=cache_hit, flags=["finding-aid"])

    # ---- public API -------------------------------------------------------------

    def get_json(self, source: str, url: str, *, params: dict | None = None,
                 query_shape: str, version: str | None = None) -> dict:
        return self._fetch(source, url, params=params, query_shape=query_shape,
                           version=version, as_json=True)

    def get_text(self, source: str, url: str, *, params: dict | None = None,
                 query_shape: str, version: str | None = None) -> str:
        """Returns the text **already through the D31 door**: scanned for
        instruction-shaped patterns, logged, and delimited as data. A caller that wants
        the raw bytes for parsing uses `get_raw`; a caller that will show text to a model
        uses this."""
        raw = self._fetch(source, url, params=params, query_shape=query_shape,
                          version=version, as_json=False)
        return self.deliver(raw, source_id=f"finding-aid:{source}")

    def get_raw(self, source: str, url: str, *, params: dict | None = None,
                query_shape: str, version: str | None = None) -> str:
        """Unmediated text, for parsers. Never hand the result to a model — every path
        that does goes through `deliver()`."""
        return self._fetch(source, url, params=params, query_shape=query_shape,
                           version=version, as_json=False)

    def deliver(self, text: str, *, source_id: str) -> str:
        """The D31 door for content this channel did not itself fetch — a mirror read, a
        rendered result block. D53's ratification put the lexical scan on this tool from
        day one, so *every* externally-derived string this package shows a model passes
        through here."""
        return self.ctx.tool_result(tool=TOOL_LOG_NAME, text=text, source_id=source_id,
                                    kind="finding-aid")
