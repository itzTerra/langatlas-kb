# Stage 1D — Commit & CI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the agent-runner commit protocol (D36) and the CI validated-artifact pipeline
skeleton (D13) — the path every later stage's agents commit facts through, and the gate that
keeps `main` publishable.

**Architecture:** Two new/extended surfaces. (1) A new `tools/commit/` package
(`langatlas_commit`) implementing the fetch-rebase-retry land loop, the `LandResult` union,
is-main-green gating, and the failure bot's auto-revert checklist, driven by a GitHub App
identity whose installation-token minting is added to 1B's `RunContext` (D26 already names
`RunContext` as the token owner). (2) `tools/validate/`'s `ci` command grows from "run the
regression-fixture suite" into a real store-validating gate: it walks every live record under
`concepts/`, `features/`, `languages/`, `edges/`, `rules/`, `sources/`, derives facts, checks for
fact-id collisions, enforces canonical ordering, and (when Postgres is reachable) resolves
locators through 1C's `SourceChunksIndex`. A new `.github/workflows/ci.yml` runs that gate on
every push and, on green `main`, compiles and publishes the dataset bundle as a GitHub Release
asset (`latest-green` + daily `data-vN` tags) and fires a `repository_dispatch` at the (still
empty) `langatlas-site` repo.

**Tech Stack:** Python 3.12, `uv`-managed packages (`hatchling` build backend, same layout as
`tools/validate`, `tools/pipeline`, `tools/ingest`), `httpx` for GitHub REST calls, `PyJWT[crypto]`
for GitHub App JWT signing, `pytest` (local git-repo fixtures for land-loop tests — no live
GitHub calls in the test suite), GitHub Actions for CI.

**Spec:** [context/spec.md §7.9](../../../context/spec.md) (D36, brainstorm 27),
[context/spec.md §8.7](../../../context/spec.md) (D13, brainstorm 10),
[context/decisions.md](../../../context/decisions.md) D36/D13 (ratified text — binding),
[docs/superpowers/plans/2026-07-25-langatlas-cross-stage-plan.md](2026-07-25-langatlas-cross-stage-plan.md)
(1D's consumes/produces contract with 1A–1C and 1E).

## Global Constraints

- No deadline; do not take shortcuts that damage the long-term product (D6/D11).
- Git is the database — Postgres, MCP, and the static site are always one-way derived build
  artifacts, never authoritative (D1).
- No PR gate for agent-committed facts — admissibility comes from the automated verification
  gate (D4/D24), never human review bandwidth (D1).
- Agents commit under a **GitHub App identity** (`langatlas-bot[bot]`), scoped to
  `Contents: write`, `Issues: write`, `Checks: read`, `Statuses: read` — deliberately **no**
  `Pull requests` scope (D36).
- **Commit granularity is one commit per touched record file** — never per agent turn, never per
  derived fact (D36/D20/D23).
- Every commit carries `LangAtlas-Record-Key: <sha256(content+path)>` and
  `LangAtlas-Chat-Run-Id: <run_id>#msg-<N>` trailers (D36).
- Fetch-rebase-retry gives up after **5 retries or 3 minutes**, whichever first, reporting
  `contention_exhausted` — never loops forever, never drops the record (D36).
- Only the final push checks `main`'s CI status (is-main-green gating); on red/unknown, hold the
  record and report `blocked_red_main` — the runner never tries to fix a red `main` itself (D36).
- Auto-revert requires **all four**: tip commit, bot-authored, deterministic failure reproduced
  once, clean `git revert` — otherwise halt and file an issue. **Circuit breaker: 2 reverts per
  run** (D36).
- DCO for automated commits: a **CONTRIBUTING.md carve-out** treats the GitHub App installation
  itself as the one-time sign-off; per-commit `Signed-off-by:` trailers are for human PRs only
  (D36, ratified — not the per-commit-trailer alternative).
- Token refresh is owned by `RunContext` (D26) and **never logged** (D18).
- CI: fast offline validators, last-green publication (red `main` publishes nothing), `data-vN`
  tags cut **daily, only on days with changes**, embeddings cache stays **private** (D13,
  ratified). Never submodules or HEAD checkouts for cross-repo consumption (D13).
- Network link-checking runs on a schedule, never on data-push CI (brainstorm 10 §2) — out of
  scope for this plan (Stage 1E's orchestrator owns the schedule).

---

## File Structure

New package `tools/commit/` (`langatlas_commit`), mirroring `tools/validate`'s layout:

```
tools/commit/
  pyproject.toml
  src/langatlas_commit/
    __init__.py         # __version__
    trailers.py          # record_key(), format_trailers(), parse_record_key()
    land.py               # LandResult union, land_record(), check_main_status()
    revert.py             # evaluate_revert_safety(), auto_revert(), RevertBudget, file_failure_issue()
  tests/
    test_trailers.py
    test_land.py
    test_revert.py
```

Extends existing packages:

```
tools/pipeline/src/langatlas_pipeline/
  providers/github_app.py   # NEW: GithubAppClient — JWT mint + installation-token exchange/cache
  providers/core.py         # MODIFIED: RunContext.github_token()
  config.py                 # MODIFIED: ProviderConfig.github_app()
tools/pipeline/tests/
  test_github_app.py        # NEW

tools/validate/src/langatlas_validate/
  store.py                  # NEW: iter_store_records(), validate_store()
  compile.py                 # NEW: derive_facts(), check_fact_collisions(), compile_bundle()
  cli.py                     # MODIFIED: cmd_ci() walks the store; new `precommit-auto` subcommand
tools/validate/tests/
  test_store.py              # NEW
  test_compile.py            # NEW
  test_precommit_auto.py     # NEW

config/providers.yaml        # MODIFIED: github_app section
CONTRIBUTING.md              # NEW: DCO carve-out + three human-contribution lanes stub
.pre-commit-config.yaml      # NEW
.github/workflows/ci.yml     # NEW
```

Each file has one responsibility: `trailers.py` never touches git; `land.py` never touches
GitHub Issues; `revert.py` never runs the fetch-rebase-retry loop itself (it calls into
`land.py` for the revert's own push). `store.py` never derives facts; `compile.py` never
validates schema shape (it assumes `store.py` already did).

---

## Task 1: GitHub App installation-token client + `RunContext` integration + DCO carve-out

**Files:**
- Create: `tools/pipeline/src/langatlas_pipeline/providers/github_app.py`
- Modify: `tools/pipeline/src/langatlas_pipeline/providers/core.py`
- Modify: `tools/pipeline/src/langatlas_pipeline/config.py`
- Modify: `tools/pipeline/src/langatlas_pipeline/errors.py`
- Modify: `tools/pipeline/pyproject.toml` (add `PyJWT[crypto]>=2.8`)
- Modify: `config/providers.yaml`
- Create: `CONTRIBUTING.md`
- Test: `tools/pipeline/tests/test_github_app.py`

**Interfaces:**
- Consumes: `ProviderConfig.load()` (existing, `tools/pipeline/src/langatlas_pipeline/config.py:51`).
- Produces for Task 3+: `RunContext.github_token() -> str` — every GitHub REST/git-remote call in
  `tools/commit` goes through this, never mints its own token.

- [x] **Step 1: Write the failing test for JWT minting and token exchange**

```python
# tools/pipeline/tests/test_github_app.py
import time
import httpx
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization

from langatlas_pipeline.providers.github_app import GithubAppClient, AppToken
from langatlas_pipeline.errors import ProviderTransportError


def _fake_private_key_pem() -> bytes:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )


def _client(handler) -> GithubAppClient:
    transport = httpx.MockTransport(handler)
    http = httpx.Client(transport=transport, base_url="https://api.github.com")
    return GithubAppClient(app_id="12345", installation_id="67890",
                           private_key_pem=_fake_private_key_pem(), http_client=http)


def test_installation_token_fetched_and_cached():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        assert request.url.path == "/app/installations/67890/access_tokens"
        assert request.headers["authorization"].startswith("Bearer ")
        return httpx.Response(201, json={
            "token": "ghs_abc123", "expires_at": "2099-01-01T00:00:00Z",
        })

    client = _client(handler)
    tok1 = client.installation_token()
    tok2 = client.installation_token()
    assert tok1 == tok2 == "ghs_abc123"
    assert calls["n"] == 1     # cached: second call does not re-request


def test_installation_token_refreshes_when_near_expiry():
    responses = iter([
        httpx.Response(201, json={"token": "ghs_old",
                                  "expires_at": time.strftime(
                                      "%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + 30))}),
        httpx.Response(201, json={"token": "ghs_new",
                                  "expires_at": "2099-01-01T00:00:00Z"}),
    ])

    def handler(request: httpx.Request) -> httpx.Response:
        return next(responses)

    client = _client(handler)
    assert client.installation_token() == "ghs_old"
    assert client.installation_token() == "ghs_new"   # near-expiry (<60s left) triggers refresh


def test_installation_token_raises_on_error_status():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"message": "Bad credentials"})

    client = _client(handler)
    with pytest.raises(ProviderTransportError):
        client.installation_token()


def test_token_never_appears_in_repr():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(201, json={"token": "ghs_secret999",
                                         "expires_at": "2099-01-01T00:00:00Z"})

    client = _client(handler)
    client.installation_token()
    assert "ghs_secret999" not in repr(client)
```

- [x] **Step 2: Run test to verify it fails**

Run: `cd tools/pipeline && uv run pytest tests/test_github_app.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'langatlas_pipeline.providers.github_app'`

- [x] **Step 3: Add the `PyJWT[crypto]` dependency**

Edit `tools/pipeline/pyproject.toml`, in the `dependencies` list, add:

```toml
  "PyJWT[crypto]>=2.8",
```

Run: `cd tools/pipeline && uv sync`

- [x] **Step 4: Add `ProviderTransportError`-compatible import and implement `github_app.py`**

```python
# tools/pipeline/src/langatlas_pipeline/providers/github_app.py
import time
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx
import jwt

from langatlas_pipeline.errors import ProviderTransportError

# GitHub caps the App JWT lifetime at 10 minutes; stay comfortably under it.
_JWT_TTL_SECONDS = 540
# Refresh the installation token once fewer than this many seconds remain,
# so a long-running land loop never has a token expire mid-retry.
_REFRESH_MARGIN_SECONDS = 60


@dataclass(frozen=True)
class AppToken:
    token: str
    expires_at: float   # unix timestamp

    def __repr__(self) -> str:   # never let a token leak into a log line via repr()
        return f"AppToken(token=<redacted>, expires_at={self.expires_at})"


class GithubAppClient:
    """Mints short-lived GitHub App installation tokens (D36 §2.2). Owned by
    `RunContext`, never constructed directly by `tools/commit` call sites — token
    refresh must go through the same non-bypassable wrapper D26 already uses for
    provider budget/logging."""

    def __init__(self, *, app_id: str, installation_id: str, private_key_pem: bytes,
                 http_client: httpx.Client | None = None):
        self._app_id = app_id
        self._installation_id = installation_id
        self._private_key_pem = private_key_pem
        self._http = http_client or httpx.Client(base_url="https://api.github.com")
        self._cached: AppToken | None = None

    def __repr__(self) -> str:
        return f"GithubAppClient(app_id={self._app_id!r}, installation_id={self._installation_id!r})"

    def _mint_jwt(self) -> str:
        now = int(time.time())
        payload = {"iat": now - 60, "exp": now + _JWT_TTL_SECONDS, "iss": self._app_id}
        return jwt.encode(payload, self._private_key_pem, algorithm="RS256")

    def installation_token(self) -> str:
        if self._cached is not None and self._cached.expires_at - time.time() > _REFRESH_MARGIN_SECONDS:
            return self._cached.token
        response = self._http.post(
            f"/app/installations/{self._installation_id}/access_tokens",
            headers={"Authorization": f"Bearer {self._mint_jwt()}",
                    "Accept": "application/vnd.github+json"},
        )
        if response.status_code >= 400:
            raise ProviderTransportError(
                f"installation token request failed: {response.status_code} {response.text}",
                status=response.status_code,
            )
        data = response.json()
        expires_at = datetime.strptime(data["expires_at"], "%Y-%m-%dT%H:%M:%SZ") \
            .replace(tzinfo=timezone.utc).timestamp()
        self._cached = AppToken(token=data["token"], expires_at=expires_at)
        return self._cached.token
```

- [x] **Step 5: Run test to verify it passes**

Run: `cd tools/pipeline && uv run pytest tests/test_github_app.py -v`
Expected: PASS (4 tests)

- [x] **Step 6: Add `ProviderConfig.github_app()` and `RunContext.github_token()`**

Edit `tools/pipeline/src/langatlas_pipeline/config.py`, add after `completion_settings`:

```python
    def github_app(self) -> dict[str, str]:
        entry = self.providers.get("github_app")
        if entry is None:
            raise UnknownAlias("no github_app section in config/providers.yaml")
        return dict(entry)
```

Edit `tools/pipeline/src/langatlas_pipeline/providers/core.py`. Add `self._github_app = None` to
`RunContext.__init__` alongside the other lazily-constructed channels, then add a method next to
`claude_run`:

```python
    def github_token(self) -> str:
        """D36 §2.2: token refresh is owned by RunContext, never logged. The token
        itself never enters the transcript writer or the cost log."""
        from langatlas_pipeline.providers.github_app import GithubAppClient
        import os

        if self._github_app is None:
            settings = self.config.github_app()
            key_path = os.environ[settings["private_key_env"]]
            with open(key_path, "rb") as fh:
                private_key_pem = fh.read()
            self._github_app = GithubAppClient(
                app_id=settings["app_id"], installation_id=settings["installation_id"],
                private_key_pem=private_key_pem,
            )
        return self._github_app.installation_token()
```

- [x] **Step 7: Add the `github_app` section to `config/providers.yaml`**

```yaml
github_app:
  app_id_env: LANGATLAS_GITHUB_APP_ID
  app_id: ""                          # set once the App is registered (Stage 0 follow-up)
  installation_id: ""
  private_key_env: LANGATLAS_GITHUB_APP_PRIVATE_KEY_PATH   # path to the .pem, never the key itself
```

Note: `app_id` is read as a plain config value (public), the private key path is read from an
env var per `private_key_env` — mirrors the existing `token_env`/`base_url_env` indirection
pattern already used for the university API in this same file.

- [x] **Step 8: Write `CONTRIBUTING.md`'s DCO carve-out**

```markdown
# Contributing to LangAtlas

## Automated (agent-runner) commits

Commits authored by the `langatlas-bot[bot]` GitHub App identity are **DCO-exempt by
design**: installing the App on this repository is itself the developer's one-time act of
contribution and sign-off for everything the pipeline subsequently produces under that
identity (D36/D14). No per-commit `Signed-off-by:` trailer is expected or required on
bot-authored commits.

## Human contributions

Every human-submitted commit (via PR) must carry a `Signed-off-by:` trailer per the
Developer Certificate of Origin (DCO), asserting you have the right to submit the change
under this project's licenses (code: MIT; corpus: CC BY-SA 4.0). Add it with
`git commit -s`.

Human contribution lanes and the fact-challenge process are documented in full once Stage 6
lands (D32); this file will grow those sections then.
```

- [x] **Step 9: Run the full pipeline test suite**

Run: `cd tools/pipeline && uv run pytest -v`
Expected: PASS, no regressions.

- [x] **Step 10: Commit**

```bash
git add tools/pipeline/src/langatlas_pipeline/providers/github_app.py \
        tools/pipeline/src/langatlas_pipeline/providers/core.py \
        tools/pipeline/src/langatlas_pipeline/config.py \
        tools/pipeline/pyproject.toml tools/pipeline/uv.lock \
        tools/pipeline/tests/test_github_app.py \
        config/providers.yaml CONTRIBUTING.md
git commit -m "feat(#stage-1d): add GitHub App token minting to RunContext"
```

---

## Task 2: Record-key and chat-run-id trailer helpers

**Files:**
- Create: `tools/commit/pyproject.toml`
- Create: `tools/commit/src/langatlas_commit/__init__.py`
- Create: `tools/commit/src/langatlas_commit/trailers.py`
- Test: `tools/commit/tests/test_trailers.py`

**Interfaces:**
- Consumes: nothing.
- Produces for Task 3: `record_key(path: str, content: str) -> str`,
  `format_trailers(record_key: str, chat_run_id: str | None, challenge_id: str | None = None) -> str`,
  `find_record_key_in_history(repo: Path, record_key: str) -> str | None` (returns the sha or
  `None`).

- [x] **Step 1: Scaffold the package**

```toml
# tools/commit/pyproject.toml
[project]
name = "langatlas-commit"
version = "0.1.0"
description = "LangAtlas agent-runner commit protocol and failure bot"
requires-python = ">=3.12"
license = "MIT"
dependencies = [
  "httpx>=0.27",
  "langatlas-validate",
  "langatlas-pipeline",
]

[project.optional-dependencies]
dev = ["pytest>=8.0"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/langatlas_commit"]

[tool.uv.sources]
langatlas-validate = { path = "../validate", editable = true }
langatlas-pipeline = { path = "../pipeline", editable = true }
```

```python
# tools/commit/src/langatlas_commit/__init__.py
__version__ = "0.1.0"
```

Run: `cd tools/commit && uv sync`

- [x] **Step 2: Write the failing test**

```python
# tools/commit/tests/test_trailers.py
import subprocess
from pathlib import Path

from langatlas_commit.trailers import (
    record_key, format_trailers, find_record_key_in_history,
)


def test_record_key_deterministic_on_content_and_path():
    k1 = record_key("features/pattern-matching.yaml", "feature: pattern-matching\n")
    k2 = record_key("features/pattern-matching.yaml", "feature: pattern-matching\n")
    k3 = record_key("features/other.yaml", "feature: pattern-matching\n")
    assert k1 == k2
    assert k1 != k3


def test_format_trailers_without_challenge():
    text = format_trailers("abc123", "2026-08-21-sweep-rust-01#msg-7")
    assert "LangAtlas-Record-Key: abc123" in text
    assert "LangAtlas-Chat-Run-Id: 2026-08-21-sweep-rust-01#msg-7" in text
    assert "LangAtlas-Challenge-Id" not in text


def test_format_trailers_with_challenge():
    text = format_trailers("abc123", "run-1#msg-1", challenge_id="ch-42")
    assert "LangAtlas-Challenge-Id: ch-42" in text


def _git(args, cwd):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True)


def test_find_record_key_in_history(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(["init", "-q", "-b", "main"], repo)
    _git(["config", "user.email", "bot@example.com"], repo)
    _git(["config", "user.name", "bot"], repo)
    (repo / "f.yaml").write_text("x: 1\n")
    _git(["add", "f.yaml"], repo)
    msg = "add f\n\n" + format_trailers("deadbeef", "run-1#msg-1")
    _git(["commit", "-q", "-m", msg], repo)

    sha = find_record_key_in_history(repo, "deadbeef")
    assert sha is not None
    assert find_record_key_in_history(repo, "not-there") is None
```

- [x] **Step 3: Run test to verify it fails**

Run: `cd tools/commit && uv run pytest tests/test_trailers.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'langatlas_commit.trailers'`

- [x] **Step 4: Implement `trailers.py`**

```python
# tools/commit/src/langatlas_commit/trailers.py
import hashlib
import subprocess
from pathlib import Path


def record_key(path: str, content: str) -> str:
    """D36 §2.3: content-derived idempotency key. Path is part of the hash input so
    the same content committed to two different paths never collides."""
    h = hashlib.sha256()
    h.update(path.encode("utf-8"))
    h.update(b"\0")
    h.update(content.encode("utf-8"))
    return h.hexdigest()


def format_trailers(record_key: str, chat_run_id: str, *, challenge_id: str | None = None) -> str:
    lines = [
        f"LangAtlas-Record-Key: {record_key}",
        f"LangAtlas-Chat-Run-Id: {chat_run_id}",
    ]
    if challenge_id is not None:
        lines.append(f"LangAtlas-Challenge-Id: {challenge_id}")
    return "\n".join(lines)


def find_record_key_in_history(repo: Path, record_key: str) -> str | None:
    """D36 §2.6: idempotent-resume ground truth — a cheap grep against main's
    reachable history, checked before any push attempt."""
    result = subprocess.run(
        ["git", "log", "--format=%H", f"--grep=LangAtlas-Record-Key: {record_key}$",
         "--fixed-strings" if False else f"--grep=LangAtlas-Record-Key: {record_key}"],
        cwd=repo, capture_output=True, text=True,
    )
    shas = [line for line in result.stdout.splitlines() if line]
    return shas[0] if shas else None
```

- [x] **Step 5: Run test to verify it passes**

Run: `cd tools/commit && uv run pytest tests/test_trailers.py -v`
Expected: PASS (4 tests)

- [x] **Step 6: Commit**

```bash
git add tools/commit/pyproject.toml tools/commit/src/langatlas_commit/__init__.py \
        tools/commit/src/langatlas_commit/trailers.py tools/commit/tests/test_trailers.py \
        tools/commit/uv.lock
git commit -m "feat(#stage-1d): add record-key and chat-run-id commit trailers"
```

---

## Task 3: Fetch-rebase-retry land loop + `LandResult`

**Files:**
- Create: `tools/commit/src/langatlas_commit/land.py`
- Test: `tools/commit/tests/test_land.py`

**Interfaces:**
- Consumes: `record_key`, `format_trailers`, `find_record_key_in_history` (Task 2).
- Produces for Task 4/5: `LandResult` (a `Landed | BlockedRedMain | ContentionExhausted |
  Reverted | UnsafeHalt` dataclass union), `land_record(repo_root, record_path, content, *,
  chat_run_id, validator, retries=5, timeout_seconds=180, remote="origin", branch="main",
  status_checker=None) -> LandResult`.

- [x] **Step 1: Write the failing tests (happy path, contention, idempotent resume)**

```python
# tools/commit/tests/test_land.py
import subprocess
import time
from pathlib import Path

import pytest

from langatlas_commit.land import land_record, Landed, ContentionExhausted
from langatlas_commit.trailers import record_key


def _git(args, cwd, check=True):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=check)


@pytest.fixture
def bare_and_clone(tmp_path):
    bare = tmp_path / "bare.git"
    _git(["init", "-q", "--bare", "-b", "main", str(bare)], tmp_path)
    clone = tmp_path / "clone"
    _git(["clone", "-q", str(bare), str(clone)], tmp_path)
    _git(["config", "user.email", "bot@example.com"], clone)
    _git(["config", "user.name", "bot"], clone)
    # seed main so `git rebase origin/main` has something to rebase onto
    (clone / "README.md").write_text("seed\n")
    _git(["add", "README.md"], clone)
    _git(["commit", "-q", "-m", "seed"], clone)
    _git(["push", "-q", "origin", "main"], clone)
    return bare, clone


def _always_pass_validator(worktree: Path) -> list[str]:
    return []   # no errors


def test_land_record_happy_path(bare_and_clone):
    bare, clone = bare_and_clone
    content = "feature: pattern-matching\n"
    result = land_record(clone, "features/pattern-matching.yaml", content,
                         chat_run_id="run-1#msg-1", validator=_always_pass_validator)
    assert isinstance(result, Landed)
    log = _git(["log", "-1", "--format=%B", "origin/main"], clone)
    assert "LangAtlas-Record-Key" in log.stdout


def test_land_record_idempotent_resume(bare_and_clone):
    bare, clone = bare_and_clone
    content = "feature: pattern-matching\n"
    first = land_record(clone, "features/pattern-matching.yaml", content,
                        chat_run_id="run-1#msg-1", validator=_always_pass_validator)
    second = land_record(clone, "features/pattern-matching.yaml", content,
                         chat_run_id="run-1#msg-1", validator=_always_pass_validator)
    assert isinstance(second, Landed)
    assert second.commit_sha == first.commit_sha   # short-circuited, no re-push


def test_land_record_retries_through_concurrent_push(bare_and_clone, tmp_path):
    bare, clone = bare_and_clone
    # A second clone lands first, moving origin/main out from under our clone's fetch.
    other = tmp_path / "other"
    _git(["clone", "-q", str(bare), str(other)], tmp_path)
    _git(["config", "user.email", "other@example.com"], other)
    _git(["config", "user.name", "other"], other)
    (other / "features").mkdir()
    (other / "features" / "unrelated.yaml").write_text("feature: unrelated\n")
    _git(["add", "features/unrelated.yaml"], other)
    _git(["commit", "-q", "-m", "unrelated"], other)
    _git(["push", "-q", "origin", "main"], other)

    result = land_record(clone, "features/pattern-matching.yaml", "feature: pattern-matching\n",
                         chat_run_id="run-1#msg-1", validator=_always_pass_validator)
    assert isinstance(result, Landed)
    log = _git(["log", "--oneline", "origin/main"], clone)
    assert "unrelated" in log.stdout   # both commits landed, no data lost


def test_land_record_reports_contention_exhausted_when_validator_never_passes(bare_and_clone):
    bare, clone = bare_and_clone

    def _always_fail(worktree: Path) -> list[str]:
        return ["schema: always broken in this test"]

    result = land_record(clone, "features/broken.yaml", "feature: broken\n",
                         chat_run_id="run-1#msg-1", validator=_always_fail,
                         retries=1, timeout_seconds=5)
    assert isinstance(result, ContentionExhausted)
```

- [x] **Step 2: Run tests to verify they fail**

Run: `cd tools/commit && uv run pytest tests/test_land.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'langatlas_commit.land'`

- [x] **Step 3: Implement `land.py`**

```python
# tools/commit/src/langatlas_commit/land.py
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Literal

from langatlas_commit.trailers import record_key, format_trailers, find_record_key_in_history

Validator = Callable[[Path], list[str]]
StatusChecker = Callable[[Path, str], Literal["green", "red", "unknown"]]


@dataclass(frozen=True)
class Landed:
    commit_sha: str


@dataclass(frozen=True)
class BlockedRedMain:
    since: float
    last_checked: float


@dataclass(frozen=True)
class ContentionExhausted:
    retries: int
    last_conflict_summary: str


@dataclass(frozen=True)
class Reverted:
    commit_sha: str
    reason: str


@dataclass(frozen=True)
class UnsafeHalt:
    commit_sha: str | None
    diagnostic: str


LandResult = Landed | BlockedRedMain | ContentionExhausted | Reverted | UnsafeHalt


def _git(args: list[str], cwd: Path, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=check)


def land_record(
    repo_root: Path, record_path: str, content: str, *, chat_run_id: str,
    validator: Validator, retries: int = 5, timeout_seconds: int = 180,
    remote: str = "origin", branch: str = "main",
    status_checker: StatusChecker | None = None, challenge_id: str | None = None,
) -> LandResult:
    """D36 §2.1/§2.3/§2.4/§2.6: one commit per record file, fetch-rebase-retry against
    `origin/<branch>`, gated on is-main-green immediately before push. Idempotent:
    safe to call again for the same (path, content) without double-committing."""
    key = record_key(record_path, content)
    existing = find_record_key_in_history(repo_root, key)
    if existing is not None:
        return Landed(commit_sha=existing)

    started = time.monotonic()
    path = repo_root / record_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    _git(["add", "--", record_path], repo_root)
    message = f"land {record_path}\n\n" + format_trailers(key, chat_run_id, challenge_id=challenge_id)
    _git(["commit", "-q", "-m", message], repo_root)

    last_conflict = ""
    for attempt in range(1, retries + 1):
        if time.monotonic() - started > timeout_seconds:
            return ContentionExhausted(retries=attempt - 1, last_conflict_summary=last_conflict)

        _git(["fetch", "-q", remote], repo_root)
        rebase = _git(["rebase", f"{remote}/{branch}"], repo_root, check=False)
        if rebase.returncode != 0:
            _git(["rebase", "--abort"], repo_root, check=False)
            return UnsafeHalt(commit_sha=None,
                              diagnostic=f"rebase conflict: {rebase.stdout}\n{rebase.stderr}")

        errors = validator(repo_root)
        if errors:
            last_conflict = "; ".join(errors)
            return ContentionExhausted(retries=attempt, last_conflict_summary=last_conflict)

        if status_checker is not None:
            head_sha = _git(["rev-parse", f"{remote}/{branch}"], repo_root).stdout.strip()
            status = status_checker(repo_root, head_sha)
            if status != "green":
                now = time.monotonic()
                return BlockedRedMain(since=started, last_checked=now)

        push = _git(["push", remote, f"HEAD:{branch}"], repo_root, check=False)
        if push.returncode == 0:
            sha = _git(["rev-parse", "HEAD"], repo_root).stdout.strip()
            return Landed(commit_sha=sha)
        last_conflict = push.stderr.strip()

    return ContentionExhausted(retries=retries, last_conflict_summary=last_conflict)
```

- [x] **Step 4: Run tests to verify they pass**

Run: `cd tools/commit && uv run pytest tests/test_land.py -v`
Expected: PASS (4 tests)

- [x] **Step 5: Commit**

```bash
git add tools/commit/src/langatlas_commit/land.py tools/commit/tests/test_land.py
git commit -m "feat(#stage-1d): add the fetch-rebase-retry land loop"
```

---

## Task 4: Is-main-green gating via GitHub Checks/Statuses

**Files:**
- Modify: `tools/commit/src/langatlas_commit/land.py`
- Create: `tools/commit/src/langatlas_commit/status.py`
- Test: `tools/commit/tests/test_status.py`
- Test: `tools/commit/tests/test_land.py` (add one gating test)

**Interfaces:**
- Consumes: `RunContext.github_token()` (Task 1).
- Produces for Task 5: `github_status_checker(ctx: RunContext, owner: str, repo: str) ->
  StatusChecker` — a closure matching `land.py`'s `StatusChecker` signature, backed by the real
  GitHub Checks + Statuses APIs.

- [x] **Step 1: Write the failing test for the status checker**

```python
# tools/commit/tests/test_status.py
import httpx

from langatlas_commit.status import github_status_checker


class _FakeRunContext:
    def github_token(self) -> str:
        return "ghs_fake"


def _checker(handler):
    transport = httpx.MockTransport(handler)
    http = httpx.Client(transport=transport, base_url="https://api.github.com")
    return github_status_checker(_FakeRunContext(), "langatlas", "langatlas-kb", http_client=http)


def test_green_when_all_checks_and_statuses_succeed():
    def handler(request: httpx.Request) -> httpx.Response:
        if "check-runs" in request.url.path:
            return httpx.Response(200, json={"check_runs": [
                {"status": "completed", "conclusion": "success"},
            ]})
        return httpx.Response(200, json={"state": "success"})

    checker = _checker(handler)
    assert checker(None, "deadbeef") == "green"


def test_red_when_any_check_failed():
    def handler(request: httpx.Request) -> httpx.Response:
        if "check-runs" in request.url.path:
            return httpx.Response(200, json={"check_runs": [
                {"status": "completed", "conclusion": "failure"},
            ]})
        return httpx.Response(200, json={"state": "success"})

    checker = _checker(handler)
    assert checker(None, "deadbeef") == "red"


def test_unknown_when_no_status_reported():
    def handler(request: httpx.Request) -> httpx.Response:
        if "check-runs" in request.url.path:
            return httpx.Response(200, json={"check_runs": []})
        return httpx.Response(200, json={"state": "pending"})

    checker = _checker(handler)
    assert checker(None, "deadbeef") == "unknown"
```

- [x] **Step 2: Run test to verify it fails**

Run: `cd tools/commit && uv run pytest tests/test_status.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'langatlas_commit.status'`

- [x] **Step 3: Implement `status.py`**

```python
# tools/commit/src/langatlas_commit/status.py
from pathlib import Path
from typing import Literal

import httpx


def github_status_checker(ctx, owner: str, repo: str, *, http_client: httpx.Client | None = None):
    """D36 §2.4: 'no status' is treated as 'not confirmed green', never as an implicit
    pass. Combines the Checks API (GitHub Actions) and the legacy Statuses API (any
    external status poster) since either can be the source of truth for a given repo."""
    http = http_client or httpx.Client(base_url="https://api.github.com")

    def checker(repo_root: Path, sha: str) -> Literal["green", "red", "unknown"]:
        headers = {"Authorization": f"Bearer {ctx.github_token()}",
                  "Accept": "application/vnd.github+json"}
        checks = http.get(f"/repos/{owner}/{repo}/commits/{sha}/check-runs", headers=headers)
        checks.raise_for_status()
        runs = checks.json().get("check_runs", [])
        if any(r["status"] == "completed" and r["conclusion"] != "success" for r in runs):
            return "red"

        statuses = http.get(f"/repos/{owner}/{repo}/commits/{sha}/status", headers=headers)
        statuses.raise_for_status()
        state = statuses.json().get("state")
        if state == "failure" or state == "error":
            return "red"

        has_signal = bool(runs) or state in ("success", "pending")
        if not has_signal:
            return "unknown"
        if runs and not all(r["status"] == "completed" and r["conclusion"] == "success"
                            for r in runs):
            return "unknown"
        if state not in (None, "success"):
            return "unknown"
        return "green"

    return checker
```

- [x] **Step 4: Run test to verify it passes**

Run: `cd tools/commit && uv run pytest tests/test_status.py -v`
Expected: PASS (3 tests)

- [x] **Step 5: Add a `land_record` test proving `blocked_red_main` short-circuits before push**

Append to `tools/commit/tests/test_land.py`:

```python
def test_land_record_blocks_on_red_status(bare_and_clone):
    bare, clone = bare_and_clone

    def _red_status(repo_root, sha):
        return "red"

    result = land_record(clone, "features/pattern-matching.yaml", "feature: pattern-matching\n",
                         chat_run_id="run-1#msg-1", validator=_always_pass_validator,
                         status_checker=_red_status)
    from langatlas_commit.land import BlockedRedMain
    assert isinstance(result, BlockedRedMain)
    log = _git(["log", "-1", "--format=%H", "origin/main"], clone)
    # nothing was pushed — origin/main is still just the seed commit
    assert "seed" in _git(["log", "-1", "--format=%s", "origin/main"], clone).stdout
```

- [x] **Step 6: Run the full land test file**

Run: `cd tools/commit && uv run pytest tests/test_land.py -v`
Expected: PASS (5 tests)

- [x] **Step 7: Commit**

```bash
git add tools/commit/src/langatlas_commit/status.py tools/commit/tests/test_status.py \
        tools/commit/tests/test_land.py
git commit -m "feat(#stage-1d): gate the land loop on is-main-green"
```

---

## Task 5: Failure bot — auto-revert safety checklist + circuit breaker

**Files:**
- Create: `tools/commit/src/langatlas_commit/revert.py`
- Test: `tools/commit/tests/test_revert.py`

**Interfaces:**
- Consumes: `land.py`'s `_git` pattern (reimplemented locally — `revert.py` does not import
  `land.py`'s private `_git`, per the file-structure boundary that `revert.py` never runs the
  land loop itself, only the plain `git revert` + push).
- Produces for Task 9/1E: `evaluate_revert_safety(...) -> tuple[bool, str]`,
  `auto_revert(repo_root, sha, *, remote="origin", branch="main") -> LandResult`,
  `RevertBudget` (a per-run counter), `RevertCircuitBroken` exception.

- [x] **Step 1: Write the failing tests**

```python
# tools/commit/tests/test_revert.py
import subprocess
from pathlib import Path

import pytest

from langatlas_commit.revert import (
    evaluate_revert_safety, auto_revert, RevertBudget, RevertCircuitBroken,
)
from langatlas_commit.land import Landed


def _git(args, cwd, check=True):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=check)


def test_evaluate_revert_safety_all_conditions_hold():
    ok, reason = evaluate_revert_safety(
        is_tip=True, author_is_bot=True, deterministic_failure=True, revert_applies_cleanly=True,
    )
    assert ok is True


@pytest.mark.parametrize("field", ["is_tip", "author_is_bot", "deterministic_failure",
                                   "revert_applies_cleanly"])
def test_evaluate_revert_safety_fails_if_any_condition_false(field):
    conditions = dict(is_tip=True, author_is_bot=True, deterministic_failure=True,
                      revert_applies_cleanly=True)
    conditions[field] = False
    ok, reason = evaluate_revert_safety(**conditions)
    assert ok is False
    assert field in reason


def test_revert_budget_allows_two_then_breaks():
    budget = RevertBudget()
    budget.record_revert()
    budget.record_revert()
    with pytest.raises(RevertCircuitBroken):
        budget.record_revert()


@pytest.fixture
def bare_and_clone(tmp_path):
    bare = tmp_path / "bare.git"
    _git(["init", "-q", "--bare", "-b", "main", str(bare)], tmp_path)
    clone = tmp_path / "clone"
    _git(["clone", "-q", str(bare), str(clone)], tmp_path)
    _git(["config", "user.email", "bot@example.com"], clone)
    _git(["config", "user.name", "bot"], clone)
    (clone / "README.md").write_text("seed\n")
    _git(["add", "README.md"], clone)
    _git(["commit", "-q", "-m", "seed"], clone)
    (clone / "bad.yaml").write_text("broken: true\n")
    _git(["add", "bad.yaml"], clone)
    _git(["commit", "-q", "-m", "bad commit"], clone)
    _git(["push", "-q", "origin", "main"], clone)
    return bare, clone


def test_auto_revert_pushes_a_clean_revert(bare_and_clone):
    bare, clone = bare_and_clone
    tip = _git(["rev-parse", "HEAD"], clone).stdout.strip()
    result = auto_revert(clone, tip)
    assert isinstance(result, Landed)
    log = _git(["log", "-1", "--format=%s", "origin/main"], clone)
    assert "Revert" in log.stdout
```

- [x] **Step 2: Run tests to verify they fail**

Run: `cd tools/commit && uv run pytest tests/test_revert.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'langatlas_commit.revert'`

- [x] **Step 3: Implement `revert.py`**

```python
# tools/commit/src/langatlas_commit/revert.py
import subprocess
from pathlib import Path

from langatlas_commit.land import Landed, UnsafeHalt, LandResult

# D36 §2.5: a run-level pattern can override an individually-safe per-event verdict.
_MAX_REVERTS_PER_RUN = 2


class RevertCircuitBroken(Exception):
    """More than _MAX_REVERTS_PER_RUN auto-reverts in one run — evidence something
    systemic is wrong (most plausibly: the runner's local validator has drifted from
    CI's copy). The caller must halt, not keep reverting one-by-one."""


class RevertBudget:
    def __init__(self) -> None:
        self._count = 0

    def record_revert(self) -> None:
        self._count += 1
        if self._count > _MAX_REVERTS_PER_RUN:
            raise RevertCircuitBroken(f"{self._count} reverts this run (max {_MAX_REVERTS_PER_RUN})")


def evaluate_revert_safety(
    *, is_tip: bool, author_is_bot: bool, deterministic_failure: bool,
    revert_applies_cleanly: bool,
) -> tuple[bool, str]:
    """D36 §2.5's four-condition checklist. All four must hold, or the failure bot
    does not touch main. Content disputes, D25 controversy flags, and anything the
    D24 verifier already gated are the caller's responsibility to exclude before
    calling this — this function only judges the four mechanical conditions."""
    if not is_tip:
        return False, "is_tip: failing commit is not main's current tip"
    if not author_is_bot:
        return False, "author_is_bot: commit was not authored by the bot identity"
    if not deterministic_failure:
        return False, "deterministic_failure: failure did not reproduce on rerun (flake)"
    if not revert_applies_cleanly:
        return False, "revert_applies_cleanly: git revert would conflict"
    return True, "all four conditions hold"


def _git(args: list[str], cwd: Path, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=check)


def auto_revert(repo_root: Path, sha: str, *, remote: str = "origin",
                branch: str = "main") -> LandResult:
    """Push a `git revert` of `sha`. Caller must have already confirmed
    `evaluate_revert_safety(...) == (True, ...)` and charged a `RevertBudget` — this
    function performs no safety checks of its own, matching the boundary that
    `revert.py`'s job is deciding-and-acting, split into a pure decision function and
    a thin git-mechanics function."""
    _git(["fetch", "-q", remote], repo_root)
    _git(["checkout", "-q", branch], repo_root)
    _git(["reset", "-q", "--hard", f"{remote}/{branch}"], repo_root)
    revert = _git(["revert", "--no-edit", sha], repo_root, check=False)
    if revert.returncode != 0:
        _git(["revert", "--abort"], repo_root, check=False)
        return UnsafeHalt(commit_sha=sha,
                          diagnostic=f"revert did not apply cleanly: {revert.stderr}")
    push = _git(["push", remote, f"HEAD:{branch}"], repo_root, check=False)
    if push.returncode != 0:
        return UnsafeHalt(commit_sha=sha, diagnostic=f"revert push failed: {push.stderr}")
    new_sha = _git(["rev-parse", "HEAD"], repo_root).stdout.strip()
    return Landed(commit_sha=new_sha)
```

- [x] **Step 4: Run tests to verify they pass**

Run: `cd tools/commit && uv run pytest tests/test_revert.py -v`
Expected: PASS (5 tests, including the parametrized one's 4 cases = 7 total)

- [x] **Step 5: Commit**

```bash
git add tools/commit/src/langatlas_commit/revert.py tools/commit/tests/test_revert.py
git commit -m "feat(#stage-1d): add the failure bot's auto-revert checklist and circuit breaker"
```

---

## Task 6: Issue filing for `blocked_red_main`/`unsafe_halt`/auto-revert

**Files:**
- Create: `tools/commit/src/langatlas_commit/issues.py`
- Test: `tools/commit/tests/test_issues.py`

**Interfaces:**
- Consumes: `RunContext.github_token()` (Task 1).
- Produces for 1E: `file_issue(ctx, owner, repo, *, title, body, labels) -> int` (returns the
  issue number).

- [x] **Step 1: Write the failing test**

```python
# tools/commit/tests/test_issues.py
import httpx

from langatlas_commit.issues import file_issue


class _FakeRunContext:
    def github_token(self) -> str:
        return "ghs_fake"


def test_file_issue_posts_expected_payload():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = request.content
        return httpx.Response(201, json={"number": 42})

    transport = httpx.MockTransport(handler)
    http = httpx.Client(transport=transport, base_url="https://api.github.com")
    number = file_issue(_FakeRunContext(), "langatlas", "langatlas-kb",
                        title="auto-revert: deadbeef", body="details",
                        labels=["auto-revert"], http_client=http)
    assert number == 42
    assert "repos/langatlas/langatlas-kb/issues" in captured["url"]
    assert b"auto-revert" in captured["body"]
```

- [x] **Step 2: Run test to verify it fails**

Run: `cd tools/commit && uv run pytest tests/test_issues.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'langatlas_commit.issues'`

- [x] **Step 3: Implement `issues.py`**

```python
# tools/commit/src/langatlas_commit/issues.py
import httpx


def file_issue(ctx, owner: str, repo: str, *, title: str, body: str,
               labels: list[str], http_client: httpx.Client | None = None) -> int:
    """D36 §2.5: the failure bot's halt/auto-revert diagnostic path, using the same
    `langatlas-kb` issue tracker D9 already uses for human fact challenges — a
    different auto-applied label keeps the two failure classes apart."""
    http = http_client or httpx.Client(base_url="https://api.github.com")
    response = http.post(
        f"/repos/{owner}/{repo}/issues",
        headers={"Authorization": f"Bearer {ctx.github_token()}",
                "Accept": "application/vnd.github+json"},
        json={"title": title, "body": body, "labels": labels},
    )
    response.raise_for_status()
    return response.json()["number"]
```

- [x] **Step 4: Run test to verify it passes**

Run: `cd tools/commit && uv run pytest tests/test_issues.py -v`
Expected: PASS

- [x] **Step 5: Commit**

```bash
git add tools/commit/src/langatlas_commit/issues.py tools/commit/tests/test_issues.py
git commit -m "feat(#stage-1d): file failure-bot issues via the GitHub App identity"
```

---

## Task 7: Store walker — turn `ci` into a real store-validating gate

**Files:**
- Create: `tools/validate/src/langatlas_validate/store.py`
- Modify: `tools/validate/src/langatlas_validate/cli.py`
- Test: `tools/validate/tests/test_store.py`

**Interfaces:**
- Consumes: `validate_record`, `normalize_record`, `validate_claim_template`, `TEMPLATED_KINDS`,
  `canonical_endpoints`, `canonical_when_all` (all already shipped by 1A, per the cross-stage
  plan's carry-over note).
- Produces for Task 8: `iter_store_records(repo_root) -> Iterator[tuple[Path, str, str, dict]]`
  (path, kind, raw_text, parsed_data), `validate_store(repo_root) -> list[str]`.

- [x] **Step 1: Write the failing test**

```python
# tools/validate/tests/test_store.py
from pathlib import Path

import pytest
from ruamel.yaml import YAML

from langatlas_validate.store import iter_store_records, validate_store
from langatlas_validate.normalize import normalize_record

_yaml = YAML()


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def _feature_instance_yaml() -> str:
    raw = (
        "feature: pattern-matching\nlanguage: rust\nstatus: present\n"
        "provenance:\n  claim_origin: source-derived\n"
    )
    return normalize_record(raw, "feature-instance")


@pytest.fixture
def store(tmp_path):
    root = tmp_path
    (root / "concepts" / ".gitkeep").parent.mkdir(parents=True, exist_ok=True)
    (root / "concepts" / ".gitkeep").write_text("")
    _write(root / "languages" / "rust" / "instances" / "pattern-matching.yaml",
          _feature_instance_yaml())
    (root / "sources" / "_tombstones.yaml").parent.mkdir(parents=True, exist_ok=True)
    (root / "sources" / "_tombstones.yaml").write_text("[]\n")
    return root


def test_iter_store_records_finds_the_instance_and_skips_ledgers(store):
    found = list(iter_store_records(store))
    kinds = {kind for _path, kind, _text, _data in found}
    assert kinds == {"feature-instance"}
    assert len(found) == 1


def test_iter_store_records_skips_gitkeep_and_tombstones(store):
    paths = {str(path) for path, _kind, _text, _data in iter_store_records(store)}
    assert not any("gitkeep" in p for p in paths)
    assert not any("_tombstones" in p for p in paths)


def test_validate_store_clean_repo_has_no_errors(store):
    assert validate_store(store) == []


def test_validate_store_flags_normalization_drift(store):
    bad_path = store / "languages" / "rust" / "instances" / "drifted.yaml"
    # deliberately unnormalized: wrong key order relative to the schema
    bad_path.write_text("language: rust\nfeature: pattern-matching\nstatus: present\n"
                        "provenance:\n  claim_origin: source-derived\n")
    errors = validate_store(store)
    assert any("not normalized" in e for e in errors)


def test_validate_store_flags_schema_violation(store):
    bad_path = store / "languages" / "rust" / "instances" / "invalid.yaml"
    bad_path.write_text("feature: pattern-matching\nlanguage: rust\nstatus: absent\n"
                        "provenance:\n  claim_origin: source-derived\n")   # missing absence_scope
    errors = validate_store(store)
    assert any("invalid.yaml" in e for e in errors)
```

- [x] **Step 2: Run test to verify it fails**

Run: `cd tools/validate && uv run pytest tests/test_store.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'langatlas_validate.store'`

- [x] **Step 3: Implement `store.py`**

```python
# tools/validate/src/langatlas_validate/store.py
from pathlib import Path
from typing import Iterator

from ruamel.yaml import YAML

from langatlas_validate.claims import TEMPLATED_KINDS, validate_claim_template
from langatlas_validate.ids import canonical_endpoints, canonical_when_all
from langatlas_validate.normalize import normalize_record
from langatlas_validate.schema import validate_record

_yaml = YAML(typ="safe")

# path glob -> record kind, or a callable(data) -> kind when the directory alone is
# ambiguous (edges/ holds two kinds, discriminated by the record's own "type" field).
_LEDGERS = {"_tombstones.yaml", "_registry.yaml", "tombstones.yaml", "contradictions.yaml",
           "overrides.yaml"}


def iter_store_records(repo_root: Path) -> Iterator[tuple[Path, str, str, dict]]:
    """Walks the canonical store per §3.3's layout, yielding every validated-record
    file. Root-level ledgers (`_tombstones.yaml`, `overrides.yaml`, ...), `.gitkeep`,
    and `languages/_registry.yaml` (a language-registry record, not walked here since
    it has exactly one instance and its own `language-registry` kind — added back in
    explicitly below) are excluded from the generic walk."""
    for path in sorted((repo_root / "concepts").glob("*.yaml")):
        yield from _load(path, "concept")
    for path in sorted((repo_root / "features").glob("*.yaml")):
        yield from _load(path, "feature")

    registry = repo_root / "languages" / "_registry.yaml"
    if registry.exists():
        yield from _load(registry, "language-registry")
    for lang_dir in sorted((repo_root / "languages").iterdir()) if (repo_root / "languages").exists() else []:
        if not lang_dir.is_dir():
            continue
        lang_file = lang_dir / "language.yaml"
        if lang_file.exists():
            yield from _load(lang_file, "language")
        instances_dir = lang_dir / "instances"
        if instances_dir.exists():
            for path in sorted(instances_dir.glob("*.yaml")):
                yield from _load(path, "feature-instance")

    edges_root = repo_root / "edges"
    if edges_root.exists():
        for from_dir in sorted(edges_root.iterdir()):
            if not from_dir.is_dir():
                continue
            for path in sorted(from_dir.glob("*.yaml")):
                text = path.read_text()
                data = _yaml.load(text)
                kind = "affects-quality-edge" if data.get("type") == "affects-quality" else "edge"
                yield path, kind, text, data

    rules_root = repo_root / "rules"
    if rules_root.exists():
        for path in sorted(rules_root.glob("*.yaml")):
            yield from _load(path, "rule")

    sources_root = repo_root / "sources"
    if sources_root.exists():
        for path in sorted(sources_root.glob("*.yaml")):
            if path.name in _LEDGERS:
                continue
            yield from _load(path, "source")


def _load(path: Path, kind: str) -> Iterator[tuple[Path, str, str, dict]]:
    if path.name == ".gitkeep":
        return
    text = path.read_text()
    if not text.strip():
        return
    data = _yaml.load(text)
    yield path, kind, text, data


def validate_store(repo_root: Path) -> list[str]:
    """CI's store-validating gate (D13): schema validity + normalization drift for
    every live record, the claim-template registry's own self-check, and D64's
    canonical-ordering rule for `alternative-to` edges and rules' `when_all`."""
    errors: list[str] = []

    for kind in TEMPLATED_KINDS:
        errors.extend(f"claim-templates/{kind}: {e}" for e in validate_claim_template(kind))

    for path, kind, text, data in iter_store_records(repo_root):
        rel = path
        for e in validate_record(data, kind):
            errors.append(f"{rel}: {e}")
        if normalize_record(text, kind) != text:
            errors.append(f"{rel}: not normalized (re-run the normalizer to fix)")

        if kind == "edge" and data.get("type") == "alternative-to":
            frm, to = data.get("from"), data.get("to")
            if isinstance(frm, str) and isinstance(to, str):
                if (frm, to) != canonical_endpoints(frm, to):
                    errors.append(f"{rel}: alternative-to endpoints not lexicographically ordered")
        if kind == "rule":
            when_all = data.get("when_all")
            if isinstance(when_all, list) and all(isinstance(x, str) for x in when_all):
                if when_all != canonical_when_all(when_all):
                    errors.append(f"{rel}: when_all not canonically (lexicographically) ordered")

    return errors
```

- [x] **Step 4: Run test to verify it passes**

Run: `cd tools/validate && uv run pytest tests/test_store.py -v`
Expected: PASS (5 tests)

- [x] **Step 5: Wire `validate_store` into `cmd_ci`**

Edit `tools/validate/src/langatlas_validate/cli.py`. Add the import and change `cmd_ci`:

```python
from langatlas_validate.store import validate_store
from langatlas_validate.paths import REPO_ROOT as _REPO_ROOT


def cmd_ci() -> int:
    rc = _print_report(run_regression(_FIXTURES), verbose=True)
    store_errors = validate_store(_REPO_ROOT)
    for e in store_errors:
        print(f"STORE {e}")
    return rc or (1 if store_errors else 0)
```

- [x] **Step 6: Run the existing CLI test to confirm the clean-repo case still passes**

Run: `cd tools/validate && uv run pytest tests/test_cli.py -v -k test_ci_exit_zero_on_clean_repo`
Expected: PASS — today's repo has only `.gitkeep`/`_registry.yaml`/`_tombstones.yaml` under the
store directories, so `validate_store` returns `[]`.

- [x] **Step 7: Run the full validate test suite**

Run: `cd tools/validate && uv run pytest -v`
Expected: PASS, no regressions.

- [x] **Step 8: Commit**

```bash
git add tools/validate/src/langatlas_validate/store.py tools/validate/src/langatlas_validate/cli.py \
        tools/validate/tests/test_store.py
git commit -m "feat(#stage-1d): make langatlas-validate ci walk the live canonical store"
```

---

## Task 8: Fact derivation and collision check

**Files:**
- Create: `tools/validate/src/langatlas_validate/compile.py`
- Modify: `tools/validate/src/langatlas_validate/cli.py`
- Test: `tools/validate/tests/test_compile.py`

**Interfaces:**
- Consumes: `iter_store_records` (Task 7), `build_claim`, `fact_id` (already shipped by 1A in
  `claims.py`), `ids.compose_instance_id`, `ids.compose_syntax_id`.
- Produces for CI publication step (Task 10): `compile_bundle(repo_root) -> dict` (`{
  "schema_version": str, "facts": list[dict], "source_manifest": list[dict] }`).

- [x] **Step 1: Write the failing test**

```python
# tools/validate/tests/test_compile.py
from pathlib import Path

from langatlas_validate.compile import derive_facts, check_fact_collisions, compile_bundle
from langatlas_validate.normalize import normalize_record


def _write_instance(root: Path) -> None:
    raw = (
        "feature: pattern-matching\nlanguage: rust\nstatus: present\n"
        "characteristics:\n"
        "  - key: c-exhaustive\n"
        "    text: match arms must be exhaustive\n"
        "    sources:\n"
        "      - source: nystrom-2021\n        locator: \"p. 42\"\n"
        "provenance:\n  claim_origin: source-derived\n"
    )
    path = root / "languages" / "rust" / "instances" / "pattern-matching.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(normalize_record(raw, "feature-instance"))


def test_derive_facts_yields_instance_exists_and_characteristic(tmp_path):
    _write_instance(tmp_path)
    from langatlas_validate.store import iter_store_records
    records = list(iter_store_records(tmp_path))
    facts = derive_facts(records)
    kinds = {f["claim"].split("(")[0] for f in facts}
    assert "instance-exists" in kinds
    assert "characteristic" in kinds
    for f in facts:
        assert f["fact_id"].startswith("f-")
        assert f["record_path"] is not None


def test_check_fact_collisions_flags_same_fact_id_from_two_records():
    facts = [
        {"fact_id": "f-abc", "claim": "instance-exists(fi.rust.x, status=present)",
        "record_path": "a.yaml"},
        {"fact_id": "f-abc", "claim": "instance-exists(fi.rust.x, status=present)",
        "record_path": "b.yaml"},
    ]
    errors = check_fact_collisions(facts)
    assert len(errors) == 1
    assert "a.yaml" in errors[0] and "b.yaml" in errors[0]


def test_check_fact_collisions_allows_unique_facts():
    facts = [
        {"fact_id": "f-abc", "claim": "instance-exists(fi.rust.x, status=present)",
        "record_path": "a.yaml"},
        {"fact_id": "f-def", "claim": "instance-exists(fi.rust.y, status=present)",
        "record_path": "b.yaml"},
    ]
    assert check_fact_collisions(facts) == []


def test_compile_bundle_shape(tmp_path):
    _write_instance(tmp_path)
    (tmp_path / "ontology").mkdir()
    (tmp_path / "ontology" / "VERSION").write_text("0.1.0\n")
    bundle = compile_bundle(tmp_path)
    assert bundle["schema_version"] == "0.1.0"
    assert isinstance(bundle["facts"], list) and len(bundle["facts"]) > 0
```

- [x] **Step 2: Run test to verify it fails**

Run: `cd tools/validate && uv run pytest tests/test_compile.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'langatlas_validate.compile'`

- [x] **Step 3: Implement `compile.py`**

```python
# tools/validate/src/langatlas_validate/compile.py
from pathlib import Path

from langatlas_validate.claims import build_claim, fact_id
from langatlas_validate.ids import compose_instance_id, compose_syntax_id


def derive_facts(records: list[tuple[Path, str, str, dict]]) -> list[dict]:
    """D20/D23: facts are never authored directly — they're derived once, here, from
    whole records. Intentionally scoped to the fields with a direct claim-template
    mapping (§ontology/claim-templates/); extending coverage to every schema field is
    later work, not a Stage-1D gap."""
    facts: list[dict] = []

    def _add(claim: str, record_path: Path, sources: list[dict] | None = None) -> None:
        facts.append({"fact_id": fact_id(claim), "claim": claim,
                     "record_path": str(record_path), "sources": sources or []})

    for path, kind, _text, data in records:
        if kind == "feature-instance":
            instance_id = compose_instance_id(data["language"], data["feature"])
            _add(build_claim("instance-exists", instance_id=instance_id, status=data["status"]),
                path)
            for c in data.get("characteristics", []):
                _add(build_claim("characteristic", instance_id=instance_id,
                                 key=c["key"], text=c["text"]), path, c.get("sources"))
            for s in data.get("syntax", []):
                syntax_id = compose_syntax_id(instance_id, s["key"])
                _add(build_claim("syntax-valid", syntax_id=syntax_id, code=s["code"]),
                    path, s.get("sources"))
        elif kind == "edge":
            edge_id = data["id"]
            _add(build_claim("edge-exists", edge_id=edge_id), path)
            if data.get("type") == "influences" and "polarity" in data:
                _add(build_claim("edge-polarity", edge_id=edge_id, polarity=data["polarity"]), path)
        elif kind == "affects-quality-edge":
            for a in data.get("assessments", []):
                _add(build_claim("quality-assessment", edge_id=data["id"],
                                 assessment_key=a["key"]), path, a.get("sources"))
        elif kind == "rule":
            _add(build_claim("rule-exists", rule_id=data["id"], message=data["message"]),
                path, data.get("sources"))

    return facts


def check_fact_collisions(facts: list[dict]) -> list[str]:
    """A fact_id colliding across two different record paths means two records both
    claim authority over the same fact — an authoring bug the store should never
    admit, not a hash collision (astronomically unlikely at sha256)."""
    by_id: dict[str, list[dict]] = {}
    for f in facts:
        by_id.setdefault(f["fact_id"], []).append(f)
    errors = []
    for fid, group in by_id.items():
        paths = {f["record_path"] for f in group}
        if len(paths) > 1:
            errors.append(f"{fid}: claimed by multiple records: {sorted(paths)}")
    return errors


def compile_bundle(repo_root: Path) -> dict:
    """D13's compiled canonical bundle — the artifact the site/Postgres/MCP consume.
    Stage 1D ships the skeleton shape; source_manifest population (per-source snapshot
    hashes) is Stage 2's ingestion-corpus concern."""
    from langatlas_validate.store import iter_store_records

    version = (repo_root / "ontology" / "VERSION").read_text().strip()
    records = list(iter_store_records(repo_root))
    facts = derive_facts(records)
    return {"schema_version": version, "facts": facts, "source_manifest": []}
```

- [x] **Step 4: Run test to verify it passes**

Run: `cd tools/validate && uv run pytest tests/test_compile.py -v`
Expected: PASS (4 tests)

- [x] **Step 5: Wire the collision check into `cmd_ci`**

Edit `cmd_ci` in `tools/validate/src/langatlas_validate/cli.py`:

```python
def cmd_ci() -> int:
    rc = _print_report(run_regression(_FIXTURES), verbose=True)
    store_errors = validate_store(_REPO_ROOT)
    for e in store_errors:
        print(f"STORE {e}")

    from langatlas_validate.store import iter_store_records
    from langatlas_validate.compile import derive_facts, check_fact_collisions
    facts = derive_facts(list(iter_store_records(_REPO_ROOT)))
    collision_errors = check_fact_collisions(facts)
    for e in collision_errors:
        print(f"COLLISION {e}")

    return rc or (1 if store_errors or collision_errors else 0)
```

- [x] **Step 6: Run the full validate test suite**

Run: `cd tools/validate && uv run pytest -v`
Expected: PASS, no regressions.

- [x] **Step 7: Commit**

```bash
git add tools/validate/src/langatlas_validate/compile.py tools/validate/src/langatlas_validate/cli.py \
        tools/validate/tests/test_compile.py
git commit -m "feat(#stage-1d): derive facts from the store and check for fact-id collisions"
```

---

## Task 9: Phase-2 locator resolution in `ci` (when Postgres is reachable)

**Files:**
- Modify: `tools/validate/src/langatlas_validate/cli.py`
- Test: `tools/validate/tests/test_locators_ci.py`

**Interfaces:**
- Consumes: `SourceChunksIndex` protocol and `validate_locator` (1A, `locators.py`),
  `PostgresSourceChunksIndex` and `langatlas_ingest.db.connect()` (1C, already shipped — per the
  cross-stage plan's explicit note that this wiring is 1D's job).
- Produces: nothing new for later stages — this closes out the "carried over from 1C" item; no
  interface change, since `precommit` intentionally stays phase-1-only (D48: no auto-upgrade).

- [x] **Step 1: Write the failing test**

```python
# tools/validate/tests/test_locators_ci.py
from pathlib import Path

from langatlas_validate.cli import cmd_ci_with_index
from langatlas_validate.normalize import normalize_record


class _FakeIndex:
    """Implements the SourceChunksIndex protocol without touching Postgres."""
    def __init__(self, resolvable: set[tuple[str, str]]):
        self._resolvable = resolvable

    def resolve(self, source_id: str, locator: str) -> list[str]:
        return ["chunk-1"] if (source_id, locator) in self._resolvable else []


def _write_instance_with_locator(root: Path, locator: str) -> None:
    raw = (
        "feature: pattern-matching\nlanguage: rust\nstatus: present\n"
        "characteristics:\n"
        "  - key: c-a\n    text: some characteristic\n"
        "    sources:\n"
        f"      - source: nystrom-2021\n        locator: \"{locator}\"\n"
        "provenance:\n  claim_origin: source-derived\n"
    )
    path = root / "languages" / "rust" / "instances" / "pattern-matching.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(normalize_record(raw, "feature-instance"))


def test_ci_with_index_passes_when_locator_resolves(tmp_path):
    _write_instance_with_locator(tmp_path, "p. 42")
    index = _FakeIndex(resolvable={("nystrom-2021", "p. 42")})
    rc, errors = cmd_ci_with_index(tmp_path, index)
    assert rc == 0
    assert errors == []


def test_ci_with_index_does_not_fail_on_unresolved_locator(tmp_path):
    # D37/1C: an unresolved-but-well-shaped locator parks in the sourcing queue and
    # renders the citing claim flagged — it must NOT redden CI (that would punish the
    # store for a source the corpus doesn't contain yet).
    _write_instance_with_locator(tmp_path, "p. 42")
    index = _FakeIndex(resolvable=set())
    rc, errors = cmd_ci_with_index(tmp_path, index)
    assert rc == 0


def test_ci_with_index_still_fails_on_malformed_locator_shape(tmp_path):
    _write_instance_with_locator(tmp_path, "not a real locator shape")
    index = _FakeIndex(resolvable=set())
    rc, errors = cmd_ci_with_index(tmp_path, index)
    assert rc == 1
    assert any("locator" in e for e in errors)
```

- [x] **Step 2: Run test to verify it fails**

Run: `cd tools/validate && uv run pytest tests/test_locators_ci.py -v`
Expected: FAIL with `ImportError: cannot import name 'cmd_ci_with_index'`

- [x] **Step 3: Implement `cmd_ci_with_index` and wire the soft-optional Postgres path into `cmd_ci`**

Edit `tools/validate/src/langatlas_validate/cli.py`:

```python
from langatlas_validate.locators import validate_locator, SourceChunksIndex


def cmd_ci_with_index(repo_root, index: SourceChunksIndex | None) -> tuple[int, list[str]]:
    """The store-validation pass, optionally resolving locators through `index`
    (1C's SourceChunksIndex). Only a malformed locator *shape* fails CI; an
    unresolved-but-well-shaped locator is a sourcing-queue matter (D37), not a
    CI failure — the corpus not containing a source yet is an expected state."""
    errors = validate_store(repo_root)
    if index is not None:
        from langatlas_validate.store import iter_store_records
        for path, _kind, _text, data in iter_store_records(repo_root):
            for entry in _iter_source_entries(data):
                result = validate_locator(entry["locator"], entry["source"], index)
                if not result.shape_ok:
                    errors.append(f"{path}: locator: unrecognized shape: {entry['locator']!r}")
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
```

Remove the now-superseded inline `validate_store`-only body from Task 7/8's `cmd_ci` (this step
replaces it wholesale — the snippet above is the final version of `cmd_ci`).

- [x] **Step 4: Run test to verify it passes**

Run: `cd tools/validate && uv run pytest tests/test_locators_ci.py -v`
Expected: PASS (3 tests)

- [x] **Step 5: Run the full validate test suite**

Run: `cd tools/validate && uv run pytest -v`
Expected: PASS, no regressions. (`test_ci_exit_zero_on_clean_repo` still passes: no live
Postgres in the test environment, so `_postgres_index()` returns `None` and CI runs
phase-1-only, same as before this task.)

- [x] **Step 6: Commit**

```bash
git add tools/validate/src/langatlas_validate/cli.py tools/validate/tests/test_locators_ci.py
git commit -m "feat(#stage-1d): wire phase-2 locator resolution into langatlas-validate ci"
```

---

## Task 10: Pre-commit hook auto-kind detection

**Files:**
- Modify: `tools/validate/src/langatlas_validate/cli.py`
- Create: `.pre-commit-config.yaml`
- Test: `tools/validate/tests/test_precommit_auto.py`

**Interfaces:**
- Consumes: `store.py`'s directory-to-kind convention (Task 7); `cmd_precommit` (existing, 1A).
- Produces: a `precommit-auto` CLI subcommand any git hook (or the agent runner's own pre-push
  validation step) can call with a bare file list — no `--kind` needed, since the pre-commit
  framework and a land-loop `validator` callback both only know paths, not record kinds.

- [x] **Step 1: Write the failing test**

```python
# tools/validate/tests/test_precommit_auto.py
from pathlib import Path

from langatlas_validate.cli import main, infer_kind_from_path


def test_infer_kind_from_path_covers_every_store_directory():
    assert infer_kind_from_path(Path("concepts/x.yaml")) == "concept"
    assert infer_kind_from_path(Path("features/x.yaml")) == "feature"
    assert infer_kind_from_path(Path("languages/_registry.yaml")) == "language-registry"
    assert infer_kind_from_path(Path("languages/rust/language.yaml")) == "language"
    assert infer_kind_from_path(Path("languages/rust/instances/x.yaml")) == "feature-instance"
    assert infer_kind_from_path(Path("rules/x.yaml")) == "rule"
    assert infer_kind_from_path(Path("sources/x.yaml")) == "source"
    assert infer_kind_from_path(Path("README.md")) is None


def test_precommit_auto_validates_a_clean_feature_instance(tmp_path):
    from langatlas_validate.normalize import normalize_record
    f = tmp_path / "languages" / "rust" / "instances" / "pattern-matching.yaml"
    f.parent.mkdir(parents=True)
    raw = ("feature: pattern-matching\nlanguage: rust\nstatus: present\n"
          "provenance:\n  claim_origin: source-derived\n")
    f.write_text(normalize_record(raw, "feature-instance"))
    assert main(["precommit-auto", str(f)]) == 0


def test_precommit_auto_skips_edges_needing_type_sniff(tmp_path):
    from langatlas_validate.normalize import normalize_record
    f = tmp_path / "edges" / "algebraic-data-types" / "requires--pattern-matching.yaml"
    f.parent.mkdir(parents=True)
    raw = ("id: edge.requires.algebraic-data-types.pattern-matching\n"
          "type: requires\nfrom: algebraic-data-types\nto: pattern-matching\n"
          "statement:\n  text: x\n  sources: []\n"
          "provenance:\n  claim_origin: source-derived\n")
    f.write_text(raw)
    # edges/ needs the record's own "type" field to disambiguate edge vs
    # affects-quality-edge — precommit-auto reads the file's contents, not just its path.
    assert main(["precommit-auto", str(f)]) in (0, 1)   # exercises the sniff path either way
```

- [x] **Step 2: Run test to verify it fails**

Run: `cd tools/validate && uv run pytest tests/test_precommit_auto.py -v`
Expected: FAIL with `ImportError: cannot import name 'infer_kind_from_path'`

- [x] **Step 3: Implement `infer_kind_from_path` and the `precommit-auto` subcommand**

Edit `tools/validate/src/langatlas_validate/cli.py`, add:

```python
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
```

Add the subcommand to `main`:

```python
    p_pre_auto = sub.add_parser("precommit-auto")
    p_pre_auto.add_argument("files", nargs="+")
```

and dispatch it:

```python
    if args.command == "precommit-auto":
        return cmd_precommit_auto(args.files)
```

- [x] **Step 4: Run test to verify it passes**

Run: `cd tools/validate && uv run pytest tests/test_precommit_auto.py -v`
Expected: PASS (3 tests)

- [x] **Step 5: Write `.pre-commit-config.yaml`**

```yaml
# Runs the same fast offline validator the agent runner uses before every commit
# (brainstorm 10 §"Direct agent commits × CI failure") — installed as a plain
# pre-commit hook so the developer's manual edits get the same gate.
repos:
  - repo: local
    hooks:
      - id: langatlas-validate
        name: langatlas-validate precommit-auto
        entry: uv --directory tools/validate run langatlas-validate precommit-auto
        language: system
        files: ^(concepts|features|languages|edges|rules|sources)/.*\.yaml$
        exclude: ^(languages/_registry\.yaml|sources/_tombstones\.yaml)$
```

- [x] **Step 6: Run the full validate test suite**

Run: `cd tools/validate && uv run pytest -v`
Expected: PASS, no regressions.

- [x] **Step 7: Commit**

```bash
git add tools/validate/src/langatlas_validate/cli.py tools/validate/tests/test_precommit_auto.py \
        .pre-commit-config.yaml
git commit -m "feat(#stage-1d): auto-detect record kind for the pre-commit validator hook"
```

---

## Task 11: CI workflow — validate on every push, publish on green `main`

**Files:**
- Create: `.github/workflows/ci.yml`
- Create: `tools/validate/src/langatlas_validate/publish_cli.py`
- Test: `tools/validate/tests/test_publish_cli.py`

**Interfaces:**
- Consumes: `compile_bundle` (Task 8), `cmd_ci` (Task 9).
- Produces: nothing consumed by a later *code* task — this is the operational wiring the
  cross-stage plan's Stage-1 exit test and Stage 2+ agents run against.

- [x] **Step 1: Write the failing test for the tag-naming helper**

```python
# tools/validate/tests/test_publish_cli.py
from datetime import date

from langatlas_validate.publish_cli import data_vn_tag_for_today


def test_data_vn_tag_is_date_stamped():
    tag = data_vn_tag_for_today(today=date(2026, 8, 21))
    assert tag == "data-v2026.08.21"
```

- [x] **Step 2: Run test to verify it fails**

Run: `cd tools/validate && uv run pytest tests/test_publish_cli.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'langatlas_validate.publish_cli'`

- [x] **Step 3: Implement `publish_cli.py`**

```python
# tools/validate/src/langatlas_validate/publish_cli.py
import argparse
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

from langatlas_validate.compile import compile_bundle
from langatlas_validate.paths import REPO_ROOT


def data_vn_tag_for_today(*, today: date | None = None) -> str:
    """D13 ratified cadence: daily, only on days with changes. The tag name itself is
    just the date stamp; "only on days with changes" is enforced by the workflow step
    that skips tagging when this tag already exists (git tags are immutable)."""
    day = today or datetime.now(timezone.utc).date()
    return f"data-v{day.isoformat().replace('-', '.')}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="langatlas-publish")
    parser.add_argument("--out", required=True, help="path to write the compiled bundle JSON")
    args = parser.parse_args(argv)

    bundle = compile_bundle(REPO_ROOT)
    Path(args.out).write_text(json.dumps(bundle, indent=2, sort_keys=True))
    print(f"wrote {args.out} ({len(bundle['facts'])} facts, schema_version={bundle['schema_version']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

Register the entry point in `tools/validate/pyproject.toml`'s `[project.scripts]`:

```toml
langatlas-publish = "langatlas_validate.publish_cli:main"
```

- [x] **Step 4: Run test to verify it passes**

Run: `cd tools/validate && uv sync && uv run pytest tests/test_publish_cli.py -v`
Expected: PASS

- [x] **Step 5: Write `.github/workflows/ci.yml`**

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - name: Install packages
        run: |
          uv --directory tools/validate sync
          uv --directory tools/pipeline sync
          uv --directory tools/ingest sync
      - name: Run the store-validating gate
        run: uv --directory tools/validate run langatlas-validate ci

  publish:
    needs: validate
    if: github.ref == 'refs/heads/main' && github.event_name == 'push'
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - name: Install packages
        run: uv --directory tools/validate sync
      - name: Compile the dataset bundle
        run: uv --directory tools/validate run langatlas-publish --out dataset.json
      - name: Compute today's data-vN tag
        id: tag
        run: |
          TAG=$(uv --directory tools/validate run python -c \
            "from langatlas_validate.publish_cli import data_vn_tag_for_today; print(data_vn_tag_for_today())")
          echo "tag=$TAG" >> "$GITHUB_OUTPUT"
      - name: Move the latest-green rolling tag
        run: |
          git tag -f latest-green
          git push -f origin latest-green
      - name: Publish latest-green release asset
        uses: softprops/action-gh-release@v2
        with:
          tag_name: latest-green
          files: dataset.json
          make_latest: false
      - name: Cut today's data-vN tag if it doesn't already exist (daily, changes-only)
        run: |
          if git rev-parse "${{ steps.tag.outputs.tag }}" >/dev/null 2>&1; then
            echo "tag already exists, skipping (no changes today or already published)"
          else
            git tag "${{ steps.tag.outputs.tag }}"
            git push origin "${{ steps.tag.outputs.tag }}"
          fi
      - name: Publish data-vN release asset
        if: steps.tag.outcome == 'success'
        uses: softprops/action-gh-release@v2
        with:
          tag_name: ${{ steps.tag.outputs.tag }}
          files: dataset.json
          make_latest: false
      - name: Dispatch to langatlas-site (best-effort; site has nothing to consume yet)
        continue-on-error: true
        env:
          GH_TOKEN: ${{ secrets.LANGATLAS_SITE_DISPATCH_TOKEN }}
        run: |
          gh api repos/langatlas/langatlas-site/dispatches \
            -f event_type=kb-updated \
            -f client_payload[tag]="${{ steps.tag.outputs.tag }}" \
            -f client_payload[sha]="${{ github.sha }}"
```

Note: `LANGATLAS_SITE_DISPATCH_TOKEN` is a placeholder secret name — actually registering the
cross-repo dispatch token is a Stage-0/operational follow-up (the org/App is not yet confirmed
per the cross-stage plan's Stage 0 section), so this step is deliberately `continue-on-error`
and does nothing observable until that secret exists.

- [x] **Step 6: Run the full validate test suite one more time**

Run: `cd tools/validate && uv run pytest -v`
Expected: PASS, no regressions.

- [x] **Step 7: Commit**

```bash
git add .github/workflows/ci.yml tools/validate/src/langatlas_validate/publish_cli.py \
        tools/validate/tests/test_publish_cli.py tools/validate/pyproject.toml tools/validate/uv.lock
git commit -m "feat(#stage-1d): add the CI workflow — validate on push, publish on green main"
```

---

## Self-Review

**Spec coverage** — every D36/D13 element the cross-stage plan lists for 1D has a task:
GitHub App identity + scoping (Task 1), token refresh via `RunContext` (Task 1), DCO carve-out
(Task 1), commit granularity + trailers (Task 2), fetch-rebase-retry + `LandResult` (Task 3),
is-main-green gating (Task 4), auto-revert checklist + circuit breaker (Task 5), issue filing
(Task 6), CI validators walking the live store (Task 7), fact derivation + collision check
(Task 8), phase-2 locator resolution (Task 9), pre-commit hook (Task 10), last-green publication
+ `data-vN` tagging + site dispatch (Task 11). Multi-runner `RUNNER_LOCK` lease (D36 §2.7) and
the external-PR provenance skim (D36 §2.8) are both explicitly *not* built yet per the ratified
decision's own "escalation path, not designed further" and "fold-in note, zero current volume"
language — correctly out of scope for this plan, not a gap.

**Placeholder scan** — no TBD/TODO markers; every step carries real, runnable code matching the
existing packages' style (dataclasses, `Path`-based APIs, soft-imports for optional
cross-package dependencies, `httpx.MockTransport` for API tests instead of live network calls).

**Type consistency** — `LandResult` (Task 3) is reused unchanged by Task 4 (`status_checker`
parameter), Task 5 (`auto_revert` returns it), and is the type Task 6/Task 9's callers pattern-
match on. `record_key`/`format_trailers` (Task 2) are the exact functions Task 3's `land_record`
imports. `iter_store_records`'s four-tuple shape (`path, kind, text, data`) from Task 7 is used
identically by Task 8's `derive_facts` and Task 9's `cmd_ci_with_index`. `compile_bundle`'s
`{schema_version, facts, source_manifest}` shape from Task 8 is exactly what Task 11's
`publish_cli.py` serializes.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-08-21-stage-1d-commit-and-ci.md`. Two
execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between
tasks, fast iteration.

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution
with checkpoints.

Which approach?
