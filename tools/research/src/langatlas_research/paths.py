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
    "consolidations": "R6 consolidation records (`<cycle>-<theme>.yaml`): whether the cross-theme\n"
                      "edge pass ran (its edges live in the cycle's carve plan, marked\n"
                      "`pass: r6`), the developer's rulings on dedup/alias candidates, and the\n"
                      "migrations this consolidation landed. Written by `langatlas-research\n"
                      "consolidate` (Stage 3F); read by later cycles' dedup audits (a `distinct`\n"
                      "ruling is never re-raised) and by `coverage report.py dossier`.\n",
    "cycles": "One file per theme cycle (`<NN>-<theme>.yaml`): the developer's sign-off, the\n"
              "cycle's rotating R5 language sample, its status, and the node ids it minted.\n"
              "Written by `langatlas-research cycle`; read by every R3-R6 runner and by\n"
              "`coverage report.py dossier`.\n",
    "surveys": "R3 candidate inventories (`<cycle>-<theme>.yaml`), one entry per candidate with\n"
               "1-3 evidence chunk ids and cross-book aliases. Written by the surveyor (Stage 3B);\n"
               "read by the ontologist (Stage 3C). Candidates are leads, never facts.\n",
    "drafts": "R4 carve plans (`<cycle>-<theme>.yaml`): the nodes, edges and quality edges one\n"
              "cycle proposes, with their evidence, contested triggers, debate ids, verification\n"
              "verdicts and mint status. Written by the ontologist and edge drafter (Stage 3C);\n"
              "read by every later R4 step and by `coverage report.py dossier` (Stage 3F).\n"
              "A carve plan is a proposal — only `status: minted` entries exist in the store.\n",
    "debates": "R4 debate records (`<debate-id>.yaml`): proposer, two challengers, moderator\n"
               "resolution, typed challenges. Written by the debate machinery (Stage 3C); read by\n"
               "the controversy assessor (Stage 3D) and the D30 instrumentation scripts.\n"
               "`draft debate` writes a record but does not commit it: the records are landed by\n"
               "`draft finalize`, together with the carve plan whose conclusions they are.\n",
    "reality-checks": "R5 reality checks (`<cycle>-<theme>.yaml`): the sampled languages' answers\n"
                      "to the theme's compiled questionnaire, the D24 gate's verdicts on them,\n"
                      "the structured findings (unmappable features, uninhabited dimension\n"
                      "values, unfittable languages, exclusivity violations) and the shakedown\n"
                      "issue log. Written by `langatlas-research reality` (Stage 3E); read by\n"
                      "`coverage report.py dossier` (Stage 3F). Nothing here is minted into the\n"
                      "store (D68), and Stage 5 sweep agents never read this directory — their\n"
                      "answers must stay independent (D5/D34).\n",
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


def consolidations_dir(repo_root: Path | None = None) -> Path:
    return research_root(repo_root) / "consolidations"


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


def drafts_dir(repo_root: Path | None = None) -> Path:
    return research_root(repo_root) / "drafts"


def private_research_dir() -> Path:
    """The private, non-git tier (§2.2) for derived R3 volume state: frozen pools and the
    tag store. Read through the module attribute so tests can monkeypatch `PRIVATE_DIR`."""
    from langatlas_pipeline import paths as pipeline_paths

    return pipeline_paths.PRIVATE_DIR / "research"


def private_controversy_dir() -> Path:
    """The private, non-git tier for the assessment ledger (§2.2). Same reasoning as
    `VerdictLedger`: a level is a measurement about the corpus made by whichever model ran
    last night, and putting its bookkeeping in git would make the canonical store depend on
    that. Read through the module attribute so tests can monkeypatch `PRIVATE_DIR`."""
    from langatlas_pipeline import paths as pipeline_paths

    return pipeline_paths.PRIVATE_DIR / "research" / "controversy"


def structure_review_path(repo_root: Path | None = None) -> Path:
    return research_root(repo_root) / "structure-review.yaml"
