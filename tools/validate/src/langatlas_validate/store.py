import re
from pathlib import Path
from typing import Iterator

from ruamel.yaml import YAML

from langatlas_validate.claims import TEMPLATED_KINDS, validate_claim_template
from langatlas_validate.ids import canonical_endpoints, canonical_when_all, contradiction_key
from langatlas_validate.normalize import normalize_record
from langatlas_validate.schema import validate_record

_yaml = YAML(typ="safe")

# §6.4's closed signal grammar. A signal is a machine reference into a debate, a verdict, a
# contradiction record or an assessment spread — never a sentence.
_SIGNAL_RE = re.compile(
    r"^(debate:[a-z0-9-]+:[a-z-]+"
    r"|verdict:[a-z-]+:[a-z-]+"
    r"|contradiction:ctr-[0-9a-f]{12}:[a-z-]+"
    r"|assessment-spread:[a-z0-9_-]+)$")

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


def validate_controversy_blocks(records) -> list[str]:
    """D21/D25: what a machine-written controversy block may say.

    @param records: `(rel_path, kind, data, fact_ids)` tuples — `fact_ids` are the ids that
        record's own `derive_facts` row produced, so a block left behind by a claim edit is
        caught here rather than surfacing on the site as a level attached to nothing.
    @returns one message per violation."""
    errors = []
    for rel, _kind, data, fact_ids in records:
        seen = set()
        for entry in data.get("controversy") or []:
            where = f"{rel}[controversy:{entry.get('key')}]"
            if entry.get("level") == 0:
                errors.append(f"{where}: level 0 is written as an absent entry (§6.4), not"
                              f" as a stored 0")
            if entry.get("key") in seen:
                errors.append(f"{where}: duplicate key")
            seen.add(entry.get("key"))
            if entry.get("fact_id") not in set(fact_ids):
                errors.append(f"{where}: names fact {entry.get('fact_id')!r}, which this"
                              f" record does not derive — re-run the assessor")
            for signal in entry.get("signals") or []:
                if not _SIGNAL_RE.match(signal):
                    errors.append(f"{where}: {signal!r} is not a machine reference; §6.4's"
                                  f" signals list is the justification and admits no prose")
    return errors


def validate_store(repo_root: Path) -> list[str]:
    """CI's store-validating gate (D13): schema validity + normalization drift for
    every live record, the claim-template registry's own self-check, D64's canonical-ordering
    rule for `alternative-to` edges and rules' `when_all`, and cross-record referential
    integrity (§3.3 — added in Stage 3A, the first stage that mints nodes), and the tombstone
    ledger and the redirect map (§3.2/§5.1 — Stage 3F)."""
    from langatlas_validate.compile import derive_facts
    from langatlas_validate.references import validate_references

    errors: list[str] = []

    for kind in TEMPLATED_KINDS:
        errors.extend(f"claim-templates/{kind}: {e}" for e in validate_claim_template(kind))

    errors.extend(validate_contradictions(repo_root))

    store_records = list(iter_store_records(repo_root))
    facts = derive_facts(store_records)

    by_path: dict[str, list[str]] = {}
    for fact in facts:
        by_path.setdefault(fact["record_path"], []).append(fact["fact_id"])
    errors.extend(validate_controversy_blocks(
        [(str(path), kind, data, by_path.get(str(path), []))
         for path, kind, _text, data in store_records]))

    for path, kind, text, data in store_records:
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

    from langatlas_validate.redirects import REDIRECTS_REL, load_redirects, validate_redirects
    from langatlas_validate.tombstones import (
        TOMBSTONES_REL, load_tombstones, validate_tombstones,
    )

    live = {fact["fact_id"] for fact in facts}
    errors.extend(f"{TOMBSTONES_REL}: {e}"
                  for e in validate_tombstones(load_tombstones(repo_root), live=live))
    nodes = {data["id"]: data.get("slug") for _p, kind, _t, data in store_records
             if kind in ("feature", "concept")}
    errors.extend(f"{REDIRECTS_REL}: {e}"
                  for e in validate_redirects(load_redirects(repo_root), nodes=nodes))

    errors.extend(validate_references(repo_root))
    return errors
