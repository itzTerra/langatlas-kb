# Stage 2A — Corpus Assembly, Ingestion & QA Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the empty `sources/` directory and empty `source_chunks` table into a real,
QA'd, embedded corpus of ~30 sources (the D15 seed collection + Jordan et al. 2015 + the D27
acquisitions + the D28 phase-1 language specs), with every source record carrying a complete
`custom` block (`tier`, `grounding`, `canonical_source`, `acquisition_note`), so 2B–2E have real
chunk ids and committed source records to build against.

**Architecture:** Four small tooling tasks close real gaps in the existing Stage 1 CLI (a
CI-enforced `acquisition_note` presence check that does not exist yet; a source-record scaffold
so ~30 CSL-JSON-as-YAML records aren't hand-typed from a blank page; a durable acquisition
checklist filed into the existing `sourcing_queue`). Seven operational tasks then run that CLI —
`langatlas-sources ingest | embed | queue | db`, `langatlas-validate ci` — against each source
group, with explicit developer checkpoints at every acquisition and QA sign-off, per the
sequencing map's "the *work* is manual; the *plan* is the tooling that makes it resumable."

**Tech Stack:** `langatlas_ingest` (`cli.py`, `pipeline.ingest_source`/`reingest_all`,
`store.SourceChunksStore`/`SourcingQueue`, `snapshot.SnapshotStore`, `embed.embed_source`,
`qa.run_qa`), `langatlas_validate` (`schema.validate_record`, `normalize.normalize_record`,
`store.validate_store`), `langatlas_pipeline.providers.core.RunContext`. Postgres via docker
compose (`langatlas-sources db`). No new packages, no schema migrations, no CLI-behavior changes
— only new modules alongside the existing ones, per the sequencing map's "used as-is; no infra
changes expected" instruction for 2A.

**Spec:** [context/spec.md](../../../context/spec.md) §4.1 (source records), §4.2 (grounding,
D51), §4.3 (locator grammar), §4.4 (ingestion QA/sourcing queue, D37), §7.4 (R1), §7.5 (D28
phase-1 selection), §8.2 (`source_chunks`). Sequencing contract:
[2026-08-23-stage-2-corpus-and-benchmark.md](2026-08-23-stage-2-corpus-and-benchmark.md), section
"2A — Corpus assembly, ingestion & QA (R1)".

## Global Constraints

- No deadline; do not take shortcuts that damage the long-term product (D6/D11).
- Git is the database — Postgres, extracted text, and embeddings are derived/private, never
  authoritative (D1). Extracted text and embeddings stay out of git (D15) — they live under the
  private snapshot store (`SNAPSHOT_ROOT`, override via `LANGATLAS_SNAPSHOT_ROOT`).
- **Agents cannot acquire books** — every acquisition (locating a PDF, using university library
  access, dropping a file into the snapshot store) is a developer checkpoint, never something an
  agent or this plan's executor does unattended.
- **Quality tiers**: A peer-reviewed/spec, B official docs/textbook, C talks/community reference,
  D blogs/popularity indexes (§4.1). Every source record needs one.
- **Grounding** (§4.2, D51): `formal-spec | reference-implementation-docs | design-doc |
  third-party-reference`, default `third-party-reference`. The phase-1-six-languages
  retroactive classification is owed **now**; phases 2–4 classify at their own ingestion time —
  out of scope here.
- **`custom.canonical_source` + `custom.acquisition_note`** (D37): every source record needs
  `canonical_source` set, and every non-canonical one needs a non-empty `acquisition_note` —
  CI-enforced presence, not truth. The R1 corpus gets a one-time retroactive backfill.
- Locators are machine-produced by the chunker, never hand-typed (§4.3) — a source record never
  contains a `locator:` field itself; that only appears on citing claims.
- Verbatim quote cap ~50 words / ~300-word per-page aggregate (D14) — not exercised by this plan
  (source records carry no quotes), named here because Task 5/7/8's records must not embed long
  extracted passages into any `note`/`title` field either.
- Model ids are configuration, never hardcoded (`config/ingest.yaml`) — this plan reads
  `models.embedding` from config, never repeats the string `qwen3-embedding-4b` as a literal
  outside of comments/docs.
- Every agent chat is logged (D18) — already true of `ingest`/`embed`'s use of `RunContext`
  in Stage 1 code; this plan adds no new provider call sites that would need their own logging.

---

## File structure

| File | Responsibility |
|---|---|
| `tools/validate/src/langatlas_validate/store.py` (modify) | Add the D37 `acquisition_note`-presence check to `validate_store` |
| `tools/validate/tests/test_store.py` (modify) | Cover the new check |
| `tools/ingest/src/langatlas_ingest/scaffold.py` (new) | Pure function rendering a schema-shaped, normalized `sources/<id>.yaml` from bibliographic fields |
| `tools/ingest/tests/test_scaffold.py` (new) | Unit tests for the renderer |
| `tools/ingest/src/langatlas_ingest/cli.py` (modify) | Add `new-source` and `file-acquisitions` subcommands |
| `tools/ingest/tests/test_cli.py` (modify) | Cover both new subcommands |
| `config/acquisitions.yaml` (new) | The durable, versioned list of sources still needing developer acquisition (D27 texts + Jordan et al.), read by `file-acquisitions` |
| `sources/*.yaml` (new, ~25–30 files) | The actual source records this task produces |
| `sources/software-foundations-plf/` naming note | Multi-chapter HTML books get one `source_id` **per chapter file** sharing one `custom.canonical_source` origin — see Task 5 |

---

### Task 1: CI-enforced `custom.acquisition_note` presence (D37)

**Files:**
- Modify: `tools/validate/src/langatlas_validate/store.py:78-105` (`validate_store`)
- Test: `tools/validate/tests/test_store.py`

**Interfaces:**
- Consumes: `iter_store_records(repo_root)` (already yields `(path, kind, text, data)` for
  `kind == "source"`, from `sources/*.yaml` excluding `_LEDGERS`).
- Produces: `validate_store(repo_root)` now also returns an error string of the shape
  `f"{rel}: custom.acquisition_note required for a non-canonical source"` for every offending
  source record — consumed today only by `langatlas-validate ci` (`cmd_ci_with_index` calls
  `validate_store` already; no caller change needed).

- [x] **Step 1: Write the failing tests**

```python
# tools/validate/tests/test_store.py — add at the end of the file

def _source_yaml(*, canonical: bool | None, note: str | None) -> str:
    custom_lines = ["  tier: B", "  grounding: third-party-reference"]
    if canonical is not None:
        custom_lines.append(f"  canonical_source: {str(canonical).lower()}")
    if note is not None:
        custom_lines.append(f"  acquisition_note: {note}")
    raw = ("id: test-source-2026\ntype: book\ntitle: Test Source\ncustom:\n"
          + "\n".join(custom_lines) + "\n")
    return normalize_record(raw, "source")


def test_validate_store_flags_missing_acquisition_note_on_noncanonical_source(store):
    path = store / "sources" / "mirror-2026.yaml"
    path.write_text(_source_yaml(canonical=False, note=None))
    errors = validate_store(store)
    assert any("acquisition_note" in e for e in errors)


def test_validate_store_allows_canonical_source_without_a_note(store):
    path = store / "sources" / "official-2026.yaml"
    path.write_text(_source_yaml(canonical=True, note=None))
    assert validate_store(store) == []


def test_validate_store_allows_noncanonical_source_with_a_note(store):
    path = store / "sources" / "mirror-2026.yaml"
    path.write_text(_source_yaml(canonical=False, note="mirrored from libgen; original OOP"))
    assert validate_store(store) == []
```

- [x] **Step 2: Run the tests to verify they fail**

Run: `cd tools/validate && uv run pytest tests/test_store.py -k acquisition_note -v`
Expected: the first test FAILs (`assert any(...)` is `False` — nothing flags the missing note
today); the other two currently pass by coincidence (no check exists yet), which is fine — they
lock in the non-error side of the behavior you're about to add.

- [x] **Step 3: Implement the check**

In `tools/validate/src/langatlas_validate/store.py`, inside the `for path, kind, text, data in
iter_store_records(repo_root):` loop of `validate_store`, after the existing
`if kind == "edge" and ...` / `if kind == "rule" and ...` blocks, add:

```python
        if kind == "source":
            custom = data.get("custom") if isinstance(data.get("custom"), dict) else {}
            if not custom.get("canonical_source") and not custom.get("acquisition_note"):
                errors.append(f"{rel}: custom.acquisition_note required for a non-canonical source")
```

- [x] **Step 4: Run the tests to verify they pass**

Run: `cd tools/validate && uv run pytest tests/test_store.py -v`
Expected: PASS, including the three new tests and every pre-existing `test_store.py` test.

- [x] **Step 5: Commit**

```bash
git add tools/validate/src/langatlas_validate/store.py tools/validate/tests/test_store.py
git commit -m "feat(#stage-2a): CI-enforce D37's acquisition_note presence for non-canonical sources"
```

---

### Task 2: Source-record scaffold renderer

**Files:**
- Create: `tools/ingest/src/langatlas_ingest/scaffold.py`
- Test: `tools/ingest/tests/test_scaffold.py`

**Interfaces:**
- Consumes: `langatlas_validate.normalize.normalize_record(text, kind)` (already returns the
  canonical serialization for a record kind); `langatlas_validate.schema.validate_record(data,
  "source")` (already validates against `ontology/schema/source.schema.json`, requiring
  `id`/`type`/`title`/`custom.tier`/`custom.grounding`).
- Produces: `render_source_yaml(id, type, title, *, author=None, issued=None, url=None,
  doi=None, tier, grounding, canonical_source=None, acquisition_note=None, edition=None,
  edition_check_url=None, locator_kinds=None) -> str` — a normalized YAML string that
  `validate_record(yaml.load(result), "source")` returns `[]` for. Task 3's CLI command calls
  this directly.

- [x] **Step 1: Write the failing tests**

```python
# tools/ingest/tests/test_scaffold.py
from ruamel.yaml import YAML
from langatlas_ingest.scaffold import render_source_yaml
from langatlas_validate.schema import validate_record
from langatlas_validate.normalize import normalize_record

_yaml = YAML(typ="safe")


def test_render_source_yaml_validates_and_is_normalized():
    text = render_source_yaml(
        "vanroy-haridi-2003", "book", "Concepts, Techniques, and Models of Computer Programming",
        author=[{"family": "Van Roy", "given": "Peter"}, {"family": "Haridi", "given": "Seif"}],
        issued={"date-parts": [[2003]]}, tier="B", grounding="third-party-reference",
        canonical_source=False, acquisition_note="developer's personal library copy")
    data = _yaml.load(text)
    assert validate_record(data, "source") == []
    assert normalize_record(text, "source") == text


def test_render_source_yaml_omits_unset_optional_fields():
    text = render_source_yaml("kaijanaho-2015", "thesis", "Empirical Evaluation in PL Design",
                              tier="B", grounding="third-party-reference",
                              canonical_source=True)
    data = _yaml.load(text)
    assert "author" not in data and "URL" not in data and "DOI" not in data
    assert "acquisition_note" not in data["custom"]


def test_render_source_yaml_carries_edition_and_locator_kinds():
    text = render_source_yaml(
        "haskell-2010-report", "report", "Haskell 2010 Language Report",
        tier="A", grounding="formal-spec", canonical_source=True,
        edition="2010", edition_check_url="https://www.haskell.org/onlinereport/haskell2010/",
        locator_kinds=["numbered-section"])
    data = _yaml.load(text)
    assert data["custom"]["edition"] == "2010"
    assert data["custom"]["locator_kinds"] == ["numbered-section"]
    assert validate_record(data, "source") == []
```

- [x] **Step 2: Run the tests to verify they fail**

Run: `cd tools/ingest && uv run pytest tests/test_scaffold.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'langatlas_ingest.scaffold'`.

- [x] **Step 3: Implement the renderer**

```python
# tools/ingest/src/langatlas_ingest/scaffold.py
from langatlas_validate.normalize import normalize_record


def render_source_yaml(id: str, type: str, title: str, *, author: list[dict] | None = None,
                       issued: dict | None = None, url: str | None = None,
                       doi: str | None = None, tier: str, grounding: str,
                       canonical_source: bool | None = None,
                       acquisition_note: str | None = None, edition: str | None = None,
                       edition_check_url: str | None = None,
                       locator_kinds: list[str] | None = None) -> str:
    """Renders a schema-shaped `sources/<id>.yaml` record (§4.1: CSL-JSON field vocabulary
    authored as YAML, plus the `custom` extras) and normalizes it through the same
    `normalize_record` CI checks, so a scaffolded record is never the thing `precommit-auto`
    flags as unnormalized. Every field a caller does not pass is omitted entirely rather than
    written as `null` — an omitted CSL-JSON field and an explicit null are not the same
    statement, and the schema treats extra properties structurally, so a stray `null` would
    only ever be noise for whoever reads the record next."""
    data: dict = {"id": id, "type": type, "title": title}
    if author is not None:
        data["author"] = author
    if issued is not None:
        data["issued"] = issued
    if url is not None:
        data["URL"] = url
    if doi is not None:
        data["DOI"] = doi
    custom: dict = {"tier": tier, "grounding": grounding}
    if canonical_source is not None:
        custom["canonical_source"] = canonical_source
    if acquisition_note is not None:
        custom["acquisition_note"] = acquisition_note
    if edition is not None:
        custom["edition"] = edition
    if edition_check_url is not None:
        custom["edition_check_url"] = edition_check_url
    if locator_kinds is not None:
        custom["locator_kinds"] = list(locator_kinds)
    data["custom"] = custom

    import io
    from ruamel.yaml import YAML

    yaml = YAML()
    yaml.default_flow_style = False
    buf = io.StringIO()
    yaml.dump(data, buf)
    return normalize_record(buf.getvalue(), "source")
```

- [x] **Step 4: Run the tests to verify they pass**

Run: `cd tools/ingest && uv run pytest tests/test_scaffold.py -v`
Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add tools/ingest/src/langatlas_ingest/scaffold.py tools/ingest/tests/test_scaffold.py
git commit -m "feat(#stage-2a): add render_source_yaml, a schema-valid sources/*.yaml scaffold"
```

---

### Task 3: `new-source` and `file-acquisitions` CLI subcommands

**Files:**
- Modify: `tools/ingest/src/langatlas_ingest/cli.py`
- Create: `config/acquisitions.yaml`
- Test: `tools/ingest/tests/test_cli.py`

**Interfaces:**
- Consumes: `scaffold.render_source_yaml(...)` (Task 2); `langatlas_ingest.paths.REPO_ROOT`;
  `langatlas_ingest.store.SourcingQueue` (`store.py:147-197`, already has `.file(kind=,
  source_id=, reason=, detail="")`); `langatlas_ingest.db.connect`; `langatlas_ingest.config.
  IngestConfig`.
- Produces: `langatlas-sources new-source <id> <type> <title> --tier {A,B,C,D} --grounding
  {formal-spec,reference-implementation-docs,design-doc,third-party-reference} [--author ...]
  [--issued-year N] [--url U] [--doi D] [--canonical/--no-canonical] [--acquisition-note N]
  [--edition E] [--edition-check-url U] [--locator-kinds K [K ...]] [--out-dir DIR]` writing
  `<out-dir or REPO_ROOT/sources>/<id>.yaml`, refusing to overwrite an existing file. `langatlas-
  sources file-acquisitions [--file PATH]` reads `config/acquisitions.yaml` (default) and calls
  `SourcingQueue.file(kind="pending-source", source_id=..., reason=..., detail=...)` once per
  entry, printing what it filed. Both consumed manually by the developer in Tasks 5–8 — no other
  code depends on their exact signatures.

- [x] **Step 1: Write the failing tests**

```python
# tools/ingest/tests/test_cli.py — add at the end of the file

def test_new_source_writes_a_normalized_validating_record(tmp_path):
    from langatlas_ingest.cli import main

    out_dir = tmp_path / "sources"
    rc = main(["new-source", "kaijanaho-2015", "thesis", "Empirical Evaluation in PL Design",
              "--tier", "B", "--grounding", "third-party-reference",
              "--canonical", "--out-dir", str(out_dir)])
    assert rc == 0
    written = (out_dir / "kaijanaho-2015.yaml").read_text()
    from ruamel.yaml import YAML
    from langatlas_validate.schema import validate_record
    from langatlas_validate.normalize import normalize_record
    data = YAML(typ="safe").load(written)
    assert validate_record(data, "source") == []
    assert normalize_record(written, "source") == written


def test_new_source_refuses_to_overwrite(tmp_path, capsys):
    from langatlas_ingest.cli import main

    out_dir = tmp_path / "sources"
    args = ["new-source", "dup-2026", "book", "Dup", "--tier", "B",
           "--grounding", "third-party-reference", "--no-canonical",
           "--acquisition-note", "test", "--out-dir", str(out_dir)]
    assert main(args) == 0
    assert main(args) == 1
    assert "already exists" in capsys.readouterr().out


def test_file_acquisitions_files_every_entry(tmp_path, monkeypatch):
    from langatlas_ingest.cli import main

    manifest = tmp_path / "acquisitions.yaml"
    manifest.write_text(
        "- source_id: harper-pfpl\n  reason: access-pending\n"
        "  detail: 'free PDF; download and drop into snapshot store'\n")
    filed: list[tuple[str, str, str, str]] = []

    class FakeQueue:
        def __init__(self, conn):
            pass

        def file(self, *, kind, source_id, reason, detail=""):
            filed.append((kind, source_id, reason, detail))
            return len(filed)

    monkeypatch.setattr("langatlas_ingest.store.SourcingQueue", FakeQueue)
    monkeypatch.setattr("langatlas_ingest.db.connect",
                        lambda dsn=None: __import__("contextlib").nullcontext(object()))
    rc = main(["file-acquisitions", "--file", str(manifest)])
    assert rc == 0
    assert filed == [("pending-source", "harper-pfpl", "access-pending",
                      "free PDF; download and drop into snapshot store")]
```

- [x] **Step 2: Run the tests to verify they fail**

Run: `cd tools/ingest && uv run pytest tests/test_cli.py -k "new_source or file_acquisitions" -v`
Expected: FAIL — `argparse` rejects the unknown `new-source`/`file-acquisitions` subcommands.

- [x] **Step 3: Implement the subcommands**

In `tools/ingest/src/langatlas_ingest/cli.py`, add two command functions and wire them into
`build_parser`:

```python
def _cmd_new_source(args) -> int:
    from langatlas_ingest.paths import REPO_ROOT
    from langatlas_ingest.scaffold import render_source_yaml

    author = None
    if args.author:
        author = [{"family": part.split(",")[0].strip(),
                   "given": part.split(",", 1)[1].strip() if "," in part else ""}
                  for part in args.author]
    issued = {"date-parts": [[args.issued_year]]} if args.issued_year else None
    canonical = True if args.canonical else (False if args.no_canonical else None)
    text = render_source_yaml(
        args.id, args.type, args.title, author=author, issued=issued, url=args.url,
        doi=args.doi, tier=args.tier, grounding=args.grounding, canonical_source=canonical,
        acquisition_note=args.acquisition_note, edition=args.edition,
        edition_check_url=args.edition_check_url, locator_kinds=args.locator_kinds or None)
    out_dir = Path(args.out_dir) if args.out_dir else REPO_ROOT / "sources"
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"{args.id}.yaml"
    if target.exists():
        print(f"{target} already exists; refusing to overwrite")
        return 1
    target.write_text(text)
    print(f"wrote {target}")
    return 0


def _cmd_file_acquisitions(args) -> int:
    from ruamel.yaml import YAML
    from langatlas_ingest.db import connect
    from langatlas_ingest.store import SourcingQueue

    manifest = Path(args.file)
    entries = YAML(typ="safe").load(manifest.read_text()) or []
    config = IngestConfig.load()
    with connect(config.dsn) as conn:
        queue = SourcingQueue(conn)
        for entry in entries:
            entry_id = queue.file(kind="pending-source", source_id=entry["source_id"],
                                  reason=entry["reason"], detail=entry.get("detail", ""))
            print(f"filed #{entry_id}: {entry['source_id']} ({entry['reason']})")
    return 0
```

```python
    new_source = sub.add_parser("new-source",
                                help="scaffold a schema-valid sources/<id>.yaml record")
    new_source.add_argument("id")
    new_source.add_argument("type", help="CSL-JSON type, e.g. book | article-journal | report")
    new_source.add_argument("title")
    new_source.add_argument("--author", nargs="*", default=[],
                            help="'Family, Given' per author, e.g. 'Van Roy, Peter'")
    new_source.add_argument("--issued-year", type=int, default=None)
    new_source.add_argument("--url", default=None)
    new_source.add_argument("--doi", default=None)
    new_source.add_argument("--tier", required=True, choices=["A", "B", "C", "D"])
    new_source.add_argument("--grounding", required=True,
                            choices=["formal-spec", "reference-implementation-docs",
                                    "design-doc", "third-party-reference"])
    canon_group = new_source.add_mutually_exclusive_group()
    canon_group.add_argument("--canonical", action="store_true")
    canon_group.add_argument("--no-canonical", action="store_true")
    new_source.add_argument("--acquisition-note", default=None)
    new_source.add_argument("--edition", default=None)
    new_source.add_argument("--edition-check-url", default=None)
    new_source.add_argument("--locator-kinds", nargs="*", default=[])
    new_source.add_argument("--out-dir", default=None)
    new_source.set_defaults(func=_cmd_new_source)

    file_acq = sub.add_parser("file-acquisitions",
                              help="file config/acquisitions.yaml's entries into sourcing_queue")
    file_acq.add_argument("--file", default=None)
    file_acq.set_defaults(func=_cmd_file_acquisitions)
```

Note: `file_acq.add_argument("--file", default=None)` must resolve to `REPO_ROOT /
"config" / "acquisitions.yaml"` when unset — add this one line inside `_cmd_file_acquisitions`
before reading `args.file`:

```python
    manifest = Path(args.file) if args.file else REPO_ROOT / "config" / "acquisitions.yaml"
```

(add `from langatlas_ingest.paths import REPO_ROOT` to `_cmd_file_acquisitions`'s imports, and
delete the now-redundant `manifest = Path(args.file)` line above it).

- [x] **Step 4: Run the tests to verify they pass**

Run: `cd tools/ingest && uv run pytest tests/test_cli.py -v`
Expected: PASS, including every pre-existing `test_cli.py` test.

- [x] **Step 5: Create `config/acquisitions.yaml`**

```yaml
# config/acquisitions.yaml — D37 acquisition tracking for Stage 2A's R1 corpus (spec §7.4).
# Filed into `sourcing_queue` via `langatlas-sources file-acquisitions`. Each entry is a
# developer checkpoint: agents cannot acquire books. `reason` is one of sourcing_queue's
# CHECK-constrained values (paywalled | access-pending | acquisition-failed).
- source_id: jordan-et-al-2015
  reason: access-pending
  detail: "Feature model of programming languages; PDF was attached to the original Notion
    brief (feature-model.pdf) — re-locate or re-request from the Notion page."
- source_id: harper-pfpl
  reason: access-pending
  detail: "Harper, PFPL — free PDF at https://www.cs.cmu.edu/~rwh/pfpl/; download and drop
    into the snapshot store."
- source_id: krishnamurthi-plai
  reason: access-pending
  detail: "Krishnamurthi, PLAI — free at https://www.plai.org/; download and drop into the
    snapshot store."
- source_id: kaijanaho-2015
  reason: access-pending
  detail: "Kaijanaho 2015 thesis, 'Evaluation of Programming Languages and Tools' — free at
    JYU's institutional repository; download and drop into the snapshot store."
- source_id: scott-plp
  reason: paywalled
  detail: "Scott, Programming Language Pragmatics — via university library access."
- source_id: turbak-gifford-dcpl
  reason: paywalled
  detail: "Turbak & Gifford, Design Concepts in Programming Languages — via university
    library access."
- source_id: sebesta-copl
  reason: paywalled
  detail: "Sebesta, Concepts of Programming Languages — via university library access."
```

- [x] **Step 6: Run `file-acquisitions` against the compose database**

Run: `docker compose up -d db && cd tools/ingest && uv run langatlas-sources db && \
  uv run langatlas-sources file-acquisitions`
Expected: seven `filed #N: <source_id> (<reason>)` lines. Verify with
`uv run langatlas-sources queue --kind pending-source` — seven open entries listed.

- [x] **Step 7: Commit**

```bash
git add tools/ingest/src/langatlas_ingest/cli.py tools/ingest/tests/test_cli.py \
  config/acquisitions.yaml
git commit -m "feat(#stage-2a): add new-source scaffold and file-acquisitions CLI subcommands"
```

---

### Task 4: Verify the tooling end-to-end against a throwaway source before touching the real corpus

**Files:** none (verification-only task; no new files).

**Interfaces:**
- Consumes: everything from Tasks 1–3 plus the existing `langatlas-sources ingest`/`embed` and
  `langatlas-validate ci`.
- Produces: confidence that Tasks 5–8's real, hours-of-developer-effort ingestion runs are not
  going to trip over a scaffold/CI bug discovered only after a real book's QA skim.

- [x] **Step 1: Scaffold and ingest a one-page throwaway source**

```bash
cd /tmp && printf 'Test Source\n\nThis is a throwaway plain-text source for tooling\nverification only. It is never committed.\n' > throwaway.txt
cd /home/terra/Projects/langatlas-kb/tools/ingest
uv run langatlas-sources new-source throwaway-2026 report "Throwaway Tooling Check" \
  --tier D --grounding third-party-reference --no-canonical \
  --acquisition-note "tooling verification only; not part of the corpus" \
  --out-dir /tmp/throwaway-sources
uv run langatlas-sources ingest throwaway-2026 --file /tmp/throwaway.txt --media-type text/plain
```

Expected: `new-source` prints `wrote /tmp/throwaway-sources/throwaway-2026.yaml`; `ingest`
prints `throwaway-2026: N chunks, QA pass` (or `warn` — a one-paragraph plain-text file has no
outline, so `outline-coverage` silent-no-ops per D37).

- [x] **Step 2: Validate the scaffolded record against the real schema and CI check**

```bash
cd /home/terra/Projects/langatlas-kb/tools/validate
LANGATLAS_ROOT=/tmp/throwaway-repo uv run python -c "
from pathlib import Path
import shutil
repo = Path('/tmp/throwaway-repo')
shutil.rmtree(repo, ignore_errors=True)
(repo / 'sources').mkdir(parents=True)
shutil.copy('/tmp/throwaway-sources/throwaway-2026.yaml', repo / 'sources')
(repo / 'sources' / '_tombstones.yaml').write_text('[]\n')
from langatlas_validate.store import validate_store
print(validate_store(repo))
"
```

Expected: `[]` — zero errors. This is the same `validate_store` Task 1 modified, run against a
`--no-canonical` record that *does* carry `acquisition_note`, confirming the new check does not
false-positive on a well-formed record.

- [x] **Step 3: Clean up the throwaway artifacts**

```bash
rm -rf /tmp/throwaway.txt /tmp/throwaway-sources /tmp/throwaway-repo
psql "$(grep -oP '(?<=dsn: ).*' /home/terra/Projects/langatlas-kb/config/ingest.yaml)" \
  -c "DELETE FROM source_chunks WHERE source_id = 'throwaway-2026'; \
      DELETE FROM source_ingestions WHERE source_id = 'throwaway-2026';"
```

Expected: no output from the `rm`; `DELETE 1` (or `DELETE 0` if promotion didn't happen) from
each SQL statement.

- [x] **Step 4: No commit for this task** — it produced no repo changes; it only proved Tasks
  1–3 work end to end before Task 5 spends real developer QA time on the actual corpus.

---

### Task 5: Ingest the seven already-downloaded seed sources

**Files:**
- Create: `sources/vanroy-haridi-2003.yaml`, `sources/pierce-tapl-2002.yaml`,
  `sources/pierce-attapl-2004.yaml`, `sources/cardelli-wegner-1985.yaml`,
  `sources/shoham-1993.yaml`, `sources/bruce-longo-1990.yaml`, and one
  `sources/software-foundations-plf-<chapter-slug>.yaml` per ingested HTML chapter (see Step 6).

**Interfaces:**
- Consumes: Task 3's `new-source`; the existing `ingest`/`qa` CLI subcommands; the developer's
  collection at `/home/terra/Downloads/hermes-research/` (confirmed present: `VanRoyHaridi2003-
  book.pdf`, `Benjamin_C._Pierce-Types_and_Programming_Languages-The_MIT_Press(2002).pdf`,
  `Benjamin_C._Pierce-Advanced_topics_in_types_and_programming_languages-The_MIT_Press(2004).pdf`,
  `onunderstanding.a4.pdf`, `1-s2.0-0004370293900349-main.pdf`, `1-s2.0-089054019090062M-
  main.pdf`, `pl-foundations/*.html`).
- Produces: seven-plus promoted, chunked sources in `source_chunks` for Task 9's embed step and
  every downstream 2B–2E consumer.

Bibliographic identity was resolved by inspecting each PDF directly (`pdftotext -l 1`) rather
than guessed — the two Elsevier filenames (`1-s2.0-...`) carry no title on their own:

| source_id | Title | Author(s) | Year | Tier | File |
|---|---|---|---|---|---|
| `vanroy-haridi-2003` | Concepts, Techniques, and Models of Computer Programming | Van Roy, Peter; Haridi, Seif | 2003 | B | `VanRoyHaridi2003-book.pdf` |
| `pierce-tapl-2002` | Types and Programming Languages | Pierce, Benjamin C. | 2002 | B | `Benjamin_C._Pierce-Types_and_Programming_Languages-The_MIT_Press(2002).pdf` |
| `pierce-attapl-2004` | Advanced Topics in Types and Programming Languages | Pierce, Benjamin C. (ed.) | 2004 | B | `Benjamin_C._Pierce-Advanced_topics_in_types_and_programming_languages-The_MIT_Press(2004).pdf` |
| `cardelli-wegner-1985` | On Understanding Types, Data Abstraction, and Polymorphism | Cardelli, Luca; Wegner, Peter | 1985 | A | `onunderstanding.a4.pdf` |
| `shoham-1993` | Agent-oriented programming | Shoham, Yoav | 1993 | A | `1-s2.0-0004370293900349-main.pdf` (Artificial Intelligence 60, pp. 51–92; DOI 10.1016/0004-3702(93)90034-9) |
| `bruce-longo-1990` | A Modest Model of Records, Inheritance, and Bounded Quantification | Bruce, Kim B.; Longo, Giuseppe | 1990 | A | `1-s2.0-089054019090062M-main.pdf` (Information and Computation 87, pp. 196–240; DOI 10.1016/0890-5401(90)90062-4) |

All six are `grounding: third-party-reference` (default — none is a phase-1 language spec).
`canonical_source: false` for every one (none of these PDFs come from the publisher's own site;
they're the developer's personal-library/preprint copies) — each therefore needs a real
`acquisition_note`.

- [x] **Step 1: Scaffold the six PDF-backed source records**

```bash
cd /home/terra/Projects/langatlas-kb/tools/ingest

uv run langatlas-sources new-source vanroy-haridi-2003 book \
  "Concepts, Techniques, and Models of Computer Programming" \
  --author "Van Roy, Peter" "Haridi, Seif" --issued-year 2003 --tier B \
  --grounding third-party-reference --no-canonical \
  --acquisition-note "developer's personal library PDF; MIT Press is the canonical publisher"

uv run langatlas-sources new-source pierce-tapl-2002 book "Types and Programming Languages" \
  --author "Pierce, Benjamin C." --issued-year 2002 --tier B \
  --grounding third-party-reference --no-canonical \
  --acquisition-note "developer's personal library PDF; MIT Press is the canonical publisher"

uv run langatlas-sources new-source pierce-attapl-2004 book \
  "Advanced Topics in Types and Programming Languages" \
  --author "Pierce, Benjamin C." --issued-year 2004 --tier B \
  --grounding third-party-reference --no-canonical \
  --acquisition-note "developer's personal library PDF; MIT Press is the canonical publisher"

uv run langatlas-sources new-source cardelli-wegner-1985 article-journal \
  "On Understanding Types, Data Abstraction, and Polymorphism" \
  --author "Cardelli, Luca" "Wegner, Peter" --issued-year 1985 --tier A \
  --grounding third-party-reference --no-canonical \
  --acquisition-note "developer's personal library PDF; ACM Computing Surveys is canonical"

uv run langatlas-sources new-source shoham-1993 article-journal "Agent-oriented programming" \
  --author "Shoham, Yoav" --issued-year 1993 --doi 10.1016/0004-3702(93)90034-9 --tier A \
  --grounding third-party-reference --no-canonical \
  --acquisition-note "developer's personal library PDF; Elsevier ScienceDirect is canonical"

uv run langatlas-sources new-source bruce-longo-1990 article-journal \
  "A Modest Model of Records, Inheritance, and Bounded Quantification" \
  --author "Bruce, Kim B." "Longo, Giuseppe" --issued-year 1990 \
  --doi 10.1016/0890-5401(90)90062-4 --tier A --grounding third-party-reference --no-canonical \
  --acquisition-note "developer's personal library PDF; Elsevier ScienceDirect is canonical"
```

Expected: six `wrote /home/terra/Projects/langatlas-kb/sources/<id>.yaml` lines.

- [x] **Step 2: Ingest each PDF**

```bash
uv run langatlas-sources ingest vanroy-haridi-2003 \
  --file "/home/terra/Downloads/hermes-research/VanRoyHaridi2003-book.pdf"
uv run langatlas-sources ingest pierce-tapl-2002 \
  --file "/home/terra/Downloads/hermes-research/Benjamin_C._Pierce-Types_and_Programming_Languages-The_MIT_Press(2002).pdf"
uv run langatlas-sources ingest pierce-attapl-2004 \
  --file "/home/terra/Downloads/hermes-research/Benjamin_C._Pierce-Advanced_topics_in_types_and_programming_languages-The_MIT_Press(2004).pdf"
uv run langatlas-sources ingest cardelli-wegner-1985 \
  --file "/home/terra/Downloads/hermes-research/onunderstanding.a4.pdf"
uv run langatlas-sources ingest shoham-1993 \
  --file "/home/terra/Downloads/hermes-research/1-s2.0-0004370293900349-main.pdf"
uv run langatlas-sources ingest bruce-longo-1990 \
  --file "/home/terra/Downloads/hermes-research/1-s2.0-089054019090062M-main.pdf"
```

Expected: each prints `<id>: N chunks, QA <pass|warn>` and a `report:` path. A `QA hard gate`
message (exit code 2) means encoding or extraction-collapse failed — read the printed report
path and treat it as a **developer checkpoint**: either the `pymupdf` extraction is genuinely
unusable for that PDF (try `--media-type application/pdf` with `extraction.pdf_backend: docling`
in a local config override, after `pip install 'langatlas-ingest[docling]'`), or the floor needs
a per-source `--min-chars` override. Do not proceed to Step 3 for a source until its QA status is
`pass` or a `warn` the developer has read.

- [x] **Step 2a: STOP — developer checkpoint**

Read every `qa/report.md` printed above (`uv run langatlas-sources qa <id>`). This is the "QA
skims double as golden-set co-authoring time" step (§7.4) — while reading, jot down 2–3 sample
`(claim, locator)` pairs per source that look like clean, unambiguous facts (e.g. "single
assignment enables safe concurrent reads, VanRoyHaridi2003 §4.3") in a scratch note for 2B; this
plan does not consume that note, but not capturing it now means re-reading the same 30 books
later. Confirm every `warn` is an acceptable soft finding (OCR noise, length outliers, missing
outline coverage — never a mojibake or extraction-collapse `fail`) before moving on.

- [x] **Step 3: Resolve the multi-chapter Software Foundations vol. 2 HTML source**

Software Foundations vol. 2 ships as one HTML file per chapter (no combined single-page
export exists in this snapshot: `pl-foundations/Preface.html`, `Norm.html`, `Smallstep.html`,
`Sub.html`, `Typechecking.html`, `MoreStlc.html`, `Equiv.html`, `LibTactics.html`,
`UseTactics.html`, `PE.html`, `RecordsTest.html`, etc.). `extract_document`/`extract_html`
(`tools/ingest/src/langatlas_ingest/extract.py:79-105`,
`tools/ingest/src/langatlas_ingest/backends/html.py`) ingest exactly one file per `source_id` —
there is no multi-page-docs backend today (confirmed: `store.SourceChunk.path` is `None` on
every chunk any current backend produces). Building one is out of scope for 2A ("no infra
changes expected" — this is a CLI-behavior change, not a config change, and multi-page-docs
locators are unexercised in the real corpus so far). **Resolution: one `source_id` per chapter
file**, sharing the same canonical origin, distinguished by a chapter-suffixed title —
exactly the pattern this table lists for the four in-scope chapters (the rest of the book is
Stage 3's to ingest as its themes reach type systems / operational semantics; ingesting all ~15
chapters up front is not required for R1's exit condition, only *some* ingested content from
each seed source is):

| source_id | chapter file | title |
|---|---|---|
| `software-foundations-plf-preface` | `Preface.html` | Software Foundations, Vol. 2: Programming Language Foundations — Preface |
| `software-foundations-plf-stlc` | (compile `Stlc.html` from `Stlc.v` first — see note below) | ... — The Simply Typed Lambda-Calculus |
| `software-foundations-plf-typechecking` | `Typechecking.html` | ... — Type Checking |
| `software-foundations-plf-norm` | `Norm.html` | ... — Strong Normalization |

`Stlc.html` is not present in the snapshot (only `StlcProp.v`/`StlcProp.html`-adjacent files are)
— check `pl-foundations/toc.html` for the actual chapter list and file names before scaffolding;
the table above is illustrative of the naming convention, not a literal file listing to trust
blindly. Use `ls /home/terra/Downloads/hermes-research/pl-foundations/*.html` to get the real,
current file list first.

- [x] **Step 4: Scaffold and ingest each chosen Software Foundations chapter**

For each chapter file chosen in Step 3 (repeat this shape per chapter, substituting the
chapter's real filename/title):

```bash
uv run langatlas-sources new-source software-foundations-plf-norm webpage \
  "Software Foundations, Vol. 2: Programming Language Foundations — Strong Normalization" \
  --url "https://softwarefoundations.cis.upenn.edu/plf-current/Norm.html" \
  --tier B --grounding third-party-reference --canonical \
  --edition "current" \
  --edition-check-url "https://softwarefoundations.cis.upenn.edu/plf-current/Norm.html"

uv run langatlas-sources ingest software-foundations-plf-norm \
  --file "/home/terra/Downloads/hermes-research/pl-foundations/Norm.html" \
  --media-type text/html --locator-kinds web-fragment
```

`--canonical` here (unlike Task 5's PDFs) because the URL given *is* the official publishing
site — no `acquisition_note` is required by Task 1's check for these records.

Expected per chapter: `<id>: N chunks, QA <pass|warn>`.

- [x] **Step 5: Commit**

```bash
git add sources/vanroy-haridi-2003.yaml sources/pierce-tapl-2002.yaml \
  sources/pierce-attapl-2004.yaml sources/cardelli-wegner-1985.yaml sources/shoham-1993.yaml \
  sources/bruce-longo-1990.yaml sources/software-foundations-plf-*.yaml
git commit -m "feat(#stage-2a): ingest the seven already-acquired D15 seed sources"
```

---

### Task 6: Acquire and ingest Jordan et al. 2015

**Files:** Create `sources/jordan-et-al-2015.yaml`.

**Interfaces:**
- Consumes: Task 3's `file-acquisitions` entry (already filed in Task 3 Step 6); `new-source`;
  `ingest`.
- Produces: one promoted source used as a **priming reference across the whole R3 research
  phase**, not just a chunk contributor — CLAUDE.md's Sources section and §7.4 both treat it as
  the seed feature-model document.

- [x] **Step 1: STOP — developer checkpoint: locate the PDF**

`config/acquisitions.yaml` (Task 3) already flags this as `access-pending`: the PDF was
attached to the original Notion brief as `feature-model.pdf` and is not present anywhere in this
repo or in `/home/terra/Downloads/hermes-research/` (confirmed by search). Options, in order of
preference: (a) re-download the attachment from the original Notion page, (b) search for the
paper's DOI/publisher record if it was later published outside Notion, (c) if genuinely
unrecoverable, leave the `pending-source` queue entry open indefinitely per D37's "genuinely
inaccessible sources stay visibly parked" clause and skip to Task 7 — **do not fabricate or
substitute a different paper**.

- [x] **Step 2: Scaffold and ingest once acquired**

```bash
cd /home/terra/Projects/langatlas-kb/tools/ingest
uv run langatlas-sources new-source jordan-et-al-2015 article-journal \
  "A feature model of programming languages" \
  --author "Jordan, H." --issued-year 2015 --tier A --grounding third-party-reference \
  --no-canonical --acquisition-note "re-acquired from the original Notion brief attachment"
uv run langatlas-sources ingest jordan-et-al-2015 --file <path-to-the-pdf>
```

(Fill in the remaining authors from the PDF's own title page once acquired, exactly as Task 5
identified Shoham 1993/Bruce & Longo 1990 by inspection rather than guesswork — `pdftotext -l 1
<path> -` prints the title page.)

- [x] **Step 3: Resolve the sourcing-queue entry**

```bash
uv run langatlas-sources queue --kind pending-source
```

Expected: the `jordan-et-al-2015` line is gone (a successful `ingest` calls
`SourcingQueue.resolve` automatically — `pipeline.py:172`). If it still lists a *different*
reason (`partially-ingested`, i.e. a QA hard gate fired), that is a developer checkpoint, not
this task's failure — read the QA report before re-attempting.

- [x] **Step 4: Commit**

```bash
git add sources/jordan-et-al-2015.yaml
git commit -m "feat(#stage-2a): ingest Jordan et al. 2015, the R3 feature-model seed"
```

If Step 1 concluded the source stays parked, skip this commit entirely and leave a note in the
plan's own checkbox (do not check off Task 6 — leave it `[ ]` with a trailing note, since D37
explicitly wants a parked source to stay *visibly* unresolved rather than silently marked done).

---

### Task 7: Acquire and ingest the six D27 texts

**Files:** Create `sources/harper-pfpl.yaml`, `sources/krishnamurthi-plai.yaml`,
`sources/kaijanaho-2015.yaml`, `sources/scott-plp.yaml`, `sources/turbak-gifford-dcpl.yaml`,
`sources/sebesta-copl.yaml`.

**Interfaces:**
- Consumes: `config/acquisitions.yaml` entries filed in Task 3 Step 6; `new-source`; `ingest`.
- Produces: the six D27-ratified acquisitions, split three free / three paywalled.

- [x] **Step 1: STOP — developer checkpoint: the three free titles**

Download and drop into a working directory (not the snapshot store — `ingest --file` copies
into the snapshot store itself):
- Harper, *Practical Foundations for Programming Languages* — free PDF from the author's page.
- Krishnamurthi, *Programming Languages: Application and Interpretation* (PLAI) — free from
  plai.org.
- Kaijanaho (2015) thesis — free from JYU's institutional repository.

- [x] **Step 2: Scaffold and ingest the three free titles**

```bash
cd /home/terra/Projects/langatlas-kb/tools/ingest

uv run langatlas-sources new-source harper-pfpl book \
  "Practical Foundations for Programming Languages" --author "Harper, Robert" \
  --url "https://www.cs.cmu.edu/~rwh/pfpl/" --tier B --grounding third-party-reference \
  --canonical
uv run langatlas-sources ingest harper-pfpl --file <path-to-downloaded-pdf>

uv run langatlas-sources new-source krishnamurthi-plai book \
  "Programming Languages: Application and Interpretation" --author "Krishnamurthi, Shriram" \
  --url "https://www.plai.org/" --tier B --grounding third-party-reference --canonical
uv run langatlas-sources ingest krishnamurthi-plai --file <path-to-downloaded-pdf>

uv run langatlas-sources new-source kaijanaho-2015 thesis \
  "Evaluation of Programming Languages and Tools" --author "Kaijanaho, Antti-Juhani" \
  --issued-year 2015 --tier B --grounding third-party-reference --canonical
uv run langatlas-sources ingest kaijanaho-2015 --file <path-to-downloaded-pdf>
```

Expected per title: `<id>: N chunks, QA <pass|warn>`; verify each with `uv run langatlas-sources
qa <id>` per Task 5's QA-skim checkpoint before moving on.

- [x] **Step 3: STOP — developer checkpoint: the three paywalled titles**

Via university library access, obtain: Scott, *Programming Language Pragmatics*; Turbak &
Gifford, *Design Concepts in Programming Languages*; Sebesta, *Concepts of Programming
Languages*. This step has no fixed timeline — `config/acquisitions.yaml`'s `paywalled` entries
stay open in `sourcing_queue` until each arrives; check status any time with
`uv run langatlas-sources queue --kind pending-source`.

- [x] **Step 4: Scaffold and ingest each paywalled title as it arrives**

```bash
uv run langatlas-sources new-source scott-plp book "Programming Language Pragmatics" \
  --author "Scott, Michael L." --tier B --grounding third-party-reference --no-canonical \
  --acquisition-note "acquired via university library access"
uv run langatlas-sources ingest scott-plp --file <path-to-library-copy>

uv run langatlas-sources new-source turbak-gifford-dcpl book \
  "Design Concepts in Programming Languages" \
  --author "Turbak, Franklyn" "Gifford, David" --tier B --grounding third-party-reference \
  --no-canonical --acquisition-note "acquired via university library access"
uv run langatlas-sources ingest turbak-gifford-dcpl --file <path-to-library-copy>

uv run langatlas-sources new-source sebesta-copl book "Concepts of Programming Languages" \
  --author "Sebesta, Robert W." --tier B --grounding third-party-reference --no-canonical \
  --acquisition-note "acquired via university library access"
uv run langatlas-sources ingest sebesta-copl --file <path-to-library-copy>
```

- [x] **Step 5: Commit each title as it lands** (do not batch all six into one commit if the
  paywalled three arrive on a different day than the free three — smaller, real-time commits
  keep the git history matching when acquisition actually happened):

```bash
git add sources/harper-pfpl.yaml sources/krishnamurthi-plai.yaml sources/kaijanaho-2015.yaml
git commit -m "feat(#stage-2a): ingest the three free D27 acquisitions"
# ... later, once library access delivers the rest ...
git add sources/scott-plp.yaml sources/turbak-gifford-dcpl.yaml sources/sebesta-copl.yaml
git commit -m "feat(#stage-2a): ingest the three paywalled D27 acquisitions"
```

---

### Task 8: Ingest the D28 phase-1 language specs (Python, C, Java, Rust, Haskell, Prolog)

**Files:** Create one `sources/<lang>-*.yaml` per spec listed below (Prolog's is already on
disk, unlike the rest — see Step 1).

**Interfaces:**
- Consumes: `new-source`; `ingest`; the D51 grounding table (§4.2) already reproduced in this
  plan's Global Constraints — used directly for each record's `--grounding` value, so Task 10's
  retroactive pass has nothing left to do for these six sources specifically (they're classified
  correctly at first ingestion, per §4.2's "phases 2–4 classify at their own ingestion time"
  carve-out — phase 1 gets the one-time pass, but nothing stops getting it right immediately).
- Produces: the ontology stress-set's grounding corpus, consumed by every later Stage 3 R3/R4
  session for these six languages.

Editions pinned per §7.5: C23/N3220, JLS SE 25, Haskell 2010 + latest GHC User's Guide, Prolog
via Deransart et al. 1996 (**already acquired** — confirmed present at
`/home/terra/Downloads/hermes-research/Prolog The Standard Reference Manual (Pierre Deransart,
AbdelAli Ed-Dbali etc.).pdf`), Rust split between the Reference and the FLS.

| language | source_id | grounding | doc | acquisition |
|---|---|---|---|---|
| Prolog | `deransart-prolog-1996` | `formal-spec` | Deransart, Ed-Dbali et al., *Prolog: The Standard Reference Manual* (1996) | **already have the PDF** |
| Python | `python-langref-3` | `reference-implementation-docs` | CPython Language Reference | official docs PDF download (docs.python.org) |
| Python | `pep-8` (repeat per referenced PEP as needed by later sweeps) | `design-doc` | PEP index entries | single-page HTML per PEP |
| C | `c23-n3220` | (unclassified in §4.2's table — default `third-party-reference` unless the developer judges the WG14 *draft* itself warrants `formal-spec`; **flag this as an open question for the developer**, do not silently pick one) | WG14 N3220 (C23 draft) | single PDF, open access |
| Java | `jls-se25` | (same open-question note as C — §4.2 names Python/R/Rust/TypeScript/SQL explicitly but not C or Java; do not default silently) | *The Java Language Specification*, SE 25 | single PDF, Oracle |
| Rust | `rust-reference` | `reference-implementation-docs` | The Rust Reference | mdBook site — check for a `/print.html` single-page export first |
| Rust | `rust-fls` | `formal-spec` | Ferrocene Language Specification | mdBook site — check for a `/print.html` single-page export first |
| Haskell | `haskell-2010-report` | `formal-spec` (per Prolog's own precedent — a language *report* is the formal-spec role; confirm against §4.2's actual wording before committing, since Haskell isn't named there either) | Haskell 2010 Language Report | single PDF |
| Haskell | `ghc-users-guide` | `reference-implementation-docs` | latest GHC User's Guide | check for a PDF download on readthedocs |

- [x] **Step 1: STOP — developer checkpoint: resolve the two open grounding classifications**

§4.2's per-language table names Python, R, Rust, TypeScript, SQL, and Prolog explicitly; it does
not name C, Java, or Haskell. Before scaffolding those three languages' records, the developer
must decide their `grounding` value (most likely `formal-spec` for a numbered ISO/ANSI-style
draft standard or language report, `reference-implementation-docs` otherwise) and record that
decision back into [context/decisions.md](../../../context/decisions.md) under D51 as a
*proposed* amendment (per this repo's decision-hygiene convention) — **do not silently pick a
default and move on**, since this is exactly the kind of judgment call §4.2 reserves for a
one-time retroactive pass, not an inferred default.

- [x] **Step 2: For each spec, find or confirm a single-file ingestible form**

The existing ingestion CLI has no multi-page-docs backend (same constraint as Task 5 Step 3).
Before acquiring anything, check each doc's official site for a single-file export:
- Python: docs.python.org offers per-manual PDF downloads (`archives/` or the version's
  "Download" page) — use the Language Reference PDF, not the multi-page HTML site.
- C23/N3220: WG14's public document register hosts N3220 as a single PDF.
- JLS SE 25: Oracle publishes the JLS as a single PDF per release.
- Rust Reference / FLS: both are mdBook sites; check `<site>/print.html` for a combined
  single-page HTML export before concluding none exists.
- Haskell 2010 Report: a single PDF at haskell.org.
- GHC User's Guide: check readthedocs for a PDF download link (readthedocs projects commonly
  expose one).

If a spec genuinely has no single-file form (neither PDF nor a `print.html`-style export), **do
not build a new ingestion backend inside 2A** — file it as a finding in this task's commit
message and in `sourcing_queue` (`reason: acquisition-failed`, `detail` explaining the missing
single-file form), leaving it for a deliberate later decision about whether a multi-page-docs
backend is worth building. This mirrors the sequencing map's explicit instruction: a needed
ingestion-CLI *behavior* change is a finding to surface, not a silent fix within 2A.

- [x] **Step 3: Scaffold and ingest Prolog (already acquired)**

```bash
cd /home/terra/Projects/langatlas-kb/tools/ingest
uv run langatlas-sources new-source deransart-prolog-1996 book \
  "Prolog: The Standard Reference Manual" \
  --author "Deransart, Pierre" "Ed-Dbali, AbdelAli" --issued-year 1996 --tier A \
  --grounding formal-spec --no-canonical \
  --acquisition-note "developer's personal library PDF; ISO/IEC 13211-1 purchase not needed \
per D28's phase-1 selection rationale"
uv run langatlas-sources ingest deransart-prolog-1996 \
  --file "/home/terra/Downloads/hermes-research/Prolog The Standard Reference Manual (Pierre Deransart, AbdelAli Ed-Dbali etc.).pdf"
```

- [x] **Step 4: Scaffold and ingest each remaining phase-1 spec once acquired**

Repeat Task 5's scaffold-then-ingest shape per row of the table above, using each row's
resolved `grounding` value from Step 1, `--tier A` for a numbered ISO/ANSI-style
standard/formal report and `--tier B` for reference-implementation docs (per §4.1's tier
definitions), and `--canonical` whenever the URL/PDF comes straight from the spec's own
publishing body (true for all of these — Python, WG14, Oracle, the Rust project, and
haskell.org/GHC all publish their own specs directly).

- [x] **Step 5: Commit as each spec lands**

```bash
git add sources/deransart-prolog-1996.yaml
git commit -m "feat(#stage-2a): ingest Deransart et al. 1996, Prolog's phase-1 formal-spec source"
# ... one commit per additional spec as it's acquired and ingested ...
```

---

### Task 9: D37 retroactive backfill verification

**Files:** none new — this task edits whichever `sources/*.yaml` files Tasks 5–8 produced, if
any slipped through without `canonical_source`/`acquisition_note` set.

**Interfaces:**
- Consumes: Task 1's extended `validate_store`.
- Produces: a corpus where `langatlas-validate ci`'s STORE section is silent about every
  source record — the exit condition the sequencing map calls "the R1 initial corpus gets a
  one-time retroactive backfill."

- [x] **Step 1: Run the CI check across every source record produced so far**

```bash
cd /home/terra/Projects/langatlas-kb/tools/validate
uv run langatlas-validate ci 2>&1 | grep -E "^STORE .*sources/"
```

Expected: no output. Because Task 5–8's `new-source` invocations already pass
`--canonical`/`--no-canonical --acquisition-note ...` explicitly per source, this step should
be a confirmation, not a fix — but every source record was hand-typed into a shell command, so
treat any hit here as a real gap to fix (edit the offending `sources/<id>.yaml`'s `custom` block
directly, then re-run `uv run langatlas-validate precommit --kind source sources/<id>.yaml` to
confirm it's clean and normalized).

- [x] **Step 2: Commit any fixes found**

```bash
git add sources/<fixed-id>.yaml
git commit -m "fix(#stage-2a): backfill missing D37 acquisition_note on <fixed-id>"
```

If Step 1 found nothing to fix, skip this commit — there is nothing to record.

---

### Task 10: D51 grounding classification retroactive pass

**Files:** none new — confirms/corrects `custom.grounding` on the phase-1 six languages' source
records only (Task 8's records already set it correctly at first ingestion, per Task 8's own
note; this task is the explicit retroactive-pass checkpoint the sequencing map names as a
separate produced deliverable, not a duplicate of Task 8).

**Interfaces:**
- Consumes: §4.2's per-language grounding table (reproduced in Task 8); the phase-1 source
  records Task 8 produced.
- Produces: the one-time retroactive classification the exit condition (sequencing map, item 1)
  names explicitly as separate from ordinary ingestion.

- [x] **Step 1: Enumerate every phase-1-language source record and its `custom.grounding`**

```bash
cd /home/terra/Projects/langatlas-kb
grep -A1 "^custom:" sources/{python,c23,jls,rust,haskell,ghc,deransart}*.yaml 2>/dev/null \
  | grep -B1 "grounding"
```

- [x] **Step 2: Cross-check each value against §4.2 and this plan's Global Constraints table**

Confirm: Python → `reference-implementation-docs` (any PEP records → `design-doc`); Rust's
Reference → `reference-implementation-docs`, Rust's FLS → `formal-spec`; Prolog →
`formal-spec`. Confirm C/Java/Haskell match whatever the developer ratified in Task 8 Step 1
(and that ratification is reflected in `context/decisions.md` under D51 — if it is not, that is
this task's finding: go back and record it, since a grounding value with no traceable rationale
is exactly the drift D51's retroactive pass exists to catch).

- [x] **Step 3: Fix and re-normalize any mismatch found**

```bash
uv run langatlas-validate precommit --kind source sources/<id>.yaml
```

Expected: no output (clean). Edit the record's `custom.grounding` value directly if Step 2 found
a mismatch, then re-run this command to confirm the edit is schema-valid and normalized.

- [x] **Step 4: Commit any fixes found**

```bash
git add sources/<fixed-id>.yaml
git commit -m "fix(#stage-2a): correct D51 grounding classification on <fixed-id>"
```

---

### Task 11: Batch-embed the corpus and final exit-condition check

**Files:** none new.

**Interfaces:**
- Consumes: `langatlas-sources embed` (`cli.py:96-106`, wraps `embed.embed_source(ctx, conn,
  source_id=None, config=, batch_size=)`); `langatlas-sources eval`; `langatlas-validate ci`.
- Produces: a fully embedded corpus on the incumbent `qwen3-embedding-4b` (per
  `config/ingest.yaml`'s `models.embedding`) — the queryable index 2B and 2C need. This is
  the R1 half of item 1 in the sequencing map's Stage 2 exit condition.

- [x] **Step 1: Batch-embed every unembedded chunk**

```bash
cd /home/terra/Projects/langatlas-kb/tools/ingest
uv run langatlas-sources embed
```

Expected: `embedded N chunks on qwen3-embedding-4b`, where N equals the sum of every source's
`chunk_count` from Tasks 5–8's ingest output. This can take hours against a slow university API
for the full corpus — it is safe to interrupt and re-run (`embed_source` only ever touches
`store.unembedded(table)`, per `embed.py:23-26`'s own docstring).

- [x] **Step 2: Sanity-check retrieval works end to end**

```bash
uv run langatlas-sources search "static type checking" -k 5
```

Expected: five hits with real `source_id`/`locator` pairs drawn from the corpus just ingested —
this is a smoke test, not 2B's real golden-set eval (`tests/golden/retrieval/` is still
deliberately empty; `langatlas-sources eval` will print `golden_dir_missing` and that is
correct at this point in the sequencing — 2B fills it next, not this plan).

- [x] **Step 3: Run the full validation/CI gate one last time**

```bash
cd /home/terra/Projects/langatlas-kb/tools/validate
uv run langatlas-validate ci
```

Expected: exit code 0. This is the mechanical half of the sequencing map's exit-condition item
1 ("Seed corpus + phase-1 language specs ingested, QA-skimmed, with `canonical_source`/
`acquisition_note` backfilled and phase-1 `grounding` classified") — the QA-skimmed and
grounding-classified halves were Tasks 5–10's developer checkpoints, not something a command can
certify on its own.

- [x] **Step 4: No commit for this task** — embedding writes only to the private snapshot
  store and Postgres, both git-excluded by design (D15); there is nothing new to stage.

---

## Self-review

**Spec coverage** — every 2A "Produces"/"Produces for 2B–2E" bullet from the sequencing map
traces to a task: acquisition tracking → Tasks 3/6/7; ingested seed corpus → Tasks 5–8; per-source
QA reports → Tasks 5–8's checkpoints; D37 backfill → Tasks 1/9; D51 grounding → Task 10; batch
embed → Task 11; real chunk ids / committed source records for 2B–2E → the cumulative effect of
Tasks 5–11. §4.4's edition/link-checker/quarterly-check machinery is explicitly **2E's**, not
2A's, per the sequencing map — correctly absent here. The repo-file-ingestion-backend question
named in the sequencing map's "Not built by Stage 1" section is resolved (Task 5 Step 3, Task 8
Step 2): no seed or phase-1 source needs one, given single-file PDF/print-page alternatives; a
genuine gap is a filed finding, not a silent workaround.

**Placeholder scan** — no "TBD"/"handle appropriately"/unshown code. The two genuinely open
judgment calls this plan cannot resolve on its own (C/Java/Haskell's `grounding` value; whether
Jordan et al. 2015 is recoverable) are marked as explicit developer-checkpoint stops with named
resolution paths, not silently deferred placeholders.

**Type consistency** — `render_source_yaml`'s keyword names (Task 2) match `new-source`'s CLI
flags (Task 3) match every `new-source` invocation in Tasks 5–8 (`--tier`, `--grounding`,
`--canonical`/`--no-canonical`, `--acquisition-note`, `--edition`, `--edition-check-url`,
`--locator-kinds`). `SourcingQueue.file`'s keyword names (`kind=`, `source_id=`, `reason=`,
`detail=`) match both Task 3's `_cmd_file_acquisitions` and the existing `pipeline.py` call
sites it was copied from.

---

## Execution handoff

Plan complete and saved to
`docs/superpowers/plans/2026-08-23-stage-2a-corpus-assembly-ingestion-qa.md`. Two execution
options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between
tasks, fast iteration. Note that Tasks 5–8 contain hard developer-checkpoint stops (book
acquisition) that no subagent can push through — expect this execution mode to pause and hand
control back to you at each one.

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution
with checkpoints for review.

Which approach?
