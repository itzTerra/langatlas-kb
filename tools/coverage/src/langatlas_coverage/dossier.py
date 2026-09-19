"""The R6 exit dossier (§7.4, D27/D52): five advisory items the developer reads before
declaring `1.0.0`. Each item is a pure function of one `DossierInputs` snapshot, so the
arithmetic is testable without a repository; `gather` (Task 16) builds the snapshot from disk.

Every bar is advisory. `met` / `not-met` report a bar, `no-data` says there is nothing yet to
measure, and `info` marks an item the spec gives no bar (graph health)."""
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from langatlas_coverage.metrics import (
    StoreReadError, fact_verification, feature_degrees, load_store,
)
from langatlas_research.draft.gate import GATED_LISTS
from langatlas_research.draft.plan import entries
from langatlas_validate.migrate import disposition_nodes, iter_manifests

ITEM_STATUSES = ("met", "not-met", "no-data", "info")
UNMAPPABLE_BAR_PERCENT = 5.0
# Long id lists are cut here: the dossier is read, not grepped.
_LIST_MAX = 20
_ADVISORY = ("All bars are advisory (D27): the `1.0.0` declaration is the developer's"
             " judgment, and no item here gates anything.")


@dataclass(frozen=True)
class DossierItem:
    key: str
    title: str
    status: str
    bar: str
    lines: tuple[str, ...]


@dataclass(frozen=True)
class DossierInputs:
    """@param verification: fact id -> §6.2 fold, or None when there is no verdict ledger.
    @param compile_errors: `validate_spec` errors, or None when the compiler itself raised
        (`compile_failure` then says how).
    @param claude_by_cycle: cycle slug -> (Claude sessions, Claude messages)."""
    store: object
    cycles: tuple
    plans: dict
    reality: dict
    manifests: tuple
    membership: dict
    verification: dict | None
    calibration: dict | None
    retrieval_verdict: bool
    compile_errors: tuple | None
    compile_failure: str
    compile_diagnostics: int
    claude_by_cycle: dict


def _pct(part: int, whole: int) -> str:
    return f"{100 * part / whole:.1f}%" if whole else "—"


def _listed(ids) -> str:
    ids = list(ids)
    more = f" … (+{len(ids) - _LIST_MAX})" if len(ids) > _LIST_MAX else ""
    return ", ".join(ids[:_LIST_MAX]) + more


def _gated_entries(plan) -> list[dict]:
    """The gated plan entries carrying a verification block; a malformed plan yields none."""
    if not isinstance(plan, dict):
        return []
    try:
        return [entry for name, entry in entries(plan)
                if name in GATED_LISTS and isinstance(entry, dict)
                and isinstance(entry.get("verification"), dict)]
    except (AttributeError, TypeError):
        return []


def _count(value) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def _reality_summary(record) -> dict:
    summary = record.get("summary") if isinstance(record, dict) else None
    return summary if isinstance(summary, dict) else {}


def _reality_reading(record):
    """@returns: `(cells, unmappable, violations, uninhabited, unfittable)`, or None when the
    record does not have the shape R5 writes."""
    if not isinstance(record, dict):
        return None
    summary = _reality_summary(record)
    findings = record.get("findings")
    if not isinstance(findings, dict):
        return None
    cells, unmappable = _count(summary.get("cells")), _count(summary.get("unmappable"))
    lists = [findings.get(name) for name in
             ("exclusivity_violations", "uninhabited_values", "unfittable")]
    if cells is None or unmappable is None or unmappable > cells \
            or not all(isinstance(found, list) for found in lists):
        return None
    return (cells, unmappable, *lists)


def _violation_line(cycle, violation) -> str:
    if not isinstance(violation, dict):
        return f"  {cycle.slug}: malformed exclusivity violation {violation!r}"
    members = violation.get("members")
    members = ", ".join(str(member) for member in members) if isinstance(members, list) else "?"
    return (f"  {cycle.slug}: {violation.get('language', '?')} holds {members}"
            f" on exclusive {violation.get('dimension', '?')}")


def sourcing_integrity(inputs: DossierInputs) -> DossierItem:
    title, bar = ("Sourcing integrity",
                  "100% of nodes with ≥1 verified tier-A/B existence/definition fact")
    store = inputs.store
    nodes = sorted(store.nodes)
    if inputs.verification is None:
        return DossierItem("sourcing-integrity", title, "no-data", bar,
                           ("No verdict ledger — run `draft verify` or the nightly"
                            " verification batch.",))
    if not nodes:
        return DossierItem("sourcing-integrity", title, "no-data", bar,
                           ("The store holds no concepts or features yet.",))
    fact_of = {fact["anchor"]: fact["fact_id"] for fact in store.facts}
    missing = [node for node in nodes
               if inputs.verification.get(fact_of.get(f"{node}#summary")) != "verified"]
    lines = [f"Nodes verified: {len(nodes) - len(missing)}/{len(nodes)}"
             f" ({_pct(len(nodes) - len(missing), len(nodes))})"]
    if missing:
        lines.append(f"Not yet verified: {_listed(missing)}")
    for label, kind in (("Edges", "edge-exists("), ("Quality assessments", "quality-assessment("),
                        ("Rules", "rule-exists(")):
        facts = [fact for fact in store.facts if fact["claim"].startswith(kind)]
        verified = sum(1 for fact in facts if inputs.verification.get(fact["fact_id"]) == "verified")
        lines.append(f"{label} verified: {verified}/{len(facts)} ({_pct(verified, len(facts))})")
    lines.append("Gate pass rate per cycle:")
    for cycle in sorted(inputs.cycles, key=lambda cycle: cycle.number):
        gated = _gated_entries(inputs.plans.get(cycle.slug))
        admitted = sum(1 for entry in gated if entry["verification"].get("admissible") is True)
        summary = _reality_summary(inputs.reality.get(cycle.slug))
        r5_admitted, r5_refused, r5_unsourced = (_count(summary.get(name)) or 0 for name in
                                                 ("admitted", "refused", "unsourced"))
        r5_tried = r5_admitted + r5_refused + r5_unsourced
        lines.append(f"  {cycle.slug}: R4/R6 gate {admitted}/{len(gated)}"
                     f" ({_pct(admitted, len(gated))}); R5 {r5_admitted}/{r5_tried}"
                     f" ({_pct(r5_admitted, r5_tried)})")
    return DossierItem("sourcing-integrity", title, "not-met" if missing else "met", bar,
                       tuple(lines))


def reality_checks(inputs: DossierInputs) -> DossierItem:
    title = "Reality-check results"
    bar = (f"<{UNMAPPABLE_BAR_PERCENT:g}% unmappable in the final cycle; zero exclusivity"
           f" violations")
    cycles = sorted(inputs.cycles, key=lambda cycle: cycle.number)
    rows = [(cycle, inputs.reality[cycle.slug]) for cycle in cycles
            if cycle.slug in inputs.reality]
    if not rows:
        return DossierItem("reality-checks", title, "no-data", bar,
                           ("No reality checks yet — R5 writes research/reality-checks/.",))
    lines = []
    readings = {}
    for cycle, record in rows:
        reading = _reality_reading(record)
        if reading is None:
            lines.append(f"{cycle.slug}: reality-check record is malformed or unreadable")
            continue
        readings[cycle.slug] = reading
        cells, unmappable, violations, uninhabited, unfittable = reading
        lines.append(f"{cycle.slug}: {unmappable}/{cells} unmappable"
                     f" ({_pct(unmappable, cells)}), {len(violations)} exclusivity"
                     f" violation(s), {len(uninhabited)} uninhabited value(s),"
                     f" {len(unfittable)} unfittable language/dimension pair(s)")
    final_cycle = cycles[-1]
    reading = readings.get(final_cycle.slug)
    if reading is None:
        lines.append(f"The final cycle {final_cycle.slug} has no usable reality check.")
        return DossierItem("reality-checks", title, "no-data", bar, tuple(lines))
    cells, unmappable, violations = reading[:3]
    lines += [_violation_line(final_cycle, violation) for violation in violations]
    if not cells:
        return DossierItem("reality-checks", title, "no-data", bar, tuple(lines))
    met = 100 * unmappable / cells < UNMAPPABLE_BAR_PERCENT and not violations
    return DossierItem("reality-checks", title, "met" if met else "not-met", bar, tuple(lines))


_DEGREE_BUCKETS = ((0, 0, "0"), (1, 1, "1"), (2, 3, "2–3"), (4, 7, "4–7"), (8, None, "8+"))


def _debated_minted(plans: dict) -> set:
    found = set()
    for plan in plans.values():
        if not isinstance(plan, dict):
            continue
        try:
            found |= {entry["id"] for name, entry in entries(plan)
                      if name == "nodes" and isinstance(entry, dict) and entry.get("debate_id")
                      and entry.get("status") == "minted"}
        except (AttributeError, TypeError, KeyError):
            continue
    return found


def _migrated_nodes(manifests) -> set:
    migrated = set()
    for manifest in manifests:
        for disposition in manifest.get("dispositions") or []:
            try:
                migrated |= set(disposition_nodes(disposition))
            except (AttributeError, TypeError, KeyError):
                continue
    return migrated


def churn(inputs: DossierInputs) -> DossierItem:
    title, bar = "Churn trend", "settled-theme restructures ≈ 0 across the last two cycles"
    numbers = sorted(cycle.number for cycle in inputs.cycles)
    touching = [manifest for manifest in inputs.manifests if manifest.get("settled_themes")]
    by_cycle = Counter(manifest.get("cycle") for manifest in touching)
    lines = [f"Migrations: {len(inputs.manifests)} total, {len(touching)} touching a settled"
             f" theme"]
    lines += [f"  cycle {number:02d}: {by_cycle.get(number, 0)} settled-theme restructure(s)"
              for number in numbers]
    later = sorted(_debated_minted(inputs.plans) & _migrated_nodes(inputs.manifests))
    lines.append(f"Debated R4 carves later migrated (D30): {_listed(later) or 'none'}")
    if len(numbers) < 2:
        return DossierItem("churn", title, "no-data", bar,
                           (*lines, "Fewer than two cycles — no trend yet."))
    recent = sum(by_cycle.get(number, 0) for number in numbers[-2:])
    return DossierItem("churn", title, "met" if recent == 0 else "not-met", bar, tuple(lines))


def graph_health(inputs: DossierInputs) -> DossierItem:
    store, membership = inputs.store, inputs.membership
    degree = feature_degrees(store)
    quality = Counter(edge["from"] for edge in store.quality_edges.values())
    in_rules = {feature for rule in store.rules.values()
                for feature in [*(rule.get("when_all") or []), *(rule.get("then") or [])]}
    orphans = sorted(feature for feature in store.features
                     if not degree.get(feature) and not quality[feature]
                     and feature not in in_rules)
    realized = {concept for feature in store.features.values()
                for concept in feature.get("realizes") or []}
    unrealized = sorted(concept for concept in store.concepts if concept not in realized)
    lines = [f"Features: {len(store.features)}, concepts: {len(store.concepts)}, edges:"
             f" {len(store.edges)}, quality edges: {len(store.quality_edges)}, rules:"
             f" {len(store.rules)}",
             f"Orphan features (no edge, quality edge or rule): {len(orphans)}"
             + (f" — {_listed(orphans)}" if orphans else ""),
             f"Concepts no feature realizes: {len(unrealized)}"
             + (f" — {_listed(unrealized)}" if unrealized else "")]
    degrees = [degree.get(feature, 0) for feature in store.features]
    histogram = [f"{label}: {sum(1 for d in degrees if d >= low and (high is None or d <= high))}"
                 for low, high, label in _DEGREE_BUCKETS]
    lines.append("Feature-edge degree distribution: " + ", ".join(histogram))

    crossing = [edge for edge in store.edges.values()
                if membership.get(edge["from"]) and membership.get(edge["to"])
                and membership[edge["from"]] != membership[edge["to"]]]
    themes = sorted({membership[node] for node in store.nodes if node in membership})
    pairs = {tuple(sorted((membership[e["from"]], membership[e["to"]]))) for e in crossing}
    possible = len(themes) * (len(themes) - 1) // 2
    lines.append(f"Cross-theme edges: {len(crossing)}/{len(store.edges)}"
                 f" ({_pct(len(crossing), len(store.edges))}); theme pairs connected:"
                 f" {len(pairs)}/{possible}")
    crossed = {edge["from"] for edge in crossing} | {edge["to"] for edge in crossing}
    for theme in themes:
        own = [feature for feature in store.features if membership.get(feature) == theme]
        lines.append(f"  {theme}: {sum(1 for f in own if f in crossed)}/{len(own)} features"
                     f" with a cross-theme edge")
    unthemed = sorted(node for node in store.nodes if node not in membership)
    if unthemed:
        lines.append(f"Nodes no cycle minted: {len(unthemed)} — {_listed(unthemed)}")
    records = [*store.features.values(), *store.concepts.values(), *store.edges.values(),
               *store.quality_edges.values(), *store.rules.values()]
    levels = Counter(entry.get("level") for record in records
                     for entry in record.get("controversy") or [] if isinstance(entry, dict))
    lines.append("Controversy levels (an absent block is level 0): "
                 + ", ".join(f"level {level}: {levels.get(level, 0)}" for level in (1, 2, 3)))
    return DossierItem("graph-health", "Graph health", "info",
                       "none set by the spec — orphans, degree distribution, cross-theme edge"
                       " coverage", tuple(lines))


def pipeline_readiness(inputs: DossierInputs) -> DossierItem:
    title = "Pipeline readiness"
    bar = "eval green, R5 shakedown issues closed, compiler producing valid sweeps"
    calibration = inputs.calibration
    eval_green = isinstance(calibration, dict) and calibration.get("thresholds_met") is True
    if calibration is None:
        lines = ["Verifier calibration: missing (benchmarks/d24-verifier/calibration.json)"]
    elif not isinstance(calibration, dict):
        lines = ["Verifier calibration: malformed (expected a JSON object)"]
    else:
        lines = [f"Verifier calibration: thresholds {'met' if eval_green else 'NOT met'} —"
                 f" false accept {_rate(calibration.get('false_accept_rate'))}, false reject"
                 f" {_rate(calibration.get('false_reject_rate'))}"
                 f" ({calibration.get('generated', 'undated')})"]
    lines.append(f"Retrieval benchmark verdict (D22): "
                 f"{'committed' if inputs.retrieval_verdict else 'missing'}")
    open_entries = []
    for slug, record in sorted(inputs.reality.items()):
        shakedown = record.get("shakedown") if isinstance(record, dict) else None
        open_entries += [(slug, entry) for entry in shakedown or []
                         if isinstance(entry, dict) and entry.get("status") == "open"]
    lines.append(f"Open R5 shakedown entries: {len(open_entries)}")
    lines += [f"  {slug} {entry.get('key', '?')} ({entry.get('component', '?')}):"
              f" {entry.get('detail', '')}" for slug, entry in open_entries[:_LIST_MAX]]
    compiler_ok = inputs.compile_errors is not None and not inputs.compile_errors
    if inputs.compile_errors is None:
        lines.append(f"Questionnaire compiler: FAILED — {inputs.compile_failure}")
    else:
        lines.append(f"Questionnaire compiler: {len(inputs.compile_errors)} spec error(s),"
                     f" {inputs.compile_diagnostics} diagnostic(s)")
    if inputs.claude_by_cycle:
        lines.append("Claude usage per cycle (budget sanity, §7.4):")
        lines += [f"  {slug}: {sessions} session(s), {messages} message(s)"
                  for slug, (sessions, messages) in sorted(inputs.claude_by_cycle.items())]
    met = eval_green and not open_entries and compiler_ok
    return DossierItem("pipeline-readiness", title, "met" if met else "not-met", bar,
                       tuple(lines))


def _rate(value) -> str:
    return f"{value:.1%}" if isinstance(value, (int, float)) and not isinstance(value, bool) \
        else "unknown"


def build_dossier(inputs: DossierInputs) -> list[DossierItem]:
    return [sourcing_integrity(inputs), reality_checks(inputs), churn(inputs),
            graph_health(inputs), pipeline_readiness(inputs)]


def _compile(root: Path) -> tuple[tuple | None, str, int]:
    from langatlas_questionnaire.compiler import compile_spec
    from langatlas_questionnaire.spec import validate_spec

    try:
        spec = compile_spec(root)
        return tuple(validate_spec(spec)), "", len(spec.get("diagnostics") or [])
    except Exception as exc:
        # A compiler that cannot run is this item's finding, not a reason for the whole report
        # to crash — so every failure is caught and reported, not just CompileError.
        return None, f"{type(exc).__name__}: {exc}", 0


def _read_json(path: Path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        raise StoreReadError(f"{path}: not readable JSON ({type(exc).__name__}: {exc})") from exc


def _read_verification(store, root: Path, ledger_file: Path):
    import sqlite3

    from langatlas_ingest.verify.ledger import VerdictLedger
    from langatlas_ingest.verify.sources import load_source_facts

    if not ledger_file.exists():
        return None
    try:
        with VerdictLedger(ledger_file) as ledger:
            return fact_verification(store.facts, ledger=ledger,
                                     source_facts=load_source_facts(root / "sources"))
    except (sqlite3.Error, OSError, ValueError, KeyError, TypeError) as exc:
        raise StoreReadError(f"{ledger_file}: verdict ledger or source records unreadable"
                             f" ({type(exc).__name__}: {exc})") from exc


def _claude_usage(cycles, cost_log: Path) -> dict:
    from langatlas_pipeline.costlog import read_cost_rows

    try:
        rows = [row for row in read_cost_rows(cost_log) if row.endpoint == "claude"]
    except (OSError, ValueError, TypeError) as exc:
        raise StoreReadError(f"{cost_log}: cost log unreadable ({type(exc).__name__}: {exc})"
                             ) from exc
    usage = {}
    for cycle in cycles:
        # run ids are `<date>-<kind>-<slug>-<seq>` (D18); every cycle-scoped run's slug starts
        # with the cycle slug.
        mine = [row for row in rows if f"-{cycle.slug}-" in f"{row.run_id}-"]
        if mine:
            usage[cycle.slug] = (len({row.run_id for row in mine}), len(mine))
    return usage


def gather(repo_root: Path, *, ledger_path: Path | None = None,
           cost_log: Path | None = None) -> DossierInputs:
    """Reads everything the dossier needs, once, and always returns well-typed inputs: a
    *missing* ledger, cost log, calibration file, carve plan or reality check is an honest
    `no-data`; a *corrupt* one is a `StoreReadError` (the CLI's exit 2), never a traceback.
    Cycles come back sorted by number."""
    from langatlas_ingest.paths import VERDICT_LEDGER_PATH
    from langatlas_pipeline import paths as pipeline_paths
    from langatlas_research.consolidate.cross_theme import theme_membership
    from langatlas_research.cycle import load_cycle
    from langatlas_research.draft.plan import load_plan
    from langatlas_research.errors import DraftMissing, RealityCheckMissing
    from langatlas_research.paths import cycles_dir
    from langatlas_research.reality.record import load_record as load_reality

    root = Path(repo_root)
    store = load_store(root)
    try:
        cycles = tuple(sorted(
            (load_cycle(int(path.name[:2]), repo_root=root)
             for path in cycles_dir(root).glob("*.yaml")), key=lambda cycle: cycle.number))
        plans, reality = {}, {}
        for cycle in cycles:
            try:
                plans[cycle.slug] = load_plan(cycle.slug, repo_root=root)
            except DraftMissing:
                pass
            try:
                reality[cycle.slug] = load_reality(cycle.slug, repo_root=root)
            except RealityCheckMissing:
                pass
        membership = theme_membership(root)
    except StoreReadError:
        raise
    except Exception as exc:
        raise StoreReadError(f"research cycles, plans or reality checks under {root} cannot be"
                             f" read ({type(exc).__name__}: {exc})") from exc

    manifests = []
    for rel, manifest in iter_manifests(root):
        if not isinstance(manifest, dict):
            raise StoreReadError(f"{rel}: migration manifest is unreadable or not a mapping"
                                 + (f" ({manifest})" if isinstance(manifest, Exception) else ""))
        manifests.append(manifest)

    verification = _read_verification(
        store, root, Path(ledger_path) if ledger_path else VERDICT_LEDGER_PATH)
    calibration_file = root / "benchmarks" / "d24-verifier" / "calibration.json"
    calibration = _read_json(calibration_file) if calibration_file.exists() else None
    compile_errors, compile_failure, diagnostics = _compile(root)
    return DossierInputs(
        store=store, cycles=cycles, plans=plans, reality=reality, manifests=tuple(manifests),
        membership=membership, verification=verification, calibration=calibration,
        retrieval_verdict=(root / "benchmarks" / "d22-source-corpus" / "verdict.json").exists(),
        compile_errors=compile_errors, compile_failure=compile_failure,
        compile_diagnostics=diagnostics,
        claude_by_cycle=_claude_usage(cycles, Path(cost_log) if cost_log
                                      else pipeline_paths.COST_LOG_PATH))


def render_dossier(items: list[DossierItem]) -> str:
    lines = ["# R6 exit dossier", "", _ADVISORY, "", "| item | status | bar |", "|---|---|---|"]
    lines += [f"| {item.title} | {item.status} | {item.bar} |" for item in items]
    for item in items:
        lines += ["", f"## {item.title} — {item.status}", "", f"Bar: {item.bar}", ""]
        lines += [f"  - {line.strip()}" if line.startswith("  ") else f"- {line}"
                  for line in item.lines]
    return "\n".join(lines) + "\n"
