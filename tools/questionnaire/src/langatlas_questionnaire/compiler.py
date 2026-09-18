"""D46's questionnaire compiler (§7.3): the ontology tree in, the sweep questionnaire out.

Six mechanical steps and zero judgment calls — that is what makes "compiled" a guarantee rather
than a label. Nothing that would need a judgment is here: which features a language is *likely*
to have is banned outright (D46; D50's `applies_to` mask is applied at instantiation, not here),
and how to phrase a question belongs to the hand-authored, versioned sweep prompt.

1. Read every feature: id, name, layer, dimension, summary, aliases.
2. Group by `dimension`, attaching that dimension's label, `exclusivity` (D39) and `applies_to`
   (D50) once per group. The group's items ARE the dimension's values (D67).
3. Give every item the fixed fact-bearing field list (`FACT_FIELDS`). Layer decides grouping,
   never field selection.
4. Compile hard `requires` / `conflicts-with` edges to `constraints:`.
5. Compile every Rule to `constraints:`, verbatim.
6. Stamp `ontology_version` and `compiler_version`, and order everything canonically.

`influences`, `enables`, `alternative-to` and `affects-quality` edges compile to nothing: they
are ontology-level judgments with no per-language answer (D46)."""
from importlib.metadata import version as _distribution_version
from pathlib import Path

from ruamel.yaml import YAML

from langatlas_questionnaire.fields import FACT_FIELDS
from langatlas_validate.store import iter_store_records, validate_store

LANG_PLACEHOLDER = "<lang>"

_yaml = YAML(typ="safe")


class CompileError(Exception):
    """The store cannot be compiled — a questionnaire compiled from an invalid store would ask
    about features the store's own references cannot resolve."""


def compiler_version() -> str:
    return _distribution_version("langatlas-questionnaire")


def _taxonomy_dimensions(repo_root: Path) -> dict[str, dict]:
    data = _yaml.load((repo_root / "ontology" / "taxonomy" / "dimensions.yaml").read_text())
    return {entry["slug"]: entry for entry in (data or {}).get("dimensions") or []}


def _item(feature: dict) -> dict:
    return {"feature": feature["id"], "name": feature["name"], "layer": feature["layer"],
            "summary": feature["summary"]["text"],
            "aliases": list(feature.get("aliases") or []),
            "anchor_prefix": f"fi.{LANG_PLACEHOLDER}.{feature['id']}",
            "fields": list(FACT_FIELDS)}


def _constraint(kind: str, data: dict) -> dict | None:
    if kind == "edge" and data["type"] == "requires":
        return {"kind": "requires", "id": data["id"], "if_present": data["from"],
                "then_present": data["to"]}
    if kind == "edge" and data["type"] == "conflicts-with":
        return {"kind": "conflicts-with", "id": data["id"],
                "features": sorted([data["from"], data["to"]])}
    if kind == "rule":
        return {"kind": "rule", "id": data["id"], "when_all": list(data["when_all"]),
                "effect": data["effect"], "then": list(data.get("then") or [])}
    return None


def compile_spec(repo_root: Path) -> dict:
    """@returns the language-agnostic spec — a plain dict, byte-stable when rendered.
    @raises CompileError: the store does not pass `validate_store`."""
    repo_root = Path(repo_root)
    errors = validate_store(repo_root)
    if errors:
        more = f" (+{len(errors) - 10} more)" if len(errors) > 10 else ""
        raise CompileError("the store does not validate, so it cannot be compiled: "
                           + "; ".join(errors[:10]) + more)
    records = list(iter_store_records(repo_root))

    # Step 1.
    features = sorted((data for _p, kind, _t, data in records if kind == "feature"),
                      key=lambda data: data["id"])
    dimensions = _taxonomy_dimensions(repo_root)

    # Steps 2 and 3.
    members: dict[str, list[dict]] = {}
    standalone: list[dict] = []
    for feature in features:
        if feature.get("dimension"):
            members.setdefault(feature["dimension"], []).append(_item(feature))
        else:
            standalone.append(_item(feature))
    groups, diagnostics = [], []
    for slug in sorted(dimensions):
        if slug not in members:
            diagnostics.append({"kind": "dimension-without-features", "dimension": slug})
            continue
        if len(members[slug]) == 1:
            diagnostics.append({"kind": "dimension-with-one-feature", "dimension": slug})
        entry = dimensions[slug]
        groups.append({"kind": "dimension", "dimension": slug, "label": entry["label"],
                       "exclusivity": entry.get("exclusivity", "exclusive"),
                       "applies_to": list(entry.get("applies_to") or ["general-purpose"]),
                       "items": members[slug]})
    for item in sorted(standalone, key=lambda item: (item["layer"], item["feature"])):
        groups.append({"kind": "standalone", **item})

    # Steps 4 and 5.
    constraints = [constraint for _p, kind, _t, data in records
                   if (constraint := _constraint(kind, data)) is not None]
    constraints.sort(key=lambda constraint: constraint["id"])

    # Step 6.
    version = (repo_root / "ontology" / "VERSION").read_text().strip()
    return {"ontology_version": version, "compiler_version": compiler_version(),
            "fields": {name: list(members) for name, members in FACT_FIELDS.items()},
            "groups": groups, "constraints": constraints, "diagnostics": diagnostics}
