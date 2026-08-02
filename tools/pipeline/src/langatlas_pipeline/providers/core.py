from dataclasses import dataclass


@dataclass
class Budget:
    """Per-run caps declared in the run manifest (D26/D43). None == uncapped."""

    max_calls: int | None = None
    max_total_tokens: int | None = None
    max_wall_seconds: int | None = None
    max_claude_messages: int | None = None

    def as_dict(self) -> dict[str, int | None]:
        return {
            "max_calls": self.max_calls,
            "max_total_tokens": self.max_total_tokens,
            "max_wall_seconds": self.max_wall_seconds,
            "max_claude_messages": self.max_claude_messages,
        }
