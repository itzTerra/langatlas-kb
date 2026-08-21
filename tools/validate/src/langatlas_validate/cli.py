import argparse
from pathlib import Path
from typing import Iterator
from ruamel.yaml import YAML
from langatlas_validate import __version__
from langatlas_validate.schema import validate_record, RECORD_KINDS
from langatlas_validate.normalize import normalize_record
from langatlas_validate.regression import run_regression
from langatlas_validate.locators import validate_locator_shape
from langatlas_validate.paths import REPO_ROOT as _REPO_ROOT, FIXTURES_DIR as _FIXTURES
from langatlas_validate.store import validate_store

_yaml = YAML(typ="safe")


def _iter_source_entries(data) -> Iterator[dict]:
    """Structurally walk a parsed record, yielding every dict that looks like a
    sourceEntry ({"source": str, "locator": str}), regardless of where it is
    nested (summary.sources, characteristics[].sources, edge/rule sources, ...)."""
    if isinstance(data, dict):
        if isinstance(data.get("source"), str) and isinstance(data.get("locator"), str):
            yield data
        for value in data.values():
            yield from _iter_source_entries(value)
    elif isinstance(data, list):
        for item in data:
            yield from _iter_source_entries(item)


def cmd_precommit(files: list[str], kind: str) -> int:
    rc = 0
    for f in files:
        text = Path(f).read_text()
        data = _yaml.load(text)
        errors = validate_record(data, kind)
        for entry in _iter_source_entries(data):
            if validate_locator_shape(entry["locator"]) is None:
                errors.append(f"locator: unrecognized shape: {entry['locator']!r}")
        if normalize_record(text, kind) != text:
            errors.append("not normalized (re-run the normalizer to fix)")
        for e in errors:
            print(f"{f}: {e}")
        rc = rc or (1 if errors else 0)
    return rc


def _print_report(report, *, verbose: bool) -> int:
    for failure in report.failures:
        print(f"FAIL {failure}")
    for warning in report.warnings:
        print(f"warn {warning}")
    for skip in report.skipped:
        print(f"skip {skip}")
    if verbose:
        print(f"ran={report.ran} passed={report.passed} failed={len(report.failures)} "
              f"warned={len(report.warnings)} skipped={len(report.skipped)}")
    return 1 if report.failures else 0


def cmd_ci() -> int:
    rc = _print_report(run_regression(_FIXTURES), verbose=True)
    store_errors = validate_store(_REPO_ROOT)
    for e in store_errors:
        print(f"STORE {e}")
    return rc or (1 if store_errors else 0)


def cmd_regression_run() -> int:
    return _print_report(run_regression(_FIXTURES), verbose=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="langatlas-validate")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command")

    p_pre = sub.add_parser("precommit")
    p_pre.add_argument("--kind", required=True, choices=RECORD_KINDS)
    p_pre.add_argument("files", nargs="+")

    sub.add_parser("ci")

    p_reg = sub.add_parser("regression")
    p_reg.add_argument("regression_command", choices=["run"])

    args = parser.parse_args(argv)
    if args.command == "precommit":
        return cmd_precommit(args.files, args.kind)
    if args.command == "ci":
        return cmd_ci()
    if args.command == "regression":
        return cmd_regression_run()
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
