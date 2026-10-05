#!/usr/bin/env python3
"""Последовательный end-to-end запуск демонстрации через OpenCode."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Callable


ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "demo"
WORKSPACE = DEMO / "workspace"
PROMPTS = {
    "plan": DEMO / "prompts" / "plan.md",
    "generate": DEMO / "prompts" / "generate.md",
    "execute": DEMO / "prompts" / "execute.md",
}
RESET = DEMO / "reset.py"
ARTIFACTS = DEMO / "artifacts"
PYTHON = ROOT / ".venv" / "bin" / "python"
OPENCODE_CONFIG = ROOT / "opencode.json"
SKILL_ROOT = (
    Path.home()
    / ".config"
    / "opencode"
    / "skills"
    / "mldev-experiment-agent"
)


def environment() -> dict[str, str]:
    """Собрать окружение процесса и дополнить его значениями из .env."""
    result = os.environ.copy()
    env_file = ROOT / ".env"
    if env_file.is_file():
        for raw_line in env_file.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            result.setdefault(key.strip(), value.strip())
    result["OPENCODE_CONFIG"] = str(OPENCODE_CONFIG)
    return result


def rendered_prompt(phase: str) -> str:
    """Подставить переносимые абсолютные пути в prompt."""
    return (
        PROMPTS[phase]
        .read_text(encoding="utf-8")
        .replace("{PROJECT_ROOT}", str(ROOT))
        .replace("{SKILL_ROOT}", str(SKILL_ROOT))
    )


def run_phase(
    phase: str,
    model: str,
    run_name: str,
    env: dict[str, str],
    timeout: int,
) -> tuple[int, Path, Path]:
    """Запустить одну независимую сессию OpenCode."""
    transcript = ARTIFACTS / f"{run_name}.{phase}.jsonl"
    stderr_log = ARTIFACTS / f"{run_name}.{phase}.stderr.log"
    command = [
        "opencode",
        "run",
        "--dir",
        str(WORKSPACE),
        "--format",
        "json",
        "--auto",
        "--model",
        model,
        "--title",
        f"{run_name}-{phase}",
        rendered_prompt(phase),
    ]

    with transcript.open("w", encoding="utf-8") as stdout, stderr_log.open(
        "w", encoding="utf-8"
    ) as stderr:
        try:
            result = subprocess.run(
                command,
                cwd=WORKSPACE,
                env=env,
                stdout=stdout,
                stderr=stderr,
                check=False,
                timeout=timeout,
            )
            returncode = result.returncode
        except subprocess.TimeoutExpired:
            stderr.write(f"Фаза превысила timeout {timeout} секунд\n")
            returncode = 124
        except FileNotFoundError as error:
            stderr.write(f"{error}\n")
            returncode = 127

    return returncode, transcript, stderr_log


def plan_checkpoint() -> list[str]:
    """Проверить, что plan-фаза создала только валидный план."""
    errors: list[str] = []
    plan = WORKSPACE / "mldev-agent-plan.json"
    if not plan.is_file():
        return ["plan-фаза не создала mldev-agent-plan.json"]

    validation = subprocess.run(
        [
            str(PYTHON),
            str(SKILL_ROOT / "helpers" / "validate_plan.py"),
            str(plan),
            "--repository",
            str(WORKSPACE),
        ],
        cwd=WORKSPACE,
        text=True,
        capture_output=True,
        check=False,
    )
    if validation.returncode != 0:
        errors.append(validation.stdout + validation.stderr)

    forbidden = ("experiment.yml", ".mldev", ".dvc", "data", "runs")
    for relative in forbidden:
        if (WORKSPACE / relative).exists():
            errors.append(f"plan-фаза создала лишний путь: {relative}")
    return errors


def generation_checkpoint() -> list[str]:
    """Проверить обязательные MLDev/DVC-файлы до execute-фазы."""
    errors: list[str] = []
    required = (
        "mldev-agent-plan.json",
        "experiment.yml",
        ".mldev/config.yaml",
        ".dvc/config",
        "data/raw.csv.dvc",
        "data/prepared.csv.dvc",
        "venv",
    )
    for relative in required:
        if not (WORKSPACE / relative).exists():
            errors.append(f"generate-фаза не создала: {relative}")

    experiment = WORKSPACE / "experiment.yml"
    if experiment.is_file():
        text = experiment.read_text(encoding="utf-8")
        for tag in ("!BasicStage", "!JupyterStage", "!GenericPipeline"):
            if tag not in text:
                errors.append(f"experiment.yml не содержит {tag}")
        for notebook_pipeline in (
            "notebooks/hypothesis_1.all_cells",
            "notebooks/hypothesis_2.all_cells",
        ):
            if notebook_pipeline not in text:
                errors.append(
                    f"experiment.yml не содержит {notebook_pipeline}"
                )
        if "!Stage" in text or "mldev_dvc" in text:
            errors.append("experiment.yml содержит устаревшую DVC-интеграцию")

    dvc_config = WORKSPACE / ".dvc" / "config"
    if dvc_config.is_file():
        lowered = dvc_config.read_text(encoding="utf-8").lower()
        if "secret" in lowered or "access_key" in lowered:
            errors.append(".dvc/config содержит credentials")

    if (WORKSPACE / "runs").exists():
        errors.append("generate-фаза преждевременно создала runs/")
    return errors


def execution_checkpoint() -> list[str]:
    """Проверить metadata последнего запуска."""
    metadata_files = sorted((WORKSPACE / "runs").glob("*/metadata.json"))
    if not metadata_files:
        return ["execute-фаза не создала metadata.json"]

    try:
        metadata = json.loads(metadata_files[-1].read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return [f"metadata.json не читается: {error}"]

    errors: list[str] = []
    if metadata.get("status") != "succeeded":
        errors.append("последний запуск не имеет status=succeeded")
    if metadata.get("errors"):
        errors.append(f"metadata содержит ошибки: {metadata['errors']}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Запустить демонстрацию агента")
    parser.add_argument("--model", default="chatwm/qwen3.5-9b")
    parser.add_argument("--run-name")
    parser.add_argument("--phase-timeout", type=int, default=600)
    args = parser.parse_args()

    if not PYTHON.is_file():
        print(f"ERROR: виртуальное окружение не найдено: {PYTHON}", file=sys.stderr)
        return 2
    if not (SKILL_ROOT / "SKILL.md").is_file():
        print(
            f"ERROR: skill не установлен: {SKILL_ROOT}. "
            "Запустите python agent/install.py",
            file=sys.stderr,
        )
        return 2

    reset = subprocess.run([str(PYTHON), str(RESET)], cwd=ROOT, check=False)
    if reset.returncode != 0:
        return reset.returncode

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    run_name = args.run_name or datetime.now().strftime("demo_%Y-%m-%d_%H%M%S")
    env = environment()
    phase_results: list[dict[str, object]] = []

    phases: tuple[tuple[str, Callable[[], list[str]]], ...] = (
        ("plan", plan_checkpoint),
        ("generate", generation_checkpoint),
        ("execute", execution_checkpoint),
    )
    final_returncode = 0

    for phase, checkpoint in phases:
        returncode, transcript, stderr_log = run_phase(
            phase,
            args.model,
            run_name,
            env,
            args.phase_timeout,
        )
        checkpoint_errors = checkpoint() if returncode == 0 else []
        checkpoint_log = ARTIFACTS / f"{run_name}.{phase}.checkpoint.log"
        checkpoint_log.write_text(
            "\n".join(checkpoint_errors)
            + ("\n" if checkpoint_errors else "PASS\n"),
            encoding="utf-8",
        )
        phase_results.append(
            {
                "phase": phase,
                "returncode": returncode,
                "checkpoint_errors": checkpoint_errors,
                "transcript": str(transcript),
                "stderr": str(stderr_log),
                "checkpoint": str(checkpoint_log),
            }
        )
        if returncode != 0 or checkpoint_errors:
            final_returncode = returncode or 1
            break

    manifest = ARTIFACTS / f"{run_name}.manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "run_name": run_name,
                "model": args.model,
                "phase_timeout": args.phase_timeout,
                "phases": phase_results,
                "returncode": final_returncode,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    for result in phase_results:
        print(f"{result['phase']}_transcript={result['transcript']}")
    print(f"manifest={manifest}")
    print(f"returncode={final_returncode}")
    return final_returncode


if __name__ == "__main__":
    raise SystemExit(main())
