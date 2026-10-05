#!/usr/bin/env python3
"""Детерминированное получение и подготовка демонстрационных данных."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path


RAW_VALUES = (2, 4, 6, 8, 10)


def download(output: Path) -> None:
    """Создать исходный набор данных."""
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=["sample_id", "raw_value"])
        writer.writeheader()
        for sample_id, value in enumerate(RAW_VALUES, start=1):
            writer.writerow({"sample_id": sample_id, "raw_value": value})

    print(f"STAGE_RESULT acquire_data output={output}")


def prepare(source: Path, output: Path) -> None:
    """Преобразовать raw_value в подготовленный признак value."""
    with source.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=["sample_id", "value"])
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "sample_id": row["sample_id"],
                    "value": float(row["raw_value"]) + 0.5,
                }
            )

    print(f"STAGE_RESULT prepare_data input={source} output={output}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Работа с данными эксперимента")
    commands = parser.add_subparsers(dest="command", required=True)

    download_parser = commands.add_parser("download")
    download_parser.add_argument("--output", type=Path, required=True)

    prepare_parser = commands.add_parser("prepare")
    prepare_parser.add_argument("--input", type=Path, required=True)
    prepare_parser.add_argument("--output", type=Path, required=True)

    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "download":
        download(args.output)
    elif args.command == "prepare":
        prepare(args.input, args.output)


if __name__ == "__main__":
    main()
