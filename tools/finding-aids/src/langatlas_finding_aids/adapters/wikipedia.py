"""Wikipedia's REST summary endpoint, through the fifth channel.

Summary only, deliberately: the full-article extract is long, CC BY-SA, and — per D29 —
unusable as fact content anyway. What a survey actually needs from Wikipedia is "does this
concept have a name, and what is it called", which is exactly what a summary is."""
from urllib.parse import quote

from langatlas_finding_aids.config import FindingAidsConfig
from langatlas_finding_aids.results import FindingAidResult, utc_now


def query_wikipedia(channel, query: str, *, config: FindingAidsConfig | None = None,
                    limit: int = 10) -> list[FindingAidResult]:
    """`query` is an article title (the R3 themes configure the titles they care about),
    not a search string: the REST summary route is title-addressed, and a title we chose
    is one more place the tool stays a *scoped* finding aid."""
    config = config or FindingAidsConfig.load()
    title = quote(query.replace(" ", "_"), safe="_()")
    payload = channel.get_json(
        "wikipedia", f"{config.wikipedia['api_base']}/page/summary/{title}",
        query_shape="summary")
    if not payload or "title" not in payload:
        return []
    url = (payload.get("content_urls", {}).get("desktop", {}).get("page")
           or f"https://en.wikipedia.org/wiki/{title}")
    return [FindingAidResult(
        source="wikipedia", item_id=payload["title"], label=payload["title"],
        fields={"extract": payload.get("extract", "")}, url=url,
        retrieved_at=utc_now())][:limit]
