# MLDev Experiment Agent

Native skill для OpenCode, который анализирует существующий ML-проект и
собирает из найденного кода воспроизводимый эксперимент на MLDev и DVC.
Каждая операция в формальном плане содержит evidence. Если код операции не
найден, агент записывает требование в `unresolved` и не запускает эксперимент.

Демонстрационный сценарий:

```text
acquire_data → prepare_data → hypothesis_1 → hypothesis_2
```

Подготовка данных выполняется один раз, обе гипотезы используют один и тот же
`data/prepared.csv`, а raw и prepared данные версионируются в локальном MinIO.

## Состав проекта

- `agent/SKILL.md` — инструкции native skill;
- `agent/schema/` — JSON Schema формального плана;
- `agent/references/` — проверенные паттерны MLDev и DVC;
- `agent/helpers/validate_plan.py` — schema и semantic validation;
- `agent/helpers/run_mldev.py` — контролируемый запуск и проверка результата;
- `demo/input/` — неизменяемый исходный ML-проект;
- `demo/prompts/` — три готовых prompt-файла для фаз plan, generate, execute;
- `demo/reset.py` — создание чистой одноразовой рабочей копии;
- `demo/verify.py` — независимая итоговая проверка;
- `demo/run.py` — автоматический end-to-end прогон через OpenCode.

Prompt-файлы не содержат project-specific placeholders: их можно целиком
копировать в OpenCode.

## Требования

Проверенная конфигурация:

- macOS или Linux;
- Python 3.11;
- Docker с `docker compose`;
- OpenCode 1.18.34 или совместимая версия;
- GNU Make;
- токен ChatWM для модели `chatwm/qwen3.5-9b`.

Версия MLDev закреплена по commit SHA, DVC ограничен одной major-версией.

## Первичная настройка

```bash
cd /путь/к/auto_prog
cp .env.example .env
```

Отредактируйте `.env`:

```dotenv
CHATWM_TOKEN=ваш-токен

MINIO_ROOT_USER=mldev-local
MINIO_ROOT_PASSWORD=сложный-локальный-пароль

AWS_ACCESS_KEY_ID=mldev-local
AWS_SECRET_ACCESS_KEY=сложный-локальный-пароль
AWS_DEFAULT_REGION=us-east-1
```

`AWS_ACCESS_KEY_ID` должен совпадать с `MINIO_ROOT_USER`, а
`AWS_SECRET_ACCESS_KEY` — с `MINIO_ROOT_PASSWORD`. Файл `.env` исключён из
Git; не показывайте и не коммитьте его.

Установите окружение, native skill и запустите MinIO:

```bash
make setup
```

Команда пересоздаёт `.venv`, устанавливает skill в
`~/.config/opencode/skills/mldev-experiment-agent`, запускает MinIO и
создаёт bucket `dvc-storage`. Повторный запуск безопасен.

MinIO API доступен на `http://localhost:9000`, web console — на
`http://localhost:9001`. Остановить сервис:

```bash
docker compose down
```

## Как посмотреть данные в DVC

Эти команды выполняются после фазы generate, когда уже созданы `.dvc/` и
файлы `data/*.dvc`:

```bash
cd demo/workspace
```

Показать remote и его настройки:

```bash
venv/bin/dvc remote list
venv/bin/dvc config --list
```

Ожидаемые значения:

```text
minio  s3://dvc-storage (default)
remote.minio.endpointurl=http://localhost:9000
```

Проверить, синхронизированы ли локальные данные с DVC cache и MinIO:

```bash
venv/bin/dvc status
venv/bin/dvc status --cloud
```

При успешной синхронизации ожидаются сообщения:

```text
Data and pipelines are up to date.
Cache and remote 'minio' are in sync.
```

Посмотреть DVC pointers и сами данные:

```bash
cat data/raw.csv.dvc
cat data/prepared.csv.dvc
cat data/raw.csv
cat data/prepared.csv
```

Загрузить данные из MinIO в рабочую копию:

```bash
venv/bin/dvc pull data/raw.csv.dvc data/prepared.csv.dvc
```

Повторно отправить данные в MinIO:

```bash
venv/bin/dvc push
```

Для просмотра remote через браузер откройте
[`http://localhost:9001`](http://localhost:9001), войдите с
`MINIO_ROOT_USER` и `MINIO_ROOT_PASSWORD` из `.env`, затем откройте bucket
`dvc-storage`. Внутри DVC хранит объекты по hash; исходные имена файлов
остаются в `data/raw.csv.dvc` и `data/prepared.csv.dvc`.

Credentials не записываются в `.dvc/config`: DVC получает
`AWS_ACCESS_KEY_ID` и `AWS_SECRET_ACCESS_KEY` из окружения, которое Make
загружает из `.env`.

## Автоматическая проверка воспроизводимости

Полный сценарий в независимых OpenCode-сессиях:

```bash
make homework
```

Команда:

1. пересоздаёт `demo/workspace` из `demo/input`;
2. строит и валидирует формальный план;
3. генерирует MLDev-конфигурацию и DVC pointers;
4. запускает pipeline только через `run_mldev.py`;
5. проверяет metadata, порядок стадий, артефакты, гипотезы и DVC.

Каждая фаза автоматически повторяется до трёх раз, если ответ модели не
проходит checkpoint. Транскрипты, stderr, checkpoint-файлы и итоговый manifest
сохраняются в `demo/artifacts/`.

Успешный итог:

```text
PASS: план, MLDev, DVC, запуск и гипотезы проверены
```

Повторно проверить уже полученный результат без обращения к модели:

```bash
make verify
```

## Сценарий ручной демонстрации

### 1. Исходный проект

```text
demo/input/
├── experiment-request.md
├── src/data_cli.py
└── notebooks/
    ├── hypothesis_1.ipynb
    └── hypothesis_2.ipynb
```

`data_cli.py` детерминированно получает и подготавливает данные. Первая
тетрадка проверяет среднее, вторая — population variance.

### 2. Skill

Откройте `agent/SKILL.md`, затем покажите:

- `agent/schema/mldev-agent-plan-v1.schema.json`;
- `agent/references/`;
- `agent/helpers/validate_plan.py`;
- `agent/helpers/run_mldev.py`.

### 3. Чистая рабочая копия

```bash
make clean
```

В `demo/workspace` появится только копия исходного проекта и ссылка `venv` на
подготовленное окружение. MLDev, DVC, данных и результатов в ней ещё нет.

### 4. OpenCode

```bash
make opencode
```

В открывшемся OpenCode загрузите skill:

```text
/mldev-experiment-agent
```

### 5. Фаза plan

Целиком скопируйте `demo/prompts/plan.md`. Агенту разрешены только исследование
и создание `mldev-agent-plan.json`.

После завершения покажите план. В нём должны быть:

- evidence для каждой стадии;
- артефакты как входы и выходы;
- один последовательный pipeline;
- пути `runs/<run_id>/hypothesis_1/result.json` и
  `runs/<run_id>/hypothesis_2/result.json`;
- пустой `unresolved`;
- успешная schema и semantic validation.

### 6. Фаза generate

Целиком скопируйте `demo/prompts/generate.md`.

После завершения покажите:

- `demo/workspace/experiment.yml`;
- `demo/workspace/.dvc/config`;
- `demo/workspace/data/raw.csv.dvc`;
- `demo/workspace/data/prepared.csv.dvc`.

`!BasicStage` запускает существующий CLI, `!JupyterStage` — существующие
notebooks, `!GenericPipeline` задаёт порядок. YAML anchors не дают объявить
стадию дважды. DVC-конфигурация содержит URL и endpoint, но не credentials.

### 7. Фаза execute

Целиком скопируйте `demo/prompts/execute.md`.

Helper повторно проверяет план и конфигурацию, запускает MLDev, а затем
проверяет stage markers, их порядок, артефакты, результаты гипотез и локальное
и remote-состояние DVC. Покажите напечатанный путь к:

```text
demo/workspace/runs/<run_id>/metadata.json
```

## Ожидаемые результаты

Исходные значения:

```text
2, 4, 6, 8, 10
```

После единственной стадии подготовки:

```text
2.5, 4.5, 6.5, 8.5, 10.5
```

- гипотеза 1: среднее `6.5 > 5.0`, поэтому `accepted: true`;
- гипотеза 2: population variance `8.0 < 10.0`, поэтому `accepted: true`.

В `metadata.json` ожидаются `status: "succeeded"`, пустой `errors`, по одному
marker каждой стадии и порядок
`acquire_data, prepare_data, hypothesis_1, hypothesis_2`.

## Воспроизводимость и границы

- `demo/input` не изменяется: каждый прогон начинается с новой копии;
- данные создаются существующим детерминированным CLI;
- формальный план проверяется до генерации и до запуска;
- pipeline нельзя запускать в обход helper;
- DVC remote работает локально и не требует внешнего S3;
- секреты передаются только через окружение;
- exit code MLDev сам по себе не считается доказательством успеха.

Если `make homework` завершился ошибкой, точная причина находится в последнем
`demo/artifacts/*.checkpoint.log` или `*.stderr.log`.
