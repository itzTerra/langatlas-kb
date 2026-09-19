"""The R6 exit dossier (§7.4, D27/D52): five advisory items the developer reads before
declaring `1.0.0`. Each item is a pure function of one `DossierInputs` snapshot, so the
arithmetic is testable without a repository; `gather` (Task 16) builds the snapshot from disk.

Every bar is advisory. `met` / `not-met` report a bar, `no-data` says there is nothing yet to
measure, and `info` marks an item the spec gives no bar (graph health)."""
from dataclasses import dataclass

from langatlas_research.draft.gate import GATED_LISTS
from langatlas_research.draft.plan import entries

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
    for cycle in inputs.cycles:
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


def render_dossier(items: list[DossierItem]) -> str:
    lines = ["# R6 exit dossier", "", _ADVISORY, "", "| item | status | bar |", "|---|---|---|"]
    lines += [f"| {item.title} | {item.status} | {item.bar} |" for item in items]
    for item in items:
        lines += ["", f"## {item.title} — {item.status}", "", f"Bar: {item.bar}", ""]
        lines += [f"  - {line.strip()}" if line.startswith("  ") else f"- {line}"
                  for line in item.lines]
    return "\n".join(lines) + "\n"
