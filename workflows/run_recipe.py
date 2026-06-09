#!/usr/bin/env python3
"""
User-facing recipe runner for common SRA paper curator workflows.

This is a thin wrapper around workflows/run_workflow_step.py. It keeps the
public quick start readable without duplicating workflow execution logic.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - dependency is optional for dry-run use
    load_dotenv = None


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_RUNNER = ROOT / "workflows/run_workflow_step.py"
OUTPUT_RUNNER = ROOT / "scripts/90_show_curator_outputs.py"
CHECK_RUNNER = ROOT / "scripts/05_run_all_checks.py"


RECIPES = {
    "check": {
        "description": "Run non-API production smoke checks.",
        "ai": False,
        "command": ["script", str(CHECK_RUNNER)],
    },
    "rna-prep": {
        "description": "Deterministic RNA setup to the AI boundary: metadata, paper packets, trusted AI queue.",
        "ai": False,
        "command": ["workflow", "--continue-from", "00", "--through", "05"],
    },
    "chip-prep": {
        "description": "Deterministic ChIP setup to the AI boundary: publication links, paper download prep, packets, preflight.",
        "ai": False,
        "command": ["workflow", "--continue-from", "20", "--through", "32"],
    },
    "rna-ai": {
        "description": "RNA AI pilot batch review, limited by the batch runner default. Requires --execute --execute-ai and API guards.",
        "ai": True,
        "command": ["workflow", "--step", "07", "--extra-args-on-execute", "--execute"],
    },
    "rna-ai-full": {
        "description": "RNA AI full trusted-queue run with --limit 0. Requires --execute --execute-ai and API guards.",
        "ai": True,
        "command": ["workflow", "--step", "07", "--extra-args-on-execute", "--execute", "--limit", "0"],
    },
    "rna-finalize": {
        "description": "Deterministic RNA aggregate inventory, QC, summaries, workbook, and finalization after RNA AI.",
        "ai": False,
        "command": [
            "sequence",
            ["workflow", "--step", "10"],
            ["workflow", "--step", "11"],
            ["workflow", "--step", "12"],
            ["workflow", "--step", "13"],
            ["workflow", "--step", "14"],
            ["workflow", "--step", "15"],
        ],
    },
    "chip-ai": {
        "description": "ChIP small-packet AI pilot batch review, limited by the batch runner default. Requires --execute --execute-ai and API guards.",
        "ai": True,
        "command": ["workflow", "--step", "33", "--extra-args-on-execute", "--execute"],
    },
    "chip-ai-full": {
        "description": "ChIP full small-packet AI run with --limit 0. Requires --execute --execute-ai and API guards.",
        "ai": True,
        "command": ["workflow", "--step", "33", "--extra-args-on-execute", "--execute", "--limit", "0"],
    },
    "chip-finalize": {
        "description": "Deterministic ChIP aggregate inventory, final QC, workbook, companion files, and summaries after ChIP AI.",
        "ai": False,
        "command": [
            "sequence",
            ["workflow", "--step", "39"],
            ["workflow", "--step", "40"],
            ["workflow", "--step", "41"],
            ["workflow", "--step", "42"],
            ["workflow", "--step", "43"],
        ],
    },
    "package": {
        "description": "Package final curator-facing release folder and zip.",
        "ai": False,
        "command": ["workflow", "--step", "90"],
    },
    "show-outputs": {
        "description": "Print current curator-facing output paths.",
        "ai": False,
        "command": ["outputs"],
    },
}


def build_single_command(parts: list[object], *, execute: bool, execute_ai: bool) -> list[str]:
    parts = list(parts)
    kind = parts.pop(0)

    if kind == "workflow":
        extra_on_execute = []
        if "--extra-args-on-execute" in parts:
            idx = parts.index("--extra-args-on-execute")
            extra_on_execute = parts[idx + 1:]
            parts = parts[:idx]
        cmd = [sys.executable, str(WORKFLOW_RUNNER)] + parts
        if execute:
            cmd.append("--execute")
        if execute_ai:
            cmd.append("--execute-ai")
        if execute and extra_on_execute:
            cmd.append("--extra-args")
            cmd.extend(extra_on_execute)
        return cmd

    if kind == "script":
        if execute:
            raise SystemExit("Recipe check is non-mutating and does not accept --execute.")
        if execute_ai:
            raise SystemExit("Recipe check is not an AI recipe and does not accept --execute-ai.")
        return [sys.executable] + parts

    if kind == "outputs":
        if execute:
            raise SystemExit("Recipe show-outputs is non-mutating and does not accept --execute.")
        if execute_ai:
            raise SystemExit("Recipe show-outputs is not an AI recipe and does not accept --execute-ai.")
        return [sys.executable, str(OUTPUT_RUNNER)]

    raise SystemExit(f"Unknown recipe command kind: {kind}")


def build_commands(recipe: dict[str, object], *, execute: bool, execute_ai: bool) -> list[list[str]]:
    parts = list(recipe["command"])
    if not parts:
        raise SystemExit("Recipe command is empty.")

    if parts[0] == "sequence":
        commands = []
        for subcommand in parts[1:]:
            if not isinstance(subcommand, list):
                raise SystemExit("Recipe sequence entries must be command lists.")
            commands.append(build_single_command(subcommand, execute=execute, execute_ai=execute_ai))
        return commands

    return [build_single_command(parts, execute=execute, execute_ai=execute_ai)]


def print_recipes() -> None:
    print("Available recipes:")
    for name, recipe in RECIPES.items():
        print(f"- {name}: {recipe['description']}")


def main() -> None:
    if load_dotenv is not None:
        load_dotenv(ROOT / ".env")

    parser = argparse.ArgumentParser()
    parser.add_argument("recipe", help="Recipe name, or 'list'.")
    parser.add_argument("--execute", action="store_true", help="Execute the underlying workflow command.")
    parser.add_argument("--execute-ai", action="store_true", help="Permit AI/API execution for AI recipes.")
    args = parser.parse_args()

    if args.recipe == "list":
        if args.execute or args.execute_ai:
            raise SystemExit("Recipe list is non-mutating and does not accept --execute or --execute-ai.")
        print_recipes()
        return

    if args.recipe not in RECIPES:
        print_recipes()
        raise SystemExit(f"Unknown recipe: {args.recipe}")

    recipe = RECIPES[args.recipe]
    if args.execute_ai and not recipe["ai"]:
        raise SystemExit(f"Recipe {args.recipe} is not an AI recipe and does not accept --execute-ai.")
    if args.execute and recipe["ai"]:
        if not args.execute_ai:
            raise SystemExit(f"Recipe {args.recipe} requires --execute-ai for API-capable execution.")
        if os.environ.get("AGENTIC_AI_ENABLE_API") != "1":
            raise SystemExit(
                f"Recipe {args.recipe} requires AGENTIC_AI_ENABLE_API=1 in .env or shell for API-capable execution."
            )
        if args.recipe in {"rna-ai", "chip-ai"}:
            print(
                f"NOTICE: {args.recipe} is a pilot/default-limited AI run. "
                f"Use {args.recipe}-full for --limit 0 full-queue execution.",
                flush=True,
            )

    commands = build_commands(recipe, execute=args.execute, execute_ai=args.execute_ai)
    print(f"Recipe: {args.recipe}", flush=True)
    print(f"Purpose: {recipe['description']}", flush=True)
    print("Underlying command:" if len(commands) == 1 else "Underlying commands:", flush=True)
    for cmd in commands:
        print("  " + " ".join(cmd), flush=True)
    print("", flush=True)

    for cmd in commands:
        result = subprocess.run(cmd, cwd=ROOT, check=False)
        if result.returncode != 0:
            print("")
            print(f"Recipe failed: {args.recipe}. See command output above.")
            raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
