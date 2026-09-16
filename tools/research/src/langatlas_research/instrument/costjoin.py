"""D30(b): Claude messages per accepted node, segmented by `debate_id` (§7.13).

Pure log reading. The cost log has carried one row per provider call since Stage 1B, every row
stamped with its `run_id`; a debate record names the run ids it used; the carve plan says which
carves a debate touched and whether they landed. Joining those three answers "what did debating
this actually cost, and what did it buy" without storing anything new.

Only `endpoint: claude` rows count. The university-API calls a debate's roles may trigger
underneath (a verification, a rerank) are not what D6's budget question is about — Claude
sessions are the scarce resource, and mixing the two would make a debate look expensive because
something cheap ran a lot."""
from dataclasses import dataclass
from pathlib import Path

from langatlas_pipeline.costlog import read_cost_rows
from langatlas_pipeline.paths import PRIVATE_DIR
from langatlas_research.draft.debate_record import iter_debates
from langatlas_research.draft.plan import entries, load_plan


@dataclass(frozen=True)
class DebateCost:
    debate_id: str
    claude_messages: int
    tokens: int
    accepted_nodes: int

    @property
    def messages_per_accepted(self) -> float | None:
        """None, not zero and not infinity: a debate that accepted nothing has no
        cost-per-accepted-node, and printing one would invent a number."""
        if not self.accepted_nodes:
            return None
        return round(self.claude_messages / self.accepted_nodes, 2)


def cost_join(repo_root: Path, *, cycle: int | None = None,
              cost_log: Path | None = None) -> list[DebateCost]:
    """@param cost_log: overrides the private cost log (tests pin it).
    @returns: one row per debate, id order; empty when there is no cost log yet."""
    rows = read_cost_rows(Path(cost_log) if cost_log else PRIVATE_DIR / "cost-log.jsonl")
    if not rows:
        return []
    claude = [row for row in rows if row.endpoint == "claude"]

    plans: dict[str, dict] = {}
    joined = []
    for debate in iter_debates(repo_root):
        if cycle is not None and debate["cycle"] != cycle:
            continue
        run_ids = {run_id for run_id in debate["runs"].values() if run_id}
        debate_rows = [row for row in claude if row.run_id in run_ids]

        slug = f"{debate['cycle']:02d}-{debate['theme']}"
        try:
            plan = plans.setdefault(slug, load_plan(slug, repo_root=repo_root))
        except Exception:
            plan = {}
        accepted = sum(1 for _name, entry in entries(plan)
                       if entry.get("debate_id") == debate["id"]
                       and entry["status"] == "minted")

        joined.append(DebateCost(
            debate_id=debate["id"], claude_messages=len(debate_rows),
            tokens=sum(row.tokens_in + row.tokens_out for row in debate_rows),
            accepted_nodes=accepted))
    return joined


def render_cost(rows: list[DebateCost]) -> str:
    lines = ["# D30(b) cost join — Claude messages per accepted node", "",
             "| debate | claude messages | tokens | accepted nodes | messages/node |",
             "|---|---|---|---|---|"]
    for row in rows:
        per = "—" if row.messages_per_accepted is None else f"{row.messages_per_accepted}"
        lines.append(f"| {row.debate_id} | {row.claude_messages} | {row.tokens} |"
                     f" {row.accepted_nodes} | {per} |")
    total_messages = sum(row.claude_messages for row in rows)
    total_accepted = sum(row.accepted_nodes for row in rows)
    overall = f"{round(total_messages / total_accepted, 2)}" if total_accepted else "—"
    lines.append(f"| **total** | {total_messages} |"
                 f" {sum(row.tokens for row in rows)} | {total_accepted} | {overall} |")
    return "\n".join(lines) + "\n"
