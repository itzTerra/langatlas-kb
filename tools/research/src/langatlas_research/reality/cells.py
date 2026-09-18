"""A reality-check cell -> the `InstanceDraft` that renders it.

The draft's provenance names the *classifier* session — the chat that produced the answer (D18)
— not the verify run that checked it. R5 lands nothing (D68); the rendering exists so the gate
verifies exactly the record a sweep would commit."""
from langatlas_research.draft.evidence import as_drafts
from langatlas_research.drafts import (
    Characteristic, InstanceDraft, InstanceNote, Proposer, SyntaxExample,
)

# The agent name is also its prompt id, matching 3C's convention.
AGENT = "r5-reality-checker"


def cell_draft(cell: dict, *, record: dict) -> InstanceDraft:
    """@raises KeyError: the cell's language has no classifier run in the record."""
    run = record["runs"]["classify"][cell["language"]]
    proposal = cell["proposal"]
    return InstanceDraft(
        language=cell["language"], feature=cell["feature"], status=cell["answer"],
        evidence=as_drafts(proposal["sources"]),
        proposer=Proposer(agent=AGENT, model=run["model"],
                          prompt_version=run["prompt_version"]),
        chat_run_id=run["run_id"], absence_scope=proposal.get("absence_scope"),
        since=proposal.get("since"),
        notes=tuple(InstanceNote(key=n["key"], type=n["type"], text=n["text"],
                                 evidence=as_drafts(n["sources"]))
                    for n in proposal.get("notes") or []),
        characteristics=tuple(Characteristic(key=c["key"], text=c["text"],
                                             evidence=as_drafts(c["sources"]))
                              for c in proposal.get("characteristics") or []),
        syntax=tuple(SyntaxExample(key=s["key"], title=s["title"], code=s["code"],
                                   evidence=as_drafts(s["sources"]))
                     for s in proposal.get("syntax") or []))
