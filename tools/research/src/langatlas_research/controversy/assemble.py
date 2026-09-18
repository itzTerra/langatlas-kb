"""Canonical store + ledgers -> §6.4's five structured inputs, for one derived fact.

Assembly is allow-list construction, exactly like D24's `whitelist_payload`: a record carries
prose, provenance, a proposer and a `detail` string, and the way to keep those away from the
assessor is to never assemble them. Nothing here calls a model, so it is fully testable
without a provider — which matters, because this is where §6.4's exclusions actually live."""
from dataclasses import dataclass
from pathlib import Path

from langatlas_ingest.verify.sources import are_independent
from langatlas_ingest.verify.verdicts import ADMITTING_VERDICTS

from langatlas_research.controversy.inputs import ControversyInputs

# Claim kind -> the `field` name 2B's cases use. `base` is the default for a fact whose claim
# *is* the record's load-bearing assertion; the rest name the field they belong to, which is
# how §6.4's "partials on load-bearing fields" distinction stays mechanical.
_FIELD_OF_KIND = {
    "node-definition": "base",
    "instance-exists": "base",
    "edge-exists": "base",
    "rule-exists": "base",
    "characteristic": "characteristic",
    "syntax-valid": "syntax",
    "edge-polarity": "polarity",
    "quality-assessment": "quality-assessment",
}


@dataclass(frozen=True)
class AssembleDeps:
    """Everything assembly reads, gathered once per run rather than per fact — a nightly
    batch over the whole store would otherwise re-read every source record thousands of
    times."""

    ledger: object                       # VerdictLedger (duck-typed: `latest_for`)
    source_facts: dict                   # source_id -> SourceFacts
    contradictions: list                 # contradictions.yaml records
    debates: dict                        # debate_id -> debate record


def fact_field(claim: str) -> str:
    """@param claim: the canonical claim string (§3.5), which always opens with its kind.
    @returns the `field` name this fact's verdict rows carry; `base` for an unknown kind, the
        conservative direction — an unknown field treated as load-bearing over-reports
        controversy rather than hiding it."""
    kind = claim.split("(", 1)[0]
    return _FIELD_OF_KIND.get(kind, "base")


def _citation_index(fact: dict, pair) -> int:
    """1-based position of the pair's citation in the fact's own `sources:` list.

    Positional rather than by source id because 2B's cases number citations, and because one
    source can legitimately back a fact at two different locators."""
    for index, entry in enumerate(fact.get("sources") or [], start=1):
        if entry.get("source") == pair.source_id and entry.get("locator") == pair.locator:
            return index
    return 0                              # a verdict for a citation the record no longer lists


def verdict_rows(fact: dict, pairs, source_facts: dict) -> list[dict]:
    """One row per (citation, field). A pair contributes its base row always, and a second
    `since` row whenever the verifier decided a `since_status` for it."""
    rows = []
    field = fact_field(fact["claim"])
    for pair in pairs:
        tier = getattr(source_facts.get(pair.source_id), "tier", "")
        index = _citation_index(fact, pair)
        rows.append({"fact": fact["fact_id"], "citation": index, "verdict": pair.verdict,
                     "field": field, "tier": tier})
        if pair.since_status:
            rows.append({"fact": fact["fact_id"], "citation": index,
                         "verdict": "supported" if pair.since_status == "since-supported"
                                    else "partial",
                         "field": "since", "tier": tier})
    return sorted(rows, key=lambda row: (row["citation"], row["field"]))


def source_strength(pairs, source_facts: dict) -> dict:
    """§6.4's "mechanically-computed source-strength context", in 2B's exact three keys.

    Only *supporting* citations count: a contradicted tier-A citation is a disagreement
    signal, not backing, and counting it as strength would let a fact look better evidenced
    the more its sources fight. Independence reuses §6.3's check verbatim rather than a second
    copy of the rule."""
    supporting = sorted({pair.source_id for pair in pairs
                         if pair.verdict in ADMITTING_VERDICTS and pair.source_id in source_facts})
    tiers = [source_facts[s].tier for s in supporting]
    corroborations = sum(
        1 for s in supporting
        if any(are_independent(source_facts[s], source_facts[other])
               for other in supporting if other != s))
    return {"tier_a": tiers.count("A"), "tier_b": tiers.count("B"),
            "independent_corroborations": corroborations}


def contradiction_projection(record: dict) -> dict:
    """The only four fields of a contradiction record the assessor may see.

    `detail` is agent-written prose, `chat_run_id` is a transcript pointer, `mechanism` says
    who minted it — none is a disagreement measurement. `closure` is dropped outright: per the
    2026-07-20 withdrawal an open record's `closure_attempt.outcome: confirmed-open` is
    human-challenge-derived and the assessor must not see it, and dropping the whole closure
    block is the version of that rule nobody can forget half of.

    `status: confirmed-open` is the same signal wearing the record's own `status` field instead
    of `closure` — it is set only via human-challenge resolution (`mechanism:
    challenge-resolution`, `closure.method: human-adjudication`) — so it is mapped down to a
    plain `open` here too. The assessor must never see that a human specifically re-confirmed a
    contradiction; an ordinary open contradiction is all the signal it is allowed."""
    status = "open" if record["status"] == "confirmed-open" else record["status"]
    return {"id": record["id"], "type": record["type"], "status": status,
            "participants": len(record.get("participants") or [])}


def _mentions(record: dict, fact: dict, record_id: str | None) -> bool:
    """True when a contradiction record names this fact, one of its citations, or the record
    that owns it. §6.5's participants are `citation:<source>:<locator>` strings or record ids."""
    participants = set(record.get("participants") or [])
    if fact["fact_id"] in participants or (record_id and record_id in participants):
        return True
    return any(f"citation:{e.get('source')}:{e.get('locator')}" in participants
               for e in fact.get("sources") or [])


def assessment_spread(record: dict, *, min_assessments: int = 2) -> dict:
    """The spread of attributed quality assessments on an `affects-quality` edge (§3.4: "no
    forced consensus" — the record keeps every assessor's view, and disagreement among them is
    exactly what level 2 is about).

    Keyed `<quality-id>_edge_strength`, matching 2B's `quality_edge_strength` /
    `readability_edge_strength` shape. A single assessment is not a spread."""
    assessments = record.get("assessments") or []
    if len(assessments) < min_assessments:
        return {}
    quality = record.get("to") or "quality"
    key = f"{quality}_edge_strength"
    return {key: sorted(f"{a['polarity']}:{a['strength']}" if a.get("polarity") else a["strength"]
                        for a in assessments)}


def assemble_inputs(fact: dict, *, record: dict, ledger, source_facts: dict,
                    contradictions: list, debates: dict,
                    spread_min_assessments: int = 2) -> ControversyInputs:
    """Build one fact's structured inputs.

    @param fact: one `derive_facts` row (`fact_id`, `claim`, `record_path`, `sources`).
    @param record: the owning record's data, read for `provenance.debate_id`, `id` and (for an
        `affects-quality` edge) `assessments` — and for nothing else.
    @param debates: debate_id -> debate record. A debate id with no record is ignored: a
        deleted debate is a missing signal, not a reason to fail a nightly batch.
    @returns the inputs, guaranteed to carry exactly §6.4's five keys."""
    from langatlas_research.draft.debate_record import as_controversy_input

    pairs = ledger.latest_for(fact["fact_id"])
    debate_id = (record.get("provenance") or {}).get("debate_id")
    debate = debates.get(debate_id) if debate_id else None
    return ControversyInputs.from_mapping({
        "debates": [as_controversy_input(debate)] if debate else [],
        "contradiction_records": [contradiction_projection(c) for c in contradictions
                                  if _mentions(c, fact, record.get("id"))],
        "verdicts": verdict_rows(fact, pairs, source_facts),
        "source_strength": source_strength(pairs, source_facts),
        "assessment_spread": assessment_spread(record,
                                               min_assessments=spread_min_assessments),
    })


def load_deps(repo_root: Path, ledger) -> AssembleDeps:
    """Gather the run-wide inputs once. Sources and contradictions are read from git, never
    from Postgres — tier and dispute state are canonical data (D1)."""
    from langatlas_ingest.verify.contradictions import load_records
    from langatlas_ingest.verify.sources import load_source_facts
    from langatlas_research.draft.debate_record import iter_debates

    return AssembleDeps(
        ledger=ledger,
        source_facts=load_source_facts(Path(repo_root) / "sources"),
        contradictions=load_records(Path(repo_root) / "contradictions.yaml"),
        debates={d["id"]: d for d in iter_debates(repo_root)})


def record_facts(path: Path, kind: str, text: str, data: dict) -> list[dict]:
    """The derived facts of one record — the assessor's work list for that file.

    Wraps `derive_facts`' whole-store signature for the single-record case so the nightly job
    never has to re-derive the entire store to assess one file."""
    from langatlas_validate.compile import derive_facts

    return derive_facts([(path, kind, text, data)])
