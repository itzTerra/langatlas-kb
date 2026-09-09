"""D53's `checklist` mode: the durable artifact R3's thematic surveys consume.

A per-call tool result vanishes into an agent's context window; a survey needs something a
later drafting run can read and a developer can tick through (D53 §O1a's rejection of a
tool-only shape). Each row is one question — "PLDB/Wikidata know about <term> for
<language>; does our store?" — and an empty `covered_by` is the finding.

Not committed (plan decision 4): every row is re-derivable from the mirror versions the
header pins, and committing a derived survey artifact would put a second, staler answer
next to the store's own."""
import json
from dataclasses import dataclass
from pathlib import Path

from langatlas_validate.paths import REPO_ROOT
from langatlas_validate.store import iter_store_records

from langatlas_finding_aids.config import FindingAidsConfig
from langatlas_finding_aids.mirror import mirror_state
from langatlas_finding_aids.paths import CHECKLIST_DIR
from langatlas_finding_aids.query import search_finding_aids
from langatlas_finding_aids.results import utc_now

_MAX_LEADS_PER_ROW = 3


@dataclass(frozen=True)
class ChecklistRow:
    term: str
    language: str
    aids: tuple[str, ...]
    leads: tuple[dict, ...]
    covered_by: tuple[str, ...]


@dataclass(frozen=True)
class Checklist:
    theme: str
    label: str
    generated_at: str
    mirror_versions: dict
    rows: tuple[ChecklistRow, ...]

    def to_dict(self) -> dict:
        return {"theme": self.theme, "label": self.label,
                "generated_at": self.generated_at,
                "mirror_versions": self.mirror_versions,
                "rows": [{"term": r.term, "language": r.language, "aids": list(r.aids),
                          "leads": list(r.leads), "covered_by": list(r.covered_by)}
                         for r in self.rows]}

    def to_markdown(self) -> str:
        versions = ", ".join(f"{name}@{version}" for name, version
                             in sorted(self.mirror_versions.items())) or "none"
        lines = [
            f"# Finding-aid coverage checklist — {self.label}",
            "",
            f"Generated {self.generated_at} from mirrors: {versions}.",
            "",
            "**Leads, never citations.** Every row is a question for a survey agent to "
            "answer from real sources; nothing in the `leads` column may be cited "
            "(D29/D3).",
            "",
            "| term | language | store coverage | leads |",
            "|---|---|---|---|",
        ]
        for row in self.rows:
            coverage = ", ".join(row.covered_by) if row.covered_by else "**GAP**"
            leads = "; ".join(f"{lead['source']}:{lead['label']}"
                              for lead in row.leads) or "—"
            lines.append(f"| {row.term} | {row.language} | {coverage} | {leads} |")
        return "\n".join(lines) + "\n"


def store_coverage(repo_root: Path | None = None) -> dict[str, set[str]]:
    """Lowercased feature name/alias -> the feature ids that claim it.

    Reads the committed store, not Postgres: coverage is a statement about the canonical
    record (D1), and at Stage 2 the store is legitimately near-empty — every row coming
    back a GAP is the correct answer, not a bug."""
    coverage: dict[str, set[str]] = {}
    for _, kind, _, data in iter_store_records(Path(repo_root or REPO_ROOT)):
        if kind != "feature":
            continue
        feature_id = data.get("id", "")
        for label in [data.get("name", "")] + list(data.get("aliases") or []):
            if label:
                coverage.setdefault(str(label).strip().lower(), set()).add(feature_id)
    return coverage


def build_checklist(ctx, theme_slug: str, *, config: FindingAidsConfig | None = None,
                    repo_root: Path | None = None, root: Path | None = None,
                    channel=None) -> Checklist:
    config = config or FindingAidsConfig.load()
    theme = config.theme(theme_slug)          # raises before any query on a bad slug
    coverage = store_coverage(repo_root)
    versions = {source: state.version for source in ("pldb", "hyperpolyglot")
                for state in [mirror_state(source, root=root)] if state}
    rows: list[ChecklistRow] = []
    for term in theme["terms"]:
        covered = tuple(sorted(coverage.get(term.strip().lower(), ())))
        for language in theme["languages"]:
            results = search_finding_aids(ctx, f"{language} {term}", config=config,
                                          root=root, channel=channel,
                                          limit=_MAX_LEADS_PER_ROW)
            for result in results:
                if result.mirror_version:
                    versions.setdefault(result.source, result.mirror_version)
            rows.append(ChecklistRow(
                term=term, language=language,
                aids=tuple(sorted({r.source for r in results})),
                leads=tuple({"source": r.source, "label": r.label, "url": r.url}
                            for r in results[:_MAX_LEADS_PER_ROW]),
                covered_by=covered))
    return Checklist(theme=theme_slug, label=theme["label"], generated_at=utc_now(),
                     mirror_versions=versions, rows=tuple(rows))


def write_checklist(checklist: Checklist, *,
                    out_dir: Path | None = None) -> tuple[Path, Path]:
    directory = Path(out_dir or CHECKLIST_DIR)
    directory.mkdir(parents=True, exist_ok=True)
    stem = f"checklist-{checklist.theme}-{checklist.generated_at[:10]}"
    md, js = directory / f"{stem}.md", directory / f"{stem}.json"
    md.write_text(checklist.to_markdown())
    js.write_text(json.dumps(checklist.to_dict(), indent=2, sort_keys=True))
    return md, js
