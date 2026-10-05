#!/usr/bin/env python3
"""Установка MLDev Experiment Agent в каталог skills OpenCode."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path


AGENT_ROOT = Path(__file__).resolve().parent
DEFAULT_TARGET = (
    Path.home()
    / ".config"
    / "opencode"
    / "skills"
    / "mldev-experiment-agent"
)
DIRECTORIES = ("schema", "references", "helpers")


def install(target: Path) -> Path:
    """Скопировать skill и связанные файлы в target."""
    target = target.expanduser().resolve()
    target.mkdir(parents=True, exist_ok=True)

    shutil.copy2(AGENT_ROOT / "SKILL.md", target / "SKILL.md")

    for directory_name in DIRECTORIES:
        source = AGENT_ROOT / directory_name
        destination = target / directory_name
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(
            source,
            destination,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )

    return target


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Установить mldev-experiment-agent для OpenCode"
    )
    parser.add_argument(
        "--target",
        type=Path,
        default=DEFAULT_TARGET,
        help=f"каталог установки (по умолчанию: {DEFAULT_TARGET})",
    )
    args = parser.parse_args()

    installed_path = install(args.target)
    print(f"Установлено: {installed_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
