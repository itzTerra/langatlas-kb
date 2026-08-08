import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from langatlas_pipeline.config import ProviderConfig
from langatlas_pipeline.observability.report import (
    main, report_capabilities, report_cost,
)


def _cost_log(tmp_path: Path) -> Path:
    path = tmp_path / "cost-log.jsonl"
    rows = [
        dict(ts="2026-08-02T10:00:00Z", run_id="r1", seq=1, endpoint="chat", alias="glm",
             resolved_model="glm-5.2", prompt_id="verifier", prompt_version="v-1",
             tokens_in=100, tokens_out=20, tokens_if_uncached=None, latency_ms=800,
             cache_hit=False, outcome="ok", cost_usd=None),
        dict(ts="2026-08-02T10:01:00Z", run_id="r1", seq=2, endpoint="chat", alias="glm",
             resolved_model="glm-5.2", prompt_id="verifier", prompt_version="v-1",
             tokens_in=0, tokens_out=0, tokens_if_uncached=120, latency_ms=0,
             cache_hit=True, outcome="ok", cost_usd=None),
        dict(ts="2026-08-02T11:00:00Z", run_id="r2", seq=1, endpoint="claude",
             alias="claude", resolved_model="claude-agent-sdk", prompt_id=None,
             prompt_version=None, tokens_in=900, tokens_out=300, tokens_if_uncached=None,
             latency_ms=5000, cache_hit=False, outcome="ok", cost_usd=0.12),
    ]
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n")
    return path


def _manifests(tmp_path: Path) -> Path:
    root = tmp_path / "transcripts" / "2026" / "08"
    for run_id, facts in [("r1", ["f-1", "f-2"]), ("r2", [])]:
        run_dir = root / run_id
        run_dir.mkdir(parents=True)
        (run_dir / "manifest.yaml").write_text(
            f"run_id: {run_id}\nkind: verification\nresulting_fact_ids: {facts}\n")
    return tmp_path / "transcripts"


def test_cost_report_totals_by_alias_and_marks_cache_savings(tmp_path: Path):
    markdown = report_cost(_cost_log(tmp_path), _manifests(tmp_path))
    assert "| glm |" in markdown
    assert "120" in markdown, "the counterfactual tokens of the cache hit"
    assert "1200" in markdown or "1,200" in markdown, "claude tokens"
    assert "$0.12" in markdown


def test_cost_report_computes_cost_per_accepted_fact(tmp_path: Path):
    markdown = report_cost(_cost_log(tmp_path), _manifests(tmp_path))
    assert "accepted facts" in markdown.lower()
    assert "60" in markdown, "120 chargeable tokens over 2 facts in run r1"


def test_cost_report_on_an_empty_log_says_so(tmp_path: Path):
    assert "no calls" in report_cost(tmp_path / "missing.jsonl", tmp_path).lower()


def _fake_config(tmp_path: Path, probed_at: str | None) -> ProviderConfig:
    """A synthetic ProviderConfig with a controlled probed_at, decoupled from the real,
    now-permanently-probed config/provider_capabilities.yaml (mirrors the fixture pattern
    commit 200ea0e introduced for test_config.py/test_probe.py)."""
    aliases = {"glm": {"resolved_model": "glm-5.2", "supports_json_schema": False,
                       "supports_json_object": True, "max_input_tokens": 131072}}
    return ProviderConfig(providers={}, capabilities={"probed_at": probed_at,
                                                       "aliases": aliases},
                          config_dir=tmp_path)


def test_capabilities_report_flags_an_unprobed_table(tmp_path: Path):
    markdown = report_capabilities(_fake_config(tmp_path, probed_at=None))
    assert "never been probed" in markdown.lower()
    assert "glm" in markdown


def test_capabilities_report_shows_a_fresh_probe_without_the_stale_suffix(tmp_path: Path):
    probed_at = (datetime.now(timezone.utc) - timedelta(days=3)).strftime(
        "%Y-%m-%dT%H:%M:%SZ")
    markdown = report_capabilities(_fake_config(tmp_path, probed_at=probed_at))
    assert "last probed" in markdown.lower()
    assert "3 days ago" in markdown
    assert "stale" not in markdown.lower()


def test_capabilities_report_flags_a_stale_probe(tmp_path: Path):
    probed_at = (datetime.now(timezone.utc) - timedelta(days=40)).strftime(
        "%Y-%m-%dT%H:%M:%SZ")
    markdown = report_capabilities(_fake_config(tmp_path, probed_at=probed_at))
    assert "40 days ago" in markdown
    assert "stale" in markdown.lower()


def test_cli_writes_to_stdout_and_never_commits(capsys, tmp_path: Path):
    code = main(["cost", "--cost-log", str(_cost_log(tmp_path)),
                 "--transcripts", str(_manifests(tmp_path))])
    assert code == 0
    assert "| alias |" in capsys.readouterr().out.lower()


def test_cli_accepts_out_after_the_subcommand(capsys, tmp_path: Path):
    """--out must work in the natural position, after the subcommand name (not just
    before it on the top-level parser) — argparse requires top-level optionals to
    precede the subcommand, so --out has to live on each subparser."""
    out_path = tmp_path / "cost-report.md"
    code = main(["cost", "--out", str(out_path), "--cost-log", str(_cost_log(tmp_path)),
                 "--transcripts", str(_manifests(tmp_path))])
    assert code == 0
    assert capsys.readouterr().out == ""
    assert "| alias |" in out_path.read_text().lower()
