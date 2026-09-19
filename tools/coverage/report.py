"""Spec-path entry point (§10.4 names `tools/coverage/report.py` exactly). The implementation
lives in the package so the library and the CLI share one code path — the same shim
`tools/observability/report.py` and `tools/finding-aids/report.py` use."""

from langatlas_coverage.report import main

if __name__ == "__main__":
    raise SystemExit(main())
