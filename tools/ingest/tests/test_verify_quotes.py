from langatlas_ingest.store import SourceChunk
from langatlas_ingest.verify.quotes import (
    MAX_QUOTE_WORDS, QUOTE_FAIL_RATIO, QUOTE_PASS_RATIO, check_quote,
    find_quote_in_source, normalize_tokens, quote_ratio, quote_within_cap,
    since_token_present,
)

PASSAGE = ("Pattern matching destructures a value against a sequence of patterns, "
           "binding names in the matched arm.")


def chunk(chunk_id, text):
    return SourceChunk(chunk_id=chunk_id, source_id="s", ordinal=1, parent_section_id=None,
                       section_path=[], breadcrumb="", locator="p. 1",
                       locator_kind="book-page", page_start=1, page_end=1,
                       section_number=None, anchor=None, line_start=None, line_end=None,
                       text=text, token_count=20, content_hash="h")


def test_nfkc_normalization_folds_ligatures_and_case():
    # A PDF extractor emits U+FB01 for "fi"; a citation typed by hand does not. Without
    # NFKC the two never match and a true quote reads as a fabrication.
    assert normalize_tokens("ﬁnal Form") == normalize_tokens("final form")


def test_curly_and_straight_quotes_normalize_alike():
    # PDF extractor emits curly right single quotation mark (U+2019); hand-typed is straight (U+0027).
    # Tokenization via \w+ drops both as non-word characters, making both apostrophe variants disappear.
    assert normalize_tokens("don’t") == normalize_tokens("don't")


def test_an_exact_quote_scores_one():
    assert quote_ratio("destructures a value", PASSAGE) == 1.0


def test_a_verbatim_quote_passes():
    got = check_quote("destructures a value against a sequence of patterns", PASSAGE)
    assert got.status == "pass"
    assert got.ratio >= QUOTE_PASS_RATIO


def test_an_unrelated_quote_is_a_mismatch_with_the_annotation():
    got = check_quote("monads are just monoids in the category of endofunctors", PASSAGE)
    assert got.status == "mismatch"
    assert got.ratio <= QUOTE_FAIL_RATIO
    assert got.annotation == "quote-mismatch"


def test_light_ocr_noise_lands_in_the_adjudication_band():
    # rn -> m is the classic OCR confusion; one corrupted token in eight should be
    # neither a clean pass nor a clean fabrication call.
    got = check_quote("destructures a value against a sequenee of patterns", PASSAGE)
    assert got.status == "adjudicate"
    assert QUOTE_FAIL_RATIO < got.ratio < QUOTE_PASS_RATIO


def test_an_empty_quote_never_passes():
    assert check_quote("", PASSAGE).status == "mismatch"


def test_a_quote_found_elsewhere_in_the_source_is_annotated_not_failed():
    chunks = [chunk("s#c00001", "unrelated text"), chunk("s#c00002", PASSAGE)]
    got = find_quote_in_source(chunks, "destructures a value against a sequence",
                               exclude=("s#c00001",))
    assert got.status == "found-elsewhere"
    assert got.annotation == "quote-found-elsewhere"
    assert got.located_chunk_id == "s#c00002"


def test_a_quote_in_no_chunk_stays_a_mismatch():
    chunks = [chunk("s#c00001", "unrelated text")]
    got = find_quote_in_source(chunks, "destructures a value against a sequence")
    assert got.status == "mismatch"
    assert got.located_chunk_id is None


def test_the_excluded_chunk_is_not_reported_as_elsewhere():
    chunks = [chunk("s#c00001", PASSAGE)]
    got = find_quote_in_source(chunks, "destructures a value", exclude=("s#c00001",))
    assert got.status == "mismatch"


def test_since_token_presence_is_a_mechanical_precheck():
    assert since_token_present("3.10", "Added in version 3.10 of the language.") is True
    assert since_token_present("3.10", "Added in version 3.9 of the language.") is False
    # No `since` to check is vacuously present — the precheck must not reject a fact
    # that never claimed an origin version.
    assert since_token_present(None, "anything") is True


def test_the_quote_cap_is_d14s_fifty_words():
    assert quote_within_cap(" ".join(["word"] * MAX_QUOTE_WORDS)) is True
    assert quote_within_cap(" ".join(["word"] * (MAX_QUOTE_WORDS + 1))) is False
    assert quote_within_cap(None) is True
