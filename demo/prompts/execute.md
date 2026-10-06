Загрузи native skill `mldev-experiment-agent`.

В текущем репозитории уже существуют:

- проверенный `mldev-agent-plan.json`;
- `experiment.yml`;
- `.mldev/config.yaml`;
- DVC-конфигурация и pointers.

Выполни только статическую проверку, запуск и проверку результата. Не изменяй
план, вычислительную логику, notebooks или DVC pointers. Не читай `../input` и
не изменяй файлы за пределами текущего репозитория.

Перед запуском проверь:

1. план с флагом `--require-resolved`;
2. соответствие порядка стадий в плане и `experiment.yml`;
3. notebook pipelines заданы буквально как
   `notebooks/hypothesis_1.all_cells` и
   `notebooks/hypothesis_2.all_cells`, без расширения `.ipynb`;
4. отсутствие `!Stage` и `mldev_dvc`;
5. отсутствие credentials в созданных файлах;
6. доступность DVC remote.

Запусти pipeline только через helper:

```bash
venv/bin/python \
  "$HOME/.config/opencode/skills/mldev-experiment-agent/helpers/run_mldev.py" \
  --repository . \
  --plan mldev-agent-plan.json \
  --experiment experiment.yml \
  --pipeline pipeline \
  --mldev-command venv/bin/mldev
```

Не доверяй только exit code MLDev. Открой путь к `metadata.json`, который
напечатает helper.

Проверь:

1. `status` равен `succeeded`;
2. `errors` пуст;
3. стадии выполнились ровно по одному разу и в правильном порядке;
4. все ожидаемые артефакты существуют;
5. обе гипотезы содержат `accepted: true`;
6. локальная и remote-проверки DVC успешны.

Если проверка не прошла, сохрани логи и сообщи точную ошибку. Не исправляй
вычислительную логику и не запускай эксперимент повторно.

В конце сообщи:

- `run_id`;
- путь к `metadata.json`;
- фактический порядок стадий;
- результат каждой гипотезы;
- состояние DVC.
