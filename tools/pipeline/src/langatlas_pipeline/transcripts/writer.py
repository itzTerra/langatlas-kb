from datetime import date, datetime, timezone
from pathlib import Path
from ruamel.yaml import YAML
from langatlas_pipeline import __version__
from langatlas_pipeline.paths import TRANSCRIPTS_ROOT
from langatlas_pipeline.transcripts.events import RunManifest, TranscriptEvent
from langatlas_pipeline.transcripts.redaction import scrub_secrets, truncate_tool_result

REDACTION_RULES_VERSION = "1"

_yaml = YAML()
_yaml.default_flow_style = False
_yaml.indent(mapping=2, sequence=4, offset=2)


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def run_dir_for(run_id: str, *, root: Path | None = None) -> Path:
    """Storage is sharded YYYY/MM/<run_id>/ (D18)."""
    root = root or TRANSCRIPTS_ROOT
    year, month = run_id[:4], run_id[5:7]
    return root / year / month / run_id


def mint_run_id(kind: str, slug: str, *, root: Path | None = None,
                today: date | None = None) -> str:
    """run_id = <date>-<kind>-<slug>-<seq> (D18). `seq` disambiguates same-day runs of the
    same kind+slug and is derived from what is already on disk, so it survives restarts."""
    root = root or TRANSCRIPTS_ROOT
    day = (today or datetime.now(timezone.utc).date()).isoformat()
    prefix = f"{day}-{kind}-{slug}-"
    shard = root / day[:4] / day[5:7]
    existing = sorted(p.name for p in shard.glob(f"{prefix}*")) if shard.exists() else []
    return f"{prefix}{len(existing) + 1:02d}"


class TranscriptWriter:
    """Appends events to transcript.jsonl and owns manifest.yaml. Every event passes the
    secret scrub; tool results additionally pass the copyright truncation rule."""

    def __init__(self, run_dir: Path, manifest: RunManifest):
        self.run_dir = run_dir
        self.manifest = manifest
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self._path = self.run_dir / "transcript.jsonl"
        self._path.touch()
        self._seq = 0

    def append(self, *, role: str, content: str, agent: str | None = None,
               model: str | None = None, tool_name: str | None = None,
               tool_args: dict | None = None, source_id: str | None = None,
               tokens_in: int = 0, tokens_out: int = 0, cache_hit: bool = False,
               flags: list[str] | None = None) -> TranscriptEvent:
        flags = list(flags or [])
        result_ref = None
        if role == "tool":
            content, result_ref = truncate_tool_result(content, source_id=source_id)
            if result_ref["truncated"]:
                flags.append("truncated")
        content, secret_kinds = scrub_secrets(content)
        if secret_kinds:
            flags.append("secret-scrubbed")
        self._seq += 1
        event = TranscriptEvent(
            seq=self._seq, ts=utc_now(), role=role, content=content, agent=agent,
            model=model,
            tool_call={"name": tool_name, "args": tool_args or {}} if tool_name else None,
            tool_result_ref=result_ref, tokens_in=tokens_in, tokens_out=tokens_out,
            cache_hit=cache_hit, flags=flags,
        )
        with self._path.open("a", encoding="utf-8") as fh:
            fh.write(event.to_json() + "\n")
        return event

    @property
    def seq(self) -> int:
        return self._seq

    def finalize(self, *, ended: str | None = None, **manifest_updates) -> Path:
        self.manifest.ended = ended or utc_now()
        self.manifest.wrapper_version = __version__
        self.manifest.redaction = {"status": "applied",
                                   "rules_version": REDACTION_RULES_VERSION}
        self.manifest.files = ["transcript.jsonl"]
        self.manifest.stats = {**self.manifest.stats, "events": self._seq}
        for key, value in manifest_updates.items():
            setattr(self.manifest, key, list(value) if isinstance(value, tuple) else value)
        path = self.run_dir / "manifest.yaml"
        with path.open("w", encoding="utf-8") as fh:
            _yaml.dump(self.manifest.as_dict(), fh)
        return path
