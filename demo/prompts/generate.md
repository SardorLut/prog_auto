Загрузи native skill `mldev-experiment-agent`.

В текущем репозитории уже существует проверенный
`mldev-agent-plan.json`. Выполни только генерацию MLDev-конфигурации и настройку
DVC.

Не исследуй проект заново и не изменяй формальный план. Не читай `../input` и
не изменяй файлы за пределами текущего репозитория.

Сначала проверь, что план полностью разрешён:

```bash
{PROJECT_ROOT}/.venv/bin/python \
  {SKILL_ROOT}/helpers/validate_plan.py \
  mldev-agent-plan.json \
  --repository . \
  --require-resolved
```

Если проверка не прошла, остановись.

Прочитай справочники:

- `{SKILL_ROOT}/references/mldev_patterns.md`;
- `{SKILL_ROOT}/references/dvc_patterns.md`.

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

Ссылка `venv` на `{PROJECT_ROOT}/.venv` уже создана reset-скриптом. Не изменяй
её.

Требования к DVC:

1. используй существующий CLI проекта для создания raw и prepared данных;
2. настрой default remote `minio` по адресу `s3://dvc-storage`;
3. настрой endpoint `http://localhost:9000`;
4. добавь оба файла данных в DVC;
5. выполни `dvc push`;
6. не записывай credentials в файлы.

Credentials уже переданы через окружение.

После генерации повторно проверь план и созданные файлы. Убедись, что
`experiment.yml` не содержит устаревших тегов и что `.dvc/config` не содержит
секретов.

Не запускай MLDev pipeline и не создавай `runs/`. В конце сообщи созданные
пути и результат `dvc status`.
