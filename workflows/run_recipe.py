#!/usr/bin/env python3
"""
User-facing recipe runner for common SRA paper curator workflows.

This is a thin wrapper around workflows/run_workflow_step.py. It keeps the
public quick start readable without duplicating workflow execution logic.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_RUNNER = ROOT / "workflows/run_workflow_step.py"
OUTPUT_RUNNER = ROOT / "scripts/90_show_curator_outputs.py"


RECIPES = {
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
        "description": "RNA AI batch review. Requires --execute --execute-ai and API guards for real API execution.",
        "ai": True,
        "command": ["workflow", "--step", "07"],
    },
    "chip-ai": {
        "description": "ChIP small-packet AI batch review. Requires --execute --execute-ai and API guards for real API execution.",
        "ai": True,
        "command": ["workflow", "--step", "33"],
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


def build_command(recipe: dict[str, object], *, execute: bool, execute_ai: bool) -> list[str]:
    parts = list(recipe["command"])
    kind = parts.pop(0)

    if kind == "workflow":
        cmd = [sys.executable, str(WORKFLOW_RUNNER)] + parts
        if execute:
            cmd.append("--execute")
        if execute_ai:
            cmd.append("--execute-ai")
        return cmd

    if kind == "outputs":
        if execute:
            raise SystemExit("Recipe show-outputs is non-mutating and does not accept --execute.")
        if execute_ai:
            raise SystemExit("Recipe show-outputs is not an AI recipe and does not accept --execute-ai.")
        return [sys.executable, str(OUTPUT_RUNNER)]

    raise SystemExit(f"Unknown recipe command kind: {kind}")


def print_recipes() -> None:
    print("Available recipes:")
    for name, recipe in RECIPES.items():
        print(f"- {name}: {recipe['description']}")


def main() -> None:
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

    cmd = build_command(recipe, execute=args.execute, execute_ai=args.execute_ai)
    print(f"Recipe: {args.recipe}", flush=True)
    print(f"Purpose: {recipe['description']}", flush=True)
    print("Underlying command:", flush=True)
    print("  " + " ".join(cmd), flush=True)
    print("", flush=True)

    result = subprocess.run(cmd, cwd=ROOT, check=False)
    if result.returncode != 0:
        print("")
        print(f"Recipe failed: {args.recipe}. See command output above.")
        raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
