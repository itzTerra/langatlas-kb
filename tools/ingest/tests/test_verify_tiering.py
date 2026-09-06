from langatlas_ingest.config import IngestConfig
from langatlas_ingest.verify.entailment import AssertionOut, EntailmentOut
from langatlas_ingest.verify.tiering import (
    DEFAULT_SECOND_OPINION_RATE, ESCALATION_ALIAS, PRIMARY_ALIAS, SECOND_OPINION_ALIAS,
    needs_escalation, sampled_for_second_opinion,
)


def out(*statuses, since_status=None):
    return EntailmentOut(
        assertions=[AssertionOut(kind="presence", text="t", status=s) for s in statuses],
        since_status=since_status)


def test_the_three_aliases_are_the_ratified_roster():
    assert (PRIMARY_ALIAS, ESCALATION_ALIAS, SECOND_OPINION_ALIAS) == \
        ("deepseek", "deepseek-thinking", "mini")


def test_partial_escalates():
    assert needs_escalation("partial", out("supported"), has_since=False) is True


def test_contradicted_escalates():
    assert needs_escalation("contradicted", out("contradicted"), has_since=False) is True


def test_supported_does_not_escalate():
    assert needs_escalation("supported", out("supported"), has_since=False) is False


def test_inconsistent_output_escalates_even_when_supported():
    assert needs_escalation("supported", out(), has_since=False) is True


def test_second_opinion_sampling_is_deterministic():
    args = ("f-000000000001", "scott-plp", "p. 12")
    first = sampled_for_second_opinion(*args, rate=DEFAULT_SECOND_OPINION_RATE)
    second = sampled_for_second_opinion(*args, rate=DEFAULT_SECOND_OPINION_RATE)
    assert first is second


def test_second_opinion_sampling_hits_roughly_the_configured_rate():
    # A drift gauge that sampled 1% or 40% would either be silent or double the batch's
    # cost. 500 pairs is enough to catch a rate that is wrong by an order of magnitude.
    hits = sum(sampled_for_second_opinion(f"f-{i:012d}", "s", "p. 1", rate=0.10)
               for i in range(500))
    assert 25 <= hits <= 75


def test_a_rate_of_one_samples_everything():
    # The hardening path Section 6.2 names: if measured false-accept misses target, the
    # `mini` sample becomes a mandatory second vote for every `supported`.
    assert all(sampled_for_second_opinion(f"f-{i:012d}", "s", "p. 1", rate=1.0)
               for i in range(50))


def test_a_rate_of_zero_samples_nothing():
    assert not any(sampled_for_second_opinion(f"f-{i:012d}", "s", "p. 1", rate=0.0)
                   for i in range(50))


def test_the_config_exposes_the_verification_block():
    config = IngestConfig.load()
    assert config.verification_aliases == ("deepseek", "deepseek-thinking", "mini")
    assert config.second_opinion_rate == DEFAULT_SECOND_OPINION_RATE
    assert config.mandatory_second_opinion is False
