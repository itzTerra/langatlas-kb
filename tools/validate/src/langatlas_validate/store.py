from pathlib import Path
from typing import Iterator

from ruamel.yaml import YAML

from langatlas_validate.claims import TEMPLATED_KINDS, validate_claim_template
from langatlas_validate.ids import canonical_endpoints, canonical_when_all, contradiction_key
from langatlas_validate.normalize import normalize_record
from langatlas_validate.schema import validate_record

_yaml = YAML(typ="safe")

# path glob -> record kind, or a callable(data) -> kind when the directory alone is
# ambiguous (edges/ holds two kinds, discriminated by the record's own "type" field).
_LEDGERS = {"_tombstones.yaml", "_registry.yaml", "tombstones.yaml", "contradictions.yaml",
           "overrides.yaml"}


def iter_store_records(repo_root: Path) -> Iterator[tuple[Path, str, str, dict]]:
    """Walks the canonical store per §3.3's layout, yielding every validated-record
    file. Root-level ledgers (`_tombstones.yaml`, `overrides.yaml`, ...), `.gitkeep`,
    and `languages/_registry.yaml` (a language-registry record, not walked here since
    it has exactly one instance and its own `language-registry` kind — added back in
    explicitly below) are excluded from the generic walk."""
    for path in sorted((repo_root / "concepts").glob("*.yaml")):
        yield from _load(path, "concept")
    for path in sorted((repo_root / "features").glob("*.yaml")):
        yield from _load(path, "feature")

    registry = repo_root / "languages" / "_registry.yaml"
    if registry.exists():
        yield from _load(registry, "language-registry")
    for lang_dir in sorted((repo_root / "languages").iterdir()) if (repo_root / "languages").exists() else []:
        if not lang_dir.is_dir():
            continue
        lang_file = lang_dir / "language.yaml"
        if lang_file.exists():
            yield from _load(lang_file, "language")
        instances_dir = lang_dir / "instances"
        if instances_dir.exists():
            for path in sorted(instances_dir.glob("*.yaml")):
                yield from _load(path, "feature-instance")

    edges_root = repo_root / "edges"
    if edges_root.exists():
        for from_dir in sorted(edges_root.iterdir()):
            if not from_dir.is_dir():
                continue
            for path in sorted(from_dir.glob("*.yaml")):
                text = path.read_text()
                data = _yaml.load(text)
                kind = "affects-quality-edge" if data.get("type") == "affects-quality" else "edge"
                yield path, kind, text, data

    rules_root = repo_root / "rules"
    if rules_root.exists():
        for path in sorted(rules_root.glob("*.yaml")):
            yield from _load(path, "rule")

    sources_root = repo_root / "sources"
    if sources_root.exists():
        for path in sorted(sources_root.glob("*.yaml")):
            if path.name in _LEDGERS:
                continue
            yield from _load(path, "source")


def _load(path: Path, kind: str) -> Iterator[tuple[Path, str, str, dict]]:
    if path.name == ".gitkeep":
        return
    text = path.read_text()
    if not text.strip():
        return
    data = _yaml.load(text)
    yield path, kind, text, data


def validate_contradictions(repo_root: Path) -> list[str]:
    """D45's register is a root-level content-keyed ledger, not a walked record file, so
    it needs its own gate: schema validity, the id-is-the-content-key invariant, and no
    duplicate ids.

    A missing file is valid — a repo that has never minted a contradiction is a normal
    repo, and `contradictions: []` is the committed empty state.

    @param repo_root: the canonical store's root directory.
    @returns: error strings, one per violation found, each prefixed
        `contradictions.yaml[<id>]:`.
    """
    path = repo_root / "contradictions.yaml"
    if not path.exists():
        return []
    data = _yaml.load(path.read_text()) or {}
    records = data.get("contradictions") or []
    errors: list[str] = []
    seen: set[str] = set()
    for record in records:
        record_id = record.get("id", "<no id>")
        errors.extend(f"contradictions.yaml[{record_id}]: {e}"
                      for e in validate_record(record, "contradiction"))
        participants = record.get("participants") or []
        if participants and record_id != contradiction_key(participants):
            errors.append(f"contradictions.yaml[{record_id}]: id is not the content key"
                          f" of its participants (expected"
                          f" {contradiction_key(participants)})")
        if record_id in seen:
            errors.append(f"contradictions.yaml[{record_id}]: duplicate id")
        seen.add(record_id)
    return errors


def validate_store(repo_root: Path) -> list[str]:
    """CI's store-validating gate (D13): schema validity + normalization drift for
    every live record, the claim-template registry's own self-check, D64's canonical-ordering
    rule for `alternative-to` edges and rules' `when_all`, and cross-record referential
    integrity (§3.3 — added in Stage 3A, the first stage that mints nodes)."""
    from langatlas_validate.references import validate_references

    errors: list[str] = []

    for kind in TEMPLATED_KINDS:
        errors.extend(f"claim-templates/{kind}: {e}" for e in validate_claim_template(kind))

    errors.extend(validate_contradictions(repo_root))

    for path, kind, text, data in iter_store_records(repo_root):
        rel = path
        for e in validate_record(data, kind):
            errors.append(f"{rel}: {e}")
        if normalize_record(text, kind) != text:
            errors.append(f"{rel}: not normalized (re-run the normalizer to fix)")

        if kind == "edge" and data.get("type") == "alternative-to":
            frm, to = data.get("from"), data.get("to")
            if isinstance(frm, str) and isinstance(to, str):
                if (frm, to) != canonical_endpoints(frm, to):
                    errors.append(f"{rel}: alternative-to endpoints not lexicographically ordered")
        if kind == "rule":
            when_all = data.get("when_all")
            if isinstance(when_all, list) and all(isinstance(x, str) for x in when_all):
                if when_all != canonical_when_all(when_all):
                    errors.append(f"{rel}: when_all not canonically (lexicographically) ordered")
        if kind == "source":
            custom = data.get("custom") if isinstance(data.get("custom"), dict) else {}
            if not custom.get("canonical_source") and not custom.get("acquisition_note"):
                errors.append(f"{rel}: custom.acquisition_note required for a non-canonical source")

    errors.extend(validate_references(repo_root))
    return errors
