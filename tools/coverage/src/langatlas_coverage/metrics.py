"""D52's one computational core: the store read once, keyed by immutable node id.

Every coverage number starts here, so `dossier` and `gaps` can never disagree about what the
store holds. Keying by id rather than slug is the only structural promise D52 needed from
topic 29: a slug rename moves no count."""
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError

from langatlas_ingest.verify.verdicts import fold_verification
from langatlas_validate.compile import derive_facts
from langatlas_validate.ids import compose_instance_id
from langatlas_validate.store import iter_store_records

INSTANCE_STATUSES = ("present", "partial", "absent")
_KINDS = {"feature": "features", "concept": "concepts", "edge": "edges",
          "affects-quality-edge": "quality_edges", "rule": "rules",
          "feature-instance": "instances"}

_yaml = YAML(typ="safe")


class StoreReadError(Exception):
    """The store could not be read as records: a missing directory, unparseable YAML or a
    record of an unexpected shape. The CLI turns it into a message and a non-zero exit."""


@dataclass(frozen=True)
class Store:
    features: dict
    concepts: dict
    edges: dict
    quality_edges: dict
    rules: dict
    instances: dict
    dimensions: dict
    facts: tuple

    @property
    def nodes(self) -> dict:
        return {**self.concepts, **self.features}


def _record_id(kind: str, data: dict) -> str:
    if kind == "feature-instance":
        return compose_instance_id(data["language"], data["feature"])
    return data["id"]


def _load_dimensions(taxonomy: Path) -> dict:
    if not taxonomy.exists():
        return {}
    try:
        loaded = _yaml.load(taxonomy.read_text()) or {}
    except (YAMLError, OSError) as error:
        raise StoreReadError(f"{taxonomy}: cannot be read: {error}") from error
    entries = loaded.get("dimensions") if isinstance(loaded, dict) else None
    if entries is None:
        return {}
    if not isinstance(entries, list) or not all(
            isinstance(entry, dict) and isinstance(entry.get("slug"), str) for entry in entries):
        raise StoreReadError(f"{taxonomy}: `dimensions` must be a list of entries with a slug")
    return {entry["slug"]: entry for entry in entries}


def load_store(repo_root: Path) -> Store:
    root = Path(repo_root)
    if not root.is_dir():
        raise StoreReadError(f"{root}: not a directory")
    buckets: dict[str, dict] = {name: {} for name in _KINDS.values()}
    try:
        records = list(iter_store_records(root))
        for path, kind, _text, data in records:
            if kind not in _KINDS:
                continue
            try:
                buckets[_KINDS[kind]][_record_id(kind, data)] = data
            except (KeyError, TypeError) as error:
                raise StoreReadError(f"{path}: record is missing or mistypes {error}") from error
        facts = tuple(derive_facts(records))
    except StoreReadError:
        raise
    except Exception as error:  # the store walker surfaces parse/shape failures untyped
        raise StoreReadError(f"store under {root} cannot be read: "
                             f"{type(error).__name__}: {error}") from error
    dimensions = _load_dimensions(root / "ontology" / "taxonomy" / "dimensions.yaml")
    return Store(**buckets, dimensions=dimensions, facts=facts)


def instance_counts(store: Store) -> dict[str, dict[str, int]]:
    """Instance count per feature, keyed by feature id — zero rows included, because "no
    instance yet" is exactly what a coverage report has to show."""
    counts = {feature: Counter({status: 0 for status in INSTANCE_STATUSES})
              for feature in store.features}
    for instance in store.instances.values():
        counts.setdefault(instance["feature"],
                          Counter({status: 0 for status in INSTANCE_STATUSES}))
        counts[instance["feature"]][instance["status"]] += 1
    return {feature: dict(counter) for feature, counter in counts.items()}


def dimension_members(store: Store) -> dict[str, list[str]]:
    """D67: a dimension's values are its member layer-3 features."""
    members: dict[str, list[str]] = {slug: [] for slug in store.dimensions}
    for feature_id, feature in sorted(store.features.items()):
        if feature.get("dimension"):
            members.setdefault(feature["dimension"], []).append(feature_id)
    return members


def feature_degrees(store: Store) -> dict[str, int]:
    """Feature↔feature edge degree (both directions)."""
    degree = {feature: 0 for feature in store.features}
    for edge in store.edges.values():
        for endpoint in (edge["from"], edge["to"]):
            if endpoint in degree:
                degree[endpoint] += 1
    return degree


def fact_verification(facts, *, ledger, source_facts: dict) -> dict[str, str]:
    """§6.2's fold over the private ledger's latest verdicts, per cited fact. A fact with no
    citations (an `edge-polarity`) has nothing to fold and is left out."""
    def tier_of(source_id: str) -> str:
        return getattr(source_facts.get(source_id), "tier", "")

    return {fact["fact_id"]: fold_verification(ledger.latest_for(fact["fact_id"]),
                                               tier_of=tier_of, has_since=bool(fact.get("since")))
            for fact in facts if fact.get("sources")}
