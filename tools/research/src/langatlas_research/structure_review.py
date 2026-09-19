"""D70's structure review: the one developer act that opens minting.

The gate is a file, not a flag on a cycle, because the decision is about the *ontology*: the
structure the first cycles' carves were drafted against is either confirmed or revised, once, for
the whole batch. Until `research/structure-review.yaml` exists no cycle mints, and `draft
finalize` lands the carve plan and moves the cycle to `r4-drafted` instead. Later cycles find the
file already there and mint per cycle as the runbook always described."""
import io
from dataclasses import dataclass
from pathlib import Path

from ruamel.yaml import YAML

from langatlas_research.cycle import load_cycle
from langatlas_research.errors import MintHeld, StructureReviewRefused
from langatlas_research.paths import cycles_dir, drafts_dir, structure_review_path
from langatlas_research.schema import validate_research_record

_read = YAML(typ="safe")


def mint_open(repo_root: Path | None = None) -> bool:
    return structure_review_path(repo_root).exists()


def require_mint_open(repo_root: Path | None = None) -> None:
    """@raises MintHeld: no structure review is recorded yet."""
    if not mint_open(repo_root):
        raise MintHeld(
            "minting is held until the structure review (D70): finish the draft-only batch,"
            " read `langatlas-research structure report`, decide the schema changes, then run"
            " `langatlas-research structure release`")


def drafted_cycles(repo_root: Path | None = None) -> list[int]:
    numbers = (int(path.name[:2]) for path in cycles_dir(repo_root).glob("[0-9][0-9]-*.yaml"))
    return sorted(n for n in numbers
                  if load_cycle(n, repo_root=repo_root).status == "r4-drafted")


def release_structure_review(*, by: str, date: str, summary: str,
                             repo_root: Path | None = None) -> Path:
    """Records the review and opens the gate. The batch is every cycle at `r4-drafted`: they are
    the carve plans the review looked at, and the ones to re-atomize.

    @raises StructureReviewRefused: a review is already recorded, no cycle is at r4-drafted,
        or `by` / `date` / `summary` is blank."""
    path = structure_review_path(repo_root)
    if path.exists():
        raise StructureReviewRefused(f"a structure review is already recorded ({path.name})")
    if not (by.strip() and date.strip() and summary.strip()):
        raise StructureReviewRefused("a review needs who, when, and a summary of the decisions")
    batch = drafted_cycles(repo_root)
    if not batch:
        raise StructureReviewRefused("no cycle is at r4-drafted: there is no draft-only batch"
                                     " to review")
    data = {"reviewed_by": by.strip(), "date": date.strip(), "summary": summary.strip(),
            "batch": batch}
    errors = validate_research_record(data, "structure-review", repo_root=repo_root)
    if errors:
        raise StructureReviewRefused("; ".join(errors))
    yaml = YAML()
    yaml.width = 100
    buf = io.StringIO()
    yaml.dump(data, buf)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(buf.getvalue())
    return path


@dataclass(frozen=True)
class FrictionRow:
    cycle: int
    theme: str
    area: str
    element: str
    detail: str
    keys: tuple[str, ...]


def collect_friction(repo_root: Path | None = None) -> list[FrictionRow]:
    """Every `structure-friction` finding in every carve plan — the structure review's agenda.
    Read it *before* re-atomizing: a re-atomized plan replaces its findings (git keeps the old
    plan)."""
    rows = []
    for path in sorted(drafts_dir(repo_root).glob("*.yaml")):
        plan = _read.load(path.read_text()) or {}
        for finding in plan.get("findings") or []:
            if finding.get("kind") == "structure-friction":
                rows.append(FrictionRow(plan["cycle"], plan["theme"], finding["area"],
                                        finding["element"], finding["detail"],
                                        tuple(finding.get("keys") or ())))
    return sorted(rows, key=lambda row: (row.cycle, row.area != "ontology", row.element))


def render_report(rows: list[FrictionRow]) -> str:
    """Grouped by area (`ontology` first), then element. How widespread a misfit is — the
    number of distinct themes it appears in — is the first thing a review wants to know."""
    if not rows:
        return "no structure-friction findings"
    lines: list[str] = []
    for area in ("ontology", "adjacent"):
        in_area = [row for row in rows if row.area == area]
        if not in_area:
            continue
        lines.append(f"== {area} ==")
        for element in sorted({row.element for row in in_area}):
            group = [row for row in in_area if row.element == element]
            themes = len({row.theme for row in group})
            lines.append(f"{element}: {len(group)} finding(s) across {themes} theme(s)")
            for row in group:
                lines.append(f"  [{row.cycle:02d} {row.theme}] {', '.join(row.keys)}:"
                             f" {row.detail}")
        lines.append("")
    return "\n".join(lines).rstrip()
