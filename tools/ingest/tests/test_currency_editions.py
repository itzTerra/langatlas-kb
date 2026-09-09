from datetime import datetime, timedelta, timezone

from langatlas_ingest.currency.editions import (
    check_edition, check_url_for, interval_days, is_due,
)
from langatlas_ingest.currency.links import FetchedPage
from langatlas_ingest.verify.sources import SourceFacts

NOW = datetime(2026, 9, 8, tzinfo=timezone.utc)


def _facts(*, grounding="reference-implementation-docs", edition="3.14.7",
           check_url=None, url="https://example.test/ref") -> SourceFacts:
    custom = {"tier": "B", "grounding": grounding, "edition": edition}
    if check_url:
        custom["edition_check_url"] = check_url
    return SourceFacts(id="s1", tier="B", grounding=grounding, locator_kinds=(),
                       csl={"id": "s1", "URL": url, "custom": custom})


def test_formal_spec_keeps_the_quarterly_interval():
    assert interval_days("formal-spec") == 90


def test_every_other_grounding_shares_one_flat_shorter_interval():
    """§4.2: flat, with no per-implementation-speed variance — the three non-formal-spec
    groundings must not drift apart into a per-language cadence table."""
    intervals = {interval_days(g) for g in ("reference-implementation-docs",
                                            "design-doc", "third-party-reference")}
    assert intervals == {30}


def test_a_never_checked_source_is_always_due():
    assert is_due("formal-spec", None, now=NOW) is True


def test_due_only_after_the_interval_elapses():
    assert is_due("formal-spec", NOW - timedelta(days=89), now=NOW) is False
    assert is_due("formal-spec", NOW - timedelta(days=91), now=NOW) is True
    assert is_due("design-doc", NOW - timedelta(days=31), now=NOW) is True
    assert is_due("design-doc", NOW - timedelta(days=29), now=NOW) is False


def test_the_check_url_wins_over_the_record_url():
    assert check_url_for(_facts(check_url="https://example.test/whatsnew")) \
        == "https://example.test/whatsnew"


def test_the_record_url_is_the_fallback():
    assert check_url_for(_facts()) == "https://example.test/ref"


def test_a_source_with_no_url_at_all_is_uncheckable():
    assert check_url_for(_facts(url=None)) is None


def test_an_edition_still_on_the_page_matches():
    result = check_edition("s1", _facts(), fetch=lambda url: FetchedPage(
        200, "Python 3.14.7 documentation"))
    assert result.matched is True and result.fetched is True


def test_a_missing_edition_string_is_a_mismatch_with_a_readable_detail():
    result = check_edition("s1", _facts(), fetch=lambda url: FetchedPage(
        200, "Python 3.15.0 documentation"))
    assert result.matched is False
    assert "3.14.7" in result.detail and "example.test" in result.detail


def test_a_failed_fetch_is_not_a_mismatch():
    """An unreachable page says nothing about the edition. Filing a mismatch here would
    have the link-checker's job filed under the wrong reason, and the developer would
    triage an edition that never moved."""
    def _boom(url):
        raise ConnectionError("gone")

    result = check_edition("s1", _facts(), fetch=_boom)
    assert result.fetched is False and result.matched is True
    assert "could not be fetched" in result.detail


def test_matching_ignores_whitespace_and_case():
    result = check_edition("s1", _facts(edition="N3220"),
                           fetch=lambda url: FetchedPage(200, "draft   n3220 (2024)"))
    assert result.matched is True
