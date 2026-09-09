import hashlib
import re
from dataclasses import dataclass
from urllib.parse import urldefrag

_WHITESPACE = re.compile(r"\s+")
# One retry, per §4.4 ("a single retry suffices before flagging link_status: dead") — so
# two attempts total. Transient network noise should not open a queue entry a human then
# has to close; a genuinely dead link fails twice just as reliably as once.
_ATTEMPTS = 2


@dataclass(frozen=True)
class FetchedPage:
    status: int
    text: str


@dataclass(frozen=True)
class LinkCheckResult:
    source_id: str
    url: str
    resolves: bool
    http_status: int | None
    anchor: str | None
    # None means "this URL has no fragment", never "the anchor is missing" — the column
    # and the finding are different statements and a bare False would conflate them.
    anchor_present: bool | None
    content_hash: str | None
    drifted: bool
    findings: tuple[str, ...]


def content_hash(text: str) -> str:
    """Hash the *content*, not its formatting. A docs site that reflows its HTML on every
    deploy would otherwise report drift monthly forever, and a job that cries wolf every
    month is a job the developer stops reading."""
    return hashlib.sha256(
        _WHITESPACE.sub(" ", text).strip().encode("utf-8")).hexdigest()


def _anchor_present(text: str, anchor: str) -> bool:
    """Substring-free check for `id="x"` / `name="x"`, quoted or not. Deliberately not an
    HTML parse: the question is only whether the fragment a citation points at still
    exists, and every generator this corpus cites emits one of these two attributes."""
    pattern = re.compile(r"""(?:id|name)\s*=\s*(?:"|')?""" + re.escape(anchor)
                         + r"""(?:"|'|\s|>)""")
    return bool(pattern.search(text))


def check_link(source_id: str, url: str, *, fetch,
               previous_hash: str | None = None) -> LinkCheckResult:
    """§4.4's three independent signals for one source's live URL.

    @param fetch - `(url) -> FetchedPage`; any exception counts as a failed attempt
    @param previous_hash - the last recorded `content_hash`, or None on a first check
    @returns every signal that could be measured, plus the `sourcing_queue` reasons they
        imply. Signals never mask each other: a page can resolve, have lost its anchor,
        and have drifted, and all three are reported.
    """
    base, fragment = urldefrag(url)
    anchor = fragment or None
    page, status = None, None
    for _ in range(_ATTEMPTS):
        try:
            page = fetch(url)
        except Exception:
            page = None
            continue
        status = page.status
        if 200 <= page.status < 300:
            break
        page = None
    findings: list[str] = []
    if page is None:
        # Dead is dead: with no body there is nothing to say about the anchor or the
        # hash, and reporting them as "missing"/"drifted" would be inventing evidence.
        return LinkCheckResult(source_id=source_id, url=url, resolves=False,
                               http_status=status, anchor=anchor, anchor_present=None,
                               content_hash=None, drifted=False,
                               findings=("link-dead",))
    anchor_present = _anchor_present(page.text, anchor) if anchor else None
    if anchor_present is False:
        findings.append("anchor-missing")
    digest = content_hash(page.text)
    drifted = previous_hash is not None and digest != previous_hash
    if drifted:
        findings.append("content-drift")
    return LinkCheckResult(source_id=source_id, url=url, resolves=True,
                           http_status=page.status, anchor=anchor,
                           anchor_present=anchor_present, content_hash=digest,
                           drifted=drifted, findings=tuple(findings))
