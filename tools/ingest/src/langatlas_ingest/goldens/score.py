import json
from dataclasses import dataclass, field
from langatlas_ingest.goldens.items import ADMITTING_VERDICTS, CONTROVERSY_LEVELS, STRATA


@dataclass(frozen=True)
class Thresholds:
    """Section 6.2's deliberately asymmetric targets: a false accept poisons a public,
    RAG-recycled corpus; a false reject costs one retry."""

    false_accept_max: float = 0.02
    false_reject_max: float = 0.10


@dataclass(frozen=True)
class VerdictOutcome:
    """What a verifier returned for one item. `per_assertion` mirrors §6.2's
    decomposition so 2D can attach it without a second type."""

    verdict: str
    annotations: tuple[str, ...] = ()
    per_assertion: tuple[dict, ...] = ()
    model: str | None = None


@dataclass(frozen=True)
class StratumScore:
    items: int = 0
    exact: int = 0
    false_accepts: int = 0
    false_rejects: int = 0

    def as_dict(self) -> dict:
        return {"items": self.items, "exact": self.exact,
                "false_accepts": self.false_accepts, "false_rejects": self.false_rejects}


@dataclass(frozen=True)
class GaugeScore:
    """§6.4's passive contamination gauge. A model that is much better on mainstream loci
    than on obscure ones is recognising, not reading."""

    gauge_items: int = 0
    gauge_exact_rate: float | None = None
    mainstream_items: int = 0
    mainstream_exact_rate: float | None = None
    gap: float | None = None

    def as_dict(self) -> dict:
        return {"gauge_items": self.gauge_items,
                "gauge_exact_rate": self.gauge_exact_rate,
                "mainstream_items": self.mainstream_items,
                "mainstream_exact_rate": self.mainstream_exact_rate, "gap": self.gap}


@dataclass(frozen=True)
class VerifierScore:
    items: int
    exact_verdict_accuracy: float
    annotation_accuracy: float | None
    # `None`, never 0.0, when the stratum mix contains no items of that side: an empty
    # denominator is "not measured", and reporting it as a perfect 0% error rate would be
    # the single most dangerous rounding in the project.
    false_accept_rate: float | None
    false_reject_rate: float | None
    false_accepts: list[str]
    false_rejects: list[str]
    per_stratum: dict
    absent_items: int
    absent_false_accept_rate: float | None
    gauge: GaugeScore
    thresholds: Thresholds
    thresholds_met: bool

    def to_markdown(self) -> str:
        def pct(value):
            return "n/a" if value is None else f"{value:.2%}"

        lines = ["# Verifier golden-set score", "",
                 f"- items: {self.items}",
                 f"- exact-verdict accuracy: {self.exact_verdict_accuracy:.2%}",
                 f"- annotation accuracy: {pct(self.annotation_accuracy)}",
                 f"- **false accept: {pct(self.false_accept_rate)}**"
                 f" (target <={self.thresholds.false_accept_max:.0%})",
                 f"- **false reject: {pct(self.false_reject_rate)}**"
                 f" (target <={self.thresholds.false_reject_max:.0%})",
                 f"- absent items: {self.absent_items}, false accept:"
                 f" {pct(self.absent_false_accept_rate)}",
                 f"- contamination gauge: obscure {pct(self.gauge.gauge_exact_rate)} vs"
                 f" mainstream {pct(self.gauge.mainstream_exact_rate)}"
                 f" (gap {pct(self.gauge.gap)})",
                 f"- thresholds met: {self.thresholds_met}", "",
                 "## Per stratum", "",
                 "| stratum | items | exact | FA | FR |", "|---|---|---|---|---|"]
        for stratum in STRATA:
            score = self.per_stratum.get(stratum, StratumScore())
            lines.append(f"| {stratum} | {score.items} | {score.exact} |"
                         f" {score.false_accepts} | {score.false_rejects} |")
        return "\n".join(lines) + "\n"

    def to_json(self) -> str:
        """The machine-readable form §6.2 requires the measured error rates to be
        published in — the D35 bundle manifest and the site both read this."""
        return json.dumps({
            "items": self.items,
            "exact_verdict_accuracy": self.exact_verdict_accuracy,
            "annotation_accuracy": self.annotation_accuracy,
            "false_accept_rate": self.false_accept_rate,
            "false_reject_rate": self.false_reject_rate,
            "false_accepts": self.false_accepts,
            "false_rejects": self.false_rejects,
            "absent_items": self.absent_items,
            "absent_false_accept_rate": self.absent_false_accept_rate,
            "contamination_gauge": self.gauge.as_dict(),
            "thresholds": {"false_accept_max": self.thresholds.false_accept_max,
                           "false_reject_max": self.thresholds.false_reject_max},
            "thresholds_met": self.thresholds_met,
            "per_stratum": {k: v.as_dict() for k, v in self.per_stratum.items()},
        }, indent=2, sort_keys=True)


def _rate(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def score_verifier(items, outcomes: dict, *, thresholds: Thresholds) -> VerifierScore:
    """Score a verifier's outcomes against the committed golden items.

    @param items - the loaded `VerifierItem`s
    @param outcomes - item id -> `VerdictOutcome`; every item must have one

    @pre item ids are unique (enforced by `loader.validate_items`)

    @returns the scored result, with false-accept and false-reject rates over their own
        denominators — the two error kinds have opposite costs and are never averaged
    """
    counters, exact_hits, annotation_hits, annotation_items = {}, 0, 0, 0
    false_accepts, false_rejects = [], []
    should_admit = admitted_wrongly = should_reject = rejected_wrongly = 0
    absent_total = absent_false_accepts = 0
    gauge_items = gauge_exact = mainstream_items = mainstream_exact = 0

    for item in items:
        outcome = outcomes.get(item.id)
        if outcome is None:
            raise ValueError(f"no outcome for golden item {item.id!r}")
        stratum = counters.setdefault(item.stratum, {"items": 0, "exact": 0,
                                                     "fa": 0, "fr": 0})
        stratum["items"] += 1
        is_exact = outcome.verdict == item.expected_verdict
        exact_hits += is_exact
        stratum["exact"] += is_exact

        if item.expected_annotations:
            annotation_items += 1
            annotation_hits += set(outcome.annotations) >= set(item.expected_annotations)

        expected_admits = item.expected_verdict in ADMITTING_VERDICTS
        actually_admits = outcome.verdict in ADMITTING_VERDICTS
        if expected_admits:
            should_admit += 1
            if not actually_admits:
                rejected_wrongly += 1
                false_rejects.append(item.id)
                stratum["fr"] += 1
        else:
            should_reject += 1
            if actually_admits:
                admitted_wrongly += 1
                false_accepts.append(item.id)
                stratum["fa"] += 1

        if item.claim.status == "absent":
            absent_total += 1
            absent_false_accepts += (not expected_admits) and actually_admits
        if item.contamination_gauge:
            gauge_items += 1
            gauge_exact += is_exact
        else:
            mainstream_items += 1
            mainstream_exact += is_exact

    false_accept_rate = _rate(admitted_wrongly, should_reject)
    false_reject_rate = _rate(rejected_wrongly, should_admit)
    gauge_rate = _rate(gauge_exact, gauge_items)
    mainstream_rate = _rate(mainstream_exact, mainstream_items)
    gap = None if gauge_rate is None or mainstream_rate is None \
        else mainstream_rate - gauge_rate
    met = ((false_accept_rate is None or
            false_accept_rate <= thresholds.false_accept_max) and
           (false_reject_rate is None or
            false_reject_rate <= thresholds.false_reject_max))

    return VerifierScore(
        items=len(items),
        exact_verdict_accuracy=_rate(exact_hits, len(items)) or 0.0,
        annotation_accuracy=_rate(annotation_hits, annotation_items),
        false_accept_rate=false_accept_rate, false_reject_rate=false_reject_rate,
        false_accepts=false_accepts, false_rejects=false_rejects,
        per_stratum={name: StratumScore(items=c["items"], exact=c["exact"],
                                        false_accepts=c["fa"], false_rejects=c["fr"])
                     for name, c in counters.items()},
        absent_items=absent_total,
        absent_false_accept_rate=_rate(absent_false_accepts, absent_total),
        gauge=GaugeScore(gauge_items=gauge_items, gauge_exact_rate=gauge_rate,
                         mainstream_items=mainstream_items,
                         mainstream_exact_rate=mainstream_rate, gap=gap),
        thresholds=thresholds, thresholds_met=met)


@dataclass(frozen=True)
class ControversyScore:
    cases: int
    exact_accuracy: float
    within_one_accuracy: float
    confusion: dict = field(default_factory=dict)
    level3_recall: float | None = None

    def to_markdown(self) -> str:
        lines = ["# Controversy golden-case score", "",
                 f"- cases: {self.cases}",
                 f"- exact level accuracy: {self.exact_accuracy:.2%}",
                 f"- within-one accuracy: {self.within_one_accuracy:.2%}",
                 "- level-3 recall: " + ("n/a" if self.level3_recall is None
                                         else f"{self.level3_recall:.2%}"), "",
                 "## Confusion (expected -> assigned)", ""]
        for expected in CONTROVERSY_LEVELS:
            row = " ".join(f"{self.confusion.get((expected, got), 0)}"
                           for got in CONTROVERSY_LEVELS)
            lines.append(f"- {expected}: {row}")
        return "\n".join(lines) + "\n"


def score_controversy(cases, levels: dict) -> ControversyScore:
    """Ordinal scoring: exact match, within-one tolerance (adjacent-level ambiguity is
    Claude's escalation path, not a bug), and a 4x4 confusion matrix. Level-3 recall is
    called out because every level-3 assignment escalates to Claude — missing one is
    materially worse than confusing 1 with 2."""
    confusion, exact, within_one = {}, 0, 0
    level3_total = level3_hits = 0
    for case in cases:
        assigned = levels.get(case.id)
        if assigned is None:
            raise ValueError(f"no level for controversy case {case.id!r}")
        confusion[(case.expected_level, assigned)] = \
            confusion.get((case.expected_level, assigned), 0) + 1
        exact += assigned == case.expected_level
        within_one += abs(assigned - case.expected_level) <= 1
        if case.expected_level == 3:
            level3_total += 1
            level3_hits += assigned == 3
    total = len(cases)
    return ControversyScore(cases=total, exact_accuracy=_rate(exact, total) or 0.0,
                            within_one_accuracy=_rate(within_one, total) or 0.0,
                            confusion=confusion,
                            level3_recall=_rate(level3_hits, level3_total))
