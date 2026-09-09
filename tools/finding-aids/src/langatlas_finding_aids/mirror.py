"""The two mirrored finding aids (D53 §O2, ratified).

PLDB publishes no API but does publish a repo, so the mirror is a git clone — the same
"pull a directory" shape the source corpus itself already uses. Hyperpolyglot publishes
neither, so the mirror is a scoped scrape of a configured page list, gated by robots.txt
and by TDM reservations (D14 rule 8).

Everything downstream reads these mirrors and never the live sites: a checklist built from
a pinned `MirrorState.version` is reproducible, and two small community-run resources are
hit once a month rather than once per query."""
import hashlib
import json
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import urlparse

from langatlas_finding_aids.channel import FindingAidChannel
from langatlas_finding_aids.config import MIRRORED_SOURCES, FindingAidsConfig
from langatlas_finding_aids.paths import MIRROR_ROOT
from langatlas_finding_aids.results import utc_now

MANIFEST_NAME = "manifest.json"


class MirrorMissing(FileNotFoundError):
    """A read asked for a mirror that has never been refreshed."""


class MirrorRefusedByRobots(RuntimeError):
    """robots.txt or a TDM reservation forbids fetching a configured page."""


class UnknownMirror(ValueError):
    """`refresh()` was called for a source that is queried live, not mirrored."""


@dataclass(frozen=True)
class MirrorState:
    source: str
    version: str
    refreshed_at: str
    item_count: int


def _dir(source: str, root: Path | None) -> Path:
    return (root or MIRROR_ROOT) / source


def mirror_state(source: str, *, root: Path | None = None) -> MirrorState | None:
    path = _dir(source, root) / MANIFEST_NAME
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    return MirrorState(source=data["source"], version=data["version"],
                       refreshed_at=data["refreshed_at"],
                       item_count=data["item_count"])


def require_mirror(source: str, *, root: Path | None = None) -> MirrorState:
    state = mirror_state(source, root=root)
    if state is None:
        raise MirrorMissing(
            f"no {source} mirror yet — run `langatlas-finding-aids mirror-refresh"
            f" --source {source}` (or the monthly-finding-aid-mirror-refresh job)."
            " Reads are never served live (D53).")
    return state


def _write_manifest(directory: Path, *, source: str, version: str,
                    items: dict[str, str]) -> MirrorState:
    directory.mkdir(parents=True, exist_ok=True)
    state = MirrorState(source=source, version=version, refreshed_at=utc_now(),
                        item_count=len(items))
    (directory / MANIFEST_NAME).write_text(
        json.dumps({**asdict(state), "items": items}, indent=2, sort_keys=True))
    return state


def _default_run_git(args: list[str], cwd: Path | None = None) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True,
                          text=True).stdout


def refresh_pldb(ctx, *, config: FindingAidsConfig | None = None,
                 root: Path | None = None, run_git=None) -> MirrorState:
    """Clone on first run, fetch-and-reset afterwards. `version` is the mirrored commit —
    the thing a checklist cites to say which PLDB it was built from."""
    config = config or FindingAidsConfig.load()
    run_git = run_git or _default_run_git
    directory = _dir("pldb", root)
    repo = directory / "repo"
    if (repo / ".git").exists():
        run_git(["fetch", "--depth", "1", "origin", "HEAD"], cwd=repo)
        run_git(["reset", "--hard", "FETCH_HEAD"], cwd=repo)
    else:
        directory.mkdir(parents=True, exist_ok=True)
        run_git(["clone", "--depth", "1", config.pldb["repo_url"], str(repo)])
    version = run_git(["rev-parse", "HEAD"], cwd=repo).strip()
    items = {path.stem: path.name
             for path in sorted(repo.glob(config.pldb["concepts_glob"]))}
    state = _write_manifest(directory, source="pldb", version=version, items=items)
    ctx.writer.append(role="assistant",
                      content=f"pldb mirror at {version}, {state.item_count} concepts",
                      flags=["finding-aid-mirror"])
    return state


def _slug(page_path: str) -> str:
    return page_path.strip("/").replace("/", "_") or "index"


def refresh_hyperpolyglot(ctx, *, config: FindingAidsConfig | None = None,
                          root: Path | None = None, channel=None,
                          robots=None) -> MirrorState:
    """Fetch each configured page once, write it under `pages/`, and hash the lot into a
    version. The page list is configuration precisely so this stays a scoped fetch and
    never becomes a crawl."""
    config = config or FindingAidsConfig.load()
    settings = config.hyperpolyglot
    # A bare `refresh(source, ctx)` call (the CLI's `mirror-refresh` with no explicit
    # source, and Task 17's monthly job) never passes a channel — default-construct one
    # exactly the way `render_for_prompt` does, or every such call crashes on `get_raw`.
    channel = channel or FindingAidChannel(ctx, config=config)
    robots = robots or RobotsPolicy(settings["base_url"], config.user_agent,
                                    channel=channel)
    directory = _dir("hyperpolyglot", root)
    pages_dir = directory / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)
    items: dict[str, str] = {}
    for page_path in settings["pages"]:
        url = f"{settings['base_url']}{page_path}"
        if not robots.can_fetch(config.user_agent, url):
            raise MirrorRefusedByRobots(f"robots.txt disallows {url}")
        if robots.tdm_reservation(url):
            raise MirrorRefusedByRobots(f"TDM reservation set on {url}")
        html = channel.get_raw("hyperpolyglot", url, query_shape="mirror-page")
        (pages_dir / f"{_slug(page_path)}.html").write_text(html)
        items[_slug(page_path)] = hashlib.sha256(html.encode("utf-8")).hexdigest()
    version = hashlib.sha256(
        json.dumps(items, sort_keys=True).encode("utf-8")).hexdigest()[:12]
    state = _write_manifest(directory, source="hyperpolyglot", version=version,
                            items=items)
    ctx.writer.append(role="assistant",
                      content=f"hyperpolyglot mirror {version}, {state.item_count} pages",
                      flags=["finding-aid-mirror"])
    return state


class RobotsPolicy:
    """robots.txt plus the W3C TDM Reservation Protocol header, in one object so both
    checks are impossible to apply separately by accident (D14 rule 8)."""

    def __init__(self, base_url: str, user_agent: str, *, channel=None):
        from urllib.robotparser import RobotFileParser

        self._parser = RobotFileParser()
        parsed = urlparse(base_url)
        self._parser.set_url(f"{parsed.scheme}://{parsed.netloc}/robots.txt")
        self._parser.read()
        self._channel = channel
        self._user_agent = user_agent

    def can_fetch(self, user_agent: str, url: str) -> bool:
        return self._parser.can_fetch(user_agent, url)

    def tdm_reservation(self, url: str) -> bool:
        """A `tdm-reservation: 1` response header (or `X-Robots-Tag: noai`) means the
        publisher has opted out of text/data mining. We stop; there is no version of this
        project worth ignoring that for."""
        import httpx

        try:
            response = httpx.head(url, timeout=15, follow_redirects=True,
                                  headers={"user-agent": self._user_agent})
        except Exception:
            return False        # a HEAD that fails is the fetcher's problem, not a refusal
        headers = {k.lower(): str(v).lower() for k, v in response.headers.items()}
        return headers.get("tdm-reservation") == "1" or "noai" in headers.get(
            "x-robots-tag", "")


_REFRESHERS = {"pldb": refresh_pldb, "hyperpolyglot": refresh_hyperpolyglot}


def refresh(source: str, ctx, **kwargs) -> MirrorState:
    if source not in MIRRORED_SOURCES:
        raise UnknownMirror(
            f"{source} is queried live, not mirrored (mirrored: {MIRRORED_SOURCES})")
    return _REFRESHERS[source](ctx, **kwargs)
