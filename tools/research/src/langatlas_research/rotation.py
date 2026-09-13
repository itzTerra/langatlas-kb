"""R5's rotating sample (D27: 4-5 languages per cycle, not the full set every cycle).

The order is family-interleaved rather than alphabetical or TIOBE-ranked, because the
property R5 needs is *paradigm spread inside one cycle* -- a cycle that checks five
curly-brace imperative languages cannot surface an unfittable language or an uninhabited
dimension value, which is the whole point of the exercise (§7.4)."""

PARADIGM_FAMILIES = {
    "c": "systems", "cpp": "systems", "rust": "systems", "go": "systems",
    "java": "oop-managed", "csharp": "oop-managed", "swift": "oop-managed",
    "python": "scripting", "javascript": "scripting", "r": "scripting",
    "haskell": "functional", "ocaml": "functional",
    "erlang": "actor", "elixir": "actor",
    "prolog": "logic",
}

# Round-robin across families, so consecutive windows are spread by construction.
SPREAD_ORDER = (
    "c", "java", "python", "haskell", "erlang",
    "prolog", "cpp", "csharp", "javascript", "ocaml",
    "elixir", "rust", "swift", "r", "go",
)


def plan_languages(cycle_number: int, *, size: int = 5) -> tuple[str, ...]:
    """@param cycle_number: 1-based cycle number.
    @param size: sample width; D27 ratified 4-5.
    @returns: the cycle's language sample, deterministic for a given (number, size).
    @raises ValueError: for a non-positive cycle number or an out-of-range size."""
    if cycle_number < 1:
        raise ValueError(f"cycle numbers are 1-based: {cycle_number}")
    if not 1 <= size <= len(SPREAD_ORDER):
        raise ValueError(f"sample size out of range: {size}")
    start = ((cycle_number - 1) * size) % len(SPREAD_ORDER)
    return tuple(SPREAD_ORDER[(start + offset) % len(SPREAD_ORDER)] for offset in range(size))
