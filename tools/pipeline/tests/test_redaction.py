from langatlas_pipeline.transcripts.redaction import scrub_secrets, truncate_tool_result


def test_scrubs_bearer_tokens_and_api_keys():
    text, kinds = scrub_secrets(
        "call with x-litellm-api-key: Bearer sk-abcdefghijklmnopqrstuvwx and ghp_0123456789abcdefghij"
    )
    assert "sk-abcdefghijklmnopqrstuvwx" not in text
    assert "ghp_0123456789abcdefghij" not in text
    assert "[REDACTED:" in text
    assert set(kinds) >= {"bearer", "github-token"}


def test_leaves_ordinary_prose_alone():
    prose = "Rust has pattern matching since 1.0; see the reference section 6.2."
    text, kinds = scrub_secrets(prose)
    assert text == prose
    assert kinds == []


def test_large_tool_result_is_truncated_to_excerpt_and_hash():
    body = "A" * 5000
    excerpt, ref = truncate_tool_result(body, source_id="src-vanroy-2003")
    assert len(excerpt) < len(body)
    assert ref["truncated"] is True
    assert ref["bytes"] == 5000
    assert len(ref["sha256"]) == 64
    assert ref["source_id"] == "src-vanroy-2003"


def test_small_tool_result_is_kept_verbatim():
    excerpt, ref = truncate_tool_result("short answer", source_id=None)
    assert excerpt == "short answer"
    assert ref["truncated"] is False
