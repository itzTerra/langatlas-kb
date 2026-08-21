import argparse
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

from langatlas_validate.compile import compile_bundle
from langatlas_validate.paths import REPO_ROOT


def data_vn_tag_for_today(*, today: date | None = None) -> str:
    """D13 ratified cadence: daily, only on days with changes. The tag name itself is
    just the date stamp; "only on days with changes" is enforced by the workflow step
    that skips tagging when this tag already exists (git tags are immutable)."""
    day = today or datetime.now(timezone.utc).date()
    return f"data-v{day.isoformat().replace('-', '.')}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="langatlas-publish")
    parser.add_argument("--out", required=True, help="path to write the compiled bundle JSON")
    args = parser.parse_args(argv)

    bundle = compile_bundle(REPO_ROOT)
    Path(args.out).write_text(json.dumps(bundle, indent=2, sort_keys=True))
    print(f"wrote {args.out} ({len(bundle['facts'])} facts, schema_version={bundle['schema_version']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
