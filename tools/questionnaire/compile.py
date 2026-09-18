"""Spec-path entry point (§7.3 names `tools/questionnaire/compile.py` exactly). The
implementation lives in the package so the library and the CLI share one code path — the same
shim `tools/finding-aids/report.py` uses."""

from langatlas_questionnaire.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
