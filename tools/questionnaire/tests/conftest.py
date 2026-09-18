"""A throwaway canonical store the compiler can read. Every record goes through
`normalize_record`, because `compile_spec` refuses a store `validate_store` rejects — and an
unnormalized record is one."""
import io
from pathlib import Path

import pytest
from ruamel.yaml import YAML

from langatlas_validate.normalize import normalize_record

SOURCES = [{"source": "pierce-tapl-2002", "locator": "§1.1"}]
PROVENANCE = {"claim_origin": "source-derived"}


def dump(data: dict) -> str:
    yaml = YAML()
    yaml.indent(mapping=2, sequence=4, offset=2)
    yaml.width = 100
    buf = io.StringIO()
    yaml.dump(data, buf)
    return buf.getvalue()


class MiniStore:
    def __init__(self, root: Path):
        self.root = root
        self._dimensions: list[dict] = []

    def write(self, rel: str, data: dict, kind: str) -> Path:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(normalize_record(dump(data), kind))
        return path

    def version(self, value: str) -> None:
        (self.root / "ontology" / "VERSION").write_text(f"{value}\n")

    def dimension(self, slug, *, exclusivity="exclusive", applies_to=("general-purpose",),
                  label=None) -> None:
        """Adds or replaces one dimension, slug-sorted like `mint_dimension` (D67: no values)."""
        self._dimensions = [d for d in self._dimensions if d["slug"] != slug]
        self._dimensions.append({"slug": slug, "label": label or slug.replace("-", " "),
                                 "exclusivity": exclusivity, "applies_to": list(applies_to)})
        self._dimensions.sort(key=lambda d: d["slug"])
        (self.root / "ontology" / "taxonomy" / "dimensions.yaml").write_text(
            dump({"dimensions": self._dimensions}))

    def feature(self, fid, *, layer=2, dimension=None, aliases=(), summary=None) -> None:
        data = {"id": fid, "slug": fid, "name": fid.replace("-", " ").capitalize(),
                "layer": layer,
                "summary": {"text": summary or f"{fid} summary.", "sources": list(SOURCES)},
                "provenance": dict(PROVENANCE)}
        if dimension:
            data["dimension"] = dimension
        if aliases:
            data["aliases"] = list(aliases)
        self.write(f"features/{fid}.yaml", data, "feature")

    def drop_feature(self, fid) -> None:
        (self.root / "features" / f"{fid}.yaml").unlink()

    def edge(self, edge_type, frm, to) -> None:
        data = {"id": f"edge.{edge_type}.{frm}.{to}", "type": edge_type, "from": frm, "to": to,
                "statement": {"text": f"{frm} {edge_type} {to}.", "sources": list(SOURCES)},
                "provenance": dict(PROVENANCE)}
        if edge_type == "influences":
            data["polarity"] = "+"
        self.write(f"edges/{frm}/{edge_type}--{to}.yaml", data, "edge")

    def rule(self, slug, when_all, effect, then) -> None:
        data = {"id": f"rule-{slug}", "when_all": sorted(when_all), "effect": effect,
                "then": list(then), "message": f"{slug} message.", "sources": list(SOURCES),
                "provenance": dict(PROVENANCE)}
        self.write(f"rules/rule-{slug}.yaml", data, "rule")


@pytest.fixture
def mini_store(tmp_path):
    root = tmp_path / "store"
    for directory in ("concepts", "features", "edges", "rules", "languages", "sources",
                      "ontology/taxonomy"):
        (root / directory).mkdir(parents=True)
    store = MiniStore(root)
    store.version("0.4.0")
    (root / "ontology" / "taxonomy" / "dimensions.yaml").write_text("dimensions: []\n")
    return store


def typing_store(store: MiniStore) -> MiniStore:
    """The shape every compiler test starts from: one exclusive dimension with two member
    features, one layer-2 and one layer-1 feature outside any dimension."""
    store.dimension("type-checking-discipline", label="Type checking discipline")
    store.feature("static-typing", layer=3, dimension="type-checking-discipline")
    store.feature("dynamic-typing", layer=3, dimension="type-checking-discipline",
                  aliases=["dynamic type checking"])
    store.feature("type-inference", layer=2)
    store.feature("type-annotation", layer=1)
    return store
