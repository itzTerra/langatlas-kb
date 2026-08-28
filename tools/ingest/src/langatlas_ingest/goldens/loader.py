from pathlib import Path
from ruamel.yaml import YAML
from langatlas_ingest.errors import GoldenItemInvalid
from langatlas_ingest.goldens.items import (
    ALLOWED_CONTROVERSY_INPUTS, ANNOTATIONS, CONTROVERSY_LEVELS,
    FORBIDDEN_CONTROVERSY_INPUTS, MAX_QUOTE_WORDS, REQUIRED_ANNOTATION, SINCE_STATUSES,
    STRATA, STRATUM_VERDICTS, VERDICTS, Citation, Claim, ControversyCase, VerifierItem,
)
from langatlas_ingest.paths import (
    GOLDEN_CONTROVERSY_DIR, GOLDEN_VERIFIER_DIR, GOLDEN_VERIFIER_HELD_OUT_DIR,
)
from langatlas_validate.claims import FREETEXT_KINDS, TEMPLATED_KINDS
from langatlas_validate.locators import validate_locator_shape
from langatlas_validate.paths import REPO_ROOT

_yaml = YAML(typ="safe")
_KNOWN_KINDS = set(TEMPLATED_KINDS) | set(FREETEXT_KINDS)

# Section 6.4's set-level targets, in one place so the README, the `--complete` checker
# and 2D's calibration write-up cannot drift apart.
SET_INVARIANTS = {
    "min_items": 200,
    "max_items": 300,
    "correct_share_min": 0.35,          # "~40% correct" with a 5-point tolerance
    "correct_share_max": 0.45,
    "overstated_share_min": 0.10,       # over-weighted per Section 6.4
    "wrong_since_share_min": 0.10,      # both `since` strata together, over-weighted
    "min_absent_items": 15,             # so D49's ladder is calibrated by the same set
    "min_contamination_gauge": 20,
    "held_out_min": 10,
    "held_out_max": 15,
}


def _claim(raw: dict) -> Claim:
    return Claim(kind=raw.get("kind", ""), text=raw.get("text", ""),
                 rendered=raw.get("rendered"), status=raw.get("status"),
                 since=raw.get("since"),
                 expected_since_status=raw.get("expected_since_status"),
                 absence_scope=raw.get("absence_scope"),
                 feature_aliases=tuple(raw.get("feature_aliases") or ()))


def _item(raw: dict, *, held_out: bool) -> VerifierItem:
    item_id = raw.get("id")
    if not item_id:
        raise GoldenItemInvalid(None, "has no `id`")
    if not raw.get("curated", True):
        # The candidate generator writes `curated: false`; the developer flips it after
        # reading the item. Refusing to load it is what makes "the developer curates"
        # a property of the pipeline rather than a note in a README.
        raise GoldenItemInvalid(item_id, "is an uncurated candidate — a generated item"
                                " enters the set only after a human has read it")
    return VerifierItem(
        id=item_id, stratum=raw.get("stratum", ""),
        expected_verdict=raw.get("expected_verdict", ""),
        claim=_claim(raw.get("claim") or {}),
        citation=Citation(**{k: v for k, v in (raw.get("citation") or {}).items()
                             if k in ("source", "locator", "quote")}),
        evidence_chunk_ids=tuple(raw.get("evidence_chunk_ids") or ()),
        expected_annotations=tuple(raw.get("expected_annotations") or ()),
        shape_invalid=bool(raw.get("shape_invalid", False)),
        contamination_gauge=bool(raw.get("contamination_gauge", False)),
        authored_by=raw.get("authored_by", "developer"), notes=raw.get("notes", ""),
        held_out=held_out)


def _read(path: Path, key: str) -> list[dict]:
    return (_yaml.load(path.read_text()) or {}).get(key) or []


def load_verifier_items(directory: Path | None = None, *,
                        include_held_out: bool = False) -> list[VerifierItem]:
    """Load every committed verifier golden item under `directory`.

    @param directory - the verifier golden directory (default `GOLDEN_VERIFIER_DIR`)
    @param include_held_out - also load the `held-out/` audit slice

    @returns the loaded items, held-out ones flagged `held_out=True`
    """
    directory = Path(directory or GOLDEN_VERIFIER_DIR)
    held_out_dir = directory / GOLDEN_VERIFIER_HELD_OUT_DIR.name
    items = [_item(raw, held_out=False)
             for path in sorted(directory.glob("*.yaml"))
             for raw in _read(path, "items")]
    if include_held_out and held_out_dir.is_dir():
        items += [_item(raw, held_out=True)
                  for path in sorted(held_out_dir.glob("*.yaml"))
                  for raw in _read(path, "items")]
    return items


def load_controversy_cases(directory: Path | None = None) -> list[ControversyCase]:
    directory = Path(directory or GOLDEN_CONTROVERSY_DIR)
    cases = []
    for path in sorted(directory.glob("*.yaml")):
        for raw in _read(path, "cases"):
            if not raw.get("curated", True):
                raise GoldenItemInvalid(raw.get("id"), "is an uncurated candidate")
            cases.append(ControversyCase(
                id=raw.get("id"), expected_level=raw.get("expected_level"),
                inputs=raw.get("inputs") or {},
                expected_signals=tuple(raw.get("expected_signals") or ()),
                authored_by=raw.get("authored_by", "developer"),
                notes=raw.get("notes", "")))
    return cases


def _item_errors(item: VerifierItem, sources: set[str] | None) -> list[str]:
    errors, where = [], f"{item.id}:"
    if item.stratum not in STRATA:
        errors.append(f"{where} unknown stratum {item.stratum!r}")
    if item.expected_verdict not in VERDICTS:
        errors.append(f"{where} unknown verdict {item.expected_verdict!r}")
    allowed = STRATUM_VERDICTS.get(item.stratum)
    if allowed and item.expected_verdict not in allowed:
        errors.append(f"{where} stratum {item.stratum!r} cannot expect verdict"
                      f" {item.expected_verdict!r} (allowed: {sorted(allowed)})")
    required = REQUIRED_ANNOTATION.get(item.stratum)
    if required and required not in item.expected_annotations:
        errors.append(f"{where} stratum {item.stratum!r} must expect the"
                      f" {required!r} annotation")
    for annotation in item.expected_annotations:
        if annotation not in ANNOTATIONS:
            errors.append(f"{where} unknown annotation {annotation!r}")
    if item.claim.kind not in _KNOWN_KINDS:
        errors.append(f"{where} unknown claim kind {item.claim.kind!r}")
    if not item.claim.text.startswith(f"{item.claim.kind}("):
        errors.append(f"{where} claim text does not open with its kind"
                      f" {item.claim.kind!r}")
    if item.claim.expected_since_status and \
            item.claim.expected_since_status not in SINCE_STATUSES:
        errors.append(f"{where} unknown since status"
                      f" {item.claim.expected_since_status!r}")
    if item.claim.since and item.expected_verdict in ("supported", "partial") \
            and not item.claim.expected_since_status:
        # Only pairs that still resolve to a status need one: a `contradicted` since
        # assertion is neither since-supported nor as-of-supported, it is refuted.
        errors.append(f"{where} carries a `since` and expects"
                      f" {item.expected_verdict!r}, so it must say which side of the"
                      " as-of/since-supported split it lands on")
    if item.claim.status == "absent":
        if not item.claim.absence_scope:
            errors.append(f"{where} an absent claim needs `absence_scope` (D49)")
        if not item.claim.feature_aliases:
            errors.append(f"{where} an absent claim needs `feature_aliases` — D49's"
                          " negative full-text grep runs over them")
    if item.citation.quote and len(item.citation.quote.split()) > MAX_QUOTE_WORDS:
        errors.append(f"{where} quote exceeds D14's {MAX_QUOTE_WORDS}-word cap")
    if REQUIRED_ANNOTATION.get(item.stratum) and not item.citation.quote:
        errors.append(f"{where} stratum {item.stratum!r} needs a quote to test")
    if not item.shape_invalid and validate_locator_shape(item.citation.locator) is None:
        errors.append(f"{where} locator {item.citation.locator!r} does not match the"
                      " Section 4.3 grammar; set `shape_invalid: true` if that is"
                      " deliberate")
    if sources is not None and item.citation.source not in sources:
        errors.append(f"{where} cites unknown source {item.citation.source!r}")
    return errors


def validate_items(items, *, sources_dir: Path | None = None) -> list[str]:
    """Per-item shape validation. Pure: no database, no provider, no network — so it can
    run in CI, where neither exists.

    @param sources_dir - directory of committed `sources/*.yaml`; None skips the
        source-existence check (used by unit tests that cite fixture ids)

    @returns human-readable error strings, empty when every item is well formed
    """
    sources = None
    if sources_dir is not None:
        sources = {path.stem for path in Path(sources_dir).glob("*.yaml")
                   if not path.stem.startswith("_")}
    errors, seen = [], set()
    for item in items:
        if item.id in seen:
            errors.append(f"{item.id}: duplicate id")
        seen.add(item.id)
        errors.extend(_item_errors(item, sources))
    return errors


def validate_controversy_cases(cases) -> list[str]:
    errors, seen = [], set()
    for case in cases:
        where = f"{case.id}:"
        if case.id in seen:
            errors.append(f"{where} duplicate id")
        seen.add(case.id)
        if case.expected_level not in CONTROVERSY_LEVELS:
            errors.append(f"{where} level {case.expected_level!r} is not 0-3")
        for key in case.inputs:
            if key in FORBIDDEN_CONTROVERSY_INPUTS:
                errors.append(f"{where} input {key!r} is human-challenge-derived and is"
                              " excluded from the assessor by Section 6.4")
            elif key not in ALLOWED_CONTROVERSY_INPUTS:
                errors.append(f"{where} unknown structured input {key!r}")
        if not case.inputs:
            errors.append(f"{where} has no structured inputs")
    return errors


def _share(count: int, total: int) -> float:
    return count / total if total else 0.0


def validate_set(items, held_out) -> list[str]:
    """Set-level invariants: the shape checks above say each item is well formed; these
    say the *set* is the one Section 6.4 specified. Run at closeout (`--complete`), never
    during incremental authoring, where every one of them is legitimately unmet."""
    errors, total = [], len(items)
    inv = SET_INVARIANTS
    if not inv["min_items"] <= total <= inv["max_items"]:
        errors.append(f"set has {total} items; Section 6.4 asks for"
                      f" {inv['min_items']}-{inv['max_items']}")
    missing = sorted(set(STRATA) - {item.stratum for item in items})
    if missing:
        errors.append(f"stratum coverage gap: {missing}")
    correct = _share(sum(1 for i in items if i.expected_verdict == "supported"), total)
    if not inv["correct_share_min"] <= correct <= inv["correct_share_max"]:
        errors.append(f"correct share {correct:.0%} is outside the"
                      f" {inv['correct_share_min']:.0%}-{inv['correct_share_max']:.0%}"
                      " band Section 6.4 asks for")
    overstated = _share(sum(1 for i in items if i.stratum == "overstated-claim"), total)
    if overstated < inv["overstated_share_min"]:
        errors.append(f"overstated-claim share {overstated:.0%} is under the"
                      f" {inv['overstated_share_min']:.0%} over-weighting floor")
    since_strata = {"wrong-since-off-by-one", "wrong-since-off-by-major"}
    wrong_since = _share(sum(1 for i in items if i.stratum in since_strata), total)
    if wrong_since < inv["wrong_since_share_min"]:
        errors.append(f"wrong-`since` share {wrong_since:.0%} is under the"
                      f" {inv['wrong_since_share_min']:.0%} over-weighting floor")
    absent = sum(1 for i in items if i.claim.status == "absent")
    if absent < inv["min_absent_items"]:
        errors.append(f"{absent} `status: absent` items; D49's ladder needs at least"
                      f" {inv['min_absent_items']}")
    gauge = sum(1 for i in items if i.contamination_gauge)
    if gauge < inv["min_contamination_gauge"]:
        errors.append(f"{gauge} contamination-gauge items; at least"
                      f" {inv['min_contamination_gauge']} obscure-locus items are needed"
                      " for the gauge to mean anything")
    if not inv["held_out_min"] <= len(held_out) <= inv["held_out_max"]:
        errors.append(f"held-out slice has {len(held_out)} items; Section 6.4 asks for"
                      f" {inv['held_out_min']}-{inv['held_out_max']}")
    non_developer = [i.id for i in held_out if i.authored_by != "developer"]
    if non_developer:
        errors.append(f"held-out items not developer-authored: {non_developer}")
    return errors
