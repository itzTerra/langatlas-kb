import argparse
from pathlib import Path
from typing import Iterator
from ruamel.yaml import YAML
from langatlas_validate import __version__
from langatlas_validate.schema import validate_record, RECORD_KINDS
from langatlas_validate.normalize import normalize_record
from langatlas_validate.regression import run_regression
from langatlas_validate.locators import validate_locator_shape, validate_locator, SourceChunksIndex
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


def infer_kind_from_path(path: Path) -> str | None:
    parts = path.parts
    if not parts:
        return None
    if parts[0] == "concepts":
        return "concept"
    if parts[0] == "features":
        return "feature"
    if parts[0] == "languages":
        if path.name == "_registry.yaml":
            return "language-registry"
        if path.name == "language.yaml":
            return "language"
        if "instances" in parts:
            return "feature-instance"
        return None
    if parts[0] == "edges":
        return "edge"   # refined by content-sniff below when the file is read
    if parts[0] == "rules":
        return "rule"
    if parts[0] == "sources" and path.name not in ("_tombstones.yaml",):
        return "source"
    return None


def cmd_precommit_auto(files: list[str]) -> int:
    rc = 0
    for f in files:
        path = Path(f)
        kind = infer_kind_from_path(path)
        if kind is None:
            continue   # not a validated-record path (docs, config, etc.) — nothing to check
        if kind == "edge":
            data = _yaml.load(path.read_text())
            if data.get("type") == "affects-quality":
                kind = "affects-quality-edge"
        rc = cmd_precommit([f], kind) or rc
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


def cmd_ci_with_index(repo_root, index: SourceChunksIndex | None) -> tuple[int, list[str]]:
    """The store-validation pass, optionally resolving locators through `index`
    (1C's SourceChunksIndex). Only a malformed locator *shape* fails CI; an
    unresolved-but-well-shaped locator is a sourcing-queue matter (D37), not a
    CI failure — the corpus not containing a source yet is an expected state."""
    errors = validate_store(repo_root)
    from langatlas_validate.store import iter_store_records
    for path, _kind, _text, data in iter_store_records(repo_root):
        for entry in _iter_source_entries(data):
            if validate_locator_shape(entry["locator"]) is None:
                errors.append(f"{path}: locator: unrecognized shape: {entry['locator']!r}")
            elif index is not None:
                # Shape already confirmed above; only the deeper resolution-through-index
                # step depends on `index` being available (D37 — unresolved-but-well-shaped
                # is a sourcing-queue matter, never a CI failure).
                validate_locator(entry["locator"], entry["source"], index)
    return (1 if errors else 0), errors


def _postgres_index():
    """Soft-imports 1C's ingest package and connects; returns None (never raises) if
    either the package or a live Postgres isn't available — CI degrades to
    phase-1-only locator-shape checking in that case, matching precommit's own
    no-auto-upgrade posture (D48)."""
    try:
        from langatlas_ingest.db import connect
        from langatlas_ingest.index import PostgresSourceChunksIndex
    except ImportError:
        return None
    try:
        conn = connect()
        return PostgresSourceChunksIndex(conn)
    except Exception:
        return None


def cmd_ci() -> int:
    rc = _print_report(run_regression(_FIXTURES), verbose=True)

    from langatlas_validate.compile import derive_facts, check_fact_collisions
    from langatlas_validate.store import iter_store_records

    index = _postgres_index()
    store_rc, store_errors = cmd_ci_with_index(_REPO_ROOT, index)
    for e in store_errors:
        print(f"STORE {e}")

    facts = derive_facts(list(iter_store_records(_REPO_ROOT)))
    collision_errors = check_fact_collisions(facts)
    for e in collision_errors:
        print(f"COLLISION {e}")

    return rc or store_rc or (1 if collision_errors else 0)


def cmd_regression_run() -> int:
    return _print_report(run_regression(_FIXTURES), verbose=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="langatlas-validate")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command")

    p_pre = sub.add_parser("precommit")
    p_pre.add_argument("--kind", required=True, choices=RECORD_KINDS)
    p_pre.add_argument("files", nargs="+")

    p_pre_auto = sub.add_parser("precommit-auto")
    p_pre_auto.add_argument("files", nargs="+")

    sub.add_parser("ci")

    p_reg = sub.add_parser("regression")
    p_reg.add_argument("regression_command", choices=["run"])

    args = parser.parse_args(argv)
    if args.command == "precommit":
        return cmd_precommit(args.files, args.kind)
    if args.command == "precommit-auto":
        return cmd_precommit_auto(args.files)
    if args.command == "ci":
        return cmd_ci()
    if args.command == "regression":
        return cmd_regression_run()
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
