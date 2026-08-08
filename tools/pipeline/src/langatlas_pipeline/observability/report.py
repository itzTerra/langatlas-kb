"""Ephemeral markdown reports (D41). Output goes to stdout or a gitignored file — never
committed as canonical data, never a service. The one legitimately public number
(verifier error rates) ships via the D35 bundle manifest, not from here."""

import argparse
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from ruamel.yaml import YAML
from langatlas_pipeline.config import ProviderConfig
from langatlas_pipeline.costlog import read_cost_rows
from langatlas_pipeline.paths import COST_LOG_PATH, TRANSCRIPTS_ROOT

_yaml = YAML(typ="safe")
_STALE_AFTER_DAYS = 35          # the probe cadence is monthly (D41)


def _accepted_facts_by_run(transcripts_root: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    for manifest_path in transcripts_root.rglob("manifest.yaml"):
        manifest = _yaml.load(manifest_path.read_text()) or {}
        counts[manifest.get("run_id", manifest_path.parent.name)] = len(
            manifest.get("resulting_fact_ids") or [])
    return counts


def report_cost(cost_log: Path | None = None,
                transcripts_root: Path | None = None) -> str:
    rows = read_cost_rows(cost_log or COST_LOG_PATH)
    if not rows:
        return "# Cost\n\nNo calls recorded yet.\n"

    by_alias: dict[str, dict[str, float]] = defaultdict(
        lambda: {"calls": 0, "tokens": 0, "cached_calls": 0, "saved_tokens": 0,
                 "usd": 0.0})
    by_run: dict[str, int] = defaultdict(int)
    for row in rows:
        bucket = by_alias[row.alias]
        bucket["calls"] += 1
        bucket["tokens"] += row.tokens_in + row.tokens_out
        bucket["usd"] += row.cost_usd or 0.0
        if row.cache_hit:
            bucket["cached_calls"] += 1
            bucket["saved_tokens"] += row.tokens_if_uncached or 0
        by_run[row.run_id] += row.tokens_in + row.tokens_out

    lines = ["# Cost", "",
             "| alias | calls | tokens | cache hits | tokens saved | usd |",
             "|---|---:|---:|---:|---:|---:|"]
    for alias, bucket in sorted(by_alias.items()):
        lines.append(f"| {alias} | {bucket['calls']:.0f} | {bucket['tokens']:.0f} | "
                     f"{bucket['cached_calls']:.0f} | {bucket['saved_tokens']:.0f} | "
                     f"${bucket['usd']:.2f} |")

    facts = _accepted_facts_by_run(transcripts_root or TRANSCRIPTS_ROOT)
    lines += ["", "## Tokens per accepted fact", "",
              "| run | tokens | accepted facts | tokens/fact |", "|---|---:|---:|---:|"]
    for run_id, tokens in sorted(by_run.items()):
        accepted = facts.get(run_id, 0)
        per_fact = f"{tokens / accepted:.0f}" if accepted else "—"
        lines.append(f"| {run_id} | {tokens} | {accepted} | {per_fact} |")
    return "\n".join(lines) + "\n"


def report_capabilities(config: ProviderConfig | None = None) -> str:
    config = config or ProviderConfig.load()
    table = config.capabilities
    probed_at = table.get("probed_at")
    lines = ["# Capabilities", ""]
    if not probed_at:
        lines.append("**The table has never been probed.** Run `langatlas-probe --write`.")
    else:
        age = (datetime.now(timezone.utc)
               - datetime.strptime(probed_at, "%Y-%m-%dT%H:%M:%SZ").replace(
                   tzinfo=timezone.utc)).days
        lines.append(f"Last probed {probed_at} ({age} days ago)"
                     + (" — **stale**, the cadence is monthly." if age > _STALE_AFTER_DAYS
                        else "."))
    lines += ["", "| alias | resolved model | json_schema | json_object | window |",
              "|---|---|---|---|---:|"]
    for alias, entry in sorted((table.get("aliases") or {}).items()):
        lines.append(f"| {alias} | {entry.get('resolved_model') or '—'} | "
                     f"{entry.get('supports_json_schema')} | "
                     f"{entry.get('supports_json_object')} | "
                     f"{entry.get('max_input_tokens')} |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="langatlas-report")
    out_help = "write to a (gitignored) file instead of stdout"
    sub = parser.add_subparsers(dest="command", required=True)

    p_cost = sub.add_parser("cost")
    p_cost.add_argument("--cost-log", type=Path, default=None)
    p_cost.add_argument("--transcripts", type=Path, default=None)
    p_cost.add_argument("--out", type=Path, default=None, help=out_help)

    p_caps = sub.add_parser("capabilities")
    p_caps.add_argument("--out", type=Path, default=None, help=out_help)

    args = parser.parse_args(argv)
    if args.command == "cost":
        markdown = report_cost(args.cost_log, args.transcripts)
    else:
        markdown = report_capabilities()
    if args.out:
        args.out.write_text(markdown)
    else:
        print(markdown)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
