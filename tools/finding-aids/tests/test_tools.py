from langatlas_finding_aids.tools import SERVER_NAME, TOOL_DESCRIPTION, TOOL_NAMES


def test_tool_names_are_never_in_the_public_set():
    """D8/D60: the public MCP server is fact-serving and read-only. Finding-aid leads are
    raw third-party material with no verification behind them — the exact thing the public
    boundary test exists to keep off it."""
    public = {"search_knowledge", "get_fact", "get_feature", "get_neighbors", "get_source",
              "get_contradiction", "list_contradictions"}
    assert not {name.split("__")[-1] for name in TOOL_NAMES} & public


def test_there_is_exactly_one_tool_and_it_is_namespaced_to_this_server():
    assert TOOL_NAMES == (f"mcp__{SERVER_NAME}__search_finding_aids",)


def test_the_description_restates_the_policy_once_per_session():
    from langatlas_finding_aids.results import NON_CITABLE_CAVEAT

    assert NON_CITABLE_CAVEAT in TOOL_DESCRIPTION
    assert "tier-A/B" in TOOL_DESCRIPTION


def test_the_schema_marks_only_query_required():
    from langatlas_finding_aids.tools import SEARCH_SCHEMA

    assert SEARCH_SCHEMA["required"] == ["query"]
    assert SEARCH_SCHEMA["properties"]["sources"]["items"]["enum"]
    assert SEARCH_SCHEMA["properties"]["limit"]["maximum"] <= 25


def test_one_channel_is_built_per_session_not_per_tool_call(monkeypatch):
    """Regression for the silently-defeated throttle: a session that makes several
    `search_finding_aids` tool calls needs one shared `FindingAidChannel` (and therefore
    one per-source `Throttle`) across the whole session, not a fresh one per call — the
    same bug `build_checklist` had. `sdk_finding_aid_tools` must construct its channel
    once, outside the `_search` closure."""
    import langatlas_finding_aids.tools as tools_module

    built = []
    real_channel = tools_module.FindingAidChannel

    def _spy(ctx, **kwargs):
        instance = real_channel(ctx, **kwargs)
        built.append(instance)
        return instance

    monkeypatch.setattr(tools_module, "FindingAidChannel", _spy)

    class _Ctx:
        pass

    tools_module.sdk_finding_aid_tools(_Ctx(), config=tools_module.FindingAidsConfig.load())

    assert len(built) == 1
