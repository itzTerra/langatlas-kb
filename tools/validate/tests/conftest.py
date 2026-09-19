"""Tiny canonical stores for the Stage 3F tests. Every record is normalized, so
`validate_store` treats them exactly like committed ones; `store_git` puts one under git for the
tests that read history (replay, ledger checks)."""
import subprocess
from pathlib import Path

import pytest

from langatlas_validate.ids import compose_edge_id
from langatlas_validate.normalize import normalize_record

_PROVENANCE = "provenance:\n  claim_origin: source-derived\n"


def _cite(indent: str) -> str:
    return f"{indent}sources:\n{indent}  - source: s\n{indent}    locator: p. 1\n"


class MiniStore:
    def __init__(self, root: Path):
        self.root = root

    def write(self, rel: str, text: str) -> Path:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def feature(self, node_id, *, layer=2, dimension=None, aliases=(), realizes=(), name=None,
                summary=None):
        body = (f"id: {node_id}\nslug: {node_id}\n"
                f"name: {name or node_id.replace('-', ' ').title()}\nlayer: {layer}\n")
        if dimension:
            body += f"dimension: {dimension}\n"
        if aliases:
            body += "aliases:\n" + "".join(f"  - {alias}\n" for alias in aliases)
        if realizes:
            body += "realizes:\n" + "".join(f"  - {concept}\n" for concept in realizes)
        body += (f"summary:\n  text: {summary or node_id + ' is a feature.'}\n" + _cite("  ")
                 + _PROVENANCE)
        return self.write(f"features/{node_id}.yaml", normalize_record(body, "feature"))

    def concept(self, node_id, *, name=None):
        body = (f"id: {node_id}\nslug: {node_id}\n"
                f"name: {name or node_id.replace('-', ' ').title()}\n"
                f"summary:\n  text: {node_id} is a concept.\n" + _cite("  ") + _PROVENANCE)
        return self.write(f"concepts/{node_id}.yaml", normalize_record(body, "concept"))

    def edge(self, edge_type, frm, to, *, polarity=None, statement=None):
        body = (f"id: {compose_edge_id(edge_type, frm, to)}\ntype: {edge_type}\n"
                f"from: {frm}\nto: {to}\n")
        if polarity:
            body += f"polarity: '{polarity}'\n"
        body += (f"statement:\n  text: {statement or f'{frm} {edge_type} {to}.'}\n"
                 + _cite("  ") + _PROVENANCE)
        return self.write(f"edges/{frm}/{edge_type}--{to}.yaml", normalize_record(body, "edge"))

    def quality_edge(self, frm, quality, *, keys=("a-1",)):
        body = (f"id: {compose_edge_id('affects-quality', frm, quality)}\n"
                f"type: affects-quality\nfrom: {frm}\nto: {quality}\nassessments:\n")
        for key in keys:
            body += (f"  - key: {key}\n    assessor:\n      agent: t\n    polarity: improves\n"
                     f"    strength: moderate\n    statement: {frm} helps {quality} ({key}).\n"
                     + _cite("    "))
        body += _PROVENANCE
        return self.write(f"edges/{frm}/affects-quality--{quality}.yaml",
                          normalize_record(body, "affects-quality-edge"))

    def rule(self, slug, when_all, *, effect="requires", then=(), message=None):
        body = (f"id: rule-{slug}\nwhen_all: [{', '.join(sorted(when_all))}]\n"
                f"effect: {effect}\nthen: [{', '.join(then)}]\n"
                f"message: {message or slug + ' holds.'}\n" + _cite("") + _PROVENANCE)
        return self.write(f"rules/rule-{slug}.yaml", normalize_record(body, "rule"))


@pytest.fixture
def mini_store(tmp_path) -> MiniStore:
    store = MiniStore(tmp_path / "store")
    for directory in ("concepts", "features", "edges", "rules", "sources", "languages"):
        (store.root / directory).mkdir(parents=True)
    store.write("ontology/taxonomy/dimensions.yaml",
                "dimensions:\n  - slug: typing-discipline\n    label: Typing discipline\n"
                "    exclusivity: exclusive\n    applies_to: [general-purpose]\n")
    store.write("ontology/taxonomy/qualities.yaml",
                "qualities:\n  - slug: learnability\n    label: Learnability\n    summary: x\n")
    store.write("languages/_registry.yaml", "languages: {}\n")
    store.write("ontology/VERSION", "0.4.0\n")
    store.write("ontology/redirects.yaml", "redirects: {}\n")
    store.write("tombstones.yaml", "tombstones: []\n")
    store.write("contradictions.yaml", "contradictions: []\n")
    return store


def _git(args, cwd):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True)


class GitRepo:
    def __init__(self, root: Path):
        self.root = root

    def commit(self, files: dict | None = None, message: str = "change") -> str:
        """Writes (or, for a None value, deletes) `files`, then commits the whole tree."""
        for rel, text in (files or {}).items():
            path = self.root / rel
            if text is None:
                path.unlink()
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text)
        _git(["add", "-A"], self.root)
        _git(["commit", "-q", "-m", message], self.root)
        return _git(["rev-parse", "HEAD"], self.root).stdout.strip()


def _init(root: Path, hooks: Path) -> GitRepo:
    """`core.hooksPath` points at an empty directory so this machine's global pre-commit hook
    does not reject the throwaway commits."""
    hooks.mkdir(exist_ok=True)
    _git(["init", "-q", "-b", "main"], root)
    for key, value in (("user.email", "bot@example.com"), ("user.name", "bot"),
                       ("commit.gpgsign", "false"), ("core.hooksPath", str(hooks))):
        _git(["config", key, value], root)
    return GitRepo(root)


@pytest.fixture
def git_repo(tmp_path) -> GitRepo:
    root = tmp_path / "repo"
    root.mkdir()
    return _init(root, tmp_path / "no-hooks")


@pytest.fixture
def store_git(mini_store, tmp_path):
    """`mini_store`, committed as the first commit of a fresh repository."""
    repo = _init(mini_store.root, tmp_path / "no-hooks-store")
    repo.commit(message="seed")
    return mini_store, repo
