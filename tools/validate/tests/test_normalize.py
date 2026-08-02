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


from langatlas_validate.normalize import normalize_record


def test_record_key_order_and_indent():
    messy = "status: present\nlanguage: rust\nfeature: pattern-matching\n"
    out = normalize_record(messy, "feature-instance")
    lines = [l for l in out.splitlines() if ":" in l]
    assert lines[0].startswith("feature:")     # schema-declared order
    assert lines[1].startswith("language:")
    assert lines[2].startswith("status:")


def test_normalize_record_is_idempotent():
    messy = "status: present\nlanguage: rust\nfeature: pattern-matching\n"
    once = normalize_record(messy, "feature-instance")
    twice = normalize_record(once, "feature-instance")
    assert once == twice


def test_keyed_list_sorted_by_key():
    src = (
        "feature: pattern-matching\nlanguage: rust\nstatus: present\n"
        "characteristics:\n"
        "  - key: c-zeta\n    text: z\n    sources: []\n"
        "  - key: c-alpha\n    text: a\n    sources: []\n"
    )
    out = normalize_record(src, "feature-instance")
    assert out.index("c-alpha") < out.index("c-zeta")
