"""D29's identification-metadata carve-out, as a deliberately separate path.

Everything else this package produces is a `FindingAidResult` — an envelope with no
citation shape. This module is the *only* place a finding aid becomes a `sources/` record,
it does so for two named fields, and it says so in the record it writes.

Per D29's 2026-07-20 note, the resulting record is an **attribution** citation for ungated
registry data (file extensions, first-appeared years live on the Language registry record
and never pass D4/D24's admissibility gate). Minting one is therefore not an admission of
anything into the knowledge base; it is how the registry says where it got a number."""
import io
from pathlib import Path

from ruamel.yaml import YAML

from langatlas_validate.normalize import normalize_record
from langatlas_validate.paths import REPO_ROOT

from langatlas_finding_aids.results import FindingAidResult

_yaml = YAML()
_yaml.default_flow_style = False

# The complete list. Widening it is a decision, not a refactor: every addition is one more
# thing a community source is trusted to state about a language.
IDENTIFICATION_FIELDS = ("file-extension", "first-appeared")

_TYPE_BY_SOURCE = {"wikidata": "webpage", "pldb": "webpage",
                   "hyperpolyglot": "webpage", "wikipedia": "webpage"}
_TITLE = {"wikidata": "Wikidata", "pldb": "PLDB", "hyperpolyglot": "Hyperpolyglot",
          "wikipedia": "Wikipedia"}


class NotIdentificationMetadata(ValueError):
    """A caller tried to mint a citation for something outside D29's carve-out."""


def identification_source_id(result: FindingAidResult, field: str) -> str:
    return f"{result.source}-{result.item_id.lower().replace(' ', '-')}-{field}"


def mint_identification_source(result: FindingAidResult, field: str, *,
                               repo_root: Path | None = None) -> Path:
    """@returns the path of the written `sources/*.yaml` record — the caller reviews and
        commits it (this module never lands anything)

    @raises NotIdentificationMetadata for any field outside `IDENTIFICATION_FIELDS`
    """
    if field not in IDENTIFICATION_FIELDS:
        raise NotIdentificationMetadata(
            f"{field!r} is not identification metadata; D29 allows only"
            f" {IDENTIFICATION_FIELDS} to be sourced from a finding aid, and everything"
            " else needs a verified tier-A/B source")
    source_id = identification_source_id(result, field)
    path = Path(repo_root or REPO_ROOT) / "sources" / f"{source_id}.yaml"
    data = {
        "id": source_id,
        "type": _TYPE_BY_SOURCE.get(result.source, "webpage"),
        "title": f"{_TITLE.get(result.source, result.source)}: {result.label}"
                 f" ({field})",
        "URL": result.url,
        "custom": {
            "tier": "D",
            "grounding": "third-party-reference",
            "canonical_source": False,
            "acquisition_note":
                f"Attribution for one identification metadata point ({field}) taken from"
                f" {result.source} on {result.retrieved_at}. This is ungated registry"
                " data per D29 — this citation records provenance and never backs a"
                " gated fact.",
            "accessed": result.retrieved_at,
            "added_by": "langatlas-finding-aids",
        },
    }
    buf = io.StringIO()
    _yaml.dump(data, buf)
    path.write_text(normalize_record(buf.getvalue(), "source"))
    return path
