from pathlib import Path

from langatlas_validate.cli import cmd_ci_with_index
from langatlas_validate.normalize import normalize_record


class _FakeIndex:
    """Implements the SourceChunksIndex protocol without touching Postgres."""
    def __init__(self, resolvable: set[tuple[str, str]]):
        self._resolvable = resolvable

    def resolve(self, source_id: str, locator: str) -> list[str]:
        return ["chunk-1"] if (source_id, locator) in self._resolvable else []


def _write_instance_with_locator(root: Path, locator: str) -> None:
    raw = (
        "feature: pattern-matching\nlanguage: rust\nstatus: present\n"
        "since:\n  value: \"1.0\"\n  sources:\n    - source: rust-reference\n      locator: p. 1\n"
        "characteristics:\n"
        "  - key: c-a\n    text: some characteristic\n"
        "    sources:\n"
        f"      - source: nystrom-2021\n        locator: \"{locator}\"\n"
        "provenance:\n  claim_origin: source-derived\n"
    )
    path = root / "languages" / "rust" / "instances" / "pattern-matching.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(normalize_record(raw, "feature-instance"))

    (root / "features").mkdir(parents=True, exist_ok=True)
    (root / "features" / "pattern-matching.yaml").write_text(
        normalize_record(
            "id: pattern-matching\nslug: pattern-matching\nname: Pattern Matching\n"
            "layer: 2\nsummary:\n  text: X.\n  sources:\n    - source: s\n      locator: p. 1\n"
            "provenance:\n  claim_origin: source-derived\n", "feature"))
    (root / "languages" / "_registry.yaml").write_text("languages:\n  rust:\n    name: Rust\n")


def test_ci_with_index_passes_when_locator_resolves(tmp_path):
    _write_instance_with_locator(tmp_path, "p. 42")
    index = _FakeIndex(resolvable={("nystrom-2021", "p. 42")})
    rc, errors = cmd_ci_with_index(tmp_path, index)
    assert rc == 0
    assert errors == []


def test_ci_with_index_does_not_fail_on_unresolved_locator(tmp_path):
    # D37/1C: an unresolved-but-well-shaped locator parks in the sourcing queue and
    # renders the citing claim flagged — it must NOT redden CI (that would punish the
    # store for a source the corpus doesn't contain yet).
    _write_instance_with_locator(tmp_path, "p. 42")
    index = _FakeIndex(resolvable=set())
    rc, errors = cmd_ci_with_index(tmp_path, index)
    assert rc == 0


def test_ci_with_index_still_fails_on_malformed_locator_shape(tmp_path):
    _write_instance_with_locator(tmp_path, "not a real locator shape")
    index = _FakeIndex(resolvable=set())
    rc, errors = cmd_ci_with_index(tmp_path, index)
    assert rc == 1
    assert any("locator" in e for e in errors)
