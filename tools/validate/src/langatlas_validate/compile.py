from pathlib import Path

from langatlas_validate.claims import build_claim, fact_id
from langatlas_validate.ids import compose_instance_id, compose_syntax_id


def anchor_record_id(anchor: str) -> str:
    """`fi.rust.pattern-matching#since` -> `fi.rust.pattern-matching`. A record id is slugs
    joined by dots, never a `#`, so the first `#` is always the split point."""
    return anchor.split("#", 1)[0]


def _grep_vocabulary(feature: dict | None) -> list[str]:
    """D49's negative-grep vocabulary for an absence claim: the feature's own name first, then
    its `aliases:`, deduplicated. Empty when the feature record is not among the derived
    records — the verifier then has no names to search for, rather than invented ones."""
    if not feature:
        return []
    return list(dict.fromkeys([feature["name"], *(feature.get("aliases") or [])]))


def derive_facts(records: list[tuple[Path, str, str, dict]]) -> list[dict]:
    """D20/D23: facts are never authored directly — they're derived once, here, from
    whole records. Intentionally scoped to the fields with a direct claim-template
    mapping (§ontology/claim-templates/); extending coverage to every schema field is
    later work, not a Stage-1D gap.

    Stage 3E (D65): every fact-bearing FeatureInstance field derives a fact carrying its §3.2
    anchor. `#exists` carries `since` as a load-bearing field and is verified against
    `since.sources` (D25's fold table); an absence cites at status level and carries D49's
    extra verifier inputs. `#since` is derived for identity only — its own fact id, never a
    second verification of the same citations.

    Stage 3F: every fact carries its §3.2 anchor — `<node>#summary`, `<edge>#exists`,
    `<edge>#polarity`, `<edge>#assessments[<key>]`, `<rule>#exists` — because D38's
    migration matchers and `tombstones.yaml` name facts by anchor, and Stage 3's store holds
    no FeatureInstances to borrow one from.
    """
    facts: list[dict] = []
    features = {data["id"]: data for _p, kind, _t, data in records if kind == "feature"}

    def _add(claim: str, record_path: Path, sources: list[dict] | None = None,
             **extra) -> None:
        facts.append({"fact_id": fact_id(claim), "claim": claim,
                      "record_path": str(record_path), "sources": sources or [], **extra})

    for path, kind, _text, data in records:
        if kind in ("concept", "feature"):
            # Stage 3C: the first stage with nodes to verify. A node's `summary` is its
            # existence/definition fact (§7.4's dossier item), and it is the only field on
            # these records that carries citations.
            summary = data.get("summary")
            if summary:
                _add(build_claim("node-definition", node_id=data["id"],
                                 text=summary["text"]), path, summary.get("sources"),
                     anchor=f"{data['id']}#summary")
        elif kind == "feature-instance":
            instance_id = compose_instance_id(data["language"], data["feature"])
            since = data.get("since")
            exists = {"anchor": f"{instance_id}#exists", "status": data["status"]}
            if data["status"] == "absent":
                exists_sources = data.get("sources")
                exists["absence_scope"] = data.get("absence_scope")
                exists["feature_aliases"] = _grep_vocabulary(features.get(data["feature"]))
            else:
                exists_sources = (since or {}).get("sources")
                if since:
                    exists["since"] = since["value"]
            _add(build_claim("instance-exists", instance_id=instance_id, status=data["status"]),
                 path, exists_sources, **exists)
            if since:
                _add(build_claim("instance-field", instance_id=instance_id, field="since",
                                 value=since["value"]),
                     path, anchor=f"{instance_id}#since", since=since["value"],
                     verified_with=f"{instance_id}#exists")
            for n in data.get("notes", []):
                _add(build_claim("instance-note", instance_id=instance_id, key=n["key"],
                                 note_type=n["type"], text=n["text"]),
                     path, n.get("sources"), anchor=f"{instance_id}#notes[{n['key']}]")
            for c in data.get("characteristics", []):
                _add(build_claim("characteristic", instance_id=instance_id,
                                 key=c["key"], text=c["text"]), path, c.get("sources"),
                     anchor=f"{instance_id}#characteristics[{c['key']}]")
            for s in data.get("syntax", []):
                syntax_id = compose_syntax_id(instance_id, s["key"])
                _add(build_claim("syntax-valid", syntax_id=syntax_id, code=s["code"]),
                     path, s.get("sources"), anchor=f"{instance_id}#syntax[{s['key']}]")
        elif kind == "edge":
            edge_id = data["id"]
            # The edge's own citations, so the pair is verifiable at all — without them
            # `edge-exists` yields zero (claim, citation) pairs and can never be verified.
            _add(build_claim("edge-exists", edge_id=edge_id), path,
                 (data.get("statement") or {}).get("sources"), anchor=f"{edge_id}#exists")
            if data.get("type") == "influences" and "polarity" in data:
                _add(build_claim("edge-polarity", edge_id=edge_id,
                                 polarity=data["polarity"]), path,
                     anchor=f"{edge_id}#polarity")
        elif kind == "affects-quality-edge":
            for a in data.get("assessments", []):
                _add(build_claim("quality-assessment", edge_id=data["id"],
                                 assessment_key=a["key"]), path, a.get("sources"),
                     anchor=f"{data['id']}#assessments[{a['key']}]")
        elif kind == "rule":
            _add(build_claim("rule-exists", rule_id=data["id"], message=data["message"]),
                 path, data.get("sources"), anchor=f"{data['id']}#exists")

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
