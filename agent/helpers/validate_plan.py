#!/usr/bin/env python3
"""Проверка структуры и смысла mldev-agent-plan/v1."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


AGENT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCHEMA = AGENT_ROOT / "schema" / "mldev-agent-plan-v1.schema.json"


def load_json(path: Path) -> dict[str, Any]:
    """Прочитать JSON-объект из файла."""
    with path.open(encoding="utf-8") as stream:
        value = json.load(stream)
    if not isinstance(value, dict):
        raise ValueError(f"{path}: корневое значение должно быть объектом")
    return value


def duplicate_ids(items: list[dict[str, Any]], section: str) -> list[str]:
    """Найти повторяющиеся идентификаторы в разделе плана."""
    seen: set[str] = set()
    errors: list[str] = []
    for item in items:
        item_id = item["id"]
        if item_id in seen:
            errors.append(f"{section}: повторяется id '{item_id}'")
        seen.add(item_id)
    return errors


def evidence_error(path: str, repository: Path, stage_id: str) -> str | None:
    """Проверить, что evidence указывает на файл внутри репозитория."""
    candidate = (repository / path).resolve()
    try:
        candidate.relative_to(repository)
    except ValueError:
        return f"стадия '{stage_id}': evidence.path выходит за границы репозитория"
    if not candidate.is_file():
        return f"стадия '{stage_id}': файл evidence не найден: {path}"
    return None


def semantic_errors(
    plan: dict[str, Any],
    repository: Path,
    require_resolved: bool,
) -> list[str]:
    """Проверить связи, которые невозможно выразить одной JSON Schema."""
    errors: list[str] = []
    hypotheses = plan["hypotheses"]
    artifacts = plan["artifacts"]
    stages = plan["stages"]

    errors.extend(duplicate_ids(hypotheses, "hypotheses"))
    errors.extend(duplicate_ids(artifacts, "artifacts"))
    errors.extend(duplicate_ids(stages, "stages"))

    hypothesis_ids = {item["id"] for item in hypotheses}
    artifact_ids = {item["id"] for item in artifacts}
    stage_ids = {item["id"] for item in stages}
    stages_by_id = {item["id"]: item for item in stages}
    artifacts_by_id = {item["id"]: item for item in artifacts}

    pipeline_runs = plan["pipeline"]["runs"]
    if set(pipeline_runs) != stage_ids:
        missing = sorted(stage_ids - set(pipeline_runs))
        unknown = sorted(set(pipeline_runs) - stage_ids)
        if missing:
            errors.append(f"pipeline не содержит стадии: {missing}")
        if unknown:
            errors.append(f"pipeline ссылается на неизвестные стадии: {unknown}")

    positions = {stage_id: index for index, stage_id in enumerate(pipeline_runs)}

    for stage in stages:
        stage_id = stage["id"]
        evidence_issue = evidence_error(
            stage["evidence"]["path"], repository, stage_id
        )
        if evidence_issue:
            errors.append(evidence_issue)

        if stage["kind"] in {"basic-script", "wrapper"} and not stage.get("command"):
            errors.append(f"стадия '{stage_id}': для kind={stage['kind']} нужна command")

        for artifact_id in stage["inputs"]:
            if artifact_id not in artifact_ids:
                errors.append(
                    f"стадия '{stage_id}': неизвестный входной artifact '{artifact_id}'"
                )
            elif stage_id not in artifacts_by_id[artifact_id]["consumers"]:
                errors.append(
                    f"artifact '{artifact_id}' не содержит consumer '{stage_id}'"
                )

        for artifact_id in stage["outputs"]:
            if artifact_id not in artifact_ids:
                errors.append(
                    f"стадия '{stage_id}': неизвестный выходной artifact '{artifact_id}'"
                )
            elif artifacts_by_id[artifact_id]["producer"] != stage_id:
                errors.append(
                    f"artifact '{artifact_id}' имеет другого producer"
                )

        for dependency in stage["depends_on"]:
            if dependency not in stage_ids:
                errors.append(
                    f"стадия '{stage_id}': неизвестная зависимость '{dependency}'"
                )
            elif (
                dependency in positions
                and stage_id in positions
                and positions[dependency] >= positions[stage_id]
            ):
                errors.append(
                    f"стадия '{stage_id}' расположена раньше зависимости '{dependency}'"
                )

    for artifact in artifacts:
        artifact_id = artifact["id"]
        producer = artifact["producer"]
        if producer is not None:
            if producer not in stage_ids:
                errors.append(
                    f"artifact '{artifact_id}': неизвестный producer '{producer}'"
                )
            elif artifact_id not in stages_by_id[producer]["outputs"]:
                errors.append(
                    f"producer '{producer}' не объявляет output '{artifact_id}'"
                )

        for consumer in artifact["consumers"]:
            if consumer not in stage_ids:
                errors.append(
                    f"artifact '{artifact_id}': неизвестный consumer '{consumer}'"
                )
            elif artifact_id not in stages_by_id[consumer]["inputs"]:
                errors.append(
                    f"consumer '{consumer}' не объявляет input '{artifact_id}'"
                )

    used_hypothesis_stages: set[str] = set()
    for hypothesis in hypotheses:
        stage_id = hypothesis["stage_id"]
        if stage_id not in stage_ids:
            errors.append(
                f"гипотеза '{hypothesis['id']}': неизвестная стадия '{stage_id}'"
            )
        elif stage_id in used_hypothesis_stages:
            errors.append(
                f"стадия '{stage_id}' назначена нескольким гипотезам"
            )
        used_hypothesis_stages.add(stage_id)

    unresolved_ids = {item["id"] for item in plan["unresolved"]}
    unknown_unresolved = unresolved_ids - stage_ids - hypothesis_ids
    if unknown_unresolved:
        errors.append(
            f"unresolved содержит неизвестные id: {sorted(unknown_unresolved)}"
        )
    if require_resolved and plan["unresolved"]:
        errors.append("план содержит unresolved и не готов к генерации")

    return errors


def validate(
    plan_path: Path,
    schema_path: Path,
    repository: Path,
    require_resolved: bool = False,
) -> list[str]:
    """Вернуть все структурные и семантические ошибки плана."""
    plan = load_json(plan_path)
    schema = load_json(schema_path)
    Draft202012Validator.check_schema(schema)

    validator = Draft202012Validator(schema)
    errors = [
        f"schema {error.json_path}: {error.message}"
        for error in sorted(validator.iter_errors(plan), key=lambda item: list(item.path))
    ]
    if errors:
        return errors

    return semantic_errors(plan, repository.resolve(), require_resolved)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Проверить mldev-agent-plan/v1"
    )
    parser.add_argument("plan", type=Path)
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    parser.add_argument(
        "--require-resolved",
        action="store_true",
        help="считать наличие unresolved ошибкой",
    )
    args = parser.parse_args()

    try:
        errors = validate(
            args.plan,
            args.schema,
            args.repository,
            args.require_resolved,
        )
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2

    if errors:
        for error in errors:
            print(f"FAIL: {error}", file=sys.stderr)
        return 1

    print("VALID: план соответствует mldev-agent-plan/v1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
