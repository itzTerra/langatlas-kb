import argparse
from pathlib import Path
from ruamel.yaml import YAML
from langatlas_validate import __version__
from langatlas_validate.schema import validate_record, RECORD_KINDS
from langatlas_validate.normalize import normalize_record
from langatlas_validate.regression import run_regression

_yaml = YAML(typ="safe")
_REPO_ROOT = Path(__file__).resolve().parents[4]   # src layout: one level deeper than tests/
_FIXTURES = _REPO_ROOT / "tests" / "fixtures" / "providers"


def cmd_precommit(files: list[str], kind: str) -> int:
    rc = 0
    for f in files:
        text = Path(f).read_text()
        data = _yaml.load(text)
        errors = validate_record(data, kind)
        if normalize_record(text, kind) != text:
            errors.append("not normalized (re-run the normalizer to fix)")
        for e in errors:
            print(f"{f}: {e}")
        rc = rc or (1 if errors else 0)
    return rc


def cmd_ci() -> int:
    report = run_regression(_FIXTURES)
    for failure in report.failures:
        print(failure)
    return 1 if report.failures else 0


def cmd_regression_run() -> int:
    report = run_regression(_FIXTURES)
    for failure in report.failures:
        print(failure)
    print(f"ran={report.ran} passed={report.passed} failed={len(report.failures)}")
    return 1 if report.failures else 0


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
