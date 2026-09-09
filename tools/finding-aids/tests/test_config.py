import pytest

from langatlas_finding_aids.config import (
    ALL_SOURCES, FindingAidsConfig, UnknownFindingAidSource, UnknownTheme,
)
from langatlas_finding_aids import paths


def test_the_committed_config_loads():
    config = FindingAidsConfig.load()
    assert set(config.sources) <= set(ALL_SOURCES)
    assert config.user_agent.startswith("LangAtlas")


def test_every_configured_source_has_settings():
    config = FindingAidsConfig.load()
    for source in config.sources:
        assert config.settings(source), f"{source} has no settings block"


def test_an_unknown_source_is_a_typed_error():
    with pytest.raises(UnknownFindingAidSource):
        FindingAidsConfig.load().settings("stackoverflow")


def test_live_sources_declare_a_conservative_throttle():
    """D53 §O3: Wikidata and Wikipedia get real per-call throttles; neither publishes a
    hard quota, so the default has to be politely slow rather than absent."""
    config = FindingAidsConfig.load()
    for source in ("wikidata", "wikipedia"):
        assert config.min_interval(source) >= 1.0


def test_mirrored_sources_do_not_throttle_reads():
    config = FindingAidsConfig.load()
    assert config.min_interval("pldb") == 0.0


def test_at_least_one_theme_is_configured_and_shaped():
    config = FindingAidsConfig.load()
    theme = config.theme(next(iter(config.themes)))
    assert theme["label"] and theme["languages"] and theme["terms"]


def test_an_unknown_theme_is_a_typed_error():
    with pytest.raises(UnknownTheme):
        FindingAidsConfig.load().theme("no-such-theme")


def test_mirrors_live_in_the_private_tier():
    """D1: a mirror is derived data. It must never land under the repo root."""
    assert paths.REPO_ROOT not in paths.MIRROR_ROOT.parents
    assert paths.mirror_dir("pldb").name == "pldb"
