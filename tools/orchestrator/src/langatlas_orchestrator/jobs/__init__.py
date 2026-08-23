"""Importing this package registers every built-in job kind (D43's periodic-job
inventory) as a side effect. `driver.main()` imports this once before dispatching;
tests import individual `jobs/*` submodules directly and rely on the same import."""
from langatlas_orchestrator.jobs import capability_probe  # noqa: F401
from langatlas_orchestrator.jobs import deferred  # noqa: F401
from langatlas_orchestrator.jobs import exit_test  # noqa: F401
