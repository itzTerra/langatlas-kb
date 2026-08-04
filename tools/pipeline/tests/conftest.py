import pytest
from pathlib import Path
from langatlas_pipeline.config import ProviderConfig
from langatlas_pipeline.providers.core import Budget, RunContext


@pytest.fixture
def workspace(tmp_path: Path) -> dict:
    """An isolated private tier + transcripts root, so no test touches real state."""
    private = tmp_path / "private"
    transcripts = tmp_path / "transcripts"
    private.mkdir()
    transcripts.mkdir()
    return {"private": private, "transcripts": transcripts}


@pytest.fixture
def ctx(workspace) -> RunContext:
    run = RunContext.start(
        kind="verification", slug="unit", budget=Budget(max_calls=10, max_total_tokens=1000),
        config=ProviderConfig.load(), transcripts_root=workspace["transcripts"],
        private_dir=workspace["private"],
    )
    yield run
    if not run.closed:
        run.close()
