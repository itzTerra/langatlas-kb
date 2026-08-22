import pytest
from langatlas_orchestrator import registry as registry_module


@pytest.fixture(autouse=True)
def _isolated_registry(monkeypatch):
    """Every test gets a private copy of the module-level registry dict so tests can
    register throwaway job kinds without leaking into each other or into the real
    built-in kinds registered by `jobs/__init__.py`."""
    monkeypatch.setattr(registry_module, "_REGISTRY", dict(registry_module._REGISTRY))
