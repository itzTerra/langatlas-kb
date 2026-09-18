"""The compiled spec as an artifact: its committed path, its rendering, its schema — and the
three ways a consumer reads it: `select` a theme's slice (R5), `instantiate` it for one language
(R5 now, the sweep launcher in Stage 5), and `diff_specs` two versions (D46's delta
questionnaire, feeding D38's `fact_remap` requeue list)."""
import io
import json
from functools import lru_cache
from pathlib import Path
from typing import Iterator

from jsonschema import Draft202012Validator
from ruamel.yaml import YAML

from langatlas_questionnaire.compiler import LANG_PLACEHOLDER

SPEC_DIR = "questionnaire"
_SCHEMA = Path(__file__).with_name("spec.schema.json")

# Item keys that are context, not the question. Changing one changes how an item reads, never
# what a sweep agent must answer — a delta that requeued on them would re-ask every item whose
# summary got a copyedit (D46: requeue exactly the changed anchors).
_CONTEXT_KEYS = frozenset({"name", "summary", "aliases"})

_yaml = YAML(typ="safe")


def spec_rel(version: str) -> str:
    return f"{SPEC_DIR}/spec-{version}.yaml"


def render_spec(spec: dict) -> str:
    yaml = YAML()
    yaml.indent(mapping=2, sequence=4, offset=2)
    yaml.width = 100
    buf = io.StringIO()
    yaml.dump(spec, buf)
    return buf.getvalue()


def write_spec(spec: dict, repo_root: Path) -> Path:
    path = Path(repo_root) / spec_rel(spec["ontology_version"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_spec(spec))
    return path


def load_spec(path: Path) -> dict:
    return _yaml.load(Path(path).read_text())


@lru_cache(maxsize=1)
def _validator() -> Draft202012Validator:
    return Draft202012Validator(json.loads(_SCHEMA.read_text()))


def validate_spec(spec: dict) -> list[str]:
    """@returns one error string per violation, empty when the spec is valid."""
    return [f"{'/'.join(str(p) for p in e.absolute_path) or '<root>'}: {e.message}"
            for e in sorted(_validator().iter_errors(spec), key=str)]


def iter_items(spec: dict) -> Iterator[tuple[dict, dict]]:
    """Every item as `(group, item)`. A standalone group is its own item, minus `kind`."""
    for group in spec["groups"]:
        if group["kind"] == "dimension":
            for item in group["items"]:
                yield group, item
        else:
            yield group, {key: value for key, value in group.items() if key != "kind"}


def _constraint_features(constraint: dict) -> set[str]:
    if constraint["kind"] == "requires":
        return {constraint["if_present"], constraint["then_present"]}
    if constraint["kind"] == "conflicts-with":
        return set(constraint["features"])
    return set(constraint["when_all"]) | set(constraint["then"])


def select(spec: dict, features) -> dict:
    """The slice of `spec` that asks about `features` — a theme's questionnaire."""
    wanted = set(features)
    groups = []
    for group in spec["groups"]:
        if group["kind"] == "dimension":
            items = [item for item in group["items"] if item["feature"] in wanted]
            if items:
                groups.append({**group, "items": items})
        elif group["feature"] in wanted:
            groups.append(group)
    constraints = [c for c in spec["constraints"] if _constraint_features(c) & wanted]
    return {**spec, "groups": groups, "constraints": constraints}


def instantiate(spec: dict, language: str, *,
                language_kind: str = "general-purpose") -> list[dict]:
    """One item per (language, feature) the language's kind reaches, anchors filled in.

    D50's `applies_to` mask is the only filter, and it is mechanical: a dimension group whose
    `applies_to` does not include `language_kind` is skipped (those cells derive `not-applicable`
    at build time). Standalone items have no `applies_to` and are always asked."""
    items = []
    for group, item in iter_items(spec):
        dimension = None
        if group["kind"] == "dimension":
            if language_kind not in group["applies_to"]:
                continue
            dimension = group["dimension"]
        items.append({**item, "dimension": dimension,
                      "anchor_prefix": item["anchor_prefix"].replace(LANG_PLACEHOLDER,
                                                                     language)})
    return items


def _identity(group: dict, item: dict) -> dict:
    identity = {key: value for key, value in item.items() if key not in _CONTEXT_KEYS}
    if group["kind"] == "dimension":
        identity.update(dimension=group["dimension"], exclusivity=group["exclusivity"],
                        applies_to=group["applies_to"])
    return identity


def diff_specs(old: dict, new: dict) -> dict:
    """D46's delta questionnaire, compared by `anchor_prefix`.

    `added` + `changed` is the requeue set; `removed` anchors belong to D38's tombstone
    dispositions, not to a re-ask. An item is `changed` when anything but its wording changed —
    its layer, its dimension, or that dimension's `exclusivity`/`applies_to`."""
    before = {item["anchor_prefix"]: _identity(group, item) for group, item in iter_items(old)}
    after = {item["anchor_prefix"]: _identity(group, item) for group, item in iter_items(new)}
    old_constraints = {c["id"]: c for c in old["constraints"]}
    new_constraints = {c["id"]: c for c in new["constraints"]}
    return {
        "from": old["ontology_version"], "to": new["ontology_version"],
        "added": sorted(set(after) - set(before)),
        "removed": sorted(set(before) - set(after)),
        "changed": sorted(a for a in set(before) & set(after) if before[a] != after[a]),
        "constraints_added": sorted(set(new_constraints) - set(old_constraints)),
        "constraints_removed": sorted(set(old_constraints) - set(new_constraints)),
        "constraints_changed": sorted(i for i in set(old_constraints) & set(new_constraints)
                                      if old_constraints[i] != new_constraints[i]),
    }
