"""R5's structured findings (D52's named artifact): unmappable features, uninhabited dimension
values, unfittable languages, exclusivity violations — plus the counts 3F's dossier turns into
"% unmappable".

All mechanical over the cells and the compiled spec. A dimension's values are its member
features (D67), so every finding is a statement about cells. And every finding is three-valued
(D49's spirit): only a *verified* answer counts, so a refused, unsourced or unverified cell is
unknown and never counts either way."""
from langatlas_questionnaire.spec import select
from langatlas_research.reality.record import cell_key


def _present(cell: dict | None) -> bool:
    return (cell is not None and cell["status"] == "admitted"
            and cell["answer"] in ("present", "partial"))


def _settled_no(cell: dict | None) -> bool:
    """A verified 'no': an admitted absence, or a carve that does not fit the language."""
    return cell is not None and (cell["status"] == "unmappable"
                                 or (cell["status"] == "admitted" and cell["answer"] == "absent"))


def compute_findings(record: dict, spec: dict) -> tuple[dict, dict]:
    """@returns: `(findings, summary)`, both in reality-check.schema.json's shape."""
    scoped = select(spec, record["scope"]["features"])
    dimensions = {g["dimension"]: g for g in scoped["groups"] if g["kind"] == "dimension"}
    cells = record["cells"]
    by_pair = {(cell["language"], cell["feature"]): cell for cell in cells}
    languages = sorted({cell["language"] for cell in cells})

    uninhabited, unfittable, violations = [], [], []
    for dimension, group in sorted(dimensions.items()):
        members = [item["feature"] for item in group["items"]]
        for feature in members:
            answered = [by_pair[(language, feature)] for language in languages
                        if (language, feature) in by_pair]
            if answered and all(_settled_no(cell) for cell in answered):
                uninhabited.append({"dimension": dimension, "value": feature})
        for language in languages:
            member_cells = [by_pair.get((language, feature)) for feature in members]
            if all(cell is None for cell in member_cells):
                continue                    # D50's mask excluded this language here
            if all(_settled_no(cell) for cell in member_cells):
                unfittable.append(cell_key(language, dimension))
            present = sorted(feature for feature in members
                             if _present(by_pair.get((language, feature))))
            if group["exclusivity"] == "exclusive" and len(present) > 1:
                violations.append({"language": language, "dimension": dimension,
                                   "members": present})

    findings = {"unmappable": sorted(c["key"] for c in cells if c["status"] == "unmappable"),
                "uninhabited_values": uninhabited,
                "unfittable": sorted(unfittable),
                "exclusivity_violations": sorted(violations,
                                                 key=lambda v: (v["language"], v["dimension"]))}

    def count(status: str) -> int:
        return sum(1 for cell in cells if cell["status"] == status)

    summary = {"languages": len(record["runs"]["classify"]), "cells": len(cells),
               "mappable": sum(1 for cell in cells if cell["mappable"]),
               "unmappable": count("unmappable"), "admitted": count("admitted"),
               "refused": count("refused"), "unsourced": count("unsourced"),
               "uncovered": len(record["uncovered"])}
    return findings, summary


def refresh(record: dict, spec: dict) -> dict:
    findings, summary = compute_findings(record, spec)
    return {**record, "findings": findings, "summary": summary}
