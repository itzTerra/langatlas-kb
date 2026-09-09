from langatlas_ingest.currency.links import FetchedPage, check_link, content_hash


def _fetcher(pages, *, fail_times=0):
    """A fetcher that fails its first `fail_times` calls, then serves `pages`."""
    state = {"calls": 0}

    def fetch(url):
        state["calls"] += 1
        if state["calls"] <= fail_times:
            raise ConnectionError("boom")
        return pages[url]

    fetch.state = state
    return fetch


PAGE = FetchedPage(status=200, text='<h2 id="lexical">Lexical analysis</h2> body text')


def test_a_resolving_page_with_no_fragment_has_no_findings():
    result = check_link("s1", "https://example.test/ref", fetch=_fetcher(
        {"https://example.test/ref": PAGE}))
    assert result.resolves is True
    assert result.anchor is None and result.anchor_present is None
    assert result.findings == ()


def test_a_missing_anchor_is_its_own_finding_on_a_page_that_still_resolves():
    result = check_link("s1", "https://example.test/ref#gone", fetch=_fetcher(
        {"https://example.test/ref#gone": PAGE}))
    assert result.resolves is True
    assert result.anchor == "gone" and result.anchor_present is False
    assert result.findings == ("anchor-missing",)


def test_a_present_anchor_is_found_by_id_or_name():
    fetch = _fetcher({"https://example.test/ref#lexical": PAGE})
    assert check_link("s1", "https://example.test/ref#lexical",
                      fetch=fetch).anchor_present is True


def test_content_drift_is_reported_against_the_previous_hash():
    result = check_link("s1", "https://example.test/ref",
                        fetch=_fetcher({"https://example.test/ref": PAGE}),
                        previous_hash="stale-hash")
    assert result.drifted is True
    assert result.findings == ("content-drift",)


def test_a_first_ever_check_is_never_drift():
    """No previous observation is not a change. Reporting drift here would open a
    queue entry for every source the first time the job ever runs."""
    result = check_link("s1", "https://example.test/ref",
                        fetch=_fetcher({"https://example.test/ref": PAGE}),
                        previous_hash=None)
    assert result.drifted is False and result.findings == ()


def test_hashing_ignores_whitespace_reflow():
    assert content_hash("a  b\n c") == content_hash("a b c")


def test_one_retry_before_flagging_dead():
    fetch = _fetcher({"https://example.test/ref": PAGE}, fail_times=1)
    result = check_link("s1", "https://example.test/ref", fetch=fetch)
    assert fetch.state["calls"] == 2
    assert result.resolves is True and result.findings == ()


def test_two_failures_flag_dead_and_stop():
    fetch = _fetcher({}, fail_times=99)
    result = check_link("s1", "https://example.test/ref", fetch=fetch)
    assert fetch.state["calls"] == 2
    assert result.resolves is False and result.findings == ("link-dead",)
    assert result.content_hash is None


def test_a_404_is_dead_without_a_content_hash():
    fetch = _fetcher({"https://example.test/ref": FetchedPage(status=404, text="nope")})
    result = check_link("s1", "https://example.test/ref", fetch=fetch)
    assert result.resolves is False and result.http_status == 404
    assert result.findings == ("link-dead",)


def test_signals_are_independent_and_all_reported():
    """A page that still resolves can lose an anchor *and* drift; §4.4 asks for three
    independent signals, so one finding must never shadow another."""
    fetch = _fetcher({"https://example.test/ref#gone": PAGE})
    result = check_link("s1", "https://example.test/ref#gone", fetch=fetch,
                        previous_hash="stale-hash")
    assert result.findings == ("anchor-missing", "content-drift")
