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
