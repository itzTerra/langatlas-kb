import pytest

from langatlas_research.paths import REPO_ROOT
from langatlas_research.themes import Theme, load_themes, theme_digest


def test_the_committed_seed_list_covers_the_twelve_spec_themes():
    themes = load_themes(REPO_ROOT)

    assert "typing" in themes
    assert "qualities-vocabulary" in themes
    assert len(themes) >= 12


def test_the_digest_is_sixteen_hex_chars_and_stable_across_cosmetic_whitespace():
    a = Theme(slug="typing", label="Typing", summary="Static and dynamic typing.",
              seed_terms=("type system", "type inference"), note="")
    b = Theme(slug="typing", label="Typing", summary="  Static and  dynamic typing. ",
              seed_terms=("type system", "type inference"), note="")

    assert len(theme_digest(a)) == 16
    assert all(c in "0123456789abcdef" for c in theme_digest(a))
    assert theme_digest(a) == theme_digest(b)


def test_the_digest_changes_when_the_scope_changes():
    a = Theme(slug="typing", label="Typing", summary="Static and dynamic typing.",
              seed_terms=("type system",), note="")
    b = Theme(slug="typing", label="Typing", summary="Static typing only.",
              seed_terms=("type system",), note="")

    assert theme_digest(a) != theme_digest(b)


def test_loading_an_invalid_registry_raises(tmp_path):
    from langatlas_research.paths import ensure_layout, themes_path
    ensure_layout(tmp_path)
    themes_path(tmp_path).write_text("themes: [{slug: typing}]\n")

    with pytest.raises(ValueError, match="label"):
        load_themes(tmp_path)
