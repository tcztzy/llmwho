"""LLMWho command-line interface."""

from __future__ import annotations

import argparse
import json
from typing import Optional, Sequence

from .storage import NDJSONStore
from .summary import summarize
from .version import __version__


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="llmwho")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)

    summary = commands.add_parser("summary", help="summarize locally stored observations")
    summary.add_argument("--storage", help="NDJSON event path")
    summary.add_argument("--json", action="store_true", help="print machine-readable JSON")

    dashboard = commands.add_parser("dashboard", help="start the local dashboard")
    dashboard.add_argument("--storage")
    dashboard.add_argument("--host", default="127.0.0.1")
    dashboard.add_argument("--port", default=7734, type=int)

    probe = commands.add_parser("probe", help="run an explicit active probe suite")
    probe.add_argument("--base-url", required=True)
    probe.add_argument("--model", required=True)
    probe.add_argument("--api-key-env", default="OPENAI_API_KEY")
    probe.add_argument("--suite", default="smoke")
    probe.add_argument("--storage")

    hook = commands.add_parser("hook", help="observe an agent lifecycle hook")
    hook.add_argument("client", choices=("claude-code", "codex"))
    hook.add_argument("--event")
    hook.add_argument("--storage")
    return parser


def _print_summary(report: dict, as_json: bool) -> None:
    if as_json:
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
        return
    success = report["availability"]["success_rate"]
    success_text = "n/a" if success is None else f"{success * 100:.1f}%"
    latency = report["transport"]["latency_ms"]
    print(f"events: {report['events']}")
    print(f"availability: {success_text}")
    print(f"latency p50/p95/p99 ms: {latency['p50']} / {latency['p95']} / {latency['p99']}")
    print(f"identity: {report['identity']['statuses']}")
    print(f"capability probes: {report['capability']['probe_count']}")


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "summary":
        _print_summary(summarize(NDJSONStore(args.storage).read()), args.json)
        return 0
    if args.command == "dashboard":
        from .dashboard import serve_dashboard

        serve_dashboard(storage_path=args.storage, host=args.host, port=args.port)
        return 0
    if args.command == "probe":
        import os
        from .probe import probe

        report = probe(
            base_url=args.base_url,
            api_key=os.environ.get(args.api_key_env),
            model=args.model,
            suite=args.suite,
            storage_path=args.storage,
        )
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
        return 0 if report["completed"] else 1
    if args.command == "hook":
        from .agent_hooks import run_hook_cli

        return run_hook_cli(
            args.client,
            expected_event=args.event,
            storage_path=args.storage,
        )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
