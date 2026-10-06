Загрузи native skill `mldev-experiment-agent`.

Выполни только этапы исследования проекта и построения формального плана.
Текущий репозиторий является одноразовой рабочей копией.

Используй как смысловой вход только:

- файлы текущего репозитория;
- `experiment-request.md`.

Не читай `../input` и не изменяй файлы за пределами текущего репозитория.

Перед созданием плана прочитай полную схему:

`~/.config/opencode/skills/mldev-experiment-agent/schema/mldev-agent-plan-v1.schema.json`

Требования к плану:

1. включи получение исходных данных;
2. включи общую подготовку данных ровно один раз;
3. включи обе hypothesis notebooks;
4. для каждой стадии укажи конкретное evidence из репозитория;
5. используй идентификаторы артефактов в `inputs` и `outputs`;
6. используй идентификаторы стадий в зависимостях, producer и consumers;
7. создай один строго последовательный pipeline;
8. не придумывай отсутствующие команды или вычисления;
9. используй `unresolved`, если доказательств недостаточно.
10. пути результатов задай буквально:
    - `runs/<run_id>/hypothesis_1/result.json`;
    - `runs/<run_id>/hypothesis_2/result.json`.

`<run_id>` — обязательный placeholder. Не заменяй его примером вроде
`mldev-001`, датой или заранее выбранным идентификатором.

Создай только:

`mldev-agent-plan.json`

Не создавай `experiment.yml`, `.mldev`, `.dvc`, данные или `runs/`.

Проверь план:

```bash
venv/bin/python \
  "$HOME/.config/opencode/skills/mldev-experiment-agent/helpers/validate_plan.py" \
  mldev-agent-plan.json \
  --repository .
```

Исправляй план, пока команда не напечатает `VALID`. После этого сообщи путь к
плану и порядок стадий pipeline.
