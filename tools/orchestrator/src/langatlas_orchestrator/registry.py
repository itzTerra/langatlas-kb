from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Literal

Status = Literal["done", "blocked", "contention", "halted"]


@dataclass(frozen=True)
class ItemOutcome:
    """What an item runner reports back to the driver for one work item. `blocked`/
    `contention` are distinguished from `halted` the same way D36's `LandResult` does:
    the former are still valid and re-attemptable, the latter needs a human to look at
    a filed issue before this item is ever retried."""

    status: Status
    record_key: str | None = None
    detail: str = ""


# (job-specific config from the batch spec, repo_root) -> ordered work-item keys
EnumeratorFn = Callable[[dict, Path], list[str]]
# (RunContext, item_key, job-specific config, repo_root) -> ItemOutcome
ItemRunnerFn = Callable[[Any, str, dict, Path], ItemOutcome]

_REGISTRY: dict[str, tuple[EnumeratorFn, ItemRunnerFn]] = {}


class UnknownJobKind(KeyError):
    """A batch spec named a `kind` no `jobs/*.py` module has registered."""


def register_job_kind(kind: str, enumerator: EnumeratorFn,
                      item_runner: ItemRunnerFn) -> None:
    """D43 §2.1: adding a job kind is one call to this function plus one YAML file —
    never a change to `driver.py` itself."""
    _REGISTRY[kind] = (enumerator, item_runner)


def get_job_kind(kind: str) -> tuple[EnumeratorFn, ItemRunnerFn]:
    try:
        return _REGISTRY[kind]
    except KeyError:
        raise UnknownJobKind(f"no job kind registered: {kind!r}") from None


def registered_kinds() -> list[str]:
    return sorted(_REGISTRY)
