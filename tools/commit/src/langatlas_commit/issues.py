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
