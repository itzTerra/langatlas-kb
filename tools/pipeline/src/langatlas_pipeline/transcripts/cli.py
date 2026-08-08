import argparse
from pathlib import Path
from langatlas_pipeline.transcripts.import_sessions import find_session_files, import_session
from langatlas_pipeline.transcripts.publish import publish_run


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="langatlas-transcript")
    sub = parser.add_subparsers(dest="command", required=True)

    p_import = sub.add_parser("import", help="normalize a Claude Code session (opt-in)")
    p_import.add_argument("path", type=Path, nargs="?",
                          help="session JSONL; omit to take the most recent one")
    p_import.add_argument("--kind", default="interactive")
    p_import.add_argument("--slug", default=None)
    p_import.add_argument("--publish", action="store_true")

    p_publish = sub.add_parser("publish")
    p_publish.add_argument("run_dir", type=Path)
    p_publish.add_argument("--no-push", action="store_true")

    args = parser.parse_args(argv)
    if args.command == "import":
        path = args.path or (find_session_files() or [None])[-1]
        if path is None:
            print("no Claude Code session files found")
            return 1
        run_dir = import_session(path, kind=args.kind, slug=args.slug)
        print(run_dir)
        if args.publish:
            print(publish_run(run_dir, repo_root=run_dir.parents[2]).status)
        return 0

    result = publish_run(args.run_dir, repo_root=args.run_dir.parents[2],
                         push=not args.no_push)
    print(result.status, result.detail or "")
    return 0 if result.status in ("published", "noop") else 1


if __name__ == "__main__":
    raise SystemExit(main())
