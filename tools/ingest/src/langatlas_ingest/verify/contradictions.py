import re
from datetime import date as _date
from pathlib import Path
from ruamel.yaml import YAML
from langatlas_ingest.paths import CONTRADICTIONS_PATH
from langatlas_validate.ids import contradiction_key

_read_yaml = YAML(typ="safe")
_write_yaml = YAML()
_write_yaml.default_flow_style = False
_write_yaml.indent(mapping=2, sequence=4, offset=2)

# Closure v0 only understands plain dotted-numeric versions (e.g. "3.10"); anything else
# (prose, codenames, ranges) is left unparsed so the comparison in `dissolves` can refuse
# rather than guess.
_VERSION_RE = re.compile(r"^\d+(\.\d+)*$")


def citation_participant(source_id: str, locator: str) -> str:
    """A citation's participant id. Prefixed and colon-separated rather than
    `<source>#<locator>`, because `#` already means "chunk" everywhere else in the
    project and a participant list is read by humans."""
    return f"citation:{source_id}:{locator}"


def load_records(path: Path | None = None) -> list[dict]:
    """Read the whole contradiction ledger.

    @param path: overrides `CONTRADICTIONS_PATH` (tests use a scratch file).
    @returns: the `contradictions` list, or `[]` when the file is absent/empty — a repo
        that has never minted a contradiction is a normal repo (mirrors
        `langatlas_validate.store.validate_contradictions`).
    """
    path = Path(path or CONTRADICTIONS_PATH)
    if not path.exists():
        return []
    return (_read_yaml.load(path.read_text()) or {}).get("contradictions") or []


def write_records(records, path: Path | None = None) -> None:
    """Rewrite the whole ledger. Closed records are carried through untouched — D45:
    closed records are never deleted.

    @param records: the full list to persist (open, dissolved, and closed alike).
    @param path: overrides `CONTRADICTIONS_PATH`.
    """
    path = Path(path or CONTRADICTIONS_PATH)
    with path.open("w", encoding="utf-8") as fh:
        _write_yaml.dump({"contradictions": list(records)}, fh)


def _parts(version: str | None) -> tuple[int, ...] | None:
    """@returns the dotted-numeric version as a comparable tuple, or None when `version`
    is missing or not in that shape."""
    if not version or not _VERSION_RE.match(version.strip()):
        return None
    return tuple(int(part) for part in version.strip().split("."))


def dissolves(fact_since: str | None, evidence_since: str | None) -> bool:
    """Closure v0 (Section 6.5): automated since/version qualification at mint time.

    Scope is deliberately narrow — `since`/`status` comparison only. The conflict
    dissolves when the contradicting evidence describes a version at or after the claim's
    `since`: the source is then simply describing a later state, not disagreeing about
    the origin. Evidence about an *earlier* version genuinely disagrees.

    Anything the comparison cannot parse stays open. A closure the code cannot justify is
    worse than an open record a human can read.

    @param fact_since: the claim's own `since` field, if any.
    @param evidence_since: the version the contradicting evidence describes, if any.
    @returns True when the disagreement is a version artefact
    """
    fact, evidence = _parts(fact_since), _parts(evidence_since)
    if fact is None or evidence is None:
        return False
    return evidence >= fact


def mint_verification_record(pairs, *, fact_id: str, has_admissible_alternative: bool,
                             path: Path | None = None, chat_run_id: str | None = None,
                             fact_since: str | None = None,
                             evidence_since: str | None = None,
                             today: str | None = None) -> list[str]:
    """D45's `type: verification` minting path — the verifier's only minting authority.

    Minted **only** when a `contradicted` verdict lands on a *secondary* citation of an
    otherwise-admissible fact. A contradicted primary/only citation blocks admission and
    mints nothing: there is no admitted fact for the record to hang off.
    `partial` verdicts never mint (they are mutually exclusive with `contradicted` under
    the decomposition fold).

    Ids are content-keyed over sorted participants, so re-minting the same conflict is a
    no-op and two processes cannot create two records for one disagreement.

    @param pairs: every `PairVerdict` for this fact (only `contradicted` ones mint).
    @param fact_id: the fact these citations were verified against.
    @param has_admissible_alternative: the fact stays admissible via a different citation;
        False means this fact never entered the store, so there is nothing to register.
    @param path: overrides `CONTRADICTIONS_PATH`.
    @param chat_run_id: the agent chat run that produced this verdict, if any.
    @param fact_since / evidence_since: inputs to closure v0; None leaves the record open.
    @param today: overrides the minted/closed date stamp (tests pin it for determinism).

    @returns the ids of every record this call is responsible for (newly minted or
        already present), newest-first order not guaranteed
    """
    if not has_admissible_alternative:
        return []
    contradicted = [p for p in pairs if p.verdict == "contradicted"]
    if not contradicted:
        return []

    records = load_records(path)
    by_id = {record.get("id"): record for record in records}
    minted, changed = [], False
    stamp = today or _date.today().isoformat()

    for pair in contradicted:
        participants = sorted([fact_id, citation_participant(pair.source_id,
                                                             pair.locator)])
        record_id = contradiction_key(participants)
        minted.append(record_id)
        if record_id in by_id:
            continue
        record = {"id": record_id, "type": "verification", "participants": participants,
                  "status": "open", "mechanism": "verifier", "minted": stamp,
                  "detail": pair.detail or "the cited passage contradicts the claim"}
        if chat_run_id:
            record["chat_run_id"] = chat_run_id
        if dissolves(fact_since, evidence_since):
            record["status"] = "dissolved"
            record["closed"] = stamp
            record["closure"] = {
                "method": "since-qualification",
                "detail": f"evidence describes {evidence_since}, at or after the claim's"
                          f" since {fact_since}; no disagreement about the origin"}
        records.append(record)
        by_id[record_id] = record
        changed = True

    if changed:
        write_records(records, path)
    return minted
