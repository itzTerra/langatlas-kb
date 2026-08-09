import re
import statistics
import unicodedata
from dataclasses import asdict, dataclass, field

# UTF-8 read as latin-1 leaves a lead byte (U+00C2/U+00C3) followed by a continuation
# byte in U+0080-U+00BF; U+FFFD is the decoder giving up outright. But the *dominant*
# real-world signature is UTF-8 read as cp1252, not plain latin-1: cp1252 remaps bytes
# 0x80-0x9F (curly quotes, dashes, ellipsis, trademark, etc.) to its own characters
# instead of passing them through as C1 controls, so a UTF-8 en-dash/em-dash/quote
# shows up as U+00E2 (â) followed by one of those cp1252 glyphs, e.g. â for a
# right single quote. Both lead bytes and both continuation ranges are covered here.
# Spelled as escapes: a mojibake detector written in mojibake-prone literals is a trap.
_CP1252_C1 = ("\u20ac\u201a\u0192\u201e\u2026\u2020\u2021\u02c6\u2030\u0160"
             "\u2039\u0152\u017d\u2018\u2019\u201c\u201d\u2022\u2013\u2014"
             "\u02dc\u2122\u0161\u203a\u0153\u017e\u0178")
_MOJIBAKE = re.compile(f"[\u00c2\u00c3\u00e2][\u0080-\u00bf{_CP1252_C1}]|\ufffd")
_MOJIBAKE_RATE = 0.001          # 1 hit per 1000 characters is already pathological
_MIN_CHARS_PER_PAGE = 200       # below this, the extractor found images, not text
_MIN_CHARS = 500
_OCR_TOKEN = re.compile(r"\b\w*(?:[0-9]+[a-z]+|[a-z]+[0-9]+)\w*\b", re.I)
_OCR_RATE = 0.05
_OUTLIER_SIGMA = 4
# Mirrors chunker._NUMBERED_HEADING: a PDF's own bookmark title and its in-body heading
# text come from different code paths (doc.get_toc() vs. the font-size heuristic) and
# routinely disagree on numbering *punctuation* alone -- e.g. a bookmark titled
# "1 Introduction" for a heading rendered "1. Introduction". Only the separator is
# normalized away (the number itself is kept, via the capture group) -- language
# references repeat subsection titles like "Syntax"/"Semantics" under every chapter,
# so discarding the number outright would silently fold distinct sections (3.1 Syntax,
# 4.2 Syntax, ...) into one key and hide a real gap in any of them.
_NUMBER_PREFIX = re.compile(r"^(\d+(?:\.\d+)*)[.)]\s+")


@dataclass
class QaCheck:
    check_id: str
    severity: str            # "hard" -> blocks promotion (D37); "soft" -> report only
    passed: bool
    detail: str = ""
    metric: float | None = None


@dataclass
class QaReport:
    source_id: str
    checks: list[QaCheck] = field(default_factory=list)
    outline_coverage: float | None = None
    missing_sections: list[str] = field(default_factory=list)
    chunk_count: int = 0
    char_count: int = 0

    @property
    def hard_failures(self) -> list[QaCheck]:
        return [c for c in self.checks if c.severity == "hard" and not c.passed]

    @property
    def status(self) -> str:
        if self.hard_failures:
            return "fail"
        return "warn" if any(not c.passed for c in self.checks) else "pass"

    def to_dict(self) -> dict:
        data = asdict(self)
        data["qa_status"] = self.status
        return data

    def to_markdown(self) -> str:
        lines = [f"# Extraction QA -- {self.source_id}", "",
                 f"- status: **{self.status}**",
                 f"- chunks: {self.chunk_count}, characters: {self.char_count}"]
        if self.outline_coverage is not None:
            lines.append(f"- outline coverage: {self.outline_coverage:.0%}")
        lines += ["", "| check | severity | result | detail |", "|---|---|---|---|"]
        for check in self.checks:
            result = "pass" if check.passed else "**FAIL**"
            lines.append(f"| {check.check_id} | {check.severity} | {result} | {check.detail} |")
        if self.missing_sections:
            lines += ["", "## Outline entries with no chunk", ""]
            lines += [f"- {section}" for section in self.missing_sections]
        return "\n".join(lines) + "\n"


def _key(text: str) -> str:
    normalized = re.sub(r"\s+", " ", unicodedata.normalize("NFC", text)).strip().lower()
    return _NUMBER_PREFIX.sub(r"\1 ", normalized)


def run_qa(doc, chunks) -> QaReport:
    """D37's harness. Encoding and extraction-collapse are hard gates; everything else is
    pre-triage for the developer's manual skim — the workflow already exists, this just
    makes it arrive sorted."""
    text = "\n".join(block.text for block in doc.blocks)
    report = QaReport(source_id=doc.source_id, chunk_count=len(chunks), char_count=len(text))

    hits = len(_MOJIBAKE.findall(text))
    rate = hits / max(1, len(text))
    report.checks.append(QaCheck(
        "encoding", "hard", rate <= _MOJIBAKE_RATE,
        f"{hits} mojibake or replacement sequences in {len(text)} chars", rate))

    # Layout whitespace (justified-text padding, table-cell gaps, blank running heads)
    # can pad a near-empty extraction past both thresholds on raw length alone; only
    # non-whitespace characters count as evidence the extractor actually found text.
    content_chars = len(re.sub(r"\s+", "", text))
    per_page = content_chars / doc.page_count if doc.page_count else float(content_chars)
    collapsed = (content_chars < _MIN_CHARS
                 or bool(doc.page_count and per_page < _MIN_CHARS_PER_PAGE))
    report.checks.append(QaCheck(
        "extraction-collapse", "hard", not collapsed,
        f"{content_chars} non-whitespace chars ({len(text)} total) over "
        f"{doc.page_count or 'n/a'} pages", per_page))

    words = re.findall(r"\b\w+\b", text)
    ocr_rate = len(_OCR_TOKEN.findall(text)) / max(1, len(words))
    report.checks.append(QaCheck(
        "ocr-noise", "soft", ocr_rate <= _OCR_RATE,
        f"{ocr_rate:.1%} of words mix digits and letters", ocr_rate))

    lengths = [chunk.token_count for chunk in chunks]
    outliers: list[int] = []
    if len(lengths) > 2:
        mean, deviation = statistics.mean(lengths), statistics.pstdev(lengths)
        if deviation:
            outliers = [n for n in lengths if abs(n - mean) > _OUTLIER_SIGMA * deviation]
    report.checks.append(QaCheck(
        "length-outliers", "soft", not outliers,
        f"{len(outliers)} chunks beyond {_OUTLIER_SIGMA} sigma of the mean length",
        float(len(outliers))))

    # Section 4.4: no machine-readable outline -> silent no-op, not a finding.
    if doc.outline:
        covered = {_key(part) for chunk in chunks for part in chunk.section_path}
        missing = [entry for entry in doc.outline if _key(entry) not in covered]
        report.missing_sections = missing
        report.outline_coverage = (len(doc.outline) - len(missing)) / len(doc.outline)
        report.checks.append(QaCheck(
            "outline-coverage", "soft", not missing,
            f"{len(missing)} of {len(doc.outline)} outline entries have no chunk",
            report.outline_coverage))
    return report
