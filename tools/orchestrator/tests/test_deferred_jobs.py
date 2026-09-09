import pytest

from langatlas_orchestrator.registry import UnknownJobKind, get_job_kind
import langatlas_orchestrator.jobs  # noqa: F401

_DEFERRED_KINDS = (
    "monthly-demand-export",
    "backstop-sweep-18mo",
)


@pytest.mark.parametrize("kind", _DEFERRED_KINDS)
def test_deferred_kind_is_registered(kind):
    import langatlas_orchestrator.jobs  # noqa: F401
    get_job_kind(kind)   # raises UnknownJobKind if not registered — the assertion itself


@pytest.mark.parametrize("kind", _DEFERRED_KINDS)
def test_deferred_kind_enumerator_raises_with_a_stage_pointer(kind, tmp_path):
    import langatlas_orchestrator.jobs  # noqa: F401
    enumerator, _item_runner = get_job_kind(kind)
    with pytest.raises(NotImplementedError, match="Stage"):
        enumerator({}, tmp_path)


def test_unregistered_kind_still_raises_unknown_job_kind():
    with pytest.raises(UnknownJobKind):
        get_job_kind("not-a-real-kind-at-all")
