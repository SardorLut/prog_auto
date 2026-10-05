# Проверенные шаблоны MLDev

Справочник относится к MLDev `0.5.0.dev1`. Используй только приведённые здесь
типы и поля.

## Конфигурация модулей

Создай `.mldev/config.yaml`:

```yaml
extras:
  base: mldev.experiment_objects
  jupyter: mldev_jupyter.ipython

logger:
  level: INFO
  path: .mldev/logs
```

`base` регистрирует `!BasicStage` и `!GenericPipeline`. `jupyter` регистрирует
`!JupyterStage`.

Не записывай токены и пароли в `environ`: окружение команды может попасть в
debug log.

## BasicStage

Используй `!BasicStage` для существующих CLI и скриптов:

```yaml
acquire_data: &acquire_data !BasicStage
  name: acquire_data
  outputs:
    - data/raw.csv
  script:
    - python src/data_cli.py download --output data/raw.csv

prepare_data: &prepare_data !BasicStage
  name: prepare_data
  inputs:
    - data/raw.csv
  outputs:
    - data/prepared.csv
  script:
    - python src/data_cli.py prepare --input data/raw.csv --output data/prepared.csv
```

Поддерживаемые поля:

- `name` — имя стадии;
- `inputs` — файлы, необходимые стадии;
- `outputs` — создаваемые файлы;
- `params` — параметры для MLDev expressions;
- `env` — окружение только этой стадии;
- `script` — список shell-команд.

Элементы `script` выполняются последовательно через `&&`. Не создавай поля
`program` или `programs`: MLDev их не поддерживает.

## JupyterStage

Используй `!JupyterStage` только для существующего notebook:

```yaml
hypothesis_1: &hypothesis_1 !JupyterStage
  name: hypothesis_1
  notebook_pipeline: notebooks/hypothesis_1.all_cells
```

`all_cells` запускает все ячейки по порядку. Используй его только после
проверки, что notebook детерминирован и все его code cells нужны эксперименту.

Для `!JupyterStage` указывай только:

- `name`;
- `notebook_pipeline`.

Не добавляй неподтверждённые поля `inputs`, `outputs` или `env`. Ожидаемые
файлы результата проверяй после выполнения pipeline.

## Последовательный pipeline

Объяви стадии через YAML anchors и перечисли ссылки в нужном порядке:

```yaml
pipeline: !GenericPipeline
  runs:
    - *acquire_data
    - *prepare_data
    - *hypothesis_1
```

Порядок `runs` должен точно совпадать с `pipeline.runs` формального плана.
Одна общая стадия должна быть объявлена и указана в pipeline только один раз.

## Запрещённые конструкции

Не используй:

- `!Stage`;
- пакет `mldev_dvc`;
- параллельное выполнение;
- отсутствующие в исходном проекте команды;
- недоверенный `experiment.yml`.

`!Stage` относится к устаревшей DVC-интеграции. Современный DVC настраивается
и запускается отдельно от MLDev.

## Запуск

По умолчанию MLDev читает `experiment.yml` и запускает объект `pipeline`:

```bash
mldev run pipeline
```

MLDev сначала вызывает `prepare` для всех стадий, затем выполняет их. Нельзя
доверять только exit code CLI: после запуска отдельно проверь логи и ожидаемые
файлы.
