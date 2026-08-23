from langatlas_validate.normalize import normalize_record


def render_source_yaml(id: str, type: str, title: str, *, author: list[dict] | None = None,
                       issued: dict | None = None, url: str | None = None,
                       doi: str | None = None, tier: str, grounding: str,
                       canonical_source: bool | None = None,
                       acquisition_note: str | None = None, edition: str | None = None,
                       edition_check_url: str | None = None,
                       locator_kinds: list[str] | None = None) -> str:
    """Renders a schema-shaped `sources/<id>.yaml` record (§4.1: CSL-JSON field vocabulary
    authored as YAML, plus the `custom` extras) and normalizes it through the same
    `normalize_record` CI checks, so a scaffolded record is never the thing `precommit-auto`
    flags as unnormalized. Every field a caller does not pass is omitted entirely rather than
    written as `null` — an omitted CSL-JSON field and an explicit null are not the same
    statement, and the schema treats extra properties structurally, so a stray `null` would
    only ever be noise for whoever reads the record next."""
    data: dict = {"id": id, "type": type, "title": title}
    if author is not None:
        data["author"] = author
    if issued is not None:
        data["issued"] = issued
    if url is not None:
        data["URL"] = url
    if doi is not None:
        data["DOI"] = doi
    custom: dict = {"tier": tier, "grounding": grounding}
    if canonical_source is not None:
        custom["canonical_source"] = canonical_source
    if acquisition_note is not None:
        custom["acquisition_note"] = acquisition_note
    if edition is not None:
        custom["edition"] = edition
    if edition_check_url is not None:
        custom["edition_check_url"] = edition_check_url
    if locator_kinds is not None:
        custom["locator_kinds"] = list(locator_kinds)
    data["custom"] = custom

    import io
    from ruamel.yaml import YAML

    yaml = YAML()
    yaml.default_flow_style = False
    buf = io.StringIO()
    yaml.dump(data, buf)
    return normalize_record(buf.getvalue(), "source")
