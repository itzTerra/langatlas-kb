"""D38's disposition DSL and the thin shared interpreter over it (§5.2, §5.4).

A manifest says *what* a restructure is — `split | merge | move | remove`, each with a
`fact_remap` of anchor matchers → `remap | requeue | tombstone | untouched` — and this module is
the only thing that turns one into a corpus diff. That is the point of fixing the DSL: a
migration is a manifest plus this interpreter, never bespoke Python, so CI can replay it
(`replay.py`) and get the committed diff back byte for byte.

`plan_migration` is a pure function of (store tree, manifest); it never writes. Derived stores
are rebuilt, never migrated (§5.2), so the only files a plan can change are canonical-store
records, `tombstones.yaml` and `ontology/redirects.yaml`.

v0 limits, each a refusal with a message rather than a silent guess:
- one action per record (an edge's `#exists` and `#polarity` travel together);
- no op may touch a FeatureInstance — instances migrate with Stage 5's sweeps;
- `move` touches no fact, because Stage 3 has no classification-asserting claim kind, so its
  `fact_remap` must be empty;
- a split's children and a merge's survivor must already be committed: a migration never mints
  a node, because only the D24 gate may admit one (D4)."""
import io
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from ruamel.yaml import YAML

from langatlas_validate.compile import derive_facts
from langatlas_validate.ids import canonical_endpoints, canonical_when_all, compose_edge_id
from langatlas_validate.normalize import normalize_record, normalize_value
from langatlas_validate.redirects import REDIRECTS_REL, parse_redirects, render_redirects
from langatlas_validate.schema import validate_record
from langatlas_validate.store import iter_store_records
from langatlas_validate.tombstones import TOMBSTONES_REL, parse_tombstones, render_tombstones

MIGRATIONS_REL = "ontology/migrations"
MANIFEST_NAME = "manifest.yaml"
OPS = ("split", "merge", "move", "remove")
REMAP_ACTIONS = ("remap", "requeue", "tombstone", "untouched")
# What a scratch copy needs for `validate_store` to judge the migrated tree.
STORE_COPY = ("concepts", "features", "edges", "rules", "languages", "sources", "ontology",
              "tombstones.yaml", "contradictions.yaml", "overrides.yaml")
_REASON = {"split": "split", "merge": "merge", "move": "move", "remove": "removal"}
_NODE_KINDS = ("feature", "concept")
_DEPENDENT_KINDS = ("edge", "affects-quality-edge", "rule")
# Walked by `iter_store_records` but never a migration's business.
_SKIPPED_KINDS = ("language-registry", "language", "source")

_safe = YAML(typ="safe")
_ID_PATTERN = re.compile(r"^[0-9]{4}-[a-z0-9]+(-[a-z0-9]+)*$")


class MigrationError(Exception):
    """A manifest the interpreter refuses. The message always names the anchor, record or node
    at fault, because the fix is an edit to the manifest."""


@dataclass(frozen=True)
class MigrationPlan:
    """@param changes: repo-relative path -> new text, or None for a deletion.
    @param tombstones: the entries this migration appends, in order.
    @param gated: rewritten fact-bearing records the D24 gate must re-admit before landing (D4).
    @param touched: every node or record id the migration changed."""
    migration_id: str
    changes: dict
    tombstones: tuple
    gated: tuple
    touched: tuple


def _round_trip() -> YAML:
    yaml = YAML()
    yaml.indent(mapping=2, sequence=4, offset=2)
    yaml.width = 100
    return yaml


def _dump(data) -> str:
    buf = io.StringIO()
    _round_trip().dump(data, buf)
    return buf.getvalue()


def is_manifest_path(rel: str) -> bool:
    """True only for `ontology/migrations/<migration id>/manifest.yaml` — the one shape
    `iter_manifests`, `validate_manifests` and replay all see. A manifest anywhere else is
    invisible to them, so nothing may treat it as one."""
    prefix = f"{MIGRATIONS_REL}/"
    if not rel.startswith(prefix):
        return False
    parts = rel[len(prefix):].split("/")
    return (len(parts) == 2 and parts[1] == MANIFEST_NAME
            and bool(_ID_PATTERN.match(parts[0])))


def manifest_rel(migration_id: str) -> str:
    if not isinstance(migration_id, str) or not _ID_PATTERN.match(migration_id):
        raise MigrationError(f"migration_id {migration_id!r} does not match the manifest"
                             f" schema pattern {_ID_PATTERN.pattern}")
    return f"{MIGRATIONS_REL}/{migration_id}/{MANIFEST_NAME}"


def render_manifest(manifest: dict) -> str:
    return normalize_record(_dump(manifest), "migration-manifest")


def load_manifest(path: Path):
    """The parsed file as-is; a syntax error is a `MigrationError`, a non-mapping is returned for
    the caller to report."""
    try:
        return _safe.load(Path(path).read_text())
    except Exception as exc:
        raise MigrationError(f"{path}: not valid YAML ({type(exc).__name__}: {exc})") from exc


def iter_manifests(repo_root: Path) -> list[tuple[str, dict]]:
    root = Path(repo_root)
    directory = root / MIGRATIONS_REL
    if not directory.exists():
        return []
    found = []
    for path in sorted(directory.glob(f"*/{MANIFEST_NAME}")):
        rel = str(path.relative_to(root))
        try:
            found.append((rel, load_manifest(path)))
        except MigrationError as exc:
            found.append((rel, exc))
    return found


def validate_manifests(repo_root: Path) -> list[str]:
    """Shape only (§7.12). Matcher resolvability is a property of the tree a manifest applied
    to — the *pre*-migration store — so it is checked at plan time and by CI replay, never
    against today's store, where a remapped anchor has correctly stopped existing."""
    errors: list[str] = []
    seen: set[str] = set()
    for rel, manifest in iter_manifests(repo_root):
        if isinstance(manifest, MigrationError):
            errors.append(f"{rel}: not valid YAML ({manifest.__cause__})")
            continue
        if not isinstance(manifest, dict):
            errors.append(f"{rel}: a manifest must be a mapping, not {type(manifest).__name__}")
            continue
        errors.extend(f"{rel}: {e}" for e in validate_record(manifest, "migration-manifest"))
        migration_id = manifest.get("migration_id")
        if not isinstance(migration_id, str):
            continue                    # the schema error above already names it
        if Path(rel).parent.name != migration_id:
            errors.append(f"{rel}: directory name must equal migration_id {migration_id!r}")
        if migration_id in seen:
            errors.append(f"{rel}: duplicate migration_id {migration_id!r}")
        seen.add(migration_id)
    return errors


def match_anchor(pattern: str, anchor: str) -> bool:
    """`*` matches any run of characters; everything else is literal. Not `fnmatch`: anchors
    carry `[key]`, which fnmatch would read as a character class."""
    regex = "^" + ".*".join(re.escape(part) for part in pattern.split("*")) + "$"
    return re.match(regex, anchor) is not None


@dataclass
class _Record:
    kind: str
    data: dict


class _Store:
    """The migration's working tree: records keyed by repo-relative path, None once deleted.
    Read once; `changes()` diffs the end state against what was read, rendering only records
    this migration touched, so an untouched record can never pick up a formatting diff."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.records: dict[str, _Record | None] = {}
        self.original: dict[str, str | None] = {}
        self.dirty: set[str] = set()
        loader = _round_trip()
        for path, kind, text, _data in iter_store_records(self.root):
            if kind in _SKIPPED_KINDS:
                continue
            rel = str(path.relative_to(self.root))
            self.records[rel] = _Record(kind, loader.load(text))
            self.original[rel] = text
        self.tombstone_text = self._read(TOMBSTONES_REL)
        self.redirect_text = self._read(REDIRECTS_REL)
        self.redirects = parse_redirects(self.redirect_text)
        taxonomy = _safe.load(self._read("ontology/taxonomy/dimensions.yaml") or "") or {}
        self.dimensions = {entry["slug"] for entry in taxonomy.get("dimensions") or []}

    def _read(self, rel: str) -> str | None:
        path = self.root / rel
        return path.read_text() if path.exists() else None

    def live(self) -> list[tuple[str, _Record]]:
        return [(rel, record) for rel, record in sorted(self.records.items())
                if record is not None]

    def node(self, node_id: str) -> tuple[str, _Record] | None:
        for kind, directory in (("feature", "features"), ("concept", "concepts")):
            rel = f"{directory}/{node_id}.yaml"
            record = self.records.get(rel)
            if record is not None and record.kind == kind:
                return rel, record
        return None

    def node_ids(self) -> set[str]:
        return {record.data["id"] for _rel, record in self.live() if record.kind in _NODE_KINDS}

    def put(self, rel: str, kind: str, data) -> None:
        self.original.setdefault(rel, None)
        self.records[rel] = _Record(kind, data)
        self.dirty.add(rel)

    def delete(self, rel: str) -> None:
        self.records[rel] = None
        self.dirty.add(rel)

    def facts(self) -> list[dict]:
        return derive_facts([(Path(rel), record.kind, "", record.data)
                             for rel, record in self.live()])

    def facts_of(self, rel: str) -> list[dict]:
        return [fact for fact in self.facts() if fact["record_path"] == rel]

    def changes(self) -> dict:
        changes = {}
        for rel in sorted(self.dirty):
            record = self.records.get(rel)
            text = None if record is None else normalize_record(_dump(record.data), record.kind)
            if text != self.original.get(rel):
                changes[rel] = text
        return changes


def disposition_nodes(disposition: dict) -> tuple[str, ...]:
    """Every node id an op names, old and new."""
    op = disposition["op"]
    if op == "merge":
        return (*disposition["from"], disposition["to"])
    if op == "split":
        return (disposition["from"], *disposition["to"])
    return (disposition["node"],)


def _old_nodes(disposition: dict) -> set[str]:
    """The nodes that stop being features: every record pointing at one must be disposed of.
    A `move` keeps its node a feature, so it disposes of nothing."""
    op = disposition["op"]
    if op == "merge":
        return set(disposition["from"])
    if op == "split":
        return {disposition["from"]}
    if op == "remove":
        return {disposition["node"]}
    return set()


def _mentions(record: _Record) -> set[str]:
    data = record.data
    if record.kind in _NODE_KINDS:
        return {data["id"]}
    if record.kind == "edge":
        return {data["from"], data["to"]}
    if record.kind == "affects-quality-edge":
        return {data["from"]}
    if record.kind == "rule":
        return {*data["when_all"], *(data.get("then") or [])}
    if record.kind == "feature-instance":
        return {data["feature"]}
    return set()


def _affected(store: _Store, disposition: dict) -> dict[str, list[dict]]:
    old = _old_nodes(disposition)
    affected: dict[str, list[dict]] = {}
    for rel, record in store.live():
        if not _mentions(record) & old:
            continue
        if record.kind == "feature-instance":
            raise MigrationError(f"{rel}: this {disposition['op']} touches a FeatureInstance;"
                                 f" instance migration arrives with Stage 5's sweeps")
        affected[rel] = store.facts_of(rel)
    return affected


def _governing(store: _Store, disposition: dict,
               affected: dict[str, list[dict]]) -> dict[str, dict | None]:
    """Resolves every `fact_remap` matcher, then the one entry that governs each affected
    record (None: nothing matched — the implicit default)."""
    op = disposition["op"]
    anchors = [fact["anchor"] for fact in store.facts()]
    owned = {fact["anchor"] for facts in affected.values() for fact in facts}
    chosen: dict[str, dict] = {}
    for index, entry in enumerate(disposition.get("fact_remap") or []):
        pattern, exclude = entry["match"]["anchor"], entry["match"].get("exclude")
        where = f"{op} fact_remap[{index}] ({pattern})"
        matched = [anchor for anchor in anchors if match_anchor(pattern, anchor)
                   and not (exclude and match_anchor(exclude, anchor))]
        if not matched:
            raise MigrationError(f"{where}: matches zero anchors — a hard failure (§5.4)")
        stray = [anchor for anchor in matched if anchor not in owned]
        if stray:
            raise MigrationError(f"{where}: matches {stray[0]!r}, which this {op} does not touch")
        for anchor in matched:
            chosen.setdefault(anchor, entry)
    governing: dict[str, dict | None] = {}
    for rel, facts in affected.items():
        explicit = [chosen[fact["anchor"]] for fact in facts if fact["anchor"] in chosen]
        actions = {(entry["action"], entry.get("target")) for entry in explicit}
        if len(actions) > 1:
            raise MigrationError(f"{rel}: its facts are given different dispositions"
                                 f" {sorted(map(str, actions))}; v0 applies one action per record")
        governing[rel] = explicit[0] if explicit else None
    return governing


def _keeps_node(disposition: dict) -> bool:
    return (disposition["op"] == "split"
            and disposition.get("old_node", "demote-to-concept") == "demote-to-concept")


def _summary_targets(store: _Store, disposition: dict) -> set[str]:
    op = disposition["op"]
    if op == "merge":
        return {disposition["to"]}
    if op == "split":
        return set(disposition["to"])
    return store.node_ids() - _old_nodes(disposition)


def _dispose_node(store: _Store, rel: str, entry: dict | None, disposition: dict,
                  pending: list) -> None:
    """The old node's own record. Its definition fact is remapped to a survivor or retired —
    unless a split demotes it to a Concept, which keeps the node and the fact alive."""
    op = disposition["op"]
    node_id = store.records[rel].data["id"]
    if _keeps_node(disposition):
        if entry is not None and entry["action"] != "untouched":
            raise MigrationError(f"{node_id}#summary: a split that demotes to a Concept keeps"
                                 f" its definition — leave it untouched")
        return
    action = entry["action"] if entry else "tombstone"
    if action in ("requeue", "untouched"):
        raise MigrationError(f"{node_id}#summary: this {op} removes the node, so its definition"
                             f" can only be remapped to a surviving node or tombstoned")
    successors = []
    if action == "remap":
        if entry["target"] not in _summary_targets(store, disposition):
            raise MigrationError(f"{node_id}#summary: remap target {entry['target']!r} is not a"
                                 f" surviving node of this {op}")
        successors = [f"{entry['target']}#summary"]
    for fact in store.facts_of(rel):
        pending.append({"fact": fact, "successors": successors, "action": action,
                        "optional": False})
    store.delete(rel)


def _dispose_dependent(store: _Store, rel: str, entry: dict | None, disposition: dict,
                       pending: list, gated: set) -> None:
    """An edge, quality edge or rule pointing at an old node: remapped onto a surviving
    feature, requeued for redrafting, or tombstoned. `untouched` would leave it dangling, so it
    is refused here with the record's name instead of surfacing later as a reference error."""
    op, old = disposition["op"], _old_nodes(disposition)
    record = store.records[rel]
    facts = store.facts_of(rel)
    action = entry["action"] if entry else "untouched"
    if action == "untouched":
        raise MigrationError(f"{rel}: still points at {sorted(_mentions(record) & old)}, which"
                             f" this {op} removes — give it a remap target, requeue or tombstone")
    if action in ("requeue", "tombstone"):
        for fact in facts:
            pending.append({"fact": fact, "successors": [], "action": action, "optional": False})
        store.delete(rel)
        return

    target = entry["target"]
    found = store.node(target)
    if found is None or found[1].kind != "feature" or target in old:
        raise MigrationError(f"{rel}: remap target {target!r} must be a surviving committed"
                             f" feature")

    def swap(node_id: str) -> str:
        return target if node_id in old else node_id

    data = record.data
    if record.kind == "rule":
        when_all = canonical_when_all(list(dict.fromkeys(swap(f) for f in data["when_all"])))
        if len(when_all) < 2:
            raise MigrationError(f"{rel}: the remap collapses when_all to {when_all}; a"
                                 f" 1-antecedent rule is degenerate (D64) — tombstone it instead")
        data["when_all"] = when_all
        data["then"] = list(dict.fromkeys(swap(f) for f in data.get("then") or []))
        store.put(rel, record.kind, data)
        for fact in facts:
            pending.append({"fact": fact, "successors": [fact["anchor"]], "action": "remap",
                            "optional": False})
        gated.add(rel)
        return

    edge_type = data["type"]
    frm = swap(data["from"])
    to = swap(data["to"]) if record.kind == "edge" else data["to"]
    if edge_type == "alternative-to":
        frm, to = canonical_endpoints(frm, to)
    if frm == to:
        raise MigrationError(f"{rel}: the remap makes this {edge_type} edge point from {frm} to"
                             f" itself — tombstone it instead")
    new_id = compose_edge_id(edge_type, frm, to)
    new_rel = f"edges/{frm}/{edge_type}--{to}.yaml"
    existing = store.records.get(new_rel)
    if existing is not None:
        if record.kind == "affects-quality-edge":
            raise MigrationError(f"{rel}: {frm} already has an affects-quality edge to {to};"
                                 f" merge the assessments by hand before migrating")
        if data.get("polarity") != existing.data.get("polarity"):
            raise MigrationError(
                f"{rel}: the remap collides with {new_rel}, whose polarity"
                f" {existing.data.get('polarity')!r} differs from {data.get('polarity')!r}; the"
                f" two claims conflict — tombstone or requeue this edge instead")
    store.delete(rel)
    if existing is not None:
        # §5.2: "duplicate claims dedupe by content key" — the surviving edge already says it.
        for fact in facts:
            pending.append({"fact": fact, "action": "remap", "optional": False,
                            "successors": [f"{new_id}#{fact['anchor'].split('#', 1)[1]}"]})
        return
    data["id"], data["from"], data["to"] = new_id, frm, to
    store.put(new_rel, record.kind, data)
    for fact in facts:
        pending.append({"fact": fact, "action": "remap", "optional": False,
                        "successors": [f"{new_id}#{fact['anchor'].split('#', 1)[1]}"]})
    gated.add(new_rel)


def _rewrite_realizes(store: _Store, mapping: dict[str, str | None]) -> None:
    """Points every feature's `realizes` at the mapped concept; a None mapping drops it."""
    for rel, record in store.live():
        if record.kind != "feature" or not record.data.get("realizes"):
            continue
        current = list(record.data["realizes"])
        updated: list[str] = []
        for concept in current:
            mapped = mapping.get(concept, concept)
            if mapped is not None and mapped not in updated:
                updated.append(mapped)
        if updated != current:
            if updated:
                record.data["realizes"] = updated
            else:
                del record.data["realizes"]
            store.put(rel, record.kind, record.data)


def _drop_redirects_to(store: _Store, node_ids: set[str]) -> None:
    """A URL to a removed node is the site's retired-index page (§5.2), not a redirect."""
    for old, target in list(store.redirects.items()):
        if target in node_ids:
            del store.redirects[old]


def _need_node(store: _Store, op: str, node_id: str, *, kind: str | None = None):
    found = store.node(node_id)
    if found is None:
        raise MigrationError(f"{op}: {node_id!r} is not a committed concept or feature")
    if kind is not None and found[1].kind != kind:
        raise MigrationError(f"{op}: {node_id!r} is a {found[1].kind}, not a {kind}")
    return found


def _check_remove(store: _Store, disposition: dict) -> None:
    _need_node(store, "remove", disposition["node"])


def _check_move(store: _Store, disposition: dict) -> None:
    _need_node(store, "move", disposition["node"], kind="feature")
    layer, dimension = disposition["to_layer"], disposition.get("to_dimension")
    if layer == 3 and dimension not in store.dimensions:
        raise MigrationError(f"move: layer 3 needs a declared dimension; {dimension!r} is not in"
                             f" ontology/taxonomy/dimensions.yaml")
    if layer != 3 and dimension:
        raise MigrationError("move: only a layer-3 feature carries a dimension")
    if disposition["fact_remap"]:
        raise MigrationError("move: touches no fact in v0 (no classification-asserting claim"
                             " kind exists yet), so its fact_remap must be empty")


def _apply_remove(store: _Store, disposition: dict, snapshots: dict) -> None:
    node_id = disposition["node"]
    _rewrite_realizes(store, {node_id: None})
    _drop_redirects_to(store, {node_id})


def _apply_move(store: _Store, disposition: dict, snapshots: dict) -> None:
    rel, record = store.node(disposition["node"])
    record.data["layer"] = disposition["to_layer"]
    if disposition["to_layer"] == 3:
        record.data["dimension"] = disposition["to_dimension"]
    else:
        record.data.pop("dimension", None)
    store.put(rel, record.kind, record.data)


def _check_merge(store: _Store, disposition: dict) -> None:
    survivor = disposition["to"]
    _rel, record = _need_node(store, "merge", survivor)
    if survivor in disposition["from"]:
        raise MigrationError(f"merge: {survivor!r} cannot be both merged away and the survivor")
    for node_id in disposition["from"]:
        _need_node(store, "merge", node_id, kind=record.kind)


def _check_split(store: _Store, disposition: dict) -> None:
    _need_node(store, "split", disposition["from"], kind="feature")
    children = disposition["to"]
    if disposition["from"] in children or len(set(children)) != len(children):
        raise MigrationError("split: the children must be distinct and must not include the"
                             " node being split")
    for child in children:
        _need_node(store, "split", child, kind="feature")


def _apply_merge(store: _Store, disposition: dict, snapshots: dict) -> None:
    """The survivor absorbs the merged nodes' names as aliases (D49: synonym search and the
    absence grep keep finding them), and their slugs 301 to it (§5.2)."""
    survivor_id = disposition["to"]
    rel, survivor = store.node(survivor_id)
    if survivor.kind == "feature":
        aliases = list(survivor.data.get("aliases") or [])
        seen = {normalize_value(name, freetext=True)
                for name in [survivor.data["name"], *aliases]}
        for node_id in disposition["from"]:
            for name in [snapshots[node_id]["name"], *(snapshots[node_id].get("aliases") or [])]:
                key = normalize_value(name, freetext=True)
                if key not in seen:
                    aliases.append(name)
                    seen.add(key)
        if aliases != list(survivor.data.get("aliases") or []):
            survivor.data["aliases"] = aliases
            store.put(rel, survivor.kind, survivor.data)
    else:
        _rewrite_realizes(store, {node_id: survivor_id for node_id in disposition["from"]})
    for node_id in disposition["from"]:
        store.redirects[snapshots[node_id]["slug"]] = survivor_id
    for old, target in list(store.redirects.items()):
        if target in disposition["from"]:
            store.redirects[old] = survivor_id
    store.redirects.pop(survivor.data["slug"], None)


def _apply_split(store: _Store, disposition: dict, snapshots: dict) -> None:
    """Demote (default): the feature becomes a Concept with the same id, name, summary and
    provenance — so its definition fact keeps its id — and every child `realizes` it. That
    Concept is the hub page §5.2 asks for. Tombstone: the node is already gone; only
    redirects to it remain to drop."""
    old_id = disposition["from"]
    if not _keeps_node(disposition):
        _drop_redirects_to(store, {old_id})
        return
    rel, record = store.node(old_id)
    concept = {key: record.data[key] for key in
               ("id", "slug", "name", "summary", "provenance", "controversy")
               if key in record.data}
    store.delete(rel)
    store.put(f"concepts/{old_id}.yaml", "concept", concept)
    for child in disposition["to"]:
        child_rel, child_record = store.node(child)
        realizes = list(child_record.data.get("realizes") or [])
        if old_id not in realizes:
            child_record.data["realizes"] = [*realizes, old_id]
            store.put(child_rel, child_record.kind, child_record.data)


_CHECKS = {"remove": _check_remove, "move": _check_move, "merge": _check_merge,
           "split": _check_split}
_APPLY = {"remove": _apply_remove, "move": _apply_move, "merge": _apply_merge,
          "split": _apply_split}


def _check(store: _Store, disposition: dict) -> None:
    op = disposition["op"]
    if op not in _CHECKS:
        raise MigrationError(f"op {op!r} has no interpreter")
    _CHECKS[op](store, disposition)


def affected_facts(repo_root: Path, disposition: dict) -> list[dict]:
    """The facts a disposition must dispose of, as `derive_facts` rows with anchors — what
    casebook drafting seeds a `fact_remap` from."""
    store = _Store(repo_root)
    _check(store, {**disposition, "fact_remap": []})
    return [fact for facts in _affected(store, disposition).values() for fact in facts]


def _finish_tombstones(store: _Store, pending: list, manifest: dict) -> list[dict]:
    final = {fact["anchor"]: fact["fact_id"] for fact in store.facts()}
    entries = []
    for item in pending:
        fact = item["fact"]
        successors = []
        for anchor in item["successors"]:
            if anchor in final:
                successors.append(final[anchor])
            elif not item["optional"]:
                raise MigrationError(f"{fact['anchor']}: its successor {anchor} does not exist"
                                     f" once the migration is applied")
        if successors == [fact["fact_id"]]:
            continue                    # identity unchanged (a rule's antecedents moved)
        entries.append({"fact_id": fact["fact_id"], "anchor": fact["anchor"],
                        "action": item["action"], "reason": item["reason"],
                        "superseded_by": successors, "migration_id": manifest["migration_id"],
                        "date": manifest["date"]})
    return entries


def plan_migration(repo_root: Path, manifest: dict) -> MigrationPlan:
    """Interprets `manifest` against the store at `repo_root`. Dispositions apply in order,
    each against the store the previous one left.

    @raises MigrationError: an invalid manifest, or one this store cannot satisfy."""
    if not isinstance(manifest, dict):
        raise MigrationError(f"a manifest must be a mapping, not {type(manifest).__name__}")
    errors = validate_record(manifest, "migration-manifest")
    if errors:
        raise MigrationError(f"manifest {manifest.get('migration_id')!r} is invalid: "
                             + "; ".join(errors))
    store = _Store(repo_root)
    pending: list[dict] = []
    gated: set[str] = set()
    touched: set[str] = set()
    for disposition in manifest["dispositions"]:
        _check(store, disposition)
        affected = _affected(store, disposition)
        governing = _governing(store, disposition, affected)
        snapshots = {node_id: dict(store.node(node_id)[1].data)
                     for node_id in disposition_nodes(disposition)}
        start = len(pending)
        for rel in sorted(affected):
            if store.records[rel].kind in _NODE_KINDS:
                _dispose_node(store, rel, governing[rel], disposition, pending)
        for rel in sorted(affected):
            record = store.records.get(rel)
            if record is not None and record.kind in _DEPENDENT_KINDS:
                _dispose_dependent(store, rel, governing[rel], disposition, pending, gated)
        _APPLY[disposition["op"]](store, disposition, snapshots)
        for item in pending[start:]:
            item["reason"] = _REASON[disposition["op"]]
        touched.update(disposition_nodes(disposition))

    tombstones = _finish_tombstones(store, pending, manifest)
    changes = store.changes()
    if tombstones:
        changes[TOMBSTONES_REL] = render_tombstones(
            [*parse_tombstones(store.tombstone_text), *tombstones])
    if store.redirects != parse_redirects(store.redirect_text):
        changes[REDIRECTS_REL] = render_redirects(store.redirects)
    # Every record the migration writes or deletes — a rewritten rule keeps its fact id, so
    # the tombstones alone would miss it, and 3F's settled-theme bookkeeping needs it.
    for rel in changes:
        if rel in (TOMBSTONES_REL, REDIRECTS_REL):
            continue
        record = store.records.get(rel)
        data = record.data if record is not None else (_safe.load(store.original.get(rel) or "")
                                                       or {})
        if data.get("id"):
            touched.add(data["id"])
    return MigrationPlan(
        migration_id=manifest["migration_id"], changes=changes, tombstones=tuple(tombstones),
        gated=tuple(sorted(rel for rel in gated if changes.get(rel) is not None)),
        touched=tuple(sorted(touched)))


def apply_plan(repo_root: Path, plan: MigrationPlan) -> None:
    """Writes a plan into a tree. Callers own that tree: a scratch copy, or a working copy
    about to commit."""
    root = Path(repo_root)
    for rel, text in sorted(plan.changes.items()):
        path = root / rel
        if text is None:
            if path.exists():
                path.unlink()
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)


def check_plan(repo_root: Path, plan: MigrationPlan, *, extra: dict | None = None) -> list[str]:
    """`validate_store` over a scratch copy with the plan — and `extra` files, e.g. the
    manifest itself — applied. The working copy is never touched."""
    from langatlas_validate.store import validate_store

    root = Path(repo_root)
    with tempfile.TemporaryDirectory() as scratch:
        copy = Path(scratch) / "store"
        copy.mkdir()
        for name in STORE_COPY:
            source = root / name
            if source.is_dir():
                shutil.copytree(source, copy / name)
            elif source.exists():
                shutil.copy2(source, copy / name)
        apply_plan(copy, MigrationPlan(plan.migration_id, {**plan.changes, **(extra or {})},
                                       (), (), ()))
        return validate_store(copy)
