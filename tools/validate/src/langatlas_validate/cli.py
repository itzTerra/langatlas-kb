import argparse
from langatlas_validate import __version__


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="langatlas-validate")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_subparsers(dest="command")
    parser.parse_args(argv)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
