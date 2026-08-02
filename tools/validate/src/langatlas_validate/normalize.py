import re
import unicodedata

_WS = re.compile(r"\s+")
_TERMINAL_PUNCT = ".!?;:,"


def normalize_value(value: str, *, freetext: bool = False) -> str:
    s = unicodedata.normalize("NFC", value)
    s = _WS.sub(" ", s).strip()
    if freetext:
        s = s.lower().rstrip(_TERMINAL_PUNCT)
    return s
