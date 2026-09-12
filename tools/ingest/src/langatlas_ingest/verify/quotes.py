import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher

# Section 6.2's fast-path thresholds. The band between them is where OCR noise and
# fabrication are genuinely indistinguishable mechanically, so an LLM adjudicates.
QUOTE_PASS_RATIO = 0.90
QUOTE_FAIL_RATIO = 0.80

# D14's verbatim cap.
MAX_QUOTE_WORDS = 50

# Cheap set-overlap gate before the O(n*m) window scan. A whole-source search over a
# 1,200-chunk book would otherwise run the matcher a thousand times per pair.
PREFILTER_OVERLAP = 0.30

_WORD_RE = re.compile(r"\w+")


def normalize_tokens(text: str) -> list[str]:
    r"""NFKC-normalize, casefold, and split into word tokens.

    NFKC folds ligatures (ﬁ → fi). Tokenization via `\w+` drops non-word characters as
    delimiters, including both straight and curly apostrophes (U+0027, U+2019, etc.),
    making an extractor's punctuation variants comparable with a hand-typed citation.

    @param text - text to tokenize (None-safe)
    @returns list of lowercased word tokens, in order
    """
    folded = unicodedata.normalize("NFKC", text or "").casefold()
    return _WORD_RE.findall(folded)


# How much of the gap between the token-level and character-level reads to credit
# toward the character-level score. Calibrated against the 8 ocr-noisy golden items
# (2026-09-12): every one of them needs some credit (their token ratio alone stays
# below QUOTE_FAIL_RATIO), 0.6 lands all 8 inside the adjudication band or above without
# pushing a real fabrication's blended score anywhere near either floor (fabrications
# score low on both reads, so the blend stays low regardless of weight).
_CHAR_BLEND_WEIGHT = 0.6


def quote_ratio(quote: str, text: str) -> float:
    """Best similarity of `quote` against any same-length window of `text`, blending a
    token-level and a character-level read of the same window.

    Token-level alone was the original design — a single garbled word costs one token,
    not a run of characters, keeping a light OCR slip inside the adjudication band
    instead of below the fabrication floor. But token equality gives a corrupted token
    *zero* credit no matter how close it is character-for-character ("prograrnrning" vs
    "programming"), so real OCR noise that hits several words in one short quote can
    still push the token ratio below the floor before the LLM adjudicator ever sees it
    (live calibration evidence, 2026-09-12: this terminal-rejected an entire golden-set
    stratum). Character-level similarity on the same window recovers that credit, but
    unweighted it overshoots — a quote sharing most of its characters with an unrelated
    passage (shared spaces, common short words) can score deceptively high purely at the
    character level, so `_CHAR_BLEND_WEIGHT` credits only part of the gap rather than
    taking the character read outright. A genuine fabrication scores low on both reads,
    so the blend stays low regardless of the weight.

    @param quote - the claimed quote to find
    @param text - the source text to search within
    @returns 0.0..1.0; 0.0 when either side has no tokens
    """
    needle, haystack = normalize_tokens(quote), normalize_tokens(text)
    if not needle or not haystack:
        return 0.0
    width = len(needle)
    needle_chars = " ".join(needle)
    best = 0.0
    for start in range(max(1, len(haystack) - width + 1)):
        window = haystack[start:start + width]
        token_ratio = SequenceMatcher(a=needle, b=window).ratio()
        char_ratio = SequenceMatcher(a=needle_chars, b=" ".join(window)).ratio()
        blended = token_ratio + (char_ratio - token_ratio) * _CHAR_BLEND_WEIGHT
        best = max(best, blended)
        if best >= 1.0:
            break
    return best


@dataclass(frozen=True)
class QuoteCheck:
    status: str                             # pass | adjudicate | mismatch | found-elsewhere
    ratio: float
    annotation: str | None = None
    located_chunk_id: str | None = None


def check_quote(quote: str, evidence_text: str) -> QuoteCheck:
    """Section 6.2's stage-2 fast path at the cited locator.

    @param quote - the claimed quote
    @param evidence_text - the text at the cited locator
    @returns a `QuoteCheck`; `adjudicate` means the caller must ask the LLM whether this
        is OCR noise or a fabrication
    """
    ratio = quote_ratio(quote, evidence_text)
    if ratio >= QUOTE_PASS_RATIO:
        return QuoteCheck("pass", ratio)
    if ratio <= QUOTE_FAIL_RATIO:
        return QuoteCheck("mismatch", ratio, annotation="quote-mismatch")
    return QuoteCheck("adjudicate", ratio)


def _prefilter(needle: set[str], text: str) -> bool:
    tokens = set(normalize_tokens(text))
    return bool(needle) and len(needle & tokens) / len(needle) >= PREFILTER_OVERLAP


def find_quote_in_source(chunks, quote: str, *, exclude=()) -> QuoteCheck:
    """Section 6.2: a miss at the locator searches the whole source.

    A real quote sitting somewhere else is a *locator* error, not a fabrication — it is
    annotated `quote-found-elsewhere` and the locator is auto-correctable.

    @param chunks - every `SourceChunk` of the cited source
    @param exclude - chunk ids already checked at the locator

    @returns `found-elsewhere` with the located chunk, or the original `mismatch`
    """
    excluded = set(exclude)
    needle = set(normalize_tokens(quote))
    best = QuoteCheck("mismatch", 0.0, annotation="quote-mismatch")
    for chunk in chunks:
        if chunk.chunk_id in excluded or not _prefilter(needle, chunk.text):
            continue
        ratio = quote_ratio(quote, chunk.text)
        if ratio >= QUOTE_PASS_RATIO:
            return QuoteCheck("found-elsewhere", ratio,
                              annotation="quote-found-elsewhere",
                              located_chunk_id=chunk.chunk_id)
        if ratio > best.ratio:
            best = QuoteCheck("mismatch", ratio, annotation="quote-mismatch")
    return best


def since_token_present(since: str | None, text: str) -> bool:
    """Section 6.2's mechanical `since` precheck: does the version string appear at all?

    Vacuously true when the fact carries no `since` — the precheck exists to catch a
    version the cited text never mentions, not to demand one where none was claimed.

    @param since - version string to search for (or None)
    @param text - source text to search within
    @returns True if since is None, or if since tokens appear as a contiguous sequence in text
    """
    if not since:
        return True
    needle = normalize_tokens(since)
    haystack = normalize_tokens(text)
    if not needle:
        return True
    return any(haystack[i:i + len(needle)] == needle
               for i in range(max(1, len(haystack) - len(needle) + 1)))


def quote_within_cap(quote: str | None) -> bool:
    """D14: verbatim quotes are capped at 50 words.

    @param quote - the quote text to validate (or None)
    @returns True if quote is None or has at most 50 whitespace-separated words
    """
    return quote is None or len(quote.split()) <= MAX_QUOTE_WORDS
