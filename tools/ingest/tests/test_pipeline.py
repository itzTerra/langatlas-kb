# tools/ingest/tests/test_pipeline.py
import pytest
from langatlas_ingest.config import IngestConfig
from langatlas_ingest.db import migrate
from langatlas_ingest.errors import ExtractionFailed, QaHardGate, SnapshotMissing
from langatlas_ingest.embed import embed_source
from langatlas_ingest.pipeline import ingest_source, reingest_all
from langatlas_ingest.snapshot import SnapshotStore
from langatlas_ingest.store import SourceChunksStore, SourcingQueue

pytestmark = pytest.mark.db

CONFIG = IngestConfig.load(overrides={"chunk_target_tokens": 40, "chunk_max_tokens": 60,
                                      "chunk_overlap_tokens": 8})

BODY = ("A match expression compares a scrutinee against a sequence of patterns and "
        "evaluates the arm of the first pattern that matches it. ") * 6
GOOD_HTML = (f"<html><body><h1 id='expressions'>Expressions</h1><p>{BODY}</p>"
             f"<h2 id='match-expressions'>Match expressions</h2><p>{BODY}</p></body></html>")

# Short enough to trip QA's extraction-collapse gate (under its 500 non-whitespace-char
# floor) but still substantial enough that trafilatura emits a real <head>. A document
# below that structural threshold degrades to headingless body text (see
# backends/html.py), and the chunker would then raise ExtractionFailed for want of an
# admissible web-fragment locator — never reaching the QA gate this test is about.
TINY_HTML = ("<html><body><article><h1 id='a'>Alpha section</h1><p>"
             + "Patterns bind names. " * 20
             + "</p></article></body></html>")


@pytest.fixture
def prepared(db_conn, snapshot_root, tmp_path):
    migrate(db_conn)
    path = tmp_path / "ref.html"
    path.write_text(GOOD_HTML)
    snapshots = SnapshotStore(snapshot_root)
    snapshots.put("rust-ref", path, media_type="text/html",
                  source_url="https://example.org/ref")
    return snapshots


def test_ingest_promotes_chunks_and_writes_the_qa_report(db_conn, prepared, snapshot_root):
    result = ingest_source("rust-ref", conn=db_conn, config=CONFIG, snapshots=prepared,
                           locator_kinds=["web-fragment"])

    assert result.promoted is True
    assert result.chunk_count > 0
    assert result.chunk_count == len(SourceChunksStore(db_conn).by_source("rust-ref"))
    assert (snapshot_root / "rust-ref" / "qa" / "report.md").exists()
    assert (snapshot_root / "rust-ref" / "extracted" / "document.json").exists()
    assert SourcingQueue(db_conn).open_entries() == []


def test_a_hard_gate_failure_promotes_nothing_and_queues_the_source(db_conn, snapshot_root,
                                                                    tmp_path):
    migrate(db_conn)
    path = tmp_path / "bad.html"
    path.write_text(TINY_HTML)
    snapshots = SnapshotStore(snapshot_root)
    snapshots.put("bad", path, media_type="text/html")

    with pytest.raises(QaHardGate) as excinfo:
        ingest_source("bad", conn=db_conn, config=CONFIG, snapshots=snapshots,
                      locator_kinds=["web-fragment"])

    assert "extraction-collapse" in [c.check_id for c in excinfo.value.checks]
    assert SourceChunksStore(db_conn).by_source("bad") == []
    entries = SourcingQueue(db_conn).open_entries()
    assert [(e["source_id"], e["reason"]) for e in entries] == [("bad", "partially-ingested")]
    with db_conn.cursor() as cur:
        cur.execute("SELECT promoted, qa_status FROM source_ingestions WHERE source_id='bad'")
        assert cur.fetchone() == (False, "fail")


def test_reingesting_replaces_rather_than_appends(db_conn, prepared):
    first = ingest_source("rust-ref", conn=db_conn, config=CONFIG, snapshots=prepared,
                          locator_kinds=["web-fragment"])
    second = ingest_source("rust-ref", conn=db_conn, config=CONFIG, snapshots=prepared,
                           locator_kinds=["web-fragment"])
    assert first.chunk_count == second.chunk_count
    assert len(SourceChunksStore(db_conn).by_source("rust-ref")) == second.chunk_count


def test_reingesting_reproduces_the_identical_rows(db_conn, prepared):
    """D1: Postgres is a regenerable derived artifact — re-running ingestion from the same
    snapshot must reproduce the same rows, not merely the same count."""
    ingest_source("rust-ref", conn=db_conn, config=CONFIG, snapshots=prepared,
                  locator_kinds=["web-fragment"])
    before = SourceChunksStore(db_conn).by_source("rust-ref")
    ingest_source("rust-ref", conn=db_conn, config=CONFIG, snapshots=prepared,
                  locator_kinds=["web-fragment"])
    assert SourceChunksStore(db_conn).by_source("rust-ref") == before
    with db_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM source_chunks")
        assert cur.fetchone()[0] == len(before)


def test_a_gate_failure_demotes_a_previously_promoted_source(db_conn, prepared,
                                                             snapshot_root, tmp_path):
    """The gate is not just a doorman on first entry: a re-ingest that now fails QA must
    take the stale chunks back out rather than leave a refused source readable."""
    ingest_source("rust-ref", conn=db_conn, config=CONFIG, snapshots=prepared,
                  locator_kinds=["web-fragment"])
    assert SourceChunksStore(db_conn).by_source("rust-ref") != []

    degraded = tmp_path / "degraded.html"
    degraded.write_text(TINY_HTML)
    prepared.put("rust-ref", degraded, media_type="text/html")
    with pytest.raises(QaHardGate):
        ingest_source("rust-ref", conn=db_conn, config=CONFIG, snapshots=prepared,
                      locator_kinds=["web-fragment"])

    assert SourceChunksStore(db_conn).by_source("rust-ref") == []
    with db_conn.cursor() as cur:
        cur.execute("SELECT promoted, chunk_count FROM source_ingestions"
                    " WHERE source_id = 'rust-ref'")
        assert cur.fetchone() == (False, 0)


def test_a_missing_snapshot_is_queued_and_still_raises(db_conn, snapshot_root):
    """D37: a refused source stays visible. A source that was never acquired must not fail
    more quietly than one that fails QA."""
    migrate(db_conn)
    snapshots = SnapshotStore(snapshot_root)
    with pytest.raises(SnapshotMissing):
        ingest_source("ghost", conn=db_conn, config=CONFIG, snapshots=snapshots,
                      locator_kinds=["web-fragment"])
    entries = SourcingQueue(db_conn).open_entries()
    assert [(e["source_id"], e["reason"]) for e in entries] == [("ghost", "acquisition-failed")]
    assert entries[0]["detail"] != ""


def test_an_extraction_failure_is_queued_and_still_raises(db_conn, snapshot_root, tmp_path):
    """A document below trafilatura's structure threshold degrades to headingless body
    text, so no web-fragment locator is admissible and the chunker refuses it — before any
    database write. It must still leave a trace."""
    migrate(db_conn)
    path = tmp_path / "degenerate.html"
    path.write_text("<html><body><h1 id='a'>A</h1><p>b c d</p></body></html>")
    snapshots = SnapshotStore(snapshot_root)
    snapshots.put("degenerate", path, media_type="text/html")

    with pytest.raises(ExtractionFailed):
        ingest_source("degenerate", conn=db_conn, config=CONFIG, snapshots=snapshots,
                      locator_kinds=["web-fragment"])

    entries = SourcingQueue(db_conn).open_entries()
    assert [(e["source_id"], e["reason"]) for e in entries] == [("degenerate",
                                                                "partially-ingested")]
    assert "no admissible locator" in entries[0]["detail"]
    assert SourceChunksStore(db_conn).by_source("degenerate") == []


def test_ingest_resolves_a_pending_source_entry(db_conn, prepared):
    """Section 4.4: claims citing an un-ingested source park in `pending-source` and
    auto-resume the moment the source ingests."""
    SourcingQueue(db_conn).file(kind="pending-source", source_id="rust-ref",
                                reason="not-ingested")
    ingest_source("rust-ref", conn=db_conn, config=CONFIG, snapshots=prepared,
                  locator_kinds=["web-fragment"])
    assert SourcingQueue(db_conn).open_entries() == []


# --- D1 regenerability and the re-embed short-circuit ---------------------------------

def _drop_the_database(db_conn):
    """Simulate D1's "drop the database and re-run ingestion from the snapshot store":
    the derived rows go, the private snapshot tier stays."""
    with db_conn.cursor() as cur:
        cur.execute("DELETE FROM source_chunks")
        cur.execute("DELETE FROM source_ingestions")


def test_locator_kinds_are_stored_and_reused_when_no_flag_is_given(db_conn, prepared):
    """`locator_kinds` decides every emitted locator — the public citation surface — and
    used to live only in an ad-hoc CLI flag that was discarded after the run. Re-ingesting
    without remembering the flag silently produced DIFFERENT locators (DEFAULT_LOCATOR_KINDS
    prefers `web-fragment` here, which is exactly what a forgotten flag would have given)."""
    ingest_source("rust-ref", conn=db_conn, config=CONFIG, snapshots=prepared,
                  locator_kinds=["named-section"])
    assert prepared.get("rust-ref").locator_kinds == ["named-section"]
    before = [c.locator for c in SourceChunksStore(db_conn).by_source("rust-ref")]
    assert all(locator.startswith("§ ") for locator in before)

    _drop_the_database(db_conn)
    ingest_source("rust-ref", conn=db_conn, config=CONFIG, snapshots=prepared)

    after = [c.locator for c in SourceChunksStore(db_conn).by_source("rust-ref")]
    assert after == before, "a re-ingest with no flag must reproduce the stored locators"


def test_an_explicit_flag_overrides_and_updates_the_stored_kinds(db_conn, prepared):
    ingest_source("rust-ref", conn=db_conn, config=CONFIG, snapshots=prepared,
                  locator_kinds=["named-section"])
    ingest_source("rust-ref", conn=db_conn, config=CONFIG, snapshots=prepared,
                  locator_kinds=["web-fragment"])

    assert prepared.get("rust-ref").locator_kinds == ["web-fragment"]
    locators = [c.locator for c in SourceChunksStore(db_conn).by_source("rust-ref")]
    assert all(locator.startswith("#") for locator in locators), \
        "a changed preference order must re-run the pipeline, not be skipped as unchanged"


def test_min_chars_is_stored_and_reused_when_no_flag_is_given(db_conn, prepared,
                                                              snapshot_root, tmp_path):
    """The QA floor decides whether a source is promoted at all, so — exactly like
    `locator_kinds` — it cannot live only in a flag the developer has to remember. A
    legitimately tiny source admitted once must not be hard-gated by the re-ingest that
    forgot the flag, which would silently drop it back out of the corpus."""
    migrate(db_conn)
    path = tmp_path / "errata.html"
    path.write_text(TINY_HTML)
    prepared.put("errata", path, media_type="text/html")

    first = ingest_source("errata", conn=db_conn, config=CONFIG, snapshots=prepared,
                          locator_kinds=["web-fragment"], min_chars=200)
    assert first.promoted and first.chunk_count > 0
    assert prepared.get("errata").min_chars == 200

    _drop_the_database(db_conn)
    second = ingest_source("errata", conn=db_conn, config=CONFIG, snapshots=prepared,
                           locator_kinds=["web-fragment"])

    assert second.promoted is True, "a re-ingest with no flag must reuse the stored floor"
    assert second.chunk_count == first.chunk_count
    assert SourceChunksStore(db_conn).by_source("errata") != []


def test_without_a_stored_min_chars_the_default_floor_still_gates(db_conn, prepared,
                                                                  tmp_path):
    """The override is opt-in per source: a source that never declared one keeps QA's own
    floor, so `None` can never read as 'no floor at all'."""
    path = tmp_path / "bad.html"
    path.write_text(TINY_HTML)
    prepared.put("still-bad", path, media_type="text/html")
    with pytest.raises(QaHardGate):
        ingest_source("still-bad", conn=db_conn, config=CONFIG, snapshots=prepared,
                      locator_kinds=["web-fragment"])


def test_a_changed_min_chars_re_runs_qa_instead_of_skipping(db_conn, prepared, fake_ctx,
                                                            tmp_path):
    """`min_chars` moves the promotion verdict for byte-identical content, so it belongs
    in the currency key beside the chunking knobs: raising the floor on an already-ingested
    source must actually re-run the gate, not be skipped as unchanged and leave a source
    promoted under a floor it no longer meets."""
    path = tmp_path / "errata.html"
    path.write_text(TINY_HTML)
    prepared.put("errata", path, media_type="text/html")
    first = ingest_source("errata", conn=db_conn, config=CONFIG, snapshots=prepared,
                          locator_kinds=["web-fragment"], min_chars=200)
    assert first.promoted and SourceChunksStore(db_conn).by_source("errata") != []

    # Everything else about the run is identical; only the floor moved, and it now
    # exceeds the source's honest length.
    with pytest.raises(QaHardGate):
        ingest_source("errata", conn=db_conn, config=CONFIG, snapshots=prepared,
                      locator_kinds=["web-fragment"], min_chars=100000)

    assert SourceChunksStore(db_conn).by_source("errata") == [], \
        "the re-ingest was skipped as unchanged instead of re-running the gate"


def test_adding_a_min_chars_override_does_not_disturb_a_source_without_one(db_conn,
                                                                           prepared):
    """The floor is omitted from the fingerprint when unset, so every source recorded
    before the field existed still fingerprints identically to its own re-run. Otherwise
    the field's mere existence would re-ingest the whole corpus and cascade away every
    embedding it has — 1263 paid provider calls for the real one."""
    ingest_source("rust-ref", conn=db_conn, config=CONFIG, snapshots=prepared,
                  locator_kinds=["web-fragment"])
    second = ingest_source("rust-ref", conn=db_conn, config=CONFIG, snapshots=prepared,
                           locator_kinds=["web-fragment"])
    assert second.skipped is True
    assert prepared.get("rust-ref").min_chars is None


def test_reingest_all_regenerates_every_stored_source(db_conn, prepared, snapshot_root,
                                                      tmp_path):
    """D1 as one runnable operation. Each source keeps its own stored locator kinds, so
    the sweep cannot homogenize them onto whatever the last flag happened to be."""
    other = tmp_path / "other.html"
    other.write_text(GOOD_HTML.replace("Expressions", "Statements"))
    prepared.put("other-ref", other, media_type="text/html",
                 locator_kinds=["named-section"])
    ingest_source("rust-ref", conn=db_conn, config=CONFIG, snapshots=prepared,
                  locator_kinds=["web-fragment"])
    ingest_source("other-ref", conn=db_conn, config=CONFIG, snapshots=prepared)
    expected = {source: [c.locator for c in SourceChunksStore(db_conn).by_source(source)]
                for source in ("rust-ref", "other-ref")}

    _drop_the_database(db_conn)
    results = reingest_all(conn=db_conn, config=CONFIG, snapshots=prepared)

    assert sorted(results) == ["other-ref", "rust-ref"]
    assert all(result.promoted for result in results.values())
    assert {source: [c.locator for c in SourceChunksStore(db_conn).by_source(source)]
            for source in ("rust-ref", "other-ref")} == expected


def test_reingest_all_reports_a_failure_without_abandoning_the_rest(db_conn, prepared,
                                                                    tmp_path):
    """A corpus-wide regeneration must not stop at the first bad source: the rest of a
    known-good corpus would silently stay unregenerated."""
    bad = tmp_path / "bad.html"
    bad.write_text(TINY_HTML)
    prepared.put("bad", bad, media_type="text/html", locator_kinds=["web-fragment"])
    prepared.set_locator_kinds("rust-ref", ["web-fragment"])

    results = reingest_all(conn=db_conn, config=CONFIG, snapshots=prepared)

    assert isinstance(results["bad"], QaHardGate)
    assert results["rust-ref"].promoted is True


def test_an_unchanged_source_is_not_re_ingested_or_re_embedded(db_conn, prepared,
                                                               fake_ctx):
    """`replace_source` is a delete-then-reinsert and the embedding tables cascade off
    `source_chunks`, so a re-ingest of an unchanged source used to throw away every
    embedding it had — 1263 paid, rate-limited provider calls for the real corpus — to
    arrive back at byte-identical rows."""
    first = ingest_source("rust-ref", conn=db_conn, config=CONFIG, snapshots=prepared,
                          locator_kinds=["web-fragment"])
    assert embed_source(fake_ctx, db_conn, config=CONFIG) == first.chunk_count
    with db_conn.cursor() as cur:
        cur.execute("SELECT max(ingested_at) FROM source_chunks")
        written_at = cur.fetchone()[0]
    fake_ctx.embed_calls.clear()

    second = ingest_source("rust-ref", conn=db_conn, config=CONFIG, snapshots=prepared,
                           locator_kinds=["web-fragment"])

    assert second.skipped is True
    assert second.chunk_count == first.chunk_count and second.promoted
    with db_conn.cursor() as cur:
        cur.execute("SELECT max(ingested_at) FROM source_chunks")
        assert cur.fetchone()[0] == written_at, "the chunk rows were rewritten"
    # the embeddings survived, so a follow-up embed run has nothing to do
    assert embed_source(fake_ctx, db_conn, config=CONFIG) == 0
    assert fake_ctx.embed_calls == []


def test_a_changed_original_still_re_runs_the_whole_pipeline(db_conn, prepared, fake_ctx,
                                                             tmp_path):
    """The short-circuit is keyed on the snapshot's content hash: a source whose file
    genuinely changed must re-extract, re-chunk, re-QA and re-embed."""
    ingest_source("rust-ref", conn=db_conn, config=CONFIG, snapshots=prepared,
                  locator_kinds=["web-fragment"])
    embed_source(fake_ctx, db_conn, config=CONFIG)
    fake_ctx.embed_calls.clear()

    revised = tmp_path / "revised.html"
    revised.write_text(GOOD_HTML.replace("scrutinee", "subject value"))
    prepared.put("rust-ref", revised, media_type="text/html")

    result = ingest_source("rust-ref", conn=db_conn, config=CONFIG, snapshots=prepared,
                           locator_kinds=["web-fragment"])

    assert result.skipped is False
    assert "subject value" in SourceChunksStore(db_conn).by_source("rust-ref")[0].text
    assert embed_source(fake_ctx, db_conn, config=CONFIG) == result.chunk_count
    assert fake_ctx.embed_calls, "changed chunks must reach the embedding provider"


def test_a_changed_chunking_config_re_chunks_instead_of_skipping(db_conn, prepared,
                                                                 fake_ctx):
    """The knobs in `config/ingest.yaml` decide every chunk boundary, but nothing in the
    recorded run used to mention them: tuning chunk size and re-running a source silently
    kept the old chunks, with no error and no warning, and the only recovery was deleting
    the `source_ingestions` row by hand."""
    ingest_source("rust-ref", conn=db_conn, config=CONFIG, snapshots=prepared,
                  locator_kinds=["web-fragment"])
    embed_source(fake_ctx, db_conn, config=CONFIG)
    fake_ctx.embed_calls.clear()
    before = SourceChunksStore(db_conn).by_source("rust-ref")

    wider = IngestConfig.load(overrides={"chunk_target_tokens": 120,
                                         "chunk_max_tokens": 160,
                                         "chunk_overlap_tokens": 8})
    second = ingest_source("rust-ref", conn=db_conn, config=wider, snapshots=prepared,
                           locator_kinds=["web-fragment"])

    assert second.skipped is False
    after = SourceChunksStore(db_conn).by_source("rust-ref")
    # The new sizing is actually in the rows, not just a re-run that reproduced them.
    assert len(after) < len(before)
    assert max(c.token_count for c in after) > max(c.token_count for c in before)
    assert embed_source(fake_ctx, db_conn, config=wider) == second.chunk_count
    assert fake_ctx.embed_calls, "re-chunked chunks must reach the embedding provider"


def test_an_ingestion_recorded_before_the_fingerprint_existed_is_not_skipped(db_conn,
                                                                             prepared):
    """A `source_ingestions` row written before 0004 has no chunking fingerprint, and the
    absence has to read as "unknown, therefore not current" — never as "matches by
    default". Otherwise the real corpus's next re-ingest is skipped forever on a row that
    cannot prove what produced it."""
    first = ingest_source("rust-ref", conn=db_conn, config=CONFIG, snapshots=prepared,
                          locator_kinds=["web-fragment"])
    # Exactly what the 0004 default leaves on a pre-migration row: everything else about
    # the run still matches this config, so only the missing fingerprint can force a re-run.
    with db_conn.cursor() as cur:
        cur.execute("UPDATE source_ingestions SET chunking = '{}'::jsonb"
                    " WHERE source_id = 'rust-ref'")

    second = ingest_source("rust-ref", conn=db_conn, config=CONFIG, snapshots=prepared,
                           locator_kinds=["web-fragment"])

    assert second.skipped is False
    assert second.chunk_count == first.chunk_count
    # ...and the re-run records the fingerprint, so the run after it skips normally again.
    third = ingest_source("rust-ref", conn=db_conn, config=CONFIG, snapshots=prepared,
                          locator_kinds=["web-fragment"])
    assert third.skipped is True


def test_a_source_whose_chunks_vanished_is_re_ingested_not_skipped(db_conn, prepared):
    """The short-circuit trusts `source_ingestions`, so it must also check that the rows
    it points at still exist: a source dropped out of `source_chunks` (a targeted delete,
    a partially restored database) would otherwise be skipped forever on a stale
    `promoted = true` and stay silently missing from the corpus."""
    first = ingest_source("rust-ref", conn=db_conn, config=CONFIG, snapshots=prepared,
                          locator_kinds=["web-fragment"])
    SourceChunksStore(db_conn).delete_source("rust-ref")

    second = ingest_source("rust-ref", conn=db_conn, config=CONFIG, snapshots=prepared,
                           locator_kinds=["web-fragment"])

    assert second.skipped is False
    assert len(SourceChunksStore(db_conn).by_source("rust-ref")) == first.chunk_count
