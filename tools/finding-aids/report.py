"""Spec-path entry point (§4.5 names `tools/finding-aids/report.py` exactly). The
implementation lives in the package so the library and the CLI share one code path —
same shim `tools/observability/report.py` already uses."""

from langatlas_finding_aids.report import main

if __name__ == "__main__":
    raise SystemExit(main())
