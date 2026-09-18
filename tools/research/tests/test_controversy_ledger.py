"""The ledger is a cache, never ground truth: losing it costs one expensive re-run and
nothing else. These tests pin the one property the nightly batch depends on — an unchanged
digest means the model is never called again."""
from langatlas_research.controversy.ledger import AssessmentLedger


class _A:
    def __init__(self, fact_id, level, signals, escalated_to=None):
        self.fact_id, self.level, self.signals = fact_id, level, tuple(signals)
        self.model, self.prompt, self.run_id = "deepseek-v4-pro-thinking", "p@v-1", "r-1"
        self.escalated_to = escalated_to


def test_an_unseen_fact_has_no_previous_assessment(tmp_path):
    with AssessmentLedger(tmp_path / "a.sqlite") as ledger:
        assert ledger.previous("f-aaaaaaaaaaaa") is None


def test_a_recorded_assessment_comes_back_by_digest(tmp_path):
    with AssessmentLedger(tmp_path / "a.sqlite") as ledger:
        ledger.record(_A("f-aaaaaaaaaaaa", 2, ["verdict:partial:since"]), digest="0123456789abcdef")
        assert ledger.previous("f-aaaaaaaaaaaa") == ("0123456789abcdef", 2,
                                                     ("verdict:partial:since",))


def test_re_recording_the_same_fact_replaces_rather_than_duplicates(tmp_path):
    with AssessmentLedger(tmp_path / "a.sqlite") as ledger:
        ledger.record(_A("f-a", 1, []), digest="aaaa")
        ledger.record(_A("f-a", 3, ["verdict:contradicted:base"]), digest="bbbb")
        assert ledger.previous("f-a") == ("bbbb", 3, ("verdict:contradicted:base",))
        assert ledger.levels() == {"f-a": 3}


def test_the_ledger_survives_reopening(tmp_path):
    path = tmp_path / "a.sqlite"
    with AssessmentLedger(path) as ledger:
        ledger.record(_A("f-a", 2, ["assessment-spread:readability_edge_strength"]), digest="cc")
    with AssessmentLedger(path) as reopened:
        assert reopened.previous("f-a")[1] == 2
