#!/usr/bin/env python3
"""Независимая итоговая проверка демонстрационного эксперимента."""

from __future__ import annotations

import configparser
import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agent.helpers.validate_plan import validate  # noqa: E402


INPUT = ROOT / "demo" / "input"
WORKSPACE = ROOT / "demo" / "workspace"
SCHEMA = ROOT / "agent" / "schema" / "mldev-agent-plan-v1.schema.json"
EXPECTED_ORDER = [
    "acquire_data",
    "prepare_data",
    "hypothesis_1",
    "hypothesis_2",
]
GENERATED_PATHS = (
    "mldev-agent-plan.json",
    "experiment.yml",
    ".mldev/config.yaml",
    ".dvc/config",
    "data/raw.csv.dvc",
    "data/prepared.csv.dvc",
)


def load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def check_input_pristine() -> list[str]:
    """Убедиться, что агент не изменил файлы исходного проекта."""
    errors: list[str] = []
    for source in INPUT.rglob("*"):
        if not source.is_file():
            continue
        relative = source.relative_to(INPUT)
        generated_copy = WORKSPACE / relative
        if not generated_copy.is_file():
            errors.append(f"workspace потерял исходный файл: {relative}")
        elif source.read_bytes() != generated_copy.read_bytes():
            errors.append(f"изменён исходный файл: {relative}")

    forbidden_in_input = (
        "mldev-agent-plan.json",
        "experiment.yml",
        ".mldev",
        ".dvc",
        "data",
        "runs",
    )
    for relative in forbidden_in_input:
        if (INPUT / relative).exists():
            errors.append(f"сгенерированный путь попал в input: {relative}")
    return errors


def check_generated_files() -> list[str]:
    errors: list[str] = []
    for relative in GENERATED_PATHS:
        if not (WORKSPACE / relative).is_file():
            errors.append(f"не найден обязательный файл: {relative}")
    return errors


def check_plan() -> list[str]:
    plan_path = WORKSPACE / "mldev-agent-plan.json"
    if not plan_path.is_file():
        return ["план отсутствует"]

    errors = validate(
        plan_path,
        SCHEMA,
        WORKSPACE,
        require_resolved=True,
    )
    if not errors:
        plan = load_json(plan_path)
        if plan["pipeline"]["runs"] != EXPECTED_ORDER:
            errors.append(
                f"неожиданный порядок pipeline: {plan['pipeline']['runs']}"
            )
    return errors


def check_experiment() -> list[str]:
    experiment = WORKSPACE / "experiment.yml"
    if not experiment.is_file():
        return ["experiment.yml отсутствует"]

    text = experiment.read_text(encoding="utf-8")
    errors: list[str] = []
    for tag in ("!BasicStage", "!JupyterStage", "!GenericPipeline"):
        if tag not in text:
            errors.append(f"experiment.yml не содержит {tag}")
    if re.search(r"!Stage(?:\s|$)", text) or "mldev_dvc" in text:
        errors.append("experiment.yml использует устаревшую DVC-интеграцию")
    if text.count("name: prepare_data") != 1:
        errors.append("prepare_data должна быть объявлена ровно один раз")

    positions = []
    for stage_id in EXPECTED_ORDER:
        match = re.search(rf"name:\s*{re.escape(stage_id)}\s*$", text, re.MULTILINE)
        if match is None:
            errors.append(f"experiment.yml не содержит stage name: {stage_id}")
        else:
            positions.append(match.start())
    if len(positions) == len(EXPECTED_ORDER) and positions != sorted(positions):
        errors.append("стадии experiment.yml объявлены не по порядку")
    return errors


def check_dvc() -> list[str]:
    errors: list[str] = []
    config_path = WORKSPACE / ".dvc" / "config"
    if not config_path.is_file():
        return [".dvc/config отсутствует"]

    config = configparser.ConfigParser()
    config.read(config_path)
    remote = next(
        (
            section
            for section in config.sections()
            if section.strip("'") == 'remote "minio"'
        ),
        'remote "minio"',
    )
    if config.get("core", "remote", fallback="") != "minio":
        errors.append("minio не является default DVC remote")
    if config.get(remote, "url", fallback="") != "s3://dvc-storage":
        errors.append("неожиданный URL DVC remote")
    if (
        config.get(remote, "endpointurl", fallback="")
        != "http://localhost:9000"
    ):
        errors.append("неожиданный endpoint MinIO")

    lowered = config_path.read_text(encoding="utf-8").lower()
    if "secret" in lowered or "access_key" in lowered:
        errors.append(".dvc/config содержит credentials")

    for relative in ("data/raw.csv.dvc", "data/prepared.csv.dvc"):
        pointer = WORKSPACE / relative
        if pointer.is_file() and not re.search(
            r"^\s*(?:md5|hash):\s*\S+", pointer.read_text(encoding="utf-8"), re.MULTILINE
        ):
            errors.append(f"DVC pointer не содержит hash: {relative}")
    return errors


def check_run() -> list[str]:
    metadata_files = sorted((WORKSPACE / "runs").glob("*/metadata.json"))
    if not metadata_files:
        return ["не найден metadata.json запуска"]

    metadata = load_json(metadata_files[-1])
    errors: list[str] = []
    if metadata.get("status") != "succeeded":
        errors.append("последний запуск не имеет status=succeeded")
    if metadata.get("errors"):
        errors.append(f"metadata содержит ошибки: {metadata['errors']}")
    if metadata.get("expected_stage_order") != EXPECTED_ORDER:
        errors.append("metadata содержит неправильный порядок стадий")

    stage_checks = {
        check["stage"]: check
        for check in metadata.get("acceptance_checks", [])
        if "stage" in check and "marker" in check
    }
    for stage_id in EXPECTED_ORDER:
        check = stage_checks.get(stage_id)
        if not check:
            errors.append(f"нет проверки стадии: {stage_id}")
        elif check.get("count") != 1 or check.get("in_order") is not True:
            errors.append(f"стадия не прошла проверку: {stage_id}")

    hypothesis_checks = [
        check
        for check in metadata.get("acceptance_checks", [])
        if "hypothesis" in check
    ]
    if len(hypothesis_checks) != 2:
        errors.append("ожидалось две проверки гипотез")
    elif not all(check.get("accepted") is True for check in hypothesis_checks):
        errors.append("не все гипотезы приняты")

    for status_name in ("workspace_status", "cloud_status"):
        status = metadata.get("dvc", {}).get(status_name, {})
        if status.get("returncode") != 0:
            errors.append(f"DVC {status_name} завершился с ошибкой")
    return errors


def main() -> int:
    errors = [
        *check_input_pristine(),
        *check_generated_files(),
        *check_plan(),
        *check_experiment(),
        *check_dvc(),
        *check_run(),
    ]
    if errors:
        for error in errors:
            print(f"FAIL: {error}", file=sys.stderr)
        return 1

    print("PASS: план, MLDev, DVC, запуск и гипотезы проверены")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
