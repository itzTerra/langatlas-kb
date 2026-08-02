import re

SLUG_RE = re.compile(r"^[a-z]([a-z0-9]*(-[a-z0-9]+)*)?$")
MAX_SLUG_LEN = 48


def is_valid_slug(s: str) -> bool:
    return len(s) <= MAX_SLUG_LEN and bool(SLUG_RE.match(s))


def _require_slug(s: str) -> str:
    if not is_valid_slug(s):
        raise ValueError(f"invalid slug/id: {s!r}")
    return s


def compose_instance_id(language: str, feature: str) -> str:
    return f"fi.{_require_slug(language)}.{_require_slug(feature)}"


def compose_edge_id(edge_type: str, frm: str, to: str) -> str:
    return f"edge.{_require_slug(edge_type)}.{_require_slug(frm)}.{_require_slug(to)}"


def compose_rule_id(slug: str) -> str:
    return f"rule-{_require_slug(slug)}"


def compose_syntax_id(instance_id: str, key: str) -> str:
    return f"{instance_id}.sx.{_require_slug(key)}"


def canonical_endpoints(a: str, b: str) -> tuple[str, str]:
    return tuple(sorted((_require_slug(a), _require_slug(b))))  # type: ignore[return-value]


def canonical_when_all(feature_ids: list[str]) -> list[str]:
    return sorted(_require_slug(f) for f in feature_ids)
