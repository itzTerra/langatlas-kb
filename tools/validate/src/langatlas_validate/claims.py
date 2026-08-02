import hashlib
import re
from functools import lru_cache
from pathlib import Path
from ruamel.yaml import YAML
from langatlas_validate.normalize import normalize_value

_TEMPLATE_DIR = Path(__file__).resolve().parents[4] / "ontology" / "claim-templates"
_yaml = YAML(typ="safe")

TEMPLATED_KINDS = (
    "instance-exists", "instance-field", "edge-exists",
    "edge-polarity", "rule-exists", "quality-assessment",
)
FREETEXT_KINDS = ("characteristic", "syntax-valid")


def _sha256_16(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def build_claim(kind: str, **params: str) -> str:
    if kind == "instance-exists":
        return f"instance-exists({params['instance_id']}, status={params['status']})"
    if kind == "instance-field":
        value = normalize_value(params["value"])
        return f'instance-field({params["instance_id"]}, {params["field"]}, "{value}")'
    if kind == "edge-exists":
        return f"edge-exists({params['edge_id']})"
    if kind == "edge-polarity":
        return f"edge-polarity({params['edge_id']}, {params['polarity']})"
    if kind == "rule-exists":
        h = _sha256_16(normalize_value(params["message"], freetext=True))
        return f"rule-exists({params['rule_id']}, sha256-16={h})"
    if kind == "quality-assessment":
        return f"quality-assessment({params['edge_id']}, {params['assessment_key']})"
    if kind == "characteristic":
        h = _sha256_16(normalize_value(params["text"], freetext=True))
        return f"characteristic({params['instance_id']}, {params['key']}, sha256-16={h})"
    if kind == "syntax-valid":
        h = _sha256_16(normalize_value(params["code"], freetext=False))
        return f"syntax-valid({params['syntax_id']}, sha256-16={h})"
    raise ValueError(f"unknown claim kind: {kind!r}")


def fact_id(claim: str) -> str:
    return "f-" + hashlib.sha256(claim.encode("utf-8")).hexdigest()[:12]


@lru_cache(maxsize=None)
def load_claim_template(kind: str) -> dict:
    if kind not in TEMPLATED_KINDS:
        raise ValueError(f"no render template for kind: {kind!r}")
    return _yaml.load((_TEMPLATE_DIR / f"{kind}.yaml").read_text())


def render_claim(kind: str, params: dict) -> str:
    return load_claim_template(kind)["render"].format(**params)


_PLACEHOLDER = re.compile(r"\{(\w+)\}")


def validate_claim_template(kind: str) -> list[str]:
    """CI cross-check: the frozen claim_pattern's shape is well-formed."""
    tpl = load_claim_template(kind)
    errors: list[str] = []
    if tpl.get("kind") != kind:
        errors.append(f"{kind}: kind field mismatch")
    if "claim_pattern" not in tpl or not _PLACEHOLDER.search(tpl["claim_pattern"]):
        errors.append(f"{kind}: claim_pattern missing or has no placeholders")
    if "render" not in tpl:
        errors.append(f"{kind}: render block missing")
    return errors
