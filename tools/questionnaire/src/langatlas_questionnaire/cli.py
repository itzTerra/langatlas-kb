"""`langatlas-questionnaire` — compile, diff and validate sweep questionnaires (D46).

On demand only, never cron: at R5 (through `langatlas-research reality compile`), at
R6/first-sweep-launch (Stage 4), and at each D28 onboarding phase start. `compile` writes the
spec; it does not commit it — R5's `reality compile` lands it through the commit protocol, and a
by-hand compile is committed by the developer."""
import argparse
import sys
from pathlib import Path

from langatlas_questionnaire.compiler import CompileError, compile_spec
from langatlas_questionnaire.paths import REPO_ROOT
from langatlas_questionnaire.spec import (
    SPEC_DIR, diff_specs, load_spec, render_spec, spec_rel, validate_spec, write_spec,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="langatlas-questionnaire")
    parser.add_argument("--repo-root", type=Path, default=None)
    sub = parser.add_subparsers(dest="command", required=True)
    p_compile = sub.add_parser("compile", help="compile the store into questionnaire/spec-<v>.yaml")
    p_compile.add_argument("--stdout", action="store_true", help="print instead of writing")
    p_compile.add_argument("--check", action="store_true",
                           help="exit 1 unless the committed spec for this version matches")
    p_diff = sub.add_parser("diff", help="the delta questionnaire between two specs")
    p_diff.add_argument("old", type=Path)
    p_diff.add_argument("new", type=Path)
    sub.add_parser("validate", help="schema-check every committed spec")
    args = parser.parse_args(argv)
    root = args.repo_root or REPO_ROOT

    if args.command == "diff":
        return _diff(load_spec(args.old), load_spec(args.new))
    if args.command == "validate":
        return _validate(root)
    try:
        spec = compile_spec(root)
    except CompileError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if args.stdout:
        print(render_spec(spec), end="")
        return 0
    if args.check:
        path = root / spec_rel(spec["ontology_version"])
        if path.exists() and path.read_text() == render_spec(spec):
            print(f"{path.relative_to(root)} matches a fresh compile")
            return 0
        print(f"{spec_rel(spec['ontology_version'])} is missing or differs from a fresh compile")
        return 1
    path = write_spec(spec, root)
    print(f"wrote {path.relative_to(root)}")
    for diagnostic in spec["diagnostics"]:
        print(f"diagnostic: {diagnostic['kind']}: {diagnostic['dimension']}")
    return 0


def _diff(old: dict, new: dict) -> int:
    diff = diff_specs(old, new)
    requeue = diff["added"] + diff["changed"]
    print(f"{diff['from']} -> {diff['to']}")
    print(f"requeue (added + changed): {len(requeue)}")
    for key in ("added", "changed", "removed", "constraints_added", "constraints_removed",
                "constraints_changed"):
        for entry in diff[key]:
            print(f"  {key}: {entry}")
    return 0


def _validate(root: Path) -> int:
    paths = sorted((root / SPEC_DIR).glob("spec-*.yaml"))
    failures = 0
    for path in paths:
        errors = validate_spec(load_spec(path))
        failures += bool(errors)
        for error in errors:
            print(f"{path.relative_to(root)}: {error}", file=sys.stderr)
    print(f"{len(paths)} spec(s), {failures} invalid")
    return 1 if failures else 0
