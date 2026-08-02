from langatlas_validate.normalize import normalize_value


def test_string_nfc_trim_collapse():
    assert normalize_value("  match   is\tan  expression ") == "match is an expression"


def test_non_freetext_preserves_case_and_punctuation():
    assert normalize_value("Rust 1.0.") == "Rust 1.0."


def test_freetext_lowercases_and_strips_terminal_punctuation():
    assert normalize_value("The compiler rejects it.", freetext=True) == \
        "the compiler rejects it"
    assert normalize_value("Is it exhaustive?", freetext=True) == "is it exhaustive"


def test_freetext_only_terminal_punctuation_stripped():
    assert normalize_value("a, b, and c.", freetext=True) == "a, b, and c"


def test_nfc_composition_stable():
    decomposed = "é"      # e + combining acute
    composed = "é"          # é
    assert normalize_value(decomposed) == normalize_value(composed)
