import pytest
from ruamel.yaml import YAML

from langatlas_research.taxonomy import mint_dimension, mint_quality, register_language

yaml = YAML(typ="safe")


@pytest.fixture
def repo(tmp_path):
    (tmp_path / "ontology" / "taxonomy").mkdir(parents=True)
    (tmp_path / "ontology" / "taxonomy" / "dimensions.yaml").write_text("dimensions: []\n")
    (tmp_path / "ontology" / "taxonomy" / "qualities.yaml").write_text("qualities: []\n")
    (tmp_path / "languages").mkdir()
    (tmp_path / "languages" / "_registry.yaml").write_text("languages: {}\n")
    return tmp_path


def test_a_dimension_carries_the_pre_emptive_defaults(repo):
    minted = mint_dimension("typing-discipline", label="Typing discipline",
                            values=("static", "dynamic", "gradual"), repo_root=repo)

    assert minted.path == "ontology/taxonomy/dimensions.yaml"
    entry = yaml.load(minted.text)["dimensions"][0]
    assert entry["exclusivity"] == "exclusive"
    assert entry["applies_to"] == ["general-purpose"]
    assert entry["values"] == ["static", "dynamic", "gradual"]
    assert minted.base_digest is not None


def test_minting_a_second_dimension_keeps_the_first(repo):
    (repo / "ontology" / "taxonomy" / "dimensions.yaml").write_text(
        mint_dimension("typing-discipline", label="Typing discipline",
                       values=("static",), repo_root=repo).text)

    minted = mint_dimension("memory-reclamation", label="Memory reclamation",
                            values=("manual", "traced-gc"), exclusivity="multi-valued",
                            repo_root=repo)

    slugs = [d["slug"] for d in yaml.load(minted.text)["dimensions"]]
    assert slugs == ["memory-reclamation", "typing-discipline"]


def test_re_minting_an_existing_dimension_is_refused(repo):
    (repo / "ontology" / "taxonomy" / "dimensions.yaml").write_text(
        mint_dimension("typing-discipline", label="Typing discipline",
                       values=("static",), repo_root=repo).text)

    with pytest.raises(ValueError, match="already exists"):
        mint_dimension("typing-discipline", label="Typing discipline",
                       values=("static", "dynamic"), repo_root=repo)


def test_a_quality_lands_in_the_quality_vocabulary(repo):
    minted = mint_quality("learnability", label="Learnability",
                          summary="How quickly a competent programmer becomes productive.",
                          repo_root=repo)

    assert minted.path == "ontology/taxonomy/qualities.yaml"
    assert yaml.load(minted.text)["qualities"][0]["slug"] == "learnability"


def test_registering_a_language_is_the_id_mint_authority(repo):
    minted = register_language("rust", name="Rust", repo_root=repo)

    assert minted.path == "languages/_registry.yaml"
    assert yaml.load(minted.text)["languages"]["rust"]["name"] == "Rust"
    assert minted.node_ids == ("rust",)


def test_an_invalid_slug_is_refused_everywhere(repo):
    with pytest.raises(ValueError, match="invalid slug"):
        mint_quality("Learn Ability", label="x", summary="y", repo_root=repo)
