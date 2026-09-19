"""Small stores for the coverage tests. Records are normalized but not store-validated: the
metrics read whatever the store holds."""
from pathlib import Path

import pytest

from langatlas_research.cycle import Cycle
from langatlas_validate.ids import compose_edge_id
from langatlas_validate.normalize import normalize_record

_CITE = "  sources:\n    - source: s\n      locator: p. 1\n"
_PROVENANCE = "provenance:\n  claim_origin: source-derived\n"


class CoverageStore:
    def __init__(self, root: Path):
        self.root = root

    def write(self, rel: str, text: str) -> None:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def feature(self, node_id, *, layer=2, dimension=None, realizes=()):
        body = f"id: {node_id}\nslug: {node_id}\nname: {node_id.title()}\nlayer: {layer}\n"
        if dimension:
            body += f"dimension: {dimension}\n"
        if realizes:
            body += "realizes:\n" + "".join(f"  - {c}\n" for c in realizes)
        body += f"summary:\n  text: {node_id} is a feature.\n" + _CITE + _PROVENANCE
        self.write(f"features/{node_id}.yaml", normalize_record(body, "feature"))

    def concept(self, node_id):
        self.write(f"concepts/{node_id}.yaml", normalize_record(
            f"id: {node_id}\nslug: {node_id}\nname: {node_id.title()}\n"
            f"summary:\n  text: {node_id} is a concept.\n" + _CITE + _PROVENANCE, "concept"))

    def edge(self, edge_type, frm, to):
        self.write(f"edges/{frm}/{edge_type}--{to}.yaml", normalize_record(
            f"id: {compose_edge_id(edge_type, frm, to)}\ntype: {edge_type}\nfrom: {frm}\n"
            f"to: {to}\nstatement:\n  text: {frm} {edge_type} {to}.\n" + _CITE + _PROVENANCE,
            "edge"))

    def instance(self, language, feature, status="present"):
        if status == "absent":
            body = (f"feature: {feature}\nlanguage: {language}\nstatus: absent\n"
                    "absence_scope: the whole reference.\n"
                    "sources:\n  - source: s\n    locator: p. 1\n" + _PROVENANCE)
        else:
            body = (f"feature: {feature}\nlanguage: {language}\nstatus: {status}\n"
                    "since:\n  value: '1.0'\n" + _CITE + _PROVENANCE)
        self.write(f"languages/{language}/instances/{feature}.yaml",
                   normalize_record(body, "feature-instance"))


@pytest.fixture
def coverage_store(tmp_path) -> CoverageStore:
    store = CoverageStore(tmp_path / "store")
    store.write("ontology/taxonomy/dimensions.yaml",
                "dimensions:\n  - slug: typing-discipline\n    label: Typing discipline\n"
                "    exclusivity: exclusive\n    applies_to: [general-purpose]\n"
                "  - slug: evaluation-strategy\n    label: Evaluation strategy\n"
                "    exclusivity: exclusive\n    applies_to: [general-purpose]\n")
    store.write("languages/_registry.yaml",
                "languages:\n  python:\n    name: Python\n  haskell:\n    name: Haskell\n")
    return store


@pytest.fixture
def make_cycle():
    def build(number, theme, status="r5-done", nodes=()):
        return Cycle(number=number, theme=theme, theme_digest="a" * 16, status=status,
                     languages=("python",), nodes_minted=tuple(nodes), artifacts={},
                     signed_off={"by": "Dev", "date": "2026-10-01", "theme_digest": "a" * 16})
    return build


@pytest.fixture
def make_inputs():
    """A `DossierInputs` with empty defaults; tests override only what they measure."""
    from langatlas_coverage.dossier import DossierInputs
    from langatlas_coverage.metrics import Store

    empty = Store(features={}, concepts={}, edges={}, quality_edges={}, rules={}, instances={},
                  dimensions={}, facts=())

    def build(**overrides):
        base = {"store": empty, "cycles": (), "plans": {}, "reality": {}, "manifests": (),
                "membership": {}, "verification": None, "calibration": None,
                "retrieval_verdict": False, "compile_errors": (), "compile_failure": "",
                "compile_diagnostics": 0, "claude_by_cycle": {}}
        return DossierInputs(**{**base, **overrides})
    return build
