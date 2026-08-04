import argparse
from pathlib import Path
from langatlas_pipeline.prompts import list_versions, load_prompt, mint_prompt_version


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="langatlas-prompts")
    sub = parser.add_subparsers(dest="command", required=True)

    p_mint = sub.add_parser("mint", help="register a new content-addressed version")
    p_mint.add_argument("prompt_id")
    p_mint.add_argument("file", type=Path)
    p_mint.add_argument("--note", default="")

    p_list = sub.add_parser("list")
    p_list.add_argument("prompt_id")

    p_show = sub.add_parser("show")
    p_show.add_argument("prompt_id")
    p_show.add_argument("version", nargs="?", default="latest")

    args = parser.parse_args(argv)
    if args.command == "mint":
        ref = mint_prompt_version(args.prompt_id, args.file.read_text(), note=args.note)
        print(ref.ref())
        return 0
    if args.command == "list":
        for version in list_versions(args.prompt_id):
            print(version)
        return 0
    print(load_prompt(args.prompt_id, args.version).text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
