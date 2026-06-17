"""CLI entry point for the runtime execution loop."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .orchestrator import Orchestrator


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Alchemy Dev Agent Runtime Engine v0.1.")
    parser.add_argument("--objective", required=True, help="User development objective.")
    parser.add_argument("--project", default=".", help="Project directory for runtime state.")
    parser.add_argument("--state-file", default=".alchemy/state.json", help="State file path under project directory.")
    parser.add_argument("--max-iterations", type=int, default=20, help="Maximum loop iterations.")
    parser.add_argument("--reset", action="store_true", help="Reset runtime state before running.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    orchestrator = Orchestrator.for_project(Path(args.project), state_file=args.state_file)
    state = orchestrator.run(args.objective, max_iterations=args.max_iterations, reset=args.reset)
    print(json.dumps(state.to_dict(), indent=2, sort_keys=True))
    return 0 if state.done else 1


if __name__ == "__main__":
    raise SystemExit(main())
