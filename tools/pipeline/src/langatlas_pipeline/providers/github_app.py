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
