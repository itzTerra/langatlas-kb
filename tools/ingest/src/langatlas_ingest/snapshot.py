import hashlib
import json
import shutil
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence
from ruamel.yaml import YAML
from langatlas_ingest import paths
from langatlas_ingest.errors import SnapshotMissing

_yaml = YAML(typ="safe")
_yaml.default_flow_style = False

_EXTENSIONS = {"application/pdf": ".pdf", "text/html": ".html", "text/plain": ".txt"}


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class Snapshot:
    source_id: str
    original_path: Path
    media_type: str
    content_hash: str
    retrieved_at: str
    source_url: str | None = None
    archive_url: str | None = None
    # The source record's `custom.locator_kinds` (§4.1), remembered here because it
    # materially determines every emitted `locator`/`locator_kind` for this source and
    # D1 requires that dropping the database and re-running ingestion from the snapshot
    # store reproduces it *exactly*. It used to live only in an ad-hoc `--locator-kinds`
    # CLI flag and was discarded after the run, so a re-ingest that forgot the flag
    # silently produced different locators — the public citation surface — than the
    # first one did. `None` means "never set": ingestion then falls back to
    # `pipeline.DEFAULT_LOCATOR_KINDS`.
    locator_kinds: list[str] | None = None


def savepagenow(url: str, *, client=None) -> str | None:
    """§4.1: web sources are archived on mint. Returns the archived permalink, or None
    if the Internet Archive did not give us one — never raises, because losing the
    source is worse than losing the archive link (which can be retried)."""
    import httpx

    owns_client = client is None
    client = client or httpx.Client(timeout=60, follow_redirects=True)
    try:
        response = client.get(f"https://web.archive.org/save/{url}")
    except Exception:
        return None
    finally:
        # Only close what we opened — an injected client belongs to its caller.
        if owns_client:
            client.close()
    location = response.headers.get("Content-Location")
    # Content-Location is untrusted external input: only trust a path-shaped value, or a
    # corrupt-but-plausible archive_url would replace the honest None retry signal.
    if response.status_code >= 400 or not location or not location.startswith("/"):
        return None
    return "https://web.archive.org" + location


class SnapshotStore:
    """The private tier (D15/§2.2): originals, extracted text, and QA reports on the dev
    machine under one directory, backed up as one tarball. Nothing here is ever committed."""

    def __init__(self, root: Path | None = None):
        # Resolved through the module, not a from-import, so tests (and a developer with
        # a relocated private tier) can repoint SNAPSHOT_ROOT without reimporting.
        self.root = Path(root) if root is not None else paths.SNAPSHOT_ROOT

    def dir_for(self, source_id: str) -> Path:
        return self.root / source_id

    def put(self, source_id: str, path: Path, *, media_type: str,
            source_url: str | None = None, archive_url: str | None = None,
            locator_kinds: Sequence[str] | None = None) -> Snapshot:
        target_dir = self.dir_for(source_id) / "original"
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / (Path(path).name or f"source{_EXTENSIONS.get(media_type, '')}")
        shutil.copyfile(path, target)
        snapshot = Snapshot(
            source_id=source_id, original_path=target, media_type=media_type,
            content_hash=hashlib.sha256(target.read_bytes()).hexdigest(),
            retrieved_at=utc_now(), source_url=source_url, archive_url=archive_url,
            locator_kinds=self._kinds_for(source_id, locator_kinds))
        self._write_manifest(snapshot)
        return snapshot

    def fetch_url(self, source_id: str, url: str, *, fetcher=None, archiver=None,
                  locator_kinds: Sequence[str] | None = None) -> Snapshot:
        fetcher = fetcher or _default_fetcher
        archiver = archiver or savepagenow
        body, media_type = fetcher(url)
        try:
            archive_url = archiver(url)
        except Exception:
            archive_url = None
        target_dir = self.dir_for(source_id) / "original"
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / f"fetched{_EXTENSIONS.get(media_type, '.bin')}"
        target.write_bytes(body)
        snapshot = Snapshot(
            source_id=source_id, original_path=target, media_type=media_type,
            content_hash=hashlib.sha256(body).hexdigest(), retrieved_at=utc_now(),
            source_url=url, archive_url=archive_url,
            locator_kinds=self._kinds_for(source_id, locator_kinds))
        self._write_manifest(snapshot)
        return snapshot

    def _kinds_for(self, source_id: str, locator_kinds: Sequence[str] | None):
        """Re-acquiring an original (a new edition, a re-fetch) must not silently forget
        the source's declared locator preference — that would change every locator it
        emits. An explicit argument wins; otherwise whatever the stored manifest already
        says is carried forward."""
        if locator_kinds is not None:
            return list(locator_kinds)
        try:
            return self.get(source_id).locator_kinds
        except SnapshotMissing:
            return None

    def set_locator_kinds(self, source_id: str, locator_kinds: Sequence[str]) -> Snapshot:
        """Record an explicit `--locator-kinds` override against an already-stored
        snapshot, so the next re-ingest reproduces this run rather than the one before it."""
        snapshot = self.get(source_id)
        snapshot.locator_kinds = list(locator_kinds)
        self._write_manifest(snapshot)
        return snapshot

    def sources(self) -> list[str]:
        """Every source with a stored snapshot, in id order — what makes "drop the
        database and regenerate it" (D1) a loop a command can run rather than a list the
        developer has to reconstruct from memory."""
        if not self.root.is_dir():
            return []
        return sorted(directory.name for directory in self.root.iterdir()
                      if (directory / "snapshot.yaml").exists())

    def get(self, source_id: str) -> Snapshot:
        manifest = self.dir_for(source_id) / "snapshot.yaml"
        if not manifest.exists():
            raise SnapshotMissing(source_id)
        data = _yaml.load(manifest.read_text())
        return Snapshot(original_path=self.dir_for(source_id) / "original" / data.pop("original"),
                        **data)

    def write_extracted(self, source_id: str, doc) -> Path:
        path = self.dir_for(source_id) / "extracted" / "document.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = asdict(doc)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=1))
        return path

    def read_extracted(self, source_id: str):
        from langatlas_ingest.extract import Block, ExtractedDocument

        path = self.dir_for(source_id) / "extracted" / "document.json"
        if not path.exists():
            raise SnapshotMissing(source_id)
        data = json.loads(path.read_text())
        blocks = [Block(**block) for block in data.pop("blocks")]
        return ExtractedDocument(blocks=blocks, **data)

    def write_qa(self, source_id: str, report) -> Path:
        directory = self.dir_for(source_id) / "qa"
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "report.json").write_text(json.dumps(report.to_dict(), indent=1))
        markdown = directory / "report.md"
        markdown.write_text(report.to_markdown())
        return markdown

    def _write_manifest(self, snapshot: Snapshot) -> None:
        data = asdict(snapshot)
        data["original"] = snapshot.original_path.name
        data.pop("original_path")
        directory = self.dir_for(snapshot.source_id)
        directory.mkdir(parents=True, exist_ok=True)
        with (directory / "snapshot.yaml").open("w") as handle:
            _yaml.dump(data, handle)


def _default_fetcher(url: str) -> tuple[bytes, str]:
    import httpx

    response = httpx.get(url, timeout=60, follow_redirects=True,
                         headers={"User-Agent": "langatlas-ingest/0.1 (+https://langatlas.dev)"})
    response.raise_for_status()
    media_type = response.headers.get("content-type", "text/html").split(";")[0].strip()
    return response.content, media_type
