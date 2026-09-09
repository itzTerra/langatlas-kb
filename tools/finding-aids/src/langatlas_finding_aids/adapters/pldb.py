"""PLDB, read from the git mirror (D53, ratified).

The concept-file format is line-oriented `<key> <value>`, and the keys this adapter lifts
are `config/finding-aids.yaml`'s `pldb.fields` — so a PLDB schema change is a config edit,
not a parser rewrite. Unknown keys are ignored rather than erroring: PLDB adds columns
regularly and a monthly mirror refresh must never fail because of one."""
from pathlib import Path

from langatlas_finding_aids.config import FindingAidsConfig
from langatlas_finding_aids.mirror import require_mirror
from langatlas_finding_aids.paths import mirror_dir
from langatlas_finding_aids.results import FindingAidResult, utc_now

_ITEM_URL = "https://pldb.io/concepts/{item_id}.html"


def _parse(text: str, wanted: set[str]) -> dict:
    fields: dict[str, str] = {}
    for line in text.splitlines():
        if not line or line[0].isspace():
            continue                      # indented lines are nested blocks, not fields
        key, _, value = line.partition(" ")
        if key in wanted:
            fields[key] = value.strip()
    return fields


def query_pldb(query: str, *, config: FindingAidsConfig | None = None,
               root: Path | None = None, limit: int = 10) -> list[FindingAidResult]:
    """Substring match over every mirrored concept's fields.

    Deliberately not a ranked search: this is a finding aid, the corpus is ~5,000 short
    records, and a lead the developer has to sift is exactly the intended product. A
    scoring function here would imply an authority the source does not have."""
    config = config or FindingAidsConfig.load()
    state = require_mirror("pldb", root=root)
    directory = (root / "pldb" if root else mirror_dir("pldb")) / "repo"
    wanted = set(config.pldb["fields"])
    needle = query.strip().lower()
    results: list[FindingAidResult] = []
    for path in sorted(directory.glob(config.pldb["concepts_glob"])):
        text = path.read_text(errors="replace")
        if needle and needle not in text.lower():
            continue
        fields = _parse(text, wanted)
        results.append(FindingAidResult(
            source="pldb", item_id=path.stem,
            label=fields.get("name") or fields.get("title") or path.stem,
            fields=fields, url=_ITEM_URL.format(item_id=path.stem),
            retrieved_at=utc_now(), mirror_version=state.version))
        if len(results) >= limit:
            break
    return results
