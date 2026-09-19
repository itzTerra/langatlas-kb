import pytest
from langatlas_pipeline.prompts import load_prompt

EXPECT = {
    "r4-ontologist": ("CURRENT WORKING MODEL", "structure-friction"),
    "r4-edge-drafter": ("CURRENT WORKING MODEL", "structure-friction"),
    "r4-challenger": ("wrong-structure",),
    "r4-moderator": ("wrong-structure", "structure_element"),
}


@pytest.mark.parametrize("prompt_id", EXPECT)
def test_the_latest_version_carries_the_provisional_structure_paragraph(prompt_id):
    text = load_prompt(prompt_id).text
    for needle in EXPECT[prompt_id]:
        assert needle in text, f"{prompt_id} does not mention {needle!r}"
    assert text.index(EXPECT[prompt_id][0]) < text.index("# user")
