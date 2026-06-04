"""Shared command execution utilities for production scripts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import subprocess


@dataclass
class CommandResult:
    returncode: int
    stdout: str
    cmd: list[str]


def run_command(
    cmd: list[str],
    cwd: str | Path = ".",
    allow_fail: bool = False,
    env: dict[str, str] | None = None,
) -> CommandResult:
    """Run a shell command safely and capture combined stdout/stderr."""
    env_full = os.environ.copy()
    if env:
        env_full.update(env)

    p = subprocess.run(
        cmd,
        cwd=Path(cwd),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=env_full,
    )

    result = CommandResult(
        returncode=p.returncode,
        stdout=p.stdout.strip(),
        cmd=cmd,
    )

    if p.returncode != 0 and not allow_fail:
        raise RuntimeError(
            "Command failed:\n"
            + " ".join(cmd)
            + "\n\nOutput:\n"
            + result.stdout
        )

    return result
