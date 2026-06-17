"""CLI for the local autonomous development demo pipeline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .pipeline import AutoDevPipeline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a local one-line autonomous app generation demo.")
    parser.add_argument("--objective", required=True)
    parser.add_argument("--output", default=".alchemy/generated/demo")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = AutoDevPipeline().run(args.objective, Path(args.output))
    print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    return 0 if result.status == "done" else 1


if __name__ == "__main__":
    raise SystemExit(main())
