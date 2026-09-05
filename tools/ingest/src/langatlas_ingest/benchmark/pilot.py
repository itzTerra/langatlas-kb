import collections
import itertools
from dataclasses import dataclass
from typing import Sequence
from langatlas_ingest.eval import expected_sources_of


@dataclass(frozen=True)
class PilotSelection:
    sources: tuple[str, ...]
    covered: int
    total: int
    per_band: dict[str, int]

    def to_markdown(self) -> str:
        bands = ", ".join(f"{band}: {count}"
                          for band, count in sorted(self.per_band.items()))
        return (f"pilot: {', '.join(self.sources)}\n"
                f"covered: {self.covered}/{self.total} queries ({bands})\n")


def source_frequency(entries: list[dict]) -> dict[str, int]:
    counter: collections.Counter = collections.Counter()
    for entry in entries:
        counter.update(expected_sources_of(entry))
    return dict(counter)


def select_pilot(entries: list[dict], *, size: int = 4,
                 available: Sequence[str] | None = None) -> PilotSelection:
    """Exhaustive over the sources the golden set actually names — twelve of them today,
    so C(12,4)=495 candidate sets, which is nothing. A greedy set-cover would be faster
    and occasionally wrong, and 'occasionally wrong' is not a property the corpus the
    whole benchmark runs on should have.

    A query counts as covered only when *every* source it names is in the pilot. That is
    strict on purpose for the cross-source-survey band: a survey scored against half its
    sources is not a survey, and `run_eval`'s `corpus_sources` gate applies the identical
    rule, so this number is exactly what the arms will report.
    """
    needs = [(entry.get("band"), expected_sources_of(entry)) for entry in entries]
    pool = sorted(source_frequency(entries))
    if available is not None:
        allowed = set(available)
        pool = [source for source in pool if source in allowed]
    size = min(size, len(pool))

    best: tuple[int, tuple[str, ...]] | None = None
    for combination in itertools.combinations(pool, size):
        chosen = set(combination)
        covered = sum(1 for _, sources in needs if sources <= chosen)
        # `itertools.combinations` walks a sorted pool in lexicographic order, and a
        # strict `>` keeps the first of any tie — so the answer is stable across runs and
        # across machines, which matters because it is committed configuration.
        if best is None or covered > best[0]:
            best = (covered, combination)

    covered, combination = best if best else (0, ())
    chosen = set(combination)
    per_band: collections.Counter = collections.Counter(
        band for band, sources in needs if sources <= chosen)
    return PilotSelection(sources=tuple(combination), covered=covered,
                          total=len(needs), per_band=dict(per_band))
