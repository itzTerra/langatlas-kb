"""D45's debate-outcome minting path — one of the register's four legal writers.

What mints: a debate whose moderator found that two *sourced* positions genuinely disagree and
that nothing in either source dissolves it. What does not: a disagreement between the agents. A
debate is an argument about a carve; the register is a record of the literature disagreeing, and
conflating the two would fill it with process noise and mislead 3D's assessor, which reads open
records as a controversy signal.

An escalated debate mints nothing either: `escalate` means the evidence on the table could not
settle the question, which is not the same as the sources contradicting each other. The developer
rules first; if the ruling is that the sources disagree, the debate is re-run to record it.

`type: verification` rather than `cross-fact`: §6.5's `cross-fact` type is for two independently
verified *facts* disagreeing, which needs the fact-embedding index that arrives in Stage 5. What
R4 finds is a claim at odds with a citation, which is exactly the verification type."""
from datetime import date as _date
from pathlib import Path

from langatlas_ingest.verify.contradictions import load_records, write_records
from langatlas_research.draft.debate_record import save_debate
from langatlas_research.mint import MintedRecord, content_digest
from langatlas_validate.ids import contradiction_key

CONTRADICTIONS_REL = "contradictions.yaml"


def _path(repo_root: Path | None) -> Path:
    return (Path(repo_root) if repo_root else Path(".")) / CONTRADICTIONS_REL


def mint_debate_contradiction(debate: dict, *, repo_root: Path | None = None,
                              today: str | None = None) -> str | None:
    """@returns: the contradiction id this debate is responsible for, or None when the
        resolution asked for none (or asked for one an escalated debate may not mint).
    @raises ValueError: a participant that is not a `citation:<source_id>:<locator>` or a
        record id — the register records sources disagreeing, never agents."""
    resolution = debate["resolution"]
    request = resolution.get("contradiction")
    if not request or resolution["outcome"] == "escalated":
        return None

    participants = sorted(request["participants"])
    for participant in participants:
        if not (participant.startswith("citation:") or participant.startswith("f-")
                or participant.startswith("edge.") or participant.startswith("rule-")):
            raise ValueError(
                f"{debate['id']}: {participant!r} is not a citation or a record id. D45's"
                f" register records sources disagreeing, not participants disagreeing.")

    record_id = contradiction_key(participants)
    path = _path(repo_root)
    records = load_records(path)
    if not any(record.get("id") == record_id for record in records):
        records.append({
            "id": record_id, "type": "verification", "participants": participants,
            "status": "open", "mechanism": "reconciler",
            "minted": today or _date.today().isoformat(),
            "chat_run_id": debate["runs"].get("moderator") or debate["runs"]["debate"],
            "detail": request["detail"]})
        write_records(records, path)

    stamped = {**debate, "resolution": {**resolution, "contradiction_id": record_id}}
    save_debate(stamped, repo_root=repo_root)
    return record_id


def contradictions_mint(repo_root: Path | None = None) -> MintedRecord:
    """The ledger as a shared-file `MintedRecord`, so `land_drafts` lands it in the same batch
    as the records that caused it — and re-renders it if someone else's contradiction lands
    first, which is exactly what `base_digest` is for."""
    path = _path(repo_root)
    text = path.read_text()
    return MintedRecord(path=CONTRADICTIONS_REL, text=text, kind="contradictions",
                        node_ids=(), base_digest=content_digest(text))
