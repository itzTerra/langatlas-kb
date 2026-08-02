import io
import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

from ruamel.yaml import YAML

_WS = re.compile(r"\s+")
_TERMINAL_PUNCT = ".!?;:,"


def normalize_value(value: str, *, freetext: bool = False) -> str:
    s = unicodedata.normalize("NFC", value)
    s = _WS.sub(" ", s).strip()
    if freetext:
        s = s.lower().rstrip(_TERMINAL_PUNCT)
    return s


_SCHEMA_DIR = Path(__file__).resolve().parents[4] / "ontology" / "schema"


@lru_cache(maxsize=None)
def _key_order(kind: str) -> tuple[str, ...]:
    schema = json.loads((_SCHEMA_DIR / f"{kind}.schema.json").read_text())
    return tuple(schema.get("properties", {}).keys())


def _reorder(data, order: tuple[str, ...]):
    if not isinstance(data, dict):
        return data
    ordered = {k: data[k] for k in order if k in data}
    for k in data:                       # any field not in schema keeps a stable tail slot
        if k not in ordered:
            ordered[k] = data[k]
    for k, v in ordered.items():
        if k in ("characteristics", "notes", "syntax") and isinstance(v, list):
            ordered[k] = sorted(v, key=lambda item: item.get("key", ""))
    return ordered


def normalize_record(text: str, kind: str) -> str:
    yaml = YAML()
    yaml.indent(mapping=2, sequence=4, offset=2)
    yaml.width = 100
    yaml.preserve_quotes = False
    data = yaml.load(text)
    data = _reorder(data, _key_order(kind))
    buf = io.StringIO()
    yaml.dump(data, buf)
    return buf.getvalue()
