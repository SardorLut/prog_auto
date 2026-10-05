# Проверенные шаблоны DVC и MinIO

DVC работает отдельно от MLDev. Не используй `!Stage` или пакет `mldev_dvc`.

## Назначение

Версионируй:

- исходные данные `data/raw.csv`;
- подготовленные данные `data/prepared.csv`.

Не добавляй в DVC:

- `runs/`;
- логи;
- токены и пароли;
- виртуальное окружение.

## Инициализация

В корне анализируемого Git-репозитория:

```bash
dvc init
dvc remote add -d minio s3://dvc-storage
dvc remote modify minio endpointurl http://localhost:9000
```

Эти команды создают `.dvc/config`. В нём должны находиться только адрес
хранилища и endpoint.

## Credentials

MinIO использует стандартные переменные S3:

```bash
export AWS_ACCESS_KEY_ID="..."
export AWS_SECRET_ACCESS_KEY="..."
export AWS_DEFAULT_REGION="us-east-1"
```

Передавай credentials только через окружение процесса. Не записывай их:

- в `.dvc/config`;
- в `experiment.yml`;
- в Git;
- в MLDev stage environment;
- в сохранённые debug logs.

## Создание данных

Используй только команды, подтверждённые evidence исходного проекта:

```bash
python src/data_cli.py download --output data/raw.csv
python src/data_cli.py prepare \
  --input data/raw.csv \
  --output data/prepared.csv
```

## Версионирование

```bash
dvc add data/raw.csv data/prepared.csv
dvc push
```

После `dvc add` должны появиться:

```text
data/raw.csv.dvc
data/prepared.csv.dvc
```

Сами CSV-файлы должны быть добавлены в `.gitignore` автоматически. Файлы
`.dvc` и `.dvc/config` являются частью воспроизводимой конфигурации проекта.

## Проверка

Проверь локальное состояние:

```bash
dvc status
```

Проверь соответствие remote:

```bash
dvc status --cloud
```

Обе команды должны завершиться успешно. Дополнительно убедись, что каждый
`.dvc`-файл содержит content hash.

## Запреты

Не выполняй:

- `dvc destroy`;
- удаление существующего remote;
- очистку чужого DVC cache;
- перезапись данных неизвестными командами;
- сохранение credentials через `dvc remote modify ... access_key_id`.

Если MinIO недоступен или credentials отклонены, сообщи об инфраструктурной
ошибке и остановись. Не изменяй эксперимент для обхода ошибки авторизации.
