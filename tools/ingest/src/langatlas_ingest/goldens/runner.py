import importlib
from typing import Callable, Protocol
from langatlas_ingest.goldens.items import ControversyCase, VerifierItem
from langatlas_ingest.goldens.score import (
    ControversyScore, Thresholds, VerdictOutcome, VerifierScore, score_controversy,
    score_verifier,
)

__all__ = ["Assessor", "Verifier", "VerdictOutcome", "load_entry_point",
           "run_controversy_goldens", "run_verifier_goldens"]


class Verifier(Protocol):
    """What 2D must provide. The runner knows nothing else about the verifier — no
    construction, no configuration, no tools — so 2B can ship a calibrated harness
    before a single line of verifier code exists."""

    def __call__(self, item: VerifierItem) -> VerdictOutcome: ...


class Assessor(Protocol):
    def __call__(self, case: ControversyCase) -> int: ...


def load_entry_point(dotted: str) -> Callable:
    """Resolve a `package.module:attribute` path.

    @param dotted - e.g. `langatlas_ingest.goldens.score:score_verifier`

    @returns the resolved attribute
    """
    module_name, _, attribute = dotted.partition(":")
    if not attribute:
        raise ImportError(f"{dotted!r} is not a `module:attribute` path")
    try:
        module = importlib.import_module(module_name)
    except ModuleNotFoundError as exc:
        raise ImportError(f"cannot import {module_name!r} for entry point"
                          f" {dotted!r}") from exc
    try:
        return getattr(module, attribute)
    except AttributeError as exc:
        raise ImportError(f"{module_name!r} has no attribute"
                          f" {attribute!r}") from exc


def run_verifier_goldens(items, verify: Verifier, *, thresholds: Thresholds,
                         ctx=None) -> VerifierScore:
    """Run `verify` over every golden item and score the outcomes.

    A verifier that raises is recorded as `source-unavailable` rather than aborting the
    run: a provider outage mid-batch must produce a legible partial score (and, for a
    should-admit item, an honest false reject) instead of losing every verdict computed
    so far.

    @param ctx - optional `RunContext`; a run summary is appended to its transcript (D18)

    @returns the scored result
    """
    outcomes = {}
    for item in items:
        try:
            outcomes[item.id] = verify(item)
        except Exception as exc:                # noqa: BLE001 — see docstring
            outcomes[item.id] = VerdictOutcome("source-unavailable",
                                               model=f"error:{type(exc).__name__}")
    score = score_verifier(items, outcomes, thresholds=thresholds)
    if ctx is not None:
        ctx.writer.append(role="assistant", content=score.to_markdown(),
                          flags=["golden-score:verifier"])
    return score


def run_controversy_goldens(cases, assess: Assessor, *, ctx=None) -> ControversyScore:
    levels = {}
    for case in cases:
        levels[case.id] = assess(case)
    score = score_controversy(cases, levels)
    if ctx is not None:
        ctx.writer.append(role="assistant", content=score.to_markdown(),
                          flags=["golden-score:controversy"])
    return score
