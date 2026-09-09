"""Hyperpolyglot, read from the scraped mirror (D53).

A page, not a row: Hyperpolyglot's value is its side-by-side comparison tables, and
slicing one into per-cell "facts" would be exactly the bulk-import shape D29 rejects. The
adapter returns the matching page's text so a human or an agent can *look*, with the page
URL to look at."""
import html
import re
from pathlib import Path

from langatlas_finding_aids.config import FindingAidsConfig
from langatlas_finding_aids.mirror import require_mirror
from langatlas_finding_aids.paths import mirror_dir
from langatlas_finding_aids.results import FindingAidResult, utc_now

_TAG = re.compile(r"<[^>]+>")
_WHITESPACE = re.compile(r"\s+")
# Enough to see a comparison row in context; short enough that four hits do not fill a
# context window. §7.11's "leads, not evidence" posture in one number.
_EXCERPT_CHARS = 2000


def _text(raw: str) -> str:
    return _WHITESPACE.sub(" ", html.unescape(_TAG.sub(" ", raw))).strip()


def query_hyperpolyglot(query: str, *, config: FindingAidsConfig | None = None,
                        root: Path | None = None,
                        limit: int = 10) -> list[FindingAidResult]:
    config = config or FindingAidsConfig.load()
    state = require_mirror("hyperpolyglot", root=root)
    directory = (root / "hyperpolyglot" if root
                 else mirror_dir("hyperpolyglot")) / "pages"
    base = config.hyperpolyglot["base_url"]
    needle = query.strip().lower()
    results: list[FindingAidResult] = []
    for path in sorted(directory.glob("*.html")):
        text = _text(path.read_text(errors="replace"))
        if needle and needle not in text.lower():
            continue
        results.append(FindingAidResult(
            source="hyperpolyglot", item_id=path.stem, label=path.stem.replace("_", "/"),
            fields={"text": text[:_EXCERPT_CHARS]},
            url=f"{base}/{path.stem.replace('_', '/')}", retrieved_at=utc_now(),
            mirror_version=state.version))
        if len(results) >= limit:
            break
    return results
