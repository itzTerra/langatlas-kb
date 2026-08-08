import hashlib
import json
import pytest
from langatlas_ingest.errors import SnapshotMissing
from langatlas_ingest.snapshot import SnapshotStore, savepagenow


def test_put_copies_the_original_and_records_its_hash(snapshot_root, tmp_path):
    pdf = tmp_path / "book.pdf"
    pdf.write_bytes(b"%PDF-1.7 fake")
    store = SnapshotStore(snapshot_root)

    snap = store.put("pierce-2002", pdf, media_type="application/pdf")

    assert snap.original_path.read_bytes() == b"%PDF-1.7 fake"
    assert snap.content_hash == hashlib.sha256(b"%PDF-1.7 fake").hexdigest()
    assert snap.retrieved_at.endswith("Z")
    assert (snapshot_root / "pierce-2002" / "snapshot.yaml").exists()
    # the original must never leave the private tier
    assert snapshot_root in snap.original_path.parents


def test_get_round_trips_the_manifest(snapshot_root, tmp_path):
    pdf = tmp_path / "book.pdf"
    pdf.write_bytes(b"x")
    store = SnapshotStore(snapshot_root)
    store.put("s", pdf, media_type="application/pdf", source_url="https://example.org/s")

    snap = store.get("s")
    assert snap.source_url == "https://example.org/s"
    assert snap.media_type == "application/pdf"


def test_get_raises_for_an_unstored_source(snapshot_root):
    with pytest.raises(SnapshotMissing):
        SnapshotStore(snapshot_root).get("never-ingested")


def test_fetch_url_archives_on_mint(snapshot_root):
    calls = {}

    def fake_fetcher(url):
        calls["fetched"] = url
        return b"<html><body><h1>Match expressions</h1></body></html>", "text/html"

    def fake_archiver(url):
        calls["archived"] = url
        return "https://web.archive.org/web/2026/https://example.org/ref"

    store = SnapshotStore(snapshot_root)
    snap = store.fetch_url("rust-reference", "https://example.org/ref",
                           fetcher=fake_fetcher, archiver=fake_archiver)

    assert calls == {"fetched": "https://example.org/ref",
                     "archived": "https://example.org/ref"}
    assert snap.archive_url.startswith("https://web.archive.org/")
    assert snap.media_type == "text/html"


def test_fetch_url_survives_a_dead_archiver(snapshot_root):
    """§4.1 wants an archive on mint, but a SavePageNow outage must not lose the source.
    The snapshot lands with archive_url = None and the caller can retry later."""
    store = SnapshotStore(snapshot_root)
    snap = store.fetch_url("s", "https://example.org/x",
                           fetcher=lambda url: (b"<html/>", "text/html"),
                           archiver=lambda url: (_ for _ in ()).throw(RuntimeError("503")))
    assert snap.archive_url is None


def test_savepagenow_returns_the_archived_permalink():
    class FakeResponse:
        status_code = 200
        headers = {"Content-Location": "/web/20260808/https://example.org/x"}

    class FakeClient:
        def get(self, url, **kwargs):
            assert url.startswith("https://web.archive.org/save/")
            return FakeResponse()

    assert savepagenow("https://example.org/x", client=FakeClient()) == (
        "https://web.archive.org/web/20260808/https://example.org/x")


def test_savepagenow_returns_none_for_a_bad_status():
    class FakeResponse:
        status_code = 404
        headers = {"Content-Location": "/web/20260808/https://example.org/x"}

    class FakeClient:
        def get(self, url, **kwargs):
            return FakeResponse()

    assert savepagenow("https://example.org/x", client=FakeClient()) is None


def test_savepagenow_returns_none_without_a_content_location():
    class FakeResponse:
        status_code = 200
        headers = {}

    class FakeClient:
        def get(self, url, **kwargs):
            return FakeResponse()

    assert savepagenow("https://example.org/x", client=FakeClient()) is None


def test_savepagenow_rejects_a_malformed_content_location():
    """Content-Location is untrusted external input; a value that isn't a path (e.g. an
    absolute URL to somewhere else) must not be silently trusted into archive_url."""
    class FakeResponse:
        status_code = 200
        headers = {"Content-Location": "https://evil.example.org/not-a-path"}

    class FakeClient:
        def get(self, url, **kwargs):
            return FakeResponse()

    assert savepagenow("https://example.org/x", client=FakeClient()) is None


def test_extracted_document_round_trips(snapshot_root, tmp_path):
    from langatlas_ingest.extract import Block, ExtractedDocument

    store = SnapshotStore(snapshot_root)
    pdf = tmp_path / "b.pdf"
    pdf.write_bytes(b"x")
    store.put("s", pdf, media_type="application/pdf")
    doc = ExtractedDocument(source_id="s", media_type="application/pdf", backend="fake",
                            backend_version="0", page_count=1,
                            blocks=[Block(text="Hello", page=1, heading_level=1)],
                            outline=["Hello"])

    path = store.write_extracted("s", doc)
    assert json.loads(path.read_text())["blocks"][0]["text"] == "Hello"
    assert store.read_extracted("s").blocks[0].page == 1
