"""CLI entry point for the runtime execution loop."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .orchestrator import Orchestrator


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Alchemy Dev Agent Runtime Engine.")
    parser.add_argument("--objective", required=True, help="User development objective.")
    parser.add_argument("--project", default=".", help="Project directory for runtime state.")
    parser.add_argument("--state-file", default=".alchemy/state.json", help="State file path under project directory.")
    parser.add_argument("--max-iterations", type=int, default=20, help="Maximum loop iterations.")
    parser.add_argument("--reset", action="store_true", help="Reset runtime state before running.")
    parser.add_argument("--real-codex", action="store_true", help="Invoke the real Codex CLI instead of dry-run worker mode.")
    parser.add_argument("--real-github", action="store_true", help="Run real git/gh branch, commit, push, and PR commands.")
    parser.add_argument("--codex-executable", default="codex", help="Codex CLI executable path or command name.")
    parser.add_argument("--max-worker-seconds", type=int, default=1800, help="Timeout for each Codex worker subprocess.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    orchestrator = Orchestrator.for_project(
        Path(args.project),
        state_file=args.state_file,
        real_codex=args.real_codex,
        real_github=args.real_github,
        codex_executable=args.codex_executable,
        max_worker_seconds=args.max_worker_seconds,
    )
    state = orchestrator.run(args.objective, max_iterations=args.max_iterations, reset=args.reset)
    print(json.dumps(state.to_dict(), indent=2, sort_keys=True))
    return 0 if state.done else 1


if __name__ == "__main__":
    raise SystemExit(main())
