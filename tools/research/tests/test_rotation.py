from langatlas_research.rotation import PARADIGM_FAMILIES, SPREAD_ORDER, plan_languages


def test_the_spread_order_is_exactly_the_d28_fifteen():
    assert len(SPREAD_ORDER) == 15
    assert set(SPREAD_ORDER) == set(PARADIGM_FAMILIES)
    assert {"python", "c", "java", "rust", "haskell", "prolog"} <= set(SPREAD_ORDER)


def test_a_plan_is_deterministic():
    assert plan_languages(4) == plan_languages(4)


def test_the_first_three_cycles_cover_all_fifteen_languages_exactly_once():
    drawn = plan_languages(1) + plan_languages(2) + plan_languages(3)

    assert sorted(drawn) == sorted(SPREAD_ORDER)


def test_every_plan_spans_at_least_three_paradigm_families():
    for cycle in range(1, 13):
        plan = plan_languages(cycle)
        families = {PARADIGM_FAMILIES[lang] for lang in plan}
        assert len(plan) == len(set(plan)), plan
        assert len(families) >= 3, (cycle, plan, families)


def test_a_four_language_sample_is_supported():
    plan = plan_languages(2, size=4)

    assert len(plan) == 4
    assert len({PARADIGM_FAMILIES[lang] for lang in plan}) >= 3
