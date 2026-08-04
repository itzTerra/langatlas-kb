import hashlib
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from ruamel.yaml import YAML
from langatlas_pipeline.paths import PROMPTS_DIR

_yaml = YAML(typ="safe")
_ROLE_HEADING = re.compile(r"(?m)^#\s+(system|user|assistant)\s*$")
_VARIABLE = re.compile(r"\{\{(\w+)\}\}")
_CHANGELOG_LINE = re.compile(r"^- (v\d+) — (v-[0-9a-f]{8}) — ")


def _split_by_role_headings(body: str) -> list[str]:
    """Split body by role headings (# system/user/assistant), ignoring those in code fences.

    Returns list like re.split() with capturing groups: [preamble, role, content, role, content, ...]
    Code fences (``` ... ```) protect their contents from role-heading recognition.
    """
    parts = []
    current_chunk = ""
    in_fence = False

    for line in body.split("\n"):
        # Check if this line toggles the fence state
        if line.startswith("```"):
            in_fence = not in_fence
            current_chunk += line + "\n"
        # Check if this is a role heading and we're not in a fence
        elif not in_fence:
            match = _ROLE_HEADING.match(line)
            if match:
                # Save current chunk and the matched role
                parts.append(current_chunk)
                parts.append(match.group(1))
                current_chunk = ""
            else:
                current_chunk += line + "\n"
        else:
            # Inside fence: just accumulate
            current_chunk += line + "\n"

    # Add final chunk
    parts.append(current_chunk)

    return parts


def version_hash(text: str) -> str:
    """D41: content-addressed versions, mirroring D16/D23's immutable-id pattern."""
    return "v-" + hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]


@dataclass(frozen=True)
class PromptRef:
    """The only prompt-registry touchpoint the provider layer knows (D26). The wrapper
    never loads prompt files itself — it records `prompt_id@version` in cache keys,
    cost-log rows, and run manifests."""

    prompt_id: str
    version: str
    path: Path
    text: str

    def ref(self) -> str:
        return f"{self.prompt_id}@{self.version}"

    def _front_matter_and_body(self) -> tuple[dict, str]:
        if not self.text.startswith("---\n"):
            return {}, self.text
        _, front, body = self.text.split("---\n", 2)
        return _yaml.load(front) or {}, body

    def render(self, **variables: str) -> list[dict[str, str]]:
        """Split on `# system` / `# user` / `# assistant` headings and substitute
        {{variables}}. Strict in both directions: a missing variable and an unexpected
        one are both errors, because a silently unsubstituted prompt is a silently
        wrong run. Role headings inside code fences are not recognized as splits."""
        front, body = self._front_matter_and_body()
        declared = set(front.get("variables") or [])
        supplied = set(variables)
        if declared - supplied:
            raise KeyError(f"{self.ref()}: missing variables {sorted(declared - supplied)}")
        if supplied - declared:
            raise KeyError(f"{self.ref()}: undeclared variables {sorted(supplied - declared)}")

        messages: list[dict[str, str]] = []
        parts = _split_by_role_headings(body)
        for role, chunk in zip(parts[1::2], parts[2::2]):
            content = _VARIABLE.sub(lambda m: variables[m.group(1)], chunk).strip()
            messages.append({"role": role, "content": content})
        if not messages:
            raise ValueError(f"{self.ref()}: no role headings found")
        return messages


def _prompt_dir(prompt_id: str, root: Path | None) -> Path:
    return (root or PROMPTS_DIR) / prompt_id


def _changelog_entries(prompt_id: str, root: Path | None) -> list[tuple[str, str]]:
    """[(alias, version)] newest first."""
    changelog = _prompt_dir(prompt_id, root) / "CHANGELOG.md"
    if not changelog.exists():
        return []
    entries = [(m.group(1), m.group(2))
               for line in changelog.read_text().splitlines()
               if (m := _CHANGELOG_LINE.match(line))]
    return sorted(entries, key=lambda e: int(e[0][1:]), reverse=True)


def list_versions(prompt_id: str, *, root: Path | None = None) -> list[str]:
    return [version for _, version in reversed(_changelog_entries(prompt_id, root))]


def load_prompt(prompt_id: str, version: str = "latest", *,
                root: Path | None = None) -> PromptRef:
    entries = _changelog_entries(prompt_id, root)
    if version == "latest":
        if not entries:
            raise FileNotFoundError(f"{prompt_id}: no versions registered")
        resolved = entries[0][1]
    elif version.startswith("v-"):
        resolved = version
    else:
        matches = [v for alias, v in entries if alias == version]
        if not matches:
            raise FileNotFoundError(f"{prompt_id}: unknown alias {version!r}")
        resolved = matches[0]
    path = _prompt_dir(prompt_id, root) / f"{resolved}.md"
    return PromptRef(prompt_id, resolved, path, path.read_text(encoding="utf-8"))


def mint_prompt_version(prompt_id: str, text: str, *, note: str = "",
                        root: Path | None = None) -> PromptRef:
    """Write a new content-addressed version and append its alias to the CHANGELOG.
    Re-minting identical text is a no-op — the hash already identifies it."""
    directory = _prompt_dir(prompt_id, root)
    directory.mkdir(parents=True, exist_ok=True)
    version = version_hash(text)
    path = directory / f"{version}.md"
    entries = _changelog_entries(prompt_id, root)
    if version not in {v for _, v in entries}:
        path.write_text(text, encoding="utf-8")
        alias = f"v{len(entries) + 1}"
        changelog = directory / "CHANGELOG.md"
        header = "" if changelog.exists() else f"# {prompt_id} — prompt versions\n\n"
        with changelog.open("a", encoding="utf-8") as fh:
            fh.write(f"{header}- {alias} — {version} — {date.today().isoformat()}"
                     f"{' — ' + note if note else ''}\n")
    return PromptRef(prompt_id, version, path, path.read_text(encoding="utf-8"))
