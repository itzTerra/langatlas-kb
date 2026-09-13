import subprocess

import pytest

from langatlas_research.paths import REPO_ROOT, ensure_layout


def _git(args, cwd):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True)


@pytest.fixture
def store_repo(tmp_path):
    """A throwaway origin + clone carrying just enough canonical store to validate.

    `core.hooksPath` is pointed at an empty directory so this machine's global pre-commit
    hook does not reject the commits `land_record` makes from a subprocess."""
    origin = tmp_path / "origin.git"
    clone = tmp_path / "clone"
    hooks = tmp_path / "no-hooks"
    hooks.mkdir()
    _git(["init", "--bare", "-b", "main", str(origin)], tmp_path)
    _git(["clone", str(origin), str(clone)], tmp_path)
    for key, value in (("user.email", "bot@example.com"), ("user.name", "bot"),
                       ("core.hooksPath", str(hooks)), ("commit.gpgsign", "false")):
        _git(["config", key, value], clone)

    for directory in ("concepts", "features", "edges", "rules", "sources",
                      "ontology/taxonomy", "languages"):
        (clone / directory).mkdir(parents=True, exist_ok=True)
        (clone / directory / ".gitkeep").touch()
    for rel in ("ontology/taxonomy/dimensions.yaml", "ontology/taxonomy/qualities.yaml",
                "ontology/taxonomy/layers.yaml", "ontology/taxonomy/edge-types.yaml",
                "languages/_registry.yaml"):
        (clone / rel).write_text((REPO_ROOT / rel).read_text())
    (clone / "contradictions.yaml").write_text("contradictions: []\n")
    (clone / "ontology").mkdir(exist_ok=True)
    (clone / "ontology" / "VERSION").write_text((REPO_ROOT / "ontology" / "VERSION").read_text())
    (clone / "ontology" / "CHANGELOG.md").write_text("# Ontology changelog\n")

    ensure_layout(clone)
    for schema in (REPO_ROOT / "research" / "schema").glob("*.schema.json"):
        (clone / "research" / "schema" / schema.name).write_text(schema.read_text())
    (clone / "research" / "themes.yaml").write_text(
        (REPO_ROOT / "research" / "themes.yaml").read_text())

    _git(["add", "-A"], clone)
    _git(["commit", "-q", "-m", "seed"], clone)
    _git(["push", "-q", "origin", "HEAD:main"], clone)
    return clone


from langatlas_pipeline.injection import delimit_untrusted


class _Writer:
    def __init__(self, events):
        self._events = events

    def append(self, **event):
        self._events.append(event)


class FakeCtx:
    """Stands in for `RunContext` without a provider, a transcript repo or a cost log.

    `tool_result` really delimits, so a test can assert D31 held; `complete` and
    `claude_run` pop scripted responders so a test states exactly what the model said."""

    def __init__(self, run_id="2026-09-20-r3-test-unit-01"):
        self.run_id = run_id
        self.events: list[dict] = []
        self.writer = _Writer(self.events)
        self.completions: list = []      # callables (alias, messages, schema) -> Completion-like
        self.complete_calls: list[dict] = []
        self.claude_results: list = []   # AgentRunResult instances, popped in order
        self.claude_calls: list = []
        self.tool_results: list[dict] = []

    def tool_result(self, *, tool, text, source_id=None, kind="source-chunk"):
        self.tool_results.append({"tool": tool, "text": text, "source_id": source_id,
                                  "kind": kind})
        return delimit_untrusted(text, source_id=source_id, kind=kind)

    def complete(self, alias, messages, *, prompt, schema=None, sampling=None):
        self.complete_calls.append({"alias": alias, "messages": messages,
                                    "prompt": prompt.ref(), "schema": schema})
        return self.completions.pop(0)(alias, messages, schema)

    def claude_run(self, prompt, *, options):
        self.claude_calls.append((prompt, options))
        return self.claude_results.pop(0)


@pytest.fixture
def fake_ctx():
    return FakeCtx()


@pytest.fixture
def private_dir(tmp_path, monkeypatch):
    """Every test writes pools and tags into a throwaway private tier."""
    root = tmp_path / "private"
    root.mkdir()
    monkeypatch.setattr("langatlas_pipeline.paths.PRIVATE_DIR", root)
    return root


from langatlas_research.cycle import new_cycle, sign_off
from langatlas_research.paths import themes_path


@pytest.fixture
def research_repo(tmp_path):
    """A research/ tree with the real schemas and theme list, no git."""
    repo = tmp_path / "repo"
    ensure_layout(repo)
    for schema in (REPO_ROOT / "research" / "schema").glob("*.schema.json"):
        (repo / "research" / "schema" / schema.name).write_text(schema.read_text())
    themes_path(repo).write_text(themes_path(REPO_ROOT).read_text())
    (repo / "config").mkdir()
    (repo / "config" / "research.yaml").write_text(
        (REPO_ROOT / "config" / "research.yaml").read_text())
    return repo


@pytest.fixture
def signed_cycle(research_repo):
    cycle = new_cycle(1, "typing", repo_root=research_repo, languages=("python", "haskell"))
    return sign_off(cycle, by="Michal Dolezel", date="2026-09-20", repo_root=research_repo)
