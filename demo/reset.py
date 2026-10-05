#!/usr/bin/env python3
"""Создание чистой рабочей копии демонстрационного ML-проекта."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


DEMO_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = DEMO_ROOT.parent
INPUT = DEMO_ROOT / "input"
WORKSPACE = DEMO_ROOT / "workspace"


def git(*arguments: str) -> None:
    subprocess.run(
        ["git", *arguments],
        cwd=WORKSPACE,
        check=True,
        text=True,
    )


def main() -> int:
    if not INPUT.is_dir():
        raise RuntimeError(f"Исходный проект не найден: {INPUT}")
    if WORKSPACE.parent != DEMO_ROOT or WORKSPACE.name != "workspace":
        raise RuntimeError(f"Небезопасный путь workspace: {WORKSPACE}")

    if WORKSPACE.exists():
        shutil.rmtree(WORKSPACE)
    shutil.copytree(INPUT, WORKSPACE)
    (WORKSPACE / "venv").symlink_to(
        PROJECT_ROOT / ".venv",
        target_is_directory=True,
    )

    git("init")
    git("config", "user.name", "MLDev Agent Demo")
    git("config", "user.email", "demo@example.invalid")
    git("add", ".")
    git("commit", "-m", "Исходный проект до работы MLDev-агента")

    print(f"Чистая рабочая копия: {WORKSPACE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
