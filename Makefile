-include .env

PYTHON := .venv/bin/python
MODEL ?= chatwm/qwen3.5-9b

export CHATWM_TOKEN
export MINIO_ROOT_USER MINIO_ROOT_PASSWORD
export AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_DEFAULT_REGION

.PHONY: setup clean opencode homework verify

setup:
	@command -v python3.11 >/dev/null || { echo "Ошибка: нужен Python 3.11"; exit 1; }
	@command -v opencode >/dev/null || { echo "Ошибка: нужен OpenCode"; exit 1; }
	@command -v docker >/dev/null || { echo "Ошибка: нужен Docker"; exit 1; }
	@python3.11 -m venv --clear .venv
	@$(PYTHON) -m pip install -r requirements.txt
	@$(PYTHON) agent/install.py
	@docker compose up -d

clean:
	@python3 demo/reset.py

opencode:
	@test -n "$$CHATWM_TOKEN" || { echo "Ошибка: задайте CHATWM_TOKEN в .env"; exit 1; }
	@test -d demo/workspace || { echo "Ошибка: сначала запустите make clean"; exit 1; }
	@OPENCODE_CONFIG="$(CURDIR)/opencode.json" \
		opencode demo/workspace -m "$(MODEL)"

homework:
	@test -n "$$CHATWM_TOKEN" || { echo "Ошибка: задайте CHATWM_TOKEN в .env"; exit 1; }
	@test -n "$$AWS_ACCESS_KEY_ID" || { echo "Ошибка: задайте AWS_ACCESS_KEY_ID в .env"; exit 1; }
	@test -n "$$AWS_SECRET_ACCESS_KEY" || { echo "Ошибка: задайте AWS_SECRET_ACCESS_KEY в .env"; exit 1; }
	@time $(PYTHON) demo/run.py --model "$(MODEL)"
	@$(PYTHON) demo/verify.py

verify:
	@$(PYTHON) demo/verify.py
