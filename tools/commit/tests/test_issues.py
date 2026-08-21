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
