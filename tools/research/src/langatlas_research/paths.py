"""Where the research phase's bookkeeping lives.

`research/` is *committed bookkeeping, not canonical store*: `iter_store_records`
deliberately does not walk it, and these artifacts validate against their own schemas under
`research/schema/` rather than against `ontology/schema/`'s closed `RECORD_KINDS`. Keeping
the two vocabularies separate is what stops a survey candidate — which is a lead, not a
fact — from ever looking like a mintable record."""
import os
from pathlib import Path

# src layout: .../tools/research/src/langatlas_research/paths.py -> parents[4] == repo root.
REPO_ROOT = Path(os.environ.get("LANGATLAS_ROOT", Path(__file__).resolve().parents[4]))

_READMES = {
    "cycles": "One file per theme cycle (`<NN>-<theme>.yaml`): the developer's sign-off, the\n"
              "cycle's rotating R5 language sample, its status, and the node ids it minted.\n"
              "Written by `langatlas-research cycle`; read by every R3-R6 runner and by\n"
              "`coverage report.py dossier`.\n",
    "surveys": "R3 candidate inventories (`<cycle>-<theme>.yaml`), one entry per candidate with\n"
               "1-3 evidence chunk ids and cross-book aliases. Written by the surveyor (Stage 3B);\n"
               "read by the ontologist (Stage 3C). Candidates are leads, never facts.\n",
    "debates": "R4 debate records (`<debate-id>.yaml`): proposer, two challengers, moderator\n"
               "resolution, typed challenges. Written by the debate machinery (Stage 3C); read by\n"
               "the controversy assessor (Stage 3D) and the D30 instrumentation scripts.\n",
    "reality-checks": "R5 structured findings (`<cycle>-<theme>.yaml`): unmappable features,\n"
                      "uninhabited dimension values, unfittable languages, exclusivity violations.\n"
                      "Written by the reality-check runner (Stage 3E); read by\n"
                      "`coverage report.py dossier` (Stage 3F) as the one dossier item that is not\n"
                      "pure computation.\n",
}


def _root(repo_root: Path | None) -> Path:
    return REPO_ROOT if repo_root is None else Path(repo_root)


def research_root(repo_root: Path | None = None) -> Path:
    return _root(repo_root) / "research"


def themes_path(repo_root: Path | None = None) -> Path:
    return research_root(repo_root) / "themes.yaml"


def cycles_dir(repo_root: Path | None = None) -> Path:
    return research_root(repo_root) / "cycles"


def surveys_dir(repo_root: Path | None = None) -> Path:
    return research_root(repo_root) / "surveys"


def debates_dir(repo_root: Path | None = None) -> Path:
    return research_root(repo_root) / "debates"


def reality_checks_dir(repo_root: Path | None = None) -> Path:
    return research_root(repo_root) / "reality-checks"


def research_schema_dir(repo_root: Path | None = None) -> Path:
    return research_root(repo_root) / "schema"


def ensure_layout(repo_root: Path | None = None) -> list[Path]:
    """Creates the `research/` tree if it is missing. Idempotent, and never rewrites an
    existing README — the directory READMEs are documentation the developer may edit.

    @param repo_root: repository root; defaults to this checkout.
    @returns: the paths this call created, empty when there was nothing to do."""
    created: list[Path] = []
    research_schema_dir(repo_root).mkdir(parents=True, exist_ok=True)
    for name, body in _READMES.items():
        directory = research_root(repo_root) / name
        if not directory.exists():
            directory.mkdir(parents=True)
            created.append(directory)
        readme = directory / "README.md"
        if not readme.exists():
            readme.write_text(body)
            created.append(readme)
    return created


def research_config_path(repo_root: Path | None = None) -> Path:
    return _root(repo_root) / "config" / "research.yaml"


def private_research_dir() -> Path:
    """The private, non-git tier (§2.2) for derived R3 volume state: frozen pools and the
    tag store. Read through the module attribute so tests can monkeypatch `PRIVATE_DIR`."""
    from langatlas_pipeline import paths as pipeline_paths

    return pipeline_paths.PRIVATE_DIR / "research"
