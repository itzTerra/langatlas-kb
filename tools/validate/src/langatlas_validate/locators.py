import re
from dataclasses import dataclass, field
from typing import Iterable, Protocol

# §4.3 grammar table. Order matters: more specific patterns first.
LOCATOR_GRAMMAR: dict[str, re.Pattern] = {
    "book-page":        re.compile(r"^p{1,2}\. \d+([–-]\d+)?$"),
    "numbered-section": re.compile(r"^§\d+(\.\d+)*$"),
    "named-section":    re.compile(r"^(ch\. \d+|§ .+)$"),
    "design-doc":       re.compile(r"^[A-Za-z]+ \d+( §.+)?$"),
    "repo-file":        re.compile(r"^[0-9a-f]{7}:[^#]+#L\d+(-L\d+)?$"),
    "multipage-docs":   re.compile(r"^[^#]+#[^#]+$"),
    "web-fragment":     re.compile(r"^#[^#]+$"),
    "video":            re.compile(r"^t=\d{2}:\d{2}:\d{2}$"),
}


def validate_locator_shape(
    locator: str, allowed_kinds: Iterable[str] | None = None
) -> str | None:
    allowed = set(allowed_kinds) if allowed_kinds is not None else None
    for kind, pattern in LOCATOR_GRAMMAR.items():
        if allowed is not None and kind not in allowed:
            continue
        if pattern.match(locator):
            return kind
    return None


class SourceChunksIndex(Protocol):
    def resolve(self, source_id: str, locator: str) -> list[str]: ...


@dataclass
class LocatorResult:
    shape_ok: bool
    kind: str | None
    resolved: bool
    chunk_ids: list[str] = field(default_factory=list)


def validate_locator(
    locator: str,
    source_id: str,
    index: SourceChunksIndex,
    allowed_kinds: Iterable[str] | None = None,
) -> LocatorResult:
    kind = validate_locator_shape(locator, allowed_kinds)
    if kind is None:
        return LocatorResult(shape_ok=False, kind=None, resolved=False)
    chunk_ids = list(index.resolve(source_id, locator))
    return LocatorResult(
        shape_ok=True, kind=kind, resolved=bool(chunk_ids), chunk_ids=chunk_ids
    )
