from pathlib import Path
from langatlas_pipeline.costlog import CostRow, append_cost_row
from langatlas_pipeline.transcripts.writer import TranscriptWriter, utc_now


class CallRecorder:
    """The single code path that writes both a transcript event and its cost row (D26).
    Nothing else in the package appends to transcript.jsonl or cost-log.jsonl for a
    provider call — that is the whole point: the two files cannot disagree."""

    def __init__(self, writer: TranscriptWriter, cost_log_path: Path, run_id: str):
        self.writer = writer
        self.cost_log_path = cost_log_path
        self.run_id = run_id

    def record_call(self, *, endpoint: str, alias: str, resolved_model: str | None,
                    messages: list[dict], response_text: str | None, tokens_in: int,
                    tokens_out: int, latency_ms: int, cache_hit: bool, outcome: str,
                    prompt_id: str | None = None, prompt_version: str | None = None,
                    tokens_if_uncached: int | None = None, cost_usd: float | None = None,
                    agent: str | None = None, tool_call: dict | None = None) -> int:
        """Returns the seq of the last event written (the anchor a manifest can point at)."""
        for message in messages:
            self.writer.append(role=message["role"], content=str(message.get("content", "")),
                               agent=agent, model=resolved_model)
        if tool_call is not None:
            self.writer.append(role="assistant", content=response_text or "", agent=agent,
                               model=resolved_model, tool_name=tool_call["name"],
                               tool_args=tool_call.get("args"), tokens_in=tokens_in,
                               tokens_out=tokens_out, cache_hit=cache_hit)
        else:
            self.writer.append(role="assistant", content=response_text or "", agent=agent,
                               model=resolved_model, tokens_in=tokens_in,
                               tokens_out=tokens_out, cache_hit=cache_hit)
        append_cost_row(self.cost_log_path, CostRow(
            ts=utc_now(), run_id=self.run_id, seq=self.writer.seq, endpoint=endpoint,
            alias=alias, resolved_model=resolved_model, prompt_id=prompt_id,
            prompt_version=prompt_version, tokens_in=tokens_in, tokens_out=tokens_out,
            tokens_if_uncached=tokens_if_uncached, latency_ms=latency_ms,
            cache_hit=cache_hit, outcome=outcome, cost_usd=cost_usd,
        ))
        return self.writer.seq
