from pathlib import Path

from langatlas_validate.claims import build_claim, fact_id
from langatlas_validate.ids import compose_instance_id, compose_syntax_id


def derive_facts(records: list[tuple[Path, str, str, dict]]) -> list[dict]:
    """D20/D23: facts are never authored directly — they're derived once, here, from
    whole records. Intentionally scoped to the fields with a direct claim-template
    mapping (§ontology/claim-templates/); extending coverage to every schema field is
    later work, not a Stage-1D gap."""
    facts: list[dict] = []

    def _add(claim: str, record_path: Path, sources: list[dict] | None = None) -> None:
        facts.append({"fact_id": fact_id(claim), "claim": claim,
                     "record_path": str(record_path), "sources": sources or []})

    for path, kind, _text, data in records:
        if kind == "feature-instance":
            instance_id = compose_instance_id(data["language"], data["feature"])
            _add(build_claim("instance-exists", instance_id=instance_id, status=data["status"]),
                path)
            for c in data.get("characteristics", []):
                _add(build_claim("characteristic", instance_id=instance_id,
                                 key=c["key"], text=c["text"]), path, c.get("sources"))
            for s in data.get("syntax", []):
                syntax_id = compose_syntax_id(instance_id, s["key"])
                _add(build_claim("syntax-valid", syntax_id=syntax_id, code=s["code"]),
                    path, s.get("sources"))
        elif kind == "edge":
            edge_id = data["id"]
            _add(build_claim("edge-exists", edge_id=edge_id), path)
            if data.get("type") == "influences" and "polarity" in data:
                _add(build_claim("edge-polarity", edge_id=edge_id, polarity=data["polarity"]), path)
        elif kind == "affects-quality-edge":
            for a in data.get("assessments", []):
                _add(build_claim("quality-assessment", edge_id=data["id"],
                                 assessment_key=a["key"]), path, a.get("sources"))
        elif kind == "rule":
            _add(build_claim("rule-exists", rule_id=data["id"], message=data["message"]),
                path, data.get("sources"))

    return facts


def check_fact_collisions(facts: list[dict]) -> list[str]:
    """A fact_id colliding across two different record paths means two records both
    claim authority over the same fact — an authoring bug the store should never
    admit, not a hash collision (astronomically unlikely at sha256)."""
    by_id: dict[str, list[dict]] = {}
    for f in facts:
        by_id.setdefault(f["fact_id"], []).append(f)
    errors = []
    for fid, group in by_id.items():
        paths = {f["record_path"] for f in group}
        if len(paths) > 1:
            errors.append(f"{fid}: claimed by multiple records: {sorted(paths)}")
    return errors


def compile_bundle(repo_root: Path) -> dict:
    """D13's compiled canonical bundle — the artifact the site/Postgres/MCP consume.
    Stage 1D ships the skeleton shape; source_manifest population (per-source snapshot
    hashes) is Stage 2's ingestion-corpus concern."""
    from langatlas_validate.store import iter_store_records

    version = (repo_root / "ontology" / "VERSION").read_text().strip()
    records = list(iter_store_records(repo_root))
    facts = derive_facts(records)
    return {"schema_version": version, "facts": facts, "source_manifest": []}
