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
