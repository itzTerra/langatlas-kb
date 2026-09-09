"""§4.4's edition check: a plain page fetch, never a re-ingestion.

Detection is deliberately crude (plan decision 3): the record's pinned `custom.edition`
string either still appears on the page it was pinned from, or it does not. A false
positive costs the developer one glance at a triage entry; the alternative — parsing
version semantics per publisher — is a maintenance burden with no better failure mode,
because adopting an edition is a human act either way (`langatlas-sources supersede`)."""
import re
from dataclasses import dataclass
from datetime import datetime, timedelta

from langatlas_ingest.currency.links import FetchedPage  # noqa: F401  (fetcher protocol)
from langatlas_ingest.verify.sources import SourceFacts

# §4.4's quarterly cadence, kept exactly for the documents it was written about.
FORMAL_SPEC_INTERVAL_DAYS = 90
# §4.2's "flat shorter interval for every non-formal-spec grounding". One number for all
# three — a per-language cadence table is exactly what that clause rules out.
OTHER_GROUNDING_INTERVAL_DAYS = 30

_WHITESPACE = re.compile(r"\s+")


@dataclass(frozen=True)
class EditionCheckResult:
    source_id: str
    edition: str
    url: str | None
    matched: bool
    detail: str
    fetched: bool


def interval_days(grounding: str) -> int:
    return (FORMAL_SPEC_INTERVAL_DAYS if grounding == "formal-spec"
            else OTHER_GROUNDING_INTERVAL_DAYS)


def is_due(grounding: str, last_checked: datetime | None, *, now: datetime) -> bool:
    if last_checked is None:
        return True
    return now - last_checked >= timedelta(days=interval_days(grounding))


def check_url_for(facts: SourceFacts) -> str | None:
    """`custom.edition_check_url` is the page that *announces* the current edition (a
    "what's new" or index page); `URL` is the document itself. Prefer the former when the
    record bothered to name one."""
    custom = facts.csl.get("custom") or {}
    return custom.get("edition_check_url") or facts.csl.get("URL") or None


def _normalized(text: str) -> str:
    return _WHITESPACE.sub(" ", text).lower()


def check_edition(source_id: str, facts: SourceFacts, *, fetch) -> EditionCheckResult:
    """@returns a result whose `matched=False` is the *only* thing that opens a triage
        entry. An unfetchable page returns `fetched=False, matched=True`: it is the
        link-checker's finding to report, not this job's."""
    custom = facts.csl.get("custom") or {}
    edition = str(custom.get("edition") or "")
    url = check_url_for(facts)
    try:
        page = fetch(url)
    except Exception as exc:
        return EditionCheckResult(source_id=source_id, edition=edition, url=url,
                                  matched=True, fetched=False,
                                  detail=f"{url} could not be fetched ({exc});"
                                         " the link-checker owns that signal")
    if not 200 <= page.status < 300:
        return EditionCheckResult(source_id=source_id, edition=edition, url=url,
                                  matched=True, fetched=False,
                                  detail=f"{url} could not be fetched (status"
                                         f" {page.status}); the link-checker owns that"
                                         " signal")
    matched = _normalized(edition) in _normalized(page.text)
    detail = ("" if matched else
              f"pinned edition {edition!r} no longer appears at {url};"
              " check whether a new edition shipped, then adopt it by hand with"
              " `langatlas-sources supersede` (never automatically, §4.4)")
    return EditionCheckResult(source_id=source_id, edition=edition, url=url,
                              matched=matched, detail=detail, fetched=True)
