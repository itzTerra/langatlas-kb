"""Spec-path entry point (§7.7). The implementation lives in the pipeline package so it
shares the cost-log and config readers; this file exists so `tools/observability/report.py`
is a real, runnable path."""

from langatlas_pipeline.observability.report import main

if __name__ == "__main__":
    raise SystemExit(main())
