#!/usr/bin/env python3
"""Последовательный end-to-end запуск демонстрации через OpenCode."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
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


def enforce_phase_boundary(phase: str) -> None:
    """Удалить артефакты, которые модель создала раньше разрешённой фазы."""
    if phase == "plan":
        forbidden = (
            "experiment.yml",
            ".mldev",
            ".dvc",
            ".dvcignore",
            "data",
            "runs",
        )
    elif phase == "generate":
        forbidden = ("runs",)
    else:
        return

    for relative in forbidden:
        path = WORKSPACE / relative
        if path.is_symlink() or path.is_file():
            path.unlink()
        elif path.is_dir():
            shutil.rmtree(path)


def run_phase(
    phase: str,
    model: str,
    run_name: str,
    env: dict[str, str],
    timeout: int,
    attempt: int,
    feedback: str,
) -> tuple[int, Path, Path]:
    """Запустить одну независимую сессию OpenCode."""
    prefix = f"{run_name}.{phase}.attempt-{attempt}"
    transcript = ARTIFACTS / f"{prefix}.jsonl"
    stderr_log = ARTIFACTS / f"{prefix}.stderr.log"
    prompt = rendered_prompt(phase)
    if feedback:
        prompt += (
            "\n\nПредыдущая попытка не прошла автоматическую проверку.\n"
            "Исправь только файлы текущего этапа и снова выполни все его проверки.\n"
            "Ошибки предыдущей попытки:\n"
            f"{feedback}"
        )
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
        f"{run_name}-{phase}-attempt-{attempt}",
        prompt,
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
    else:
        try:
            plan_data = json.loads(plan.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            errors.append(f"план не читается: {error}")
        else:
            artifact_paths = {
                artifact.get("path")
                for artifact in plan_data.get("artifacts", [])
            }
            expected_results = (
                "runs/<run_id>/hypothesis_1/result.json",
                "runs/<run_id>/hypothesis_2/result.json",
            )
            for expected_path in expected_results:
                if expected_path not in artifact_paths:
                    errors.append(
                        "план должен содержать артефакт с path="
                        f"{expected_path}"
                    )

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
        expected_declarations = (
            r"^acquire_data:\s*&acquire_data\s+!BasicStage\s*$",
            r"^prepare_data:\s*&prepare_data\s+!BasicStage\s*$",
            r"^hypothesis_1:\s*&hypothesis_1\s+!JupyterStage\s*$",
            r"^hypothesis_2:\s*&hypothesis_2\s+!JupyterStage\s*$",
            r"^pipeline:\s*!GenericPipeline\s*$",
        )
        for pattern in expected_declarations:
            if not re.search(pattern, text, re.MULTILINE):
                errors.append(
                    "experiment.yml содержит неверное объявление: "
                    f"{pattern}"
                )
        for grouped_tag in ("!BasicStage:", "!JupyterStage:", "!GenericPipeline:"):
            if grouped_tag in text:
                errors.append(
                    f"experiment.yml ошибочно использует тег как ключ: {grouped_tag}"
                )

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
    parser.add_argument("--max-phase-attempts", type=int, default=3)
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
        attempts: list[dict[str, object]] = []
        feedback = ""
        returncode = 1
        checkpoint_errors: list[str] = []

        for attempt in range(1, args.max_phase_attempts + 1):
            returncode, transcript, stderr_log = run_phase(
                phase,
                args.model,
                run_name,
                env,
                args.phase_timeout,
                attempt,
                feedback,
            )
            enforce_phase_boundary(phase)
            checkpoint_errors = checkpoint() if returncode == 0 else [
                f"OpenCode завершился с кодом {returncode}"
            ]
            checkpoint_log = (
                ARTIFACTS
                / f"{run_name}.{phase}.attempt-{attempt}.checkpoint.log"
            )
            checkpoint_log.write_text(
                "\n".join(checkpoint_errors)
                + ("\n" if checkpoint_errors else "PASS\n"),
                encoding="utf-8",
            )
            attempts.append(
                {
                    "attempt": attempt,
                    "returncode": returncode,
                    "checkpoint_errors": checkpoint_errors,
                    "transcript": str(transcript),
                    "stderr": str(stderr_log),
                    "checkpoint": str(checkpoint_log),
                }
            )
            if returncode == 0 and not checkpoint_errors:
                break
            feedback = "\n".join(checkpoint_errors)

        phase_results.append(
            {
                "phase": phase,
                "returncode": returncode,
                "checkpoint_errors": checkpoint_errors,
                "attempts": attempts,
                "transcript": attempts[-1]["transcript"],
                "stderr": attempts[-1]["stderr"],
                "checkpoint": attempts[-1]["checkpoint"],
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
