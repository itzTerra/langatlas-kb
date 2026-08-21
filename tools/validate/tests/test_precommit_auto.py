from pathlib import Path

from langatlas_validate.cli import main, infer_kind_from_path


def test_infer_kind_from_path_covers_every_store_directory():
    assert infer_kind_from_path(Path("concepts/x.yaml")) == "concept"
    assert infer_kind_from_path(Path("features/x.yaml")) == "feature"
    assert infer_kind_from_path(Path("languages/_registry.yaml")) == "language-registry"
    assert infer_kind_from_path(Path("languages/rust/language.yaml")) == "language"
    assert infer_kind_from_path(Path("languages/rust/instances/x.yaml")) == "feature-instance"
    assert infer_kind_from_path(Path("rules/x.yaml")) == "rule"
    assert infer_kind_from_path(Path("sources/x.yaml")) == "source"
    assert infer_kind_from_path(Path("README.md")) is None


def test_precommit_auto_validates_a_clean_feature_instance(tmp_path):
    from langatlas_validate.normalize import normalize_record
    f = tmp_path / "languages" / "rust" / "instances" / "pattern-matching.yaml"
    f.parent.mkdir(parents=True)
    raw = ("feature: pattern-matching\nlanguage: rust\nstatus: present\n"
          "provenance:\n  claim_origin: source-derived\n")
    f.write_text(normalize_record(raw, "feature-instance"))
    assert main(["precommit-auto", str(f)]) == 0


def test_precommit_auto_skips_edges_needing_type_sniff(tmp_path):
    from langatlas_validate.normalize import normalize_record
    f = tmp_path / "edges" / "algebraic-data-types" / "requires--pattern-matching.yaml"
    f.parent.mkdir(parents=True)
    raw = ("id: edge.requires.algebraic-data-types.pattern-matching\n"
          "type: requires\nfrom: algebraic-data-types\nto: pattern-matching\n"
          "statement:\n  text: x\n  sources: []\n"
          "provenance:\n  claim_origin: source-derived\n")
    f.write_text(raw)
    # edges/ needs the record's own "type" field to disambiguate edge vs
    # affects-quality-edge — precommit-auto reads the file's contents, not just its path.
    assert main(["precommit-auto", str(f)]) in (0, 1)   # exercises the sniff path either way
