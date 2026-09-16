"""The debate record: what a debate was about, who said what, and what was decided.

This file is 3C's hand-off to 3D. The controversy assessor reads debates as *structured inputs*
in exactly the `{id, outcome, standing_dissent, rounds}` shape 2B's committed bootstrap cases
already use, and it emits signals of the form `debate:<id>:<outcome>` — so the outcome
vocabulary here is a fixed contract with a committed golden set, not a local choice.

The moderator never types an outcome. It types a **disposition** — what should happen to the
carve — and `resolution_outcome` maps it. A model that could type the outcome directly could
drift the vocabulary 3D scores against; a model that types a disposition cannot."""
import io
import re
from pathlib import Path
from typing import Iterator

from ruamel.yaml import YAML

from langatlas_research.errors import DebateIncomplete
from langatlas_research.paths import debates_dir
from langatlas_research.schema import validate_research_record

CHALLENGE_TYPES = ("wrong-atomization", "wrong-layer", "missing-source", "redundant-with",
                   "scope")
DISPOSITIONS = ("keep", "revise", "split", "merge", "drop", "escalate")
# Fixed by tests/golden/controversy/cases-bootstrap.yaml — see the module docstring.
DEBATE_OUTCOMES = ("resolved", "converged-after-revision", "escalated")

_OUTCOME_OF = {"keep": "resolved", "revise": "converged-after-revision",
               "split": "converged-after-revision", "merge": "converged-after-revision",
               "drop": "converged-after-revision", "escalate": "escalated"}

_ID_RE = re.compile(r"^d-(\d{2})-([a-z][a-z0-9-]*)-(\d{3})$")

_yaml = YAML(typ="safe")


def resolution_outcome(disposition: str) -> str:
    """@raises ValueError: unknown disposition."""
    if disposition not in _OUTCOME_OF:
        raise ValueError(f"unknown debate disposition: {disposition!r}")
    return _OUTCOME_OF[disposition]


def rounds(debate: dict) -> int:
    """How many messages actually raised a challenge. Not the message count: a challenger
    that reads the draft and has nothing to object to did not add a round, and counting it
    as one would make every debate look equally hard to 3D."""
    return sum(1 for message in debate["messages"] if message.get("challenges"))


def debate_path(debate_id: str, *, repo_root: Path | None = None) -> Path:
    return debates_dir(repo_root) / f"{debate_id}.yaml"


def next_debate_id(cycle_slug: str, *, repo_root: Path | None = None) -> str:
    """`d-<NN>-<theme>-<NNN>`, one sequence per cycle. Readable and sortable; nothing reads a
    debate id as structured data, so it is not content-keyed."""
    prefix = f"d-{cycle_slug}-"
    used = [int(match.group(3))
            for path in debates_dir(repo_root).glob(f"{prefix}*.yaml")
            if (match := _ID_RE.match(path.stem))]
    return f"{prefix}{max(used, default=0) + 1:03d}"


def render_debate(data: dict) -> str:
    yaml = YAML()
    yaml.indent(mapping=2, sequence=4, offset=2)
    yaml.width = 100
    buf = io.StringIO()
    yaml.dump(data, buf)
    return buf.getvalue()


def save_debate(data: dict, *, repo_root: Path | None = None) -> Path:
    """@raises DebateIncomplete: when the record does not satisfy debate.schema.json."""
    errors = validate_research_record(data, "debate", repo_root=repo_root)
    if errors:
        raise DebateIncomplete(f"debate {data.get('id')} is invalid: " + "; ".join(errors))
    path = debate_path(data["id"], repo_root=repo_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_debate(data))
    return path


def load_debate(debate_id: str, *, repo_root: Path | None = None) -> dict:
    """@raises FileNotFoundError: no such debate record."""
    return _yaml.load(debate_path(debate_id, repo_root=repo_root).read_text())


def iter_debates(repo_root: Path | None = None) -> Iterator[dict]:
    """Every committed debate record, id order. The D30 scripts and 3D's assessor both walk
    this rather than guessing at filenames."""
    for path in sorted(debates_dir(repo_root).glob("d-*.yaml")):
        yield _yaml.load(path.read_text())


def as_controversy_input(debate: dict) -> dict:
    """The projection 3D's assessor consumes — and nothing else. A debate record carries
    personas, free text and evidence; none of that is a structured input under §6.4, so none
    of it crosses this boundary."""
    resolution = debate["resolution"]
    return {"id": debate["id"], "outcome": resolution["outcome"],
            "standing_dissent": bool(resolution["standing_dissent"]),
            "rounds": int(resolution["rounds"])}


def debate_signals(debate: dict) -> list[str]:
    """§6.4's machine references. Standing dissent outranks the outcome: a debate that
    "resolved" over a live objection is the more informative fact about it."""
    resolution = debate["resolution"]
    if resolution["standing_dissent"]:
        return [f"debate:{debate['id']}:standing-dissent"]
    return [f"debate:{debate['id']}:{resolution['outcome']}"]


def load_debate_goldens(path: Path | None = None) -> list[dict]:
    """The committed R4 debate golden set (`tests/golden/debates/cases-r4.yaml`).

    @returns: the `cases` list; empty when the file is absent, which is a normal repo state
        before 3C lands."""
    from langatlas_research.paths import REPO_ROOT

    path = Path(path) if path else REPO_ROOT / "tests" / "golden" / "debates" / "cases-r4.yaml"
    if not path.exists():
        return []
    return (_yaml.load(path.read_text()) or {}).get("cases") or []
