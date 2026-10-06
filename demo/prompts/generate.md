Загрузи native skill `mldev-experiment-agent`.

В текущем репозитории уже существует проверенный
`mldev-agent-plan.json`. Выполни только генерацию MLDev-конфигурации и настройку
DVC.

Не исследуй проект заново и не изменяй формальный план. Не читай `../input` и
не изменяй файлы за пределами текущего репозитория.

Сначала проверь, что план полностью разрешён:

```bash
venv/bin/python \
  "$HOME/.config/opencode/skills/mldev-experiment-agent/helpers/validate_plan.py" \
  mldev-agent-plan.json \
  --repository . \
  --require-resolved
```

Если проверка не прошла, остановись.

Прочитай справочники:

- `~/.config/opencode/skills/mldev-experiment-agent/references/mldev_patterns.md`;
- `~/.config/opencode/skills/mldev-experiment-agent/references/dvc_patterns.md`.

Создай:

1. `experiment.yml`;
2. `.mldev/config.yaml`;
3. современную независимую DVC-конфигурацию;
4. DVC pointers для raw и prepared данных.

Требования к MLDev:

1. используй только `!BasicStage`, `!JupyterStage` и `!GenericPipeline`;
2. объяви каждую стадию один раз через YAML anchor;
3. сохрани точный порядок стадий формального плана;
4. укажи точные notebook pipelines без расширения `.ipynb`:
   - `notebooks/hypothesis_1.all_cells`;
   - `notebooks/hypothesis_2.all_cells`;
5. не используй `!Stage` или `mldev_dvc`.

Объявляй тег у каждого объекта в той же строке, что ключ и anchor:

```yaml
acquire_data: &acquire_data !BasicStage
  name: acquire_data

hypothesis_1: &hypothesis_1 !JupyterStage
  name: hypothesis_1
  notebook_pipeline: notebooks/hypothesis_1.all_cells

pipeline: !GenericPipeline
  runs:
    - *acquire_data
```

Не создавай группирующие ключи `!BasicStage:`, `!JupyterStage:` или
`!GenericPipeline:`. У `pipeline` не должно быть поля `name`.

Ссылка `venv` на виртуальное окружение уже создана reset-скриптом. Не изменяй
её. Все Python и DVC команды запускай через `venv/bin/`.

Требования к DVC:

1. используй существующий CLI проекта для создания raw и prepared данных;
2. настрой default remote `minio` по адресу `s3://dvc-storage`;
3. настрой endpoint `http://localhost:9000`;
4. добавь оба файла данных в DVC;
5. выполни `dvc push`;
6. не записывай credentials в файлы.

Credentials уже переданы через окружение.

Отсутствие `data/raw.csv` и `data/prepared.csv` не является блокером: именно
этот этап обязан создать их существующим CLI из evidence. Обязательно выполни
в текущем репозитории все команды по порядку:

```bash
venv/bin/python src/data_cli.py download --output data/raw.csv
venv/bin/python src/data_cli.py prepare \
  --input data/raw.csv \
  --output data/prepared.csv

test -d .dvc || venv/bin/dvc init
venv/bin/dvc remote add -f -d minio s3://dvc-storage
venv/bin/dvc remote modify minio endpointurl http://localhost:9000
venv/bin/dvc add data/raw.csv data/prepared.csv
venv/bin/dvc push
venv/bin/dvc status
venv/bin/dvc status --cloud
```

Не ограничивайся `dvc init` и настройкой remote. Этап считается завершённым
только если существуют оба файла:

- `data/raw.csv.dvc`;
- `data/prepared.csv.dvc`.

После генерации повторно проверь план и созданные файлы. Убедись, что
`experiment.yml` не содержит устаревших тегов и что `.dvc/config` не содержит
секретов.

Не запускай MLDev pipeline и не создавай `runs/`. В конце сообщи созданные
пути и результат `dvc status`.
