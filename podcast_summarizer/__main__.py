import argparse
import logging
import sys

from .logging_config import setup_logging


def main() -> int:
    parser = argparse.ArgumentParser(prog="podcast_summarizer")
    sub = parser.add_subparsers(dest="cmd")
    p_ingest = sub.add_parser("ingest", help="fetch + transcribe new episodes, publish to the data branch")
    p_ingest.add_argument("--only", nargs="*", help="podcast keys to process (default: all enabled)")
    sub.add_parser("summarize", help="optional: local LLM summaries for transcripts without one")
    sub.add_parser("status", help="show host role, heartbeat and transcript counts")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    setup_logging(logging.DEBUG if args.verbose else logging.INFO)
    from . import pipeline
    from .config import load_podcasts

    cmd = args.cmd or "ingest"
    if cmd == "ingest":
        pods = load_podcasts()
        if getattr(args, "only", None):
            pods = [p for p in load_podcasts(include_disabled=True) if p.key in args.only]
        result = pipeline.ingest(pods)
        return 1 if result.failures else 0
    if cmd == "summarize":
        print(f"{pipeline.summarize_pending()} summaries written")
        return 0
    if cmd == "status":
        print(pipeline.status())
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
