#!/usr/bin/env python3
"""Запуск MLDev с сохранением логов и независимой проверкой результата."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


SECRET_VARIABLES = {
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "CHATWM_TOKEN",
    "MINIO_ROOT_PASSWORD",
    "MINIO_ROOT_USER",
}
FAILURE_MARKERS = (
    "Traceback (most recent call last)",
    "Cannot run mldev experiment",
)


def environment_tool(name: str) -> str:
    """Найти CLI рядом с текущим Python или в системном PATH."""
    sibling = Path(sys.executable).with_name(name)
    if sibling.is_file():
        return str(sibling)
    return shutil.which(name) or name


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as stream:
        value = json.load(stream)
    if not isinstance(value, dict):
        raise ValueError(f"{path}: ожидался JSON-объект")
    return value


def resolve_path(repository: Path, value: str, run_id: str) -> Path:
    """Подставить run_id и запретить выход за границы репозитория."""
    rendered = (
        value.replace("<run_id>", run_id)
        .replace("{run_id}", run_id)
        .replace("${run_id}", run_id)
    )
    path = (repository / rendered).resolve()
    path.relative_to(repository)
    return path


def run_command(
    command: list[str],
    cwd: Path,
    env: dict[str, str],
) -> dict[str, Any]:
    """Выполнить команду и вернуть безопасный сериализуемый результат."""
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        return {
            "command": command,
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
    except FileNotFoundError as error:
        return {
            "command": command,
            "returncode": 127,
            "stdout": "",
            "stderr": str(error),
        }


def check_stage_trace(
    output: str,
    expected_order: list[str],
) -> tuple[list[dict[str, Any]], list[str]]:
    """Проверить, что каждая стадия оставила один marker в нужном порядке."""
    checks: list[dict[str, Any]] = []
    errors: list[str] = []
    previous_position = -1

    for stage_id in expected_order:
        marker = f"STAGE_RESULT {stage_id}"
        count = output.count(marker)
        position = output.find(marker)
        in_order = count == 1 and position > previous_position
        checks.append(
            {
                "stage": stage_id,
                "marker": marker,
                "count": count,
                "in_order": in_order,
            }
        )
        if count != 1:
            errors.append(
                f"стадия '{stage_id}': marker найден {count} раз вместо одного"
            )
        elif position <= previous_position:
            errors.append(f"стадия '{stage_id}' выполнена не по порядку")
        previous_position = max(previous_position, position)

    return checks, errors


def check_artifacts(
    plan: dict[str, Any],
    repository: Path,
    run_id: str,
) -> tuple[list[dict[str, Any]], list[str]]:
    checks: list[dict[str, Any]] = []
    errors: list[str] = []

    for artifact in plan["artifacts"]:
        try:
            path = resolve_path(repository, artifact["path"], run_id)
            exists = path.exists()
        except ValueError:
            path = repository / artifact["path"]
            exists = False
            errors.append(
                f"artifact '{artifact['id']}' выходит за границы репозитория"
            )

        checks.append(
            {
                "artifact": artifact["id"],
                "path": str(path),
                "exists": exists,
            }
        )
        if not exists:
            errors.append(f"artifact '{artifact['id']}' не найден: {path}")

    return checks, errors


def check_hypotheses(
    plan: dict[str, Any],
    repository: Path,
    run_id: str,
) -> tuple[list[dict[str, Any]], list[str]]:
    checks: list[dict[str, Any]] = []
    errors: list[str] = []

    for hypothesis in plan["hypotheses"]:
        stage_id = hypothesis["stage_id"]
        result_path = (
            repository
            / "runs"
            / run_id
            / stage_id
            / "result.json"
        )
        check: dict[str, Any] = {
            "hypothesis": hypothesis["id"],
            "stage": stage_id,
            "path": str(result_path),
            "accepted": False,
        }

        if not result_path.is_file():
            errors.append(
                f"гипотеза '{hypothesis['id']}': result.json не найден"
            )
            checks.append(check)
            continue

        try:
            result = load_json(result_path)
        except (OSError, ValueError, json.JSONDecodeError) as error:
            errors.append(f"гипотеза '{hypothesis['id']}': {error}")
            checks.append(check)
            continue

        accepted = result.get("accepted") is True
        check["accepted"] = accepted
        check["result"] = result
        checks.append(check)
        if not accepted:
            errors.append(f"гипотеза '{hypothesis['id']}' не принята")

    return checks, errors


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Запустить и проверить MLDev experiment"
    )
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--plan", type=Path, default=Path("mldev-agent-plan.json"))
    parser.add_argument("--experiment", type=Path, default=Path("experiment.yml"))
    parser.add_argument("--pipeline", default="pipeline")
    parser.add_argument("--mldev-command", default="mldev")
    args = parser.parse_args()

    repository = args.repository.resolve()
    plan_path = args.plan if args.plan.is_absolute() else repository / args.plan
    experiment_path = (
        args.experiment
        if args.experiment.is_absolute()
        else repository / args.experiment
    )
    run_id = (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        + "-"
        + uuid4().hex[:8]
    )
    run_directory = repository / "runs" / run_id
    run_directory.mkdir(parents=True, exist_ok=False)

    try:
        plan = load_json(plan_path)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2

    execution_env = {
        key: value
        for key, value in os.environ.items()
        if key not in SECRET_VARIABLES
    }
    execution_env["MLDEV_RUN_ID"] = run_id

    command = [
        args.mldev_command,
        "run",
        "-f",
        str(experiment_path),
        "--force-run",
        args.pipeline,
    ]
    execution = run_command(command, repository, execution_env)
    stdout_path = run_directory / "stdout.log"
    stderr_path = run_directory / "stderr.log"
    stdout_path.write_text(execution["stdout"], encoding="utf-8")
    stderr_path.write_text(execution["stderr"], encoding="utf-8")

    combined_output = execution["stdout"] + "\n" + execution["stderr"]
    errors: list[str] = []
    if execution["returncode"] != 0:
        errors.append(f"MLDev returncode={execution['returncode']}")
    for marker in FAILURE_MARKERS:
        if marker in combined_output:
            errors.append(f"обнаружен failure marker: {marker}")

    expected_order = plan["pipeline"]["runs"]
    stage_checks, stage_errors = check_stage_trace(
        combined_output, expected_order
    )
    artifact_checks, artifact_errors = check_artifacts(
        plan, repository, run_id
    )
    hypothesis_checks, hypothesis_errors = check_hypotheses(
        plan, repository, run_id
    )
    errors.extend(stage_errors)
    errors.extend(artifact_errors)
    errors.extend(hypothesis_errors)

    dvc_env = os.environ.copy()
    dvc = environment_tool("dvc")
    dvc_workspace = run_command([dvc, "status"], repository, dvc_env)
    dvc_cloud = run_command([dvc, "status", "--cloud"], repository, dvc_env)
    if dvc_workspace["returncode"] != 0:
        errors.append("dvc status завершился с ошибкой")
    if dvc_cloud["returncode"] != 0:
        errors.append("dvc status --cloud завершился с ошибкой")

    metadata = {
        "run_id": run_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "succeeded" if not errors else "failed",
        "expected_stage_order": expected_order,
        "execution": {
            "command": command,
            "returncode": execution["returncode"],
            "stdout": str(stdout_path),
            "stderr": str(stderr_path),
        },
        "acceptance_checks": [
            *stage_checks,
            *artifact_checks,
            *hypothesis_checks,
        ],
        "dvc": {
            "workspace_status": dvc_workspace,
            "cloud_status": dvc_cloud,
        },
        "errors": errors,
    }
    metadata_path = run_directory / "metadata.json"
    metadata_path.write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print(f"run_id={run_id}")
    print(f"metadata={metadata_path}")
    print(f"status={metadata['status']}")
    for error in errors:
        print(f"FAIL: {error}", file=sys.stderr)

    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
