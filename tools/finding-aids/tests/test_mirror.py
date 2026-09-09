import json

import pytest

from langatlas_finding_aids import mirror
from langatlas_finding_aids.channel import FindingAidChannel
from langatlas_finding_aids.config import FindingAidsConfig


class _Ctx:
    def __init__(self):
        self.run_id = "run-1"
        self.logged = []

    def writer_append(self, **event):
        self.logged.append(event)

    class _W:
        def __init__(self, outer):
            self.outer = outer

        def append(self, **event):
            self.outer.logged.append(event)

    @property
    def writer(self):
        return self._W(self)


class _Channel:
    def __init__(self, pages):
        self.pages, self.fetched = pages, []

    def get_raw(self, source, url, *, params=None, query_shape, version=None):
        self.fetched.append(url)
        return self.pages[url]


class _Robots:
    def __init__(self, allowed=True, tdm_reserved=False):
        self.allowed, self.tdm_reserved = allowed, tdm_reserved

    def can_fetch(self, user_agent, url):
        return self.allowed

    def tdm_reservation(self, url):
        return self.tdm_reserved


@pytest.fixture
def config():
    return FindingAidsConfig.load()


def test_no_mirror_yet_reads_as_none(tmp_path):
    assert mirror.mirror_state("pldb", root=tmp_path) is None


def test_require_mirror_raises_a_typed_error_rather_than_live_fetching(tmp_path):
    """D53: all reads are served from mirrors. A missing mirror must be loud — a silent
    live fetch would make a checklist irreproducible and hit a small community site on
    every query."""
    with pytest.raises(mirror.MirrorMissing, match="mirror-refresh"):
        mirror.require_mirror("pldb", root=tmp_path)


def test_refresh_pldb_clones_then_fetches_and_records_the_commit(tmp_path, config):
    calls = []

    def run_git(args, cwd=None):
        calls.append((args, cwd))
        if args[0] == "rev-parse":
            return "abc1234def\n"
        if args[0] == "clone":
            (tmp_path / "pldb" / "repo" / "concepts").mkdir(parents=True)
            (tmp_path / "pldb" / "repo" / "concepts" / "rust.scroll").write_text("id rust\n")
        return ""

    state = mirror.refresh_pldb(_Ctx(), config=config, root=tmp_path, run_git=run_git)

    assert calls[0][0][0] == "clone"
    assert state.version == "abc1234def" and state.item_count == 1
    manifest = json.loads((tmp_path / "pldb" / "manifest.json").read_text())
    assert manifest["source"] == "pldb" and manifest["version"] == "abc1234def"


def test_a_second_refresh_fetches_instead_of_recloning(tmp_path, config):
    (tmp_path / "pldb" / "repo" / ".git").mkdir(parents=True)
    (tmp_path / "pldb" / "repo" / "concepts").mkdir(parents=True)
    (tmp_path / "pldb" / "repo" / "concepts" / "rust.scroll").write_text("id rust\n")
    seen = []

    def run_git(args, cwd=None):
        seen.append(args[0])
        return "deadbee\n" if args[0] == "rev-parse" else ""

    state = mirror.refresh_pldb(_Ctx(), config=config, root=tmp_path, run_git=run_git)
    assert "clone" not in seen and "fetch" in seen
    assert state.version == "deadbee"


def test_refresh_hyperpolyglot_writes_one_file_per_configured_page(tmp_path, config):
    pages = {f"{config.hyperpolyglot['base_url']}{path}": f"<html>{path}</html>"
             for path in config.hyperpolyglot["pages"]}
    channel = _Channel(pages)
    state = mirror.refresh_hyperpolyglot(_Ctx(), config=config, root=tmp_path,
                                         channel=channel, robots=_Robots())
    written = sorted(p.name for p in (tmp_path / "hyperpolyglot" / "pages").iterdir())
    assert len(written) == len(config.hyperpolyglot["pages"])
    assert state.item_count == len(written)


def test_a_disallowed_page_is_skipped_not_fetched(tmp_path, config):
    channel = _Channel({})
    with pytest.raises(mirror.MirrorRefusedByRobots):
        mirror.refresh_hyperpolyglot(_Ctx(), config=config, root=tmp_path,
                                     channel=channel, robots=_Robots(allowed=False))
    assert channel.fetched == []


def test_a_tdm_reservation_is_honoured(tmp_path, config):
    """D14 rule 8: a TDM opt-out is a refusal, and this project respects it even where
    robots.txt alone would allow the fetch."""
    channel = _Channel({})
    with pytest.raises(mirror.MirrorRefusedByRobots, match="TDM"):
        mirror.refresh_hyperpolyglot(_Ctx(), config=config, root=tmp_path,
                                     channel=channel, robots=_Robots(tdm_reserved=True))
    assert channel.fetched == []


def test_the_version_changes_when_a_page_changes(tmp_path, config):
    base = config.hyperpolyglot["base_url"]
    first = {f"{base}{p}": "<html>a</html>" for p in config.hyperpolyglot["pages"]}
    second = dict(first)
    second[f"{base}{config.hyperpolyglot['pages'][0]}"] = "<html>b</html>"
    v1 = mirror.refresh_hyperpolyglot(_Ctx(), config=config, root=tmp_path,
                                      channel=_Channel(first), robots=_Robots()).version
    v2 = mirror.refresh_hyperpolyglot(_Ctx(), config=config, root=tmp_path,
                                      channel=_Channel(second), robots=_Robots()).version
    assert v1 != v2


def test_refresh_dispatches_by_source_name(tmp_path, config):
    with pytest.raises(mirror.UnknownMirror):
        mirror.refresh("wikidata", _Ctx(), config=config, root=tmp_path)


class _FullCtx:
    """Unlike `_Ctx` above, this stands in for everything `FindingAidChannel` itself
    needs (`check_budget`, `note_usage`, `cache`) — required only when a test exercises
    the channel's *default construction* rather than injecting a pre-built `_Channel`."""

    def __init__(self):
        self.run_id = "run-1"
        self.cache = None
        self.checks = []
        self.usage = []
        self.logged = []

    def check_budget(self, **kwargs):
        self.checks.append(kwargs)

    def note_usage(self, **kwargs):
        self.usage.append(kwargs)

    class _W:
        def __init__(self, outer):
            self.outer = outer

        def append(self, **event):
            self.outer.logged.append(event)

    @property
    def writer(self):
        return self._W(self)


class _NoThrottle:
    def run(self, call):
        return call()


class _FakeHttpClient:
    """The minimal `httpx.Client`-shaped surface `FindingAidChannel._http()` calls
    through — injected via the `client=` kwarg `FindingAidChannel` already accepts."""

    def __init__(self, pages):
        self.pages, self.calls = pages, []

    def get(self, url, params=None, headers=None):
        self.calls.append(url)
        return self._Response(self.pages[url])

    class _Response:
        def __init__(self, text):
            self.text = text

        def raise_for_status(self):
            pass


def test_refresh_hyperpolyglot_default_constructs_a_channel_when_none_given(
        tmp_path, config, monkeypatch):
    """A bare `refresh(source, ctx)` — exactly what the CLI's `mirror-refresh` (Task 15)
    and the monthly job's `_run_item` (Task 17) both call — passes no `channel`. The
    default-construction path has to actually work rather than leave `channel` as `None`
    and crash on the first `get_raw`."""
    base = config.hyperpolyglot["base_url"]
    pages = {f"{base}{path}": f"<html>{path}</html>"
             for path in config.hyperpolyglot["pages"]}
    client = _FakeHttpClient(pages)
    monkeypatch.setattr(
        mirror, "FindingAidChannel",
        lambda ctx, **kw: FindingAidChannel(ctx, config=kw.get("config") or config,
                                            client=client, throttle=_NoThrottle()))

    state = mirror.refresh_hyperpolyglot(_FullCtx(), config=config, root=tmp_path,
                                         robots=_Robots())

    assert state.source == "hyperpolyglot"
    assert state.item_count == len(config.hyperpolyglot["pages"])
    assert sorted(client.calls) == sorted(pages)
