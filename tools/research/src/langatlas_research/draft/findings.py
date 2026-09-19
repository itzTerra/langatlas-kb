"""The finding vocabulary the R4 roles share (ontologist, edge drafter, R6's cross-theme drafter).

`structure-friction` is the D70 addition: the sign that the seed structure, not the carve, is
what does not fit. It is classified, not free prose, so the structure review can group findings
by the structural element at issue and by whether they concern ontology structure or a
neighbouring ("adjacent") schema."""
from typing import Literal

from pydantic import BaseModel, Field, model_validator

FINDING_KINDS = ("rule-candidate", "cross-theme-edge", "unmappable-candidate",
                 "missing-locator-backend", "structure-friction")
STRUCTURE_ELEMENTS = ("layers", "concept-feature-split", "realizes", "edge-types",
                      "dimension-model", "qualities", "record-kinds", "other")
STRUCTURE_AREAS = ("ontology", "adjacent")


class FindingOut(BaseModel):
    kind: Literal[FINDING_KINDS]                    # type: ignore[valid-type]
    detail: str
    keys: list[str] = Field(default_factory=list)
    area: Literal[STRUCTURE_AREAS] | None = None    # type: ignore[valid-type]
    element: Literal[STRUCTURE_ELEMENTS] | None = None   # type: ignore[valid-type]

    @model_validator(mode="after")
    def _only_friction_is_classified(self):
        friction = self.kind == "structure-friction"
        if friction and (self.area is None or self.element is None):
            raise ValueError("a structure-friction finding needs `area` and `element`")
        if not friction and (self.area is not None or self.element is not None):
            raise ValueError("only a structure-friction finding carries `area` / `element`")
        return self

    def as_entry(self) -> dict:
        """The plan-file shape: unset fields are absent, so a finding of an older kind is
        byte-identical to what the plan held before D70."""
        return self.model_dump(exclude_none=True)


def friction_entry(detail: str, *, keys, element: str, area: str = "ontology") -> dict:
    return {"kind": "structure-friction", "detail": detail, "keys": list(keys),
            "area": area, "element": element}
